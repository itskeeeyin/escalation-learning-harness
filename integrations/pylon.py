"""Pylon issues and accounts.

Inbound. Issue objects follow the public issue resource wrapped in data:
id, number, title, body_html, state, link, created_at, source, account, and
requester. Standard state values are new, waiting_on_you, waiting_on_customer,
on_hold, and closed. Account search rows use id, name, and domains.

Docs:
- https://docs.usepylon.com/pylon-docs/developer/api/api-reference/issues
- https://docs.usepylon.com/pylon-docs/developer/api/conventions
"""

from integrations.base import EscalationSignal
from integrations.fixtures import load

STATES = {"new", "waiting_on_you", "waiting_on_customer", "on_hold", "closed"}


class PylonAdapter:
    name = "pylon"
    direction = "inbound"

    def parse_issue(self, payload):
        issue = payload["data"]
        state = issue["state"]
        if state not in STATES:
            raise ValueError(f"Unexpected Pylon state {state!r}.")
        account = issue.get("account") or {}
        return EscalationSignal(
            tool=self.name,
            external_id=issue["id"],
            title=issue["title"],
            status=state,
            summary=_text(issue.get("body_html") or issue["title"]),
            opened_at=issue["created_at"],
            customer=account.get("id"),
            links={
                "number": issue.get("number"),
                "link": issue.get("link"),
                "source": issue.get("source"),
                "account_id": account.get("id"),
            },
            sample=True,
        )

    def parse_account(self, payload):
        account = payload["data"]
        return {
            "id": account["id"],
            "name": account["name"],
            "domains": list(account.get("domains") or []),
        }

    def load_sample(self):
        return {
            "issue": self.parse_issue(load("pylon_issue.json")).as_dict(),
            "account": self.parse_account(load("pylon_account.json")),
        }


def _text(html):
    out = []
    skip = False
    for char in html:
        if char == "<":
            skip = True
        elif char == ">":
            skip = False
        elif not skip:
            out.append(char)
    return " ".join("".join(out).split())
