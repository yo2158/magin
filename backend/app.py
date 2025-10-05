"""
MAGIN FastAPI Application

This module implements the FastAPI backend for MAGIN (Multi-AI Governance Interfaces Node).

Endpoints:
- POST /api/judge: Execute judgment with 3 AIs in parallel
- GET /api/history: Retrieve judgment history with pagination

Features:
- Simple mode support (plain text output)
- CORS middleware for localhost development
- Global error handling
- Database initialization on startup
- Comprehensive request/response validation

Implements Tasks 20-23 from Phase 6: FastAPI Endpoints
"""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.db_manager import get_history, get_judgment_by_id, init_db, save_judgment
from backend.magi_orchestrator import generate_plain_text_output, run_parallel_judgment
from backend.models import ErrorResponse, JudgmentModel, JudgmentRequest
from backend.severity_judge import judge_issue

# ============================================================
# Task 20: FastAPI Application Setup
# ============================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title="MAGIN API",
    description="Multi-AI Governance Interfaces Node - AI-powered decision support system",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)


# ============================================================
# Task 23: CORS Middleware Configuration
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Static Files Configuration
# ============================================================

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Mount static files (CSS, JS)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    logger.info(f"Static files mounted from: {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend directory not found: {FRONTEND_DIR}")


# ============================================================
# Root Endpoint - Serve Frontend
# ============================================================

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """
    Serve the frontend index.html at root path.

    Returns:
        FileResponse: index.html file
    """
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    else:
        raise HTTPException(status_code=404, detail="Frontend not found")


# ============================================================
# Task 23: Startup Event - Database Initialization
# ============================================================

@app.on_event("startup")
async def startup_event():
    """
    Initialize database on application startup.

    Creates data directory and judgments table if they don't exist.
    """
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise


# ============================================================
# Task 21: POST /api/judge Endpoint
# ============================================================

@app.post(
    "/api/judge",
    response_model=JudgmentModel,
    responses={
        200: {"description": "Judgment completed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Judgment failed"}
    },
    summary="Execute judgment with AI consensus",
    description="""
    Execute judgment on an issue using Claude, Gemini, and ChatGPT in parallel.

    **Process**:
    1. Validates input (10-2000 chars, no dangerous characters)
    2. Executes 3 AIs in parallel with timeout handling
    3. Calculates final verdict using weighted scoring
    4. Saves to database
    5. Returns complete judgment with reasoning

    **Simple Mode**:
    - If simple_mode=true, generates plain text output
    - Useful for non-browser clients (CLI, API testing)

    **Error Handling**:
    - Returns 400 if input validation fails
    - Returns 500 if fewer than 2 AIs respond successfully
    - Returns 500 if database save fails
    """
)
async def judge_endpoint(request: JudgmentRequest) -> JudgmentModel:
    """
    Execute judgment endpoint with simple_mode support.

    Args:
        request: JudgmentRequest with issue text and simple_mode flag

    Returns:
        JudgmentModel: Complete judgment result

    Raises:
        HTTPException: 500 if judgment fails or insufficient AI responses

    Example:
        >>> # Normal mode
        >>> response = await judge_endpoint(JudgmentRequest(
        ...     issue="新機能を実装すべきか？",
        ...     simple_mode=False
        ... ))
        >>> response.result
        '承認'

        >>> # Simple mode
        >>> response = await judge_endpoint(JudgmentRequest(
        ...     issue="新機能を実装すべきか？",
        ...     simple_mode=True
        ... ))
        >>> response.plain_text_output
        '========================================...'
    """
    try:
        logger.info(f"Received judgment request: issue='{request.issue[:50]}...', simple_mode={request.simple_mode}")

        # Execute judgment
        judgment = await judge_issue(request.issue)

        # Generate plain text output if simple mode enabled
        if request.simple_mode:
            logger.info("Generating plain text output for simple mode")
            plain_text = generate_plain_text_output({
                "issue": judgment.issue,
                "result": judgment.result,
                "reasoning": judgment.reasoning,
                "severity_level": judgment.severity_level,
                "judgment_severity": judgment.judgment_severity,
                "claude": judgment.claude.dict() if judgment.claude else None,
                "gemini": judgment.gemini.dict() if judgment.gemini else None,
                "chatgpt": judgment.chatgpt.dict() if judgment.chatgpt else None
            })
            judgment.plain_text_output = plain_text

        # Save to database
        try:
            judgment_id = save_judgment(judgment.dict())
            judgment.id = judgment_id
            logger.info(f"Judgment saved with ID: {judgment_id}")
        except Exception as db_error:
            logger.error(f"Failed to save judgment to database: {db_error}", exc_info=True)
            # Continue even if database save fails (non-critical)

        logger.info(f"Judgment completed successfully: result={judgment.result}")
        return judgment

    except ValueError as e:
        # Insufficient AI responses (< 2 successful)
        error_msg = str(e)
        logger.error(f"Judgment validation error: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INSUFFICIENT AI RESPONSES",
                "details": [error_msg]
            }
        )

    except Exception as e:
        # Unexpected errors
        logger.error(f"Judgment execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "JUDGMENT FAILED",
                "details": [str(e)]
            }
        )


