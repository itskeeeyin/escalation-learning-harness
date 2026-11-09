"""Practice workflow for the assessment-template escalation case."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from incident_triage import validate_incident

DATA = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))
INCIDENTS = {case["incident_id"]: case for case in DATA["incidents"]}
FACTS = {
    fact["id"]: {**fact, "title": article["title"], "url": article["url"]}
    for article in DATA["knowledge_base"]
    for fact in article["facts"]
}
COMMUNITY_IDS = {source["id"] for source in DATA["community_signals"]}
DRAFT = DATA["customer_draft_fixture"]
UPDATE_AT = "2026-11-04T22:00:00Z"
REBUILD_WORDING = (
    DRAFT["claims"][-1]["text"],
    "To move forward, we’ll create a new assessment template and configure it again.",
)
REVIEWER = "Demo escalation manager"


class ReviewError(ValueError):
    pass


def triage(incident_id, available_citation_ids, *, as_of=None):
    """Interpret the explicitly labeled evidence in these synthetic fixtures."""
    case = INCIDENTS[incident_id]
    incident = validate_incident(case)
    available = set(available_citation_ids)
    evidence = {row.id: row for row in incident.evidence if row.id in available}
    if "E2" in evidence:
        citations = {"discard": ["E2"]}
        if "KB1-F2" in available:
            citations["rebuild"] = ["KB1-F2"]
        severity = "NEEDS_IMPACT_CHECK"
        if "E3" in evidence:
            rollout = case["rollout"]
            now = datetime.fromisoformat(as_of or evidence["E3"].timestamp)
            hours_until_launch = (datetime.fromisoformat(rollout["launch_at"]) - now).total_seconds() / 3600
            if (
                "rebuild" in citations
                and rollout["blocked_rollouts"] == 1
                and rollout["worksheet_available"]
                and 0 <= hours_until_launch <= 24
            ):
                severity = "P2"
            citations["impact_and_deadline"] = ["E3"]
        return {
            "finding": "confirmed_draft_discard",
            "severity_recommendation": severity,
            "severity_state": "provisional",
            "required_citations": citations,
            "unknowns": ["impact_on_launched_assessments"],
        }
    if "E6" in evidence:
        citations = {"path_specific_reproduction": ["E6"]}
        if "E5" in evidence:
            citations["reported_symptom"] = ["E5"]
        if "KB3-F1" in available:
            citations["documented_logic"] = ["KB3-F1"]
        return {
            "finding": "reproduced_on_one_answer_path",
            "hypothesis": "conditional_question_logic",
            "root_cause": "unverified",
            "severity_recommendation": "NEEDS_IMPACT_CHECK",
            "required_citations": citations,
            "next_check": "Compare the template’s Q7-to-Q12 conditions and repeat both answer paths on a test copy.",
        }
    return {
        "finding": "cause_unverified",
        "severity_recommendation": "NEEDS_IMPACT_CHECK",
        "ask_for": ["exact_template_name", "record_type", "solution", "customer_impact", "deadline"],
        "suggest_if_searching_gallery": ["check_archived_templates"],
        "required_citations": {
            "launch_checks": sorted(available & {"KB2-F1", "KB2-F2"}),
            "gallery_checks": sorted(available & {"KB2-F3"}),
        },
    }


def validate_claim(text, citation_ids, available_citation_ids):
    """Practice mode accepts only reviewed wording and its designated support."""
    sources = set(citation_ids)
    if sources & COMMUNITY_IDS:
        return {"approval_allowed": False, "failure_code": "COMMUNITY_SOURCE_NOT_AUTHORITATIVE_FOR_CLAIM"}
    if not sources or not sources <= set(available_citation_ids):
        return {"approval_allowed": False, "failure_code": "MISSING_OR_UNKNOWN_CITATION"}
    wording = text.casefold()
    if "restore" in wording and "backup" in wording and "KB1-F1" in available_citation_ids:
        return {
            "approval_allowed": False,
            "failure_code": "CONTRADICTS_PRODUCT_GUIDANCE",
            "supporting_citation_ids": ["KB1-F1"],
        }
    allowed = {claim["text"]: set(claim["citation_ids"]) for claim in DRAFT["claims"]}
    allowed[REBUILD_WORDING[1]] = {"KB1-F2"}
    if allowed.get(text) != sources:
        return {"approval_allowed": False, "failure_code": "CITATION_DOES_NOT_SUPPORT_CLAIM"}
    return {"approval_allowed": True}


def preview_allowed(draft_id, version, decision, claims_valid):
    return bool(
        claims_valid
        and decision
        and decision["decision"] == "approved"
        and decision["draft_id"] == draft_id
        and decision["version"] == version
    )


@dataclass
class Session:
    confirmed: bool = False
    priority_confirmed: bool = False
    version: int = 0
    claims: list = field(default_factory=list)
    audit: list = field(default_factory=list)

    @property
    def evidence_ids(self):
        lookup = {"E1", "KB2-F1", "KB2-F2", "KB2-F3"}
        return lookup | {"E2", "E3", "KB1-F1", "KB1-F2"} if self.confirmed else lookup

    @property
    def validation(self):
        return [
            {"claim_id": claim["id"], **validate_claim(claim["text"], claim["citation_ids"], self.evidence_ids)}
            for claim in self.claims
        ]

    def apply(self, action, version=None):
        if action == "reveal" and not self.confirmed and version == self.version:
            self.confirmed = True
            self._set_draft("original")
            return
        if not self.confirmed or version != self.version:
            raise ReviewError("This case view is out of date. Refresh it before making a decision.")
        if action == "confirm_priority":
            self.priority_confirmed = True
            return
        if action in {"revise", "inject_restore", "original"}:
            self._set_draft(action)
            return
        if action not in {"approve", "reject"}:
            raise ReviewError("Unknown review action.")
        if any(event["version"] == self.version for event in self.audit):
            raise ReviewError("This version has already been reviewed. Revise it before reviewing again.")
        if action == "approve" and (not self.priority_confirmed or not self.claims or not all(
            check["approval_allowed"] for check in self.validation
        )):
            raise ReviewError("Confirm the priority and resolve draft validation before approving.")
        self.audit.append({
            "draft_id": DRAFT["id"],
            "version": self.version,
            "reviewer": REVIEWER,
            "decision": "approved" if action == "approve" else "rejected",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    def _set_draft(self, variant):
        previous = self.claims[-1]["text"] if self.claims else None
        self.claims = [dict(claim) for claim in DRAFT["claims"]]
        if variant == "revise":
            self.claims[-1]["text"] = (
                REBUILD_WORDING[0] if previous == REBUILD_WORDING[1] else REBUILD_WORDING[1]
            )
        elif variant == "inject_restore":
            self.claims[-1].update(
                text="Engineering can restore the discarded draft from backup.",
                citation_ids=["KB1-F1"],
            )
        self.version += 1

    def view(self):
        case = INCIDENTS["ESC-1042"]
        evidence = [row for row in case["evidence"] if row["id"] in self.evidence_ids]
        decision = self.audit[-1] if self.audit else None
        checks = self.validation
        preview = preview_allowed(DRAFT["id"], self.version, decision, bool(checks) and all(
            check["approval_allowed"] for check in checks
        ))
        current_decision = decision if decision and decision["version"] == self.version else None
        return {
            "case": {key: case[key] for key in ("incident_id", "customer", "template_name", "symptom")},
            "confirmed": self.confirmed,
            "priority_confirmed": self.priority_confirmed,
            "triage": triage(case["incident_id"], self.evidence_ids),
            "timeline": case["timeline"] if self.confirmed else case["timeline"][:1],
            "evidence": evidence,
            "facts": {key: FACTS[key] for key in sorted(self.evidence_ids & FACTS.keys())},
            "follow_up": case["follow_up"] if self.confirmed else None,
            "preventive_follow_up": case["preventive_follow_up"] if self.confirmed else None,
            "next_update_at": UPDATE_AT if self.confirmed else None,
            "draft": {
                "version": self.version,
                "claims": self.claims,
                "commitment": DRAFT["proposed_commitment"] if self.confirmed else None,
                "validation": checks,
                "decision": current_decision,
            },
            "preview": " ".join([
                *(claim["text"] for claim in self.claims),
                DRAFT["proposed_commitment"]["text"],
            ]) if preview else None,
            "audit": self.audit,
        }
