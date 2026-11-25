"""Influence scorecard for the practice case.

The math reads lesson records and the example history in measurement.json.
It does not call a model, a tracker, or a company system. Every figure is synthetic.
systems-mapping.example.json says where the same fields would live in tools an
organization already uses. This module does not connect to those tools.
"""
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "measurement.json").read_text(encoding="utf-8"))
SYSTEMS = json.loads((ROOT / "systems-mapping.example.json").read_text(encoding="utf-8"))

DATE_INPUTS = frozenset({
    "example_routed_on", "example_accepted_on", "example_accepted_link",
    "example_implemented_on", "example_reimplemented_on",
    "example_verified_on", "example_shipped_on",
    "example_reverified_on", "example_reshipped_on",
})
ROUTED_STATES = frozenset({"Assigned", "Needs rework", "Verified"})
SHIPPED_TYPES = frozenset({"defect", "architecture"})
LIFECYCLE = ("created", "routed", "accepted", "implemented", "verified", "held")
RECORD_FIELDS = (
    "escalation_ticket", "engineering_issue", "lesson_record", "root_cause_tag",
    "owner_team", "lifecycle_status", "required_links", "recurrence_flag",
)
OWNERS = (
    ("Support", "Training for the gap, and a runbook the support team can rehearse."),
    ("Solutions Architects", "A solution pattern the account team can apply on the next design."),
    ("Data center / hardware operations", "A check or procedure so the same hardware fault is caught before customers see it."),
    ("Product management", "A clearer warning, screen, or guide."),
    ("Field / professional services engineers", "A tool or check so a field or professional services engineer can solve the issue without escalating."),
    ("Engineering", "A defect is fixed, or the component changes so the same issue cannot recur."),
)
OUTCOME_WORD = {
    "defect": "Shipped", "architecture": "Shipped", "training": "Published",
    "tool": "Adopted", "docs": "Shipped", "design": "Published", "operations": "In place",
}


def hours_between(start, end):
    opened = datetime.fromisoformat(start.replace("Z", "+00:00"))
    closed = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return (closed - opened).total_seconds() / 3600


def routed_on_time(lesson, target_days):
    if not lesson.get("routed_on") or not lesson.get("opened_on"):
        return False
    delta = (date.fromisoformat(lesson["routed_on"]) - date.fromisoformat(lesson["opened_on"])).days
    return 0 <= delta <= target_days


def mean(values):
    values = list(values)
    if not values:
        raise ValueError("No example values to average.")
    return sum(values) / len(values)