# ============================================================
# SSE Endpoint: GET /api/judge/stream
# ============================================================

@app.get(
    "/api/judge/stream",
    responses={
        200: {"description": "SSE stream of judgment progress"},
        400: {"model": ErrorResponse, "description": "Invalid request"}
    },
    summary="Execute judgment with real-time SSE updates",
    description="""
    Execute judgment with Server-Sent Events (SSE) for real-time progress updates.

    **Process**:
    1. Validates input (10-2000 chars)
    2. Streams AI completion events as they finish
    3. Sends final verdict when all AIs complete

    **Event Types**:
    - ai_complete: Individual AI finished (data: {ai, result})
    - final_result: All AIs finished (data: {result, reasoning, severity_level})
    - error: Error occurred (data: {error, details})
    """
)
async def judge_stream_endpoint(issue: str = Query(..., min_length=1, max_length=2000)):
    """
    SSE endpoint for real-time judgment updates.

    Args:
        issue: Issue text to judge

    Yields:
        SSE events with AI completion and final result
    """
    import json
    import asyncio
    from queue import Queue
    from threading import Thread

    async def event_generator():
        event_queue = asyncio.Queue()

        def on_ai_complete(ai_name: str, result: dict):
            # Thread-safe event queuing
            # Normalize AI name to lowercase for frontend compatibility
            asyncio.create_task(event_queue.put({
                "type": "ai_complete",
                "ai": ai_name.lower(),
                "result": result
            }))

        # Start judgment with callback
        async def run_judgment():
            try:
                # Use the full judge_issue flow but with callback
                from backend.severity_judge import calculate_judgment_severity, check_hard_flags, calculate_final_result

                # Get AI responses with callback
                responses = await run_parallel_judgment(issue, on_ai_complete=on_ai_complete)

                # Calculate judgment severity
                judgment_severity = calculate_judgment_severity(responses)

                # Check hard flags
                hard_flags = check_hard_flags(responses)

                # Calculate final result
                result, reasoning, severity_level = calculate_final_result(responses, judgment_severity, hard_flags)

                # Build judgment object for DB save
                from backend.models import JudgmentModel, AIResponseModel

                # Extract AI response data (flatten structure for db_manager)
                def extract_ai_data(resp):
                    if not resp or not resp.get("success"):
                        # Save failure info with special marker
                        return {
                            "decision": "FAILED",
                            "severity": 0,
                            "reason": resp.get("raw_output") or resp.get("error") or "AI request failed" if resp else "No response",
                            "concerns": [],
                            "elapsed_seconds": resp.get("elapsed_seconds", 0) if resp else 0
                        }
                    # Merge response data with top-level fields (elapsed_seconds, etc.)
                    response_data = resp.get("response", {})
                    return {
                        **response_data,
                        "elapsed_seconds": resp.get("elapsed_seconds")
                    }

                judgment_data = {
                    "issue": issue,
                    "result": result,
                    "reasoning": reasoning,
                    "severity_level": severity_level,
                    "judgment_severity": judgment_severity,
                    "avg_severity": judgment_severity,  # avg_severity required by db_manager
                    "claude": extract_ai_data(responses[0]) if len(responses) > 0 else None,
                    "gemini": extract_ai_data(responses[1]) if len(responses) > 1 else None,
                    "chatgpt": extract_ai_data(responses[2]) if len(responses) > 2 else None
                }

                # Save to database
                try:
                    judgment_id = save_judgment(judgment_data)
                    logger.info(f"SSE judgment saved with ID: {judgment_id}")
                except Exception as db_error:
                    logger.error(f"Failed to save SSE judgment to database: {db_error}", exc_info=True)

                # Send final result event
                await event_queue.put({
                    "type": "final_result",
                    "result": result,
                    "reasoning": reasoning,
                    "severity_level": severity_level,
                    "responses": responses
                })

                # Signal completion
                await event_queue.put(None)

            except Exception as e:
                logger.error(f"SSE judgment failed: {e}", exc_info=True)
                await event_queue.put({
                    "type": "error",
                    "error": str(e)
                })
                await event_queue.put(None)

        # Start judgment task
        judgment_task = asyncio.create_task(run_judgment())

        # Stream events
        while True:
            event = await event_queue.get()

            if event is None:
                break

            yield f"data: {json.dumps(event)}\n\n"

        # Ensure task completes
        await judgment_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# ============================================================
