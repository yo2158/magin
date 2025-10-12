"""
Configuration module for MAGIN application.

Centralized configuration management with environment variable support.
"""
import os
from typing import List


# Timeout settings (seconds)
SINGLE_AI_TIMEOUT: int = int(os.getenv("SINGLE_AI_TIMEOUT", "300"))
TOTAL_TIMEOUT: int = int(os.getenv("TOTAL_TIMEOUT", "600"))

# Database path
DB_PATH: str = os.getenv("DB_PATH", "data/judgments.db")

# CORS settings
ALLOWED_ORIGINS_STR: str = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS: List[str] = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",")]

# Logging level
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
