"""Replay one fictional escalation across the sample tool payloads.

The order is a page, an incident-channel thread, the customer case in
ServiceNow, Salesforce, and Pylon, then the harness lesson, then proposed
writes. Nothing in this function contacts a network.
"""

from integrations.base import FollowUp, Lesson, approve
from integrations.jira import JiraAdapter
from integrations.pagerduty import PagerDutyAdapter
from integrations.pylon import PylonAdapter
from integrations.salesforce import SalesforceAdapter
from integrations.servicenow import ServiceNowAdapter
from integrations.slack import SlackAdapter

# Product, Engineering, and Customer Success are the follow-ups this replay
# turns into proposed Jira tasks. The harness catalog still owns the rest.
ACTION_IDS = ("ENG", "PROD", "CS")


def lesson_from_actions(actions):
    chosen = [row for row in actions if row["id"] in ACTION_IDS]
    return Lesson(
        case_id="ESC-1042",
        title="Protect irreversible draft discard",
        cause="The draft was discarded. A test copy showed the prompt omitted the draft name and the permanent loss of configuration.",
        actions=tuple(
            FollowUp(
                id=row["id"],
                team=row["team"],
                title=row["title"],
                owner=row["owner"],
                criterion=row["criterion"],
            )
            for row in chosen
        ),
    )


def cross_tool_replay(actions):
    pagerduty = PagerDutyAdapter().load_sample()
    slack_signal = SlackAdapter().load_sample()
    servicenow = ServiceNowAdapter().load_sample()
    salesforce = SalesforceAdapter().load_sample()
    pylon = PylonAdapter().load_sample()
    lesson = lesson_from_actions(actions)
    jira = JiraAdapter()
    slack = SlackAdapter()
    snow = ServiceNowAdapter()
    proposals = jira.propose_all(lesson, project_key="LEARN")
    proposals.append(slack.propose_status(
        lesson,
        channel=slack_signal["links"]["channel"],
        thread_ts=slack_signal["links"]["thread_ts"],
    ))
    proposals.append(snow.propose_work_note(lesson, servicenow["incident"]["external_id"]))
    # Show the gate: the first Jira task is approved and dry-run. It is not sent.
    approved = approve(proposals[0])
    dry = jira.execute(approved, dry_run=True)
    steps = [
        {"step": 1, "tool": "pagerduty", "direction": "in", "label": "Page", "detail": pagerduty},
        {"step": 2, "tool": "slack", "direction": "in", "label": "Incident thread", "detail": slack_signal},
        {"step": 3, "tool": "servicenow", "direction": "in", "label": "Incident and problem", "detail": servicenow},
        {"step": 4, "tool": "salesforce", "direction": "in", "label": "Service Cloud case", "detail": salesforce},
        {"step": 5, "tool": "pylon", "direction": "in", "label": "Pylon issue and account", "detail": pylon},
        {"step": 6, "tool": "harness", "direction": "internal", "label": "Lesson", "detail": lesson.as_dict()},
        {
            "step": 7,
            "tool": "outbound",
            "direction": "out",
            "label": "Proposed writes",
            "detail": {
                "proposals": [item.as_dict() for item in proposals],
                "approved_dry_run": dry,
            },
        },
    ]
    return {
        "sample": True,
        "case_id": "ESC-1042",
        "summary": "Sample replay. No live ServiceNow, Pylon, Salesforce, Jira, PagerDuty, or Slack account is contacted.",
        "steps": steps,
    }
