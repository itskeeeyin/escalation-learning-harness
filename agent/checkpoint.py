"""JSON checkpoints. Resume loads the last completed step or stops."""

import json
from copy import deepcopy

from harness import Harness

from agent.failures import ResumeStateCorrupt, SecretInTrace
from agent.trace import assert_no_secrets

HARNESS_FIELDS = (
    "stage", "revision", "actions", "history", "audit", "proof_available",
    "resolution_available", "picker_stage", "active_signal", "signal_decisions",
    "problem_phase", "known_error",
)
TRIAGE_FIELDS = ("confirmed", "priority_confirmed", "version", "claims", "audit")
CHECKPOINT_FIELDS = (
    "run_id", "case_id", "backend", "script", "step_index", "script_index",
    "messages", "harness", "writes", "trace", "totals", "executor",
)


def export_harness(harness):
    return {
        "triage": {name: deepcopy(getattr(harness.triage, name)) for name in TRIAGE_FIELDS},
        **{name: deepcopy(getattr(harness, name)) for name in HARNESS_FIELDS},
    }


def import_harness(payload):
    if not isinstance(payload, dict) or "triage" not in payload:
        raise ResumeStateCorrupt("Checkpoint harness state is missing.")
    harness = Harness()
    triage = payload["triage"]
    if not isinstance(triage, dict) or any(name not in triage for name in TRIAGE_FIELDS):
        raise ResumeStateCorrupt("Checkpoint triage state is missing.")
    for name in TRIAGE_FIELDS:
        setattr(harness.triage, name, deepcopy(triage[name]))
    for name in HARNESS_FIELDS:
        if name not in payload:
            raise ResumeStateCorrupt(f"Checkpoint is missing harness.{name}.")
        setattr(harness, name, deepcopy(payload[name]))
    return harness


def dumps_checkpoint(payload):
    try:
        text = json.dumps(payload, indent=2, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ResumeStateCorrupt("Checkpoint state could not be serialized.") from exc
    assert_no_secrets(text)
    return text


def load_checkpoint(path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResumeStateCorrupt(f"Checkpoint {path.name} could not be read.") from exc
    try:
        assert_no_secrets(text)
    except SecretInTrace as exc:
        raise ResumeStateCorrupt("Checkpoint failed the secret check and was not loaded.") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResumeStateCorrupt(
            f"Checkpoint {path.name} is truncated or invalid JSON. The run stopped."
        ) from exc
    if not isinstance(payload, dict) or any(name not in payload for name in CHECKPOINT_FIELDS):
        raise ResumeStateCorrupt(
            "Checkpoint is missing fields from the last completed step. The run stopped."
        )
    payload["harness_obj"] = import_harness(payload["harness"])
    return payload
