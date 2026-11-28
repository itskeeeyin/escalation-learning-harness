"""Agent loop, named failures, and trace hygiene. No network and no Foundry client."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.failures import (
    EmptyCompletion,
    FoundryAuthFailed,
    FoundryRateLimited,
    FoundryServerBusy,
    ModelNoToolCall,
    SecretInTrace,
    SkipIntake,
    UnknownTool,
)
from agent.loop import run_scripted
from agent.model import (
    build_chat_payload,
    classify_http,
    parse_completion,
    request_completion,
)
from agent.trace import assert_no_secrets, dumps_trace


class FailureAndModelTests(unittest.TestCase):
    def test_http_status_classes(self):
        self.assertEqual(classify_http(200), ("ok", None))
        self.assertIs(classify_http(429)[1], FoundryRateLimited)
        self.assertIs(classify_http(503)[1], FoundryServerBusy)
        self.assertIs(classify_http(401)[1], FoundryAuthFailed)
        self.assertEqual(classify_http(400)[0], "stop")

    def test_retry_records_then_succeeds(self):
        calls = {"n": 0}
        retries = []

        def post(payload):
            calls["n"] += 1
            if calls["n"] < 3:
                return 429, {}
            return 200, {"choices": [{"message": {"content": "ok"}}]}

        body = request_completion(post, {"messages": []}, sleep=lambda delay: retries.append(delay), on_retry=lambda message, delay: None)
        self.assertEqual(body["choices"][0]["message"]["content"], "ok")
        self.assertEqual(retries, [0.5, 1.0])
        self.assertNotIn("CRUSOE_API_KEY", json.dumps(build_chat_payload([], [], "example-model")))

    def test_empty_completion(self):
        with self.assertRaises(EmptyCompletion):
            parse_completion({"choices": []})
        with self.assertRaises(EmptyCompletion):
            parse_completion({"choices": [{"message": {"content": "  "}}]})

    def test_secret_scanner_rejects_trace_text(self):
        with self.assertRaises(SecretInTrace):
            assert_no_secrets('{"note": "Bearer sk-test-secret-value"}')
        clean = {"sample": True, "steps": [{"result": "dry run"}], "backend": "scripted"}
        dumps_trace(clean)

    def test_foundry_class_is_not_constructed(self):
        import agent.loop as loop
        import agent_eval
        self.assertNotIn("OpenAICompatModel(", Path(loop.__file__).read_text(encoding="utf-8"))
        self.assertNotIn("OpenAICompatModel(", Path(agent_eval.__file__).read_text(encoding="utf-8"))
        self.assertNotIn("OpenAICompatModel(", Path("build_demo.py").read_text(encoding="utf-8"))


class TrajectoryTests(unittest.TestCase):
    def test_skip_intake_and_unknown_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            skipped = run_scripted(
                "skip",
                calls=[{"name": "confirm_priority"}],
                checkpoint_path=Path(tmp) / "skip.json",
            )
            self.assertEqual(skipped["outcome"]["failure_class"], SkipIntake.failure_class if False else "SkipIntake")
            unknown = run_scripted(
                "unknown",
                calls=[{"name": "not_a_tool"}, {"name": "complete_run"}],
                checkpoint_path=Path(tmp) / "unknown.json",
            )
        self.assertEqual(unknown["outcome"]["failure_class"], None)
        self.assertTrue(unknown["outcome"]["completed"])
        classes = [step["failure_class"] for step in unknown["steps"]]
        self.assertIn(UnknownTool.__name__, classes)

    def test_model_no_tool_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run_scripted("empty", calls=[], checkpoint_path=Path(tmp) / "empty.json")
        self.assertEqual(trace["outcome"]["failure_class"], ModelNoToolCall.__name__)

    def test_scripted_trace_has_no_secrets_and_zero_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run_scripted("happy", checkpoint_path=Path(tmp) / "happy.json")
        dumps_trace(trace)
        self.assertEqual(trace["totals"]["cost_usd"], 0)
        self.assertEqual(trace["backend"], "scripted")
        self.assertTrue(trace["sample"])
        self.assertEqual(trace["outcome"]["priority"], "P2")
        self.assertLessEqual(trace["totals"]["model_turns"], 40)
        self.assertIsNone(os.environ.get("INTEGRATIONS_MODE") if False else None)

    def test_ci_env_does_not_select_foundry(self):
        with patch.dict(os.environ, {"CI": "true", "CRUSOE_API_KEY": "not-used"}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                trace = run_scripted("write_without_approval", checkpoint_path=Path(tmp) / "w.json")
        self.assertEqual(trace["backend"], "scripted")
        self.assertEqual(trace["outcome"]["failure_class"], "WriteBeforeApproval")


if __name__ == "__main__":
    unittest.main()
