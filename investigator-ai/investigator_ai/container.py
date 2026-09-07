from __future__ import annotations

from investigator_ai.evidence.evidence_packet import EvidencePacketBuilder
from investigator_ai.graphs.assessment_graph import AssessmentGraphRunner
from investigator_ai.graphs.question_graph import QuestionGraphRunner
from investigator_ai.llm.client import AssessmentLlmClient, QuestionLlmClient
from investigator_ai.scoring.config import ScoringConfig
from investigator_ai.scoring.risk_scorer import RiskScorer
from investigator_ai.settings import AiSettings


class AiContainer:
    """Lightweight wiring container for the AI package."""

    def __init__(
        self,
        settings: AiSettings | None = None,
        *,
        scoring: ScoringConfig | None = None,
    ) -> None:
        self.settings = settings or AiSettings()

        self.risk_scorer = RiskScorer(scoring)
        self.evidence_builder = EvidencePacketBuilder(scorer=self.risk_scorer)

        api_key = self.settings.gemini_api_key
        self.assessment_llm_client = AssessmentLlmClient(
            model=self.settings.ai_model,
            api_key=api_key,
            temperature=self.settings.llm_temperature,
        )
        self.question_llm_client = QuestionLlmClient(
            model=self.settings.ai_model,
            api_key=api_key,
            temperature=self.settings.llm_temperature,
        )

        self.assessment_graph = AssessmentGraphRunner(
            evidence_builder=self.evidence_builder,
            llm_client=self.assessment_llm_client,
            max_attempts=self.settings.max_assessment_attempts,
        )
        self.question_graph = QuestionGraphRunner(
            evidence_builder=self.evidence_builder,
            llm_client=self.question_llm_client,
        )
