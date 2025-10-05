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
                "avg_severity": float,
                "claude": Optional[Dict] with {decision, severity, reason, concerns, elapsed_seconds},
                "gemini": Optional[Dict],
                "chatgpt": Optional[Dict],
                "reasoning": str
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

        # Helper function to serialize concerns list
        def serialize_concerns(ai_data: Optional[Dict]) -> Optional[str]:
            if ai_data and "concerns" in ai_data:
                return json.dumps(ai_data["concerns"])
            return None

        cursor.execute("""
            INSERT INTO judgments (
                issue, result, avg_severity,
                claude_decision, claude_severity, claude_reason, claude_concerns, claude_elapsed,
                gemini_decision, gemini_severity, gemini_reason, gemini_concerns, gemini_elapsed,
                chatgpt_decision, chatgpt_severity, chatgpt_reason, chatgpt_concerns, chatgpt_elapsed,
                reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            judgment["issue"],
            judgment["result"],
            judgment["avg_severity"],

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

            judgment["reasoning"]
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
        result = {
            "id": item["id"],
            "issue": item["issue"],
            "result": item["result"],
            "avg_severity": item["avg_severity"],
            "judgment_severity": item.get("avg_severity"),  # Use avg_severity as fallback
            "severity_level": None,  # Not stored in DB, will be calculated
            "claude": build_ai_response("claude"),
            "gemini": build_ai_response("gemini"),
            "chatgpt": build_ai_response("chatgpt"),
            "reasoning": item["reasoning"],
            "created_at": item["created_at"]
        }

        logger.info(f"Retrieved judgment ID {judgment_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve judgment {judgment_id}: {e}", exc_info=True)
        raise
