"""Ask the model, run one tool, checkpoint, and repeat.

``apply`` on the harness remains the only workflow state change. Hard gates
stop the run after they are written on the trace. Policy gates stay on the
trace so a later step can choose a different tool.
"""

import json
from pathlib import Path

from integrations.base import WriteProposal

from agent.checkpoint import dumps_checkpoint, export_harness, load_checkpoint
from agent.failures import (
    HARD_STOPS,
    AgentFailure,
    CostBudgetExceeded,
    ModelNoToolCall,
    PolicyGate,
    StepBudgetExceeded,
    UnknownTool,
)
from agent.model import ScriptedModel
from agent.scripts import SCRIPT_CASE, SCRIPTS
from agent.tools import PUBLISHED_STEP_CAP, Registry, ToolExecutor
from agent.trace import add_step, dumps_trace, new_trace, redact_messages

SYSTEM = (
    "You are running a fictional escalation practice case. "
    "Choose the next tool. Sample records are labeled sample true. "
    "Do not invent customers, and do not send writes before they are approved."
)


def problem_state(executor):
    view = executor.harness.view()
    if view["case_id"] == "ESC-1043":
        return "separate_lookalike"
    stage = view["stage"]
    if stage == "Closed":
        return "closed"
    if stage == "Verify":
        return "known_error" if executor.known_error else "fix_in_progress"
    if stage == "Learn":
        return "root_cause_analysis"
    return "investigation"


def build_outcome(executor, *, completed, failure=None):
    view = executor.harness.view()
    actions = view["actions"]
    verified = bool(actions) and all(row.get("state") == "Verified" for row in actions)
    priority = executor.priority or {}
    return {
        "priority": priority.get("priority"),
        "impact": priority.get("impact"),
        "urgency": priority.get("urgency"),
        "escalation_types": dict(executor.handoffs),
        "incident_state": view["stage"],
        "problem_state": problem_state(executor),
        "known_error": executor.known_error,
        "kedb": list(executor.kedb),
        "write_states": executor.export_writes(),
        "effectiveness": "verified" if verified else "unconfirmed",
        "case_id": view["case_id"],
        "completed": completed,
        "failure_class": failure.failure_class if failure else None,
        "failure_message": str(failure) if failure else None,
        "step_cap": PUBLISHED_STEP_CAP,
    }


def _restore_writes(executor, rows):
    executor.writes = []
    for row in rows:
        executor.writes.append({
            "proposal": WriteProposal(
                tool=row["tool"], operation=row["operation"], summary=row["summary"],
                request=row["request"], state=row["state"],
            ),
            "receipt": row.get("receipt"),
        })


