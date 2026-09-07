"""Pre-assess the whole queue and write investigator-be/data/snapshot.json.

Run once (after setting GEMINI_API_KEY) so a fresh clone opens to a fully triaged queue
without spending any tokens:

    cd investigator-be
    python scripts/build_snapshot.py

Only assessments are written - no decisions/notes/chat, so the committed snapshot is a
clean seed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_BE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BE_ROOT))

from app.container import Container  # noqa: E402


def main() -> int:
    container = Container.from_env()
    if not container.settings.ai.gemini_api_key:
        print("! No GEMINI_API_KEY set - the snapshot would be rules-only. Aborting.")
        return 1

    dataset = container.dataset
    graph = container.ai.assessment_graph

    assessments = {}
    t0 = time.time()
    for i, case in enumerate(dataset.cases, 1):
        a = graph.run(case, dataset.peers(case.care_type))
        assessments[case.case_id] = a.model_dump()
        print(f"  [{i:>2}/{len(dataset.cases)}] {case.case_id}  {a.risk_level:6} "
              f"conf={a.confidence:6} llm={'y' if a.llm_used else 'n'}")

    out = _BE_ROOT / "data" / "snapshot.json"
    payload = {
        "assessments": assessments,
        "decisions": {},
        "notes": {},
        "chat": {},
        "status": {cid: "AI_TRIAGED" for cid in assessments},
    }
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out} ({len(assessments)} assessments) in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
