"""How this practice flow maps onto ITIL 4 terms.

The matrix, records, and phases are example data for the fictional case.
They are not an organizational standard and not a certification claim.
"""


class ItilFailure(ValueError):
    def __init__(self, failure_class, message):
        self.failure_class = failure_class
        super().__init__(f"{failure_class}: {message}")


# Fictional example. Impact is how much is broken. Urgency is how soon it must move.
IMPACT = {
    "1": "High. Many customers, or the service is unusable.",
    "2": "Medium. One customer workflow is blocked.",
    "3": "Low. A workaround is already available and no rollout is blocked.",
}
URGENCY = {
    "1": "High. The customer deadline is inside 24 hours.",
    "2": "Medium. The customer deadline is inside five days.",
    "3": "Low. The work can wait for the normal queue.",
}
# Rows are impact, columns are urgency. P1 on this example is the major-incident cell.
MATRIX = {
    ("1", "1"): "P1",
    ("1", "2"): "P2",
    ("1", "3"): "P3",
    ("2", "1"): "P2",
    ("2", "2"): "P3",
    ("2", "3"): "P4",
    ("3", "1"): "P3",
    ("3", "2"): "P4",
    ("3", "3"): "P5",
}
PHASES = ("problem_identification", "problem_control", "error_control")
CHANGE_STATES = (
    "proposed",
    "assessed_authorized",
    "implemented",
    "verified_effective",
    "closed",
)
WORKAROUND = (
    "Rebuild the template from the requirements worksheet and validate both routing paths."
)
ROOT_CAUSE = (
    "Confirming Discard removes the draft. On a test copy the prompt did not name the draft "
    "or state that configuration would be lost."
)


def matrix_table():
    return [
        {
            "impact": impact,
            "impact_meaning": IMPACT[impact],
            "urgency": urgency,
            "urgency_meaning": URGENCY[urgency],
            "priority": priority,
        }
        for (impact, urgency), priority in MATRIX.items()
    ]


def priority_from_matrix(impact, urgency):
    key = (str(impact), str(urgency))
    if key not in MATRIX:
        raise ItilFailure(
            "PriorityMatrixMiss",
            f"Impact {impact!r} and urgency {urgency!r} are not on the example matrix.",
        )
    return MATRIX[key]


def handoff(handoff_id, escalation, destination, summary):
    if escalation not in {"functional", "hierarchical"}:
        raise ItilFailure(
            "EscalationTypeMissing",
            f"Handoff {handoff_id} needs escalation functional or hierarchical.",
        )
    return {
        "id": handoff_id,
        "escalation": escalation,
        "to": destination,
        "summary": summary,
        "sample": True,
    }


def change_record(row):
    if not row.get("change_id"):
        return None
    state = row.get("change_state")
    if state not in CHANGE_STATES:
        raise ItilFailure(
            "ChangeStateInvalid",
            f"{row['change_id']} is {state!r}. Expected one of {', '.join(CHANGE_STATES)}.",
        )
    return {
        "id": row["change_id"],
        "action_id": row["id"],
        "kind": row["kind"].lower(),
        "title": row["title"],
        "owner": row["owner"],
        "state": state,
        "effectiveness_required": True,
        "problem_id": "PRB-1042",
        "sample": True,
        "label": "Fictional change request. Effectiveness is a required gate.",
    }


def practice_records(*, stage, problem_phase, known_error, priority_confirmed=False):
    """Incident, problem, known error, and a known error database entry.

    The incident is closed once the customer is recovered. The problem stays
    open through error control until every corrective and preventive change
    is verified effective and the learning record closes.
    """
    incident_closed = stage in {"Learn", "Verify", "Closed"}
    incident = {
        "record_type": "incident",
        "id": "INC-1042",
        "case_id": "ESC-1042",
        "servicenow_number": "INC0011042",
        "sample": True,
        "label": "Fictional incident. Example Privacy Team is not a real customer.",
        "state": "closed" if incident_closed else "in_progress" if stage == "Coordinate" else "new",
        "priority": "P2" if priority_confirmed else "pending",
        "problem_id": "PRB-1042" if problem_phase else None,
        "resolution": WORKAROUND if incident_closed else None,
    }
    if problem_phase not in {None, *PHASES}:
        raise ItilFailure(
            "ProblemPhaseInvalid",
            f"Problem phase {problem_phase!r} is not one of {', '.join(PHASES)}.",
        )
    problem = None
    known = None
    database = []
    if problem_phase:
        completed = list(PHASES[: PHASES.index(problem_phase)])
        problem_open = stage != "Closed"
        cause = ROOT_CAUSE if known_error else None
        problem = {
            "record_type": "problem",
            "id": "PRB-1042",
            "servicenow_number": "PRB0001042",
            "sample": True,
            "label": "Fictional problem. It stays open after the incident closes.",
            "state": "open" if problem_open else "closed",
            "phase": problem_phase,
            "phases_completed": completed,
            "incident_id": "INC-1042",
            "workaround": WORKAROUND if known_error else None,
            "root_cause": cause,
            "known_error_id": "KE-1042" if known_error else None,
        }
        if known_error:
            fix_verified = stage == "Closed"
            known = {
                "record_type": "known_error",
                "id": "KE-1042",
                "sample": True,
                "label": "Fictional known error, created because a workaround or root cause is documented.",
                "problem_id": "PRB-1042",
                "kedb_id": "KEDB-1042",
                "workaround": WORKAROUND,
                "root_cause": cause,
                "status": "permanent_fix_verified" if fix_verified else "known_error",
            }
            database = [{
                "id": "KEDB-1042",
                "sample": True,
                "label": "Fictional known error database entry.",
                "title": "Irreversible draft discard without a named warning",
                "workaround": WORKAROUND,
                "root_cause": cause,
                "status": known["status"],
            }]
    return {
        "sample": True,
        "label": "Fictional example records for how this flow maps to ITIL 4 practices.",
        "incident": incident,
        "problem": problem,
        "known_error": known,
        "known_error_database": database,
    }
