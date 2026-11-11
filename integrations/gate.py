"""Human approval for writes. Dry-run is the default, including in live mode.

A proposed payload is the native request body for that tool. Nothing is sent
until approve() records an explicit decision and execute() is called with
dry_run left false. Tests and the hosted demo never reach a live transport.
"""

import os
from dataclasses import dataclass, field

from integrations.model import IntegrationError

MODE_ENV = "ELH_INTEGRATIONS_MODE"
DRY_RUN_ENV = "ELH_INTEGRATIONS_DRY_RUN"


def live_mode_enabled():
    """Live HTTP is opt-in. Unset, empty, and any value other than 'live' stay offline."""
    return os.environ.get(MODE_ENV) == "live"


def dry_run_enabled():
    """Writes stay dry-run unless the operator sets ELH_INTEGRATIONS_DRY_RUN=0."""
    return os.environ.get(DRY_RUN_ENV, "1") != "0"


@dataclass
class ProposedWrite:
    proposal_id: str
    tool: str
    operation: str
    summary: str
    request: dict
    status: str = "proposed"
    approval: str | None = None
    receipt: dict | None = None

    def as_dict(self):
        return {
            "proposal_id": self.proposal_id,
            "tool": self.tool,
            "operation": self.operation,
            "summary": self.summary,
            "request": self.request,
            "status": self.status,
            "approval": self.approval,
            "receipt": self.receipt,
            "sample": True,
        }


@dataclass
class WriteGate:
    dry_run: bool = True
    proposals: dict = field(default_factory=dict)

    def propose(self, proposal_id, tool, operation, summary, request):
        if proposal_id in self.proposals:
            raise IntegrationError(f"Proposal {proposal_id} already exists.")
        if not isinstance(request, dict) or not request:
            raise IntegrationError("A write proposal needs the native request body.")
        proposal = ProposedWrite(proposal_id, tool, operation, summary, request)
        self.proposals[proposal_id] = proposal
        return proposal

    def approve(self, proposal_id, reviewer):
        proposal = self._pending(proposal_id)
        if not reviewer or not str(reviewer).strip():
            raise IntegrationError("Approval requires a named reviewer.")
        proposal.approval = str(reviewer).strip()
        proposal.status = "approved"
        return proposal

    def reject(self, proposal_id, reviewer):
        proposal = self._pending(proposal_id)
        if not reviewer or not str(reviewer).strip():
            raise IntegrationError("Rejection requires a named reviewer.")
        proposal.approval = str(reviewer).strip()
        proposal.status = "rejected"
        proposal.receipt = {"executed": False, "reason": "Reviewer rejected the write."}
        return proposal

    def execute(self, proposal_id, transport=None):
        """Run a write only after approval. Dry-run returns the request and does not call transport."""
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise IntegrationError(f"Unknown proposal {proposal_id}.")
        if proposal.status == "rejected":
            raise IntegrationError("A rejected proposal cannot be executed.")
        if proposal.status != "approved":
            raise IntegrationError("Writes stay proposed until a reviewer approves them.")
        if proposal.receipt and proposal.receipt.get("executed"):
            raise IntegrationError("This proposal was already executed.")
        if self.dry_run:
            proposal.status = "dry_run"
            proposal.receipt = {
                "executed": False,
                "dry_run": True,
                "tool": proposal.tool,
                "operation": proposal.operation,
                "request": proposal.request,
            }
            return proposal
        if transport is None:
            raise IntegrationError("Live execution needs a transport. Refusing to call a service implicitly.")
        if not live_mode_enabled():
            raise IntegrationError("Set ELH_INTEGRATIONS_MODE=live before sending an approved write.")
        response = transport(proposal.request)
        proposal.status = "executed"
        proposal.receipt = {"executed": True, "dry_run": False, "response": response}
        return proposal

    def _pending(self, proposal_id):
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise IntegrationError(f"Unknown proposal {proposal_id}.")
        if proposal.status != "proposed":
            raise IntegrationError("Only a proposed write can be approved or rejected.")
        return proposal
