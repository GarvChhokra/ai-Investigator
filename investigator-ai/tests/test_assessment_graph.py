"""Assessment graph: validation, one-retry, and graceful fallback - all without a real LLM."""

from __future__ import annotations

import pytest

from investigator_ai.evidence.evidence_packet import EvidencePacketBuilder
from investigator_ai.graphs.assessment_graph import AssessmentGraphRunner
from investigator_ai.scoring.risk_scorer import RiskScorer
from investigator_ai.schemas import AssessmentLLM, KeyIndicator

from fakes import FakeAssessmentLlmClient, good_response


@pytest.fixture
def make_runner(builder: EvidencePacketBuilder):
    def _make(responses) -> AssessmentGraphRunner:
        return AssessmentGraphRunner(builder, FakeAssessmentLlmClient(responses), max_attempts=2)

    return _make


def _run(runner, dataset, case_id):
    case = dataset.get(case_id)
    return runner.run(case, dataset.peers(case.care_type))


def test_happy_path_uses_llm_output(make_runner, dataset):
    runner = make_runner([good_response("duplicate_service_billed")])
    a = _run(runner, dataset, "C1024")
    assert a.llm_used is True
    assert a.risk_level == "High"
    assert a.key_indicators[0].evidence_id == "duplicate_service_billed"
    assert a.missing_info == ["provider licensing status"]
    assert a.model == "fake-assess-model"


def test_unknown_evidence_id_dropped_then_retried_then_recovered(make_runner, dataset):
    bad = AssessmentLLM(
        summary="x", risk_level="High", confidence="Low",
        key_indicators=[KeyIndicator(evidence_id="totally_made_up", explanation="hallucinated")],
        recommended_action="do something",
    )
    runner = make_runner([bad, good_response("amount_vs_peer_avg_pct")])
    a = _run(runner, dataset, "C1024")
    assert a.llm_used is True
    assert a.key_indicators[0].evidence_id == "amount_vs_peer_avg_pct"
    assert any("unknown evidence id" in n for n in a.validation_notes)


def test_persistent_bad_output_falls_back_to_rules_only(make_runner, dataset):
    bad = AssessmentLLM(
        summary="x", risk_level="Low", confidence="Low",  # 2 bands from C1024's High
        key_indicators=[KeyIndicator(evidence_id="nope", explanation="bad")],
        recommended_action="whatever",
    )
    runner = make_runner([bad, bad])
    a = _run(runner, dataset, "C1024")
    assert a.llm_used is False
    assert a.risk_level == a.heuristic_band == "High"
    assert a.confidence == "Low"
    assert a.key_indicators


def test_llm_exception_falls_back_cleanly(make_runner, dataset):
    runner = make_runner([RuntimeError("gemini 500"), RuntimeError("gemini 500")])
    a = _run(runner, dataset, "C1013")
    assert a.llm_used is False
    assert a.risk_level == "Low"


def test_band_disagreement_flagged_not_hidden(make_runner, dataset):
    runner = make_runner([good_response("duplicate_service_billed", risk="Medium")])
    a = _run(runner, dataset, "C1024")
    assert a.risk_level == "Medium"
    assert a.disagreement is True
