"""Parse public API payloads into EscalationSignal records.

Each parser accepts the JSON a documented endpoint or webhook returns. Sample
fixtures are labeled and loaded from disk. Optional live pulls build the same
request and send it only when ELH_INTEGRATIONS_MODE=live and a transport is
passed in. Credential values are read from the environment at call time and
are never stored on the signal.

Doc links live next to the parser they describe.
"""

import json
from pathlib import Path

from integrations.model import (
    ACKNOWLEDGED,
    CLOSED,
    OPEN,
    RESOLVED,
    UNKNOWN,
    WAITING,
    EscalationSignal,
    IntegrationError,
)

FIXTURES = Path(__file__).with_name("fixtures")

# Incident state values from the incident state model. Choice values are strings
# in Table API responses.
# https://www.servicenow.com/docs/bundle/xanadu-it-service-management/page/product/incident-management/concept/c_IncidentManagementStateModel.html
SERVICENOW_INCIDENT_STATES = {
    "1": OPEN,          # New
    "2": ACKNOWLEDGED,  # In Progress
    "3": WAITING,       # On Hold
    "6": RESOLVED,      # Resolved
    "7": CLOSED,        # Closed
    "8": CLOSED,        # Canceled
}

# Problem states commonly returned by the problem table. The Table API example
# uses a numeric string for state.
# https://www.servicenow.com/docs/r/xanadu/api-reference/rest-apis/c_TableAPI.html
SERVICENOW_PROBLEM_STATES = {
    "101": OPEN,
    "102": ACKNOWLEDGED,  # Assess
    "103": ACKNOWLEDGED,  # Root Cause Analysis
    "104": ACKNOWLEDGED,  # Fix in Progress
    "106": RESOLVED,
    "107": CLOSED,
}

# https://docs.usepylon.com/pylon-docs/developer/api/api-reference/issues
PYLON_STATES = {
    "new": OPEN,
    "waiting_on_you": ACKNOWLEDGED,
    "waiting_on_customer": WAITING,
    "on_hold": WAITING,
    "closed": CLOSED,
}

# https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_case.htm
SALESFORCE_CASE_STATUSES = {
    "new": OPEN,
    "working": ACKNOWLEDGED,
    "escalated": ACKNOWLEDGED,
    "on hold": WAITING,
    "closed": CLOSED,
}

# https://docs.pagerduty.com/developer/webhooks-v2-overview
PAGERDUTY_STATUSES = {
    "triggered": OPEN,
    "acknowledged": ACKNOWLEDGED,
    "resolved": RESOLVED,
}


def load_fixture(name):
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not payload.get("sample"):
        raise IntegrationError(f"{name} must set sample=true so fixtures cannot be mistaken for a live tenant.")
    return payload["body"]


def _require(record, *keys):
    missing = [key for key in keys if record.get(key) in (None, "")]
    if missing:
        raise IntegrationError("Missing required fields: " + ", ".join(missing))
    return record


def _reference(value):
    """Table API reference fields are either a sys_id string or {link, value}."""
    if isinstance(value, dict):
        return value.get("value") or ""
    return value or ""