# Task 22: GET /api/history Endpoint
# ============================================================

@app.get(
    "/api/history",
    response_model=dict,
    responses={
        200: {"description": "History retrieved successfully"},
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Database error"}
    },
    summary="Retrieve judgment history",
    description="""
    Retrieve paginated judgment history from the database.

    **Query Parameters**:
    - limit: Maximum number of records to return (1-100, default: 10)
    - offset: Number of records to skip for pagination (default: 0)

    **Response**:
    - total: Total number of records in database
    - items: List of judgment records (most recent first)
    - limit: Requested limit
    - offset: Requested offset

    **Example**:
    - GET /api/history?limit=20&offset=0 → First 20 records
    - GET /api/history?limit=10&offset=20 → Records 21-30
    """
)
async def history_endpoint(
    limit: int = Query(default=100, ge=1, le=100, description="Maximum records to return (1-100)"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip")
) -> dict:
    """
    Retrieve judgment history with pagination.

    Args:
        limit: Maximum number of records to return (1-100, default: 10)
        offset: Number of records to skip (default: 0)

    Returns:
        dict: {
            "total": int,
            "items": List[Dict],
            "limit": int,
            "offset": int
        }

    Raises:
        HTTPException: 500 if database query fails

    Example:
        >>> response = await history_endpoint(limit=20, offset=0)
        >>> response["total"]
        45
        >>> len(response["items"])
        20
    """
    try:
        logger.info(f"Retrieving history: limit={limit}, offset={offset}")

        history_data = get_history(limit=limit, offset=offset)

        logger.info(
            f"History retrieved successfully: "
            f"{len(history_data['items'])} items, "
            f"total={history_data['total']}"
        )

        return history_data

    except Exception as e:
        logger.error(f"Failed to retrieve history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "DATABASE ERROR",
                "details": [str(e)]
            }
        )


# ============================================================
# Task 23: GET /api/history/{id} Endpoint
# ============================================================

@app.get(
    "/api/history/{id}",
    responses={
        200: {"description": "Judgment retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Judgment not found"},
        500: {"model": ErrorResponse, "description": "Database error"}
    },
    summary="Retrieve judgment by ID",
    description="""
    Retrieve a specific judgment record by its ID.

    **Path Parameters**:
    - id: Judgment record ID (integer)

    **Returns**:
    - Complete judgment record with all AI responses

    **Error Codes**:
    - 404: Judgment with given ID does not exist
    - 500: Database error
    """
)
async def history_detail_endpoint(id: int):
    """
    Retrieve judgment by ID.

    Args:
        id: Judgment record ID

    Returns:
        JudgmentModel: Complete judgment record

    Raises:
        HTTPException: 404 if not found, 500 if database error

    Example:
        >>> response = await history_detail_endpoint(id=1)
        >>> response.result
        '承認'
    """
    try:
        logger.info(f"Retrieving judgment with ID: {id}")

        judgment = get_judgment_by_id(id)

        if judgment is None:
            logger.warning(f"Judgment not found: ID={id}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "NOT FOUND",
                    "details": [f"Judgment with ID {id} does not exist"]
                }
            )

        logger.info(f"Judgment retrieved successfully: ID={id}")
        return judgment

    except HTTPException:
        # Re-raise HTTP exceptions (404)
        raise

    except Exception as e:
        logger.error(f"Failed to retrieve judgment {id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "DATABASE ERROR",
                "details": [str(e)]
            }
        )


# ============================================================
# Task 23: Global Error Handling
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """
    Global exception handler for unhandled errors.

    Catches all exceptions not handled by specific endpoints
    and returns a standardized error response.

    Args:
        request: FastAPI request object
        exc: Exception instance

    Returns:
        JSONResponse: 500 error with error details
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL SERVER ERROR",
            "details": [str(exc)]
        }
    )


# ============================================================
# Health Check Endpoint (Bonus)
# ============================================================

@app.get(
    "/api/health",
    summary="Health check",
    description="Check if the API is running and database is accessible"
)
async def health_check():
    """
    Health check endpoint for monitoring.

    Returns:
        dict: {
            "status": "ok",
            "message": "MAGIN API is running"
        }
    """
    try:
        # Quick database check
        get_history(limit=1)
        return {
            "status": "ok",
            "message": "MAGIN API is running",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "Database connection failed",
                "error": str(e)
            }
        )


# ============================================================
# Application Entry Point
# ============================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting MAGIN API server...")
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
