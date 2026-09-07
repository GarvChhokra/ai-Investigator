from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["cases_loaded"] == 50


def test_queue_starts_unassessed_then_batch_assesses(client):
    q = client.get("/api/cases").json()
    assert q["counts"]["total"] == 50
    assert q["counts"]["assessed"] == 0
    assert all(c["assessment"] is None for c in q["cases"])
    # standup-line fields are present even before assessment
    for k in ("needs_review", "high_dollar", "disagreements", "likely_benign"):
        assert k in q["counts"]

    b = client.post("/api/assess/batch").json()
    assert b["assessed"] + b["reused_from_cache"] == 50

    q2 = client.get("/api/cases").json()
    assert q2["counts"]["assessed"] == 50
    assert q2["counts"]["high"] >= 8
    assert q2["counts"]["high_dollar"] >= 5  # several LTC claims are > $20k
    # Queue is risk-sorted: first case is High.
    assert q2["cases"][0]["assessment"]["risk_level"] == "High"


def test_case_detail_lazily_assesses_on_open(client):
    d = client.get("/api/cases/C1006").json()
    assert d["assessment"] is not None
    assert d["status"] == "AI_TRIAGED"
    assert d["assessment"]["risk_level"] == "High"
    assert len(d["assessment"]["evidence"]) > 8


def test_unknown_case_404(client):
    assert client.get("/api/cases/NOPE").status_code == 404


def test_notes_and_decision_advance_status_and_persist(client, tmp_path):
    client.post("/api/cases/C1006/notes", json={"body": "Checking provider registry."})
    d = client.get("/api/cases/C1006").json()
    assert d["status"] == "UNDER_REVIEW"
    assert len(d["notes"]) == 1

    dec = client.post(
        "/api/cases/C1006/decision",
        json={"action": "escalate", "risk_override": "High",
              "indicator_verdicts": {"duplicate_service_billed": "accept"}},
    ).json()
    assert dec["action"] == "escalate"

    d2 = client.get("/api/cases/C1006").json()
    assert d2["status"] == "RESOLVED"
    assert d2["effective_risk"] == "High"

    # Persisted to snapshot on disk.
    assert (tmp_path / "snapshot.json").exists()


def test_assessment_is_cached_by_signal_hash(client):
    a1 = client.post("/api/assess/C1006").json()
    a2 = client.post("/api/assess/C1006").json()
    assert a1["generated_at"] == a2["generated_at"]  # reused, not recomputed


def test_chat_streams_and_persists(client):
    with client.stream("POST", "/api/cases/C1006/chat", json={"question": "Why is this high risk?"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    assert "delta" in body

    history = client.get("/api/cases/C1006/chat").json()
    assert [m["role"] for m in history] == ["investigator", "assistant"]
    assert history[1]["content"]
