"""HTTP request/response DTOs. Kept separate from domain + reasoning-layer models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from investigator_ai.schemas import Assessment

from app.domain import (
    CaseStatus,
    ChatMessage,
    Decision,
    DecisionAction,
    IndicatorVerdict,
    Note,
    RiskLevel,
)


class AssessmentSummary(BaseModel):
    """Compact assessment view for the queue list."""

    risk_level: RiskLevel
    confidence: str
    summary: str
    heuristic_score: float
    heuristic_band: RiskLevel
    disagreement: bool
    llm_used: bool


class CaseListItem(BaseModel):
    case_id: str
    claim_number: str
    claim_date: str
    care_type: str
    claim_amount_usd: float
    state: str
    status: CaseStatus
    assessment: AssessmentSummary | None
    effective_risk: RiskLevel | None = Field(
        description="risk_override if the investigator set one, else the AI risk_level"
    )


class QueueCounts(BaseModel):
    total: int
    assessed: int
    needs_review: int  # Medium + High and not yet RESOLVED
    likely_benign: int  # Low
    high: int
    medium: int
    low: int
    resolved: int
    high_dollar: int  # claim_amount_usd >= HIGH_DOLLAR and still open
    disagreements: int  # AI risk level differs from the rule-based band, still open


class QueueResponse(BaseModel):
    counts: QueueCounts
    cases: list[CaseListItem]


class CaseDetail(BaseModel):
    case_id: str
    case: dict
    status: CaseStatus
    assessment: Assessment | None
    effective_risk: RiskLevel | None
    decisions: list[Decision]
    notes: list[Note]
    chat: list[ChatMessage]


class BatchAssessResponse(BaseModel):
    assessed: int
    reused_from_cache: int
    total: int


class DecisionRequest(BaseModel):
    action: DecisionAction
    risk_override: RiskLevel | None = None
    indicator_verdicts: dict[str, IndicatorVerdict] = Field(default_factory=dict)
    rationale: str | None = None


class NoteRequest(BaseModel):
    body: str = Field(min_length=1)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
