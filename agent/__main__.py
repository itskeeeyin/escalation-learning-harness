"""Run one practice case and write a trace.

Example:
    python3 -m agent --case ESC-1042 --model scripted --trace traces/esc-1042.json
"""

import argparse
import sys
from pathlib import Path

from agent.failures import AgentFailure, FoundryRequestRejected
from agent.loop import run_scripted, write_trace
from agent.scripts import SCRIPT_CASE, SCRIPTS


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=sorted(set(SCRIPT_CASE.values())))
    parser.add_argument("--model", choices=("scripted", "foundry"), default="scripted")
    parser.add_argument("--script", choices=tuple(SCRIPTS), default=None)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    script = args.script
    if script is None:
        script = "lookalike" if args.case == "ESC-1043" else "happy"
    if SCRIPT_CASE[script] != args.case:
        parser.error(f"{script} belongs to {SCRIPT_CASE[script]}, not {args.case}.")
    if args.model == "foundry":
        import os
        if os.environ.get("CI") == "true":
            raise FoundryRequestRejected("The Foundry backend is a maintainer command. CI uses the scripted model.")
        from agent.model import OpenAICompatModel
        model = OpenAICompatModel()
        from agent.loop import AgentLoop
        loop = AgentLoop(model, case_id=args.case, script_name=script, checkpoint_path=args.checkpoint)
        if args.resume:
            loop.resume()
        try:
            trace = loop.run()
        except AgentFailure as exc:
            print(f"{exc.failure_class}: {exc}", file=sys.stderr)
            return 1
    else:
        checkpoint = args.checkpoint
        if checkpoint is None:
            checkpoint = Path("traces") / f"{args.case}-{script}.checkpoint.json"
        try:
            trace = run_scripted(script, checkpoint_path=checkpoint, resume=args.resume)
        except AgentFailure as exc:
            print(f"{exc.failure_class}: {exc}", file=sys.stderr)
            return 1
    write_trace(trace, args.trace)
    failure = trace["outcome"].get("failure_class")
    if failure:
        print(f"{failure}: {trace['outcome'].get('failure_message')}")
        return 1
    print(f"Wrote {args.trace} ({trace['totals']['model_turns']} model turns, cost ${trace['totals']['cost_usd']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
