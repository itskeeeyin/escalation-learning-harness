# Evaluation notes

## What the checks cover

| Suite | Cases | Behavior covered |
| --- | ---: | --- |
| Assessment golden cases | 8 | Confirmed discard, unverified missing template, unsupported restore and impact claims, preview approval, re-review after revision, conditional question issue, and unsupported community citation |
| Learning workflow checks | 7 | Premature learning, draft invalidation, separate recovery and learning closure, recurrence exclusion, routing with insufficient history, action and executive verification, and stale case revisions |
| Reliability cases | 7 | Malformed HTTP bodies, rejected origins, missing sessions, unknown and stale actions, blocked restore claims with recovery, missing recovery evidence, and malformed incident records |

The commands below are optional maintainer verification from a checkout. The hosted demo is the way to practice the case. CI does not browse the hosted demo, and there is no hosted evaluation panel.

```sh
python3 assessment_check.py --copilot-path .
python3 -m unittest -v
```

The [Actions workflow](../.github/workflows/evals.yml) runs both commands with Python 3.11. A local browser replay also exercised the blocked claim, draft revision, team verification, closure, JSON export, reload, session isolation, reset, and mobile layout. The hosted browser replay was also checked through blocked claims, draft reapproval, customer recovery, team and executive verification, closure, reload, and reset. These browser checks are manual and run separately from CI.

## What the numbers mean

Passing checks establish the specified behavior for the fixtures. They provide no measurement of live model quality, actual recurrence, customer sentiment, or production reliability. [Reliability notes](reliability.md) separate these deterministic results from live-model evidence. The local harness does not call a model, so token use and model cost are unmeasured. The apparent reduction in the Operations proof is an example of how to write a measurable acceptance criterion. All inputs used to calculate it are synthetic.

For a production pilot, report verified actions completed on time, median time to customer recovery, time to verified closure, and confirmed repeat escalations per 100 comparable product actions. Compare equal observation windows and have a human reviewer adjudicate suspected repeats.
