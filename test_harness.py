import unittest
from unittest.mock import patch

from harness import Harness, ReviewError, propose_actions


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.runbook = Harness()

    def apply(self, command, action_id=None):
        self.runbook.apply(command, self.runbook.revision, action_id)
        return self.runbook.view()

    def coordinate(self):
        self.apply("reveal")
        self.apply("confirm_priority")

    def recover(self):
        self.coordinate()
        self.apply("approve")
        self.apply("load_resolution")
        self.apply("confirm_recovery")

    def test_unknown_cause_cannot_trigger_learning(self):
        for action in ("confirm_recovery", "learn", "approve_plan", "close"):
            with self.subTest(action=action), self.assertRaises(ReviewError):
                self.apply(action)
        self.assertFalse(self.runbook.audit)

    def test_unsupported_claim_and_revised_preview(self):
        self.coordinate()
        self.apply("inject_restore")
        with self.assertRaises(ReviewError):
            self.apply("approve")
        self.apply("original")
        self.assertTrue(self.apply("approve")["triage"]["preview"])
        self.apply("load_resolution")
        self.assertIsNone(self.apply("revise")["triage"]["preview"])
        with self.assertRaises(ReviewError):
            self.apply("confirm_recovery")
        self.apply("approve")
        self.assertTrue(self.apply("confirm_recovery")["recovered"])

    def test_recovery_and_learning_have_separate_closure(self):
        self.recover()
        self.assertEqual(self.runbook.stage, "Learn")
        with self.assertRaises(ReviewError):
            self.apply("close")

    def test_recurrence_excludes_unverified_near_miss(self):
        self.recover()
        view = self.apply("learn")
        self.assertEqual([row["source"] for row in view["history"] if row["match"]], ["H1", "H2"])
        self.assertEqual(set(self.runbook.actions), {"ENG", "PROD", "SUP", "CS", "DOC", "OPS", "EXEC"})
        self.assertFalse({"PROD", "OPS"} & propose_actions(["H1"]).keys())

    def test_routing_follows_recurrence_result(self):
        self.recover()
        with patch("harness.recurrence", return_value=[]):
            view = self.apply("learn")
        self.assertFalse({"PROD", "OPS"} & {row["id"] for row in view["actions"]})

    def test_team_verification_and_executive_sign_off(self):
        self.recover()
        self.apply("learn")
        with self.assertRaises(ReviewError):
            self.apply("verify", "ENG")
        view = self.apply("approve_plan")
        self.assertNotIn("proof", view["actions"][0])
        with self.assertRaises(ReviewError):
            self.apply("verify", "ENG")
        self.apply("load_proof")
        for command, action_id in (("verify", "EXEC"), ("close", None)):
            with self.assertRaises(ReviewError):
                self.apply(command, action_id)
        for key in ["ENG", "PROD", "SUP", "CS", "DOC", "OPS"]:
            self.apply("verify", key)
        self.apply("verify", "EXEC")
        with self.assertRaises(ReviewError):
            self.apply("verify", "EXEC")
        view = self.apply("close")
        self.assertEqual(view["stage"], "Closed")
        self.assertEqual(view["learning_review"]["interval_days"], 30)
        self.assertEqual([row["state"] for row in view["actions"]], ["Verified"] * 7)

    def test_stale_revision_leaves_the_case_unchanged(self):
        self.apply("reveal")
        with self.assertRaises(ReviewError):
            self.runbook.apply("confirm_priority", 0)
        self.assertFalse(self.runbook.triage.priority_confirmed)
        self.assertEqual(self.runbook.revision, 1)


if __name__ == "__main__":
    unittest.main()
