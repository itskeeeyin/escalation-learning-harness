"""Stdio JSON-RPC wrapper around the same tool registry.

Speaks ``initialize``, ``tools/list``, and ``tools/call`` with Content-Length
framing. Writes use the same approval gate and stay a dry run. This module
does not set ``INTEGRATIONS_MODE`` and does not read API keys.

    python3 -m agent.mcp
"""

import json
import sys

from agent.failures import AgentFailure
from agent.tools import Registry, ToolExecutor

PROTOCOL = "2024-11-05"


class Session:
    def __init__(self):
        self.registry = Registry()
        self.executor = ToolExecutor()
        self.initialized = False


def tool_list(session):
    return {
        "tools": [
            {
                "name": spec["function"]["name"],
                "description": spec["function"]["description"],
                "inputSchema": spec["function"]["parameters"],
            }
            for spec in session.registry.schemas()
        ]
    }


def call_tool(session, params):
    name = (params or {}).get("name")
    arguments = (params or {}).get("arguments") or {}
    try:
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise AgentFailure("tools/call needs a tool name and an arguments object.")
        text = session.registry.call(session.executor, name, arguments)
    except AgentFailure as exc:
        return {
            "content": [{"type": "text", "text": f"{exc.failure_class}: {exc}"}],
            "isError": True,
        }
    return {"content": [{"type": "text", "text": text}], "isError": False}


def handle(message, session):
    """Return a JSON-RPC response, or None when the message is a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid JSON-RPC request.")
    method = message.get("method")
    msg_id = message.get("id")
    if msg_id is None:
        return None
    params = message.get("params") or {}
    if method == "initialize":
        session.initialized = True
        return _result(msg_id, {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "escalation-learning-harness", "version": "0"},
            "instructions": (
                "Fictional practice tools. Sample records are labeled sample true. "
                "Writes stay proposed until approve_write, and execute_write is a dry run."
            ),
        })
    if not session.initialized:
        return _error(msg_id, -32002, "Call initialize before other methods.")
    if method == "tools/list":
        return _result(msg_id, tool_list(session))
    if method == "tools/call":
        return _result(msg_id, call_tool(session, params))
    return _error(msg_id, -32601, f"Method {method} is not implemented. Use initialize, tools/list, or tools/call.")


def _result(msg_id, payload):
    return {"jsonrpc": "2.0", "id": msg_id, "result": payload}


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def read_message(stream):
    headers = {}
    while True:
        line = stream.readline()
        if line == b"":
            return None
        if line in (b"\r\n", b"\n"):
            break
        if b":" not in line:
            raise ValueError("MCP header was not a field.")
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    if "content-length" not in headers:
        raise ValueError("MCP message is missing Content-Length.")
    length = int(headers["content-length"])
    body = stream.read(length)
    if len(body) != length:
        raise ValueError("MCP message ended before Content-Length bytes.")
    return json.loads(body.decode("utf-8"))


def write_message(stream, payload):
    data = json.dumps(payload).encode("utf-8")
    stream.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
    stream.flush()


def serve(stdin, stdout):
    session = Session()
    while True:
        try:
            message = read_message(stdin)
        except (ValueError, json.JSONDecodeError) as exc:
            write_message(stdout, _error(None, -32700, f"The message could not be read: {exc}"))
            return
        if message is None:
            return
        response = handle(message, session)
        if response is not None:
            write_message(stdout, response)


def main():
    serve(sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
