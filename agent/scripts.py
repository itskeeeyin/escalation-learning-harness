"""Fixture tool sequences. The scripted model replays these in order."""

HAPPY_ESC_1042 = [
    {"name": "read_case_evidence"},
    {"name": "read_sample_records", "arguments": {"tool": "pagerduty"}},
    {"name": "classify_priority", "arguments": {"impact": 2, "urgency": 1}},
    {"name": "record_intake"},
    {"name": "confirm_priority"},
    {"name": "record_handoff", "arguments": {"team": "support", "escalation_type": "functional"}},
    {"name": "record_handoff", "arguments": {"team": "engineering", "escalation_type": "functional"}},
    {"name": "record_handoff", "arguments": {"team": "executive", "escalation_type": "hierarchical"}},
    {"name": "approve_draft"},
    {"name": "load_recovery_evidence"},
    {"name": "confirm_recovery"},
    {"name": "match_recurrence"},
    {"name": "match_known_error"},
    {"name": "run_learning"},
    {"name": "approve_plan"},
    {"name": "load_completion_evidence"},
    {"name": "return_engineering_proof"},
    {"name": "resubmit_engineering_proof"},
    *({"name": "verify_change", "arguments": {"action_id": action}} for action in (
        "ENG", "PROD", "SUP", "CS", "DOC", "OPS", "EXEC",
    )),
    {"name": "propose_jira"},
    {"name": "approve_write", "arguments": {"proposal_index": 0}},
    {"name": "execute_write", "arguments": {"proposal_index": 0, "dry_run": True}},
    {"name": "close_case"},
    {"name": "complete_run", "arguments": {"summary": "Fictional ESC-1042 practice run finished."}},
]

WRITE_WITHOUT_APPROVAL = [
    {"name": "propose_jira"},
    {"name": "execute_write", "arguments": {"proposal_index": 0}},
]

CLOSE_WITHOUT_EFFECTIVENESS = [
    {"name": "record_intake"},
    {"name": "close_case"},
]

LOOKALIKE_ESC_1043 = [
    {"name": "start_lookalike"},
    {"name": "inspect_lookalike"},
    {"name": "read_practice_record", "arguments": {"record_id": "P2"}},
    {"name": "route_lookalike", "arguments": {"decision": "separate"}},
    {"name": "recover_lookalike"},
    {"name": "match_known_error"},
    {"name": "complete_run", "arguments": {"summary": "Fictional ESC-1043 stayed separate."}},
]

SCRIPTS = {
    "happy": HAPPY_ESC_1042,
    "write_without_approval": WRITE_WITHOUT_APPROVAL,
    "close_without_effectiveness": CLOSE_WITHOUT_EFFECTIVENESS,
    "lookalike": LOOKALIKE_ESC_1043,
}

SCRIPT_CASE = {
    "happy": "ESC-1042",
    "write_without_approval": "ESC-1042",
    "close_without_effectiveness": "ESC-1042",
    "lookalike": "ESC-1043",
}
