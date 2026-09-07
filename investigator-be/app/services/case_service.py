"""Application service: the one place the API talks to for everything case-related.

Orchestrates the reasoning layer (assessment + question graph runners) and the in-memory
state (decisions, notes, chat history, status).
"""

from __future__ import annotations

from collections.abc import Iterator

from investigator_ai.data import Dataset, signals_hash
from investigator_ai.graphs.assessment_graph import AssessmentGraphRunner
from investigator_ai.graphs.question_graph import QuestionGraphRunner
from investigator_ai.schemas import Assessment, Case

from app.domain import ChatMessage, Decision, Note
from app.schemas import (
    AssessmentSummary,
    BatchAssessResponse,
    CaseDetail,
    CaseListItem,
    ChatRequest,
    DecisionRequest,
    NoteRequest,
    QueueCounts,
    QueueResponse,
)
from app.stores import InMemoryState


class CaseService:
    def __init__(
        self,
        dataset: Dataset,
        state: InMemoryState,
        assessment_graph: AssessmentGraphRunner,
        question_graph: QuestionGraphRunner,
        actor: str = "investigator",
    ):
        self._dataset = dataset
        self._state = state
        self._assessment_graph = assessment_graph
        self._question_graph = question_graph
        self._actor = actor

    # --- helpers ---------------------------------------------------------
    def case_exists(self, case_id: str) -> bool:
        try:
            self._dataset.get(case_id)
            return True
        except KeyError:
            return False

    def _peers(self, case: Case) -> list[Case]:
        return self._dataset.peers(case.care_type)

    def _summary(self, a: Assessment | None) -> AssessmentSummary | None:
        if a is None:
            return None
        return AssessmentSummary(
            risk_level=a.risk_level,
            confidence=a.confidence,
            summary=a.summary,
            heuristic_score=a.heuristic_score,
            heuristic_band=a.heuristic_band,
            disagreement=a.disagreement,
            llm_used=a.llm_used,
        )

    def _effective_risk(self, case_id: str, a: Assessment | None):
        for d in reversed(self._state.decisions.get(case_id, [])):
            if d.risk_override:
                return d.risk_override
        return a.risk_level if a else None

    # --- queue / detail -------------------------------------------------
    HIGH_DOLLAR = 20_000

    def queue(self) -> QueueResponse:
        items: list[CaseListItem] = []
        counts = {"High": 0, "Medium": 0, "Low": 0}
        assessed = needs_review = resolved = high_dollar = disagreements = 0

        for case in self._dataset.cases:
            a = self._state.get_assessment(case.case_id)
            status = self._state.status_of(case.case_id)
            eff = self._effective_risk(case.case_id, a)
            is_open = status.value != "RESOLVED"
            if a:
                assessed += 1
                counts[eff or a.risk_level] += 1
                if is_open and a.disagreement:
                    disagreements += 1
            if not is_open:
                resolved += 1
            elif (eff or (a.risk_level if a else "Low")) in ("Medium", "High"):
                needs_review += 1
            if is_open and case.claim_amount_usd >= self.HIGH_DOLLAR:
                high_dollar += 1
            items.append(
                CaseListItem(
                    case_id=case.case_id,
                    claim_number=case.claim_number,
                    claim_date=case.claim_date,
                    care_type=case.care_type,
                    claim_amount_usd=case.claim_amount_usd,
                    state=case.state,
                    status=status,
                    assessment=self._summary(a),
                    effective_risk=eff,
                )
            )

        rank = {"High": 0, "Medium": 1, "Low": 2, None: 3}
        items.sort(key=lambda i: (rank[i.effective_risk], -i.claim_amount_usd))
        return QueueResponse(
            counts=QueueCounts(
                total=len(items),
                assessed=assessed,
                needs_review=needs_review,
                likely_benign=counts["Low"],
                high=counts["High"],
                medium=counts["Medium"],
                low=counts["Low"],
                resolved=resolved,
                high_dollar=high_dollar,
                disagreements=disagreements,
            ),
            cases=items,
        )

    def detail(self, case_id: str, assess_if_missing: bool = True) -> CaseDetail:
        case = self._dataset.get(case_id)
        a = self._state.get_assessment(case_id)
        if a is None and assess_if_missing:
            a = self.assess(case_id)
        return CaseDetail(
            case_id=case_id,
            case=case.model_dump(),
            status=self._state.status_of(case_id),
            assessment=a,
            effective_risk=self._effective_risk(case_id, a),
            decisions=self._state.decisions.get(case_id, []),
            notes=self._state.notes.get(case_id, []),
            chat=self._state.chat.get(case_id, []),
        )

    # --- assessment ---------------------------------------------------
    def assess(self, case_id: str, force: bool = False) -> Assessment:
        case = self._dataset.get(case_id)
        if not force:
            cached = self._state.cached_for_hash(signals_hash(case))
            if cached is not None:
                self._state.put_assessment(cached)
                return cached
        assessment = self._assessment_graph.run(case, self._peers(case))
        self._state.put_assessment(assessment)
        return assessment

    def assess_batch(self, force: bool = False) -> BatchAssessResponse:
        assessed = reused = 0
        for case in self._dataset.cases:
            cached = self._state.cached_for_hash(signals_hash(case))
            if cached is not None and not force:
                self._state.put_assessment(cached)
                reused += 1
            else:
                self.assess(case.case_id, force=force)
                assessed += 1
        return BatchAssessResponse(
            assessed=assessed, reused_from_cache=reused, total=len(self._dataset.cases)
        )

    # --- human actions ----------------------------------------------
    def record_decision(self, case_id: str, req: DecisionRequest) -> Decision:
        self._dataset.get(case_id)
        return self._state.add_decision(
            Decision(
                case_id=case_id,
                action=req.action,
                risk_override=req.risk_override,
                indicator_verdicts=req.indicator_verdicts,
                rationale=req.rationale,
                actor=self._actor,
            )
        )

    def add_note(self, case_id: str, req: NoteRequest) -> Note:
        self._dataset.get(case_id)
        return self._state.add_note(Note(case_id=case_id, body=req.body, actor=self._actor))

    # --- chat -----------------------------------------------------
    def chat_history(self, case_id: str) -> list[ChatMessage]:
        return self._state.chat.get(case_id, [])

    def stream_chat(self, case_id: str, req: ChatRequest) -> Iterator[str]:
        """Persist the question, stream the answer, then persist the assistant turn."""
        case = self._dataset.get(case_id)
        peers = self._peers(case)
        history = [
            {"role": m.role, "content": m.content} for m in self._state.chat.get(case_id, [])
        ]
        assessment = self._state.get_assessment(case_id) or self.assess(case_id)

        self._state.add_chat(
            ChatMessage(case_id=case_id, role="investigator", content=req.question)
        )

        parts: list[str] = []

        def gen() -> Iterator[str]:
            for chunk in self._question_graph.stream(
                case,
                peers,
                req.question,
                assessment_summary=assessment.summary,
                history=history,
            ):
                parts.append(chunk)
                yield chunk
            answer = "".join(parts).strip()
            citations = self._question_graph.citations(case, peers, answer)
            self._state.add_chat(
                ChatMessage(
                    case_id=case_id,
                    role="assistant",
                    content=answer,
                    citations=[c.model_dump() for c in citations],
                )
            )

        return gen()
