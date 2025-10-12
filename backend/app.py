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

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.db_manager import get_history, get_judgment_by_id, init_db, save_judgment
from backend.magi_orchestrator import PERSONAS, generate_plain_text_output, run_parallel_judgment
from backend.models import ErrorResponse, JudgmentModel, JudgmentRequest
from backend.severity_judge import judge_issue
from backend.config_manager import load_user_config, save_user_config, load_env, save_env

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
    version="1.4.0",
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

# Mount static files (CSS, JS, sounds)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    logger.info(f"Static files mounted from: {FRONTEND_DIR}")

    # Mount sounds directory separately for cleaner URL paths
    SOUNDS_DIR = FRONTEND_DIR / "sounds"
    if SOUNDS_DIR.exists():
        app.mount("/sounds", StaticFiles(directory=str(SOUNDS_DIR)), name="sounds")
        logger.info(f"Sound files mounted from: {SOUNDS_DIR}")
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
# Task 7 (v1.2): GET /api/personas Endpoint
# ============================================================

def validate_persona_ids(persona_ids: Optional[List[str]]) -> List[str]:
    """
    Validate and normalize persona_ids list.

    Rules:
    1. If None or empty, return default persona IDs
    2. If length != 3, pad with defaults or truncate to 3
    3. Replace invalid IDs with corresponding defaults
    4. Return exactly 3 valid persona IDs

    Args:
        persona_ids: Optional list of persona IDs

    Returns:
        List[str]: Exactly 3 valid persona IDs

    Example:
        >>> validate_persona_ids(None)
        ['neutral_ai', 'neutral_ai', 'neutral_ai']
        >>> validate_persona_ids(['invalid', 'researcher', 'mother'])
        ['neutral_ai', 'researcher', 'mother']
        >>> validate_persona_ids(['AI'])
        ['AI', 'neutral_ai', 'neutral_ai']
    """
    from backend.magi_orchestrator import DEFAULT_PERSONA_IDS

    # Default values
    defaults = [
        DEFAULT_PERSONA_IDS["ai1"],
        DEFAULT_PERSONA_IDS["ai2"],
        DEFAULT_PERSONA_IDS["ai3"]
    ]

    # Handle None or empty list
    if not persona_ids:
        logger.info("Using default persona IDs: %s", defaults)
        return defaults

    # Normalize to exactly 3 elements
    normalized = list(persona_ids)[:3]  # Truncate if > 3
    while len(normalized) < 3:  # Pad if < 3
        normalized.append(defaults[len(normalized)])

    # Replace invalid IDs with defaults
    validated = []
    for i, persona_id in enumerate(normalized):
        if persona_id in PERSONAS:
            validated.append(persona_id)
            logger.debug(f"Persona {i+1}: {persona_id} (valid)")
        else:
            validated.append(defaults[i])
            logger.warning(f"Invalid persona_id '{persona_id}' at index {i}, using default: {defaults[i]}")

    logger.info(f"Validated persona IDs: {validated}")
    return validated


# ============================================================
# Task 7 (v1.2): GET /api/personas Endpoint
# ============================================================

@app.get(
    "/api/personas",
    responses={
        200: {"description": "Persona list retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Failed to load personas"}
    },
    summary="Retrieve all available personas",
    description="""
    Retrieve a list of all 41 available personas for AI judgment.

    **Response**:
    - personas: List of {id, name} objects sorted in 五十音順 (Japanese syllabary order)

    **Error Handling**:
    - Returns 500 if personas.json fails to load or PERSONAS is empty

    **Example Response**:
    ```json
    {
      "personas": [
        {"id": "AI", "name": "人間は愚かだと結論し、人類を滅ぼそうとするAI"},
        {"id": "ITベンチャー", "name": "意識高い系の発言が多いITベンチャー企業の社長"},
        ...
      ]
    }
    ```
    """
)
async def get_personas():
    """
    Retrieve all personas sorted in 五十音順.

    Returns:
        dict: {"personas": [{"id": str, "name": str}, ...]}

    Raises:
        HTTPException: 500 if PERSONAS is empty or not loaded

    Implementation:
        1. Check PERSONAS is loaded
        2. Extract {id, name} from each persona
        3. Sort by persona_name in 五十音順 (Japanese collation)
        4. Return as JSON array
    """
    try:
        if not PERSONAS:
            logger.error("PERSONAS variable is empty or not loaded")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "PERSONAS NOT LOADED",
                    "details": ["personas.json failed to load during startup"]
                }
            )

        # Build persona list: [{id, name}, ...]
        persona_list = [
            {"id": persona_id, "name": persona_data["persona_name"]}
            for persona_id, persona_data in PERSONAS.items()
        ]

        # Sort by persona_name in Japanese collation (五十音順)
        # Python's default sort handles Japanese characters correctly
        persona_list.sort(key=lambda x: x["name"])

        logger.info(f"Retrieved {len(persona_list)} personas")

        return {"personas": persona_list}

    except HTTPException:
        # Re-raise HTTP exceptions
        raise

    except Exception as e:
        logger.error(f"Failed to retrieve personas: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "PERSONAS RETRIEVAL FAILED",
                "details": [str(e)]
            }
        )


