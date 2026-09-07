from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["Low", "Medium", "High"]
Confidence = Literal["Low", "Medium", "High"]
Direction = Literal["elevated", "normal", "low", "unknown"]
Severity = Literal["high", "medium", "low", "info"]
EvidenceCategory = Literal[
    "billing", "relationship", "utilization", "geography", "policy", "context", "data_quality"
]


class Case(BaseModel):
    """One referred claim, straight from the queue (CSV row), lightly typed."""

    case_id: str
    claim_number: str
    claim_date: str
    care_type: str
    claim_amount_usd: float
    state: str
    duplicate_service_billed: int
    weekly_visit_frequency: float
    member_provider_distance_miles: float
    prior_claims_last_12mo: float
    shared_contact_with_provider: int
    weekend_billing_ratio: float
    amount_vs_peer_avg_pct: float
    round_dollar_billing_ratio: float
    recent_policy_change_flag: int
    service_overlap_other_provider: int


class Evidence(BaseModel):
    """A single computed fact about the case. Deterministic - no model involved."""

    id: str = Field(description="Stable identifier the LLM cites, e.g. 'amount_vs_peer_avg_pct'")
    label: str = Field(description="Human-readable one-liner, e.g. 'Billed 146% above peer average'")
    category: EvidenceCategory
    raw_value: float | int | str | None
    unit: str | None = None
    peer_context: str | None = Field(
        default=None, description="How this compares to the peer group, in plain words."
    )
    direction: Direction = "normal"
    severity: Severity = "info"
    weight: float = 0.0
    contribution: float = Field(
        default=0.0, description="weight * signal-strength; how much this moved the risk score"
    )


class EvidencePacket(BaseModel):
    """Everything the deterministic layer knows about a case - the LLM's whole world."""

    case_id: str
    peer_group: str
    peer_group_size: int
    evidence: list[Evidence]
    heuristic_score: float = Field(description="0-100, higher = more suspicious")
    heuristic_band: RiskLevel
    top_signal_ids: list[str] = Field(description="Evidence ids sorted by contribution, desc")

    def evidence_ids(self) -> set[str]:
        return {e.id for e in self.evidence}


class KeyIndicator(BaseModel):
    evidence_id: str = Field(description="Must match an Evidence.id from the packet")
    explanation: str = Field(description="Why this indicator matters for THIS case, 1-2 sentences")


class AssessmentLLM(BaseModel):
    """The schema the LLM is constrained to. Kept small and strict."""

    summary: str = Field(description="2-4 sentences a busy investigator can scan")
    risk_level: RiskLevel
    confidence: Confidence
    key_indicators: list[KeyIndicator] = Field(min_length=1, max_length=6)
    recommended_action: str = Field(description="One concrete next step for the investigator")
    missing_info: list[str] = Field(
        default_factory=list,
        description="Data the AI could not verify that a human should check. [] if none.",
    )


class Assessment(BaseModel):
    """Final per-case assessment served to the UI: LLM judgement + deterministic evidence."""

    case_id: str
    summary: str
    risk_level: RiskLevel
    confidence: Confidence
    key_indicators: list[KeyIndicator]
    recommended_action: str
    missing_info: list[str] = Field(default_factory=list)

    # Grounding / transparency metadata
    evidence: list[Evidence]
    heuristic_score: float
    heuristic_band: RiskLevel
    peer_group: str
    disagreement: bool = Field(
        default=False,
        description="True when the LLM risk_level differs from the heuristic band",
    )
    validation_notes: list[str] = Field(default_factory=list)
    llm_used: bool = True
    model: str | None = None
    signals_hash: str | None = Field(default=None, description="Cache key - hash of signal values")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChatCitation(BaseModel):
    evidence_id: str
    label: str


class ChatAnswer(BaseModel):
    case_id: str
    question: str
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
