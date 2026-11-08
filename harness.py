"""Offline escalation coordinator. Agents read evidence and propose. The reviewer decides."""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from command_center.workflow import FACTS, INCIDENTS, ReviewError, Session

DATA = json.loads(Path(__file__).with_name("scenario.json").read_text(encoding="utf-8"))
CASE_ID = "ESC-1042"
CASE = INCIDENTS[CASE_ID]


def recurrence():
    """Match a verified mechanism on the same surface, regardless of symptom wording."""
    return [
        {**case, "match": case["confirmed"] and
         (case["surface"], case["mechanism"]) == ("template_authoring", "draft_discard")}
        for case in DATA["history"]
    ]


def propose_actions(matches):
    anchor = date.fromisoformat(CASE["rollout"]["launch_at"][:10])
    return {
        row["id"]: {**row, "due": (anchor + timedelta(days=row["offset"])).isoformat(),
                    "state": "Proposed"}
        for row in DATA["actions"]
        if len(matches) >= 2 or not row.get("recurrence_required")
    }


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

    def record(self, actor, summary, sources=()):
        self.audit.append({
            "step": len(self.audit) + 1, "actor": actor, "summary": summary,
            "sources": list(sources), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    def require(self, condition, reason):
        if not condition:
            raise ReviewError(reason)

    def apply(self, command, revision, action_id=None):
        self.require(revision == self.revision, "This view changed. Reload before applying an action.")
        if command in {"reveal", "confirm_priority", "approve", "revise", "inject_restore", "original"}:
            self.require(self.stage in {"Engage", "Coordinate"}, "Triage review is complete.")
            self.require(command != "confirm_priority" or not self.triage.priority_confirmed,
                         "Priority is already confirmed.")
            self.triage.apply(command, self.triage.version)
            self.stage = "Coordinate"
            summaries = {
                "reveal": ("Triage agent", "Matched the discard event and rollout impact. Suggested P2.", ["E2","E3","KB1-F2"]),
                "confirm_priority": ("Escalation manager", "Confirmed P2 and took ownership.", ["E3"]),
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
            self.record("Escalation manager", "Confirmed customer recovery. Prevention work is still open.", ["R1","R2"])
        elif command == "learn":
            self.require(self.stage == "Learn" and not self.actions, "Confirm customer recovery before running the learning agents.")
            self.history = recurrence()
            matches = [case["source"] for case in self.history if case["match"]]
            self.actions = propose_actions(matches)
            self.record("RCA agent", "Separated the confirmed discard from the contributing prompt design observed in a test copy.", ["E2","R3"])
            self.record("Recurrence agent", f"Matched {len(matches)} prior verified discards and excluded the launch-picker report.", [*matches,"H3"])
            self.record("Routing agent", f"Proposed {len(self.actions)} follow-ups with owners, due dates, and acceptance criteria.", ["E2","R3",*matches])
        elif command == "approve_plan":
            self.require(self.stage == "Learn" and self.actions, "Run and review the learning agents first.")
            self.stage = "Verify"
            for action in self.actions.values():
                action["state"] = "Assigned"
            self.record("Escalation manager", "Accepted ownership and verification criteria for the proposed plan.")
        elif command == "load_proof":
            self.require(self.stage == "Verify" and not self.proof_available, "Approve the follow-up plan first.")
            self.proof_available = True
            self.record("Verification agent", "Loaded simulated completion evidence. Owner sign-off is pending.")
        elif command == "verify":
            action = self.actions.get(action_id)
            self.require(self.stage == "Verify" and self.proof_available and action
                         and action["state"] == "Assigned", "Verification requires an assigned action and completion evidence.")
            self.require(action_id != "EXEC" or all(row["state"] == "Verified"
                         for key, row in self.actions.items() if key != "EXEC"),
                         "Executive sign-off requires the other teams’ evidence.")
            action["state"] = "Verified"
            self.record(action["owner"], f"Verified {action_id}. {action['proof']}", action["sources"])
        elif command == "close":
            self.require(self.stage == "Verify" and self.actions
                         and all(row["state"] == "Verified" for row in self.actions.values()),
                         "Every assigned action needs owner sign-off before learning can close.")
            self.stage = "Closed"
            self.record("Escalation manager", "Closed the learning loop. Scheduled 30-day recurrence review.")
        else:
            raise ReviewError("Unknown workflow action.")
        self.revision += 1

    def view(self):
        triage = self.triage.view()
        evidence = {row["id"]: [row["source"], row["observation"]] for row in triage["evidence"]}
        for key, fact in triage["facts"].items():
            evidence[key] = [fact["title"], fact["paraphrase"], fact["url"]]
        if self.resolution_available:
            evidence.update({key: DATA["evidence"][key] for key in ("R1", "R2")})
        if self.actions:
            evidence.update({key: DATA["evidence"][key] for key in ("R3", "H1", "H2", "H3")})
        recovered = self.stage in {"Learn","Verify","Closed"}
        return {
            "case_id": CASE_ID, "customer": CASE["customer"], "stage": self.stage, "revision": self.revision,
            "triage": triage, "evidence": evidence, "recovered": recovered,
            "resolution_available": self.resolution_available,
            "proof_available": self.proof_available,
            "actions": [
                {key: value for key, value in row.items() if key != "proof" or self.proof_available}
                for row in self.actions.values()
            ],
            "history": self.history, "audit": self.audit,
            "learning_review": {"interval_days": 30, "owner": "Support operations lead"} if self.stage == "Closed" else None,
            "executive": {
                "status": "Rollout restored and confirmed by the customer" if recovered else
                          "One rollout at risk" if self.triage.confirmed else "Impact under investigation",
                "priority": "P2 confirmed" if self.triage.priority_confirmed else "Priority pending",
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