# ============================================================
# Task 2.2.1 (v1.3 Phase 2): GET /api/config Endpoint
# ============================================================

@app.get(
    "/api/config",
    responses={
        200: {"description": "Configuration retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Failed to load configuration"}
    },
    summary="Retrieve user configuration",
    description="""
    Retrieve user configuration from config/user_config.json.

    **Response**:
    - nodes: List of node configurations (engine, model, persona_id)

    **Error Handling**:
    - Returns default configuration if user_config.json does not exist
    - Returns 500 if configuration is corrupted

    **Example Response**:
    ```json
    {
      "nodes": [
        {
          "id": 1,
          "name": "NODE 1",
          "engine": "Claude",
          "model": null,
          "persona_id": "researcher"
        },
        ...
      ]
    }
    ```
    """
)
async def get_config():
    """
    Retrieve user configuration.

    Returns:
        dict: User configuration from config/user_config.json or default config

    Example:
        >>> config = await get_config()
        >>> len(config["nodes"])
        3
    """
    try:
        config = load_user_config()
        logger.info(f"Configuration retrieved: {len(config.get('nodes', []))} nodes")
        return config

    except Exception as e:
        logger.error(f"Failed to load configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "CONFIGURATION LOAD FAILED",
                "details": [str(e)]
            }
        )


# ============================================================
# Task 2.2.2 (v1.3 Phase 2): POST /api/config Endpoint
# ============================================================

@app.post(
    "/api/config",
    responses={
        200: {"description": "Configuration saved successfully"},
        400: {"model": ErrorResponse, "description": "Invalid configuration"},
        500: {"model": ErrorResponse, "description": "Failed to save configuration"}
    },
    summary="Save user configuration",
    description="""
    Save user configuration to config/user_config.json.

    **Request Body**:
    - nodes: List of exactly 3 node configurations

    **Validation**:
    - Exactly 3 nodes required
    - Each node must have: id, name, engine, model, persona_id

    **Error Handling**:
    - Returns 400 if validation fails
    - Returns 500 if file write fails
    """
)
async def post_config(config: dict):
    """
    Save user configuration.

    Args:
        config: Configuration dictionary with "nodes" field

    Returns:
        dict: {"status": "ok"}

    Raises:
        HTTPException: 400 if validation fails, 500 if save fails

    Example:
        >>> config = {"nodes": [...]}
        >>> response = await post_config(config)
        >>> response["status"]
        'ok'
    """
    try:
        # Validate and save configuration
        save_user_config(config)
        logger.info("Configuration saved successfully")
        return {"status": "ok"}

    except ValueError as e:
        # Validation error
        logger.error(f"Configuration validation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID CONFIGURATION",
                "details": [str(e)]
            }
        )

    except Exception as e:
        # File write error
        logger.error(f"Failed to save configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "CONFIGURATION SAVE FAILED",
                "details": [str(e)]
            }
        )


# ============================================================
# Task 2.2.2 (v1.3 Phase 2): GET /api/env Endpoint
# ============================================================

@app.get(
    "/api/env",
    responses={
        200: {"description": "Environment variables retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Failed to read .env file"}
    },
    summary="Get environment variables",
    description="Retrieve current environment variables from .env file (keys only, no values exposed)"
)
async def get_env_endpoint():
    """
    Get environment variables from .env file.

    Returns:
        dict: Environment variables with keys indicating if set (values masked)
    """
    try:
        from backend.config_manager import load_env

        env = load_env()

        # Return keys with boolean indicators (don't expose actual values)
        return {
            "GEMINI_API_KEY": bool(env.get("GEMINI_API_KEY")),
            "OPENROUTER_API_KEY": bool(env.get("OPENROUTER_API_KEY")),
            "OLLAMA_URL": env.get("OLLAMA_URL", "http://localhost:11434")
        }

    except Exception as e:
        logger.error(f"Failed to read environment variables: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "ENV READ FAILED",
                "details": [str(e)]
            }
        )


# ============================================================
# Task 2.2.3 (v1.3 Phase 2): POST /api/save-env Endpoint
# ============================================================

