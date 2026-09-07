"""Put the backend package on sys.path so `pytest investigator-be` works from the repo root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
