# Evaluation notes

## What the checks cover

| Suite | Cases | Behavior covered |
| --- | ---: | --- |
| Assessment golden cases | 8 | Confirmed discard, unverified missing template, unsupported restore and impact claims, preview approval, re-review after revision, conditional question issue, and unsupported community citation |
| Learning workflow checks | 7 | Premature learning, draft invalidation, separate recovery and learning closure, recurrence exclusion, routing with insufficient history, action and executive verification, and stale case revisions |
| Workflow replay scorecard | 3 | Incomplete proof and resubmission, separate routing for a launch-picker lookalike, and reopening and reclosing after a confirmed repeat |

```sh
python3 assessment_check.py --copilot-path .
python3 -m unittest -v
python3 workflow_eval.py
```

The [Actions workflow](../.github/workflows/evals.yml) runs all three checks with Python 3.11 and checks that the generated browser replay matches the Python scorecard. A local browser replay also exercised the blocked claim, draft revision, team verification, closure, JSON export, reload, session isolation, reset, and mobile layout. The hosted browser replay was also checked through blocked claims, proof resubmission, separate routing for the alternate case, and reopening and reclosing after a confirmed repeat. These browser checks are manual and run separately from CI.

Export the per-step decisions, evidence checks, and failures with `python3 workflow_eval.py --report /tmp/escalation-scorecard.json`. The [iteration notes](iteration.md) explain the before and after.

## What the numbers mean

Passing checks establish the specified behavior for the fixtures. They provide no measurement of live model quality, actual recurrence, customer sentiment, or production reliability. The apparent reduction in the Operations proof is an example of how to write a measurable acceptance criterion. All inputs used to calculate it are synthetic.

For a production pilot, report verified actions completed on time, median time to customer recovery, time to verified closure, and confirmed repeat escalations per 100 comparable product actions. Compare equal observation windows and have a human reviewer adjudicate suspected repeats.
