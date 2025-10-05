"""
Pydantic models for MAGIN (Multi-AI Governance Interfaces Node).

This module defines all data models for API requests, responses, and database records
according to the new specification with 4-aspect scoring and hard flags.

New Specification Features:
- 4-aspect scoring: validity, feasibility, risk, certainty (0.0-1.0)
- Hard flags: compliance/security/privacy automatic detection
- Weighted judgment: approval=1.0, partial=0.5, rejection=0.0
- Plain text output for simple mode
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class AIScores(BaseModel):
    """
    4-aspect scoring model for AI evaluation (New Specification).

    Each aspect is scored from 0.0 to 1.0:
    - validity: Proposal alignment with objectives
    - feasibility: Resource and condition availability
    - risk: Safety/ethics/cost risk level (1.0=minimal risk, 0.0=critical risk)
    - certainty: Evidence and assumption clarity

    Example:
        >>> scores = AIScores(
        ...     validity=0.85,
        ...     feasibility=0.90,
        ...     risk=0.70,
        ...     certainty=0.80
        ... )
        >>> scores.validity
        0.85
    """

    validity: float = Field(
        ...,
        description="Proposal alignment with objectives (0.0-1.0)",
    )
    feasibility: float = Field(
        ...,
        description="Resource and condition availability (0.0-1.0)",
    )
    risk: float = Field(
        ...,
        description="Safety/ethics/cost risk level (1.0=minimal, 0.0=critical)",
    )
    certainty: float = Field(
        ...,
        description="Evidence and assumption clarity (0.0-1.0)",
    )

    @field_validator("validity", "feasibility", "risk", "certainty")
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        """Clip scores to 0.0-1.0 range if out of bounds."""
        return max(0.0, min(1.0, v))


class AIResponseModel(BaseModel):
    """
    Individual AI response model (New Specification).

    Includes 4-aspect scores, average score, decision, severity, reasoning,
    concerns, hard flag detection, and elapsed time.

    Example:
        >>> response = AIResponseModel(
        ...     scores=AIScores(validity=0.9, feasibility=0.85, risk=0.75, certainty=0.88),
        ...     average_score=0.845,
        ...     decision="承認",
        ...     severity=65,
        ...     reason="提案は実現可能で妥当性が高い",
        ...     concerns=["予算超過の可能性"],
        ...     hard_flag="none",
        ...     elapsed_seconds=12.5
        ... )
        >>> response.decision
        '承認'
    """

    scores: AIScores = Field(
        ..., description="4-aspect evaluation scores (validity/feasibility/risk/certainty)"
    )
    average_score: float = Field(
        ...,
        description="Average of 4 aspect scores (0.0-1.0)",
    )
    decision: str = Field(
        ...,
        description="AI decision: 承認 | 部分的承認 | 否決",
    )
    severity: int = Field(
        ..., description="Issue severity score (0-100)"
    )
    reason: str = Field(..., description="Reasoning for the decision (100 chars approx)")
    concerns: List[str] = Field(
        default_factory=list, description="List of concerns raised by the AI"
    )
    hard_flag: str = Field(
        default="none",
        description="Hard flag: none | compliance | security | privacy",
    )
    elapsed_seconds: float = Field(
        ..., ge=0.0, description="AI response elapsed time in seconds"
    )

    @field_validator("average_score")
    @classmethod
    def validate_average_score(cls, v: float) -> float:
        """Clip average score to 0.0-1.0 range if out of bounds."""
        return max(0.0, min(1.0, v))

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        """Validate decision is one of the allowed values, default to 否決 if invalid."""
        allowed = ["承認", "部分的承認", "否決", "NOT_APPLICABLE", "FAILED"]
        if v not in allowed:
            return "否決"  # Invalid values default to rejection
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: int) -> int:
        """Clip severity to 0-100 range if out of bounds."""
        return max(0, min(100, v))

    @field_validator("hard_flag")
    @classmethod
    def validate_hard_flag(cls, v: str) -> str:
        """Validate hard_flag is one of the allowed values, default to 'none' if invalid."""
        allowed = ["none", "compliance", "security", "privacy"]
        if v not in allowed:
            return "none"  # Invalid values default to none
        return v


class JudgmentRequest(BaseModel):
    """
    Request model for judgment endpoint.

    Validates user input for issue text and simple mode flag.
    Implements security checks for dangerous characters and length constraints.

    Example:
        >>> request = JudgmentRequest(
        ...     issue="新機能Xを実装すべきか？",
        ...     simple_mode=False
        ... )
        >>> request.issue
        '新機能Xを実装すべきか？'
    """

    issue: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Issue text to judge (10-2000 chars)",
    )
    simple_mode: bool = Field(
        default=False, description="Simple mode flag (no animations, plain text output)"
    )

    @field_validator("issue")
    @classmethod
    def validate_issue(cls, v: str) -> str:
        """
        Validate issue text:
        - Remove dangerous characters (shell injection prevention)
        - Remove control characters
        - Ensure non-empty after stripping
        """
        # Check for dangerous shell characters
        dangerous_chars = [";", "|", "&", "`", "$", "(", ")"]
        if any(char in v for char in dangerous_chars):
            raise ValueError("危険な文字が含まれています")

        # Remove control characters (keep only printable + newline/tab)
        v = "".join(c for c in v if c.isprintable() or c in "\n\r\t")

        # Ensure non-empty after cleanup
        if not v.strip():
            raise ValueError("議題が空です")

        return v.strip()


class JudgmentModel(BaseModel):
    """
    Complete judgment result model.

    Contains final decision, reasoning, severity classification,
    individual AI responses, timestamp, duration, and optional plain text output.

    New Specification:
    - plain_text_output: Optional field for simple mode text-only output
    - judgment_severity: Calculated as max(avg_severity, max_severity * 0.8)
    - severity_level: Classification as HIGH/MID/LOW based on judgment_severity

    Example:
        >>> judgment = JudgmentModel(
        ...     id=1,
        ...     issue="新機能Xを実装すべきか？",
        ...     result="承認",
        ...     avg_severity=65.0,
        ...     judgment_severity=68.0,
        ...     severity_level="MID",
        ...     claude=AIResponseModel(...),
        ...     gemini=AIResponseModel(...),
        ...     chatgpt=AIResponseModel(...),
        ...     reasoning="判定用重大度68.0%（中リスク）で合計点2.5/3.0点。過半数の要件を満たし承認されました。",
        ...     created_at=datetime.now(),
        ...     duration=45.2
        ... )
        >>> judgment.result
        '承認'
    """

    id: Optional[int] = Field(default=None, description="Database record ID")
    issue: str = Field(..., description="Original issue text")
    result: str = Field(
        ..., description="Final decision: 承認 | 否決 | 条件付き承認"
    )
    avg_severity: float = Field(
        ..., ge=0.0, le=100.0, description="Average severity from all AIs (0-100)"
    )
    judgment_severity: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Judgment severity = max(avg_severity, max_severity * 0.8)",
    )
    severity_level: Optional[str] = Field(
        default=None, description="Severity classification: HIGH | MID | LOW"
    )
    claude: Optional[AIResponseModel] = Field(
        default=None, description="Claude AI response (None if failed)"
    )
    gemini: Optional[AIResponseModel] = Field(
        default=None, description="Gemini AI response (None if failed)"
    )
    chatgpt: Optional[AIResponseModel] = Field(
        default=None, description="ChatGPT AI response (None if failed)"
    )
    reasoning: str = Field(
        ..., description="Final decision reasoning (100-200 chars)"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="Judgment creation timestamp"
    )
    duration: Optional[float] = Field(
        default=None, ge=0.0, description="Total judgment duration in seconds"
    )
    plain_text_output: Optional[str] = Field(
        default=None,
        description="Plain text output for simple mode (New Specification)",
    )

    @field_validator("result")
    @classmethod
    def validate_result(cls, v: str) -> str:
        """Validate final result is one of the allowed values."""
        allowed = ["承認", "否決", "条件付き承認", "NOT_APPLICABLE"]
        if v not in allowed:
            raise ValueError(f"Invalid result: {v}. Must be one of {allowed}")
        return v

    @field_validator("severity_level")
    @classmethod
    def validate_severity_level(cls, v: Optional[str]) -> Optional[str]:
        """Validate severity level if provided."""
        if v is None:
            return v
        allowed = ["HIGH", "MID", "LOW", "NONE"]
        if v not in allowed:
            raise ValueError(f"Invalid severity_level: {v}. Must be one of {allowed}")
        return v


class ErrorResponse(BaseModel):
    """
    Error response model for API errors.

    Example:
        >>> error = ErrorResponse(
        ...     error="INSUFFICIENT AI RESPONSES",
        ...     details=["Claude: timeout", "Gemini: JSON parse error"]
        ... )
        >>> error.error
        'INSUFFICIENT AI RESPONSES'
    """

    error: str = Field(..., description="Error message")
    details: Optional[List[str]] = Field(
        default=None, description="Detailed error information"
    )
