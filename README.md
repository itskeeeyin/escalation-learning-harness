# Escalation Learning Harness

[Open the live demo](https://escalation-learning-harness.insightfulfeast.chatgpt.site) in your browser. No account or installation required.

A runnable demo that follows a critical customer escalation from the first report to customer recovery, then turns the evidence into corrective and preventive actions. The learning record closes after team owners verify their actions and an executive sponsor reviews the residual risk.

![Escalation learning loop with evidence inputs, reviewer decisions, verified outputs, and a proposed production feedback loop](docs/images/learning-loop.svg)

The demo replays one fictional assessment-template incident. The agents run deterministic rules, the evidence is synthetic, and a single browser session role-plays the people making decisions. The hosted replay keeps decisions in your browser tab and requires no account or API key.

## Run the Python version locally

The local version requires Python 3.11 or newer and uses the standard library.

```sh
git clone https://github.com/itskeeeyin/escalation-learning-harness.git
cd escalation-learning-harness
python3 serve.py
```

Open [the local demo](http://127.0.0.1:8796). If the port is in use, run `python3 serve.py --port 8797` and open that port instead. Use **Restart practice case** to rehearse again.

## What to show

1. **Engage.** Open the customer report. Run triage, inspect the discard event and rollout impact, then confirm P2. The severity rubric is fictional.
2. **Coordinate.** Review the executive brief and customer draft. Try the unsupported restore claim to see the approval block. Approve supported wording, revise it, and watch the preview lock again until the new version is approved.
3. **Confirm recovery.** Replay Support's rebuild validation and the customer's acceptance. The customer moves to **Recovered** while learning stays **Open**.
4. **Learn.** Run the RCA, recurrence, and routing stages. Two prior confirmed discard cases match. A similar launch-picker report is excluded because its mechanism is unverified.
5. **Verify.** Approve the follow-up plan and review simulated completion evidence. Verify each action, then record executive sign-off and close learning. **Export JSON** saves the decision record.

[Open a screenshot of the live demo](docs/images/demo-preview.png) · [Read the rehearsal guide](docs/demo-guide.md)

## What each team owns

| Team | Follow-up in the replay |
| --- | --- |
| Engineering | Verify safeguards and regression coverage for irreversible discard |
| Product & Design | Test whether customers understand the warning before they confirm |
| Support | Publish and rehearse a decision tree for discarded drafts and missing templates |
| Customer Success | Record customer acceptance and check readiness for the next rollout |
| Documentation & Enablement | Publish safe draft-editing and rebuild guidance |
| Operations & Analytics | Measure confirmed repeat escalations per 100 draft edits |
| Executive leadership | Review residual risk after team verification and set the next review |

The escalation manager owns the case, confirms priority and recovery, approves the follow-up plan, and closes the learning record. Each action carries an owner, due date, evidence references, and an acceptance criterion. See the [roles and decisions visual](docs/images/main-players.svg).

## Benefits and boundaries

![Expected benefits alongside the limits of the current demo](docs/images/benefits-and-limits.svg)

The replay demonstrates source-linked drafts, explicit recovery and closure decisions, and routing based on recurrence. The example reduction from **3 to 1 confirmed discards per 100 edits** is synthetic. A production pilot would measure repeat escalations, follow-up completion, and time to verified closure. The demo records a 30-day review commitment without scheduling it.

- [Design notes](docs/design.md) describe inputs, outputs, code structure, and proposed production work.
- [Rehearsal guide](docs/demo-guide.md) includes the main walkthrough and what to inspect at each decision.
- [Evaluation notes](docs/evaluation.md) explain what CI checks and what remains outside the test set.
- [Reliability notes](docs/reliability.md) record measured failure and recovery cases from the local harness. The demo does not call a model.

## Run the checks

```sh
python3 assessment_check.py --copilot-path .
python3 -m unittest -v
```

GitHub Actions runs both suites on pushes and pull requests. See the [workflow](.github/workflows/evals.yml).

## Prior work and license

The demo reuses the prior assessment workflow built on [Runbook Copilot](https://github.com/itskeeeyin/runbook-copilot/tree/d40faf4) and the golden-case approach from [Copilot Evals](https://github.com/itskeeeyin/copilot-evals/tree/60d8e98). The diagrams follow the visual style of those repos. See [MIT license and attribution](LICENSE).
