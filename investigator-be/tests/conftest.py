from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from investigator_ai import AiContainer
from investigator_ai.graphs.assessment_graph import AssessmentGraphRunner
from investigator_ai.graphs.question_graph import QuestionGraphRunner
from investigator_ai.settings import AiSettings

from fakes import FakeAssessmentLlmClient, FakeQuestionLlmClient, good_response

from app.config import BackendSettings
from app.container import Container
from app.main import create_app


@pytest.fixture
def ai_container() -> AiContainer:
    """Real container, but LLM clients swapped for deterministic fakes (no API key needed)."""
    c = AiContainer(AiSettings())
    c.assessment_graph = AssessmentGraphRunner(
        c.evidence_builder,
        FakeAssessmentLlmClient(lambda: good_response("duplicate_service_billed")),
        max_attempts=2,
    )
    c.question_graph = QuestionGraphRunner(c.evidence_builder, FakeQuestionLlmClient())
    return c


@pytest.fixture
def client(tmp_path: Path, ai_container: AiContainer) -> TestClient:
    settings = BackendSettings(
        ai=ai_container.settings, snapshot_path=str(tmp_path / "snapshot.json")
    )
    return TestClient(create_app(Container(settings, ai=ai_container)))
