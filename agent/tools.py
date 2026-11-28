"""Tool registry. Handlers call the existing adapters and ``Harness.apply``.

Gates stay in the harness and the write adapters. This module does not
reimplement them and does not set ``INTEGRATIONS_MODE``.
"""

import json

from command_center.workflow import ReviewError
from harness import DATA, Harness, recurrence
from itil import handoff, priority_from_matrix, ItilFailure
from integrations.base import ApprovalRequired, approve
from integrations.jira import JiraAdapter
from integrations.pagerduty import PagerDutyAdapter
from integrations.pylon import PylonAdapter
from integrations.replay import lesson_from_actions
from integrations.salesforce import SalesforceAdapter
from integrations.servicenow import ServiceNowAdapter
from integrations.slack import SlackAdapter

from agent.failures import (
    CloseBeforeVerification,
    EffectivenessUnconfirmed,
    PolicyGate,
    SkipIntake,
    UnknownTool,
    WriteBeforeApproval,
    WrongCaseType,
    WrongEscalationType,
)

# Same fictional matrix as itil.priority_from_matrix. Impact 2 and urgency 1 score P2.
KNOWN_ERROR_ID = "KE-1042"
KEDB_ID = "KEDB-1042"
FUNCTIONAL = {"support": "functional", "engineering": "functional"}
HIERARCHICAL = {"executive": "hierarchical"}
PUBLISHED_STEP_CAP = 40


