import unittest
from unittest.mock import patch

from harness import Harness, ReviewError, propose_actions
from itil import ItilFailure, priority_from_matrix


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
        records = self.runbook.view()["records"]
        self.assertEqual(records["incident"]["state"], "closed")
        self.assertEqual(records["problem"]["state"], "open")
        self.assertEqual(records["problem"]["phase"], "problem_identification")
        self.assertIsNone(records["known_error"])
        with self.assertRaises(ReviewError):
            self.apply("close")

    def test_priority_comes_from_the_example_matrix(self):
        view = self.apply("reveal")
        triage = view["triage"]["triage"]
        self.assertEqual(priority_from_matrix("2", "1"), "P2")
        self.assertEqual(triage["impact"], "2")
        self.assertEqual(triage["urgency"], "1")
        self.assertEqual(triage["priority"], "P2")
        self.assertIsNone(triage["failure_class"])
        with self.assertRaises(ItilFailure) as caught:
            priority_from_matrix("9", "1")
        self.assertEqual(caught.exception.failure_class, "PriorityMatrixMiss")

    def test_known_error_and_change_effectiveness(self):
        self.recover()
        learned = self.apply("learn")
        self.assertEqual(learned["records"]["problem"]["phase"], "problem_control")
        self.assertEqual(learned["records"]["known_error"]["id"], "KE-1042")
        self.assertEqual(learned["records"]["known_error_database"][0]["id"], "KEDB-1042")
        self.assertTrue(all(row["state"] == "proposed" for row in learned["changes"]))
        self.assertIn("functional", {row["escalation"] for row in learned["handoffs"]})
        self.assertIn("hierarchical", {row["escalation"] for row in learned["handoffs"]})
        self.apply("approve_plan")
        self.apply("load_proof")
        self.runbook.actions["SUP"]["change_state"] = "proposed"
        with self.assertRaises(ReviewError) as caught:
            self.apply("verify", "SUP")
        self.assertEqual(caught.exception.failure_class, "EffectivenessUnconfirmed")
        self.assertIn("EffectivenessUnconfirmed", str(caught.exception))

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
        with self.assertRaisesRegex(ReviewError, "Engineering proof is incomplete"):
            self.apply("verify", "ENG")
        self.apply("return_proof")
        self.apply("resubmit_proof")
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
