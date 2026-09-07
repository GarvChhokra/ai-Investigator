"""Backend-owned domain types: investigator actions on a case.

The case rows and AI assessments come from the reasoning layer; everything a human does to a
case lives here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["Low", "Medium", "High"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class CaseStatus(str, Enum):
    NEW = "NEW"                # no AI assessment yet
    AI_TRIAGED = "AI_TRIAGED"  # assessed, not yet touched by a human
    UNDER_REVIEW = "UNDER_REVIEW"  # a human has added notes / verdicts but not resolved
    RESOLVED = "RESOLVED"      # a human accepted / rejected / escalated


DecisionAction = Literal["accept", "reject", "escalate"]
IndicatorVerdict = Literal["accept", "reject"]


class Decision(BaseModel):
    id: str = Field(default_factory=lambda: _id("dec"))
    case_id: str
    action: DecisionAction
    risk_override: RiskLevel | None = None
    indicator_verdicts: dict[str, IndicatorVerdict] = Field(default_factory=dict)
    rationale: str | None = None
    actor: str = "investigator"
    created_at: str = Field(default_factory=_now)


class Note(BaseModel):
    id: str = Field(default_factory=lambda: _id("note"))
    case_id: str
    body: str
    actor: str = "investigator"
    created_at: str = Field(default_factory=_now)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: _id("msg"))
    case_id: str
    role: Literal["investigator", "assistant"]
    content: str
    citations: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
