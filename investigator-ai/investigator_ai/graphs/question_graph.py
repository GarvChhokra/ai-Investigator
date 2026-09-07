"""Grounded follow-up Q&A for a single case.

A question is one constrained call over a fixed context (case row + evidence packet + prior
assessment summary), so this "graph" is linear: build_packet -> answer. The system prompt
forbids going beyond the supplied context. No dataset access, no memory of other cases.
"""

from __future__ import annotations

from collections.abc import Iterator

from investigator_ai.evidence.evidence_packet import EvidencePacketBuilder
from investigator_ai.llm.client import LlmUnavailable, QuestionLlmClient
from investigator_ai.prompts import QUESTION_SYSTEM, question_user_prompt
from investigator_ai.schemas import Case, ChatAnswer, ChatCitation, EvidencePacket

Msg = dict  # {"role": "investigator" | "assistant", "content": str}


class QuestionGraphRunner:
    def __init__(
        self,
        evidence_builder: EvidencePacketBuilder,
        llm_client: QuestionLlmClient,
    ):
        self._evidence_builder = evidence_builder
        self._llm = llm_client

    # --- context ---------------------------------------------------------
    def _packet(self, case: Case, peers: list[Case]) -> EvidencePacket:
        return self._evidence_builder.build(case, peers)

    def _prompt(self, case, packet, assessment_summary, history, question) -> str:
        return question_user_prompt(
            case, packet, assessment_summary or "(no prior assessment)", history or [], question
        )

    # --- public ------------------------------------------------------
    def answer(
        self,
        case: Case,
        peers: list[Case],
        question: str,
        *,
        assessment_summary: str = "",
        history: list[Msg] | None = None,
    ) -> ChatAnswer:
        packet = self._packet(case, peers)
        prompt = self._prompt(case, packet, assessment_summary, history, question)
        try:
            text = self._llm.answer(QUESTION_SYSTEM, prompt)
        except LlmUnavailable as exc:
            text = (
                "The chat assistant is offline (no model API key configured), so I can't "
                f"answer free-form questions right now. Reason: {exc}"
            )
        except Exception as exc:  # noqa: BLE001
            text = f"Sorry - the assistant hit an error answering that ({type(exc).__name__})."
        return ChatAnswer(
            case_id=case.case_id,
            question=question,
            answer=text.strip(),
            citations=citations_for(packet, text),
        )

    def stream(
        self,
        case: Case,
        peers: list[Case],
        question: str,
        *,
        assessment_summary: str = "",
        history: list[Msg] | None = None,
    ) -> Iterator[str]:
        packet = self._packet(case, peers)
        prompt = self._prompt(case, packet, assessment_summary, history, question)
        try:
            yield from self._llm.stream(QUESTION_SYSTEM, prompt)
        except LlmUnavailable as exc:
            yield f"The chat assistant is offline (no model API key configured). Reason: {exc}"
        except Exception as exc:  # noqa: BLE001
            yield f"Sorry - the assistant hit an error answering that ({type(exc).__name__})."

    def citations(self, case: Case, peers: list[Case], text: str) -> list[ChatCitation]:
        return citations_for(self._packet(case, peers), text)


def citations_for(packet: EvidencePacket, answer_text: str) -> list[ChatCitation]:
    out: list[ChatCitation] = []
    lowered = answer_text.lower()
    for e in packet.evidence:
        if e.category in {"context", "data_quality"}:
            continue
        key = e.label.split(".")[0].strip().lower()
        if e.id in lowered or (len(key) > 8 and key[:24] in lowered):
            out.append(ChatCitation(evidence_id=e.id, label=e.label))
    return out[:5]
