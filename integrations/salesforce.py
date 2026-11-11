"""Salesforce Service Cloud Case records.

Inbound. The sample is a SOQL query response: totalSize, done, and records[]
with attributes.type Case plus Id, CaseNumber, Subject, Description, Status,
Priority, Origin, and AccountId. Status values in the sample are the defaults
New, Working, Escalated, and Closed.

Docs:
- https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_case.htm
- https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/dome_query.htm
"""

from integrations.base import EscalationSignal
from integrations.fixtures import load

STATUSES = {"New", "Working", "Escalated", "Closed"}


class SalesforceAdapter:
    name = "salesforce"
    direction = "inbound"

    def parse_query(self, payload):
        if payload.get("done") is not True:
            raise ValueError("Salesforce query is not done; this harness reads one page.")
        signals = []
        for record in payload["records"]:
            if record.get("attributes", {}).get("type") != "Case":
                raise ValueError("Salesforce record is not a Case.")
            status = record["Status"]
            if status not in STATUSES:
                raise ValueError(f"Unexpected Case Status {status!r}.")
            signals.append(EscalationSignal(
                tool=self.name,
                external_id=record["Id"],
                title=record["Subject"],
                status=status.lower(),
                summary=record.get("Description") or record["Subject"],
                opened_at=record["CreatedDate"],
                customer=record.get("AccountId"),
                links={
                    "case_number": record["CaseNumber"],
                    "priority": record.get("Priority"),
                    "origin": record.get("Origin"),
                },
                sample=True,
            ))
        return signals

    def load_sample(self):
        return [signal.as_dict() for signal in self.parse_query(load("salesforce_cases.json"))]
