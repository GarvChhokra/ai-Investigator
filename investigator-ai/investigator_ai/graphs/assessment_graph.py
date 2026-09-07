"""Per-case assessment as a small LangGraph state machine.

    build_packet -> llm_assess -> validate -> (retry once | finalize)

The deterministic layer builds the evidence packet up front; the single LLM step only
synthesises and judges, constrained to a strict schema and to citing evidence by id.
``validate`` is the deterministic critic: it repairs bad citations, checks the LLM against
the heuristic prior, and either triggers one retry with feedback or falls back to a
rules-only assessment rather than surfacing a broken card.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from investigator_ai.data import signals_hash
from investigator_ai.evidence.evidence_packet import EvidencePacketBuilder
from investigator_ai.llm.client import AssessmentLlmClient, LlmUnavailable
from investigator_ai.prompts import ASSESSMENT_SYSTEM, assessment_user_prompt
from investigator_ai.scoring.config import BAND_ORDER
from investigator_ai.schemas import Assessment, AssessmentLLM, Case, EvidencePacket, KeyIndicator


class _State(TypedDict, total=False):
    case: Case
    peers: list[Case]
    packet: EvidencePacket
    attempts: int
    feedback: str
    llm_result: AssessmentLLM | None
    llm_error: str | None
    validation_notes: list[str]
    assessment: Assessment


def _band_gap(a: str, b: str) -> int:
    return abs(BAND_ORDER.index(a) - BAND_ORDER.index(b))


class AssessmentGraphRunner:
    def __init__(
        self,
        evidence_builder: EvidencePacketBuilder,
        llm_client: AssessmentLlmClient,
        max_attempts: int = 2,
    ):
        self._evidence_builder = evidence_builder
        self._llm = llm_client
        self._max_attempts = max_attempts
        self._graph = self._build_graph()

    # --- public ----------------------------------------------------------
    def run(self, case: Case, peers: list[Case]) -> Assessment:
        final = self._graph.invoke({"case": case, "peers": peers})
        return final["assessment"]

    # --- nodes ---------------------------------------------------------
    def _build_packet(self, state: _State) -> _State:
        packet = self._evidence_builder.build(state["case"], state["peers"])
        return {"packet": packet, "attempts": 0, "validation_notes": []}

    def _llm_assess(self, state: _State) -> _State:
        prompt = assessment_user_prompt(state["case"], state["packet"])
        if state.get("feedback"):
            prompt += f"\n\nREVISION REQUESTED - fix this and try again:\n{state['feedback']}"
        try:
            result = self._llm.assess(ASSESSMENT_SYSTEM, prompt)
            return {"llm_result": result, "llm_error": None, "attempts": state["attempts"] + 1}
        except LlmUnavailable as exc:
            return {"llm_result": None, "llm_error": str(exc), "attempts": state["attempts"] + 1}
        except Exception as exc:  # noqa: BLE001 - any failure degrades gracefully
            return {
                "llm_result": None,
                "llm_error": f"{type(exc).__name__}: {exc}",
                "attempts": state["attempts"] + 1,
            }

    def _validate(self, state: _State) -> _State:
        notes = list(state.get("validation_notes", []))
        result = state.get("llm_result")
        packet = state["packet"]

        if result is None:
            notes.append(
                f"LLM unavailable ({state.get('llm_error')}); using rules-only fallback."
            )
            return {"validation_notes": notes, "feedback": ""}

        valid_ids = packet.evidence_ids()
        kept, dropped = [], []
        for ind in result.key_indicators:
            (kept if ind.evidence_id in valid_ids else dropped).append(ind)
        if dropped:
            notes.append(
                "Dropped indicator(s) citing unknown evidence id: "
                + ", ".join(i.evidence_id for i in dropped)
                + "."
            )
        result.key_indicators = kept

        problems: list[str] = []
        if not kept:
            problems.append("key_indicators must cite at least one id from the packet.")
        if _band_gap(result.risk_level, packet.heuristic_band) > 1:
            problems.append(
                f"risk_level '{result.risk_level}' is more than one level from the "
                f"deterministic band '{packet.heuristic_band}'. Move within one level."
            )

        if problems and state["attempts"] < self._max_attempts:
            return {"llm_result": result, "validation_notes": notes, "feedback": " ".join(problems)}
        if problems:
            notes.append("LLM still off after retry: " + " ".join(problems))
        return {"llm_result": result, "validation_notes": notes, "feedback": ""}

    def _finalize(self, state: _State) -> _State:
        case, packet = state["case"], state["packet"]
        notes = state.get("validation_notes", [])
        result = state.get("llm_result")

        if result is None or not result.key_indicators:
            return {"assessment": _fallback(case, packet, notes)}

        return {
            "assessment": Assessment(
                case_id=case.case_id,
                summary=result.summary,
                risk_level=result.risk_level,
                confidence=result.confidence,
                key_indicators=result.key_indicators,
                recommended_action=result.recommended_action,
                missing_info=result.missing_info,
                evidence=packet.evidence,
                heuristic_score=packet.heuristic_score,
                heuristic_band=packet.heuristic_band,
                peer_group=packet.peer_group,
                disagreement=_band_gap(result.risk_level, packet.heuristic_band) >= 1,
                validation_notes=notes,
                llm_used=True,
                model=self._llm.model_id,
                signals_hash=signals_hash(case),
            )
        }

    @staticmethod
    def _route(state: _State) -> str:
        return "llm_assess" if state.get("feedback") else "finalize"

    def _build_graph(self):
        g = StateGraph(_State)
        g.add_node("build_packet", self._build_packet)
        g.add_node("llm_assess", self._llm_assess)
        g.add_node("validate", self._validate)
        g.add_node("finalize", self._finalize)
        g.set_entry_point("build_packet")
        g.add_edge("build_packet", "llm_assess")
        g.add_edge("llm_assess", "validate")
        g.add_conditional_edges(
            "validate", self._route, {"llm_assess": "llm_assess", "finalize": "finalize"}
        )
        g.add_edge("finalize", END)
        return g.compile()


def _fallback(case: Case, packet: EvidencePacket, notes: list[str]) -> Assessment:
    top = [e for e in packet.evidence if e.contribution > 0][:3]
    indicators = [
        KeyIndicator(evidence_id=e.id, explanation=f"{e.label}. {e.peer_context or ''}".strip())
        for e in top
    ] or [
        KeyIndicator(
            evidence_id=packet.evidence[0].id,
            explanation="No signals are elevated versus peers for this case.",
        )
    ]
    return Assessment(
        case_id=case.case_id,
        summary=(
            f"Rules-only assessment (AI narration unavailable). Deterministic score "
            f"{packet.heuristic_score}/100 puts this in the {packet.heuristic_band} band for "
            f"{packet.peer_group}. Review the indicators below directly."
        ),
        risk_level=packet.heuristic_band,
        confidence="Low",
        key_indicators=indicators,
        recommended_action=(
            "Escalate for manual review - the AI summary could not be generated, so rely on "
            "the deterministic indicators and your own judgement."
        ),
        missing_info=["AI-generated narrative and recommended action (LLM was unavailable)."],
        evidence=packet.evidence,
        heuristic_score=packet.heuristic_score,
        heuristic_band=packet.heuristic_band,
        peer_group=packet.peer_group,
        disagreement=False,
        validation_notes=notes,
        llm_used=False,
        model=None,
        signals_hash=signals_hash(case),
    )
