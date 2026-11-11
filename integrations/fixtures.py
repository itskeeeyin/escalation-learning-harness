"""Load sample payloads. Each file is labeled _sample so it cannot be mistaken for a live tenant."""

import json
from pathlib import Path

ROOT = Path(__file__).with_name("fixtures")


def load(name):
    payload = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if payload.get("_sample") is not True:
        raise ValueError(f"{name} is missing the _sample label.")
    return payload
