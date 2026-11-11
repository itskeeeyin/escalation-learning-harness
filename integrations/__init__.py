"""Tool adapters for escalation intake and follow-up.

Default mode reads labeled sample payloads. Live calls are optional, use
environment variables only, and never run unless a reviewer has approved a
write and dry-run is turned off. See docs/integrations.md.
"""

from integrations.base import (
    ApprovalRequired,
    EscalationSignal,
    FollowUp,
    Lesson,
    LiveConfigError,
    WriteProposal,
)
from integrations.replay import cross_tool_replay

__all__ = [
    "ApprovalRequired",
    "EscalationSignal",
    "FollowUp",
    "Lesson",
    "LiveConfigError",
    "WriteProposal",
    "cross_tool_replay",
]