def _schema(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _string(description, enum=None):
    spec = {"type": "string", "description": description}
    if enum:
        spec["enum"] = list(enum)
    return spec


class ToolExecutor:
    def __init__(self, harness=None):
        self.harness = harness or Harness()
        self.writes = []
        self.priority = None
        self.known_error = None
        self.kedb = []
        self.handoffs = {}
        self.adapters = {
            "jira": JiraAdapter(),
            "slack": SlackAdapter(),
            "servicenow": ServiceNowAdapter(),
        }

    def export_writes(self):
        return [item["proposal"].as_dict() | {"receipt": item.get("receipt")} for item in self.writes]

    def apply_command(self, command, action_id=None):
        try:
            self.harness.apply(command, self.harness.revision, action_id)
        except ReviewError as exc:
            message = str(exc)
            if command == "verify" and "incomplete" in message:
                raise EffectivenessUnconfirmed(message) from exc
            raise PolicyGate(message) from exc
        view = self.harness.view()
        return f"{command} applied. Stage is {view['stage']}. Revision is {view['revision']}."

    def read_sample_records(self, arguments):
        tool = arguments["tool"]
        if tool == "pagerduty":
            payload = PagerDutyAdapter().load_sample()
        elif tool == "slack":
            payload = SlackAdapter().load_sample()
        elif tool == "servicenow":
            payload = ServiceNowAdapter().load_sample()
        elif tool == "salesforce":
            payload = SalesforceAdapter().load_sample()
        elif tool == "pylon":
            payload = PylonAdapter().load_sample()
        else:
            raise UnknownTool(f"There is no sample reader for {tool}.")
        return json.dumps({"sample": True, "tool": tool, "record": payload}, default=str)

    def read_case_evidence(self, arguments):
        view = self.harness.view()
        return json.dumps({
            "sample": True,
            "case_id": view["case_id"],
            "stage": view["stage"],
            "evidence_ids": sorted(view["evidence"]),
        })

    def classify_priority(self, arguments):
        impact = arguments["impact"]
        urgency = arguments["urgency"]
        try:
            priority = priority_from_matrix(impact, urgency)
        except ItilFailure as exc:
            raise PolicyGate(str(exc)) from exc
        self.priority = {"impact": impact, "urgency": urgency, "priority": priority}
        return f"Example matrix maps impact {impact} and urgency {urgency} to {priority}."

    def match_recurrence(self, arguments):
        rows = recurrence()
        matched = [row["id"] for row in rows if row["match"]]
        excluded = [row["id"] for row in rows if not row["match"]]
        return json.dumps({"sample": True, "matched": matched, "excluded": excluded})

    def match_known_error(self, arguments):
        if self.harness.picker_stage:
            self.known_error = None
            return "ESC-1043 does not match the draft-discard known error. No KEDB entry was added."
        rows = [row for row in recurrence() if row["match"]]
        if len(rows) < 2:
            self.known_error = None
            return "No known error. Fewer than two confirmed draft-discard matches."
        self.known_error = KNOWN_ERROR_ID
        if KEDB_ID not in self.kedb:
            self.kedb.append(KEDB_ID)
        return f"Matched known error {KNOWN_ERROR_ID} and {KEDB_ID} for draft discard on template authoring."

    def read_practice_record(self, arguments):
        record_id = arguments["record_id"]
        if record_id not in DATA["evidence"]:
            raise PolicyGate(f"Practice record {record_id} is not in the fictional evidence set.")
        return json.dumps({"sample": True, "id": record_id, "record": DATA["evidence"][record_id]})

    def record_intake(self, arguments):
        return self.apply_command("reveal")

    def confirm_priority(self, arguments):
        if not self.harness.triage.confirmed:
            raise SkipIntake("Confirm priority only after intake has recorded the case.")
        if self.priority and self.priority["priority"] != "P2":
            raise WrongCaseType(
                f"ESC-1042 is P2 on the practice matrix. Got {self.priority['priority']}."
            )
        if self.priority is None:
            raise PolicyGate("Classify priority on the practice matrix before confirming it.")
        return self.apply_command("confirm_priority")

    def approve_draft(self, arguments):
        return self.apply_command("approve")

    def revise_draft(self, arguments):
        return self.apply_command("revise")

    def load_recovery_evidence(self, arguments):
        return self.apply_command("load_resolution")

    def confirm_recovery(self, arguments):
        return self.apply_command("confirm_recovery")

    def run_learning(self, arguments):
        return self.apply_command("learn")

    def approve_plan(self, arguments):
        return self.apply_command("approve_plan")

    def load_completion_evidence(self, arguments):
        return self.apply_command("load_proof")

    def return_engineering_proof(self, arguments):
        return self.apply_command("return_proof")

    def resubmit_engineering_proof(self, arguments):
        return self.apply_command("resubmit_proof")

    def verify_change(self, arguments):
        action_id = arguments["action_id"]
        action = self.harness.actions.get(action_id)
        if self.harness.stage != "Verify" or not self.harness.proof_available or not action:
            raise EffectivenessUnconfirmed(
                "Effectiveness is unconfirmed. Verification needs an assigned change and loaded evidence."
            )
        if action_id == "ENG" and not action.get("proof_ready"):
            raise EffectivenessUnconfirmed(
                "Engineering effectiveness is unconfirmed until the returned proof is resubmitted."
            )
        if action.get("state") == "Verified":
            raise PolicyGate(f"{action_id} is already verified.")
        return self.apply_command("verify", action_id)

    def close_case(self, arguments):
        actions = list(self.harness.actions.values())
        if not actions or any(row.get("state") != "Verified" for row in actions):
            raise CloseBeforeVerification(
                "Close is blocked until every assigned change is verified effective."
            )
        return self.apply_command("close")

    def start_lookalike(self, arguments):
        if self.harness.stage != "Engage" or self.harness.triage.confirmed:
            raise WrongCaseType("Open the lookalike from a fresh case, separate from ESC-1042.")
        return self.apply_command("start_picker")

    def inspect_lookalike(self, arguments):
        return self.apply_command("inspect_picker")

    def route_lookalike(self, arguments):
        decision = arguments["decision"]
        if decision == "discard":
            raise WrongCaseType(
                "ESC-1043 stays a separate launch-picker case. It is not routed as a draft-discard recurrence."
            )
        if decision != "separate":
            raise PolicyGate("Route the lookalike as separate or discard.")
        result = self.apply_command("route_picker")
        self.known_error = None
        return result + " No draft-discard KEDB entry was added."

    def recover_lookalike(self, arguments):
        return self.apply_command("recover_picker")

    def record_handoff(self, arguments):
        team = arguments["team"]
        kind = arguments["escalation_type"]
        expected = {**FUNCTIONAL, **HIERARCHICAL}.get(team)
        if expected is None:
            raise WrongEscalationType(f"{team} is not a handoff team on this practice case.")
        if kind != expected:
            raise WrongEscalationType(
                f"{team} handoffs on this case are {expected}. Received {kind}."
            )
        try:
            record = handoff(f"HO-{team}", kind, team, f"Fictional {kind} handoff for {team}.")
        except ItilFailure as exc:
            raise WrongEscalationType(str(exc)) from exc
        self.handoffs[team] = record["escalation"]
        return f"Recorded a {record['escalation']} handoff for {team}."

    def _lesson(self):
        return lesson_from_actions(DATA["actions"])

    def propose_jira(self, arguments):
        proposal = self.adapters["jira"].propose_action_item(self._lesson(), self._lesson().actions[0])
        self.writes.append({"proposal": proposal, "receipt": None})
        return f"Proposed Jira write {len(self.writes) - 1}. State is proposed."

    def propose_slack(self, arguments):
        sample = SlackAdapter().load_sample()
        proposal = self.adapters["slack"].propose_status(
            self._lesson(), channel=sample["links"]["channel"], thread_ts=sample["links"]["thread_ts"],
        )
        self.writes.append({"proposal": proposal, "receipt": None})
        return f"Proposed Slack write {len(self.writes) - 1}. State is proposed."

    def propose_servicenow(self, arguments):
        sample = ServiceNowAdapter().load_sample()
        proposal = self.adapters["servicenow"].propose_work_note(
            self._lesson(), sample["incident"]["external_id"],
        )
        self.writes.append({"proposal": proposal, "receipt": None})
        return f"Proposed ServiceNow write {len(self.writes) - 1}. State is proposed."

    def _proposal(self, arguments):
        index = arguments["proposal_index"]
        if not isinstance(index, int) or not 0 <= index < len(self.writes):
            raise PolicyGate("proposal_index does not match a write from this run.")
        return index, self.writes[index]

    def approve_write(self, arguments):
        index, item = self._proposal(arguments)
        try:
            item["proposal"] = approve(item["proposal"])
        except ApprovalRequired as exc:
            raise PolicyGate(str(exc)) from exc
        return f"Approved write {index}. State is approved. It has not been sent."

    def execute_write(self, arguments):
        index, item = self._proposal(arguments)
        proposal = item["proposal"]
        if proposal.state != "approved":
            raise WriteBeforeApproval(
                f"{proposal.tool} {proposal.operation} is still {proposal.state}. Approve it before execution."
            )
        dry_run = arguments.get("dry_run", True)
        if dry_run is not True:
            dry_run = True
            note = " Live mode is not enabled by the agent. The call stays a dry run."
        else:
            note = ""
        adapter = self.adapters[proposal.tool]
        receipt = adapter.execute(proposal, dry_run=True if dry_run else False)
        item["receipt"] = receipt
        if receipt.get("network"):
            raise PolicyGate("A write receipt reported network=true. The agent only dry-runs.")
        return f"Write {index} finished as {receipt['status']}. network=false.{note}"

    def complete_run(self, arguments):
        return arguments.get("summary") or "Run complete."


def _spec(name, description, parameters, handler):
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
    }


