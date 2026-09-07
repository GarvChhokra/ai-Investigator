"""Scoring configuration - pure data, no behaviour.

Bundled into :data:`DEFAULT_SCORING` and injected into :class:`RiskScorer` so the weights
and thresholds can be reviewed, version-controlled, and (in a real system) calibrated
against investigator outcomes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from investigator_ai.schemas import EvidenceCategory


@dataclass(frozen=True)
class NumericSignal:
    weight: float
    category: EvidenceCategory
    unit: str | None
    label: Callable[[float], str]


@dataclass(frozen=True)
class BinarySignal:
    weight: float
    category: EvidenceCategory
    label: str


_NUMERIC: dict[str, NumericSignal] = {
    "amount_vs_peer_avg_pct": NumericSignal(
        2.5, "billing", "%", lambda v: f"Billed {v:+.0f}% vs peer average"
    ),
    "member_provider_distance_miles": NumericSignal(
        2.0, "geography", "mi", lambda v: f"Member is {v:.0f} miles from the provider"
    ),
    "prior_claims_last_12mo": NumericSignal(
        1.5, "utilization", "claims", lambda v: f"{v:.0f} prior claims in the last 12 months"
    ),
    "round_dollar_billing_ratio": NumericSignal(
        1.5, "billing", None, lambda v: f"{v * 100:.0f}% of charges are round-dollar amounts"
    ),
    "weekly_visit_frequency": NumericSignal(
        1.3, "utilization", "/wk", lambda v: f"{v:.0f} visits per week billed"
    ),
    "weekend_billing_ratio": NumericSignal(
        1.3, "billing", None, lambda v: f"{v * 100:.0f}% of billing falls on weekends"
    ),
    "claim_amount_usd": NumericSignal(
        0.8, "billing", "USD", lambda v: f"Claim amount ${v:,.0f}"
    ),
}

_BINARY: dict[str, BinarySignal] = {
    "duplicate_service_billed": BinarySignal(
        2.5, "billing", "Duplicate service billed on this claim"
    ),
    "shared_contact_with_provider": BinarySignal(
        2.5, "relationship", "Member shares a contact detail with the provider"
    ),
    "service_overlap_other_provider": BinarySignal(
        2.0, "relationship", "Same service billed by another provider in the same period"
    ),
    "recent_policy_change_flag": BinarySignal(
        1.2, "policy", "Policy was changed shortly before this claim"
    ),
}


@dataclass(frozen=True)
class ScoringConfig:
    numeric_signals: dict[str, NumericSignal] = field(default_factory=lambda: dict(_NUMERIC))
    binary_signals: dict[str, BinarySignal] = field(default_factory=lambda: dict(_BINARY))
    # Score -> band. Calibrated against the synthetic queue: obvious fraud lands well above
    # high_min; clean low-dollar claims land below medium_min.
    medium_min: float = 22.0
    high_min: float = 42.0
    elevated_pctile: float = 0.75
    low_pctile: float = 0.25

    @property
    def max_score(self) -> float:
        return sum(s.weight for s in self.numeric_signals.values()) + sum(
            s.weight for s in self.binary_signals.values()
        )

    def band(self, score: float) -> str:
        if score >= self.high_min:
            return "High"
        if score >= self.medium_min:
            return "Medium"
        return "Low"


BAND_ORDER: tuple[str, ...] = ("Low", "Medium", "High")

DEFAULT_SCORING = ScoringConfig()
