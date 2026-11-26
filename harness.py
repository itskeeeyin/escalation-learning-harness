"""Deterministic escalation coordinator. Agents read evidence and propose. The reviewer decides."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from command_center.workflow import FACTS, INCIDENTS, ReviewError, Session
from itil import change_record, handoff, practice_records
from measurement import DATE_INPUTS, apply_lifecycle, build_scorecard, lesson_records

DATA = json.loads(Path(__file__).with_name("scenario.json").read_text(encoding="utf-8"))
CASE_ID = "ESC-1042"
CASE = INCIDENTS[CASE_ID]


def same_mechanism(case):
    return case["confirmed"] and (
        case["surface"], case["mechanism"]
    ) == ("template_authoring", "draft_discard")


def recurrence():
    """Match a verified mechanism on the same surface, regardless of symptom wording."""
    return [
        {**case, "match": same_mechanism(case)}
        for case in DATA["history"]
    ]


def propose_actions(matches):
    anchor = date.fromisoformat(CASE["rollout"]["launch_at"][:10])
    actions = {}
    for row in DATA["actions"]:
        if len(matches) < 2 and row.get("recurrence_required"):
            continue
        governance = row["kind"] == "Governance"
        actions[row["id"]] = {
            **row,
            "due": (anchor + timedelta(days=row["offset"])).isoformat(),
            "state": "Proposed",
            "escalation": "hierarchical" if row["team"] == "Executive leadership" else "functional",
            "change_id": None if governance else f"CHG-{row['id']}-1042",
            "change_state": None if governance else "proposed",
        }
    return actions


def set_change_state(actions, state, action_id=None):
    for key, row in actions.items():
        if row.get("change_id") and (action_id is None or key == action_id):
            row["change_state"] = state


@dataclass
class Harness:
    triage: Session = field(default_factory=Session)
    stage: str = "Engage"
    revision: int = 0
    actions: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    audit: list = field(default_factory=list)
    proof_available: bool = False
    resolution_available: bool = False
    picker_stage: str | None = None
    active_signal: str | None = None
    signal_decisions: dict = field(default_factory=dict)
    problem_phase: str | None = None
    known_error: bool = False

    def record(self, actor, summary, sources=()):
        self.audit.append({
            "step": len(self.audit) + 1, "actor": actor, "summary": summary,
            "sources": list(sources), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    def require(self, condition, reason):
        if not condition:
            raise ReviewError(reason)

    def review_picker(self, command):
        if command == "inspect_picker" and self.picker_stage == "Reported":
            self.picker_stage = "Evidence"
            self.record("Triage agent", "Found the published template and reproduced a solution filter mismatch.", ["P2", "P3"])
        elif command == "route_picker" and self.picker_stage == "Evidence":
            self.picker_stage = "Routed"
            self.record("Escalation manager", "Routed to launch-picker Support. Excluded this case from draft-discard recurrence.", ["P2", "P3"])
        elif command == "recover_picker" and self.picker_stage == "Routed":
            self.picker_stage = "Recovered"
            self.record("Escalation manager", "Confirmed launch readiness after the customer validated the corrected filter.", ["P4"])
        elif command == "route_as_discard" and self.picker_stage == "Evidence":
            raise ReviewError("The publish record and filter test support a visibility issue. Review P2 and P3.")
        else:
            raise ReviewError("Complete the current launch-picker review step first.")

    def review_engineering(self, command):
        action = self.actions.get("ENG")
        self.require(self.stage == "Verify" and self.proof_available and action,
                     "Load the completion evidence first.")
        if command == "return_proof":
            self.require(action["state"] == "Assigned" and not action["proof_ready"],
                         "Only an incomplete submission can be returned.")
            action["state"] = "Needs rework"
            self.record("Verification reviewer", "Returned Engineering proof. A merged PR does not demonstrate a passing regression or customer workflow.", ["V1"])
        else:
            self.require(action["state"] == "Needs rework", "Return the incomplete proof before resubmitting.")
            action.update(state="Assigned", proof_ready=True, proof=(
                "Regression CI-42 and customer-path replay CX-42 passed on the patched build. "
                "The replay used the editor entry point that reproduced the repeat."
                if action.get("reopened") else
                "Regression CI-17 passed cancel and warning checks. Customer-path replay CX-17 preserved the draft on cancel and verified the warning before discard."
            ))
            action["proof_source"] = "V3" if action.get("reopened") else "V2"
            self.record(action["owner"], "Submitted the passing regression and customer-path replay for review.", [action["proof_source"]])

    def review_recurrence(self, command, choice):
        self.require(self.stage == "Closed", "Close learning before replaying the recurrence review.")
        if command == "load_signal":
            self.require(choice in DATA["review_signals"] and choice not in self.signal_decisions
                         and not self.active_signal, "Review the current report before loading another.")
            self.active_signal = choice
            self.record("Support operations lead", "Loaded a simulated report at the 30-day review.", [DATA["review_signals"][choice]["source"]])
            return
        self.require(self.active_signal, "Load a report before making a recurrence decision.")
        signal = DATA["review_signals"][self.active_signal]
        matched = same_mechanism(signal)
        self.require((choice == "repeat" and matched) or (choice == "separate" and not matched),
                     "That decision conflicts with the report evidence. Compare the product surface and confirmed mechanism.")
        self.signal_decisions[self.active_signal] = "Confirmed repeat" if matched else "Separate issue"
        self.active_signal = None
        if matched:
            self.stage = "Verify"
            engineering = self.actions["ENG"]
            engineering.update(
                state="Needs rework", proof_ready=False, reopened=True,
                criterion="Pass the regression and customer-path replay on the editor entry point implicated by the repeat.",
            )
            engineering.pop("proof", None)
            engineering.pop("proof_source", None)
            self.actions["EXEC"]["state"] = "Assigned"
            self.actions["EXEC"]["proof"] = "Decision log EXEC-03 reviews the repeat, accepts the revised safeguard evidence and keeps the recurrence check on the review agenda."
            set_change_state(self.actions, "implemented", "ENG")
            self.record("Escalation manager", "Confirmed the repeat and reopened Engineering verification and executive sign-off. The original customer recovery remains confirmed. The problem stays in error control until the revised change is verified effective.", [signal["source"]])
        else:
            self.record("Escalation manager", "Kept the visibility issue separate. Draft-discard prevention stays closed.", [signal["source"]])

    def apply(self, command, revision, action_id=None):
        self.require(revision == self.revision, "This view changed. Reload before applying an action.")
        if self.picker_stage:
            self.review_picker(command)
        elif command == "start_picker":
            self.require(self.stage == "Engage", "Restart the practice case before choosing another report.")
            self.picker_stage = "Reported"
            self.record("Escalation manager", "Opened the alternate missing-template report.", ["P1"])
        elif command in {"return_proof", "resubmit_proof"}:
            self.review_engineering(command)
        elif command in {"load_signal", "decide_signal"}:
            self.review_recurrence(command, action_id)
        elif command in {"reveal", "confirm_priority", "approve", "revise", "inject_restore", "original"}:
            self.require(self.stage in {"Engage", "Coordinate"}, "Triage review is complete.")
            self.require(command != "confirm_priority" or not self.triage.priority_confirmed,
                         "Priority is already confirmed.")
            self.triage.apply(command, self.triage.version)
            self.stage = "Coordinate"
            summaries = {
                "reveal": ("Triage agent", "Matched the discard event and rollout impact. Impact 2 and urgency 1 map to P2 on the example matrix.", ["E2","E3","KB1-F2"]),
                "confirm_priority": ("Escalation manager", "Confirmed P2 from the example impact and urgency matrix and took ownership.", ["E3"]),
                "approve": ("Escalation manager", f"Approved customer draft v{self.triage.version} for preview.", []),
                "revise": ("Escalation manager", "Revised draft wording. Prior approval expired.", []),
                "inject_restore": ("Triage agent", "Proposed a restore claim. Claim check blocked approval.", ["KB1-F1"]),
                "original": ("Escalation manager", "Restored supported rebuild wording for review.", ["KB1-F2"]),
            }
            self.record(*summaries[command])
        elif command == "load_resolution":
            self.require(self.stage == "Coordinate" and self.triage.view()["preview"]
                         and not self.resolution_available, "Approve the customer draft first.")
            self.resolution_available = True
            self.record("Recovery agent", "Read Support validation and customer acceptance. Recommended recovery sign-off.", ["R1","R2"])
        elif command == "confirm_recovery":
            self.require(self.stage == "Coordinate" and self.resolution_available
                         and self.triage.view()["preview"], "Recovery requires validation, acceptance and an approved draft.")
            self.stage = "Learn"
            self.problem_phase = "problem_identification"
            self.record("Escalation manager", "Confirmed customer recovery and closed the incident. The linked problem stays open for identification.", ["R1","R2"])
        elif command == "learn":
            self.require(self.stage == "Learn" and not self.actions, "Confirm customer recovery before running the learning agents.")
            self.history = recurrence()
            matches = [case["source"] for case in self.history if case["match"]]
            self.actions = propose_actions(matches)
            self.problem_phase = "problem_control"
            self.known_error = True
            self.record("RCA agent", "Separated the confirmed discard from the contributing prompt design observed in a test copy. The workaround and root cause make this a known error.", ["E2","R3"])
            self.record("Recurrence agent", f"Matched {len(matches)} prior verified discards and excluded the launch-picker report.", [*matches,"H3"])
            self.record("Routing agent", f"Proposed {len(self.actions)} follow-ups with owners, due dates, and acceptance criteria.", ["E2","R3",*matches])
        elif command == "approve_plan":
            self.require(self.stage == "Learn" and self.actions, "Run and review the learning agents first.")
            self.stage = "Verify"
            self.problem_phase = "error_control"
            for action in self.actions.values():
                action["state"] = "Assigned"
            set_change_state(self.actions, "assessed_authorized")
            self.record("Escalation manager", "Accepted the plan. Corrective and preventive changes are assessed and authorized. Effectiveness is still unconfirmed.")
        elif command == "load_proof":
            self.require(self.stage == "Verify" and not self.proof_available, "Approve the follow-up plan first.")
            self.proof_available = True
            self.actions["ENG"].update(
                proof_ready=False, proof_source="V1", proof="PR ENG-17 merged. The submission contains no regression result or customer-path replay."
            )
            set_change_state(self.actions, "implemented")
            self.record("Verification agent", "Loaded simulated submissions. Changes are implemented. Engineering supplied a merged PR only, so effectiveness is unconfirmed.", ["V1"])
        elif command == "verify":
            action = self.actions.get(action_id)
            self.require(self.stage == "Verify" and self.proof_available and action
                         and action["state"] == "Assigned", "Verification requires an assigned action and completion evidence.")
            self.require(action_id != "ENG" or action["proof_ready"],
                         "Engineering proof is incomplete. Return it and request regression and customer-path evidence.")
            self.require(action_id != "EXEC" or all(row["state"] == "Verified"
                         for key, row in self.actions.items() if key != "EXEC"),
                         "Executive sign-off requires the other teams’ evidence.")
            if action.get("change_id") and action.get("change_state") != "implemented":
                raise ReviewError(
                    "EffectivenessUnconfirmed: verify the change only after it is implemented. Completion alone does not show it worked.",
                    "EffectivenessUnconfirmed",
                )
            action["state"] = "Verified"
            if action.get("change_id"):
                action["change_state"] = "verified_effective"
            sources = [*action["sources"], action["proof_source"]] if action_id == "ENG" else action["sources"]
            self.record(action["owner"], f"Verified {action_id} effective. {action['proof']}", sources)
        elif command == "close":
            self.require(self.stage == "Verify" and self.actions
                         and all(row["state"] == "Verified" for row in self.actions.values()),
                         "Every assigned action needs owner sign-off before learning can close.")
            self.require(all(
                row.get("change_state") in {None, "verified_effective", "closed"}
                for row in self.actions.values()
            ), "EffectivenessUnconfirmed: a corrective or preventive change is not verified effective, so the problem record stays open.")
            self.stage = "Closed"
            set_change_state(self.actions, "closed")
            summary = ("Closed reopened follow-up after verifying the revised safeguard and executive sign-off."
                       if self.actions["ENG"].get("reopened") else
                       "Closed learning and recorded the 30-day recurrence review commitment.")
            self.record("Escalation manager", summary)
        else:
            raise ReviewError("Unknown workflow action.")
        self.revision += 1

    def published_action(self, row):
        return {
            key: value for key, value in row.items()
            if key not in DATE_INPUTS and (key != "proof" or self.proof_available)
        }

    def picker_view(self):
        stage = self.picker_stage
        evidence_ids = ["P1"]
        if stage != "Reported":
            evidence_ids.extend(["P2", "P3"])
        if stage == "Recovered":
            evidence_ids.append("P4")
        briefs = {
            "Reported": ("Missing template reported", "Confirm the template and picker scope.", "Review the publish and audit records."),
            "Evidence": ("Solution filter mismatch confirmed", "Route to launch-picker Support.", "Confirm the corrected picker path."),
            "Routed": ("Launch-picker Support owns the follow-up", "Validate the corrected filter with the customer.", "Confirm launch readiness."),
            "Recovered": ("Customer confirmed launch readiness", "Keep this case separate from draft-discard recurrence.", "No draft-discard follow-up for this case."),
        }
        status, decision, next_step = briefs[stage]
        return {
            "case_id": "ESC-1043", "customer": "Example Governance Team",
            "stage": stage, "revision": self.revision, "picker_stage": stage,
            "triage": None, "evidence": {key: DATA["evidence"][key] for key in evidence_ids},
            "recovered": stage == "Recovered", "resolution_available": stage == "Recovered",
            "proof_available": False, "actions": [], "history": [], "audit": self.audit,
            "lessons": [], "scorecard": None, "learning_review": None,
            "records": {
                "sample": True,
                "label": "Fictional lookalike. It is not the draft-discard incident or problem.",
                "incident": {
                    "record_type": "incident", "id": "INC-1043", "state": "closed" if stage == "Recovered" else "in_progress",
                    "problem_id": None, "sample": True,
                },
                "problem": None, "known_error": None, "known_error_database": [],
            },
            "changes": [],
            "handoffs": [handoff(
                "launch-picker-support", "functional", "Launch-picker Support",
                "The corrected filter is a functional escalation to the team that can reproduce it.",
            )] if stage in {"Routed", "Recovered"} else [],
            "executive": {
                "status": status, "priority": "Launch-picker review", "next": next_step,
                "decision": decision, "sources": evidence_ids,
            },
        }

    def view(self):
        if self.picker_stage:
            return self.picker_view()
        triage = self.triage.view()
        evidence = {row["id"]: [row["source"], row["observation"]] for row in triage["evidence"]}
        for key, fact in triage["facts"].items():
            evidence[key] = [fact["title"], fact["paraphrase"], fact["url"]]
        if self.resolution_available:
            evidence.update({key: DATA["evidence"][key] for key in ("R1", "R2")})
        if self.actions:
            evidence.update({key: DATA["evidence"][key] for key in ("R3", "H1", "H2", "H3")})
        if self.proof_available:
            engineering = self.actions["ENG"]
            evidence["V1"] = DATA["evidence"]["V1"]
            if engineering.get("proof_ready") or engineering.get("reopened"):
                evidence["V2"] = DATA["evidence"]["V2"]
            if engineering.get("proof_source") == "V3":
                evidence["V3"] = DATA["evidence"]["V3"]
        for signal in self.signal_decisions.keys() | ({self.active_signal} if self.active_signal else set()):
            source = DATA["review_signals"][signal]["source"]
            evidence[source] = DATA["evidence"][source]
        recovered = self.stage in {"Learn", "Verify", "Closed"}
        review = None
        if self.stage == "Closed" or self.signal_decisions:
            review = {
                "interval_days": 30,
                "owner": "Support operations lead",
                "active": DATA["review_signals"][self.active_signal]["source"] if self.active_signal else None,
                "decisions": self.signal_decisions,
                "reopened": self.stage == "Verify",
            }
        lessons, scorecard = self.measurement(evidence)
        return {
            "case_id": CASE_ID,
            "customer": CASE["customer"],
            "stage": self.stage, "revision": self.revision, "picker_stage": self.picker_stage,
            "triage": triage, "evidence": evidence, "recovered": recovered,
            "resolution_available": self.resolution_available,
            "proof_available": self.proof_available,
            "actions": [self.published_action(row) for row in self.actions.values()],
            "lessons": lessons, "scorecard": scorecard,
            "history": self.history, "audit": self.audit,
            "learning_review": review,
            "records": practice_records(
                stage=self.stage, problem_phase=self.problem_phase, known_error=self.known_error,
                priority_confirmed=self.triage.priority_confirmed,
            ),
            "changes": [record for record in (change_record(row) for row in self.actions.values()) if record],
            "handoffs": self.handoffs(),
            "executive": {
                "status": "Rollout restored and confirmed by the customer" if recovered else
                          "One rollout at risk" if self.triage.confirmed else "Impact under investigation",
                "priority": "P2 confirmed · impact 2 × urgency 1" if self.triage.priority_confirmed else "Priority pending",
                "next": ("30-day recurrence review" if self.stage == "Closed" else
                         "Review owners and verify preventive actions" if recovered else
                         "Escalation manager update by 2 p.m. Pacific (simulated)" if self.triage.confirmed else
                         "Confirm scope, deadline, and the draft event"),
                "decision": ("Continue monitoring the rollout of preventive changes" if self.stage == "Closed" else
                             "Sponsor to review residual risk after action verification" if recovered else
                             "Support to validate the rebuild. Product and Engineering to investigate draft safeguards."
                             if self.triage.confirmed else "Support to confirm impact and locate the draft event."),
                "sources": ["R1","R2"] if recovered else ["E2","E3"] if self.triage.confirmed else ["E1"],
            },
        }

    def handoffs(self):
        rows = []
        if self.triage.confirmed:
            rows.append(handoff(
                "support-rebuild", "functional", "Support",
                "Support validates the rebuilt template. That is a functional escalation to the team doing the work.",
            ))
            rows.append(handoff(
                "engineering-investigation", "functional", "Engineering",
                "The discard safeguard investigation goes to Engineering, the technical owner.",
            ))
            rows.append(handoff(
                "executive-brief", "hierarchical", "Executive leadership",
                "The stakeholder brief carries impact and the next checkpoint up to management.",
            ))
        for row in self.actions.values():
            rows.append(handoff(
                f"route-{row['id']}", row["escalation"], row["team"],
                f"{row['kind']} follow-up: {row['title']}",
            ))
        return rows

    def measurement(self, evidence):
        if not self.actions:
            return [], None
        lessons = apply_lifecycle(lesson_records(self.actions.values(), set(evidence)))
        scorecard = None
        if lessons and (self.stage == "Closed" or self.signal_decisions):
            scorecard = build_scorecard(lessons)
        return lessons, scorecard