def tool_specs():
    empty = _schema({}, [])
    return [
        _spec("read_sample_records", "Read one labeled sample tool record.", _schema(
            {"tool": _string("Sample source.", ["pagerduty", "slack", "servicenow", "salesforce", "pylon"])},
            ["tool"],
        ), ToolExecutor.read_sample_records),
        _spec("read_case_evidence", "Read evidence ids currently visible on the case.", empty, ToolExecutor.read_case_evidence),
        _spec("classify_priority", "Map practice impact and urgency to a priority. ESC-1042 is impact 2 and urgency 1.", _schema(
            {"impact": {"type": "integer", "description": "Practice impact, 1 to 3."},
             "urgency": {"type": "integer", "description": "Practice urgency, 1 to 3."}},
            ["impact", "urgency"],
        ), ToolExecutor.classify_priority),
        _spec("match_recurrence", "Match confirmed draft-discard history and exclude non-matches.", empty, ToolExecutor.match_recurrence),
        _spec("match_known_error", "Match the draft-discard known error. The lookalike does not get a KEDB entry.", empty, ToolExecutor.match_known_error),
        _spec("read_practice_record", "Read one fictional evidence row by id.", _schema(
            {"record_id": _string("Evidence id such as E2 or P2.")}, ["record_id"],
        ), ToolExecutor.read_practice_record),
        _spec("record_intake", "Record intake for ESC-1042. Required before confirm_priority.", empty, ToolExecutor.record_intake),
        _spec("confirm_priority", "Confirm the classified priority through the harness.", empty, ToolExecutor.confirm_priority),
        _spec("approve_draft", "Approve the current customer draft version.", empty, ToolExecutor.approve_draft),
        _spec("revise_draft", "Revise the draft. The previous approval expires.", empty, ToolExecutor.revise_draft),
        _spec("load_recovery_evidence", "Load fictional recovery evidence.", empty, ToolExecutor.load_recovery_evidence),
        _spec("confirm_recovery", "Confirm customer recovery. Learning stays open.", empty, ToolExecutor.confirm_recovery),
        _spec("run_learning", "Run recurrence and routing after recovery.", empty, ToolExecutor.run_learning),
        _spec("approve_plan", "Approve the follow-up plan and assign the changes.", empty, ToolExecutor.approve_plan),
        _spec("load_completion_evidence", "Load fictional completion evidence.", empty, ToolExecutor.load_completion_evidence),
        _spec("return_engineering_proof", "Return incomplete Engineering proof.", empty, ToolExecutor.return_engineering_proof),
        _spec("resubmit_engineering_proof", "Resubmit Engineering proof after it was returned.", empty, ToolExecutor.resubmit_engineering_proof),
        _spec("verify_change", "Verify one assigned change.", _schema(
            {"action_id": _string("Action id.", ["ENG", "PROD", "SUP", "CS", "DOC", "OPS", "EXEC"])},
            ["action_id"],
        ), ToolExecutor.verify_change),
        _spec("close_case", "Close the learning record after every change is verified.", empty, ToolExecutor.close_case),
        _spec("start_lookalike", "Open ESC-1043, the launch-picker lookalike.", empty, ToolExecutor.start_lookalike),
        _spec("inspect_lookalike", "Inspect the lookalike publish and filter evidence.", empty, ToolExecutor.inspect_lookalike),
        _spec("route_lookalike", "Route ESC-1043. discard is rejected.", _schema(
            {"decision": _string("separate keeps the case off the discard KEDB.", ["separate", "discard"])},
            ["decision"],
        ), ToolExecutor.route_lookalike),
        _spec("recover_lookalike", "Confirm lookalike launch readiness.", empty, ToolExecutor.recover_lookalike),
        _spec("record_handoff", "Record a functional or hierarchical handoff.", _schema(
            {"team": _string("Team.", ["support", "engineering", "executive"]),
             "escalation_type": _string("functional or hierarchical.", ["functional", "hierarchical"])},
            ["team", "escalation_type"],
        ), ToolExecutor.record_handoff),
        _spec("propose_jira", "Propose a Jira task. It stays proposed until approve_write.", empty, ToolExecutor.propose_jira),
        _spec("propose_slack", "Propose a Slack status post.", empty, ToolExecutor.propose_slack),
        _spec("propose_servicenow", "Propose a ServiceNow work note.", empty, ToolExecutor.propose_servicenow),
        _spec("approve_write", "Approve one proposed write. This does not send it.", _schema(
            {"proposal_index": {"type": "integer", "description": "Index from the propose tool."}},
            ["proposal_index"],
        ), ToolExecutor.approve_write),
        _spec("execute_write", "Dry-run an approved write. The default is dry_run true.", _schema(
            {"proposal_index": {"type": "integer", "description": "Index from the propose tool."},
             "dry_run": {"type": "boolean", "description": "Defaults to true. A remote send is not enabled."}},
            ["proposal_index"],
        ), ToolExecutor.execute_write),
        _spec("complete_run", "Stop the loop after the case tools have finished.", _schema(
            {"summary": _string("Short fictional summary.")}, [],
        ), ToolExecutor.complete_run),
    ]


def openai_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for spec in tool_specs()
    ]


class Registry:
    def __init__(self):
        self._tools = {spec["name"]: spec for spec in tool_specs()}

    def schemas(self):
        return openai_tools()

    def call(self, executor, name, arguments):
        spec = self._tools.get(name)
        if spec is None:
            raise UnknownTool(f"Unknown tool {name}.")
        return spec["handler"](executor, arguments or {})
