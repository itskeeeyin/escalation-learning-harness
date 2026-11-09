# What changed and why

The first public demo showed the path from a customer report to verified closure. Its evidence was synthetic and its reviewer decisions were deterministic. In the first replay, Engineering's completion proof passed as soon as it was loaded. The launch-picker lookalike appeared only in the case history. Closing the learning record logged a 30-day review commitment, but the reviewer could stop there.

The next iteration asks a harder question. What should happen when the evidence fails, points to a different cause, or shows the problem happened again?

| Decision | Before | After | Why we changed it |
| --- | --- | --- | --- |
| Is a merged pull request enough to verify a preventive action? | The first demo loaded a passing Engineering fixture. In the draft revision, the new gate rejected incomplete proof, but the browser had no way to continue. | The reviewer returns the merged-PR-only submission. Engineering supplies a passing regression and a customer-path replay. The reviewer can then verify the action. | A merged change proves something shipped. The acceptance criterion asks whether the affected workflow actually works. |
| Does the same symptom imply the same cause? | The launch-picker report was excluded as an unverified item in the main case history. The draft alternate case also leaked the original case ID and cited evidence from the wrong case. | The alternate replay shows a published template and a reproducible solution-filter mismatch. It has its own case identity, sources, owner, and customer recovery decision. | A missing item can have different causes. Routing on symptom alone would send the issue to the wrong team and inflate recurrence counts. |
| What happens if the same mechanism recurs after closure? | The first demo stopped at the review commitment. The draft reopening path hid proof that an earlier decision still cited. | Report A remains separate. Report B confirms another discard and reopens Engineering verification and executive sign-off while preserving the original customer's recovery. Revised proof has its own evidence ID. | Recurrence can invalidate confidence in a safeguard without changing what happened for the original customer. The old decision still needs to be auditable. |

## Evidence from the rerun

- The first release passed **8 assessment cases and 7 workflow tests**.
- During review of the draft revision, **1 of 7 workflow tests failed** at Engineering verification. An alternate-case replay also reproduced mismatched case identity and missing source links. Reopening reproduced a missing source in the prior audit record.
- The corrected version passes **8 assessment cases, 7 workflow tests, and 3 new replay cases**. The new scorecard checks expected transitions, blocked actions, unchanged state after rejection, and whether cited evidence resolves at each step. The generated browser replay also runs the same cases against the Python results.

Run the scorecard and export its decision trace:

```sh
python3 workflow_eval.py --report /tmp/escalation-scorecard.json
```

The three new cases are synthetic regression examples written around these findings. The results measure the workflow rules and evidence references. A future evaluation can add independently reviewed cases to measure behavior on unfamiliar inputs. The demo records the review decision without scheduling a live review.

[Live demo](https://escalation-learning-harness.insightfulfeast.chatgpt.site/) · [Rehearsal guide](demo-guide.md) · [Evaluation notes](evaluation.md)
