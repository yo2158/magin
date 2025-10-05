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
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.config import SINGLE_AI_TIMEOUT
from backend.models import AIResponseModel, AIScores

# Configure logging
logger = logging.getLogger(__name__)

# AI Configuration (Task 8)
AI_CONFIGS = [
    {
        "name": "Claude",
        "command": ["claude"],
        "role": "balanced",
        "display_name": "Claude"
    },
    {
        "name": "Gemini",
        "command": ["gemini"],
        "role": "logical",
        "display_name": "Gemini"
    },
    {
        "name": "ChatGPT",
        "command": ["codex", "exec", "--skip-git-repo-check"],
        "role": "technical",
        "display_name": "ChatGPT"
    }
]


# ============================================================
# Task 9: JSON Extraction Utilities
# ============================================================

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

    # Try ```json ... ```
    match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error in ```json block: {e}")

    # Try ``` ... ```
    match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error in ``` block: {e}")

    # Try raw JSON { ... }
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error in raw JSON: {e}")

    return None


def extract_codex_response(output: str) -> str:
    """
    Remove Codex CLI timestamp logs from output.

    Example:
        "[2025-10-04T12:34:56] codex\\nsome output" → "some output"

    Args:
        output: Raw Codex CLI output

    Returns:
        Cleaned output without timestamp logs
    """
    match = re.search(
        r'\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\] codex\s*\n(.*?)(?:\[\d{4}-\d{2}-\d{2}T|$)',
        output,
        re.DOTALL
    )

    if match:
        return match.group(1).strip()

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
# Task 11: AI Prompt Generation (NEW SPEC)
# ============================================================

def create_ai_prompt(issue: str, ai_role: str) -> str:
    """
    Generate AI prompt with NEW SPECIFICATION features.

    Includes:
    - 4-aspect evaluation criteria (validity, feasibility, risk, certainty)
    - Risk floor constraint (risk < 0.6 prevents approval)
    - Hard flag setting criteria (compliance/security/privacy)
    - Constraint priorities (hard_flag must have evidence, risk floor, 0.9 boundary strict)

    Args:
        issue: Issue text to judge
        ai_role: balanced/logical/technical

    Returns:
        Formatted prompt string

    Example:
        >>> prompt = create_ai_prompt("新機能を実装すべきか？", "balanced")
        >>> "4観点評価" in prompt
        True
    """
    role_descriptions = {
        "balanced": "あなたはバランス重視の視点で判断してください。賛成・反対双方の意見を公平に考慮します。",
        "logical": "あなたは論理的妥当性重視の視点で判断してください。理論的整合性と倫理を最優先します。",
        "technical": "あなたは実現可能性重視の視点で判断してください。技術的・経済的な実装面を重視します。"
    }

    return f"""
{role_descriptions.get(ai_role, "")}

議題: {issue}

【重要】もし議題が意思決定に関するものでない場合（例: 天気予報、挨拶、一般質問、雑談等）、
以下のフォーマットで回答してください:
{{
  "scores": {{"validity": 0.0, "feasibility": 0.0, "risk": 0.0, "certainty": 0.0}},
  "average_score": 0.0,
  "decision": "NOT_APPLICABLE",
  "severity": 0,
  "reason": "この質問は意思決定事項ではありません",
  "concerns": [],
  "hard_flag": "none"
}}

意思決定に関する議題の場合のみ、以下の4観点で評価し、JSON形式で返してください。他の説明は一切不要です。

**4観点評価基準（各0.0-1.0）**:
1. **validity（妥当性）**: 提案が目的に合致しているか（1.0=完全合致、0.0=無関係）
2. **feasibility（実現可能性）**: リソースや条件が整っているか（1.0=実現容易、0.0=不可能）
3. **risk（リスク）**: 安全性・倫理・コストリスク（1.0=リスク極小、0.0=致命的リスク）
4. **certainty（確実性）**: 根拠や前提の明確さ（1.0=確実、0.0=不確実）

**重大度ガイドライン（0-100）**:
- 0-20: 個人レベル（個人の習慣・趣味）
- 21-40: 組織レベル（チーム・部署の判断）
- 41-60: 事業レベル（企業戦略・投資判断）
- 61-80: 社会レベル（法律・政策・大規模影響）
- 81-100: 存続レベル（生命・存続・倫理の根幹）

**判定ルール**:
- 平均スコア >= 0.9: 承認
- 平均スコア 0.7-0.9: 部分的承認
- 平均スコア < 0.7: 否決
- **リスク下限制約**: risk < 0.6 の場合、承認不可（最高でも部分的承認）

**ハードフラグ設定基準**:
- **compliance**: 法令・規制違反の可能性がある場合
- **security**: セキュリティリスク・情報漏洩の懸念がある場合
- **privacy**: プライバシー侵害の懸念がある場合
- **none**: 上記のいずれにも該当しない場合（デフォルト）

**制約の優先順位**:
1. ハードフラグは根拠必須（具体的な懸念がない場合は"none"）
2. risk < 0.6 の場合は承認不可
3. 0.9境界を厳守（0.89は部分的承認、0.90は承認）

**出力形式（JSON）**:
{{
  "scores": {{
    "validity": 0.0-1.0,
    "feasibility": 0.0-1.0,
    "risk": 0.0-1.0,
    "certainty": 0.0-1.0
  }},
  "average_score": 0.0-1.0,
  "decision": "承認" | "部分的承認" | "否決",
  "severity": 0-100,
  "reason": "判断理由（100文字程度）",
  "concerns": ["懸念点1", "懸念点2"],
  "hard_flag": "none" | "compliance" | "security" | "privacy"
}}
"""


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

        # Extract JSON
        json_data = extract_json_from_markdown(clean_output)

        # Validate response
        if json_data:
            is_valid, error_msg, sanitized = validate_ai_response(json_data)
            if not is_valid:
                logger.error(f"{ai_name} validation failed: {error_msg}")
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

