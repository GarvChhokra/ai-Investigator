"""In-memory stores + a JSON snapshot so a demo survives a restart.

No database (by design, for the prototype). The stores are the source of truth at runtime;
``snapshot.json`` is a flat mirror written on every mutation and reloaded on boot. A
committed snapshot ships the queue pre-assessed so a fresh clone needs zero API calls.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from investigator_ai.schemas import Assessment

from app.domain import CaseStatus, ChatMessage, Decision, Note


class InMemoryState:
    def __init__(self, snapshot_path: str):
        self._path = Path(snapshot_path)
        self._lock = threading.RLock()
        self.assessments: dict[str, Assessment] = {}
        self.assessment_by_hash: dict[str, Assessment] = {}
        self.decisions: dict[str, list[Decision]] = {}
        self.notes: dict[str, list[Note]] = {}
        self.chat: dict[str, list[ChatMessage]] = {}
        self.status: dict[str, CaseStatus] = {}

    # --- assessments ----------------------------------------------------------
    def get_assessment(self, case_id: str) -> Assessment | None:
        return self.assessments.get(case_id)

    def cached_for_hash(self, signals_hash: str) -> Assessment | None:
        return self.assessment_by_hash.get(signals_hash)

    def put_assessment(self, assessment: Assessment) -> None:
        with self._lock:
            self.assessments[assessment.case_id] = assessment
            if assessment.signals_hash:
                self.assessment_by_hash[assessment.signals_hash] = assessment
            if self.status.get(assessment.case_id, CaseStatus.NEW) == CaseStatus.NEW:
                self.status[assessment.case_id] = CaseStatus.AI_TRIAGED
            self._save()

    # --- decisions / notes --------------------------------------------------
    def add_decision(self, decision: Decision) -> Decision:
        with self._lock:
            self.decisions.setdefault(decision.case_id, []).append(decision)
            self.status[decision.case_id] = CaseStatus.RESOLVED
            self._save()
        return decision

    def add_note(self, note: Note) -> Note:
        with self._lock:
            self.notes.setdefault(note.case_id, []).append(note)
            if self.status.get(note.case_id) in (None, CaseStatus.NEW, CaseStatus.AI_TRIAGED):
                self.status[note.case_id] = CaseStatus.UNDER_REVIEW
            self._save()
        return note

    def add_chat(self, message: ChatMessage) -> ChatMessage:
        with self._lock:
            self.chat.setdefault(message.case_id, []).append(message)
            self._save()
        return message

    def status_of(self, case_id: str) -> CaseStatus:
        return self.status.get(case_id, CaseStatus.NEW)

    # --- persistence ------------------------------------------------------
    def load(self) -> None:
        if not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        with self._lock:
            self.assessments = {
                cid: Assessment.model_validate(a) for cid, a in raw.get("assessments", {}).items()
            }
            self.assessment_by_hash = {
                a.signals_hash: a for a in self.assessments.values() if a.signals_hash
            }
            self.decisions = {
                cid: [Decision.model_validate(d) for d in lst]
                for cid, lst in raw.get("decisions", {}).items()
            }
            self.notes = {
                cid: [Note.model_validate(n) for n in lst]
                for cid, lst in raw.get("notes", {}).items()
            }
            self.chat = {
                cid: [ChatMessage.model_validate(m) for m in lst]
                for cid, lst in raw.get("chat", {}).items()
            }
            self.status = {cid: CaseStatus(s) for cid, s in raw.get("status", {}).items()}

    def _save(self) -> None:
        payload = {
            "assessments": {cid: a.model_dump() for cid, a in self.assessments.items()},
            "decisions": {
                cid: [d.model_dump() for d in lst] for cid, lst in self.decisions.items()
            },
            "notes": {cid: [n.model_dump() for n in lst] for cid, lst in self.notes.items()},
            "chat": {cid: [m.model_dump() for m in lst] for cid, lst in self.chat.items()},
            "status": {cid: s.value for cid, s in self.status.items()},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._path)