def num(value, digits=2):
    rounded = round(float(value), digits)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def days_between(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def reading_date(lessons, as_of):
    stamp = date.fromisoformat(as_of)
    for lesson in lessons:
        for key in ("opened_on", "created_on", "routed_on", "accepted_on", "implemented_on", "verified_on", "shipped_on"):
            value = lesson.get(key)
            if value:
                stamp = max(stamp, date.fromisoformat(value))
    return stamp


def lesson_lifecycle(lesson, as_of, hold_days):
    """Furthest lifecycle stage the record has earned. A recurrence reopens it."""
    if lesson.get("recurrence") == "reopened" and lesson.get("state") != "Verified":
        return "reopened"
    if not lesson.get("routed_on"):
        return "created"
    if not lesson.get("accepted_on"):
        return "routed"
    if not lesson.get("implemented_on"):
        return "accepted"
    if lesson.get("state") != "Verified" or not lesson.get("verified_on"):
        return "implemented"
    if lesson.get("recurrence") == "reopened":
        return "verified"
    if days_between(lesson["verified_on"], as_of.isoformat()) >= hold_days:
        return "held"
    return "verified"


def apply_lifecycle(live_lessons, config=None):
    config = config or CONFIG
    pool = [*config["history"], *live_lessons]
    as_of = reading_date(pool, config["as_of"])
    stamped = []
    for lesson in live_lessons:
        status = lesson_lifecycle(lesson, as_of, config["hold_days"])
        stamped.append({**lesson, "lifecycle": status, "held": status == "held", "hold_days": config["hold_days"]})
    return stamped


def lesson_records(actions, evidence_ids):
    """Routing records for the practice case. Dates stay empty until that state is earned."""
    practice = CONFIG["practice_case"]
    lessons = []
    for action in actions:
        if "owner_type" not in action:
            continue
        state = action["state"]
        reopened = bool(action.get("reopened"))
        routed = state in ROUTED_STATES or reopened
        verified = state == "Verified"
        verified_once = verified or reopened
        first_verified = action["example_verified_on"] if verified_once else None
        first_shipped = action["example_shipped_on"] if verified_once else None
        first_implemented = action.get("example_implemented_on", action["example_shipped_on"]) if verified_once else None
        if reopened and verified:
            verified_on = action.get("example_reverified_on", action["example_verified_on"])
            shipped_on = action.get("example_reshipped_on", action["example_shipped_on"])
            implemented_on = action.get("example_reimplemented_on", shipped_on)
        else:
            verified_on = first_verified
            shipped_on = first_shipped
            implemented_on = first_implemented
        sources = list(action["sources"])
        accepted_on = action["example_accepted_on"] if routed else None
        lessons.append({
            "id": f"{practice['id']}-{action['id']}",
            "case_id": practice["id"],
            "quarter": practice["quarter"],
            "title": action["title"],
            "owner": action["owner"],
            "owner_type": action["owner_type"],
            "action_type": action["action_type"],
            "product_area": action["product_area"],
            "state": state,
            "opened_on": practice["opened_on"],
            "created_on": practice["opened_on"],
            "routed_on": action["example_routed_on"] if routed else None,
            "accepted_on": accepted_on,
            "accepted_link": action.get("example_accepted_link") if accepted_on else None,
            "lesson_ref": f"example:jira/LESSON-{practice['id']}-{action['id']}",
            "implemented_on": implemented_on,
            "verified_on": verified_on,
            "shipped_on": shipped_on,
            "first_verified_on": first_verified,
            "first_shipped_on": first_shipped,
            "first_implemented_on": first_implemented,
            "recurrence": "reopened" if reopened else "none",
            "repeat_count": 1 if reopened else 0,
            "human_approved": verified_once,
            "cited_ok": bool(sources) and all(source in evidence_ids for source in sources),
            "sources": sources,
            "scope": "practice_case",
            "example": True,
        })
    return lessons


def _quarter(lessons, quarter):
    return [lesson for lesson in lessons if lesson["quarter"] == quarter]


def _share(lessons, predicate):
    if not lessons:
        raise ValueError("No lessons to score.")
    return sum(1 for lesson in lessons if predicate(lesson)) / len(lessons)


def assemble_inputs(live_lessons, config=None):
    config = config or CONFIG
    history_ids = {lesson["id"] for lesson in config["history"]}
    overlap = history_ids & {lesson["id"] for lesson in live_lessons}
    if overlap:
        raise ValueError(f"Lesson id {sorted(overlap)[0]} is already in the example history.")
    practice = config["practice_case"]
    return {
        "target_days": config["target_days"],
        "repeat_target": config["repeat_target"],
        "eval_floor": config["eval_floor"],
        "eval_scale": config["eval_scale"],
        "baseline_quarters": list(config["baseline_quarters"]),
        "current_quarter": config["current_quarter"],
        "lessons": [*config["history"], *live_lessons],
        "areas": config["areas"],
        "hours_by_quarter": config["hours_by_quarter"],
        "quarter_median_hours": config["quarter_median_hours"],
        "field_solves": config["field_solves"],
        "eval_score": config["eval_score"],
        "as_of": config["as_of"],
        "hold_days": config["hold_days"],
        "practice_case": {
            "reported_at": practice["reported_at"],
            "first_update_at": practice["first_update_at"],
            "product_area": practice["product_area"],
        },
    }


def _area_rate(area, quarter, lessons, current_quarter):
    bucket = area["quarters"][quarter]
    escalations = bucket["escalations"]
    if quarter == current_quarter:
        escalations += sum(
            lesson["repeat_count"] for lesson in _quarter(lessons, quarter)
            if lesson["scope"] == "practice_case" and lesson["product_area"] == area["name"]
        )
    return escalations / bucket["volume"] * 100


def summarize(inputs):
    lessons = inputs["lessons"]
    baseline = inputs["baseline_quarters"]
    current = inputs["current_quarter"]
    target_days = inputs["target_days"]

    def closed_count(quarter):
        return sum(lesson["state"] == "Verified" for lesson in _quarter(lessons, quarter))

    def on_time(quarter):
        routed = [lesson for lesson in _quarter(lessons, quarter) if lesson.get("routed_on")]
        return _share(routed, lambda lesson: routed_on_time(lesson, target_days))

    def shipped(quarter):
        return sum(
            1 for lesson in _quarter(lessons, quarter)
            if lesson["action_type"] in SHIPPED_TYPES and lesson.get("shipped_on")
        )

    def of_type(quarter, action_type):
        return sum(
            1 for lesson in _quarter(lessons, quarter)
            if lesson["action_type"] == action_type and lesson.get("shipped_on")
        )

    def repeats(quarter):
        return sum(lesson["repeat_count"] for lesson in _quarter(lessons, quarter))

    def flagged(quarter, key):
        return _share(_quarter(lessons, quarter), lambda lesson: lesson[key])

    areas = []
    for area in inputs["areas"]:
        baseline_rate = mean([_area_rate(area, quarter, lessons, current) for quarter in baseline])
        current_rate = _area_rate(area, current, lessons, current)
        areas.append({
            "name": area["name"],
            "unit": area["unit"],
            "baseline_value": baseline_rate,
            "current_value": current_rate,
            "held": current_rate <= baseline_rate,
        })
    practice_hours = hours_between(
        inputs["practice_case"]["reported_at"], inputs["practice_case"]["first_update_at"]
    )
    hours_baseline = mean(inputs["hours_by_quarter"][quarter] for quarter in baseline)
    field_baseline = mean(inputs["field_solves"][quarter] for quarter in baseline)
    eval_baseline = mean(inputs["eval_score"][quarter] for quarter in baseline)
    eval_current = inputs["eval_score"][current]
    return {
        "repeat_count": repeats(current),
        "repeat_target": inputs["repeat_target"],
        "repeat_held": repeats(current) == inputs["repeat_target"],
        "practice_hours": practice_hours,
        "metrics": {
            "lessons_closed": _count_metric(mean([closed_count(q) for q in baseline]), closed_count(current), "up"),
            "routed_on_time": _count_metric(mean([on_time(q) for q in baseline]), on_time(current), "up"),
            "shipped_changes": _count_metric(mean([shipped(q) for q in baseline]), shipped(current), "up"),
            "training_published": _count_metric(mean([of_type(q, "training") for q in baseline]), of_type(current, "training"), "up"),
            "tools_adopted": _count_metric(mean([of_type(q, "tool") for q in baseline]), of_type(current, "tool"), "up"),
            "repeats": _count_metric(mean([repeats(q) for q in baseline]), repeats(current), "down", held=repeats(current) == inputs["repeat_target"]),
            "escalation_rate": {"areas": areas, "held": all(area["held"] for area in areas)},
            "first_update": _count_metric(hours_baseline, practice_hours, "down"),
            "field_solves": _count_metric(field_baseline, inputs["field_solves"][current], "up"),
            "eval_score": _count_metric(eval_baseline, eval_current, "up", held=eval_current >= inputs["eval_floor"]),
            "citations": _count_metric(mean([flagged(q, "cited_ok") for q in baseline]), flagged(current, "cited_ok"), "up", held=flagged(current, "cited_ok") == 1),
            "human_approval": _count_metric(mean([flagged(q, "human_approved") for q in baseline]), flagged(current, "human_approved"), "up", held=flagged(current, "human_approved") == 1),
        },
        "teams": _team_metrics(inputs),
    }


def _team_rows(lessons, quarter, owner):
    return [
        lesson for lesson in _quarter(lessons, quarter)
        if lesson["owner_type"] == owner and lesson.get("routed_on")
    ]


def _mean_defined(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return mean(values)


def _acceptance(rows):
    if not rows:
        return None
    return sum(1 for lesson in rows if lesson.get("accepted_on")) / len(rows)


def _verified_share(rows):
    if not rows:
        return None
    return sum(1 for lesson in rows if lesson["state"] == "Verified") / len(rows)


def _span(rows, start_key, end_key):
    samples = [
        days_between(lesson[start_key], lesson[end_key])
        for lesson in rows if lesson.get(start_key) and lesson.get(end_key)
    ]
    if not samples:
        return None
    return mean(samples)


def _team_repeats(rows):
    if not rows:
        return None
    return sum(lesson["repeat_count"] for lesson in rows if lesson.get("first_verified_on"))


def _optional_metric(baseline, current, better, held=None):
    if baseline is None or current is None:
        return {"baseline_value": baseline, "current_value": current, "better": better, "held": False}
    return _count_metric(baseline, current, better, held)


def _team_metrics(inputs):
    lessons = inputs["lessons"]
    baseline = inputs["baseline_quarters"]
    current = inputs["current_quarter"]
    rows = []
    for owner_type, _blurb in OWNERS:
        def series(calc, owner=owner_type):
            return _mean_defined(calc(_team_rows(lessons, quarter, owner)) for quarter in baseline)

        current_rows = _team_rows(lessons, current, owner_type)
        acceptance = _optional_metric(series(_acceptance), _acceptance(current_rows), "up")
        accept_days = _optional_metric(series(lambda bucket: _span(bucket, "routed_on", "accepted_on")), _span(current_rows, "routed_on", "accepted_on"), "down")
        implement_days = _optional_metric(series(lambda bucket: _span(bucket, "accepted_on", "implemented_on")), _span(current_rows, "accepted_on", "implemented_on"), "down")
        verified = _optional_metric(series(_verified_share), _verified_share(current_rows), "up")
        repeats_current = _team_repeats(current_rows)
        repeats = _optional_metric(
            series(_team_repeats), repeats_current, "down",
            held=repeats_current == inputs["repeat_target"] if repeats_current is not None else False,
        )
        rows.append({
            "owner_type": owner_type,
            "acceptance_rate": acceptance,
            "time_to_accept": accept_days,
            "time_to_implement": implement_days,
            "verified_pct": verified,
            "repeats": repeats,
        })
    return rows


def _count_metric(baseline, current, better, held=None):
    if held is None:
        held = current >= baseline if better == "up" else current <= baseline
    return {"baseline_value": baseline, "current_value": current, "better": better, "held": held}


def _change(metric, *, points=False, suffix=""):
    delta = metric["current_value"] - metric["baseline_value"]
    if abs(delta) < 1e-9:
        return "No change"
    amount = abs(delta * 100) if points else abs(delta)
    digits = 1 if points else 2
    word = "higher" if delta > 0 else "lower"
    if metric["better"] == "down" and suffix == " hours":
        word = "slower" if delta > 0 else "faster"
        return f"{num(amount, digits)} hours {word}"
    label = f"{num(amount, digits)}{' points' if points else suffix} {word}"
    return label


def _percent(value):
    return f"{num(value * 100, 1)}%"


def _per_100(value, unit):
    return f"{num(value)} per 100 {unit}"


def _lesson_view(lesson, as_of, hold_days):
    status_name = lesson_lifecycle(lesson, as_of, hold_days)
    status = {
        "created": "Created", "routed": "Routed", "accepted": "Accepted",
        "implemented": "Implemented", "verified": "Verified", "held": "Held",
        "reopened": "Reopened",
    }[status_name]
    if status_name == "verified" and lesson.get("recurrence") == "reopened":
        status = "Verified again"
    word = OUTCOME_WORD.get(lesson["action_type"], "Done")
    if status_name == "held":
        when = f"Held · {word.lower()} {lesson.get('shipped_on') or lesson.get('verified_on')}"
    elif status_name == "verified" or status == "Verified again":
        when = f"Verified {lesson['verified_on']} · hold window open"
        if lesson.get("first_verified_on") and lesson["first_verified_on"] != lesson["verified_on"]:
            when += f" · first {lesson['first_verified_on']}"
    elif status_name == "reopened":
        when = f"Reopened · first verified {lesson.get('first_verified_on')}"
    elif lesson.get("accepted_on"):
        when = f"Accepted {lesson['accepted_on']}"
    elif lesson.get("routed_on"):
        when = f"Routed {lesson['routed_on']}"
    else:
        when = "Not routed yet"
    return {
        "id": lesson["id"],
        "title": lesson["title"],
        "action_type": lesson["action_type"],
        "status": status,
        "lifecycle": status_name,
        "when": when,
        "accepted_link": lesson.get("accepted_link"),
        "scope_label": "This case" if lesson["scope"] == "practice_case" else "Example quarter",
        "recurrence": lesson["recurrence"],
    }


def _status_note(live_lessons):
    reopened = [lesson for lesson in live_lessons if lesson["recurrence"] == "reopened"]
    open_now = [lesson for lesson in reopened if lesson["state"] != "Verified"]
    if open_now:
        titles = ", ".join(lesson["title"] for lesson in open_now)
        return (
            f"A confirmed repeat reopened {titles}. The customer stays recovered. "
            "The repeat target is missed, and verifying the revised proof does not erase the repeat."
        )
    if reopened:
        return "The lesson is verified again. The repeat still counts. The target is zero."
    return "No closed lesson in this example quarter has recurred. The target is zero."


def build_scorecard(live_lessons, config=None):
    config = config or CONFIG
    inputs = assemble_inputs(live_lessons, config)
    summary = summarize(inputs)
    metrics = summary["metrics"]
    current = config["current_quarter"]
    as_of = reading_date(inputs["lessons"], config["as_of"])
    hold_days = config["hold_days"]
    routed_now = [lesson for lesson in _quarter(inputs["lessons"], current) if lesson.get("routed_on")]
    verified_now = [lesson for lesson in routed_now if lesson["state"] == "Verified"]
    from_case = [lesson for lesson in routed_now if lesson["scope"] == "practice_case"]
    bank = (
        f"{len(verified_now)} of {len(routed_now)} routed lessons in this example quarter are verified. "
        f"{len(from_case)} are from this practice case."
    )
    owners = []
    for owner_type, blurb in OWNERS:
        owners.append({
            "owner_type": owner_type,
            "blurb": blurb,
            "lessons": [
                _lesson_view(lesson, as_of, hold_days)
                for lesson in routed_now if lesson["owner_type"] == owner_type
            ],
        })
    target = config["target_days"]
    scale = config["eval_scale"]
    floor = config["eval_floor"]
    hours = summary["practice_hours"]
    groups = [
        {
            "id": "influence",
            "title": "Influence",
            "question": "What did the escalation manager get finished?",
            "metrics": [
                _card("lessons_closed", "Lessons verified and closed", metrics["lessons_closed"], "This quarter",
                      f"{num(metrics['lessons_closed']['baseline_value'])} per quarter",
                      num(metrics["lessons_closed"]["current_value"]),
                      _change(metrics["lessons_closed"]),
                      "Lessons whose owner has verified the evidence. A lesson in rework is not counted as closed. Customer acceptance, the measurement action, and executive sign-off stay on the case; they are not extra lessons."),
                _card("routed_on_time", f"Routed to an owner within {target} days", metrics["routed_on_time"], "This quarter",
                      _percent(metrics["routed_on_time"]["baseline_value"]),
                      _percent(metrics["routed_on_time"]["current_value"]),
                      _change(metrics["routed_on_time"], points=True),
                      f"Share of the quarter's lessons with a named owner and an owner type within {target} days of opening. Baseline is the average of the three earlier quarters."),
                _card("shipped_changes", "Defects and architecture changes shipped", metrics["shipped_changes"], "This quarter",
                      f"{num(metrics['shipped_changes']['baseline_value'])} per quarter",
                      num(metrics["shipped_changes"]["current_value"]),
                      _change(metrics["shipped_changes"]),
                      "Defect and architecture lessons with a ship date. A later repeat does not erase the ship. It fails the repeat target instead."),
                _card("training_published", "Training and runbooks published", metrics["training_published"], "This quarter",
                      f"{num(metrics['training_published']['baseline_value'])} per quarter",
                      num(metrics["training_published"]["current_value"]),
                      _change(metrics["training_published"]),
                      "Training lessons with a publish date, including a runbook a support team can rehearse."),
                _card("tools_adopted", "Field tools adopted", metrics["tools_adopted"], "This quarter",
                      f"{num(metrics['tools_adopted']['baseline_value'])} per quarter",
                      num(metrics["tools_adopted"]["current_value"]),
                      _change(metrics["tools_adopted"]),
                      "Tool lessons a field or professional services engineer can use. This practice case did not add one. The example quarter already includes one, marked as example quarter."),
            ],
        },
        {
            "id": "outcome",
            "title": "Outcome",
            "question": "Did the same problem stop coming back?",
            "metrics": [
                _card("repeats", "Repeat escalations on closed lessons", metrics["repeats"], "This quarter",
                      f"{num(metrics['repeats']['baseline_value'])} per quarter",
                      num(metrics["repeats"]["current_value"]),
                      _change(metrics["repeats"]),
                      "Verified lessons in this quarter whose confirmed mechanism came back. The target is zero. Re-verifying the lesson does not reset the count."),
                _area_card(metrics["escalation_rate"]),
                _card("first_update", "Time to first honest customer update", metrics["first_update"], "This case",
                      f"{num(metrics['first_update']['baseline_value'])} hours",
                      f"{num(hours)} hours",
                      _change(metrics["first_update"], suffix=" hours"),
                      f"Hours from the customer report to the first person-approved update that stays inside what the product can do. This case uses the example timeline, {config['practice_case']['reported_at'][11:16]} to {config['practice_case']['first_update_at'][11:16]} UTC on 4 Nov 2026. Other example cases this quarter have a median of {config['quarter_median_hours']} hours. An unsupported restore claim cannot be that update."),
                _card("field_solves", "Issues solved without escalating", metrics["field_solves"], "This quarter",
                      f"{num(metrics['field_solves']['baseline_value'])} per quarter",
                      num(metrics["field_solves"]["current_value"]),
                      _change(metrics["field_solves"]),
                      "Issues closed with a field tool or check and no escalation opened. This practice case is an escalation, so it is not in the count. The number is the example quarter's tally."),
            ],
        },
        {
            "id": "ai_loop",
            "title": "AI loop",
            "question": "Did the tools stay reviewable?",
            "metrics": [
                _card("eval_score", "Copilot eval score held in CI", metrics["eval_score"], "This quarter",
                      f"{num(metrics['eval_score']['baseline_value'])} of {scale}",
                      f"{num(metrics['eval_score']['current_value'])} of {scale}",
                      _change(metrics["eval_score"]),
                      f"Example figure for a practice eval set, out of {scale}. This replay does not run a model or read CI. Held when the figure stays at or above the floor of {floor}. Baseline is the average of the earlier example quarters.",
                      example_only=True),
                _card("citations", "Runbook answers cited correctly", metrics["citations"], "This quarter",
                      _percent(metrics["citations"]["baseline_value"]),
                      _percent(metrics["citations"]["current_value"]),
                      _change(metrics["citations"], points=True),
                      "Share of lessons whose cited sources resolve. The target is every lesson. On this practice case, each source has to be an evidence id on the decision record."),
                _card("human_approval", "Human approval on every action", metrics["human_approval"], "This quarter",
                      _percent(metrics["human_approval"]["baseline_value"]),
                      _percent(metrics["human_approval"]["current_value"]),
                      _change(metrics["human_approval"], points=True),
                      "Share of lessons a person approved. The target is every lesson. The replay will not verify an action, or approve an unsupported customer claim, without that decision."),
            ],
        },
    ]
    quarters = []
    template = config["areas"][0]
    for quarter in config["baseline_quarters"]:
        rows = _quarter(inputs["lessons"], quarter)
        routed = [lesson for lesson in rows if lesson.get("routed_on")]
        quarters.append({
            "id": quarter,
            "label": config["quarter_labels"][quarter],
            "lessons_closed": str(sum(lesson["state"] == "Verified" for lesson in rows)),
            "repeats": str(sum(lesson["repeat_count"] for lesson in rows)),
            "routed_on_time": _percent(_share(routed, lambda lesson: routed_on_time(lesson, target))),
            "template_rate": _per_100(
                _area_rate(template, quarter, inputs["lessons"], current), template["unit"]
            ),
        })
    return {
        "example": True,
        "disclaimer": config["disclaimer"],
        "summary": config["summary"],
        "status_note": _status_note(live_lessons),
        "repeat_count": summary["repeat_count"],
        "repeat_target": summary["repeat_target"],
        "repeat_held": summary["repeat_held"],
        "bank": bank,
        "owners": owners,
        "lifecycle": {
            "stages": list(LIFECYCLE),
            "hold_days": hold_days,
            "as_of": as_of.isoformat(),
            "note": (
                f"Read as of {as_of.isoformat()} in this example. A lesson is held when it stays verified, "
                f"with no recurrence, for {hold_days} days. A recurrence reopens it, and the repeat stays counted."
            ),
        },
        "teams": _team_cards(summary["teams"]),
        "systems": _systems_view(),
        "groups": groups,
        "baseline": {
            "window": "2026 Q1–Q3 example history",
            "current_label": config["quarter_labels"][current],
            "method_steps": config["method_steps"],
            "messy_data": config["messy_data"],
            "definitions": config["definitions"],
            "interviews": config["interviews"],
            "quarters": quarters,
        },
        "inputs": inputs,
    }


def _card(metric_id, label, metric, caption, baseline, current, change, how, example_only=False):
    return {
        "id": metric_id,
        "label": label,
        "baseline": baseline,
        "current_caption": caption,
        "current": current,
        "change": change,
        "how": how,
        "held": metric["held"],
        "baseline_value": metric["baseline_value"],
        "current_value": metric["current_value"],
        "example_only": example_only,
    }


def _area_card(metric):
    areas = []
    for area in metric["areas"]:
        delta = area["current_value"] - area["baseline_value"]
        if abs(delta) < 1e-9:
            change = "No change"
        else:
            change = f"{num(abs(delta))} per 100 {'lower' if delta < 0 else 'higher'}"
        areas.append({
            "name": area["name"],
            "baseline": _per_100(area["baseline_value"], area["unit"]),
            "current": _per_100(area["current_value"], area["unit"]),
            "change": change,
            "held": area["held"],
            "baseline_value": area["baseline_value"],
            "current_value": area["current_value"],
        })
    return {
        "id": "escalation_rate",
        "label": "Escalation rate by product area",
        "current_caption": "This quarter",
        "areas": areas,
        "how": "Escalations per 100 in-scope product actions, by area. The example quarter already includes this practice case once. Each confirmed repeat on the case adds one escalation in its area. A better rate can sit beside a missed repeat target. They answer different questions.",
        "held": metric["held"],
        "example_only": False,
    }


def _days_label(value):
    if value is None:
        return "—"
    amount = num(value)
    return f"{amount} day" if amount == "1" else f"{amount} days"


def _rate_label(value):
    if value is None:
        return "—"
    return _percent(value)


def _team_fact(metric, baseline, current):
    return {
        "baseline": baseline,
        "current": current,
        "held": metric["held"],
        "baseline_value": metric["baseline_value"],
        "current_value": metric["current_value"],
    }


def _team_cards(rows):
    cards = []
    for row in rows:
        repeats = row["repeats"]
        cards.append({
            "owner_type": row["owner_type"],
            "acceptance_rate": _team_fact(row["acceptance_rate"], _rate_label(row["acceptance_rate"]["baseline_value"]), _rate_label(row["acceptance_rate"]["current_value"])),
            "time_to_accept": _team_fact(row["time_to_accept"], _days_label(row["time_to_accept"]["baseline_value"]), _days_label(row["time_to_accept"]["current_value"])),
            "time_to_implement": _team_fact(row["time_to_implement"], _days_label(row["time_to_implement"]["baseline_value"]), _days_label(row["time_to_implement"]["current_value"])),
            "verified_pct": _team_fact(row["verified_pct"], _rate_label(row["verified_pct"]["baseline_value"]), _rate_label(row["verified_pct"]["current_value"])),
            "repeats": _team_fact(
                repeats,
                "—" if repeats["baseline_value"] is None else f"{num(repeats['baseline_value'])} per quarter",
                "—" if repeats["current_value"] is None else num(repeats["current_value"]),
            ),
        })
    return {
        "question": "Did each owner team accept the lesson in its own system, do the work, verify it, and keep it from coming back?",
        "note": "Quarters with no lesson for a team are left out of that team's baseline. Repeats are counted on lessons that were verified. The target is zero.",
        "rows": cards,
    }


def _systems_view(mapping=None):
    mapping = mapping or SYSTEMS
    rows = []
    for key in (*RECORD_FIELDS, "account_context", "public_incident", "scorecard"):
        record = mapping["records"][key]
        rows.append({
            "id": key,
            "label": record["label"],
            "system": record["system"],
            "object": record["object"],
        })
    return {
        "example": True,
        "principle": mapping["principle"],
        "disclaimer": mapping["disclaimer"],
        "rows": rows,
        "owners": [
            {"name": team["name"], "accepts_in": team["accepts_in"]}
            for team in mapping["owner_teams"]
        ],
    }
