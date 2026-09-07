"""Case repository + in-memory dataset.

:class:`CaseRepository` is the seam: the prototype ships :class:`CsvCaseRepository`, a real
deployment would swap in one backed by the claims platform without touching anything else.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from investigator_ai.schemas import Case

# Columns that make up a case's "fraud signal fingerprint" - the assessment cache key.
SIGNAL_COLUMNS: tuple[str, ...] = (
    "claim_amount_usd",
    "duplicate_service_billed",
    "weekly_visit_frequency",
    "member_provider_distance_miles",
    "prior_claims_last_12mo",
    "shared_contact_with_provider",
    "weekend_billing_ratio",
    "amount_vs_peer_avg_pct",
    "round_dollar_billing_ratio",
    "recent_policy_change_flag",
    "service_overlap_other_provider",
    "care_type",
)


class Dataset:
    """The whole referral queue held in memory. Cheap for tens of thousands of rows."""

    def __init__(self, cases: list[Case]):
        self._cases = list(cases)
        self._by_id = {c.case_id: c for c in self._cases}

    @property
    def cases(self) -> list[Case]:
        return list(self._cases)

    def get(self, case_id: str) -> Case:
        if case_id not in self._by_id:
            raise KeyError(f"Unknown case_id: {case_id!r}")
        return self._by_id[case_id]

    def peers(self, care_type: str) -> list[Case]:
        return [c for c in self._cases if c.care_type == care_type]


class CaseRepository(Protocol):
    def load(self) -> Dataset: ...


class CsvCaseRepository:
    def __init__(self, csv_path: str | Path):
        self._path = Path(csv_path)

    def load(self) -> Dataset:
        if not self._path.exists():
            raise FileNotFoundError(
                f"Cases CSV not found at {self._path}. Set CASES_CSV or pass an explicit path."
            )
        df = pd.read_csv(self._path)
        return Dataset([Case(**row) for row in df.to_dict(orient="records")])


def signals_hash(case: Case) -> str:
    payload = {col: getattr(case, col) for col in SIGNAL_COLUMNS}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
