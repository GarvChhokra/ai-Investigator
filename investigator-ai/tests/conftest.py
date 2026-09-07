from __future__ import annotations

import pytest

from investigator_ai.data import CsvCaseRepository, Dataset
from investigator_ai.evidence.evidence_packet import EvidencePacketBuilder
from investigator_ai.scoring.risk_scorer import RiskScorer
from investigator_ai.settings import AiSettings


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    return CsvCaseRepository(AiSettings().cases_csv).load()


@pytest.fixture(scope="session")
def scorer() -> RiskScorer:
    return RiskScorer()


@pytest.fixture(scope="session")
def builder(scorer) -> EvidencePacketBuilder:
    return EvidencePacketBuilder(scorer=scorer)
