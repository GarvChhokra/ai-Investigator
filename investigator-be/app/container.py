"""Backend composition root.

Owns a reasoning-layer :class:`investigator_ai.AiContainer` and adds the backend's own
collaborators: the ingested queue (:class:`Dataset`), the in-memory state, and the case
service the API talks to. Built once in :func:`app.main.create_app`.
"""

from __future__ import annotations

from functools import cached_property

from investigator_ai import AiContainer
from investigator_ai.data import CsvCaseRepository, Dataset

from app.config import BackendSettings
from app.services.case_service import CaseService
from app.stores import InMemoryState


class Container:
    def __init__(
        self,
        settings: BackendSettings,
        *,
        ai: AiContainer | None = None,
        dataset: Dataset | None = None,
    ):
        self._settings = settings
        self._ai = ai or AiContainer(settings.ai)
        self._dataset_override = dataset

    @classmethod
    def from_env(cls) -> "Container":
        return cls(BackendSettings.from_env())

    @property
    def settings(self) -> BackendSettings:
        return self._settings

    @property
    def ai(self) -> AiContainer:
        return self._ai

    @cached_property
    def dataset(self) -> Dataset:
        if self._dataset_override is not None:
            return self._dataset_override
        return CsvCaseRepository(self._settings.ai.cases_csv).load()

    @cached_property
    def state(self) -> InMemoryState:
        state = InMemoryState(self._settings.snapshot_path)
        state.load()
        return state

    @cached_property
    def case_service(self) -> CaseService:
        return CaseService(
            dataset=self.dataset,
            state=self.state,
            assessment_graph=self._ai.assessment_graph,
            question_graph=self._ai.question_graph,
            actor=self._settings.actor,
        )
