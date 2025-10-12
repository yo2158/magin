"""
MAGIN AI Orchestrator - AI Integration Layer

This module orchestrates parallel execution of Claude, Gemini, and ChatGPT CLIs
with NEW SPECIFICATION features:
- 4-aspect scoring (validity, feasibility, risk, certainty)
- Hard flag detection (compliance/security/privacy)
- Risk floor constraint (risk < 0.6 prevents approval)
- Weighted approval scoring
- Robust validation and error handling

Implements Tasks 8-14 from Phase 4: AI Integration Layer
"""

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.config import SINGLE_AI_TIMEOUT
from backend.config_manager import load_user_config
from backend.models import AIResponseModel, AIScores

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Enable DEBUG logging for troubleshooting

# ============================================================
# Backend基盤: Persona & Prompt Template Loading
# ============================================================

# グローバル変数
PERSONAS: Dict[str, Any] = {}
PROMPT_TEMPLATE: str = ""

# デフォルトペルソナID定義
DEFAULT_PERSONA_IDS = {
    "ai1": "neutral_ai",
    "ai2": "neutral_ai",
    "ai3": "neutral_ai"
}

# プロンプトテンプレートのパス
PROMPT_TEMPLATE_PATH = Path(__file__).parent / "prompt_template.md"

def load_personas() -> Dict[str, Any]:
    """
    Load personas from personas.json.

    Returns:
        Dict containing all personas

    Raises:
        ValueError: If personas.json is missing or corrupted
    """
    personas_path = Path(__file__).parent / "personas.json"
    try:
        with open(personas_path, "r", encoding="utf-8") as f:
            personas = json.load(f)
        logger.info(f"Loaded {len(personas)} personas from {personas_path}")
        return personas
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load personas.json: {e}")
        raise ValueError(f"Persona loading failed: {e}")

def load_prompt_template() -> str:
    """
    Load prompt template from prompt_template_v1_1draft.md.

    Returns:
        Template string

    Raises:
        FileNotFoundError: If template file is missing
    """
    try:
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        logger.info(f"Prompt template loaded: {len(template)} chars")
        return template
    except FileNotFoundError:
        logger.error(f"Prompt template not found: {PROMPT_TEMPLATE_PATH}")
        raise

# tiktokenの可用性チェック
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available, token validation disabled")

def validate_prompt_tokens(prompt: str, max_tokens: int = 3000) -> bool:
    """
    Validate prompt token count using tiktoken.

    Args:
        prompt: Prompt string to validate
        max_tokens: Maximum allowed tokens (default: 2000)

    Returns:
        True if validation passed or tiktoken unavailable
        False if token count exceeds max_tokens

    Example:
        >>> validate_prompt_tokens("短いプロンプト")
        True
    """
    if not TIKTOKEN_AVAILABLE:
        logger.warning("Token validation skipped (tiktoken not installed)")
        return True
    try:
        encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")
        token_count = len(encoder.encode(prompt))
        if token_count > max_tokens:
            logger.error(f"Prompt exceeds {max_tokens} tokens: {token_count}")
            return False
        logger.debug(f"Prompt token count: {token_count}/{max_tokens}")
        return True
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return True

# 起動時に読み込み
PERSONAS = load_personas()
PROMPT_TEMPLATE = load_prompt_template()

# AI Configuration (Task 8, modified by Task 3)
AI_CONFIGS = [
    {
        "name": "Claude",
        "command": ["claude"],
        "persona_id": "researcher",
        "display_name": "Claude"
    },
    {
        "name": "Gemini",
        "command": ["gemini"],
        "persona_id": "mother",
        "display_name": "Gemini"
    },
    {
        "name": "ChatGPT",
        "command": ["codex", "exec", "--skip-git-repo-check"],
        "persona_id": "woman",
        "display_name": "ChatGPT"
    }
]


# ============================================================
# Task 9: JSON Extraction Utilities
# ============================================================

