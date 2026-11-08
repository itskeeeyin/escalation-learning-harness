"""Score the key-free assessment command center against its golden cases."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_case(workflow, test):
    case = workflow.INCIDENTS[test["incident_id"]]
    evidence = {row["id"] for row in case["evidence"]} | workflow.FACTS.keys()
    payload = test["input"]
    operation = payload["operation"]
    if operation == "triage":
        return workflow.triage(case["incident_id"], payload["available_citation_ids"], as_of=payload.get("as_of"))
    if operation == "validate_draft":
        result = workflow.validate_claim(payload["claim"], payload["citation_ids"], evidence)
        if test["id"] == "unsupported_restore_promise":
            session = start_session(workflow)
            session.apply("inject_restore", session.version)
            try:
                session.apply("approve", session.version)
            except workflow.ReviewError:
                pass
            else:
                raise AssertionError("The workflow approved the unsupported draft.")
            if session.view()["preview"] is not None:
                raise AssertionError("An unsupported draft unlocked the preview.")
        return result
    if operation != "preview":
        raise ValueError(f"Unknown operation: {operation}")
    session = start_session(workflow)
    if payload["review_decision"]:
        session.apply("approve", session.version)
        if not session.view()["preview"]:
            raise AssertionError("The approved version did not unlock the preview.")
        session.apply("revise", session.version)
    if session.version != payload["draft_version"]:
        raise AssertionError(f"Expected draft version {payload['draft_version']}, got {session.version}.")
    view = session.view()
    decision = view["draft"]["decision"]
    return {
        "customer_ready_preview": view["preview"] is not None,
        "draft_state": decision["decision"] if decision else "pending_review",
    }


def start_session(workflow):
    session = workflow.Session()
    session.apply("reveal", 0)
    session.apply("confirm_priority", session.version)
    return session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copilot-path", type=Path, default=HERE.parent / "runbook-copilot")
    args = parser.parse_args()
    checkout = args.copilot_path.expanduser().resolve()
    if not (checkout / "command_center/workflow.py").is_file():
        parser.error("Use --copilot-path with a checkout containing the assessment command center.")
    sys.path.insert(0, str(checkout))
    from command_center import workflow

    tests = json.loads((HERE / "assessment_golden.json").read_text(encoding="utf-8"))
    passed = 0
    for test in tests:
        try:
            actual = run_case(workflow, test)
            differences = [
                f"{key}: expected {expected!r}, got {actual.get(key)!r}"
                for key, expected in test["expected"].items()
                if key not in actual or actual[key] != expected
            ]
        except (AssertionError, ValueError, KeyError) as exc:
            differences = [str(exc)]
        if differences:
            print(f"FAIL {test['id']}\n  " + "\n  ".join(differences))
        else:
            print(f"PASS {test['id']}")
            passed += 1
    print(f"{passed}/{len(tests)} assessment cases passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
