"""Adapter fixtures, harness mapping, and approval gating. No network."""

import os
import unittest
from unittest.mock import patch

from integrations.adapters import (
    JiraAdapter,
    PagerDutyAdapter,
    PylonAdapter,
    SalesforceAdapter,
    ServiceNowAdapter,
    SlackAdapter,
    load_fixture,
)
from integrations.gate import WriteGate, live_mode_enabled
from integrations.model import ACKNOWLEDGED, CLOSED, OPEN, RESOLVED, IntegrationError
from integrations.replay import cross_tool_replay


class FixtureMappingTests(unittest.TestCase):
    def test_pagerduty_page_and_timeline(self):
        signal = PagerDutyAdapter().parse_webhook(load_fixture("pagerduty_webhook.json"))
        self.assertTrue(signal.sample)
        self.assertEqual(signal.external_id, "1042")
        self.assertEqual(signal.status, OPEN)
        self.assertEqual(signal.severity, "P2")
        self.assertEqual(signal.links["service"], "Assessment authoring (sample)")
        timeline = PagerDutyAdapter().parse_log_entries(load_fixture("pagerduty_log_entries.json"))
        self.assertEqual([row["type"] for row in timeline], [
            "trigger_log_entry", "acknowledge_log_entry", "annotate_log_entry",
        ])

    def test_slack_thread_and_event(self):
        thread = SlackAdapter().parse_replies(load_fixture("slack_replies.json"))
        self.assertEqual(thread.links["channel"], "C0SAMPLEINC")
        self.assertIn("Learning record stays open", thread.body)
        event = SlackAdapter().parse_event(load_fixture("slack_event.json"))
        self.assertEqual(event.external_id, "C0SAMPLEINC:1743606240.000100")
        self.assertEqual(event.links["event_id"], "Ev0SAMPLE1042")

    def test_servicenow_incident_links_problem(self):
        rows = ServiceNowAdapter().parse_table_response(
            load_fixture("servicenow_incident.json"), kind="incident"
        )
        self.assertEqual(len(rows), 1)
        incident = rows[0]
        self.assertEqual(incident.external_id, "INC0010420")
        self.assertEqual(incident.status, RESOLVED)
        self.assertEqual(incident.links["problem_id"], "04ce72c9c0a8016600b5b7f75ac67b5b")
        self.assertEqual(incident.customer, "samplecaller")
        problem = ServiceNowAdapter().parse_problem(
            load_fixture("servicenow_problem.json")["result"]
        )
        self.assertEqual(problem.kind, "problem")
        self.assertEqual(problem.status, ACKNOWLEDGED)
        self.assertEqual(problem.external_id, "PRB0010420")

    def test_salesforce_case_and_change_event(self):
        case = SalesforceAdapter().parse_case(load_fixture("salesforce_case.json"))
        self.assertEqual(case.external_id, "00010420")
        self.assertEqual(case.status, ACKNOWLEDGED)
        self.assertEqual(case.raw_status, "Escalated")
        self.assertFalse(case.links["is_closed"])
        change = SalesforceAdapter().parse_case(load_fixture("salesforce_case_change.json"))
        self.assertEqual(change.kind, "case_change")
        self.assertEqual(change.links["change_type"], "UPDATE")

    def test_pylon_issue_account_and_string_webhook(self):
        issue = PylonAdapter().parse_issue(load_fixture("pylon_issue.json"))
        self.assertEqual(issue.external_id, "1042")
        self.assertEqual(issue.status, ACKNOWLEDGED)
        self.assertEqual(issue.severity, "high")
        self.assertEqual(issue.links["external_incidents"], ["1042"])
        self.assertNotIn("<p>", issue.body)
        account = PylonAdapter().parse_account(load_fixture("pylon_account.json"))
        self.assertEqual(account["name"], "Example Privacy Team")
        hook = PylonAdapter().parse_webhook(load_fixture("pylon_webhook.json"))
        self.assertEqual(hook.links["tags"], ["escalation", "assessment"])
        self.assertEqual(hook.external_id, "1042")

    def test_jira_webhook_reads_summary(self):
        signal = JiraAdapter().parse_issue_webhook(load_fixture("jira_issue_webhook.json"))
        self.assertEqual(signal.external_id, "LEARN-17")
        self.assertEqual(signal.status, OPEN)
        self.assertIn("CI covers the cancel path", signal.body)

    def test_missing_field_is_rejected(self):
        with self.assertRaises(IntegrationError):
            PagerDutyAdapter().parse_incident({"id": "Q1", "title": "no status"})


