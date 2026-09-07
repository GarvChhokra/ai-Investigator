"""Test doubles for the Gemini clients. Kept in the test tree, not the package."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from investigator_ai.schemas import AssessmentLLM, KeyIndicator


def good_response(evidence_id: str, risk: str = "High") -> AssessmentLLM:
    return AssessmentLLM(
        summary="Deterministic test summary - looks suspicious.",
        risk_level=risk,
        confidence="Medium",
        key_indicators=[KeyIndicator(evidence_id=evidence_id, explanation="test rationale")],
        recommended_action="Open an investigation.",
        missing_info=["provider licensing status"],
    )


class FakeAssessmentLlmClient:
    """Drop-in for :class:`investigator_ai.llm.client.AssessmentLlmClient`.

    ``responses`` is a callable returning an ``AssessmentLLM`` (or an ``Exception`` to raise),
    or a list of them to script a multi-attempt sequence.
    """

    model_id = "fake-assess-model"

    def __init__(self, responses: Callable[[], object] | list):
        self._responses = responses
        self.calls = 0

    def assess(self, _system: str, _user: str) -> AssessmentLLM:
        self.calls += 1
        item = self._responses.pop(0) if isinstance(self._responses, list) else self._responses()
        if isinstance(item, Exception):
            raise item
        return item


class FakeQuestionLlmClient:
    model_id = "fake-question-model"

    def __init__(self, text: str = "Fake grounded answer about the distance signal."):
        self._text = text

    def answer(self, _system: str, _user: str) -> str:
        return self._text

    def stream(self, _system: str, _user: str) -> Iterator[str]:
        for piece in self._text.split(" "):
            yield piece + " "
