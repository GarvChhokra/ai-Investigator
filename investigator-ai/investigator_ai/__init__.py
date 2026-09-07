"""Junior AI Investigator - reasoning layer.

Build an :class:`~investigator_ai.container.AiContainer` (the composition root) and pass a
case + its peer group into the graph runners::

    from investigator_ai import AiContainer
    from investigator_ai.data import CsvCaseRepository

    c = AiContainer()
    ds = CsvCaseRepository(c.settings.cases_csv).load()
    case = ds.get("C1006")
    peers = ds.peers(case.care_type)

    assessment = c.assessment_graph.run(case, peers)
    answer = c.question_graph.answer(case, peers, "why is the distance a concern?",
                                     assessment_summary=assessment.summary)
"""

from investigator_ai.container import AiContainer
from investigator_ai.settings import AiSettings
from investigator_ai.schemas import Assessment, ChatAnswer, Evidence, EvidencePacket

__all__ = ["AiContainer", "AiSettings", "Assessment", "ChatAnswer", "Evidence", "EvidencePacket"]
