# Reliability notes

This page records failure and recovery behavior that the local harness already implements. The runs below are deterministic checks against fixtures and an in-process HTTP server. They are not production incidents, deployment telemetry, or live-model evaluations.

## What this harness does and does not do

The demo workflow is rule-based. `serve.py` accepts a small JSON review action, and `harness.py` applies it only when the case revision and the evidence gates match. A rejected action raises `ReviewError` before `revision` increments, and the HTTP handler returns that message with status 409. Malformed bodies return 400 and leave the session as it was. A request whose `Origin` is not this server returns 403 before the session is read.

There is no tool-call timeout, automatic retry, or fallback model. The browser client in `web/app.js` shows the error text and ignores a second click while one request is in flight. It does not retry. Token use and model cost are unmeasured because this repository does not call a model. The checks below are optional maintainer verification. No API key is required for them. The hosted demo is the case replay; these checks do not add a browser evaluation panel.

The read-only helper `incident_triage.triage` is separate from the customer-recovery workflow. `command_center.workflow` uses `validate_incident` to reject malformed case records. It does not use the keyword hypotheses. Incomplete proof, the launch-picker route, and reopening after a confirmed repeat are covered by `workflow_eval.py` and [iteration notes](iteration.md), not by the HTTP cases below.

## What failed, and how it was reproduced

Two gaps showed up while reading the existing tests, before any new behavior was added.

1. `test_harness.py` already checked workflow gates in memory. It did not send a malformed HTTP body, a foreign origin, or a missing session cookie, so a regression in `serve.py` could pass CI.
2. Calling `incident_triage.triage` on the observation `No worker, storage, or capacity signal is present.` matched the words `worker`, `storage`, and `capacity`. The helper then cleared `missing_evidence` for those hypotheses even though the sentence is a negation. `confirmed_root_cause` stayed `null`, and the customer sentence still says a root cause is not confirmed. That keyword limitation was already in the helper. This change does not treat it as fixed.

Reproducing the HTTP cases means starting `serve.Handler` on `127.0.0.1` with an ephemeral port and sending the requests in `test_reliability.py`. Reproducing the keyword case is a direct call to `incident_triage.triage` with that one-sentence fixture. No debugger beyond the assertion traceback and a one-off print of the helper’s JSON was required. The first test draft expected every hypothesis to list missing evidence. That assertion failed in 0.0008s and is what surfaced the negation match.

## What changed

`test_reliability.py` locks the current gates:

| Case | Expected stop or recovery |
| --- | --- |
| Empty body, non-JSON content type, invalid JSON, non-string action, non-integer revision, body over 1024 bytes | HTTP 400, `Invalid review request.`, revision and audit unchanged |
| `Origin` not equal to this host | HTTP 403, session not applied |
| POST with no demo cookie | HTTP 409, `Demo session expired. Reload the page.` |
| Unknown action, or a revision that is not current | HTTP 409, revision unchanged; the same session then accepts `reveal` at the current revision |
| Unsupported restore wording | HTTP 409, preview stays locked; restoring the supported wording and approving it unlocks the preview |
| `confirm_recovery` before recovery evidence is loaded | HTTP 409, stage stays `Coordinate`, customer not recovered, no actions |
| Incident missing required fields, duplicate evidence id, or blank evidence source | `ValueError` from `validate_incident` |
| Evidence with no hypothesis keywords | Every hypothesis stays `unverified`, lists missing evidence, and `confirmed_root_cause` is null |
| Negated keyword sentence above | Keywords still count as support; confirmed cause stays null |

No demo route, public URL, style, or session behavior was changed. No dependency was added.

## Measured results

The numbers below are from one maintainer run of the fixture checks on this workspace with Python 3.12.3 on 2026-11-09. GitHub Actions uses Python 3.11. They are not a hosted evaluation and they do not measure the public demo in a browser.

Optional maintainer commands, from a checkout:

```sh
python3 -m unittest test_reliability test_harness
python3 assessment_check.py --copilot-path .
```

| Check | Result | Wall clock |
| --- | --- | --- |
| `unittest` (`test_reliability` + `test_harness`) | 14 tests, OK | 0.6364s process, 0.546s reported by `unittest` |
| Seven reliability cases, timers inside the tests | 7/7 passed | 0.0404s combined |
| `assessment_check.py --copilot-path .` | 8/8 passed | 0.0417s |

A second `unittest` invocation on the same machine reported 0.550s for 14 tests and 0.0455s inside the seven reliability cases. Treat the table as one measured run, not a stable benchmark.

Per-case times from that same reliability run:

| Case | Seconds |
| --- | ---: |
| Malformed HTTP requests, then reread the session | 0.0242 |
| Unsupported claim, then supported wording | 0.0063 |
| Missing recovery evidence | 0.0042 |
| Unknown and stale actions, then a valid `reveal` | 0.0036 |
| Rejected origin and missing session | 0.0014 |
| Keyword triage, including the negation limitation | 0.0004 |
| Malformed incident records | 0.0002 |

Before this change, the same `test_harness.py` file and the eight golden assessment cases were the CI suites. Those 7 + 8 checks still pass. The new file adds the seven HTTP and validation cases. There is no earlier production outage or latency baseline to compare.

## Limits

- These are fixture results. They do not measure a hosted browser session, a live model, customer impact, or recurrence in a real product.
- The server has no request timeout. A client that sends a `Content-Length` and then stalls can hold the handler. The tests send complete bodies and pass `timeout=5` on the client socket only.
- The browser double-click guard was read in `web/app.js`. It was not executed in this measurement.
- The keyword helper can treat a negated mention as supporting evidence. The customer-recovery path does not call that helper. A production pilot would need a reviewed matcher, not this word list.
- Model token usage and cost were not measured.
