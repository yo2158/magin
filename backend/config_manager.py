"""
Configuration Manager for MAGIN v1.3 - Multi-Node System.

This module provides configuration management for AI node settings,
supporting both MCP and API-based engine configurations.

New in v1.3:
- Multi-node configuration (default 3 nodes)
- Engine selection: Claude, Gemini, ChatGPT, API_Gemini, API_OpenRouter, API_Ollama
- Per-node persona assignment
- Configurable model names (optional)

Example:
    >>> config = get_default_config()
    >>> config["nodes"][0]["engine"]
    'Claude'
"""

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List


def get_default_config() -> Dict[str, Any]:
    """
    Get default configuration for MAGIN v1.3.

    Returns the default 3-node configuration with MCP engines
    (Claude, Gemini, ChatGPT) and researcher persona.

    Returns:
        Dict[str, Any]: Configuration dictionary containing:
            - nodes: List of node configurations, each with:
                - id (int): Node ID (1-based)
                - name (str): Node display name
                - engine (str): Engine type (Claude/Gemini/ChatGPT/API_Gemini/API_OpenRouter/API_Ollama)
                - model (Optional[str]): Model name (null for default)
                - persona_id (str): Persona ID for this node

    Example:
        >>> config = get_default_config()
        >>> len(config["nodes"])
        3
        >>> config["nodes"][0]["engine"]
        'Claude'
        >>> config["nodes"][1]["persona_id"]
        'researcher'
    """
    return {
        "nodes": [
            {
                "id": 1,
                "name": "NODE 1",
                "engine": "Claude",
                "model": None,
                "persona_id": "neutral_ai",
            },
            {
                "id": 2,
                "name": "NODE 2",
                "engine": "Gemini",
                "model": None,
                "persona_id": "neutral_ai",
            },
            {
                "id": 3,
                "name": "NODE 3",
                "engine": "ChatGPT",
                "model": None,
                "persona_id": "neutral_ai",
            },
        ]
    }


# ============================================================
# Configuration File Paths
# ============================================================

CONFIG_DIR = Path(__file__).parent.parent / "config"
USER_CONFIG_PATH = CONFIG_DIR / "user_config.json"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "user_config.json.default"
ENV_FILE_PATH = Path(__file__).parent.parent / ".env"


# ============================================================
# User Configuration Management (Task 1.1.2)
# ============================================================

def load_user_config() -> Dict[str, Any]:
    """
    Load user configuration from config/user_config.json.

    If the file does not exist:
    1. Try to copy from user_config.json.default
    2. If default file exists, copy it to user_config.json
    3. Otherwise, returns default configuration from get_default_config()

    Returns:
        Dict[str, Any]: User configuration dictionary.

    Example:
        >>> config = load_user_config()
        >>> "nodes" in config
        True
        >>> len(config["nodes"]) == 3
        True
    """
    if not USER_CONFIG_PATH.exists():
        # Try to copy from default file
        if DEFAULT_CONFIG_PATH.exists():
            try:
                shutil.copy(DEFAULT_CONFIG_PATH, USER_CONFIG_PATH)
                print(f"[INFO] Created user_config.json from default template")
            except IOError as e:
                print(f"[WARNING] Failed to copy default config: {e}")
                return get_default_config()
        else:
            # No default file, return hardcoded default
            return get_default_config()

    try:
        with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except (json.JSONDecodeError, IOError) as e:
        # If file is corrupted, return default config
        print(f"[WARNING] Failed to load user config: {e}, using default")
        return get_default_config()


def save_user_config(config: Dict[str, Any]) -> None:
    """
    Save user configuration to config/user_config.json.

    Validates the configuration before saving:
    - "nodes" field must exist
    - Exactly 3 nodes are required
    - Each node must have: id, name, engine, model, persona_id

    Args:
        config: Configuration dictionary to save.

    Raises:
        ValueError: If configuration is invalid.

    Example:
        >>> config = get_default_config()
        >>> save_user_config(config)  # Should succeed
        >>> save_user_config({"nodes": []})  # Should raise ValueError
        Traceback (most recent call last):
        ...
        ValueError: Configuration must have exactly 3 nodes, got 0
    """
    # Validation: "nodes" must exist
    if "nodes" not in config:
        raise ValueError("Configuration must have 'nodes' field")

    # Validation: Exactly 3 nodes required
    nodes = config["nodes"]
    if not isinstance(nodes, list):
        raise ValueError("'nodes' must be a list")

    if len(nodes) != 3:
        raise ValueError(f"Configuration must have exactly 3 nodes, got {len(nodes)}")

    # Validation: Each node structure
    required_fields = ["id", "name", "engine", "model", "persona_id"]
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"Node {i+1} must be a dictionary")

        for field in required_fields:
            if field not in node:
                raise ValueError(f"Node {i+1} missing required field: {field}")

    # Create config directory if not exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Save configuration
    with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ============================================================
# Environment Variables Management (Task 1.1.3)
# ============================================================

def load_env() -> Dict[str, str]:
    """
    Load environment variables from .env file.

    Reads GEMINI_API_KEY, OPENROUTER_API_KEY, and OLLAMA_URL.
    If .env does not exist, returns None for each key.
    OLLAMA_URL defaults to "http://localhost:11434" if not set.

    Returns:
        Dict[str, str]: Dictionary with API keys and OLLAMA_URL.
            Keys: "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_URL"
            Values: str or None

    Example:
        >>> env = load_env()
        >>> "GEMINI_API_KEY" in env
        True
        >>> env["OLLAMA_URL"]  # Has default value
        'http://localhost:11434'
    """
    env_vars = {
        "GEMINI_API_KEY": None,
        "OPENROUTER_API_KEY": None,
        "OLLAMA_URL": "http://localhost:11434"  # Default value
    }

    if not ENV_FILE_PATH.exists():
        return env_vars

    try:
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Parse KEY=value or KEY="value"
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    if key in env_vars:
                        env_vars[key] = value

        return env_vars

    except IOError:
        return env_vars


def save_env(env_vars: Dict[str, str]) -> None:
    """
    Save environment variables to .env file.

    Overwrites existing .env file with new values.
    Format: KEY="value"

    Args:
        env_vars: Dictionary with environment variables.
            Keys: "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_URL"

    Example:
        >>> save_env({
        ...     "GEMINI_API_KEY": "test_key",
        ...     "OPENROUTER_API_KEY": "test_key2",
        ...     "OLLAMA_URL": "http://localhost:11434"
        ... })
    """
    lines = []
    lines.append("# MAGIN v1.3 Environment Variables")
    lines.append("# Auto-generated by config_manager.py")
    lines.append("")

    for key, value in env_vars.items():
        if value is not None:
            lines.append(f'{key}="{value}"')
        else:
            lines.append(f'# {key}=""')

    with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

