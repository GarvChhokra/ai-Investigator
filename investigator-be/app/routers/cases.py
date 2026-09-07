"""Case queue, detail, assessment, and human-in-the-loop actions."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.domain import ChatMessage, Decision, Note
from app.schemas import (
    BatchAssessResponse,
    CaseDetail,
    ChatRequest,
    DecisionRequest,
    NoteRequest,
    QueueResponse,
)
from app.services.case_service import CaseService
from investigator_ai.schemas import Assessment

router = APIRouter(prefix="/api", tags=["cases"])


def _get_case_service(request: Request) -> CaseService:
    """The Container is stashed on app.state in create_app(); pull the service off it."""
    return request.app.state.container.case_service


CaseServiceDep = Annotated[CaseService, Depends(_get_case_service)]


def _require(service: CaseServiceDep, case_id: str):
    if not service.case_exists(case_id):
        raise HTTPException(status_code=404, detail=f"Unknown case {case_id}")


@router.get("/cases", response_model=QueueResponse)
def list_cases(service: CaseServiceDep) -> QueueResponse:
    return service.queue()


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(
    service: CaseServiceDep,
    case_id: str,
    assess: bool = Query(True, description="Assess on first open if not already assessed"),
) -> CaseDetail:
    _require(service, case_id)
    return service.detail(case_id, assess_if_missing=assess)


@router.post("/assess/batch", response_model=BatchAssessResponse)
def assess_batch(service: CaseServiceDep, force: bool = False) -> BatchAssessResponse:
    return service.assess_batch(force=force)


@router.post("/assess/{case_id}", response_model=Assessment)
def assess_case(service: CaseServiceDep, case_id: str, force: bool = False) -> Assessment:
    _require(service, case_id)
    return service.assess(case_id, force=force)


@router.post("/cases/{case_id}/decision", response_model=Decision)
def record_decision(service: CaseServiceDep, case_id: str, req: DecisionRequest) -> Decision:
    _require(service, case_id)
    return service.record_decision(case_id, req)


@router.post("/cases/{case_id}/notes", response_model=Note)
def add_note(service: CaseServiceDep, case_id: str, req: NoteRequest) -> Note:
    _require(service, case_id)
    return service.add_note(case_id, req)


@router.get("/cases/{case_id}/chat", response_model=list[ChatMessage])
def chat_history(service: CaseServiceDep, case_id: str) -> list[ChatMessage]:
    _require(service, case_id)
    return service.chat_history(case_id)


@router.post("/cases/{case_id}/chat")
def chat(service: CaseServiceDep, case_id: str, req: ChatRequest) -> StreamingResponse:
    _require(service, case_id)

    def sse():
        for chunk in service.stream_chat(case_id, req):
            yield "data: " + json.dumps({"delta": chunk}) + "\n\n"
        yield "data: " + json.dumps({"done": True}) + "\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
