"""ServiceNow incidents, problems, and change requests via the Table API.

Inbound rows use documented fields: sys_id, number, short_description,
description, state, priority, impact, urgency, opened_at. Incident state
values in the sample follow the default choice list: 1 New, 2 In Progress,
3 On Hold, 6 Resolved, 7 Closed. Problem state 107 is Closed on the default
problem model. Change state -3 is Authorize.

The sample links incident.problem_id to the problem and problem.rfc to the
change_request. Outbound notes are a Table API PATCH and stay proposed until
a person approves them. The sample update sets work_notes and does not close
the record or mark a change effective by itself.

Docs:
- https://www.servicenow.com/docs/r/xanadu/api-reference/rest-apis/c_TableAPI.html
"""

from integrations.base import EscalationSignal, IntegrationFailure, WriteProposal
from integrations.fixtures import load
from integrations.transport import guarded_execute, require_env

INCIDENT_STATES = {
    "1": "new",
    "2": "in_progress",
    "3": "on_hold",
    "6": "resolved",
    "7": "closed",
    "8": "canceled",
}
PROBLEM_STATES = {
    "101": "new",
    "102": "assess",
    "103": "root_cause_analysis",
    "104": "fix_in_progress",
    "106": "resolved",
    "107": "closed",
}
CHANGE_STATES = {
    "-5": "new",
    "-4": "assess",
    "-3": "authorize",
    "-2": "scheduled",
    "-1": "implement",
    "0": "review",
    "3": "closed",
    "4": "canceled",
}


def _signal(record, *, kind, states):
    state = str(record["state"])
    if state not in states:
        raise IntegrationFailure(
            "UnrecognizedServiceNowState",
            f"ServiceNow {kind} state {state!r} is not in the sample choice list.",
        )
    return EscalationSignal(
        tool="servicenow",
        external_id=record["sys_id"],
        title=record["short_description"],
        status=states[state],
        summary=record.get("description") or record["short_description"],
        opened_at=record["opened_at"],
        customer=(record.get("caller_id") or {}).get("display_value"),
        links={
            "number": record["number"],
            "table": kind,
            "priority": record.get("priority"),
            "state": state,
        },
        sample=True,
    )


class ServiceNowAdapter:
    name = "servicenow"
    direction = "both"

    def parse_incident(self, payload):
        return _signal(payload["result"], kind="incident", states=INCIDENT_STATES)

    def parse_problem(self, payload):
        return _signal(payload["result"], kind="problem", states=PROBLEM_STATES)

    def parse_change(self, payload):
        signal = _signal(payload["result"], kind="change_request", states=CHANGE_STATES)
        parent = (payload["result"].get("parent") or {}).get("display_value")
        incident = (payload["result"].get("u_incident") or {}).get("display_value")
        signal.links["problem"] = parent
        signal.links["incident"] = incident
        return signal

    def propose_work_note(self, lesson, incident_sys_id):
        note = (
            f"Learning record {lesson.case_id}. {lesson.cause} "
            "Follow-up tickets stay proposed until a person approves them."
        )
        return WriteProposal(
            tool=self.name,
            operation="PATCH incident work_notes",
            summary="Add the lesson as a work note on the incident.",
            request={
                "table": "incident",
                "sys_id": incident_sys_id,
                "body": {"work_notes": note},
            },
        )

    def execute(self, proposal, *, dry_run=True):
        def send():
            env = require_env(["SERVICENOW_INSTANCE", "SERVICENOW_USER", "SERVICENOW_PASSWORD"])
            import base64
            from integrations.transport import http_json

            token = base64.b64encode(
                f"{env['SERVICENOW_USER']}:{env['SERVICENOW_PASSWORD']}".encode()
            ).decode()
            instance = env["SERVICENOW_INSTANCE"].rstrip("/")
            body = proposal.request["body"]
            url = (
                f"{instance}/api/now/table/{proposal.request['table']}/"
                f"{proposal.request['sys_id']}"
            )
            return http_json(
                url,
                method="PATCH",
                headers={"Authorization": f"Basic {token}"},
                body=body,
            )

        return guarded_execute(proposal, dry_run=dry_run, send=send)

    def propose_change_note(self, lesson, change_sys_id):
        note = (
            f"Learning record {lesson.case_id}. Change stays proposed until a person approves it. "
            "Implemented is not the same as verified effective."
        )
        return WriteProposal(
            tool=self.name,
            operation="PATCH change_request work_notes",
            summary="Add the lesson as a work note on the change request. Do not close it.",
            request={
                "table": "change_request",
                "sys_id": change_sys_id,
                "body": {"work_notes": note},
            },
        )

    def load_sample(self):
        incident_payload = load("servicenow_incident.json")
        problem_payload = load("servicenow_problem.json")
        change_payload = load("servicenow_change_request.json")
        incident = self.parse_incident(incident_payload)
        problem = self.parse_problem(problem_payload)
        change = self.parse_change(change_payload)
        problem_number = (incident_payload["result"].get("problem_id") or {}).get("display_value")
        change_number = (problem_payload["result"].get("rfc") or {}).get("display_value")
        if problem_number != problem.links["number"] or change.links.get("problem") != problem.links["number"]:
            raise IntegrationFailure(
                "ServiceNowLinkageBroken",
                "The sample incident, problem, and change request do not point at one another.",
            )
        if change_number != change.links["number"] or change.links.get("incident") != incident.links["number"]:
            raise IntegrationFailure(
                "ServiceNowLinkageBroken",
                "The sample change request is not tied to this incident and problem.",
            )
        return {
            "incident": incident.as_dict(),
            "problem": problem.as_dict(),
            "change_request": change.as_dict(),
            "linkage": {
                "sample": True,
                "label": "Example linkage. Incident to problem to change request.",
                "incident": incident.links["number"],
                "problem": problem.links["number"],
                "change_request": change.links["number"],
            },
        }
