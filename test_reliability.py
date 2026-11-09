"""Deterministic failure and recovery cases for the local harness.

These tests exercise the shipped HTTP gates and evidence checks. They do not
call a model, and they do not represent production incidents.
"""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from collections import OrderedDict
from http.server import ThreadingHTTPServer

import incident_triage
from serve import Handler

MINIMAL_INCIDENT = {
    "incident_id": "ESC-FIXTURE",
    "symptom": "template missing",
    "impact": "one rollout blocked",
    "timeline": ["reported"],
    "evidence": [{
        "id": "E1",
        "source": "fixture",
        "observation": "No worker, storage, or capacity signal is present.",
    }],
}


class ReliabilityTests(unittest.TestCase):
    timings = []

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.sessions = OrderedDict()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        total = sum(row[1] for row in cls.timings)
        print(f"\nreliability timings: {len(cls.timings)} cases, {total:.4f}s wall clock inside tests")
        for name, seconds in cls.timings:
            print(f"  {seconds:.4f}s  {name}")

    def setUp(self):
        self._started = time.perf_counter()

    def tearDown(self):
        self.timings.append((self.id().rsplit(".", 1)[-1], time.perf_counter() - self._started))

    def request(self, method, body=None, *, cookie=None, origin=True, content_type="application/json"):
        headers = {}
        if origin:
            headers["Origin"] = self.base
        if cookie:
            headers["Cookie"] = f"learning_demo={cookie}"
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.base + "/api/session", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode()), response.headers.get("Set-Cookie")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode()
            return exc.code, json.loads(payload) if payload else {}, None

    def open_case(self):
        status, view, cookie = self.request("GET", origin=False)
        self.assertEqual(status, 200)
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        return token, view

    def post(self, token, action, revision, action_id=None, **kwargs):
        body = {"action": action, "revision": revision, "action_id": action_id}
        return self.request("POST", body, cookie=token, **kwargs)

    def test_malformed_requests_stop_before_mutation(self):
        token, view = self.open_case()
        cases = [
            (b"", "text/plain"),
            (b"{}", "text/plain"),
            (b"not-json", "application/json"),
            (json.dumps({"action": 1, "revision": 0}).encode(), "application/json"),
            (json.dumps({"action": "reveal", "revision": "0"}).encode(), "application/json"),
            (b"x" * 1100, "application/json"),
        ]
        for body, content_type in cases:
            with self.subTest(body=body[:24]):
                status, payload, _ = self.request(
                    "POST", body, cookie=token, content_type=content_type
                )
                self.assertEqual(status, 400)
                self.assertEqual(payload["error"], "Invalid review request.")
        status, again, _ = self.request("GET", cookie=token, origin=False)
        self.assertEqual(status, 200)
        self.assertEqual(again["revision"], view["revision"])
        self.assertEqual(again["audit"], [])

    def test_rejected_origin_and_missing_session_do_not_apply(self):
        status, payload, _ = self.request("POST", {"action": "reveal", "revision": 0}, origin=False)
        self.assertEqual(status, 403)
        self.assertIn("command center", payload["error"])
        status, payload, _ = self.request("POST", {"action": "reveal", "revision": 0})
        self.assertEqual(status, 409)
        self.assertIn("expired", payload["error"])

    def test_unknown_and_stale_actions_leave_revision_unchanged(self):
        token, view = self.open_case()
        status, payload, _ = self.post(token, "not-a-command", view["revision"])
        self.assertEqual(status, 409)
        self.assertIn("Unknown", payload["error"])
        status, payload, _ = self.post(token, "reveal", view["revision"] + 9)
        self.assertEqual(status, 409)
        self.assertIn("Reload", payload["error"])
        status, current, _ = self.request("GET", cookie=token, origin=False)
        self.assertEqual(current["revision"], view["revision"])
        status, advanced, _ = self.post(token, "reveal", current["revision"])
        self.assertEqual(status, 200)
        self.assertEqual(advanced["revision"], view["revision"] + 1)
        self.assertEqual(advanced["stage"], "Coordinate")

    def test_unsupported_claim_blocks_then_supported_wording_recovers(self):
        token, view = self.open_case()
        for action in ("reveal", "confirm_priority", "inject_restore"):
            status, view, _ = self.post(token, action, view["revision"])
            self.assertEqual(status, 200)
        status, blocked, _ = self.post(token, "approve", view["revision"])
        self.assertEqual(status, 409)
        self.assertIn("draft validation", blocked["error"])
        status, view, _ = self.request("GET", cookie=token, origin=False)
        self.assertIsNone(view["triage"]["preview"])
        status, view, _ = self.post(token, "original", view["revision"])
        self.assertEqual(status, 200)
        status, view, _ = self.post(token, "approve", view["revision"])
        self.assertEqual(status, 200)
        self.assertTrue(view["triage"]["preview"])

    def test_missing_recovery_evidence_stops_before_learning(self):
        token, view = self.open_case()
        for action in ("reveal", "confirm_priority", "approve"):
            status, view, _ = self.post(token, action, view["revision"])
            self.assertEqual(status, 200)
        status, payload, _ = self.post(token, "confirm_recovery", view["revision"])
        self.assertEqual(status, 409)
        self.assertIn("Recovery requires", payload["error"])
        status, view, _ = self.request("GET", cookie=token, origin=False)
        self.assertEqual(view["stage"], "Coordinate")
        self.assertFalse(view["recovered"])
        self.assertEqual(view["actions"], [])

    def test_malformed_incident_records_fail_closed(self):
        with self.assertRaises(ValueError):
            incident_triage.validate_incident({"incident_id": "x"})
        broken = json.loads(json.dumps(MINIMAL_INCIDENT))
        broken["evidence"].append(dict(broken["evidence"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate evidence id"):
            incident_triage.validate_incident(broken)
        broken["evidence"] = [{"id": "E9", "source": "", "observation": "blank"}]
        with self.assertRaisesRegex(ValueError, "nonempty"):
            incident_triage.validate_incident(broken)

    def test_triage_records_missing_evidence_and_does_not_confirm_cause(self):
        quiet = json.loads(json.dumps(MINIMAL_INCIDENT))
        quiet["evidence"][0]["observation"] = "The draft is gone."
        result = incident_triage.triage(quiet)
        self.assertIsNone(result["confirmed_root_cause"])
        self.assertEqual(result["action_mode"], "simulation_only")
        self.assertTrue(all(row["status"] == "unverified" for row in result["hypotheses"]))
        self.assertTrue(all(row["missing_evidence"] for row in result["hypotheses"]))
        self.assertIn("have not confirmed a root cause", result["customer_update"])

        # Keyword search treats a negated mention as support and clears missing_evidence.
        # The helper still refuses to confirm a cause. This locks the current limitation.
        negated = incident_triage.triage(MINIMAL_INCIDENT)
        self.assertIsNone(negated["confirmed_root_cause"])
        self.assertIn("have not confirmed a root cause", negated["customer_update"])
        self.assertTrue(any(row["supporting_evidence_ids"] and not row["missing_evidence"]
                            for row in negated["hypotheses"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