def find_nth_json_object(text: str, n: int = 1) -> Optional[Dict[str, Any]]:
    """
    Find the Nth JSON object in text (useful for skipping persona JSON).

    Args:
        text: Text containing JSON objects
        n: Which JSON object to return (1-indexed, default=1 for first)

    Returns:
        The Nth JSON object, or None if not found
    """
    if not text or n < 1:
        return None

    found_count = 0
    start_idx = 0

    while start_idx < len(text):
        # Find next '{'
        start_idx = text.find('{', start_idx)
        if start_idx == -1:
            break

        # Try to parse JSON from this position
        brace_count = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

                    if brace_count == 0:
                        json_str = text[start_idx:i+1]
                        try:
                            json_obj = json.loads(json_str)
                            found_count += 1
                            if found_count == n:
                                return json_obj
                        except json.JSONDecodeError:
                            pass
                        # Move to next potential JSON
                        start_idx = i + 1
                        break
        else:
            # Didn't find matching brace, move forward
            start_idx += 1

    return None

def extract_json_from_markdown(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from markdown code blocks or raw JSON.

    Priority:
    1. ```json ... ``` blocks
    2. ``` ... ``` blocks
    3. Raw JSON (starts with { or [)

    Args:
        text: Raw AI output text

    Returns:
        Parsed JSON dict or None if extraction fails

    Example:
        >>> extract_json_from_markdown('```json\\n{"decision": "承認"}\\n```')
        {'decision': '承認'}
    """
    if not text:
        return None

    # Pre-process: Fix common JSON formatting errors
    # Fix missing quotes before field names (e.g., hard_flag" -> "hard_flag")
    text = re.sub(r'(\n\s*)([a-zA-Z_][a-zA-Z0-9_]*)":', r'\1"\2":', text)

    # Try ```json ... ``` blocks
    match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error in ```json block: {e}")

    # Try ``` ... ``` blocks
    match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error in ``` block: {e}")

    # Try raw JSON { ... } with balanced braces
    search_start = 0

    while search_start < len(text):
        start_idx = text.find('{', search_start)
        if start_idx == -1:
            break
        # Try to find a valid JSON object by iteratively extending the slice
        brace_count = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(text)):
            char = text[i]

            # Handle string escaping
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue

            # Track if we're inside a string
            if char == '"':
                in_string = not in_string
                continue

            # Only count braces outside strings
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

                    # Found matching closing brace
                    if brace_count == 0:
                        json_str = text[start_idx:i+1]
                        try:
                            parsed = json.loads(json_str)
                            return parsed
                        except json.JSONDecodeError as e:
                            logger.warning(f"JSON decode error in raw JSON: {e}")
                            # Continue searching for next JSON object
                            search_start = i + 1
                            break
        else:
            # Inner loop completed without break - no valid JSON found from this position
            search_start = start_idx + 1

    return None


def extract_codex_response(output: str) -> str:
    """
    Remove Codex CLI metadata from output.

    Handles Codex v0.44.0 format where output contains:
    1. Metadata headers
    2. User prompt (with persona JSON)
    3. "codex\\n" marker
    4. Response JSON
    5. "\\ntokens used" marker

    Strategy: Extract content between "codex\\n" and "tokens used",
    then find the FIRST valid JSON (which is the response, not persona)

    Args:
        output: Raw Codex CLI output

    Returns:
        Cleaned output without metadata (just the response JSON)
    """
    # Extract content between "codex\n" and "tokens used"
    codex_match = re.search(r'\bcodex\s*\n(.*?)\ntokens used', output, re.DOTALL)
    if codex_match:
        extracted = codex_match.group(1).strip()
        logger.debug(f"Extracted codex section ({len(extracted)} chars)")
        return extracted

    # Fallback: try simple "codex\n" pattern
    codex_simple = re.search(r'\bcodex\s*\n(.*)', output, re.DOTALL)
    if codex_simple:
        extracted = codex_simple.group(1).strip()
        logger.debug(f"Extracted using simple codex pattern ({len(extracted)} chars)")
        return extracted

    # If no pattern matched, return as-is
    logger.warning(f"No extraction pattern matched, returning raw output")
    return output.strip()


# ============================================================
# Task 10: AI Response Validation (NEW SPEC)
# ============================================================

def validate_ai_response(response: Dict) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """
    Validate AI response according to NEW SPECIFICATION.

    Validation Rules:
    1. Required fields: scores, decision, severity, reason
    2. scores sub-fields: validity, feasibility, risk, certainty (0.0-1.0, clipped)
    3. decision: ["承認", "部分的承認", "否決"] (invalid → "否決")
    4. severity: 0-100 (clipped)
    5. hard_flag: ["none", "compliance", "security", "privacy"] (invalid → "none")

    Args:
        response: Extracted JSON response from AI

    Returns:
        (is_valid, error_message, sanitized_response)
        - is_valid: True if validation passed
        - error_message: Error description if failed
        - sanitized_response: Clipped/corrected response

    Example:
        >>> validate_ai_response({"scores": {"validity": 1.5, ...}, "decision": "承認", ...})
        (True, None, {"scores": {"validity": 1.0, ...}, ...})
    """
    if not response:
        return False, "Empty response", None

    # 1. Required fields check
    required_fields = ["scores", "decision", "severity", "reason"]
    for field in required_fields:
        if field not in response:
            return False, f"必須フィールド欠如: {field}", None

    # 2. scores sub-fields check
    required_scores = ["validity", "feasibility", "risk", "certainty"]
    for score_field in required_scores:
        if score_field not in response["scores"]:
            return False, f"必須スコア欠如: {score_field}", None

    # 3. Create sanitized copy and clip scores to 0.0-1.0
    sanitized = json.loads(json.dumps(response))  # Deep copy
    for key in required_scores:
        try:
            value = float(sanitized["scores"][key])
            sanitized["scores"][key] = max(0.0, min(1.0, value))
        except (TypeError, ValueError):
            return False, f"不正なスコア値: {key}", None

    # 4. decision validation
    if sanitized["decision"] not in ["承認", "部分的承認", "否決", "NOT_APPLICABLE"]:
        logger.warning(f"Invalid decision '{sanitized['decision']}', defaulting to 否決")
        sanitized["decision"] = "否決"

    # 5. severity clipping
    try:
        sanitized["severity"] = max(0, min(100, int(sanitized["severity"])))
    except (TypeError, ValueError):
        return False, "不正な重大度値", None

    # 6. hard_flag validation
    if "hard_flag" in sanitized:
        if sanitized["hard_flag"] not in ["none", "compliance", "security", "privacy"]:
            logger.warning(f"Invalid hard_flag '{sanitized['hard_flag']}', defaulting to none")
            sanitized["hard_flag"] = "none"
    else:
        sanitized["hard_flag"] = "none"

    # 7. Ensure concerns is a list
    if "concerns" not in sanitized:
        sanitized["concerns"] = []
    elif not isinstance(sanitized["concerns"], list):
        sanitized["concerns"] = []

    # 8. Calculate average_score if not present
    if "average_score" not in sanitized:
        avg_score = sum(sanitized["scores"].values()) / len(sanitized["scores"])
        sanitized["average_score"] = avg_score

    return True, None, sanitized


# ============================================================
# Task 11: AI Prompt Generation (PERSONA-DRIVEN)
# ============================================================

def create_ai_prompt(issue: str, persona_id: str) -> str:
    """
    ペルソナJSONを埋め込んだプロンプトを生成

    旧実装を完全削除し、新規実装に置き換え
    旧: create_ai_prompt(issue, ai_role)  # ai_role = "balanced"/"logical"/"technical"
    新: create_ai_prompt(issue, persona_id)  # persona_id = "researcher"/"mother"等

    処理:
    1. PERSONAS[persona_id] を取得
    2. PROMPT_TEMPLATE の {{PERSONA_JSON}} に埋め込み
    3. {issue} を置換
    4. トークン数検証（上限2000トークン）

    Args:
        issue: 議題
        persona_id: ペルソナID（例: "researcher"）

    Returns:
        str: 完成したプロンプト

    Raises:
        ValueError: トークン数超過の場合

    Example:
        >>> prompt = create_ai_prompt("ランチにカレーを食べる", "researcher")
        >>> "研究者" in prompt
        True
    """
    # 1. ペルソナ取得
    persona_data = PERSONAS.get(persona_id)
    if not persona_data:
        logger.error(f"Invalid persona_id: {persona_id}")
        # デフォルトペルソナにフォールバック
        persona_id = DEFAULT_PERSONA_IDS["ai1"]
        persona_data = PERSONAS[persona_id]
        logger.warning(f"Using default persona: {persona_id}")

    # 2. ペルソナJSONを文字列化
    persona_json_str = json.dumps(persona_data, ensure_ascii=False, indent=2)

    # 3. プロンプトテンプレートに埋め込み
    prompt = PROMPT_TEMPLATE.replace("{{PERSONA_JSON}}", persona_json_str)
    prompt = prompt.replace("{issue}", issue)

    # 4. トークン数検証
    if not validate_prompt_tokens(prompt):
        raise ValueError(f"Prompt exceeds 3000 tokens for persona: {persona_id}")

    return prompt


# ============================================================
# Task 8: AI CLI Execution (Base Function)
# ============================================================

async def call_ai_async(
    ai_name: str,
    command: List[str],
    prompt: str,
    timeout: int = SINGLE_AI_TIMEOUT
) -> Dict[str, Any]:
    """
    Execute single AI CLI asynchronously.

    Args:
        ai_name: AI name (Claude/Gemini/ChatGPT)
        command: Command list (e.g., ["claude"] or ["codex", "exec", "--skip-git-repo-check"])
        prompt: Prompt to send
        timeout: Timeout in seconds

    Returns:
        {
            "ai": str,
            "success": bool,
            "response": {
                "scores": {...},
                "decision": str,
                "severity": int,
                "reason": str,
                "concerns": [...],
                "hard_flag": str
            } | None,
            "raw_output": str,
            "error": str | None,
            "elapsed_seconds": float
        }
    """
    start_time = datetime.now()

    try:
        logger.info(f"Starting AI CLI execution: {ai_name}")

        # Create subprocess with shell=False (security)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for completion with timeout
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=prompt.encode('utf-8')),
            timeout=timeout
        )

        stdout_text = stdout.decode('utf-8').strip()
        stderr_text = stderr.decode('utf-8').strip()

        elapsed = (datetime.now() - start_time).total_seconds()

        # Extract response (Codex requires special handling)
        if 'codex' in ai_name.lower() or 'chatgpt' in ai_name.lower():
            clean_output = extract_codex_response(stdout_text)
        else:
            clean_output = stdout_text

        # Debug: Log for ChatGPT BEFORE JSON extraction
        if 'chatgpt' in ai_name.lower():
            logger.debug(f"ChatGPT stdout length: {len(stdout_text)} chars")
            logger.debug(f"ChatGPT stdout (first 500 chars): {stdout_text[:500]}")
            logger.debug(f"ChatGPT clean_output length: {len(clean_output)} chars")
            logger.debug(f"ChatGPT clean_output (first 1000 chars): {clean_output[:1000]}")

            # Find ALL JSON objects in clean_output
            all_jsons = []
            pos = 0
            while pos < len(clean_output):
                brace_idx = clean_output.find('{', pos)
                if brace_idx == -1:
                    break
                try:
                    # Try to parse JSON from this position
                    for end_pos in range(brace_idx + 1, len(clean_output) + 1):
                        try:
                            parsed = json.loads(clean_output[brace_idx:end_pos])
                            all_jsons.append({
                                'start': brace_idx,
                                'end': end_pos,
                                'preview': str(parsed)[:200]
                            })
                            pos = end_pos
                            break
                        except json.JSONDecodeError:
                            continue
                    else:
                        pos = brace_idx + 1
                except Exception:
                    pos = brace_idx + 1

            logger.debug(f"ChatGPT found {len(all_jsons)} JSON objects in clean_output:")
            for idx, j in enumerate(all_jsons, 1):
                logger.debug(f"  JSON #{idx} at pos {j['start']}-{j['end']}: {j['preview']}")

        # Extract JSON
        # For Codex/ChatGPT: Find all valid JSON objects and take the LAST one
        if 'codex' in ai_name.lower() or 'chatgpt' in ai_name.lower():
            all_jsons = []
            search_pos = 0

            while search_pos < len(clean_output):
                # Find next '{' starting position
                brace_pos = clean_output.find('{', search_pos)
                if brace_pos == -1:
                    break

                # Try to extract JSON from this position
                test_json = extract_json_from_markdown(clean_output[brace_pos:])
                if test_json:
                    # Filter out incomplete JSON (must have 'scores' field for valid responses)
                    # Skip persona JSON (has 'persona_name') and NOT_APPLICABLE template (has decision='NOT_APPLICABLE')
                    is_persona = 'persona_name' in test_json
                    is_not_applicable = test_json.get('decision') == 'NOT_APPLICABLE'
                    is_incomplete = 'scores' not in test_json and 'validity' in test_json  # Incomplete JSON with bare scores

                    if not is_persona and not is_not_applicable and not is_incomplete:
                        all_jsons.append(test_json)

                    # Convert back to JSON string to find its actual end position
                    json_str = json.dumps(test_json, ensure_ascii=False)
                    # Search for the end of this JSON object (with balanced braces)
                    # Move past the opening brace
                    search_pos = brace_pos + len(json_str)
                else:
                    # No valid JSON found, move past this brace
                    search_pos = brace_pos + 1

            # Take the LAST JSON (after filtering)
            json_data = all_jsons[-1] if all_jsons else None
            if 'chatgpt' in ai_name.lower():
                logger.debug(f"ChatGPT found {len(all_jsons)} valid JSON objects (after filtering), using last one")
                logger.debug(f"ChatGPT extracted JSON: {json_data}")
        else:
            json_data = extract_json_from_markdown(clean_output)

        # Validate response
        if json_data:
            is_valid, error_msg, sanitized = validate_ai_response(json_data)
            if not is_valid:
                logger.error(f"{ai_name} validation failed: {error_msg}")
                logger.error(f"{ai_name} extracted JSON was: {json_data}")
                return {
                    "ai": ai_name,
                    "success": False,
                    "response": None,
                    "raw_output": clean_output[:500],
                    "error": f"Validation error: {error_msg}",
                    "elapsed_seconds": elapsed
                }
            json_data = sanitized

        logger.info(f"{ai_name} execution completed in {elapsed:.2f}s")

        return {
            "ai": ai_name,
            "success": json_data is not None,
            "response": json_data,
            "raw_output": clean_output[:500],
            "error": stderr_text if stderr_text and not json_data else None,
            "elapsed_seconds": elapsed
        }

    except asyncio.TimeoutError:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.warning(f"{ai_name} timed out after {timeout}s")
        return {
            "ai": ai_name,
            "success": False,
            "response": None,
            "raw_output": None,
            "error": f"タイムアウト ({timeout}秒)",
            "elapsed_seconds": elapsed
        }

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"{ai_name} execution error: {e}", exc_info=True)
        return {
            "ai": ai_name,
            "success": False,
            "response": None,
            "raw_output": None,
            "error": str(e),
            "elapsed_seconds": elapsed
        }


# ============================================================
# Tasks 12-13: Parallel AI Execution with Timeout Handling
# ============================================================

async def run_parallel_judgment(
    issue: str,
    persona_ids: Optional[List[str]] = None,
    on_ai_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None
) -> List[Dict[str, Any]]:
    """
    Execute all 3 AIs in parallel with timeout handling.

    Modified in Task 3 to support persona_ids parameter.
    Modified in Phase 2 Task 2.1.1 to support user_config.json NODE settings.

    Args:
        issue: Issue text to judge
        persona_ids: List of persona IDs for each AI (optional, defaults to AI_CONFIGS persona_ids or user_config.json)
        on_ai_complete: Optional callback function called when each AI completes.
                       Signature: (ai_name: str, result: Dict[str, Any]) -> None

    Returns:
        List of AI responses (success or failure)

    Raises:
        ValueError: If fewer than 2 AIs respond successfully

    Example:
        >>> responses = await run_parallel_judgment("新機能を実装すべきか？")
        >>> len(responses)
        3
        >>> responses = await run_parallel_judgment("カレー", ["neutral_ai", "neutral_ai", "neutral_ai"])
        >>> all("ai" in r for r in responses)
        True
    """
    logger.info(f"Starting parallel judgment for issue: {issue[:50]}...")

    # Load user configuration (NODE settings)
    config = load_user_config()
    nodes = config.get("nodes", [])

    # Validate we have exactly 3 nodes
    if len(nodes) != 3:
        logger.warning(f"Expected 3 nodes in config, got {len(nodes)}. Using default AI_CONFIGS.")
        nodes = []  # Fall back to AI_CONFIGS

    # Use default persona_ids from AI_CONFIGS if not provided
    if persona_ids is None:
        if nodes:
            # Use persona_ids from user_config.json
            persona_ids = [node.get("persona_id", "researcher") for node in nodes]
        else:
            # Use persona_ids from AI_CONFIGS
            persona_ids = [config["persona_id"] for config in AI_CONFIGS]

    # Create tasks for parallel execution
    async def execute_with_callback(config_or_node, persona_id, index):
        # Import call_ai here to avoid circular import
        from backend.ai_factory import call_ai

        # If using user_config.json nodes
        if nodes and index < len(nodes):
            node = nodes[index]
            engine = node.get("engine", "Claude")
            model = node.get("model")
            ai_name = node.get("name", f"AI {index + 1}")

            # Call new ai_factory.call_ai() function
            result = await call_ai(
                engine,
                model,
                create_ai_prompt(issue, persona_id),
                timeout=SINGLE_AI_TIMEOUT
            )
            # Add ai_name, engine, and model to result
            result["ai"] = ai_name
            result["engine"] = engine
            result["model"] = model or "default"
        else:
            # Fall back to old AI_CONFIGS (MCP CLI only)
            result = await call_ai_async(
                config_or_node["name"],
                config_or_node["command"],
                create_ai_prompt(issue, persona_id),
                timeout=SINGLE_AI_TIMEOUT
            )

        # Call callback if provided
        if on_ai_complete:
            on_ai_complete(result["ai"], result)
        return result

    # Build task list
    if nodes:
        tasks = [execute_with_callback(nodes[i], persona_ids[i], i) for i in range(3)]
    else:
        tasks = [execute_with_callback(AI_CONFIGS[i], persona_ids[i], i) for i in range(len(AI_CONFIGS))]

    # Execute in parallel with exception handling
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to error responses
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            ai_name = nodes[i]["name"] if nodes else AI_CONFIGS[i]["name"]
            logger.error(f"AI {ai_name} raised exception: {result}")
            error_result = {
                "ai": ai_name,
                "success": False,
                "response": None,
                "raw_output": None,
                "error": str(result),
                "elapsed_seconds": 0.0
            }
            processed_results.append(error_result)
            # Call callback for error case too
            if on_ai_complete:
                on_ai_complete(ai_name, error_result)
        else:
            processed_results.append(result)

    # Log summary
    successful_count = sum(1 for r in processed_results if r["success"])
    logger.info(f"Parallel judgment completed: {successful_count}/3 successful")

    # Task 2.1.2: Check minimum 2 AIs responded successfully
    if successful_count < 2:
        raise ValueError("At least 2 AIs must respond")

    return processed_results


# ============================================================
# Task 14: Plain Text Output Generation for Simple Mode
# ============================================================

def generate_plain_text_output(judgment: Dict[str, Any]) -> str:
    """
    Generate plain text output for simple mode (NEW SPEC requirement).

    Format:
        ========================================
        PROPOSITION: {issue}
        ========================================
        FINAL VERDICT: {result}
        SEVERITY: {severity_level} ({judgment_severity})
        REASONING: {reasoning}

        ========================================
        CLAUDE: {decision} ({severity})
        REASON: {reason}
        CONCERNS: {concerns}

        GEMINI: {decision} ({severity})
        REASON: {reason}
        CONCERNS: {concerns}

        CHATGPT: {decision} ({severity})
        REASON: {reason}
        CONCERNS: {concerns}
        ========================================

    Args:
        judgment: JudgmentModel dict with all fields

    Returns:
        Formatted plain text string

    Example:
        >>> judgment = {
        ...     "issue": "Deploy new feature X?",
        ...     "result": "承認",
        ...     "severity_level": "MID",
        ...     "judgment_severity": 65.0,
        ...     "reasoning": "All AIs approved",
        ...     "claude": {"decision": "承認", "severity": 70, "reason": "Good idea", "concerns": []},
        ...     "gemini": {"decision": "承認", "severity": 60, "reason": "Feasible", "concerns": ["Cost"]},
        ...     "chatgpt": {"decision": "承認", "severity": 65, "reason": "Technical OK", "concerns": []}
        ... }
        >>> text = generate_plain_text_output(judgment)
        >>> "FINAL VERDICT" in text
        True
    """
    lines = []
    lines.append("=" * 60)
    lines.append(f"PROPOSITION: {judgment.get('issue', 'N/A')}")
    lines.append("=" * 60)
    lines.append(f"FINAL VERDICT: {judgment.get('result', 'N/A')}")

    severity_level = judgment.get('severity_level', 'UNKNOWN')
    judgment_severity = judgment.get('judgment_severity', judgment.get('avg_severity', 0.0))
    lines.append(f"SEVERITY: {severity_level} ({judgment_severity:.1f}%)")
    lines.append(f"REASONING: {judgment.get('reasoning', 'N/A')}")
    lines.append("")

    # Individual AI responses
    lines.append("=" * 60)
    for ai_name in ['claude', 'gemini', 'chatgpt']:
        ai_data = judgment.get(ai_name)
        if ai_data:
            decision = ai_data.get('decision', 'N/A')
            severity = ai_data.get('severity', 0)
            reason = ai_data.get('reason', 'N/A')
            concerns = ai_data.get('concerns', [])

            lines.append(f"{ai_name.upper()}: {decision} ({severity})")
            lines.append(f"REASON: {reason}")
            if concerns:
                concerns_str = ', '.join(concerns)
                lines.append(f"CONCERNS: {concerns_str}")
            lines.append("")
        else:
            lines.append(f"{ai_name.upper()}: ERROR (No response)")
            lines.append("")

    lines.append("=" * 60)

    return '\n'.join(lines)


# ============================================================
# Error Handling and Logging Summary
# ============================================================

# Error handling is integrated throughout all functions:
# - JSON parse errors: Handled in extract_json_from_markdown with logging
# - CLI execution errors: Handled in call_ai_async with try/except and logging
# - Timeout errors: Handled with asyncio.TimeoutError and logging
# - Validation errors: Handled in validate_ai_response with detailed messages
# - All errors preserve details for debugging via raw_output and error fields