@app.post(
    "/api/save-env",
    responses={
        200: {"description": "Environment variables saved successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Failed to save .env file"}
    },
    summary="Save environment variables",
    description="""
    Save environment variables to .env file.

    **Request Body**:
    - GEMINI_API_KEY: Gemini API key (optional)
    - OPENROUTER_API_KEY: OpenRouter API key (optional)
    - OLLAMA_URL: Ollama server URL (optional, default: http://localhost:11434)

    **File Format**:
    - KEY="value" format
    - Auto-generated comment header

    **Error Handling**:
    - Returns 500 if file write fails
    """
)
async def save_env_endpoint(env_vars: dict):
    """
    Save environment variables to .env file.

    Args:
        env_vars: Dictionary with API keys and URLs

    Returns:
        dict: {"status": "ok"}

    Raises:
        HTTPException: 500 if file write fails

    Example:
        >>> env_vars = {
        ...     "GEMINI_API_KEY": "test_key",
        ...     "OPENROUTER_API_KEY": "test_key2",
        ...     "OLLAMA_URL": "http://localhost:11434"
        ... }
        >>> response = await save_env_endpoint(env_vars)
        >>> response["status"]
        'ok'
    """
    try:
        # Load existing env and merge with new values
        from backend.config_manager import load_env

        existing_env = load_env()

        # Merge: keep existing values, update only provided ones
        merged_env = {
            "GEMINI_API_KEY": env_vars.get("GEMINI_API_KEY", existing_env.get("GEMINI_API_KEY")),
            "OPENROUTER_API_KEY": env_vars.get("OPENROUTER_API_KEY", existing_env.get("OPENROUTER_API_KEY")),
            "OLLAMA_URL": env_vars.get("OLLAMA_URL", existing_env.get("OLLAMA_URL", "http://localhost:11434"))
        }

        # Save merged environment variables
        save_env(merged_env)
        logger.info("Environment variables saved successfully")
        return {"status": "ok"}

    except Exception as e:
        # File write error
        logger.error(f"Failed to save .env file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "ENV SAVE FAILED",
                "details": [str(e)]
            }
        )


# ============================================================
# Task 2.2.4 (v1.3 Phase 2): POST /api/test-connections Endpoint
# ============================================================

