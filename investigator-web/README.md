# investigator-web

The investigator's screen. Plain HTML/CSS/JS — no build step, no dependencies.

```bash
cd investigator-be && uvicorn app.main:app --port 8000
```

```
index.html    two-pane shell (queue left, case detail right)
styles.css    the whole look — Source Serif / Inter / IBM Plex Mono, muted "paper" palette
app.js        state + rendering + the FastAPI calls (incl. the SSE chat reader)
```

Double click on index.html to run.
