"""PagerDuty incidents and timeline log entries.

Inbound. Incident fields follow the REST incident resource (id, incident_number,
title, status, urgency, html_url, service, created_at). Status values used here
are triggered, acknowledged, and resolved.

Webhook envelopes follow PagerDuty v3: event.event_type, event.occurred_at, and
event.data for the incident. Timeline rows follow log entry `type` values such
as trigger_log_entry and resolve_log_entry.

Docs:
- https://docs.pagerduty.com/developer/api/reference/rest/incidents/get-incident
- https://docs.pagerduty.com/developer/webhooks-overview
- https://docs.pagerduty.com/developer/api/reference/rest/log-entries/list-log-entries
"""

from integrations.base import EscalationSignal
from integrations.fixtures import load

STATUSES = {"triggered", "acknowledged", "resolved"}


class PagerDutyAdapter:
    name = "pagerduty"
    direction = "inbound"

    def parse_incident(self, incident):
        status = incident["status"]
        if status not in STATUSES:
            raise ValueError(f"Unexpected PagerDuty status {status!r}.")
        return EscalationSignal(
            tool=self.name,
            external_id=incident["id"],
            title=incident["title"],
            status=status,
            summary=incident.get("description") or incident["title"],
            opened_at=incident["created_at"],
            customer=None,
            links={
                "html_url": incident.get("html_url"),
                "incident_number": incident.get("incident_number"),
                "service": (incident.get("service") or {}).get("summary"),
                "urgency": incident.get("urgency"),
            },
            sample=True,
        )

    def parse_webhook(self, envelope):
        event = envelope["event"]
        if not str(event["event_type"]).startswith("incident."):
            raise ValueError("PagerDuty webhook is not an incident event.")
        return self.parse_incident(event["data"])

    def parse_timeline(self, payload):
        return [
            {
                "id": entry["id"],
                "type": entry["type"],
                "summary": entry["summary"],
                "created_at": entry["created_at"],
            }
            for entry in payload["log_entries"]
        ]

    def load_sample(self):
        webhook = load("pagerduty_webhook.json")
        timeline = load("pagerduty_log_entries.json")
        return {
            "signal": self.parse_webhook(webhook).as_dict(),
            "timeline": self.parse_timeline(timeline),
        }