class ServiceNowAdapter:
    """Incidents and problem records via the Table API. Updates are outbound writes.

    https://www.servicenow.com/docs/r/xanadu/api-reference/rest-apis/c_TableAPI.html
    """

    tool = "servicenow"

    def parse_incident(self, record, *, sample=True):
        record = _require(record, "sys_id", "number", "short_description", "state")
        state = str(record["state"])
        return EscalationSignal(
            tool=self.tool,
            kind="incident",
            external_id=record["number"],
            title=record["short_description"],
            body=record.get("description") or record["short_description"],
            status=SERVICENOW_INCIDENT_STATES.get(state, UNKNOWN),
            raw_status=state,
            occurred_at=record.get("opened_at") or record.get("sys_created_on"),
            customer=_reference(record.get("caller_id")) or None,
            severity=str(record["priority"]) if record.get("priority") else None,
            url=None,
            sample=sample,
            links={
                "sys_id": record["sys_id"],
                "problem_id": _reference(record.get("problem_id")),
                "assignment_group": _reference(record.get("assignment_group")),
            },
        )

    def parse_problem(self, record, *, sample=True):
        record = _require(record, "sys_id", "number", "short_description", "state")
        state = str(record["state"])
        return EscalationSignal(
            tool=self.tool,
            kind="problem",
            external_id=record["number"],
            title=record["short_description"],
            body=record.get("description") or record.get("close_notes") or record["short_description"],
            status=SERVICENOW_PROBLEM_STATES.get(state, UNKNOWN),
            raw_status=state,
            occurred_at=record.get("opened_at") or record.get("sys_created_on"),
            severity=str(record["priority"]) if record.get("priority") else None,
            sample=sample,
            links={"sys_id": record["sys_id"]},
        )

    def parse_table_response(self, payload, *, kind, sample=True):
        """Accept either a single record or the Table API list envelope {"result": [...]}."""
        if isinstance(payload, dict) and "result" in payload:
            rows = payload["result"]
            if isinstance(rows, dict):
                rows = [rows]
        elif isinstance(payload, dict):
            rows = [payload]
        else:
            raise IntegrationError("ServiceNow payload must be a record or a result envelope.")
        parser = self.parse_incident if kind == "incident" else self.parse_problem
        return [parser(row, sample=sample) for row in rows]

    def work_note_request(self, signal, note):
        """PATCH body for /api/now/table/incident/{sys_id}. Proposed, not sent."""
        sys_id = signal.links.get("sys_id")
        if signal.kind != "incident" or not sys_id:
            raise IntegrationError("A ServiceNow work note needs an incident sys_id.")
        if not note.strip():
            raise IntegrationError("A work note cannot be empty.")
        return {
            "method": "PATCH",
            "path": f"/api/now/table/incident/{sys_id}",
            "headers": {"Accept": "application/json", "Content-Type": "application/json"},
            "body": {"work_notes": note},
        }

    def pull_live(self, kind, sys_id, transport):
        import os
        instance = os.environ.get("SERVICENOW_INSTANCE", "").strip().rstrip("/")
        token = os.environ.get("SERVICENOW_TOKEN", "")
        if not instance or not token:
            raise IntegrationError("Live ServiceNow needs SERVICENOW_INSTANCE and SERVICENOW_TOKEN.")
        table = "incident" if kind == "incident" else "problem"
        request = {
            "method": "GET",
            "url": f"{instance}/api/now/table/{table}/{sys_id}",
            "headers": {"Accept": "application/json", "Authorization": f"Bearer {token}"},
        }
        payload = transport(request)
        result = payload.get("result", payload)
        parser = self.parse_incident if kind == "incident" else self.parse_problem
        signal = parser(result, sample=False)
        return signal


