from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.container import Container
from app.routers import cases

def create_app(container: Container | None = None) -> FastAPI:
    container = container or Container.from_env()

    app = FastAPI(
        title="Junior AI Investigator - backend",
        version="0.1.0",
        summary="Referral queue, per-case AI assessment, and human-in-the-loop actions.",
    )
    app.state.container = container

    # CORS is only needed if the UI is served from a separate origin (e.g. during frontend
    # dev). When served from this app at / it's same-origin and this is a no-op.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=container.settings.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(cases.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        ai = container.settings.ai
        return {
            "status": "ok",
            "cases_loaded": len(container.dataset.cases),
            "assessments_cached": len(container.state.assessments),
            "llm_configured": bool(ai.gemini_api_key),
            "model": ai.ai_model,
        }

    return app


app = create_app()
