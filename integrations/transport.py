"""Optional live HTTP. Offline mode never opens a socket."""

import json
import os
import urllib.error
import urllib.request

from integrations.base import LiveConfigError, receipt


def mode():
    value = os.environ.get("INTEGRATIONS_MODE", "offline").strip().lower()
    if value not in {"offline", "live"}:
        raise LiveConfigError("INTEGRATIONS_MODE must be offline or live.")
    return value


def require_env(names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise LiveConfigError("Live mode needs " + ", ".join(missing) + ".")
    return {name: os.environ[name] for name in names}


def http_json(url, *, method="GET", headers=None, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:500]
        raise LiveConfigError(f"Live {method} {url} returned {error.code}: {detail}") from error


def guarded_execute(proposal, *, approved_state_required=True, dry_run=True, send=None):
    """Refuse unapproved writes. Dry-run, the default, describes the request and does not send it."""
    if approved_state_required and proposal.state != "approved":
        from integrations.base import ApprovalRequired

        raise ApprovalRequired(
            f"{proposal.tool} {proposal.operation} is still proposed. Approve it before execution."
        )
    if dry_run or mode() != "live":
        if not dry_run and mode() != "live":
            detail = "Refused to call a remote service because INTEGRATIONS_MODE is offline."
            status = "refused"
        else:
            detail = "Dry run. The request was not sent."
            status = "dry_run"
        return receipt(proposal, network=False, status=status, detail=detail)
    if send is None:
        raise LiveConfigError("Live execution has no transport.")
    status_code, payload = send()
    return receipt(
        proposal,
        network=True,
        status="sent",
        detail={"http_status": status_code, "body": payload},
    )