class PylonAdapter:
    """Pylon issues and the account nested on an issue. Inbound only.

    Issue resource: https://docs.usepylon.com/pylon-docs/developer/api/api-reference/issues
    Webhook variables: https://docs.usepylon.com/pylon-docs/developer/webhooks
    """

    tool = "pylon"

    def parse_issue(self, payload, *, sample=True):
        record = payload.get("data", payload) if isinstance(payload, dict) else None
        if not isinstance(record, dict):
            raise IntegrationError("Pylon issue payload must be an object or {data: issue}.")
        record = _require(record, "id", "number", "title", "state")
        account = record.get("account") or {}
        state = str(record["state"])
        return EscalationSignal(
            tool=self.tool,
            kind="issue",
            external_id=str(record["number"]),
            title=record["title"],
            body=_html_to_text(record.get("body_html") or record.get("title")),
            status=PYLON_STATES.get(state, UNKNOWN),
            raw_status=state,
            occurred_at=record.get("created_at"),
            customer=account.get("id") or (record.get("requester") or {}).get("email"),
            severity=_pylon_priority(record),
            url=record.get("link") or None,
            sample=sample,
            links={
                "id": record["id"],
                "account_id": account.get("id") or "",
                "requester_email": (record.get("requester") or {}).get("email") or "",
                "external_incidents": [
                    item.get("external_id") for item in record.get("external_incidents") or []
                    if isinstance(item, dict) and item.get("external_id")
                ],
            },
        )

    def parse_webhook(self, payload, *, sample=True):
        """Trigger webhooks arrive as strings, including numbers and booleans.

        https://docs.usepylon.com/pylon-docs/developer/webhooks
        """
        payload = _require(payload, "issue_id", "issue_number", "title", "status")
        state = str(payload["status"])
        tags = [part.strip() for part in str(payload.get("tags") or "").split(",") if part.strip()]
        return EscalationSignal(
            tool=self.tool,
            kind="issue",
            external_id=str(payload["issue_number"]),
            title=payload["title"],
            body=str(payload.get("message_body") or payload["title"]),
            status=PYLON_STATES.get(state, UNKNOWN),
            raw_status=state,
            occurred_at=payload.get("message_sent_at") or None,
            customer=payload.get("account_id") or payload.get("requester_email") or None,
            sample=sample,
            links={
                "id": payload["issue_id"],
                "account_id": payload.get("account_id") or "",
                "tags": tags,
            },
        )

    def parse_account(self, record, *, sample=True):
        record = record.get("data", record) if isinstance(record, dict) else None
        record = _require(record, "id", "name")
        domains = record.get("domains") or []
        if isinstance(domains, str):
            domains = [part.strip() for part in domains.split(",") if part.strip()]
        return {
            "id": record["id"],
            "name": record["name"],
            "domains": domains,
            "sample": sample,
        }

    def pull_live(self, issue_id, transport):
        import os
        token = os.environ.get("PYLON_API_TOKEN", "")
        if not token:
            raise IntegrationError("Live Pylon needs PYLON_API_TOKEN.")
        request = {
            "method": "GET",
            "url": f"https://api.usepylon.com/issues/{issue_id}",
            "headers": {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        }
        return self.parse_issue(transport(request), sample=False)


class SalesforceAdapter:
    """Service Cloud Case records. Inbound. Change events and sObject GETs both parse.

    Case fields: https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_case.htm
    Retrieve: https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_sobject_retrieve.htm
    Change events: https://developer.salesforce.com/docs/atlas.en-us.change_data_capture.meta/change_data_capture/cdc_event_fields_body.htm
    """

    tool = "salesforce"

    def parse_case(self, record, *, sample=True):
        if isinstance(record, dict) and "ChangeEventHeader" in record:
            return self.parse_change_event(record, sample=sample)
        record = _require(record, "Id", "CaseNumber", "Subject", "Status")
        status = str(record["Status"])
        return EscalationSignal(
            tool=self.tool,
            kind="case",
            external_id=record["CaseNumber"],
            title=record["Subject"],
            body=record.get("Description") or record["Subject"],
            status=SALESFORCE_CASE_STATUSES.get(status.lower(), UNKNOWN),
            raw_status=status,
            occurred_at=record.get("CreatedDate"),
            customer=record.get("AccountId") or None,
            severity=record.get("Priority"),
            sample=sample,
            links={
                "id": record["Id"],
                "origin": record.get("Origin") or "",
                "owner_id": record.get("OwnerId") or "",
                "is_closed": bool(record.get("IsClosed")),
            },
        )

    def parse_change_event(self, event, *, sample=True):
        header = _require(event.get("ChangeEventHeader") or {}, "entityName", "recordIds", "changeType")
        if header["entityName"] != "Case":
            raise IntegrationError("Only Case change events map into the harness.")
        record_id = header["recordIds"][0]
        status = str(event.get("Status") or "")
        subject = event.get("Subject") or f"Case {record_id}"
        return EscalationSignal(
            tool=self.tool,
            kind="case_change",
            external_id=record_id,
            title=subject,
            body=event.get("Description") or subject,
            status=SALESFORCE_CASE_STATUSES.get(status.lower(), UNKNOWN) if status else UNKNOWN,
            raw_status=status or header["changeType"],
            sample=sample,
            links={"change_type": header["changeType"], "changed_fields": header.get("changedFields") or []},
        )

    def pull_live(self, case_id, transport):
        import os
        base = os.environ.get("SALESFORCE_INSTANCE_URL", "").strip().rstrip("/")
        token = os.environ.get("SALESFORCE_ACCESS_TOKEN", "")
        version = os.environ.get("SALESFORCE_API_VERSION", "v62.0")
        if not base or not token:
            raise IntegrationError("Live Salesforce needs SALESFORCE_INSTANCE_URL and SALESFORCE_ACCESS_TOKEN.")
        request = {
            "method": "GET",
            "url": f"{base}/services/data/{version}/sobjects/Case/{case_id}",
            "headers": {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        }
        return self.parse_case(transport(request), sample=False)


class PagerDutyAdapter:
    """Incidents and incident log entries (the timeline). Inbound.

    REST incident: https://docs.pagerduty.com/developer/api/reference/rest/incidents/get-incident
    Log entries: https://docs.pagerduty.com/developer/api/reference/rest/incidents/list-incident-log-entries
    V3 webhook: https://developer.pagerduty.com/docs/webhooks/v3-overview
    V2 webhook: https://docs.pagerduty.com/developer/webhooks-v2-overview
    """

    tool = "pagerduty"

    def parse_incident(self, payload, *, sample=True):
        record = payload.get("incident", payload) if isinstance(payload, dict) else None
        record = _require(record, "id", "title", "status")
        number = record.get("incident_number", record.get("number"))
        if number in (None, ""):
            raise IntegrationError("Missing required fields: incident_number")
        status = str(record["status"])
        service = record.get("service") or {}
        return EscalationSignal(
            tool=self.tool,
            kind="incident",
            external_id=str(number),
            title=record["title"],
            body=record.get("description") or record["title"],
            status=PAGERDUTY_STATUSES.get(status, UNKNOWN),
            raw_status=status,
            occurred_at=record.get("created_at"),
            severity=(record.get("priority") or {}).get("summary") or record.get("urgency"),
            url=record.get("html_url"),
            sample=sample,
            links={
                "id": record["id"],
                "incident_key": record.get("incident_key") or "",
                "service": service.get("summary") or service.get("id") or "",
            },
        )

    def parse_webhook(self, payload, *, sample=True):
        if isinstance(payload, dict) and "event" in payload:
            event = payload["event"]
            data = _require(event.get("data") or {}, "id", "title", "status", "number")
            data = {**data, "incident_number": data.get("number")}
            signal = self.parse_incident(data, sample=sample)
            signal.links["event_type"] = event.get("event_type") or ""
            signal.occurred_at = event.get("occurred_at") or signal.occurred_at
            return signal
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not messages:
            raise IntegrationError("PagerDuty webhook needs an event object or a messages array.")
        message = messages[0]
        return self.parse_incident(message.get("incident") or {}, sample=sample)

    def parse_log_entries(self, payload, *, sample=True):
        entries = payload.get("log_entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries:
            raise IntegrationError("PagerDuty timeline needs a log_entries array.")
        timeline = []
        for entry in entries:
            _require(entry, "id", "type", "created_at", "summary")
            timeline.append({
                "id": entry["id"],
                "type": entry["type"],
                "created_at": entry["created_at"],
                "summary": entry["summary"],
                "sample": sample,
            })
        return timeline

    def pull_live(self, incident_id, transport):
        import os
        token = os.environ.get("PAGERDUTY_API_TOKEN", "")
        if not token:
            raise IntegrationError("Live PagerDuty needs PAGERDUTY_API_TOKEN.")
        headers = {
            "Authorization": f"Token token={token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }
        incident = transport({
            "method": "GET",
            "url": f"https://api.pagerduty.com/incidents/{incident_id}",
            "headers": headers,
        })
        timeline = transport({
            "method": "GET",
            "url": f"https://api.pagerduty.com/incidents/{incident_id}/log_entries",
            "headers": headers,
        })
        signal = self.parse_incident(incident, sample=False)
        signal.links["timeline"] = self.parse_log_entries(timeline, sample=False)
        return signal


class SlackAdapter:
    """Incident-channel threads in, lesson posts out.

    Events API: https://docs.slack.dev/apis/events-api
    conversations.replies: https://docs.slack.dev/reference/methods/conversations.replies
    chat.postMessage: https://docs.slack.dev/reference/methods/chat.postMessage/
    """

    tool = "slack"

    def parse_event(self, payload, *, sample=True):
        if payload.get("type") != "event_callback":
            raise IntegrationError("Slack inbound expects an event_callback envelope.")
        event = _require(payload.get("event") or {}, "type", "channel", "text", "ts")
        if event["type"] != "message":
            raise IntegrationError("Only message events map into the harness.")
        thread_ts = event.get("thread_ts") or event["ts"]
        return EscalationSignal(
            tool=self.tool,
            kind="thread_message",
            external_id=f"{event['channel']}:{thread_ts}",
            title=_title_from_text(event["text"]),
            body=event["text"],
            status=OPEN,
            raw_status="message",
            occurred_at=event.get("ts"),
            sample=sample,
            links={
                "channel": event["channel"],
                "ts": event["ts"],
                "thread_ts": thread_ts,
                "user": event.get("user") or "",
                "event_id": payload.get("event_id") or "",
            },
        )

    def parse_replies(self, payload, *, sample=True):
        if not payload.get("ok"):
            raise IntegrationError("conversations.replies returned ok=false.")
        messages = payload.get("messages") or []
        if not messages:
            raise IntegrationError("Slack thread has no messages.")
        parent = messages[0]
        _require(parent, "text", "ts")
        channel = payload.get("channel") or ""
        thread = []
        for message in messages:
            _require(message, "text", "ts")
            thread.append({
                "user": message.get("user") or "",
                "text": message["text"],
                "ts": message["ts"],
                "thread_ts": message.get("thread_ts") or parent["ts"],
                "sample": sample,
            })
        signal = EscalationSignal(
            tool=self.tool,
            kind="thread",
            external_id=f"{channel}:{parent['ts']}" if channel else parent["ts"],
            title=_title_from_text(parent["text"]),
            body="\n".join(item["text"] for item in thread),
            status=OPEN,
            raw_status="thread",
            occurred_at=parent["ts"],
            sample=sample,
            links={"channel": channel, "thread_ts": parent["ts"], "messages": thread},
        )
        return signal

    def post_request(self, channel, thread_ts, text):
        if not channel or not thread_ts or not text.strip():
            raise IntegrationError("A Slack reply needs channel, thread_ts, and text.")
        return {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "body": {"channel": channel, "thread_ts": thread_ts, "text": text},
        }

    def pull_live(self, channel, thread_ts, transport):
        import os
        token = os.environ.get("SLACK_BOT_TOKEN", "")
        if not token:
            raise IntegrationError("Live Slack reads need SLACK_BOT_TOKEN.")
        request = {
            "method": "GET",
            "url": "https://slack.com/api/conversations.replies",
            "headers": {"Authorization": f"Bearer {token}"},
            "query": {"channel": channel, "ts": thread_ts},
        }
        payload = transport(request)
        payload = {**payload, "channel": channel}
        return self.parse_replies(payload, sample=False)


class JiraAdapter:
    """Create follow-up issues from lessons. Outbound and approval-gated.

    Create issue: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post
    Issue webhook shape, used if a created issue is read back:
    https://developer.atlassian.com/cloud/jira/platform/webhooks/
    """

    tool = "jira"

    def create_request(self, follow_up, *, project_key="LEARN"):
        if not follow_up.title or not follow_up.criterion:
            raise IntegrationError("A Jira action item needs a title and an acceptance criterion.")
        description = (
            f"Owner: {follow_up.owner or 'unassigned'}\n"
            f"Acceptance: {follow_up.criterion}\n"
            f"Sources: {', '.join(follow_up.sources)}"
        )
        return {
            "method": "POST",
            "path": "/rest/api/3/issue",
            "body": {
                "fields": {
                    "project": {"key": project_key},
                    "issuetype": {"name": "Task"},
                    "summary": follow_up.title,
                    "labels": ["escalation-learning", "action-item"],
                    "description": _adf(description),
                }
            },
        }

    def parse_issue_webhook(self, payload, *, sample=True):
        if payload.get("webhookEvent") not in {"jira:issue_created", "jira:issue_updated"}:
            raise IntegrationError("Unsupported Jira webhookEvent.")
        issue = _require(payload.get("issue") or {}, "id", "key")
        fields = _require(issue.get("fields") or {}, "summary")
        status_name = ((fields.get("status") or {}).get("name")) or "To Do"
        return EscalationSignal(
            tool=self.tool,
            kind="issue",
            external_id=issue["key"],
            title=fields["summary"],
            body=_adf_text(fields.get("description")) or fields["summary"],
            status=RESOLVED if status_name.lower() == "done" else OPEN,
            raw_status=status_name,
            occurred_at=fields.get("created"),
            sample=sample,
            links={"id": issue["id"], "webhook_event": payload["webhookEvent"]},
        )

    def pull_live(self, issue_key, transport):
        import os
        base = os.environ.get("JIRA_BASE_URL", "").strip().rstrip("/")
        email = os.environ.get("JIRA_EMAIL", "")
        token = os.environ.get("JIRA_API_TOKEN", "")
        if not base or not email or not token:
            raise IntegrationError("Live Jira needs JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN.")
        import base64
        basic = base64.b64encode(f"{email}:{token}".encode()).decode()
        request = {
            "method": "GET",
            "url": f"{base}/rest/api/3/issue/{issue_key}",
            "headers": {"Authorization": f"Basic {basic}", "Accept": "application/json"},
        }
        issue = transport(request)
        return self.parse_issue_webhook({
            "webhookEvent": "jira:issue_updated",
            "issue": issue,
        }, sample=False)


def _title_from_text(text):
    line = text.strip().splitlines()[0]
    return line[:120]


def _html_to_text(value):
    text = str(value)
    for token in ("<p>", "</p>", "<br>", "<br/>"):
        text = text.replace(token, " ")
    return " ".join(text.split())


def _pylon_priority(record):
    custom = record.get("custom_fields") or {}
    priority = custom.get("priority")
    if isinstance(priority, dict):
        return priority.get("value")
    return None


def _adf(text):
    return {
        "type": "doc",
        "version": 1,
        "content": [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }],
    }


def _adf_text(value):
    if not isinstance(value, dict):
        return str(value or "")
    chunks = []
    for block in value.get("content") or []:
        for inline in block.get("content") or []:
            if inline.get("text"):
                chunks.append(inline["text"])
    return "\n".join(chunks)
