# Junior AI Investigator

An AI-first case-review tool for insurance fraud investigators. Instead of opening a reactive
tool and reading dozens of signals per case, the investigator opens this and the **queue is
already triaged**: every referral has a short summary, the key indicators that drove the
conclusion, a risk level + confidence, and a recommended next step. The human stays in
control — drill in, ask follow-up questions in natural language, accept/reject findings,
override the risk, add notes, and move the case forward.

Built for the take-home. Synthetic data only (50 long-term-care referrals in
`investigator-be/data/sample_cases_synthetic.csv`).

> **Demo video:** [_(link)_](https://youtu.be/Q-wVx5McgIU) ·
> **Engineering notes:** [`docs/WRITEUP.md`](docs/WRITEUP.md) ·
> **Architecture + diagrams:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## What it does

| | |
|---|---|
| **Triage dashboard** | The morning queue, grouped by risk (High / Medium / Low), with counts ("N need review · M likely benign"), an AI one-liner per case, and a one-click **Assess queue**. |
| **Per-case assessment** | Summary, risk + confidence, recommended action, and key indicators — each expandable to the raw value + peer comparison that produced it. Flags what the AI could **not** verify. |
| **Grounded chat** | Ask follow-up questions about a case. Answers are constrained to that case's data; it says "not in the data" rather than guessing. Streamed. |
| **Human-in-the-loop** | Accept/reject each indicator, override the risk level, add notes, and Accept / Reject / Escalate — all captured with a status workflow. |

## How the AI reasons (the short version)

A **deterministic-first pipeline with one constrained LLM step**, run as a small LangGraph
state machine:

```
evidence packet (deterministic: peer stats, percentiles, rule flags, weighted score)
      │  the LLM never emits a number — it cites evidence by id
      ▼
llm_assess  →  validate (drop bad citations, check vs the rule score, retry once)  →  finalize
      │
      └─ if the model is unavailable / keeps failing → rules-only assessment, clearly labelled
```

Grounding is by construction: the LLM only sees the case row + the pre-computed evidence, it
references evidence by id, and the UI shows every cited indicator next to its raw value. See
[`docs/WRITEUP.md`](docs/WRITEUP.md) for the full reasoning, uncertainty handling, and scaling
story.

## Repo layout

```
investigator-ai/    Python · LangGraph · Gemini — the reasoning layer (RiskScorer,
                    EvidencePacketBuilder, AssessmentGraphRunner, QuestionGraphRunner),
                    wired by AiContainer.
investigator-be/    FastAPI — referral queue, assessment cache, decisions/notes/chat, and
                    it serves the web UI. In-memory state mirrored to data/snapshot.json
                    (no database, by design).
investigator-web/   Plain HTML/CSS/JS — the investigator's screen. No build step; FastAPI
                    serves it at /.
```

---

## Run it locally

**Prerequisites:** Python 3.11+ and a Google AI Studio (Gemini) API key.

```bash
# from the repo root
python -m venv .venv
# Windows:  .venv\Scripts\activate       macOS/Linux:  source .venv/bin/activate
pip install -r investigator-be/requirements.txt      # pulls in investigator-ai as editable
```

Add your key: copy `investigator-ai/.env.example` to `investigator-ai/.env` and set
`GEMINI_API_KEY=...`. That one file is read by the backend and the snapshot script.

```bash
cd investigator-be
uvicorn app.main:app --port 8000
```

**Double click** on investigator-web/index.html to open the UI.

> Without a key the backend still runs — every case falls back to a **rules-only** assessment
> that is clearly labelled in the UI.

### Pre-assessing the queue

The repo ships `investigator-be/data/snapshot.json` — all 50 cases already assessed — so the
first load is instant and costs nothing. Cases you change are re-assessed lazily on open, or
all at once via **Assess queue** in the UI. To regenerate the snapshot from scratch:

```bash
cd investigator-be && python scripts/build_snapshot.py
```

---

## Tests

```bash
pip install pytest
pytest investigator-ai          # scorer determinism, band calibration, graph validation/retry/fallback
pytest investigator-be          # queue, lazy + cached assessment, decisions/notes/chat, persistence
```
