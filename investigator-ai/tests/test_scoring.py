"""The deterministic scorer + evidence packet - the grounding foundation."""

from __future__ import annotations

import pytest

# Unambiguous cases in the synthetic data.
OBVIOUS_FRAUD = ["C1006", "C1021", "C1024", "C1030", "C1034", "C1036", "C1037", "C1031"]
CLEAN = ["C1004", "C1013", "C1028", "C1005", "C1017"]


def _score(scorer, dataset, case_id):
    case = dataset.get(case_id)
    return scorer.score(case, dataset.peers(case.care_type))


@pytest.mark.parametrize("case_id", OBVIOUS_FRAUD)
def test_obvious_fraud_scores_high(scorer, dataset, case_id):
    s = _score(scorer, dataset, case_id)
    assert s.band == "High", (case_id, s.score)
    assert s.score >= 60


@pytest.mark.parametrize("case_id", CLEAN)
def test_clean_claims_score_low(scorer, dataset, case_id):
    assert _score(scorer, dataset, case_id).band == "Low"


def test_scorer_is_deterministic(scorer, dataset):
    a = _score(scorer, dataset, "C1019")
    b = _score(scorer, dataset, "C1019")
    assert a == b


def test_contributions_are_bounded_by_weight(scorer, dataset):
    s = _score(scorer, dataset, "C1006")
    for c in s.contributions.values():
        assert 0.0 <= c.contribution <= c.weight + 1e-6


def test_ordered_signal_ids_sorted_by_contribution(scorer, dataset):
    s = _score(scorer, dataset, "C1024")
    contribs = [s.contributions[sid].contribution for sid in s.ordered_signal_ids]
    assert contribs == sorted(contribs, reverse=True)


def test_packet_evidence_ids_cover_all_signals(builder, dataset):
    case = dataset.get("C1006")
    packet = builder.build(case, dataset.peers(case.care_type))
    ids = packet.evidence_ids()
    assert {"amount_vs_peer_avg_pct", "duplicate_service_billed", "care_type"} <= ids
