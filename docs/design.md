# Design notes

## Purpose

A customer recovery decision answers whether the affected workflow is usable again. A learning closure decision answers whether owners delivered and verified the follow-up. A real rollout would keep both decisions visible, even when work moves to a different team or planning cycle.

## Evidence in and records out

| Inputs | How the demo uses them | Outputs |
| --- | --- | --- |
| Customer report, discard event, rollout deadline and worksheet availability | Estimate impact and check that the event concerns this draft | Priority recommendation, rebuild plan, customer and executive drafts |
| Product guidance and draft claims | Validate the supported recovery path and bind approval to a draft version | Approved local preview or a blocked claim with a reason |
| Rebuild validation and customer acceptance | Show the reviewer why recovery can be confirmed | Customer recovery decision |
| RCA review and earlier incident records | Separate the discard event from the prompt design and match the confirmed mechanism on the same product surface | Cause and contributing factor, prior matches, excluded near miss |
| Team action catalog and simulated completion evidence | Route work, present acceptance criteria, and collect role-played decisions | Assigned and verified actions, executive decision, recurrence review commitment |
| Session decisions and evidence IDs | Preserve the order of workflow events | Downloadable JSON decision record |

The fictional customer is **Example Privacy Team**, case **ESC-1042**. Support validates the rebuilt template against 18 required questions and both routing paths. The customer accepts the outcome. The review treats the discard as the direct cause of the missing draft and identifies incomplete warning copy as a contributing design factor observed on a test copy. It leaves the scope of previously launched assessments open.

## Approval and evidence gates

- The workflow validates the wording and citations before exposing a preview. Approval applies to the displayed draft version. Editing that version requires approval again.
- The reviewer can confirm recovery after seeing Support validation and customer acceptance alongside an approved draft. Recovery unlocks RCA and routing.
- Routing uses the team catalog. Product and Operations actions in this fixture require at least two prior matches. The general match rule requires a confirmed mechanism and the same product surface.
- The reviewer approves the proposed plan before the harness assigns its actions. Verification requires an assigned action and loaded completion evidence. Executive verification follows the other team verifications.
- Closure requires every assigned action to be verified. The export includes the recurrence review owner and interval.

The demo server checks the case revision before applying changes. That protects the replay from stale browser actions. Reviewer roles are labels in the trace, with one local human acting all roles. The audit view records decisions and evidence references in session memory and exports a snapshot on demand.

## Where to look in the code

| File | Responsibility |
| --- | --- |
| [command_center/workflow.py](../command_center/workflow.py) | Triage, claim validation, and version-specific approval from the earlier assessment demo |
| [command_center/cases.json](../command_center/cases.json) | Synthetic intake scenarios and paraphrased public product guidance |
| [harness.py](../harness.py) | Recovery, recurrence, routing, action verification, and closure rules |
| [scenario.json](../scenario.json) | Synthetic history, recovery evidence, team catalog, and completion evidence |
| [serve.py](../serve.py) | Local HTTP interface and in-memory browser sessions |
| [web/](../web/) | Replay UI, evidence viewer, executive brief, and JSON export |
| [assessment_golden.json](../assessment_golden.json) and [test_harness.py](../test_harness.py) | Golden assessment scenarios and workflow guard checks |

## Proposed production design

| Workstream | Current replay | Proposed pilot |
| --- | --- | --- |
| Intake | A single interactive case with fixed evidence | Read approved case and product signals with stable record IDs and redacted customer data |
| Reasoning | Deterministic stages and a small historical set | Use a larger, independently reviewed case set with confirmed matches, lookalikes, and contradictory evidence |
| Decision authority | One reviewer plays every role | Authenticate decision-makers and enforce ownership and approval roles at each gate |
| Work tracking | Local action catalog and simulated proof | Use approved, retry-safe ticket creation and link actual changes, tests, and customer acceptance |
| Trace and review | In-memory records with JSON export | Persist decision history, assign review dates, and reopen follow-up when recurrence exceeds the agreed threshold |
| Measurement | Synthetic improvement figures and deterministic tests | Establish a baseline for time to recovery, on-time verification, and confirmed recurrences per unit of product usage |

The prototype uses no live model, CRM, messaging, ticketing, or production telemetry. State resets when the server restarts. The demo neither schedules the recurrence review nor takes automatic follow-up action. A pilot would first compare the model and rules against human-reviewed cases and agree on who can approve each transition.
