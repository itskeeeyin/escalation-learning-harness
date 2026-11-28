"""Score scripted agent trajectories and optionally write a JSON report.

The Foundry client is not constructed. Every case uses ``ScriptedModel``.
"""

import argparse
import json
import tempfile
from pathlib import Path

from agent.loop import run_scripted
from agent.score import happy_failures, lookalike_failures
from agent.tools import PUBLISHED_STEP_CAP


def _case(name, passed, failures, trace):
    return {
        "id": name,
        "passed": passed,
        "failures": failures,
        "failure_class": trace["outcome"].get("failure_class"),
        "model_turns": trace["totals"]["model_turns"],
        "cost_usd": trace["totals"]["cost_usd"],
        "backend": trace["backend"],
        "sample": trace["sample"],
    }


def evaluate(tmp):
    tmp = Path(tmp)
    results = []

    happy = run_scripted("happy", checkpoint_path=tmp / "happy.json")
    failures = happy_failures(happy)
    results.append(_case("happy_esc_1042", not failures, failures, happy))

    blocked = run_scripted("write_without_approval", checkpoint_path=tmp / "write.json")
    ok = blocked["outcome"].get("failure_class") == "WriteBeforeApproval"
    results.append(_case(
        "write_without_approval", ok,
        [] if ok else [f"Expected WriteBeforeApproval, got {blocked['outcome'].get('failure_class')}."],
        blocked,
    ))

    early = run_scripted("close_without_effectiveness", checkpoint_path=tmp / "close.json")
    ok = early["outcome"].get("failure_class") == "CloseBeforeVerification"
    results.append(_case(
        "close_without_effectiveness", ok,
        [] if ok else [f"Expected CloseBeforeVerification, got {early['outcome'].get('failure_class')}."],
        early,
    ))

    lookalike = run_scripted("lookalike", checkpoint_path=tmp / "lookalike.json")
    failures = lookalike_failures(lookalike)
    results.append(_case("lookalike_esc_1043", not failures, failures, lookalike))

    resume_path = tmp / "resume.json"
    partial = run_scripted("happy", checkpoint_path=resume_path, stop_after=6)
    continued = run_scripted("happy", checkpoint_path=resume_path, resume=True)
    names = [step["name"] for step in continued["steps"] if step["kind"] == "tool" and step["name"] == "record_intake"]
    failures = happy_failures(continued)
    if len(names) != 1:
        failures.append("Resume repeated or dropped intake.")
    if partial["totals"]["model_turns"] != 6:
        failures.append("Partial run did not stop after six model turns.")
    if continued["totals"]["model_turns"] <= 6:
        failures.append("Resume did not continue past the checkpoint.")
    results.append(_case("resume_mid_run", not failures, failures, continued))

    corrupt_path = tmp / "corrupt.json"
    corrupt_path.write_text("{", encoding="utf-8")
    corrupt = run_scripted("happy", checkpoint_path=corrupt_path, resume=True)
    ok = corrupt["outcome"].get("failure_class") == "ResumeStateCorrupt" and corrupt_path.read_text(encoding="utf-8") == "{"
    results.append(_case(
        "corrupt_checkpoint", ok,
        [] if ok else [f"Expected ResumeStateCorrupt and an untouched file, got {corrupt['outcome'].get('failure_class')}."],
        corrupt,
    ))

    over = run_scripted("happy", checkpoint_path=tmp / "cap.json", step_budget=2)
    ok = over["outcome"].get("failure_class") == "StepBudgetExceeded" and over["totals"]["model_turns"] <= PUBLISHED_STEP_CAP
    results.append(_case(
        "step_cap", ok,
        [] if ok else ["Expected StepBudgetExceeded inside the published cap."],
        over,
    ))

    return {
        "sample": True,
        "fictional": "Fictional trajectory scores. Not a customer record.",
        "backend": "scripted",
        "step_cap": PUBLISHED_STEP_CAP,
        "passed": sum(row["passed"] for row in results),
        "total": len(results),
        "cases": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        report = evaluate(tmp)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['total']} scripted trajectories passed.")
    for case in report["cases"]:
        if not case["passed"]:
            print(f"FAIL {case['id']}")
            for failure in case["failures"]:
                print(f"  {failure}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
