"""
MAGIN Severity Judge - Judgment Logic Layer

This module implements the final judgment logic with NEW SPECIFICATION features:
- Judgment severity calculation (防止極端値埋没: max(avg, max*0.8))
- Hard flag detection (compliance/security/privacy automatic rejection)
- Risk floor constraint (risk < 0.6 prevents approval)
- Weighted approval scoring (承認=1.0, 部分的承認=0.5, 否決=0.0)
- Dynamic threshold logic based on severity level
- Conditional approval reasoning generation

Implements Tasks 15-19 from Phase 5: Judgment Logic
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.magi_orchestrator import run_parallel_judgment
from backend.models import AIResponseModel, JudgmentModel

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================
# Task 15: Calculate Judgment Severity
# ============================================================

def calculate_judgment_severity(responses: List[Dict[str, Any]]) -> float:
    """
    Calculate judgment severity to prevent extreme value burial.

    Formula: max(平均重大度, 最大重大度 * 0.8)

    This prevents a single extreme severity from being averaged out.
    Example: [30, 30, 90] → avg=50, max*0.8=72 → judgment_severity=72

    Args:
        responses: List of AI responses from call_ai_async()
                   Each response has structure:
                   {
                       "ai": str,
                       "success": bool,
                       "response": {...} | None,
                       "error": str | None,
                       "elapsed_seconds": float
                   }

    Returns:
        float: Judgment severity (0.0-100.0)

    Example:
        >>> responses = [
        ...     {"success": True, "response": {"severity": 30}},
        ...     {"success": True, "response": {"severity": 90}},
        ...     {"success": True, "response": {"severity": 40}}
        ... ]
        >>> calculate_judgment_severity(responses)
        72.0
    """
    # Extract severity values from successful responses
    severities = []
    for r in responses:
        if r.get("success") and r.get("response"):
            severities.append(r["response"].get("severity", 0))

    if not severities:
        logger.warning("No successful responses with severity, defaulting to 0.0")
        return 0.0

    avg_severity = sum(severities) / len(severities)
    max_severity = max(severities)

    # Apply formula: max(avg, max * 0.8)
    judgment_severity = max(avg_severity, max_severity * 0.8)

    logger.info(
        f"Calculated judgment_severity={judgment_severity:.1f} "
        f"(avg={avg_severity:.1f}, max={max_severity}, formula=max(avg, max*0.8))"
    )

    return round(judgment_severity, 1)


# ============================================================
# Task 16: Check Hard Flags
# ============================================================

def check_hard_flags(responses: List[Dict[str, Any]]) -> List[str]:
    """
    Check for hard flags in ALL responses (success status irrelevant).

    Hard flags (compliance/security/privacy) trigger automatic rejection
    regardless of scores or other factors.

    Args:
        responses: List of AI responses from call_ai_async()

    Returns:
        List[str]: Detected hard flags (e.g., ["compliance", "security"])
                   Empty list if no hard flags detected

    Example:
        >>> responses = [
        ...     {"success": True, "response": {"hard_flag": "security"}},
        ...     {"success": True, "response": {"hard_flag": "none"}},
        ...     {"success": False, "response": None}
        ... ]
        >>> check_hard_flags(responses)
        ['security']
    """
    detected_flags = []

    for r in responses:
        # Check all responses, even if success=False
        if r.get("response") and isinstance(r["response"], dict):
            hard_flag = r["response"].get("hard_flag", "none")
            if hard_flag != "none" and hard_flag not in detected_flags:
                detected_flags.append(hard_flag)
                logger.warning(f"Hard flag detected: {hard_flag} from {r.get('ai', 'unknown')}")

    if detected_flags:
        logger.warning(f"Total hard flags detected: {detected_flags}")
    else:
        logger.info("No hard flags detected")

    return detected_flags


# ============================================================
# Task 17: Calculate Final Result
# ============================================================

def calculate_final_result(
    responses: List[Dict[str, Any]],
    judgment_severity: float,
    hard_flags: List[str]
) -> Tuple[str, str, str, float]:
    """
    Calculate final judgment result (UPDATED for Task T5).

    変更内容:
    - risk < 0.6 制約を完全削除
    - _determine_final_decision()を呼び出す新アーキテクチャ

    Priority Logic:
    1. Hard flags detected → Instant rejection
    2. Weighted scoring with dynamic thresholds (risk制約削除済み)

    Weighted Scoring:
    - 承認 = 1.0 point
    - 部分的承認 = 0.5 point
    - 否決 = 0.0 point

    Dynamic Threshold Logic (Task T4 _get_judgment_thresholds):
    - HIGH (severity >= 80): approve=3.0, conditional=2.0
    - MID (50-79): approve=2.0, conditional=1.5
    - LOW (<50): approve=1.5, conditional=1.0

    Args:
        responses: List of AI responses
        judgment_severity: Calculated judgment severity (0-100)
        hard_flags: List of detected hard flags

    Returns:
        Tuple[str, str, str, float]: (result, reasoning, severity_level, total_score)
        - result: "承認" | "否決" | "条件付き承認"
        - reasoning: Explanation string
        - severity_level: "HIGH" | "MID" | "LOW"
        - total_score: Total decision score (0.0-3.0)

    Example:
        >>> responses = [
        ...     {"success": True, "response": {"decision": "承認", "scores": {"risk": 0.8}}},
        ...     {"success": True, "response": {"decision": "承認", "scores": {"risk": 0.9}}},
        ...     {"success": True, "response": {"decision": "部分的承認", "scores": {"risk": 0.7}}}
        ... ]
        >>> calculate_final_result(responses, 65.0, [])
        ('承認', '合計点2.5/2.0 (MID重大度)', 'MID', 2.5)
    """
    # Step 0: Check for NOT_APPLICABLE (意思決定以外の入力)
    successful_responses = [r for r in responses if r.get("success") and r.get("response")]
    not_applicable_count = sum(1 for r in successful_responses if r["response"].get("decision") == "NOT_APPLICABLE")

    if not_applicable_count >= 2:  # 2つ以上のAIがNOT_APPLICABLEと判断
        logger.info(f"NOT_APPLICABLE detected: {not_applicable_count}/3 AIs")
        return "NOT_APPLICABLE", "この質問は意思決定事項ではありません", "NONE", 0.0

    # Step 1: 新しい_determine_final_decision()を呼び出す
    return _determine_final_decision(responses, judgment_severity, hard_flags)


# ============================================================
# Task 18: Generate Conditional Reasoning
# ============================================================

def generate_conditional_reasoning(
    responses: List[Dict[str, Any]],
    score: float,
    judgment_severity: float,
    risk_level: str
) -> str:
    """
    Generate detailed reasoning for conditional approval (条件付き承認).

    Algorithm:
    1. Collect concerns from 部分的承認 or 否決 responses
    2. Deduplicate and select max 3 concerns
    3. Format: "判定用重大度X%（risk_level）で合計点Y/3.0点。条件付き承認されました。"
    4. Include concern list if available

    Args:
        responses: Successful AI responses
        score: Weighted approval score (0.0-3.0)
        judgment_severity: Judgment severity (0-100)
        risk_level: "高リスク" | "中リスク" | "低リスク"

    Returns:
        str: Formatted conditional approval reasoning (100-200 chars)

    Example:
        >>> responses = [
        ...     {"response": {"decision": "部分的承認", "concerns": ["予算超過の可能性", "期間が不透明"]}},
        ...     {"response": {"decision": "否決", "concerns": ["技術的困難"]}}
        ... ]
        >>> generate_conditional_reasoning(responses, 1.5, 65.0, "中リスク")
        '判定用重大度65.0%（中リスク）で合計点1.5/3.0点。条件付き承認されました。\\n懸念事項: 予算超過の可能性, 期間が不透明, 技術的困難。慎重な実行が推奨されます。'
    """
    # Base message
    base_msg = (
        f"判定用重大度{judgment_severity:.1f}%（{risk_level}）で合計点{score}/3.0点。"
        f"条件付き承認されました。"
    )

    # Step 1: Collect concerns from 部分的承認 or 否決 responses
    all_concerns = []
    for r in responses:
        decision = r.get("decision", "") if isinstance(r, dict) and "decision" in r else r.get("response", {}).get("decision", "")
        concerns = r.get("concerns", []) if isinstance(r, dict) and "concerns" in r else r.get("response", {}).get("concerns", [])

        if decision in ["部分的承認", "否決"] and concerns:
            all_concerns.extend(concerns)

    # Step 2: Deduplicate and select max 3 concerns
    unique_concerns = []
    seen = set()
    for concern in all_concerns:
        if concern not in seen:
            unique_concerns.append(concern)
            seen.add(concern)
        if len(unique_concerns) >= 3:
            break

    # Step 3: Format message
    if unique_concerns:
        concern_str = ', '.join(unique_concerns)
        concern_msg = f"懸念事項: {concern_str}。慎重な実行が推奨されます。"
    else:
        concern_msg = "一部AIの評価が保留のため、条件付き承認となりました。"

    return base_msg + "\n" + concern_msg


# ============================================================
# Task 19: Main Orchestration - judge_issue
# ============================================================

async def judge_issue(issue: str, persona_ids: Optional[List[str]] = None) -> JudgmentModel:
    """
    Main orchestration function for issue judgment.

    Process Flow:
    1. Call run_parallel_judgment(issue) to get AI responses
    2. Validate responses (ensure at least 2 successful)
    3. Calculate judgment_severity
    4. Check hard_flags
    5. Calculate final result (decision, reasoning, severity_level)
    6. Construct AIResponseModel instances for successful AIs
    7. Return JudgmentModel with all fields populated

    Args:
        issue: Issue text to judge (validated by JudgmentRequest)
        persona_ids: Optional list of persona IDs (e.g., ["neutral_ai", "neutral_ai", "neutral_ai"])

    Returns:
        JudgmentModel: Complete judgment result with:
            - result: Final decision
            - avg_severity: Average severity from all AIs
            - judgment_severity: Calculated judgment severity
            - severity_level: HIGH/MID/LOW classification
            - claude/gemini/chatgpt: AIResponseModel instances (or None if failed)
            - reasoning: Final decision reasoning
            - duration: Total elapsed time
            - plain_text_output: None (will be set by API layer if simple_mode)

    Raises:
        ValueError: If fewer than 2 AIs respond successfully

    Example:
        >>> judgment = await judge_issue("新機能Xを実装すべきか？")
        >>> judgment.result
        '承認'
        >>> judgment.severity_level
        'MID'
    """
    start_time = datetime.now()

    logger.info(f"Starting judgment for issue: {issue[:50]}...")

    # Step 1: Execute parallel judgment (with optional persona_ids)
    responses = await run_parallel_judgment(issue, persona_ids=persona_ids)

    # Step 2: Validate responses (require at least 2 successful)
    successful_responses = [r for r in responses if r.get("success")]
    if len(successful_responses) < 2:
        error_details = []
        for r in responses:
            ai_name = r.get("ai", "unknown")
            error = r.get("error", "unknown error")
            error_details.append(f"{ai_name}: {error}")

        logger.error(f"Insufficient successful responses: {len(successful_responses)}/3")
        raise ValueError(
            f"少なくとも2つのAIが必要ですが、{len(successful_responses)}個のみ成功しました。"
            f" エラー詳細: {'; '.join(error_details)}"
        )

    # Step 3: Calculate judgment severity (UPDATED to use _compute_final_severity from Task T4)
    judgment_severity = _compute_final_severity(responses)

    # Calculate average severity for database storage
    severities = [r["response"]["severity"] for r in successful_responses]
    avg_severity = sum(severities) / len(severities)

    # Step 4: Check hard flags
    hard_flags = check_hard_flags(responses)

    # Step 5: Calculate final result (UPDATED to use _determine_final_decision from Task T5)
    result, reasoning, severity_level, total_score = calculate_final_result(
        responses,
        judgment_severity,
        hard_flags
    )

    # Step 6: Construct AIResponseModel instances
    ai_response_models = {}
    for r in responses:
        ai_name = r.get("ai", "unknown").lower()
        if r.get("success") and r.get("response"):
            try:
                ai_response_models[ai_name] = AIResponseModel(
                    scores=r["response"]["scores"],
                    average_score=r["response"]["average_score"],
                    decision=r["response"]["decision"],
                    severity=r["response"]["severity"],
                    reason=r["response"]["reason"],
                    concerns=r["response"].get("concerns", []),
                    hard_flag=r["response"].get("hard_flag", "none"),
                    elapsed_seconds=r["elapsed_seconds"]
                )
            except Exception as e:
                logger.error(f"Failed to create AIResponseModel for {ai_name}: {e}")
                ai_response_models[ai_name] = None
        else:
            ai_response_models[ai_name] = None

    # Step 7: Calculate total duration
    duration = (datetime.now() - start_time).total_seconds()

    # Step 8: Construct and return JudgmentModel
    # IMPORTANT: avg_severity is kept for backward compatibility but judgment_severity is the correct value
    judgment = JudgmentModel(
        issue=issue,
        result=result,
        avg_severity=judgment_severity,  # Store judgment_severity in avg_severity for DB compatibility
        judgment_severity=judgment_severity,
        severity_level=severity_level,
        total_score=total_score,
        claude=ai_response_models.get("claude"),
        gemini=ai_response_models.get("gemini"),
        chatgpt=ai_response_models.get("chatgpt"),
        reasoning=reasoning,
        duration=duration,
        plain_text_output=None  # Will be set by API layer if simple_mode=True
    )

    logger.info(
        f"Judgment completed in {duration:.2f}s: "
        f"result={result}, severity_level={severity_level}, judgment_severity={judgment_severity:.1f}"
    )

    return judgment


# ============================================================
# Synchronous Wrapper for Testing
# ============================================================

def judge_issue_sync(issue: str) -> JudgmentModel:
    """
    Synchronous wrapper for judge_issue for testing purposes.

    Args:
        issue: Issue text to judge

    Returns:
        JudgmentModel: Complete judgment result

    Example:
        >>> judgment = judge_issue_sync("新機能を実装すべきか？")
        >>> judgment.result
        '承認'
    """
    return asyncio.run(judge_issue(issue))


# ============================================================
# NEW SPEC: Task T4 - Judgment Logic Base Functions
# ============================================================

def _compute_final_severity(responses: List[Dict[str, Any]]) -> float:
    """
    最終重大度（判定用重大度, judgment_severity）を計算

    変更内容:
    - 旧: max(平均重大度, 最大重大度 × 0.8)
    - 新: max(AI A重大度, AI B重大度, AI C重大度)

    Args:
        responses: AI応答リスト

    Returns:
        float: 最終重大度 (0-100)

    Example:
        >>> responses = [
        ...     {"success": True, "response": {"severity": 30}},
        ...     {"success": True, "response": {"severity": 90}},
        ...     {"success": True, "response": {"severity": 40}}
        ... ]
        >>> _compute_final_severity(responses)
        90.0
    """
    severities = [
        r["response"]["severity"]
        for r in responses
        if r.get("success") and r.get("response") and "severity" in r["response"]
    ]

    if not severities:
        logger.warning("No valid severities found in responses")
        return 0.0

    final_severity = max(severities)
    logger.info(f"Final severity (max of {severities}): {final_severity}")
    return final_severity


def _get_judgment_thresholds(severity: float) -> Dict[str, float]:
    """
    重大度別判定テーブル取得

    要件定義準拠の閾値:
    - HIGH (≥80): approve=3.0, conditional=2.0
    - MID (50-79): approve=2.0, conditional=1.5
    - LOW (<50): approve=1.5, conditional=1.0

    Args:
        severity: 最終重大度 (0-100)

    Returns:
        Dict[str, float]: {"approve": float, "conditional": float}

    Example:
        >>> _get_judgment_thresholds(85)
        {"approve": 3.0, "conditional": 2.0}
        >>> _get_judgment_thresholds(55)
        {"approve": 2.0, "conditional": 1.5}
        >>> _get_judgment_thresholds(30)
        {"approve": 1.5, "conditional": 1.0}
    """
    if severity >= 80:
        # HIGH重大度: 全員一致レベルの承認が必要
        return {"approve": 3.0, "conditional": 2.0}
    elif severity >= 50:
        # MID重大度: 多数決で承認可能
        return {"approve": 2.0, "conditional": 1.5}
    else:
        # LOW重大度: 過半数で承認可能
        return {"approve": 1.5, "conditional": 1.0}


def _determine_final_decision(
    responses: List[Dict[str, Any]],
    final_severity: float,
    hard_flags: List[str]
) -> Tuple[str, str, str, float]:
    """
    最終判定を決定

    変更内容:
    - risk < 0.6 制約を削除（ペルソナのdecision_policyに移譲）
    - 合計点計算: 承認=1.0, 部分的承認=0.5, 否決=0.0
    - 重大度別テーブル適用

    Args:
        responses: AI応答リスト
        final_severity: 最終重大度
        hard_flags: ハードフラグリスト

    Returns:
        Tuple[str, str, str, float]: (result, reasoning, severity_level, total_score)
    """
    # 1. ハードフラグチェック（最優先）
    if "compliance" in hard_flags or "security" in hard_flags or "privacy" in hard_flags:
        severity_level = "HIGH" if final_severity >= 80 else ("MID" if final_severity >= 50 else "LOW")
        flag_list = ', '.join(set(hard_flags))
        return (
            "否決",
            f"ハードフラグ検出: {flag_list}により自動否決",
            severity_level,
            0.0
        )

    # 2. 合計点計算
    decision_scores = {
        "承認": 1.0,
        "部分的承認": 0.5,
        "否決": 0.0
    }

    total_score = 0.0
    successful_responses = [r for r in responses if r.get("success") and r.get("response")]

    for r in successful_responses:
        decision = r["response"].get("decision", "否決")
        total_score += decision_scores.get(decision, 0.0)

    logger.info(f"Total decision score: {total_score}/3.0")

    # 3. 重大度別テーブル適用
    thresholds = _get_judgment_thresholds(final_severity)

    if final_severity >= 80:
        severity_level = "HIGH"
    elif final_severity >= 50:
        severity_level = "MID"
    else:
        severity_level = "LOW"

    # 4. 最終判定
    if total_score >= thresholds["approve"]:
        result = "承認"
        reasoning = f"合計点{total_score:.1f}/{thresholds['approve']:.1f} ({severity_level}重大度)"
    elif total_score >= thresholds["conditional"]:
        result = "条件付き承認"
        reasoning = f"合計点{total_score:.1f}/{thresholds['approve']:.1f} ({severity_level}重大度)"
    else:
        result = "否決"
        reasoning = f"合計点{total_score:.1f}/{thresholds['conditional']:.1f}未満 ({severity_level}重大度)"

    logger.info(f"Final decision: {result} - {reasoning}")
    return (result, reasoning, severity_level, total_score)
