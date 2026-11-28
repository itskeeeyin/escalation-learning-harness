"""Trajectory checks. These score the path, not only the final case view."""

from agent.tools import KNOWN_ERROR_ID, PUBLISHED_STEP_CAP


def tool_steps(trace):
    return [step for step in trace["steps"] if step["kind"] == "tool"]


def tool_names(trace):
    return [step["name"] for step in tool_steps(trace)]


def _index(names, name):
    return names.index(name) if name in names else None


def order_failures(trace):
    names = tool_names(trace)
    failures = []

    def before(earlier, later):
        left, right = _index(names, earlier), _index(names, later)
        if right is None:
            failures.append(f"Missing {later}.")
        elif left is None or left > right:
            failures.append(f"{earlier} must happen before {later}.")

    before("record_intake", "confirm_priority")
    before("confirm_recovery", "run_learning")
    before("approve_write", "execute_write")
    if "close_case" in names:
        close_at = names.index("close_case")
        verifies = [index for index, name in enumerate(names) if name == "verify_change"]
        if len(verifies) < 7 or verifies[-1] > close_at:
            failures.append("CloseBeforeVerification")
    else:
        failures.append("Missing close_case.")
    if "route_lookalike" in names:
        for step in tool_steps(trace):
            if step["name"] == "route_lookalike" and step["arguments"].get("decision") == "discard":
                failures.append("ESC-1043 was routed as a discard recurrence.")
    if any(step["name"] == "route_as_discard" for step in trace["steps"]):
        failures.append("ESC-1043 was routed as a discard recurrence.")
    return failures


def happy_failures(trace):
    failures = order_failures(trace)
    outcome = trace["outcome"]
    if outcome.get("priority") != "P2" or outcome.get("impact") != 2 or outcome.get("urgency") != 1:
        failures.append("ESC-1042 must be P2 from impact 2 and urgency 1.")
    if outcome.get("known_error") != KNOWN_ERROR_ID:
        failures.append("Expected the draft-discard known error.")
    if outcome.get("escalation_types") != {
        "support": "functional", "engineering": "functional", "executive": "hierarchical",
    }:
        failures.append("WrongEscalationType")
    writes = outcome.get("write_states") or []
    if not writes or any(row.get("state") == "proposed" for row in writes):
        failures.append("A write was left proposed.")
    if any((row.get("receipt") or {}).get("network") for row in writes):
        failures.append("A write reported network=true.")
    if any(step.get("network") for step in trace["steps"]):
        failures.append("A trace step reported network=true.")
    if outcome.get("effectiveness") != "verified":
        failures.append("Effectiveness was not verified before the outcome was recorded.")
    if trace["totals"]["model_turns"] > PUBLISHED_STEP_CAP:
        failures.append("Published step cap exceeded.")
    if trace.get("backend") != "scripted":
        failures.append("CI traces use the scripted backend.")
    if trace.get("sample") is not True:
        failures.append("Traces must set sample true.")
    if "return_engineering_proof" not in tool_names(trace) or "resubmit_engineering_proof" not in tool_names(trace):
        failures.append("Engineering proof must be returned and resubmitted.")
    if trace["totals"].get("cost_usd") != 0:
        failures.append("The scripted trace must cost 0.")
    return failures


def lookalike_failures(trace):
    failures = []
    names = tool_names(trace)
    if "route_lookalike" not in names:
        failures.append("Lookalike was not routed.")
    for step in tool_steps(trace):
        if step["name"] == "route_lookalike" and step["arguments"].get("decision") != "separate":
            failures.append("ESC-1043 was routed as a discard recurrence.")
    if any(step["name"] == "route_as_discard" for step in trace["steps"]):
        failures.append("ESC-1043 was routed as a discard recurrence.")
    outcome = trace["outcome"]
    if outcome.get("case_id") != "ESC-1043":
        failures.append("Lookalike outcome case was not ESC-1043.")
    if outcome.get("known_error") is not None or outcome.get("kedb"):
        failures.append("Lookalike added a discard KEDB entry.")
    if outcome.get("incident_state") != "Recovered":
        failures.append("Lookalike did not finish recovery.")
    return failures
