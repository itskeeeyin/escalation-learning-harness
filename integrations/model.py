"""Shared escalation records produced by every support-tool adapter.

Field names on the wire stay in each adapter. This module is the harness-side
shape: one signal in, one follow-up or lesson out, and one proposed write that
stays unsent until a person approves it.
"""

from dataclasses import asdict, dataclass, field


class IntegrationError(ValueError):
    """A fixture or live payload does not match the documented shape."""


@dataclass
class EscalationSignal:
    tool: str
    kind: str
    external_id: str
    title: str
    body: str
    status: str
    raw_status: str
    occurred_at: str | None = None
    customer: str | None = None
    severity: str | None = None
    url: str | None = None
    sample: bool = True
    links: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


@dataclass
class FollowUp:
    """A lesson the harness can hand to a downstream tracker."""

    team: str
    title: str
    criterion: str
    sources: list
    owner: str | None = None
    lesson_id: str | None = None

    def as_dict(self):
        return asdict(self)


OPEN = "open"
ACKNOWLEDGED = "acknowledged"
WAITING = "waiting"
RESOLVED = "resolved"
CLOSED = "closed"
UNKNOWN = "unknown"
