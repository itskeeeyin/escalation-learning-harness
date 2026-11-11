"""ServiceNow incidents and problem records via the Table API.

Inbound rows use the documented incident and problem fields: sys_id, number,
short_description, description, state, priority, impact, urgency, opened_at.
Incident state values in the sample follow the default choice list: 1 New,
2 In Progress, 3 On Hold, 6 Resolved, 7 Closed. Problem state 107 is Closed
on the default problem model.

Outbound work notes are a Table API PATCH and stay proposed until approved.
The sample update sets work_notes and does not close the record by itself.

Docs:
- https://www.servicenow.com/docs/r/xanadu/api-reference/rest-apis/c_TableAPI.html
"""

from integrations.base import EscalationSignal, WriteProposal
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


def _signal(record, *, kind, states):
    state = str(record["state"])
    if state not in states:
        raise ValueError(f"Unexpected ServiceNow {kind} state {state!r}.")
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

    def load_sample(self):
        incident = self.parse_incident(load("servicenow_incident.json"))
        problem = self.parse_problem(load("servicenow_problem.json"))
        return {"incident": incident.as_dict(), "problem": problem.as_dict()}
