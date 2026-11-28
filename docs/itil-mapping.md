# How this flow maps to ITIL 4 practices

This page is a reading guide for an escalation manager walking an ITIL-literate team through the demo. It describes how the fictional case lines up with ITIL 4 practices and terms. It does not say this harness is ITIL certified, and it does not say an organization has adopted ITIL.

The customer is **Example Privacy Team**. The case is **ESC-1042**. Every record, score, and date is example data.

The stages on the demo are Engage, Coordinate, Confirm recovery, Learn, Verify, Review recurrence, and Measure.

## Incident management

Incident management restores the service. In this replay, Engage and Coordinate are that practice.

| Demo moment | What it maps to |
| --- | --- |
| The customer report (E1) | An incident is logged. The practice record is **INC-1042** (sample ServiceNow number INC0011042). |
| Triage confirms a draft discard and a blocked rollout | Incident diagnosis. The impact and the deadline are the inputs to priority. |
| Support rebuilds the template and the customer accepts it | Resolution and recovery. Confirm recovery **closes the incident**. |
| The launch-picker lookalike | A separate incident, INC-1043. It is not linked to this problem. |

The incident close notes say the customer is restored. They do not claim the cause is removed.

## Major incident procedure

On the example priority matrix below, **P1** is the major-incident cell: high impact and high urgency. A major incident procedure would add a named incident manager, a short communication cadence, and hierarchical escalation to management while specialists work the fix.

This case is **P2**. One customer workflow is blocked, and the deadline is inside 24 hours. The demo does not start the major incident procedure. The executive brief is still a hierarchical escalation, because management needs the impact and the next checkpoint.

## Priority: impact × urgency

Priority in this demo comes from a fictional matrix, not from a single severity sentence. Impact is how much is broken. Urgency is how soon it has to move.

| Impact \ Urgency | 1 High. Deadline inside 24 hours | 2 Medium. Deadline inside five days | 3 Low. Normal queue |
| --- | --- | --- | --- |
| 1 High. Many customers, or the service is unusable | P1 | P2 | P3 |
| 2 Medium. One customer workflow is blocked | **P2** | P3 | P4 |
| 3 Low. A workaround exists and no rollout is blocked | P3 | P4 | P5 |

ESC-1042 is impact **2** and urgency **1**, so the matrix returns **P2**. That is the same outcome the earlier one-line rubric described ("one rollout blocked within 24 hours, and a rebuild path exists"). The rubric is now the reason those two scores were chosen. If impact or urgency is still unknown, the failure class is **ImpactOrUrgencyUnverified** and no priority is assigned. A pair that is not on the matrix fails as **PriorityMatrixMiss**.

## Functional and hierarchical escalation

Functional escalation moves the work to the team that can do it. Hierarchical escalation moves it up to management.

| Handoff | Type |
| --- | --- |
| Support validates the rebuild | Functional |
| Engineering investigates the discard safeguard | Functional |
| Product, Documentation, Operations, and Customer Success follow-ups | Functional |
| Launch-picker Support on the lookalike case | Functional |
| Stakeholder brief during the incident | Hierarchical |
| Executive residual-risk review | Hierarchical |

Each handoff in the decision record has `escalation` set to `functional` or `hierarchical`.

## Problem management

Problem management looks for the cause and stops the repeat. The problem record is **PRB-1042** (sample ServiceNow number PRB0001042). It is opened when the incident closes, and it stays open while the cause is still being handled.

| Phase | When the demo enters it | What is true |
| --- | --- | --- |
| Problem identification | Confirm recovery | The incident is closed. The problem is logged and linked. The cause is not documented yet. |
| Problem control | Learn | The RCA names the cause. The rebuild is copied onto the problem as the workaround. Two earlier incidents match. The launch-picker report stays out. |
| Error control | Verify | Known-error fixes are raised as changes. The problem stays open until those changes are verified effective. |

Review recurrence can send the problem back through error control when the same mechanism is confirmed. The incident stays closed. The customer stays recovered.

## Known error and the known error database

A known error is a problem with a documented root cause or a documented workaround. This demo creates **KE-1042** at the end of problem control, when both are written down.

The workaround is: rebuild the template from the requirements worksheet and validate both routing paths.

The root cause is: confirming Discard removes the draft, and on a test copy the prompt did not name the draft or say that configuration would be lost.

**KEDB-1042** is the matching known error database entry in the JSON export. It is example data, not a live database. While error control is open the status is `known_error`. After the changes are verified effective and the learning record closes, the status is `permanent_fix_verified`. A confirmed repeat sets it back until the revised change is verified again.

## Change enablement

Corrective and preventive actions are change requests, not a checklist of tasks that disappear when someone says they are done. Governance review by the executive sponsor is not itself a change.

Each change uses this lifecycle:

1. **proposed** — raised with an owner, a due date, and an acceptance criterion
2. **assessed_authorized** — the escalation manager accepts the plan
3. **implemented** — the team submits completion evidence
4. **verified_effective** — a reviewer accepts that the evidence shows the change worked
5. **closed** — only after that gate, when the learning record closes

Implemented is not enough. Closing while a corrective or preventive change is short of `verified_effective` fails as **EffectivenessUnconfirmed**, and the problem stays open. Returning Engineering's merged pull request is that gate in the replay: the change was implemented, and the proof did not show it was effective.

Sample ServiceNow change **CHG0001042** is the same fictional fix, stopped at Authorize. The adapter will not send it until a person approves, and the default is a dry run.

## Service level management

The 2 p.m. Pacific customer update and the 30-day recurrence review are example commitments on this case. They show the kind of target service level management would agree and watch. They are not a live SLA, and the demo does not schedule them.

## Continual improvement

Measure is the continual improvement view of this case. The influence scorecard compares an example baseline with this practice quarter: acceptance, implementation, verification, and repeats. A repeat reopens the lesson. Verifying the revised proof does not erase the repeat. That is the improvement loop: identify, control, change, confirm it worked, and check whether it held.

## Where the records show up

The practice UI keeps the incident, the problem, the known error, and the change states next to the case. **Export JSON** writes `records` (incident, problem, known_error, known_error_database), `changes`, and `handoffs`. The [ServiceNow sample](integrations.md) shows the same story as incident → problem → change on labeled fixtures.