class AgentLoop:
    def __init__(self, model, *, case_id, script_name, checkpoint_path=None, step_budget=PUBLISHED_STEP_CAP, cost_budget=1.0):
        self.model = model
        self.case_id = case_id
        self.script_name = script_name
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.step_budget = step_budget
        self.cost_budget = cost_budget
        self.registry = Registry()
        self.executor = ToolExecutor()
        self.run_id = f"{case_id}-{script_name}"
        self.trace = new_trace(self.run_id, case_id, model.name)
        self.messages = [{"role": "system", "content": SYSTEM}]
        self.completed = False

    def resume(self):
        if self.checkpoint_path is None or not self.checkpoint_path.exists():
            return False
        payload = load_checkpoint(self.checkpoint_path)
        if payload["run_id"] != self.run_id or payload["backend"] != self.model.name:
            from agent.failures import ResumeStateCorrupt
            raise ResumeStateCorrupt("Checkpoint does not match this run.")
        if payload["trace"].get("outcome", {}).get("failure_class") or payload["trace"].get("outcome", {}).get("completed"):
            self.trace = payload["trace"]
            self.completed = True
            return True
        self.trace = payload["trace"]
        self.messages = payload["messages"]
        self.executor.harness = payload["harness_obj"]
        _restore_writes(self.executor, payload["writes"])
        extra = payload["executor"]
        self.executor.priority = extra.get("priority")
        self.executor.known_error = extra.get("known_error")
        self.executor.kedb = list(extra.get("kedb") or [])
        self.executor.handoffs = dict(extra.get("handoffs") or {})
        self.model.index = payload["script_index"]
        return True

    def checkpoint(self):
        payload = {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "backend": self.model.name,
            "script": self.script_name,
            "step_index": self.trace["totals"]["model_turns"],
            "script_index": getattr(self.model, "index", 0),
            "messages": redact_messages(self.messages),
            "harness": export_harness(self.executor.harness),
            "writes": self.executor.export_writes(),
            "trace": self.trace,
            "totals": self.trace["totals"],
            "executor": {
                "priority": self.executor.priority,
                "known_error": self.executor.known_error,
                "kedb": self.executor.kedb,
                "handoffs": self.executor.handoffs,
            },
        }
        if self.checkpoint_path is not None:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self.checkpoint_path.write_text(dumps_checkpoint(payload), encoding="utf-8")
        return payload

    def finish(self, *, completed, failure=None):
        self.completed = completed
        self.trace["outcome"] = build_outcome(self.executor, completed=completed, failure=failure)
        self.checkpoint()
        return self.trace

    def run(self, *, stop_after=None):
        schemas = self.registry.schemas()
        while not self.completed:
            turns = self.trace["totals"]["model_turns"]
            if stop_after is not None and turns >= stop_after:
                return self.finish(completed=False)
            if turns >= self.step_budget:
                failure = StepBudgetExceeded(
                    f"Stopped at the published step cap of {self.step_budget} model turns."
                )
                add_step(self.trace, kind="gate", name="step_budget", result=str(failure), failure_class=failure.failure_class)
                return self.finish(completed=False, failure=failure)
            if self.trace["totals"]["cost_usd"] > self.cost_budget:
                failure = CostBudgetExceeded(
                    f"Stopped because cost {self.trace['totals']['cost_usd']} exceeded {self.cost_budget}."
                )
                add_step(self.trace, kind="gate", name="cost_budget", result=str(failure), failure_class=failure.failure_class)
                return self.finish(completed=False, failure=failure)

            def on_retry(message, delay):
                add_step(
                    self.trace, kind="retry", name="model", result=message,
                    failure_class="ModelRetry",
                )

            try:
                if isinstance(self.model, ScriptedModel):
                    turn = self.model.complete(self.messages, schemas)
                else:
                    turn = self.model.complete(self.messages, schemas, on_retry=on_retry)
            except AgentFailure as exc:
                add_step(self.trace, kind="gate", name="model", result=str(exc), failure_class=exc.failure_class)
                return self.finish(completed=False, failure=exc)

            self.trace["totals"]["model_turns"] += 1
            self.trace["totals"]["prompt_tokens"] += turn.prompt_tokens
            self.trace["totals"]["completion_tokens"] += turn.completion_tokens
            self.trace["totals"]["cost_usd"] = round(self.trace["totals"]["cost_usd"] + turn.cost_usd, 6)
            self.trace["totals"]["latency_s"] = round(self.trace["totals"]["latency_s"] + turn.latency_s, 6)
            add_step(
                self.trace, kind="model", name=self.model.name,
                arguments={"tool_calls": [call.as_dict() for call in turn.tool_calls]},
                result=turn.text or ",".join(call.name for call in turn.tool_calls),
                tokens=turn.prompt_tokens + turn.completion_tokens,
                cost_usd=turn.cost_usd, latency_s=turn.latency_s,
            )
            if self.trace["totals"]["cost_usd"] > self.cost_budget:
                failure = CostBudgetExceeded(
                    f"Stopped because cost {self.trace['totals']['cost_usd']} exceeded {self.cost_budget}."
                )
                add_step(self.trace, kind="gate", name="cost_budget", result=str(failure), failure_class=failure.failure_class)
                return self.finish(completed=False, failure=failure)
            if not turn.tool_calls:
                failure = ModelNoToolCall("The model returned text and no tool call.")
                add_step(self.trace, kind="gate", name="model", result=str(failure), failure_class=failure.failure_class)
                self.messages.append({"role": "assistant", "content": turn.text})
                return self.finish(completed=False, failure=failure)

            self.messages.append({
                "role": "assistant",
                "content": turn.text,
                "tool_calls": [call.as_dict() for call in turn.tool_calls],
            })
            for call in turn.tool_calls:
                try:
                    result = self.registry.call(self.executor, call.name, call.arguments)
                except AgentFailure as exc:
                    add_step(
                        self.trace, kind="gate" if isinstance(exc, HARD_STOPS) else "tool",
                        name=call.name, arguments=call.arguments, result=str(exc),
                        failure_class=exc.failure_class,
                    )
                    self.messages.append({"role": "tool", "name": call.name, "content": str(exc)})
                    if isinstance(exc, (PolicyGate, UnknownTool)):
                        continue
                    return self.finish(completed=False, failure=exc)
                network = False if call.name == "execute_write" else None
                add_step(
                    self.trace, kind="tool", name=call.name, arguments=call.arguments,
                    result=result, network=network,
                )
                self.messages.append({"role": "tool", "name": call.name, "content": result})
                if call.name == "complete_run":
                    return self.finish(completed=True)
            self.checkpoint()
        return self.trace


def run_scripted(script_name, *, checkpoint_path=None, resume=False, stop_after=None, step_budget=PUBLISHED_STEP_CAP, cost_budget=1.0, calls=None):
    """Run a named fixture on the scripted model. Never constructs the Foundry client."""
    sequence = list(calls if calls is not None else SCRIPTS[script_name])
    case_id = SCRIPT_CASE.get(script_name, "ESC-1042")
    start = 0
    model = ScriptedModel(sequence, start=start)
    loop = AgentLoop(
        model, case_id=case_id, script_name=script_name,
        checkpoint_path=checkpoint_path, step_budget=step_budget, cost_budget=cost_budget,
    )
    if resume:
        try:
            loop.resume()
        except AgentFailure as exc:
            add_step(loop.trace, kind="gate", name="resume", result=str(exc), failure_class=exc.failure_class)
            loop.trace["outcome"] = build_outcome(loop.executor, completed=False, failure=exc)
            return loop.trace
    return loop.run(stop_after=stop_after)


def write_trace(trace, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_trace(trace) + "\n", encoding="utf-8")
    return path
