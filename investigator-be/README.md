# investigator-be

FastAPI backend. Owns the referral queue (loads the CSV), the assessment cache, and all
human-in-the-loop state (decisions, notes, chat, status). **In-memory** — mirrored to
`data/snapshot.json` on every write so a demo survives a restart. No database, by design.

```
app/
  main.py            create_app(container) -> FastAPI
  container.py       Container — wires AiContainer + Dataset + state + CaseService
  config.py          BackendSettings (wraps AiSettings)
  domain.py          Decision, Note, ChatMessage, CaseStatus
  stores.py          InMemoryState + JSON snapshot load/save
  schemas.py         HTTP request/response DTOs
  services/
    case_service.py  the one entry point the routers use
  routers/
    cases.py         queue, detail, assess, decision, notes, chat (SSE)
scripts/
  build_snapshot.py  pre-assess the whole queue -> data/snapshot.json
```

## Run

```bash
# from repo root, with the venv active:
#   pip install -r investigator-be/requirements.txt
cp investigator-ai/.env.example investigator-ai/.env    # set GEMINI_API_KEY (one file, whole app)
cd investigator-be
uvicorn app.main:app --port 8000
# open http://localhost:8000  (UI, API, and /docs all here)
```

- `GET /health` · `GET /docs`
- `GET /api/cases` — triage queue with counts
- `GET /api/cases/{id}` — full case; assesses lazily on first open (`?assess=false` to skip)
- `POST /api/assess/{id}` (`?force=true`) · `POST /api/assess/batch`
- `POST /api/cases/{id}/decision` · `/notes` · `/chat` (SSE stream)

Without `GEMINI_API_KEY` the API still works — assessments fall back to rules-only.

## Tests

```bash
pytest        # uses a fake model client; no API key needed
```