class ApprovalGateTests(unittest.TestCase):
    def test_replay_proposes_writes_and_does_not_execute(self):
        self.assertFalse(live_mode_enabled())
        replay = cross_tool_replay()
        self.assertTrue(replay["sample"])
        self.assertEqual(replay["case_id"], "ESC-1042")
        tools = [step["tool"] for step in replay["steps"]]
        self.assertEqual(tools, [
            "pagerduty", "slack", "servicenow", "servicenow", "salesforce", "pylon", "harness",
        ])
        self.assertIn("prior confirmed discards", replay["steps"][-1]["detail"])
        self.assertEqual(len(replay["timeline"]), 3)
        ids = [item["proposal_id"] for item in replay["proposals"]]
        self.assertEqual(ids, ["jira-eng-1042", "slack-lesson-1042", "snow-note-1042"])
        for proposal in replay["proposals"]:
            self.assertEqual(proposal["status"], "proposed")
            self.assertIsNone(proposal["receipt"])
        jira = replay["proposals"][0]["request"]["body"]["fields"]
        self.assertEqual(jira["project"]["key"], "LEARN")
        self.assertEqual(jira["issuetype"]["name"], "Task")
        self.assertEqual(jira["description"]["type"], "doc")
        self.assertIn("Protect the draft discard path", jira["summary"])

    def test_execute_requires_approval_then_stays_dry_run(self):
        gate = WriteGate(dry_run=True)
        request = SlackAdapter().post_request("C0SAMPLEINC", "1743606240.000100", "Lesson summary")
        gate.propose("slack-1", "slack", "chat.postMessage", "Post the lesson.", request)
        calls = []
        with self.assertRaises(IntegrationError):
            gate.execute("slack-1", transport=calls.append)
        gate.approve("slack-1", "Escalation manager")
        proposal = gate.execute("slack-1", transport=calls.append)
        self.assertEqual(calls, [])
        self.assertEqual(proposal.status, "dry_run")
        self.assertFalse(proposal.receipt["executed"])
        self.assertEqual(proposal.receipt["request"]["body"]["channel"], "C0SAMPLEINC")

    def test_rejected_proposal_cannot_execute(self):
        gate = WriteGate(dry_run=False)
        gate.propose("snow-1", "servicenow", "patch_incident", "Note", {"method": "PATCH", "body": {"work_notes": "x"}})
        gate.reject("snow-1", "Escalation manager")
        with self.assertRaises(IntegrationError):
            gate.execute("snow-1", transport=lambda request: request)

    def test_live_execute_uses_transport_only_when_enabled(self):
        request = {"method": "POST", "url": "https://example.atlassian.net/rest/api/3/issue", "body": {"fields": {}}}
        gate = WriteGate(dry_run=False)
        gate.propose("jira-1", "jira", "create_issue", "Create the action item.", request)
        gate.approve("jira-1", "Assessment engineering lead")
        with patch.dict(os.environ, {"ELH_INTEGRATIONS_MODE": ""}, clear=False):
            with self.assertRaises(IntegrationError):
                gate.execute("jira-1", transport=lambda payload: {"key": "LEARN-17"})
        with patch.dict(os.environ, {"ELH_INTEGRATIONS_MODE": "live"}):
            proposal = gate.execute("jira-1", transport=lambda payload: {"id": "99291", "key": "LEARN-17"})
        self.assertEqual(proposal.status, "executed")
        self.assertEqual(proposal.receipt["response"]["key"], "LEARN-17")

    def test_live_pull_refuses_without_credentials_and_does_not_require_network(self):
        env = {
            "SERVICENOW_INSTANCE": "",
            "SERVICENOW_TOKEN": "",
            "PYLON_API_TOKEN": "",
            "SALESFORCE_INSTANCE_URL": "",
            "SALESFORCE_ACCESS_TOKEN": "",
            "PAGERDUTY_API_TOKEN": "",
            "SLACK_BOT_TOKEN": "",
            "JIRA_BASE_URL": "",
            "JIRA_EMAIL": "",
            "JIRA_API_TOKEN": "",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(IntegrationError):
                ServiceNowAdapter().pull_live("incident", "abc", lambda request: {})
            with self.assertRaises(IntegrationError):
                PylonAdapter().pull_live("iss_sample_1042", lambda request: {})
            with self.assertRaises(IntegrationError):
                SalesforceAdapter().pull_live("500SAMPLE", lambda request: {})
            with self.assertRaises(IntegrationError):
                PagerDutyAdapter().pull_live("Q1", lambda request: {})
            with self.assertRaises(IntegrationError):
                SlackAdapter().pull_live("C0", "1.0", lambda request: {})
            with self.assertRaises(IntegrationError):
                JiraAdapter().pull_live("LEARN-17", lambda request: {})

    def test_live_pull_parses_transport_response_without_calling_out(self):
        seen = []

        def transport(request):
            seen.append(request["url"])
            self.assertTrue(request["headers"]["Authorization"].startswith("Bearer "))
            self.assertNotIn("super-secret-token", request["url"])
            return load_fixture("pylon_issue.json")

        with patch.dict(os.environ, {"PYLON_API_TOKEN": "super-secret-token"}):
            signal = PylonAdapter().pull_live("iss_sample_1042", transport)
        self.assertEqual(seen, ["https://api.usepylon.com/issues/iss_sample_1042"])
        self.assertFalse(signal.sample)
        self.assertEqual(signal.external_id, "1042")


if __name__ == "__main__":
    unittest.main()
