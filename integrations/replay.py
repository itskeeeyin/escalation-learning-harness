"""One fictional escalation read from several tools, then a gated Jira follow-up.

The payloads are the labeled fixtures in integrations/fixtures. This module does
not open sockets. Live mode is a separate call on each adapter.
"""

from harness import propose_actions, recurrence
from integrations.adapters import (
    JiraAdapter,
    PagerDutyAdapter,
    PylonAdapter,
    SalesforceAdapter,
    ServiceNowAdapter,
    SlackAdapter,
    load_fixture,
)
from integrations.gate import WriteGate

CASE_ID = "ESC-1042"


def cross_tool_replay():
    """PagerDuty page, Slack thread, case records, harness lesson, proposed writes."""
    pagerduty = PagerDutyAdapter()
    slack = SlackAdapter()
    servicenow = ServiceNowAdapter()
    salesforce = SalesforceAdapter()
    pylon = PylonAdapter()
    jira = JiraAdapter()

    page = pagerduty.parse_webhook(load_fixture("pagerduty_webhook.json"))
    timeline = pagerduty.parse_log_entries(load_fixture("pagerduty_log_entries.json"))
    thread = slack.parse_replies(load_fixture("slack_replies.json"))
    incident = servicenow.parse_table_response(
        load_fixture("servicenow_incident.json"), kind="incident"
    )[0]
    problem = servicenow.parse_table_response(
        load_fixture("servicenow_problem.json"), kind="problem"
    )[0]
    case = salesforce.parse_case(load_fixture("salesforce_case.json"))
    issue = pylon.parse_issue(load_fixture("pylon_issue.json"))
    account = pylon.parse_account(load_fixture("pylon_account.json"))

    matches = [row for row in recurrence() if row["match"]]
    actions = propose_actions(matches)
    engineering = actions["ENG"]
    follow_up_title = engineering["title"]
    from integrations.model import FollowUp
    follow_up = FollowUp(
        team=engineering["team"],
        title=follow_up_title,
        criterion=engineering["criterion"],
        sources=engineering["sources"],
        owner=engineering["owner"],
        lesson_id="ENG",
    )

    gate = WriteGate(dry_run=True)
    jira_proposal = gate.propose(
        "jira-eng-1042",
        "jira",
        "create_issue",
        "Create the Engineering action item from the verified discard lesson.",
        jira.create_request(follow_up, project_key="LEARN"),
    )
    slack_proposal = gate.propose(
        "slack-lesson-1042",
        "slack",
        "chat.postMessage",
        "Post the lesson summary back to the incident thread.",
        slack.post_request(
            thread.links["channel"],
            thread.links["thread_ts"],
            f"{CASE_ID}: lesson proposed for {follow_up.team}. {follow_up.title}",
        ),
    )
    note = (
        f"Learning record {CASE_ID} linked problem {problem.external_id}. "
        f"Follow-up '{follow_up.title}' is proposed, not assigned, until the reviewer approves the plan."
    )
    snow_proposal = gate.propose(
        "snow-note-1042",
        "servicenow",
        "patch_incident",
        "Add an internal work note on the incident. Customer-visible comments stay out of this write.",
        servicenow.work_note_request(incident, note),
    )

    steps = [
        _step("pagerduty", "Inbound page", page, detail=f"{len(timeline)} timeline entries"),
        _step("slack", "Incident channel thread", thread, detail=f"{len(thread.links['messages'])} messages"),
        _step("servicenow", "Incident", incident),
        _step("servicenow", "Problem record", problem),
        _step("salesforce", "Service Cloud case", case),
        _step("pylon", "Support issue", issue, detail=account["name"]),
        {
            "tool": "harness",
            "label": "Lesson for Engineering",
            "direction": "internal",
            "external_id": "ENG",
            "title": follow_up.title,
            "status": "proposed",
            "sample": True,
            "detail": f"{len(matches)} prior confirmed discards matched before routing.",
        },
    ]
    return {
        "sample": True,
        "case_id": CASE_ID,
        "summary": (
            "A fictional draft-discard escalation replayed from labeled sample payloads. "
            "No request is sent to PagerDuty, Slack, ServiceNow, Salesforce, Pylon, or Jira."
        ),
        "steps": steps,
        "timeline": timeline,
        "proposals": [item.as_dict() for item in (jira_proposal, slack_proposal, snow_proposal)],
        "dry_run": True,
        "approval_required": True,
    }


def _step(tool, label, signal, detail=""):
    return {
        "tool": tool,
        "label": label,
        "direction": "in",
        "external_id": signal.external_id,
        "title": signal.title,
        "status": signal.status,
        "raw_status": signal.raw_status,
        "sample": signal.sample,
        "detail": detail,
    }
