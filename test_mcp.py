"""In-process MCP stdio checks. No network and no live mode."""

import io
import json
import unittest

from agent.mcp import handle, read_message, serve, write_message
from agent.tools import Registry


def _frame(payload):
    stream = io.BytesIO()
    write_message(stream, payload)
    return stream.getvalue()


def _exchange(messages):
    inbound = io.BytesIO(b"".join(_frame(message) for message in messages))
    outbound = io.BytesIO()
    serve(inbound, outbound)
    outbound.seek(0)
    responses = []
    while True:
        message = read_message(outbound)
        if message is None:
            return responses
        responses.append(message)


class McpTests(unittest.TestCase):
    def test_initialize_and_list_the_same_registry(self):
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        self.assertEqual([item["id"] for item in responses], [1, 2])
        names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        expected = {spec["function"]["name"] for spec in Registry().schemas()}
        self.assertEqual(names, expected)
        self.assertIn("approve_write", names)
        self.assertIn("execute_write", names)
        rendered = json.dumps(responses)
        self.assertNotIn("INTEGRATIONS_MODE", rendered)
        self.assertNotIn("CRUSOE_API_KEY", rendered)

    def test_write_requires_approval_and_stays_dry_run(self):
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "propose_jira", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "execute_write", "arguments": {"proposal_index": 0, "dry_run": False},
            }},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "approve_write", "arguments": {"proposal_index": 0},
            }},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
                "name": "execute_write", "arguments": {"proposal_index": 0},
            }},
        ])
        blocked = responses[2]["result"]
        self.assertTrue(blocked["isError"])
        self.assertIn("WriteBeforeApproval", blocked["content"][0]["text"])
        dry = responses[4]["result"]
        self.assertFalse(dry["isError"])
        self.assertIn("network=false", dry["content"][0]["text"])

    def test_methods_before_initialize_are_rejected(self):
        response = handle({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}, type("S", (), {"initialized": False})())
        self.assertEqual(response["error"]["code"], -32002)

    def test_unknown_method(self):
        session_response = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
        ])
        self.assertEqual(session_response[1]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
