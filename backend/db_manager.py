"""
Database manager for MAGIN application.

Handles SQLite database operations including initialization, saving judgments,
and retrieving history.
"""
import sqlite3
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import json

from backend.config import DB_PATH


logger = logging.getLogger(__name__)


def init_db(db_path: str = DB_PATH) -> None:
    """
    Initialize SQLite database and create tables if they don't exist.

    Creates the data/ directory if it doesn't exist and sets up the
    judgments table with proper schema and indexes.

    Args:
        db_path: Path to SQLite database file (default from config.DB_PATH)
    """
    # Create data directory if it doesn't exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logger.info(f"Created database directory: {db_dir}")

    # Connect and create table
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create judgments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS judgments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue TEXT NOT NULL,
            result TEXT NOT NULL,
            avg_severity REAL NOT NULL,

            claude_decision TEXT,
            claude_severity INTEGER,
            claude_reason TEXT,
            claude_concerns TEXT,
            claude_elapsed REAL,

            gemini_decision TEXT,
            gemini_severity INTEGER,
            gemini_reason TEXT,
            gemini_concerns TEXT,
            gemini_elapsed REAL,

            chatgpt_decision TEXT,
            chatgpt_severity INTEGER,
            chatgpt_reason TEXT,
            chatgpt_concerns TEXT,
            chatgpt_elapsed REAL,

            reasoning TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create index for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_created_at
        ON judgments(created_at DESC)
    """)

    # Add persona columns if they don't exist (v1.1 migration)
    # Check if persona columns exist
    cursor.execute("PRAGMA table_info(judgments)")
    columns = [row[1] for row in cursor.fetchall()]

    if "persona_claude" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN persona_claude TEXT")
        logger.info("Added persona_claude column to judgments table")

    if "persona_gemini" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN persona_gemini TEXT")
        logger.info("Added persona_gemini column to judgments table")

    if "persona_chatgpt" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN persona_chatgpt TEXT")
        logger.info("Added persona_chatgpt column to judgments table")

    # Add engine/model columns if they don't exist (v1.3 migration)
    if "engine_claude" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN engine_claude TEXT")
        logger.info("Added engine_claude column to judgments table")

    if "engine_gemini" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN engine_gemini TEXT")
        logger.info("Added engine_gemini column to judgments table")

    if "engine_chatgpt" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN engine_chatgpt TEXT")
        logger.info("Added engine_chatgpt column to judgments table")

    if "model_claude" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN model_claude TEXT")
        logger.info("Added model_claude column to judgments table")

    if "model_gemini" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN model_gemini TEXT")
        logger.info("Added model_gemini column to judgments table")

    if "model_chatgpt" not in columns:
        cursor.execute("ALTER TABLE judgments ADD COLUMN model_chatgpt TEXT")
        logger.info("Added model_chatgpt column to judgments table")

    conn.commit()
    conn.close()

    logger.info(f"Database initialized successfully at {db_path}")


def save_judgment(judgment: Dict[str, Any], db_path: str = DB_PATH) -> int:
    """
    Save a judgment result to the database.

    Args:
        judgment: Dictionary containing judgment data with structure:
            {
                "issue": str,
                "result": str,
                "avg_severity": float,  # DEPRECATED: Actually stores judgment_severity (max logic, not average)
                "judgment_severity": float,  # The actual judgment severity (max of AI severities)
                "claude": Optional[Dict] with {decision, severity, reason, concerns, elapsed_seconds},
                "gemini": Optional[Dict],
                "chatgpt": Optional[Dict],
                "reasoning": str,
                "persona_names": Optional[Dict] with {claude, gemini, chatgpt}
            }
        db_path: Path to SQLite database file (default from config.DB_PATH)

    Returns:
        ID of the inserted row

    Raises:
        Exception: If database operation fails (logged but not suppressed)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Extract AI responses (may be None if AI failed)
        claude = judgment.get("claude")
        gemini = judgment.get("gemini")
        chatgpt = judgment.get("chatgpt")

        # Extract persona names (v1.1)
        persona_names = judgment.get("persona_names", {})
        persona_claude = persona_names.get("claude")
        persona_gemini = persona_names.get("gemini")
        persona_chatgpt = persona_names.get("chatgpt")

        # Helper function to serialize concerns list
        def serialize_concerns(ai_data: Optional[Dict]) -> Optional[str]:
            if ai_data and "concerns" in ai_data:
                return json.dumps(ai_data["concerns"])
            return None

        # IMPORTANT: avg_severity column stores judgment_severity (max logic) for backward compatibility
        # judgment_severity is the correct value to save (not avg_severity)
        severity_to_save = judgment.get("judgment_severity", judgment.get("avg_severity", 0.0))

        # Extract engine and model info
        ai_engines = judgment.get("ai_engines", {})
        ai_models = judgment.get("ai_models", {})

        cursor.execute("""
            INSERT INTO judgments (
                issue, result, avg_severity,
                claude_decision, claude_severity, claude_reason, claude_concerns, claude_elapsed,
                gemini_decision, gemini_severity, gemini_reason, gemini_concerns, gemini_elapsed,
                chatgpt_decision, chatgpt_severity, chatgpt_reason, chatgpt_concerns, chatgpt_elapsed,
                reasoning,
                persona_claude, persona_gemini, persona_chatgpt,
                engine_claude, engine_gemini, engine_chatgpt,
                model_claude, model_gemini, model_chatgpt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            judgment["issue"],
            judgment["result"],
            severity_to_save,  # Save judgment_severity in avg_severity column

            claude["decision"] if claude else None,
            claude["severity"] if claude else None,
            claude["reason"] if claude else None,
            serialize_concerns(claude),
            claude["elapsed_seconds"] if claude else None,

            gemini["decision"] if gemini else None,
            gemini["severity"] if gemini else None,
            gemini["reason"] if gemini else None,
            serialize_concerns(gemini),
            gemini["elapsed_seconds"] if gemini else None,

            chatgpt["decision"] if chatgpt else None,
            chatgpt["severity"] if chatgpt else None,
            chatgpt["reason"] if chatgpt else None,
            serialize_concerns(chatgpt),
            chatgpt["elapsed_seconds"] if chatgpt else None,

            judgment["reasoning"],

            persona_claude,
            persona_gemini,
            persona_chatgpt,

            ai_engines.get("claude"),
            ai_engines.get("gemini"),
            ai_engines.get("chatgpt"),

            ai_models.get("claude"),
            ai_models.get("gemini"),
            ai_models.get("chatgpt")
        ))

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Judgment saved successfully with ID: {row_id}")
        return row_id

    except Exception as e:
        logger.error(f"Failed to save judgment: {e}", exc_info=True)
        raise


def get_history(limit: int = 10, offset: int = 0, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Retrieve paginated judgment history from the database.

    Args:
        limit: Maximum number of records to return (default: 10)
        offset: Number of records to skip (default: 0)
        db_path: Path to SQLite database file (default from config.DB_PATH)

    Returns:
        Dictionary with structure:
        {
            "total": int,           # Total number of records
            "items": List[Dict],    # List of judgment records
            "limit": int,           # Requested limit
            "offset": int           # Requested offset
        }
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()

        # Get total count
        cursor.execute("SELECT COUNT(*) as count FROM judgments")
        total = cursor.fetchone()["count"]

        # Get paginated items (most recent first)
        cursor.execute("""
            SELECT * FROM judgments
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        rows = cursor.fetchall()

        # Convert rows to dictionaries
        items = []
        for row in rows:
            item = dict(row)

            # Deserialize concerns JSON strings back to lists
            for ai_name in ["claude", "gemini", "chatgpt"]:
                concerns_key = f"{ai_name}_concerns"
                if item[concerns_key]:
                    try:
                        item[concerns_key] = json.loads(item[concerns_key])
                    except json.JSONDecodeError:
                        item[concerns_key] = []

            # Reconstruct ai_engines and ai_models objects (v1.3)
            item["ai_engines"] = {
                "claude": item.get("engine_claude"),
                "gemini": item.get("engine_gemini"),
                "chatgpt": item.get("engine_chatgpt")
            }
            item["ai_models"] = {
                "claude": item.get("model_claude"),
                "gemini": item.get("model_gemini"),
                "chatgpt": item.get("model_chatgpt")
            }

            items.append(item)

        conn.close()

        logger.info(f"Retrieved {len(items)} history items (offset: {offset}, limit: {limit})")

        return {
            "total": total,
            "items": items,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Failed to retrieve history: {e}", exc_info=True)
        raise


def get_judgment_by_id(judgment_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific judgment by its ID.

    Args:
        judgment_id: ID of the judgment to retrieve
        db_path: Path to SQLite database file (default from config.DB_PATH)

    Returns:
        Dictionary containing judgment data, or None if not found
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM judgments WHERE id = ?", (judgment_id,))
        row = cursor.fetchone()

        conn.close()

        if row is None:
            logger.warning(f"Judgment ID {judgment_id} not found")
            return None

        # Convert row to dictionary
        item = dict(row)

        # Convert flat structure to nested structure for API response
        def build_ai_response(ai_name: str) -> Optional[Dict]:
            decision = item.get(f"{ai_name}_decision")
            if not decision:
                return None

            concerns_str = item.get(f"{ai_name}_concerns")
            concerns = []
            if concerns_str:
                try:
                    concerns = json.loads(concerns_str)
                except json.JSONDecodeError:
                    concerns = []

            # Check if this is a failed AI response
            if decision == "FAILED":
                return {
                    "failed": True,
                    "error": item.get(f"{ai_name}_reason") or "AI request failed",
                    "raw_output": item.get(f"{ai_name}_reason") or ""
                }

            return {
                "scores": {
                    "validity": 0.0,
                    "feasibility": 0.0,
                    "risk": 0.0,
                    "certainty": 0.0
                },
                "average_score": 0.0,
                "decision": decision,
                "severity": item.get(f"{ai_name}_severity") or 0,
                "reason": item.get(f"{ai_name}_reason") or "",
                "reasoning": item.get(f"{ai_name}_reason") or "",  # Alias for frontend compatibility
                "concerns": concerns,
                "hard_flag": "none",
                "elapsed_seconds": item.get(f"{ai_name}_elapsed") or 0.0
            }

        # Build nested structure
        # IMPORTANT: avg_severity column actually stores judgment_severity (max logic)
        judgment_severity = item["avg_severity"]  # This is actually judgment_severity

        result = {
            "id": item["id"],
            "issue": item["issue"],
            "result": item["result"],
            "avg_severity": judgment_severity,  # Keep for backward compatibility
            "judgment_severity": judgment_severity,  # This is the correct value
            "severity_level": None,  # Not stored in DB, will be calculated
            "claude": build_ai_response("claude"),
            "gemini": build_ai_response("gemini"),
            "chatgpt": build_ai_response("chatgpt"),
            "reasoning": item["reasoning"],
            "created_at": item["created_at"],
            "persona_names": {
                "claude": item.get("persona_claude"),
                "gemini": item.get("persona_gemini"),
                "chatgpt": item.get("persona_chatgpt")
            },
            "ai_engines": {
                "claude": item.get("engine_claude"),
                "gemini": item.get("engine_gemini"),
                "chatgpt": item.get("engine_chatgpt")
            },
            "ai_models": {
                "claude": item.get("model_claude"),
                "gemini": item.get("model_gemini"),
                "chatgpt": item.get("model_chatgpt")
            }
        }

        logger.info(f"Retrieved judgment ID {judgment_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve judgment {judgment_id}: {e}", exc_info=True)
        raise
