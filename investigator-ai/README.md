# investigator-ai

The reasoning layer. Pure Python — deterministic scoring + one grounded LLM step, wired by a
composition-root container. No web server; the backend imports it.

```
investigator_ai/
  settings.py            AiSettings (env / .env)
  container.py           AiContainer — constructs & wires everything
  scoring/
    risk_scorer.py       RiskScorer — deterministic 0-100 score + per-signal contributions
    config.py            weights & band thresholds (pure data)
  evidence/
    evidence_packet.py   EvidencePacketBuilder — RiskScore → Evidence[] with peer context
  llm/
    client.py            AssessmentLlmClient (structured) · QuestionLlmClient (stream)
  graphs/
    assessment_graph.py  AssessmentGraphRunner — LangGraph: build_packet→llm_assess→validate→finalize
    question_graph.py     QuestionGraphRunner — grounded single-case Q&A
  schemas.py             Case, Evidence, EvidencePacket, Assessment, ...
  data.py                Dataset + CsvCaseRepository
```

## Use

```python
from investigator_ai import AiContainer
from investigator_ai.data import CsvCaseRepository

c = AiContainer()                       # reads GEMINI_API_KEY / AI_MODEL from env or .env
ds = CsvCaseRepository(c.settings.cases_csv).load()
case = ds.get("C1006")
peers = ds.peers(case.care_type)

a = c.assessment_graph.run(case, peers)
print(a.risk_level, a.confidence, a.summary)

ans = c.question_graph.answer(case, peers, "why is the distance a concern?",
                              assessment_summary=a.summary)
```

## Tests

```bash
pytest            # runs without an API key — a fake Gemini client stands in
```

## Config

```bash
# from the repo root
cp investigator-ai/.env.example investigator-ai/.env    # then set GEMINI_API_KEY
```

Model id is `AI_MODEL` (default `gemini-3.1-flash-lite`); confirm current Gemini ids at
ai.google.dev.

Without a key, `assessment_graph.run(...)` returns a clearly-labelled rules-only assessment
rather than raising.
