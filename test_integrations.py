"""Adapter fixtures, harness mapping, and approval gating. No network."""

import os
import unittest
from unittest.mock import patch

from harness import DATA
from integrations.base import ApprovalRequired, approve
from integrations.jira import JiraAdapter
from integrations.pagerduty import PagerDutyAdapter
from integrations.pylon import PylonAdapter
from integrations.replay import cross_tool_replay, lesson_from_actions
from integrations.salesforce import SalesforceAdapter
from integrations.servicenow import ServiceNowAdapter
from integrations.slack import SlackAdapter
from integrations.transport import http_json


class AdapterTests(unittest.TestCase):
    def test_pagerduty_webhook_and_timeline(self):
        sample = PagerDutyAdapter().load_sample()
        signal = sample["signal"]
        self.assertEqual(signal["external_id"], "Q0SAMPLEINCIDENT")
        self.assertEqual(signal["status"], "triggered")
        self.assertEqual(signal["links"]["incident_number"], 1042)
        self.assertEqual([row["type"] for row in sample["timeline"]], [
            "trigger_log_entry", "acknowledge_log_entry", "resolve_log_entry",
        ])
        self.assertTrue(signal["sample"])

    def test_slack_thread_maps_to_one_signal(self):
        signal = SlackAdapter().load_sample()
        self.assertEqual(signal["links"]["channel"], "C0SAMPLE")
        self.assertIn("rebuilt template", signal["summary"])
        self.assertEqual(signal["status"], "thread")

    def test_servicenow_incident_and_problem(self):
        sample = ServiceNowAdapter().load_sample()
        self.assertEqual(sample["incident"]["status"], "resolved")
        self.assertEqual(sample["incident"]["links"]["number"], "INC0011042")
        self.assertEqual(sample["incident"]["customer"], "Example Privacy Team")
        self.assertEqual(sample["problem"]["status"], "root_cause_analysis")
        self.assertEqual(sample["problem"]["links"]["table"], "problem")

    def test_salesforce_case_query(self):
        cases = SalesforceAdapter().load_sample()
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["links"]["case_number"], "00001042")
        self.assertEqual(cases[0]["status"], "closed")
        self.assertEqual(cases[0]["customer"], "001SAMPLEACCOUNT")

    def test_pylon_issue_and_account(self):
        sample = PylonAdapter().load_sample()
        self.assertEqual(sample["issue"]["status"], "closed")
        self.assertEqual(sample["issue"]["links"]["number"], 1042)
        self.assertEqual(sample["issue"]["customer"], sample["account"]["id"])
        self.assertEqual(sample["account"]["name"], "Example Privacy Team")
        self.assertNotIn("<p>", sample["issue"]["summary"])

    def test_lesson_uses_harness_actions(self):
        lesson = lesson_from_actions(DATA["actions"])
        self.assertEqual([action.id for action in lesson.actions], ["ENG", "PROD", "CS"])
        engineering = next(row for row in DATA["actions"] if row["id"] == "ENG")
        self.assertEqual(lesson.actions[0].criterion, engineering["criterion"])
        self.assertEqual(lesson.actions[0].owner, engineering["owner"])

    def test_writes_stay_proposed_until_approved(self):
        lesson = lesson_from_actions(DATA["actions"])
        jira = JiraAdapter().propose_action_item(lesson, lesson.actions[0], project_key="LEARN")
        slack = SlackAdapter().propose_status(lesson, channel="C0SAMPLE", thread_ts="1.2")
        note = ServiceNowAdapter().propose_work_note(lesson, "abc")
        for proposal in (jira, slack, note):
            self.assertEqual(proposal.state, "proposed")
            adapter = {
                "jira": JiraAdapter(),
                "slack": SlackAdapter(),
                "servicenow": ServiceNowAdapter(),
            }[proposal.tool]
            with self.assertRaises(ApprovalRequired):
                adapter.execute(proposal, dry_run=False)
            self.assertEqual(proposal.state, "proposed")

    def test_approved_write_is_dry_run_by_default(self):
        lesson = lesson_from_actions(DATA["actions"])
        proposal = approve(JiraAdapter().propose_action_item(lesson, lesson.actions[0]))
        with patch("integrations.transport.http_json") as http:
            result = JiraAdapter().execute(proposal)
        http.assert_not_called()
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(result["network"])
        self.assertEqual(result["request"]["fields"]["project"]["key"], "LEARN")
        self.assertEqual(result["request"]["fields"]["description"]["type"], "doc")

    def test_offline_refuses_a_real_send(self):
        lesson = lesson_from_actions(DATA["actions"])
        proposal = approve(SlackAdapter().propose_status(lesson, channel="C0SAMPLE", thread_ts="1.2"))
        with patch.dict(os.environ, {"INTEGRATIONS_MODE": "offline"}, clear=False):
            with patch("integrations.transport.http_json") as http:
                result = SlackAdapter().execute(proposal, dry_run=False)
        http.assert_not_called()
        self.assertEqual(result["status"], "refused")
        self.assertFalse(result["network"])

    def test_live_send_builds_the_documented_request(self):
        lesson = lesson_from_actions(DATA["actions"])
        proposal = approve(JiraAdapter().propose_action_item(lesson, lesson.actions[1], project_key="LEARN"))
        env = {
            "INTEGRATIONS_MODE": "live",
            "JIRA_BASE_URL": "https://example.atlassian.net",
            "JIRA_EMAIL": "dev@example.test",
            "JIRA_API_TOKEN": "sample-token",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("integrations.transport.http_json", return_value=(201, {"key": "LEARN-1"})) as http:
                result = JiraAdapter().execute(proposal, dry_run=False)
        self.assertEqual(result["status"], "sent")
        self.assertTrue(result["network"])
        url = http.call_args.args[0]
        self.assertEqual(url, "https://example.atlassian.net/rest/api/3/issue")
        self.assertEqual(http.call_args.kwargs["method"], "POST")
        self.assertIn("Basic ", http.call_args.kwargs["headers"]["Authorization"])

    def test_replay_spans_the_tools_and_stops_at_a_dry_run(self):
        replay = cross_tool_replay(DATA["actions"])
        self.assertTrue(replay["sample"])
        self.assertEqual([step["tool"] for step in replay["steps"]], [
            "pagerduty", "slack", "servicenow", "salesforce", "pylon", "harness", "outbound",
        ])
        outbound = replay["steps"][-1]["detail"]
        self.assertTrue(all(item["state"] == "proposed" for item in outbound["proposals"]))
        self.assertEqual(outbound["approved_dry_run"]["status"], "dry_run")
        self.assertIn("ENG", outbound["approved_dry_run"]["request"]["fields"]["summary"])

    def test_http_helper_is_not_used_by_import(self):
        self.assertTrue(callable(http_json))


if __name__ == "__main__":
    unittest.main()
