"""Trace records. Sample data only. Secret-looking text is a hard stop."""

import json
import re

from agent.failures import SecretInTrace

FICTIONAL = "Fictional sample. Not a customer or employee record."
SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{8,})|(Bearer\s+[A-Za-z0-9._\-]{8,})|(api[_-]?key)|(CRUSOE_API_KEY)|(\"Authorization\")",
    re.IGNORECASE,
)


def assert_no_secrets(text):
    if SECRET.search(text):
        raise SecretInTrace("Trace or checkpoint text looks like a credential and was not stored.")


def short_text(value, limit=240):
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def new_trace(run_id, case_id, backend):
    return {
        "sample": True,
        "fictional": FICTIONAL,
        "run_id": run_id,
        "case_id": case_id,
        "backend": backend,
        "steps": [],
        "totals": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "model_turns": 0,
            "latency_s": 0.0,
        },
        "outcome": {},
    }


def add_step(trace, **fields):
    step = {
        "index": len(trace["steps"]),
        "kind": fields["kind"],
        "name": fields.get("name"),
        "arguments": fields.get("arguments") or {},
        "result": short_text(fields["result"]) if fields.get("result") is not None else None,
        "failure_class": fields.get("failure_class"),
        "tokens": fields.get("tokens") or 0,
        "cost_usd": fields.get("cost_usd") or 0,
        "latency_s": round(float(fields.get("latency_s") or 0), 6),
        "network": fields.get("network"),
    }
    trace["steps"].append(step)
    return step


def redact_messages(messages):
    rendered = json.dumps(messages)
    assert_no_secrets(rendered)
    return json.loads(rendered)


def dumps_trace(trace):
    text = json.dumps(trace, indent=2, sort_keys=True)
    assert_no_secrets(text)
    return text