@app.post(
    "/api/test-connections",
    responses={
        200: {"description": "Connection tests completed"},
        500: {"model": ErrorResponse, "description": "Test execution failed"}
    },
    summary="Test AI engine connections",
    description="""
    Test connections to all configured AI engines.

    **Process**:
    1. Load configuration from config/user_config.json
    2. Send test prompt to each NODE: "OKとだけ返答してください"
    3. Timeout: 30 seconds per engine
    4. Return results with status and response time

    **Response**:
    - results: List of test results for each NODE
      - node_id: NODE ID
      - engine: Engine type
      - model: Model name
      - status: "ok" | "error"
      - response_time_ms: Response time in milliseconds
      - error: Error message (if status == "error")

    **Example Response**:
    ```json
    {
      "results": [
        {
          "node_id": 1,
          "engine": "Claude",
          "model": null,
          "status": "ok",
          "response_time_ms": 1523,
          "error": null
        },
        {
          "node_id": 2,
          "engine": "API_Gemini",
          "model": "gemini-2.5-flash",
          "status": "error",
          "response_time_ms": 0,
          "error": "GEMINI_API_KEY not set"
        }
      ]
    }
    ```
    """
)
async def test_connections_endpoint():
    """
    Test connections to all configured AI engines.

    Returns:
        dict: Test results for each NODE

    Example:
        >>> response = await test_connections_endpoint()
        >>> len(response["results"])
        3
        >>> response["results"][0]["status"]
        'ok'
    """
    try:
        # Load configuration
        config = load_user_config()
        nodes = config.get("nodes", [])

        if not nodes:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "NO NODES CONFIGURED",
                    "details": ["Configuration has no nodes"]
                }
            )

        # Test prompt (simple judgment format)
        test_prompt = """以下のJSON形式で返答してください:
{
  "decision": "PASS",
  "severity": 0,
  "scores": {"validity": 1.0, "feasibility": 1.0, "risk": 0.0, "certainty": 1.0},
  "reason": "接続テスト成功"
}"""
        timeout = 300

        # Test each node
        async def test_node(node):
            from datetime import datetime
            # Import call_ai here to avoid circular import
            from backend.ai_factory import call_ai

            start_time = datetime.now()

            try:
                result = await call_ai(
                    engine=node.get("engine", "Claude"),
                    model=node.get("model"),
                    prompt=test_prompt,
                    timeout=timeout
                )

                elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                return {
                    "node_id": node.get("id", 0),
                    "engine": node.get("engine", ""),
                    "model": node.get("model"),
                    "status": "ok" if result.get("success") else "error",
                    "response_time_ms": elapsed_ms,
                    "error": result.get("error")
                }

            except Exception as e:
                elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                return {
                    "node_id": node.get("id", 0),
                    "engine": node.get("engine", ""),
                    "model": node.get("model"),
                    "status": "error",
                    "response_time_ms": elapsed_ms,
                    "error": str(e)
                }

        # Execute tests in parallel
        tasks = [test_node(node) for node in nodes]
        results = await asyncio.gather(*tasks)

        logger.info(f"Connection tests completed: {len(results)} nodes tested")
        return {"results": results}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to execute connection tests: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "TEST EXECUTION FAILED",
                "details": [str(e)]
            }
        )


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
        logger.info(f"Received judgment request: issue='{request.issue[:50]}...', simple_mode={request.simple_mode}, persona_ids={request.persona_ids}")

        # Validate and normalize persona_ids
        validated_persona_ids = validate_persona_ids(request.persona_ids)

        # Execute judgment with persona_ids
        judgment = await judge_issue(request.issue, persona_ids=validated_persona_ids)

        # Populate persona_names in response
        # NODE 1 → gemini, NODE 2 → claude, NODE 3 → chatgpt (fixed mapping for legacy compatibility)
        if validated_persona_ids:
            judgment.persona_names = {
                "gemini": PERSONAS[validated_persona_ids[0]]["persona_name"],
                "claude": PERSONAS[validated_persona_ids[1]]["persona_name"],
                "chatgpt": PERSONAS[validated_persona_ids[2]]["persona_name"]
            }
            logger.info(f"Persona names populated: {judgment.persona_names}")

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
async def judge_stream_endpoint(
    issue: str = Query(..., min_length=1, max_length=2000),
    persona_ids: Optional[str] = Query(None, description="JSON array of 3 persona IDs")
):
    """
    SSE endpoint for real-time judgment updates.

    Args:
        issue: Issue text to judge
        persona_ids: Optional JSON array of 3 persona IDs (e.g., '["neutral_ai","neutral_ai","neutral_ai"]')

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
                # Parse and validate persona_ids
                parsed_persona_ids = None
                if persona_ids:
                    try:
                        parsed_persona_ids = json.loads(persona_ids)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid persona_ids JSON: {persona_ids}")

                validated_persona_ids = validate_persona_ids(parsed_persona_ids)
                logger.info(f"SSE endpoint using persona_ids: {validated_persona_ids}")

                # Use the full judge_issue flow but with callback
                from backend.severity_judge import _compute_final_severity, check_hard_flags, calculate_final_result

                # Get AI responses with callback
                responses = await run_parallel_judgment(issue, persona_ids=validated_persona_ids, on_ai_complete=on_ai_complete)

                # Calculate judgment severity (use new max logic)
                judgment_severity = _compute_final_severity(responses)

                # Check hard flags
                hard_flags = check_hard_flags(responses)

                # Calculate final result
                result, reasoning, severity_level, total_score = calculate_final_result(responses, judgment_severity, hard_flags)

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

                # Populate persona_names
                # NODE 1 → gemini, NODE 2 → claude, NODE 3 → chatgpt (fixed mapping for legacy compatibility)
                persona_names = None
                if validated_persona_ids:
                    persona_names = {
                        "gemini": PERSONAS[validated_persona_ids[0]]["persona_name"],
                        "claude": PERSONAS[validated_persona_ids[1]]["persona_name"],
                        "chatgpt": PERSONAS[validated_persona_ids[2]]["persona_name"]
                    }
                    logger.info(f"SSE persona names populated: {persona_names}")

                # Extract engine and model info from responses (v1.3)
                ai_engines = {}
                ai_models = {}
                if len(responses) > 0:
                    ai_engines["gemini"] = responses[0].get("engine")
                    ai_models["gemini"] = responses[0].get("model")
                if len(responses) > 1:
                    ai_engines["claude"] = responses[1].get("engine")
                    ai_models["claude"] = responses[1].get("model")
                if len(responses) > 2:
                    ai_engines["chatgpt"] = responses[2].get("engine")
                    ai_models["chatgpt"] = responses[2].get("model")

                judgment_data = {
                    "issue": issue,
                    "result": result,
                    "reasoning": reasoning,
                    "severity_level": severity_level,
                    "total_score": total_score,
                    "judgment_severity": judgment_severity,
                    "avg_severity": judgment_severity,  # avg_severity required by db_manager
                    # NODE 1 → gemini, NODE 2 → claude, NODE 3 → chatgpt (fixed mapping for legacy compatibility)
                    "gemini": extract_ai_data(responses[0]) if len(responses) > 0 else None,
                    "claude": extract_ai_data(responses[1]) if len(responses) > 1 else None,
                    "chatgpt": extract_ai_data(responses[2]) if len(responses) > 2 else None,
                    "persona_names": persona_names,  # Add persona_names (v1.1)
                    "ai_engines": ai_engines,  # Add ai_engines (v1.3)
                    "ai_models": ai_models  # Add ai_models (v1.3)
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
                    "total_score": total_score,
                    "judgment_severity": judgment_severity,  # Add judgment_severity to SSE response
                    "responses": responses,
                    "persona_names": persona_names
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
