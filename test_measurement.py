import unittest

from harness import Harness
from measurement import (
    OWNERS, RECORD_FIELDS, SYSTEMS, assemble_inputs, build_scorecard, hours_between,
    lesson_lifecycle, reading_date, routed_on_time, summarize,
)


def metric(scorecard, metric_id):
    for group in scorecard["groups"]:
        for row in group["metrics"]:
            if row["id"] == metric_id:
                return row
    raise AssertionError(metric_id)


class MeasurementMathTests(unittest.TestCase):
    def test_routing_window_includes_the_fifth_day(self):
        self.assertTrue(routed_on_time({"opened_on": "2026-01-01", "routed_on": "2026-01-06"}, 5))
        self.assertFalse(routed_on_time({"opened_on": "2026-01-01", "routed_on": "2026-01-07"}, 5))
        self.assertFalse(routed_on_time({"opened_on": "2026-01-01"}, 5))

    def test_practice_case_update_is_four_hours(self):
        self.assertEqual(hours_between("2026-11-04T16:55:00Z", "2026-11-04T20:55:00Z"), 4)

    def test_history_ids_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            assemble_inputs([{"id": "EX-11"}])


class ScorecardTests(unittest.TestCase):
    def walk(self, *steps):
        harness = Harness()
        for command in (
            "reveal", "confirm_priority", "approve", "load_resolution", "confirm_recovery",
            "learn", "approve_plan", "load_proof", "return_proof", "resubmit_proof",
        ):
            harness.apply(command, harness.revision)
        for action_id in ("ENG", "PROD", "SUP", "CS", "DOC", "OPS", "EXEC"):
            harness.apply("verify", harness.revision, action_id)
        harness.apply("close", harness.revision)
        for command, action_id in steps:
            harness.apply(command, harness.revision, action_id)
        return harness

    def test_routing_is_earned_and_exported(self):
        harness = Harness()
        for command in ("reveal", "confirm_priority", "approve", "load_resolution", "confirm_recovery", "learn"):
            harness.apply(command, harness.revision)
        proposed = {lesson["id"]: lesson for lesson in harness.view()["lessons"]}
        self.assertEqual(proposed["ESC-1042-ENG"]["lifecycle"], "created")
        self.assertIsNone(proposed["ESC-1042-ENG"]["routed_on"])
        self.assertIsNone(proposed["ESC-1042-ENG"]["accepted_on"])
        self.assertIsNone(proposed["ESC-1042-ENG"]["shipped_on"])
        self.assertIsNone(harness.view()["scorecard"])
        harness.apply("approve_plan", harness.revision)
        routed = {lesson["id"]: lesson for lesson in harness.view()["lessons"]}
        self.assertEqual(routed["ESC-1042-ENG"]["lifecycle"], "accepted")
        self.assertEqual(routed["ESC-1042-ENG"]["routed_on"], "2026-11-06")
        self.assertEqual(routed["ESC-1042-ENG"]["accepted_on"], "2026-11-07")
        self.assertEqual(routed["ESC-1042-ENG"]["accepted_link"], "example:jira/ENG-1042")
        self.assertIsNone(routed["ESC-1042-ENG"]["verified_on"])
        self.assertIsNone(routed["ESC-1042-ENG"]["implemented_on"])
        self.assertIsNone(routed["ESC-1042-ENG"]["shipped_on"])
        self.assertNotIn("example_shipped_on", harness.view()["actions"][0])
        self.assertNotIn("example_accepted_link", harness.view()["actions"][0])
        engineering = next(row for row in harness.view()["actions"] if row["id"] == "ENG")
        self.assertEqual(engineering["owner_type"], "Engineering")
        self.assertEqual(engineering["action_type"], "defect")
        self.assertNotIn("CS", {lesson["id"].rsplit("-", 1)[-1] for lesson in harness.view()["lessons"]})

    def test_closed_case_matches_the_example_quarter(self):
        view = self.walk().view()
        scorecard = view["scorecard"]
        lessons = {lesson["id"]: lesson for lesson in view["lessons"]}
        engineering = lessons["ESC-1042-ENG"]
        self.assertEqual(engineering["owner_type"], "Engineering")
        self.assertEqual(engineering["action_type"], "defect")
        self.assertEqual(engineering["recurrence"], "none")
        self.assertEqual(engineering["lifecycle"], "verified")
        self.assertFalse(engineering["held"])
        self.assertEqual(engineering["routed_on"], "2026-11-06")
        self.assertEqual(engineering["accepted_on"], "2026-11-07")
        self.assertEqual(engineering["accepted_link"], "example:jira/ENG-1042")
        self.assertTrue(engineering["accepted_link"].startswith("example:"))
        self.assertEqual(engineering["implemented_on"], "2026-11-18")
        self.assertEqual(engineering["verified_on"], "2026-11-18")
        self.assertEqual(engineering["shipped_on"], "2026-11-18")
        self.assertTrue(all(lesson["cited_ok"] for lesson in lessons.values()))
        self.assertTrue(all(lesson["example"] for lesson in lessons.values()))
        self.assertEqual(
            {lesson["owner_type"] for lesson in lessons.values()},
            {"Engineering", "Support", "Product management"},
        )
        self.assertEqual(metric(scorecard, "lessons_closed")["current"], "11")
        self.assertEqual(metric(scorecard, "lessons_closed")["baseline"], "8 per quarter")
        self.assertEqual(metric(scorecard, "shipped_changes")["current"], "2")
        self.assertEqual(metric(scorecard, "training_published")["current"], "2")
        self.assertEqual(metric(scorecard, "tools_adopted")["current"], "1")
        self.assertEqual(metric(scorecard, "repeats")["current"], "0")
        self.assertTrue(metric(scorecard, "repeats")["held"])
        self.assertEqual(metric(scorecard, "first_update")["current"], "4 hours")
        self.assertEqual(metric(scorecard, "first_update")["current_caption"], "This case")
        self.assertTrue(metric(scorecard, "first_update")["held"])
        template = metric(scorecard, "escalation_rate")["areas"][0]
        self.assertEqual(template["name"], "Template authoring")
        self.assertEqual(template["baseline_value"], 1.5)
        self.assertEqual(template["current_value"], 1)
        self.assertTrue(scorecard["repeat_held"])
        self.assertEqual(scorecard["baseline"]["quarters"][0]["template_rate"], "2 per 100 draft edits")
        self.assertLess(metric(scorecard, "routed_on_time")["baseline_value"], 1)
        self.assertEqual(metric(scorecard, "routed_on_time")["current"], "100%")
        evaluation = metric(scorecard, "eval_score")
        self.assertTrue(evaluation["example_only"])
        self.assertIn("does not run a model", evaluation["how"])
        self.assertTrue(metric(scorecard, "human_approval")["held"])
        self.assertTrue(metric(scorecard, "citations")["held"])
        self.assertIn("not a personal track record", scorecard["disclaimer"])
        self.assertTrue(scorecard["example"])
        fresh = summarize(scorecard["inputs"])
        self.assertEqual(fresh["repeat_count"], scorecard["repeat_count"])
        for metric_id, raw in fresh["metrics"].items():
            if metric_id == "escalation_rate":
                published = {area["name"]: area["current_value"] for area in metric(scorecard, metric_id)["areas"]}
                rebuilt = {area["name"]: area["current_value"] for area in raw["areas"]}
                self.assertEqual(published, rebuilt)
            else:
                self.assertEqual(metric(scorecard, metric_id)["current_value"], raw["current_value"])
                self.assertEqual(metric(scorecard, metric_id)["held"], raw["held"])
        blob = str(scorecard).lower()
        for banned in ("datadog", "pagerduty", "itil"):
            self.assertNotIn(banned, blob)

    def test_repeat_stays_counted_after_the_lesson_is_verified_again(self):
        harness = self.walk(("load_signal", "a"), ("decide_signal", "separate"))
        self.assertTrue(harness.view()["scorecard"]["repeat_held"])
        self.assertEqual(metric(harness.view()["scorecard"], "escalation_rate")["areas"][0]["current_value"], 1)
        harness.apply("load_signal", harness.revision, "b")
        harness.apply("decide_signal", harness.revision, "repeat")
        opened = {lesson["id"]: lesson for lesson in harness.view()["lessons"]}["ESC-1042-ENG"]
        self.assertEqual(opened["recurrence"], "reopened")
        self.assertEqual(opened["state"], "Needs rework")
        self.assertEqual(opened["lifecycle"], "reopened")
        self.assertFalse(opened["held"])
        self.assertEqual(opened["verified_on"], "2026-11-18")
        self.assertEqual(opened["implemented_on"], "2026-11-18")
        self.assertEqual(opened["shipped_on"], "2026-11-18")
        scorecard = harness.view()["scorecard"]
        self.assertFalse(scorecard["repeat_held"])
        self.assertEqual(scorecard["repeat_count"], 1)
        self.assertEqual(metric(scorecard, "lessons_closed")["current"], "10")
        self.assertEqual(metric(scorecard, "shipped_changes")["current"], "2")
        self.assertEqual(metric(scorecard, "escalation_rate")["areas"][0]["current_value"], 1.25)
        self.assertIn("reopened", scorecard["status_note"])
        engineering = next(row for row in scorecard["teams"]["rows"] if row["owner_type"] == "Engineering")
        self.assertEqual(engineering["repeats"]["current"], "1")
        self.assertFalse(engineering["repeats"]["held"])
        self.assertLess(engineering["verified_pct"]["current_value"], 1)
        harness.apply("resubmit_proof", harness.revision)
        harness.apply("verify", harness.revision, "ENG")
        harness.apply("verify", harness.revision, "EXEC")
        harness.apply("close", harness.revision)
        closed = {lesson["id"]: lesson for lesson in harness.view()["lessons"]}["ESC-1042-ENG"]
        self.assertEqual(closed["state"], "Verified")
        self.assertEqual(closed["recurrence"], "reopened")
        self.assertEqual(closed["lifecycle"], "verified")
        self.assertFalse(closed["held"])
        self.assertEqual(closed["verified_on"], "2026-12-16")
        self.assertEqual(closed["implemented_on"], "2026-12-16")
        self.assertEqual(closed["shipped_on"], "2026-12-16")
        self.assertEqual(closed["first_verified_on"], "2026-11-18")
        self.assertFalse(harness.view()["scorecard"]["repeat_held"])
        self.assertEqual(metric(harness.view()["scorecard"], "lessons_closed")["current"], "11")

    def test_a_missed_citation_or_approval_does_not_hold(self):
        live = self.walk().view()["lessons"]
        uncited = [{**lesson, "cited_ok": False} if lesson["id"].endswith("ENG") else lesson for lesson in live]
        self.assertFalse(metric(build_scorecard(uncited), "citations")["held"])
        unapproved = [{**lesson, "human_approved": False} if lesson["id"].endswith("SUP") else lesson for lesson in live]
        self.assertFalse(metric(build_scorecard(unapproved), "human_approval")["held"])

    def test_team_lifecycle_and_systems_mapping(self):
        view = self.walk().view()
        scorecard = view["scorecard"]
        self.assertEqual([name for name, _blurb in OWNERS], [row["owner_type"] for row in scorecard["teams"]["rows"]])
        self.assertEqual(scorecard["lifecycle"]["hold_days"], 30)
        self.assertEqual(scorecard["lifecycle"]["stages"], ["created", "routed", "accepted", "implemented", "verified", "held"])
        support = next(row for row in scorecard["teams"]["rows"] if row["owner_type"] == "Support")
        engineering = next(row for row in scorecard["teams"]["rows"] if row["owner_type"] == "Engineering")
        self.assertLess(support["acceptance_rate"]["baseline_value"], 1)
        self.assertEqual(support["acceptance_rate"]["current_value"], 1)
        self.assertTrue(support["acceptance_rate"]["held"])
        self.assertEqual(engineering["repeats"]["current_value"], 0)
        self.assertTrue(engineering["repeats"]["held"])
        fresh = summarize(scorecard["inputs"])
        for published, raw in zip(scorecard["teams"]["rows"], fresh["teams"]):
            self.assertEqual(published["owner_type"], raw["owner_type"])
            self.assertEqual(published["acceptance_rate"]["current_value"], raw["acceptance_rate"]["current_value"])
            self.assertEqual(published["repeats"]["held"], raw["repeats"]["held"])
        as_of = reading_date(scorecard["inputs"]["lessons"], scorecard["inputs"]["as_of"])
        early = next(lesson for lesson in scorecard["inputs"]["lessons"] if lesson["id"] == "EX-11")
        recent = next(lesson for lesson in scorecard["inputs"]["lessons"] if lesson["id"] == "EX-43")
        self.assertEqual(lesson_lifecycle(early, as_of, 30), "held")
        self.assertEqual(lesson_lifecycle(recent, as_of, 30), "verified")
        mapped = {row["id"] for row in scorecard["systems"]["rows"]}
        self.assertTrue(set(RECORD_FIELDS) <= mapped)
        self.assertEqual([team["name"] for team in SYSTEMS["owner_teams"]], [name for name, _blurb in OWNERS])
        self.assertIn("not a map of any real company", scorecard["systems"]["disclaimer"])
        self.assertEqual(
            {row["system"] for row in scorecard["systems"]["rows"]},
            {"Zendesk", "Jira", "Salesforce", "Statuspage", "Spreadsheet or BI tool"},
        )
        for record in SYSTEMS["records"].values():
            self.assertIn("system", record)
            self.assertIn("fields", record)

    def test_account_teams_are_example_quarter_lessons(self):
        scorecard = self.walk().view()["scorecard"]
        owners = {owner["owner_type"]: owner for owner in scorecard["owners"]}
        live = {lesson["owner_type"] for lesson in scorecard["inputs"]["lessons"] if lesson["scope"] == "practice_case"}
        self.assertNotIn("Customer Success", live)
        self.assertNotIn("Technical Account Managers (including Strategic TAMs)", live)
        success = owners["Customer Success"]
        managers = owners["Technical Account Managers (including Strategic TAMs)"]
        self.assertIn("CSM lead", success["blurb"])
        self.assertIn("TAM manager", managers["blurb"])
        self.assertIn("renewal-risk", success["blurb"])
        self.assertIn("QBR", managers["blurb"])
        for owner in (success, managers):
            self.assertTrue(owner["lessons"])
            self.assertTrue(all(lesson["scope_label"] == "Example quarter" for lesson in owner["lessons"]))
        mapped = {team["name"]: team for team in SYSTEMS["owner_teams"]}
        self.assertEqual(mapped["Customer Success"]["accepts_in"], "Salesforce")
        self.assertEqual(mapped["Technical Account Managers (including Strategic TAMs)"]["accepts_in"], "Salesforce")
        self.assertIn("success_plan", {row["id"] for row in scorecard["systems"]["rows"]})

    def test_launch_picker_case_is_not_a_draft_discard_lesson(self):
        harness = Harness()
        harness.apply("start_picker", harness.revision)
        view = harness.view()
        self.assertEqual(view["lessons"], [])
        self.assertIsNone(view["scorecard"])


if __name__ == "__main__":
    unittest.main()
