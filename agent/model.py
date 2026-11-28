"""Model contract: messages and tool schemas in, tool calls or text out.

``ScriptedModel`` replays a fixture. CI, trajectory evals, and the hosted trace
use it. ``OpenAICompatModel`` posts to an OpenAI-compatible ``/chat/completions``
endpoint with the standard library. The maintainer command is the only caller.
"""

import json
import os
import time
import urllib.error
import urllib.request

from agent.failures import (
    EmptyCompletion,
    FoundryAuthFailed,
    FoundryKeyMissing,
    FoundryRateLimited,
    FoundryRequestRejected,
    FoundryServerBusy,
)

DEFAULT_BASE_URL = "https://api.inference.crusoecloud.com/v1"
DEFAULT_MODEL = "crusoe-model"
BACKOFF_SECONDS = (0.5, 1.0, 2.0)
MAX_ATTEMPTS = 4


class ToolCall:
    def __init__(self, name, arguments, call_id):
        self.name = name
        self.arguments = arguments if isinstance(arguments, dict) else {}
        self.id = call_id

    def as_dict(self):
        return {"name": self.name, "arguments": self.arguments, "id": self.id}


class ModelTurn:
    def __init__(self, *, tool_calls, text, prompt_tokens, completion_tokens, cost_usd, latency_s):
        self.tool_calls = tool_calls
        self.text = text or ""
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost_usd = cost_usd
        self.latency_s = latency_s


class ScriptedModel:
    """Return the next fixture tool call. Used by CI and the hosted trace."""

    name = "scripted"

    def __init__(self, calls, *, start=0):
        self.calls = list(calls)
        self.index = start

    def complete(self, messages, tools):
        started = time.perf_counter()
        if self.index >= len(self.calls):
            return ModelTurn(
                tool_calls=[], text="", prompt_tokens=0, completion_tokens=0,
                cost_usd=0.0, latency_s=time.perf_counter() - started,
            )
        spec = self.calls[self.index]
        self.index += 1
        call = ToolCall(spec["name"], spec.get("arguments") or {}, f"scripted-{self.index}")
        return ModelTurn(
            tool_calls=[call], text="", prompt_tokens=0, completion_tokens=0,
            cost_usd=0.0, latency_s=time.perf_counter() - started,
        )


def classify_http(status):
    """Return ``ok``, ``retry``, or ``stop`` and the failure class for a status."""
    if status == 200:
        return "ok", None
    if status == 429:
        return "retry", FoundryRateLimited
    if status >= 500:
        return "retry", FoundryServerBusy
    if status in {401, 403}:
        return "stop", FoundryAuthFailed
    return "stop", FoundryRequestRejected


def http_failure_message(status):
    if status == 429:
        return "The model endpoint returned 429. The retry budget is exhausted."
    if status >= 500:
        return f"The model endpoint returned {status}. The retry budget is exhausted."
    if status in {401, 403}:
        return f"The model endpoint rejected the credentials ({status})."
    return f"The model endpoint rejected the request ({status})."


def parse_completion(payload):
    """Turn a chat-completions body into text, tool calls, and token counts."""
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        raise EmptyCompletion("The completion returned no choices.")
    message = choices[0].get("message") or {}
    if not message.get("tool_calls") and not (message.get("content") or "").strip():
        raise EmptyCompletion("The completion returned no tool call and no text.")
    calls = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function") or {}
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError as exc:
                raise FoundryRequestRejected("A tool call had arguments that were not JSON.") from exc
        if not isinstance(arguments, dict):
            raise FoundryRequestRejected("A tool call had arguments that were not an object.")
        name = function.get("name")
        if not name:
            raise FoundryRequestRejected("A tool call was missing a name.")
        calls.append(ToolCall(name, arguments, raw.get("id") or f"call-{len(calls) + 1}"))
    usage = payload.get("usage") or {}
    return {
        "text": message.get("content") or "",
        "tool_calls": calls,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }


def build_chat_payload(messages, tools, model):
    return {"model": model, "messages": messages, "tools": tools, "temperature": 0}


def request_completion(post, payload, *, sleep, on_retry):
    """POST until 200, a non-retry status, or the backoff budget ends.

    ``post`` returns ``(status, body)``. ``on_retry`` records a ModelRetry.
    ``sleep`` receives the delay so tests can skip waiting.
    """
    last_type = FoundryServerBusy
    for attempt in range(MAX_ATTEMPTS):
        status, body = post(payload)
        kind, exc_type = classify_http(status)
        if kind == "ok":
            return body
        last_type = exc_type
        if kind != "retry" or attempt == MAX_ATTEMPTS - 1:
            raise exc_type(http_failure_message(status))
        delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
        on_retry(exc_type("The model endpoint returned %s. Retrying." % status).args[0], delay)
        sleep(delay)
    raise last_type(http_failure_message(503))


def _scrub(text, secret):
    if secret and secret in text:
        text = text.replace(secret, "[redacted]")
    return text[:300]


class OpenAICompatModel:
    """Stdlib client for an OpenAI-compatible chat endpoint.

    Construct this from the maintainer command only. CI and the demo call
    ``ScriptedModel`` and do not construct this class.
    """

    name = "foundry"

    def __init__(self, *, base_url=None, api_key=None, model=None, sleep=time.sleep, post=None):
        if os.environ.get("CI") == "true" and post is None:
            raise FoundryRequestRejected(
                "The Foundry backend is a maintainer command. CI uses the scripted model."
            )
        key = api_key if api_key is not None else os.environ.get("CRUSOE_API_KEY")
        if not key:
            raise FoundryKeyMissing("CRUSOE_API_KEY is not set. The model request was not sent.")
        self._key = key
        self.base_url = (base_url or os.environ.get("CRUSOE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model_id = model or os.environ.get("CRUSOE_MODEL") or DEFAULT_MODEL
        self._sleep = sleep
        self._post = post

    def complete(self, messages, tools, *, on_retry):
        payload = build_chat_payload(messages, tools, self.model_id)
        started = time.perf_counter()

        def post(body):
            if self._post is not None:
                return self._post(body)
            return self._urllib_post(body)

        raw = request_completion(post, payload, sleep=self._sleep, on_retry=on_retry)
        parsed = parse_completion(raw)
        cost = float((raw.get("usage") or {}).get("cost") or 0)
        return ModelTurn(
            tool_calls=parsed["tool_calls"],
            text=parsed["text"],
            prompt_tokens=parsed["prompt_tokens"],
            completion_tokens=parsed["completion_tokens"],
            cost_usd=cost,
            latency_s=time.perf_counter() - started,
        )

    def _urllib_post(self, payload):
        data = json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=data,
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("Authorization", "Bearer " + self._key)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = _scrub(error.read().decode(errors="replace"), self._key)
            kind, exc_type = classify_http(error.code)
            if kind == "retry":
                return error.code, {"error": detail}
            raise exc_type(http_failure_message(error.code)) from error
        except urllib.error.URLError as error:
            raise FoundryServerBusy("The model endpoint could not be reached.") from error
