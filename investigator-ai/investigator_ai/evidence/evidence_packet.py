"""Build the evidence packet: the deterministic, investigator-facing view of a case that is
the *only* thing the LLM is allowed to reason from.
"""

from __future__ import annotations

import math

from investigator_ai.schemas import Case, Evidence, EvidencePacket
from investigator_ai.scoring.risk_scorer import RiskScore, RiskScorer


class EvidencePacketBuilder:
    def __init__(self, scorer: RiskScorer):
        self._scorer = scorer

    def build(self, case: Case, peers: list[Case]) -> EvidencePacket:
        risk = self._scorer.score(case, peers)
        cfg = self._scorer.config

        scored: list[Evidence] = []
        for sid, spec in cfg.numeric_signals.items():
            scored.append(self._numeric_evidence(case, peers, sid, spec, risk))
        for sid, spec in cfg.binary_signals.items():
            scored.append(self._binary_evidence(case, sid, spec, risk))
        scored.sort(key=lambda e: e.contribution, reverse=True)

        context = self._context_evidence(case)

        return EvidencePacket(
            case_id=case.case_id,
            peer_group=f"{case.care_type} (n={len(peers)})",
            peer_group_size=len(peers),
            evidence=scored + context,
            heuristic_score=risk.score,
            heuristic_band=risk.band,  # type: ignore[arg-type]
            top_signal_ids=risk.ordered_signal_ids,
        )

    # --- per-signal evidence -------------------------------------------------
    def _numeric_evidence(self, case, peers, sid, spec, risk: RiskScore) -> Evidence:
        c = risk.contributions[sid]
        if not spec.unit or spec.unit == "USD":
            unit = ""
        elif spec.unit == "%":
            unit = "%"
        else:
            unit = f" {spec.unit}"
        peer_context = (
            f"Peer group {case.care_type} (n={len(peers)}): "
            f"{(c.percentile or 0) * 100:.0f}% of peers are at or below this. "
            f"Peer median {c.peer_median:g}{unit}, peer p90 {c.peer_p90:g}{unit}."
        )
        return Evidence(
            id=sid,
            label=spec.label(c.raw_value),
            category=spec.category,
            raw_value=round(c.raw_value, 2),
            unit=spec.unit,
            peer_context=peer_context,
            direction=c.direction,  # type: ignore[arg-type]
            severity=c.severity,  # type: ignore[arg-type]
            weight=c.weight,
            contribution=c.contribution,
        )

    def _binary_evidence(self, case, sid, spec, risk: RiskScore) -> Evidence:
        c = risk.contributions[sid]
        on = bool(c.raw_value)
        label = spec.label if on else f"Not flagged: {spec.label[0].lower()}{spec.label[1:]}"
        return Evidence(
            id=sid,
            label=label,
            category=spec.category,
            raw_value=int(c.raw_value),
            direction="elevated" if on else "normal",
            severity="high" if on else "info",
            weight=c.weight,
            contribution=c.contribution,
        )

    # --- non-scoring context + data quality -------------------------------
    def _context_evidence(self, case: Case) -> list[Evidence]:
        out = [
            Evidence(id="care_type", label=f"Care type: {case.care_type}", category="context",
                     raw_value=case.care_type),
            Evidence(id="state", label=f"State: {case.state}", category="context",
                     raw_value=case.state),
            Evidence(id="claim_date", label=f"Claim date: {case.claim_date}", category="context",
                     raw_value=case.claim_date),
        ]

        # Data quality: surface any missing / non-finite signal value for a human to chase.
        for sid in list(self._scorer.config.numeric_signals) + list(
            self._scorer.config.binary_signals
        ):
            v = getattr(case, sid, None)
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                out.append(
                    Evidence(
                        id=f"missing_{sid}",
                        label=f"Signal '{sid}' is missing for this case",
                        category="data_quality",
                        raw_value=None,
                        direction="unknown",
                        severity="low",
                    )
                )
        return out
