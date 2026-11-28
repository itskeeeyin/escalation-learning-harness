# Agent harness

A verified escalation workflow whose next tool can now be chosen by a model, with approval-gated writes, crash-safe resume, and CI that scores the steps on a scripted model.

The loop asks a model for one tool call, runs that tool, appends the result, and writes a JSON checkpoint. Workflow changes go through `Harness.apply`. Writes go through the existing proposal and `approve()` helpers. `execute_write` defaults to a dry run and does not set `INTEGRATIONS_MODE`.

A second page replays a recorded agent trace; the agent isn't called in the visitor's browser; the interactive case walk is unchanged.

## What CI runs

`python3 agent_eval.py` replays fixture tool sequences with `ScriptedModel`:

| Case | Expected stop |
| --- | --- |
| ESC-1042 happy path | Intake, P2 from impact 2 and urgency 1, returned then resubmitted Engineering proof, one approved dry run, then close |
| Write without approval | `WriteBeforeApproval` |
| Close before effectiveness | `CloseBeforeVerification` |
| ESC-1043 lookalike | Separate route. No discard known-error entry |
| Resume | Continue from the last completed step |
| Corrupt checkpoint | `ResumeStateCorrupt`, file left as it was |
| Step cap | `StepBudgetExceeded` inside the published cap of 40 model turns |

Support and Engineering handoffs on the happy path are functional. The executive brief is hierarchical. A mismatch is `WrongEscalationType`. Traces set `sample` true, label the run as fictional, and fail closed on secret-looking text (`SecretInTrace`). Scripted traces record `network: false` and cost `$0`.

Other named stops include `SkipIntake`, `WrongCaseType`, `ModelNoToolCall`, `UnknownTool`, `EffectivenessUnconfirmed`, `StepBudgetExceeded`, and `CostBudgetExceeded`. Policy gates are stored on the trace. Hard gates stop the run.

```sh
python3 -m agent --case ESC-1042 --model scripted --trace traces/esc-1042.json
python3 agent_eval.py --report /tmp/agent-scorecard.json
```

## Maintainer model command

This command is not a CI job. The demo build does not construct the client. Set the variables in your own shell. The process reads them and does not write them into the trace.

```sh
CRUSOE_API_KEY=... CRUSOE_MODEL=... python3 -m agent --case ESC-1042 --model foundry --trace traces/esc-1042.json
```

`CRUSOE_BASE_URL` defaults to `https://api.inference.crusoecloud.com/v1`. The client POSTs to `/chat/completions`. Missing key is `FoundryKeyMissing`. HTTP 401 or 403 is `FoundryAuthFailed`. HTTP 429 is `FoundryRateLimited`. HTTP 5xx is `FoundryServerBusy`. Other HTTP errors are `FoundryRequestRejected`. An empty body is `EmptyCompletion`. Retries on 429 and 5xx are recorded as `ModelRetry` and use delays of 0.5s, 1s, and 2s.

## Checkpoint

Each file stores the case id, the backend name, the step index, redacted messages, harness state, write states, the trace, and totals. Resume loads that file. Truncated or invalid JSON raises `ResumeStateCorrupt` and does not continue.

The same registry is also available as a stdio JSON-RPC process. See [MCP wrapper](mcp.md). That process does not enable live writes.

## Limits

These scores are fixture results. They do not measure a hosted model, customer impact, or recurrence outside the sample history. The case walk in `index.html` is still the reviewer replay. `measurement.py` is unchanged. The local server still drops sessions on restart.
