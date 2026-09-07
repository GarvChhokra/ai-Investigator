from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from investigator_ai.settings import AiSettings

_BE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SNAPSHOT = str(_BE_ROOT / "data" / "snapshot.json")
# investigator-web is served from a static file server on some localhost port; allow any.
# Also allow "null", which is the Origin browsers send for file:// pages (e.g. double-clicking
# index.html) -- convenient for this prototype, but note it accepts requests from ANY local
# file, not just this one.
_DEFAULT_CORS_REGEX = r"http://(localhost|127\.0\.0\.1)(:\d+)?|null"


@dataclass(frozen=True)
class BackendSettings:
    ai: AiSettings = field(default_factory=AiSettings)
    snapshot_path: str = _DEFAULT_SNAPSHOT
    cors_origin_regex: str = _DEFAULT_CORS_REGEX
    actor: str = "investigator"  # single-user prototype

    @classmethod
    def from_env(cls) -> "BackendSettings":
        return cls(
            ai=AiSettings(),
            snapshot_path=os.getenv("SNAPSHOT_PATH", _DEFAULT_SNAPSHOT),
            cors_origin_regex=os.getenv("CORS_ORIGIN_REGEX", _DEFAULT_CORS_REGEX),
        )
