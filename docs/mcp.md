# MCP stdio wrapper

`python3 -m agent.mcp` exposes the same tool registry over stdin and stdout. The framing is `Content-Length`, then a JSON-RPC 2.0 body. The methods are `initialize`, `tools/list`, and `tools/call`.

The process keeps one in-memory case. `tools/call` runs the same handlers as the agent loop, including `Harness.apply` and the write adapters. A write stays proposed until `approve_write`. `execute_write` is a dry run even if the caller sets `dry_run` false. This command does not set `INTEGRATIONS_MODE` and does not take an API key.

Example messages, with the length header omitted:

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read_case_evidence", "arguments": {}}}
```

A refused tool comes back as `result.isError` true and names the failure class, such as `WriteBeforeApproval`. The server does not open a network connection in these examples.

`python3 -m unittest test_mcp` drives the server in process. It is part of the unit run in CI.
