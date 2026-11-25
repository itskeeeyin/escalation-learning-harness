"""Generate the example lesson-velocity charts.

Reads examples/lesson-velocity.example.json and writes three SVG charts under
docs/images/. Every chart is stamped EXAMPLE DATA. Matplotlib is an optional
developer dependency; see requirements-dev.txt.

    python3 scripts/make_charts.py
    python3 scripts/make_charts.py --data examples/lesson-velocity.example.json --out docs/images
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "examples" / "lesson-velocity.example.json"
DEFAULT_OUT = ROOT / "docs" / "images"

CHARTS = (
    "lesson-velocity-swimlanes.svg",
    "lesson-impact-effort-quadrant.svg",
    "lesson-days-to-impact-by-team.svg",
)

BG = "#0f1420"
PANEL = "#161d2e"
FG = "#e8ecf4"
MUTED = "#8a94a8"
GRID = "#2a3348"
FAST = "#2ec4b6"
SLOW = "#ff9f1c"
STUCK = "#e63946"
STAMP = "EXAMPLE DATA — illustrative only, not real results"

TEAM_LINES = {
    "Support": "Support",
    "Customer Success": "Customer Success",
    "Technical Account Managers (including Strategic TAMs)": "Technical Account Managers\n(including Strategic TAMs)",
    "Solutions Architects": "Solutions Architects",
    "Data center / hardware operations": "Data center /\nhardware operations",
    "Product management": "Product management",
    "Field / professional services engineers": "Field / professional\nservices engineers",
    "Engineering": "Engineering",
}

LESSON_FIELDS = (
    "name", "short_name", "owner", "days_to_accept", "days_to_implement",
    "days_to_impact", "blocker", "status", "effort", "impact",
    "arr_at_risk_k", "age_days",
)
COST_FIELDS = ("repeats_per_month", "hours_per_escalation", "workaround_hours_per_month")


def scorecard_owners():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from measurement import OWNERS
    return [name for name, _blurb in OWNERS]


def load_data(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Example data file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Example data is not valid JSON: {path}: {exc}") from exc
    validate(data)
    return data


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    if value < 0:
        raise ValueError(f"{label} must be zero or positive.")
    return value


def _optional_number(value, label):
    if value is None:
        return None
    return _number(value, label)


def validate(data):
    owners = scorecard_owners()
    lessons = data.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        raise ValueError("lessons must be a non-empty list.")
    codes = data.get("blocked_reason_codes")
    if not isinstance(codes, list) or not codes:
        raise ValueError("blocked_reason_codes must list the allowed blocker codes.")
    allowed = set(codes)
    today = _number(data.get("today"), "today")
    fast_days = _number(data.get("fast_mover_days"), "fast_mover_days")
    _number(data.get("slow_mover_days"), "slow_mover_days")
    _number(data.get("impact_target_days"), "impact_target_days")
    _number(data.get("loaded_hourly_cost"), "loaded_hourly_cost")
    if data.get("days_to_impact_seed") is None:
        raise ValueError("days_to_impact_seed is required so the team chart is reproducible.")
    samples = data.get("days_to_impact_samples")
    if not isinstance(samples, int) or samples < 1:
        raise ValueError("days_to_impact_samples must be a positive integer.")
    clip = data.get("days_to_impact_clip")
    if (
        not isinstance(clip, list) or len(clip) != 2
        or clip[0] < 0 or clip[1] <= clip[0] or clip[1] > 145
    ):
        raise ValueError("days_to_impact_clip must be [low, high] with high <= 145.")
    if data.get("bubble_legend_days") in (None, []):
        raise ValueError("bubble_legend_days must list the age key.")

    seen = set()
    for lesson in lessons:
        for field in LESSON_FIELDS:
            if field not in lesson:
                raise ValueError(f"Lesson {lesson.get('name', '?')!r} is missing {field}.")
        name = lesson["name"]
        if lesson["owner"] not in owners:
            raise ValueError(f"{name} uses an unknown owner team: {lesson['owner']}.")
        if lesson["status"] not in ("done", "open"):
            raise ValueError(f"{name} has an unknown status.")
        blocker = lesson["blocker"]
        if blocker is not None and blocker not in allowed:
            raise ValueError(f"{name} has a blocker that is not in blocked_reason_codes.")
        if lesson["status"] == "open" and not blocker:
            raise ValueError(f"{name} is open and needs a blocked reason code.")
        accept = _number(lesson["days_to_accept"], f"{name} days_to_accept")
        implement = _optional_number(lesson["days_to_implement"], f"{name} days_to_implement")
        impact = _optional_number(lesson["days_to_impact"], f"{name} days_to_impact")
        if implement is None and impact is not None:
            raise ValueError(f"{name} cannot record impact before implementation.")
        if lesson["status"] == "done" and None in (implement, impact):
            raise ValueError(f"{name} is done and needs accept, implement, and impact durations.")
        elapsed = accept + (implement or 0) + (impact or 0)
        if lesson["status"] == "open" and elapsed >= today:
            raise ValueError(f"{name} is open and already extends to today.")
        if lesson["status"] == "done" and blocker is None and elapsed > fast_days:
            raise ValueError(
                f"{name} is a fast mover in the legend but took more than {fast_days:.0f} days."
            )
        effort = _number(lesson["effort"], f"{name} effort")
        impact_score = _number(lesson["impact"], f"{name} impact")
        if not 0 <= effort <= 10 or not 0 <= impact_score <= 20:
            raise ValueError(f"{name} effort must be 1–10 and impact 0–20 for the quadrant axes.")
        _number(lesson["arr_at_risk_k"], f"{name} arr_at_risk_k")
        _number(lesson["age_days"], f"{name} age_days")
        present = [lesson.get(field) is not None for field in COST_FIELDS]
        if any(present) and not all(present):
            raise ValueError(f"{name} needs all three cost-of-delay inputs, or none.")
        for field in COST_FIELDS:
            if lesson.get(field) is not None:
                _number(lesson[field], f"{name} {field}")
        seen.add(lesson["owner"])

    missing = [name for name in owners if name not in seen]
    if missing:
        raise ValueError("Every scorecard owner team needs at least one example lesson: " + ", ".join(missing))

    rows = data.get("days_to_impact_by_team")
    if not isinstance(rows, list) or [row.get("owner") for row in rows] != owners:
        raise ValueError(
            "days_to_impact_by_team must list the scorecard owner teams, in scorecard order."
        )
    for row in rows:
        _number(row.get("center"), f"{row.get('owner')} center")
        _number(row.get("spread"), f"{row.get('owner')} spread")


def require_plotting():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required to generate lesson-velocity charts.\n"
            "Install the optional chart dependency: python3 -m pip install -r requirements-dev.txt"
        ) from exc
    plt.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor": PANEL,
        "axes.edgecolor": GRID,
        "text.color": FG,
        "axes.labelcolor": FG,
        "xtick.color": MUTED,
        "ytick.color": FG,
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "svg.fonttype": "none",
    })
    return plt, Patch, np


def stamp(fig):
    fig.text(
        0.985, 0.975, "EXAMPLE DATA",
        ha="right", va="top", fontsize=13, color=SLOW, fontweight="bold",
    )
    fig.text(
        0.99, 0.012, STAMP,
        ha="right", va="bottom", fontsize=10, color=SLOW, fontweight="bold",
    )
    fig.text(
        0.012, 0.012, "escalation-learning-harness · lesson velocity",
        ha="left", va="bottom", fontsize=9, color=MUTED,
    )


def titles(fig, title, subtitle):
    fig.suptitle(title, x=0.02, ha="left", fontsize=18, fontweight="bold", y=0.968, color=FG)
    fig.text(0.02, 0.908, subtitle, fontsize=10.5, color=MUTED)


def save_svg(fig, path, title):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        format="svg",
        facecolor=fig.get_facecolor(),
        metadata={
            "Title": title,
            "Description": STAMP,
        },
    )


def _style_axes(ax):
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _money(thousands):
    if thousands >= 1000:
        millions = thousands / 1000
        text = f"{millions:.1f}".rstrip("0").rstrip(".")
        return f"${text}M"
    return f"${thousands:.0f}k"


def _elapsed(lesson):
    total = lesson["days_to_accept"]
    for key in ("days_to_implement", "days_to_impact"):
        if lesson[key] is None:
            break
        total += lesson[key]
    return total


def chart_swimlanes(data, plt, np, patch):
    lessons = []
    by_owner = {owner: [] for owner in scorecard_owners()}
    for lesson in data["lessons"]:
        by_owner[lesson["owner"]].append(lesson)
    for owner in scorecard_owners():
        lessons.extend(by_owner[owner])

    fig, ax = plt.subplots(figsize=(18, 11))
    fig.subplots_adjust(left=0.40, right=0.985, top=0.86, bottom=0.15)
    shade = {"accept": 0.95, "impl": 0.70, "impact": 0.45}
    y = len(lessons) - 1
    positions = []
    labels = []
    groups_y = {}
    today = data["today"]
    for lesson in lessons:
        blocker = lesson["blocker"]
        if blocker is None:
            color = FAST
        elif lesson["status"] == "open":
            color = STUCK
        else:
            color = SLOW
        x = 0
        for key, band in (
            ("days_to_accept", "accept"),
            ("days_to_implement", "impl"),
            ("days_to_impact", "impact"),
        ):
            duration = lesson[key]
            if duration is None:
                break
            ax.barh(
                y, duration, left=x, height=0.62, color=color, alpha=shade[band],
                edgecolor=BG, linewidth=1.5,
            )
            x += duration
        if lesson["status"] == "open":
            ax.barh(
                y, today - x, left=x, height=0.62, color="none", edgecolor=color,
                hatch="///", linewidth=0.8, alpha=0.9,
            )
            ax.text(
                today + 1.6, y, f"BLOCKED: {blocker}",
                va="center", fontsize=10, color=color, fontweight="bold", clip_on=False,
            )
        else:
            ax.plot(x, y, marker="D", color=FG, ms=7, zorder=5)
            note = f"{x:.0f} days to impact"
            if blocker:
                note += f"  ·  slowed by {blocker}"
            ax.text(
                x + 1.6, y, note, va="center", fontsize=9.5,
                color=SLOW if blocker else MUTED, clip_on=False,
            )
        groups_y.setdefault(lesson["owner"], []).append(y)
        positions.append(y)
        labels.append(lesson["name"])
        y -= 1

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=10)
    ax.tick_params(axis="y", length=0, pad=4)
    for ys in groups_y.values():
        boundary = min(ys) - 0.5
        ax.axhline(boundary, color=GRID, lw=1)
    ax.axvline(today, color=MUTED, ls="--", lw=1)
    ax.text(today, len(lessons) - 0.58, "today", ha="center", va="bottom", color=MUTED, fontsize=9)
    ax.set_xlim(0, 188)
    ax.set_ylim(-0.7, len(lessons) - 0.28)
    ax.set_xlabel("Days since the lesson was verified")
    _style_axes(ax)
    titles(
        fig,
        "Lesson velocity: from verified lesson to measurable customer impact",
        "Example lessons. Each bar: verified → accepted by the owner team (darkest) → implemented → customer impact measured (lightest).  ◆ = impact confirmed.  Hatched = still waiting.",
    )
    fast_days = int(data["fast_mover_days"])
    legend = [
        patch(color=FAST, label=f"Fast mover (≤ {fast_days} days)"),
        patch(color=SLOW, label="Lagged, then landed"),
        patch(color=STUCK, label="Stalled — blocker named"),
        patch(facecolor="none", edgecolor=FG, hatch="///", label="Open time to date"),
    ]
    ax.legend(
        handles=legend, loc="upper center", bbox_to_anchor=(0.48, -0.08), ncol=4,
        facecolor=PANEL, edgecolor=GRID, labelcolor=FG, fontsize=10,
    )
    fig.canvas.draw()
    for owner, ys in groups_y.items():
        _x_disp, y_disp = ax.transData.transform((0.0, float(np.mean(ys))))
        _x_fig, y_fig = fig.transFigure.inverted().transform((0.0, y_disp))
        fig.text(
            0.012, y_fig, TEAM_LINES.get(owner, owner),
            ha="left", va="center", fontsize=10.5, fontweight="bold",
            color=SLOW, linespacing=1.15,
        )
    stamp(fig)
    return fig


# Point labels sit beside the bubble. Offsets are points, tuned for this example set.
QUADRANT_LABELS = {
    "Health review on repeats": dict(xytext=(-30, 0), ha="right", va="center"),
    "Quota pre-flight validator": dict(xytext=(0, 36), ha="center", va="bottom"),
    "Onboarding config linter": dict(xytext=(58, 8), ha="left", va="center"),
    "UI cosmetic in console": dict(xytext=(-30, 0), ha="right", va="center"),
    "Capacity-planning playbook": dict(xytext=(46, 0), ha="left", va="center"),
    "NIC firmware link flaps": dict(xytext=(0, -42), ha="center", va="top"),
    "Scheduler preemption bug": dict(xytext=(50, -2), ha="left", va="center"),
    "Renewal-risk warning": dict(xytext=(-10, 0), ha="right", va="center"),
    "Driver timeout fix": dict(xytext=(12, 0), ha="left", va="center"),
    "Health-check script": dict(xytext=(12, 0), ha="left", va="center"),
    "Log bundle collector": dict(xytext=(10, -8), ha="left", va="top"),
    "Comms template": dict(xytext=(-8, 0), ha="right", va="center"),
    "Storage detach race": dict(xytext=(12, 0), ha="left", va="center"),
}


def chart_quadrant(data, plt):
    import matplotlib.patheffects as path_effects
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.subplots_adjust(left=0.07, right=0.78, top=0.86, bottom=0.12)
    ax.set_xlim(-0.25, 11.2)
    ax.set_ylim(-0.15, 21.1)
    ax.set_xticks(range(0, 11, 2))
    ax.axvline(5, color=GRID, lw=1.5)
    ax.axhline(10, color=GRID, lw=1.5)
    ax.fill_between([0, 5], 10, 21.1, color=STUCK, alpha=0.07)
    labels = [
        (2.5, 20.7, "QUICK WINS + NEGLECTED HIGH-IMPACT\nlow effort, high impact — why are these still open?", STUCK, "top"),
        (7.5, 20.7, "STRATEGIC BETS\nneed an exec sponsor and a roadmap slot", SLOW, "top"),
        (2.15, 0.35, "BUNDLE / BATCH\nsmall fixes, ship together", FAST, "bottom"),
        (8.15, 0.35, "PARK / LET GO\nrevisit if repeats grow", MUTED, "bottom"),
    ]
    for x, y, text, color, valign in labels:
        ax.text(
            x, y, text, ha="center", va=valign, fontsize=10.5, color=color,
            fontweight="bold", linespacing=1.35,
        )
    halo = [path_effects.withStroke(linewidth=3, foreground=PANEL)]
    for lesson in data["lessons"]:
        effort = lesson["effort"]
        impact = lesson["impact"]
        if lesson["status"] == "done":
            color = FAST
        elif impact >= 10 and effort < 5:
            color = STUCK
        elif impact >= 10:
            color = SLOW
        else:
            color = MUTED
        ax.scatter(
            effort, impact, s=lesson["age_days"] * 28 + 60, color=color,
            alpha=0.55 if lesson["status"] == "open" else 0.35,
            edgecolor=color, linewidth=1.5, zorder=3,
        )
        if lesson["status"] == "open":
            label = f"{lesson['short_name']}\n{_money(lesson['arr_at_risk_k'])} ARR at risk"
        else:
            label = lesson["short_name"]
        place = QUADRANT_LABELS.get(lesson["short_name"], {})
        note = ax.annotate(
            label, (effort, impact),
            xytext=place.get("xytext", (0, 0)), textcoords="offset points",
            ha=place.get("ha", "center"), va=place.get("va", "center"),
            fontsize=8.4, color=FG, zorder=4, linespacing=1.15, clip_on=False,
        )
        note.set_path_effects(halo)
    ax.set_xlabel("Effort / complexity to implement (1 = small change, 10 = architecture work)")
    ax.set_ylabel("Customer impact (repeat escalations per quarter if not fixed)")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    titles(
        fig,
        "Which lessons deserve focus: customer impact vs. effort",
        "Example lessons. Bubble size = days the lesson has sat in the backlog.  Teal = already shipped.  Red = open, high impact, low effort: the neglected backlog to push first.",
    )
    for age in data["bubble_legend_days"]:
        ax.scatter([], [], s=age * 28 + 60, color=MUTED, alpha=0.4, label=f"{int(age)} days")
    legend = ax.legend(
        title="Age in backlog", loc="upper left", bbox_to_anchor=(1.02, 0.78),
        facecolor=PANEL, edgecolor=GRID, labelcolor=FG, labelspacing=3.2,
        borderpad=1.8, handletextpad=2.0, fontsize=10,
    )
    legend.get_title().set_color(FG)
    fig.text(
        0.80, 0.30,
        "Cost of delay (example)\n"
        "= repeat escalations × hrs each\n"
        "   × loaded hourly cost\n"
        "+ ARR at risk × churn odds",
        fontsize=10, color=MUTED, va="top", linespacing=1.5,
    )
    stamp(fig)
    return fig


def chart_days(data, plt, np):
    spec = data["days_to_impact_by_team"]
    rng = np.random.default_rng(data["days_to_impact_seed"])
    count = data["days_to_impact_samples"]
    low, high = data["days_to_impact_clip"]
    samples = [
        np.clip(rng.normal(row["center"], row["spread"], count), low, high)
        for row in spec
    ]
    order = list(np.argsort([float(np.median(sample)) for sample in samples]))
    fast_days = data["fast_mover_days"]
    slow_days = data["slow_mover_days"]
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.subplots_adjust(left=0.24, right=0.96, top=0.86, bottom=0.12)
    for row, idx in enumerate(order):
        sample = samples[idx]
        median = float(np.median(sample))
        if median <= fast_days:
            color = FAST
        elif median <= slow_days:
            color = SLOW
        else:
            color = STUCK
        jitter = row + rng.uniform(-0.18, 0.18, len(sample))
        ax.scatter(sample, jitter, color=color, alpha=0.65, s=40, zorder=3)
        ax.plot(
            [np.percentile(sample, 25), np.percentile(sample, 75)],
            [row, row], color=color, lw=8, alpha=0.35, solid_capstyle="round",
        )
        ax.plot(median, row, "|", color=FG, ms=22, mew=3, zorder=4)
        ax.text(
            166, row, f"median {median:.0f} d",
            va="center", ha="right", color=color, fontsize=11, fontweight="bold",
        )
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(
        [TEAM_LINES.get(spec[idx]["owner"], spec[idx]["owner"]) for idx in order],
        fontsize=11,
    )
    target = data["impact_target_days"]
    ax.axvline(target, color=SLOW, ls="--", lw=1.2)
    # The fast teams sit at the bottom and finish left of the target line,
    # so the label has a clear lane on the lowest row.
    ax.text(
        target + 1.5, 0.28,
        f"example target: impact within {int(target)} days of verification",
        color=SLOW, fontsize=10, va="bottom", ha="left",
    )
    ax.set_xlim(0, 168)
    ax.set_ylim(-0.75, len(order) - 0.15)
    ax.set_xlabel("Days from verified lesson to measured customer impact")
    _style_axes(ax)
    titles(
        fig,
        "Days to customer impact, by owner team",
        f"Example distribution. Each dot is one synthetic lesson ({count} per team).  Band = middle 50%.  White tick = median.  Process lessons land fast. Code, roadmap, and hardware lessons lag.",
    )
    stamp(fig)
    return fig


def render(data, plt, patch, np):
    charts = (
        (CHARTS[0], "Lesson velocity swimlanes", chart_swimlanes(data, plt, np, patch)),
        (CHARTS[1], "Impact versus effort", chart_quadrant(data, plt)),
        (CHARTS[2], "Days to impact by team", chart_days(data, plt, np)),
    )
    return charts


def write_charts(charts, out_dir, plt):
    out_dir = Path(out_dir)
    written = []
    for name, title, fig in charts:
        path = out_dir / name
        save_svg(fig, path, title)
        written.append(path)
        plt.close(fig)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate example lesson-velocity charts.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Example JSON input.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Directory for the SVG charts.")
    args = parser.parse_args(argv)
    try:
        data = load_data(args.data)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    plt, patch, np = require_plotting()
    written = write_charts(render(data, plt, patch, np), args.out, plt)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
