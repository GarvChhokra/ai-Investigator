"""Deterministic risk scoring.

Given a case and its peer group, compute a transparent 0-100 risk score and per-signal
contributions. No LLM, no randomness - identical inputs always yield identical output.
:class:`EvidencePacketBuilder` turns this into investigator-facing evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from investigator_ai.schemas import Case
from investigator_ai.scoring.config import DEFAULT_SCORING, ScoringConfig


@dataclass(frozen=True)
class SignalContribution:
    signal_id: str
    weight: float
    strength: float           # 0-1, how far above the peer norm
    contribution: float       # weight * strength
    raw_value: float
    percentile: float | None  # None for binary signals
    peer_median: float | None
    peer_p90: float | None
    direction: str
    severity: str


@dataclass(frozen=True)
class RiskScore:
    case_id: str
    score: float              # 0-100
    band: str
    peer_group_size: int
    contributions: dict[str, SignalContribution] = field(default_factory=dict)

    @property
    def ordered_signal_ids(self) -> list[str]:
        return [
            c.signal_id
            for c in sorted(
                (c for c in self.contributions.values() if c.contribution > 0),
                key=lambda c: c.contribution,
                reverse=True,
            )
        ]


def _percentile(value: float, population: list[float]) -> float:
    if not population:
        return 0.5
    return sum(1 for p in population if p <= value) / len(population)


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _quantile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def _severity(strength: float) -> str:
    if strength >= 0.66:
        return "high"
    if strength >= 0.33:
        return "medium"
    if strength > 0:
        return "low"
    return "info"


class RiskScorer:
    def __init__(self, scoring: ScoringConfig | None = None):
        self._cfg = scoring or DEFAULT_SCORING

    @property
    def config(self) -> ScoringConfig:
        return self._cfg

    def score(self, case: Case, peers: list[Case]) -> RiskScore:
        contributions: dict[str, SignalContribution] = {}

        for sid, spec in self._cfg.numeric_signals.items():
            value = float(getattr(case, sid))
            peer_values = [float(getattr(p, sid)) for p in peers]
            pctile = _percentile(value, peer_values)
            strength = max(0.0, (pctile - 0.5) * 2.0)  # only above-median counts
            contributions[sid] = SignalContribution(
                signal_id=sid,
                weight=spec.weight,
                strength=strength,
                contribution=round(spec.weight * strength, 3),
                raw_value=value,
                percentile=pctile,
                peer_median=_median(peer_values),
                peer_p90=_quantile(peer_values, 0.9),
                direction=self._direction(pctile),
                severity=_severity(strength),
            )

        for sid, spec in self._cfg.binary_signals.items():
            value = float(getattr(case, sid))
            contributions[sid] = SignalContribution(
                signal_id=sid,
                weight=spec.weight,
                strength=value,
                contribution=round(spec.weight * value, 3),
                raw_value=value,
                percentile=None,
                peer_median=None,
                peer_p90=None,
                direction="elevated" if value else "normal",
                severity="high" if value else "info",
            )

        raw = sum(c.contribution for c in contributions.values())
        score = round(100.0 * raw / self._cfg.max_score, 1)
        return RiskScore(
            case_id=case.case_id,
            score=score,
            band=self._cfg.band(score),
            peer_group_size=len(peers),
            contributions=contributions,
        )

    def _direction(self, pctile: float) -> str:
        if pctile >= self._cfg.elevated_pctile:
            return "elevated"
        if pctile <= self._cfg.low_pctile:
            return "low"
        return "normal"
