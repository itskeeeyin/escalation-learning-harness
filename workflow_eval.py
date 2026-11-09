"""Replay the escalation regression cases and optionally export a JSON scorecard."""
import argparse
import json
from copy import deepcopy
from pathlib import Path

from harness import Harness, ReviewError

FIXTURES = Path(__file__).with_name("workflow_cases.json")


def checkpoint(view):
    actions = {action["id"]: action for action in view["actions"]}
    engineering = actions.get("ENG", {})
    review = view["learning_review"] or {}
    refs = set(view["executive"]["sources"])
    for entry in [*view["audit"], *view["actions"]]:
        refs.update(entry["sources"])
    refs.update(action["proof_source"] for action in view["actions"] if action.get("proof_source"))
    refs.update(row["source"] for row in view["history"])
    if review.get("active"):
        refs.add(review["active"])
    return {
        "case_id": view["case_id"],
        "triage_case_id": (view["triage"] or {}).get("case", {}).get("incident_id"),
        "stage": view["stage"],
        "recovered": view["recovered"],
        "executive_sources": view["executive"]["sources"],
        "engineering_state": engineering.get("state"),
        "engineering_proof": engineering.get("proof_source"),
        "executive_state": actions.get("EXEC", {}).get("state"),
        "assigned_actions": list(actions),
        "verified_actions": sum(row["state"] == "Verified" for row in actions.values()),
        "active_report": review.get("active"),
        "report_decisions": review.get("decisions", {}),
        "missing_evidence": sorted(refs - view["evidence"].keys()),
    }


def run_case(case, setup):
    session = Harness()
    steps = [{"command": command} for name in case.get("setup", []) for command in setup[name]]
    results = []
    for step in [*steps, *case["steps"]]:
        command, _, target = step["command"].partition(":")
        before = deepcopy(session.view())
        blocked = step.get("blocked")
        error = None
        try:
            session.apply(command, session.revision, target or None)
        except ReviewError as exc:
            error = str(exc)
        after = session.view()
        actual = checkpoint(after)
        failures = []
        if blocked and (not error or blocked not in error):
            failures.append(f"Expected a block containing {blocked!r}, got {error!r}.")
        if not blocked and error:
            failures.append(f"Unexpected block: {error}")
        if error and before != after:
            failures.append("A rejected command changed the case.")
        expected = {"missing_evidence": [], **step.get("expect", {})}
        failures.extend(
            f"{key}: expected {value!r}, got {actual[key]!r}"
            for key, value in expected.items() if actual[key] != value
        )
        results.append({
            "command": step["command"], "stage_before": before["stage"],
            "expected": expected, "actual": actual, "error": error,
            "events": after["audit"][len(before["audit"]):], "failures": failures,
        })
        if failures:
            break
    return {"id": case["id"], "passed": all(not row["failures"] for row in results), "steps": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write per-step results and events as JSON.")
    args = parser.parse_args()
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    cases = [run_case(case, fixtures["setup"]) for case in fixtures["cases"]]
    for case in cases:
        print(f"{'PASS' if case['passed'] else 'FAIL'} {case['id']}")
        for step in case["steps"]:
            for failure in step["failures"]:
                print(f"  {step['command']}: {failure}")
    passed = sum(case["passed"] for case in cases)
    total = len(cases)
    print(f"{passed}/{total} workflow replay cases passed")
    if args.report:
        report = {"dataset": fixtures["dataset"], "passed": passed, "total": total, "cases": cases}
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
