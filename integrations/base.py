"""Shared escalation signal, lesson, and human-approved write types."""

from dataclasses import dataclass, field


class ApprovalRequired(Exception):
    """A write was attempted before a person approved the proposal."""


class LiveConfigError(Exception):
    """Live mode was requested without the environment variables it needs."""


@dataclass(frozen=True)
class EscalationSignal:
    """A normalized intake record. Field names here are the harness model, not a vendor schema."""

    tool: str
    external_id: str
    title: str
    status: str
    summary: str
    opened_at: str
    customer: str | None = None
    links: dict = field(default_factory=dict)
    sample: bool = True

    def as_dict(self):
        return {
            "tool": self.tool,
            "external_id": self.external_id,
            "title": self.title,
            "status": self.status,
            "summary": self.summary,
            "opened_at": self.opened_at,
            "customer": self.customer,
            "links": self.links,
            "sample": self.sample,
        }


@dataclass(frozen=True)
class FollowUp:
    id: str
    team: str
    title: str
    owner: str
    criterion: str

    def as_dict(self):
        return {
            "id": self.id,
            "team": self.team,
            "title": self.title,
            "owner": self.owner,
            "criterion": self.criterion,
        }


@dataclass(frozen=True)
class Lesson:
    case_id: str
    title: str
    cause: str
    actions: tuple

    def as_dict(self):
        return {
            "case_id": self.case_id,
            "title": self.title,
            "cause": self.cause,
            "actions": [action.as_dict() for action in self.actions],
        }


@dataclass
class WriteProposal:
    """A write that has not been sent. Execution requires state 'approved'."""

    tool: str
    operation: str
    summary: str
    request: dict
    state: str = "proposed"

    def as_dict(self):
        return {
            "tool": self.tool,
            "operation": self.operation,
            "summary": self.summary,
            "request": self.request,
            "state": self.state,
        }


def approve(proposal):
    """Return an approved copy. The original proposal stays proposed."""
    if proposal.state != "proposed":
        raise ApprovalRequired("Only a proposed write can be approved.")
    return WriteProposal(
        tool=proposal.tool,
        operation=proposal.operation,
        summary=proposal.summary,
        request=proposal.request,
        state="approved",
    )


def receipt(proposal, *, network, status, detail):
    return {
        "tool": proposal.tool,
        "operation": proposal.operation,
        "state": proposal.state,
        "status": status,
        "network": network,
        "detail": detail,
        "request": proposal.request,
    }