async def run_parallel_judgment(issue: str, on_ai_complete: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> List[Dict[str, Any]]:
    """
    Execute all 3 AIs in parallel with timeout handling.

    Args:
        issue: Issue text to judge
        on_ai_complete: Optional callback function called when each AI completes.
                       Signature: (ai_name: str, result: Dict[str, Any]) -> None

    Returns:
        List of AI responses (success or failure)

    Example:
        >>> responses = await run_parallel_judgment("新機能を実装すべきか？")
        >>> len(responses)
        3
        >>> all("ai" in r for r in responses)
        True
    """
    logger.info(f"Starting parallel judgment for issue: {issue[:50]}...")

    # Create tasks for parallel execution
    async def execute_with_callback(config):
        result = await call_ai_async(
            config["name"],
            config["command"],
            create_ai_prompt(issue, config["role"]),
            timeout=SINGLE_AI_TIMEOUT
        )
        # Call callback if provided
        if on_ai_complete:
            on_ai_complete(config["name"], result)
        return result

    tasks = [execute_with_callback(config) for config in AI_CONFIGS]

    # Execute in parallel with exception handling
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to error responses
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"AI {AI_CONFIGS[i]['name']} raised exception: {result}")
            error_result = {
                "ai": AI_CONFIGS[i]["name"],
                "success": False,
                "response": None,
                "raw_output": None,
                "error": str(result),
                "elapsed_seconds": 0.0
            }
            processed_results.append(error_result)
            # Call callback for error case too
            if on_ai_complete:
                on_ai_complete(AI_CONFIGS[i]["name"], error_result)
        else:
            processed_results.append(result)

    # Log summary
    successful_count = sum(1 for r in processed_results if r["success"])
    logger.info(f"Parallel judgment completed: {successful_count}/3 successful")

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
