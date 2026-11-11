"""Build a static replay of the synthetic case using the Python workflow as its rules."""
import copy
import json
from pathlib import Path

from harness import DATA, Harness, ReviewError
from integrations.replay import cross_tool_replay

ROOT = Path(__file__).resolve().parent
COMMANDS = (
    "reveal", "confirm_priority", "approve", "revise", "inject_restore", "original",
    "load_resolution", "confirm_recovery", "learn", "approve_plan", "load_proof", "close",
    "start_picker", "inspect_picker", "route_picker", "route_as_discard", "recover_picker",
    "return_proof", "resubmit_proof",
)
ACTIONS = [(command, None) for command in COMMANDS] + [
    ("verify", row["id"]) for row in DATA["actions"]
] + [("load_signal", key) for key in DATA["review_signals"]] + [
    ("decide_signal", choice) for choice in ("separate", "repeat")
]


def replay_graph():
    """Enumerate the reachable states, leaving counters and history to the browser."""
    states, nodes, indexes = [], [], {}
    values, value_indexes = [], {}

    def intern(value):
        key = json.dumps(value, sort_keys=True)
        if key not in value_indexes:
            value_indexes[key] = len(values)
            values.append(value)
        return value_indexes[key]

    def add_state(state):
        state.revision = 0
        state.audit = []
        version = state.triage.version
        decision = state.triage.audit[-1] if state.triage.audit else None
        if decision and decision["version"] == version:
            state.triage.audit = [{**decision, "version": 1, "timestamp": None}]
        else:
            state.triage.audit = []
        state.triage.version = int(bool(version))
        view = state.view()
        key = json.dumps(view, sort_keys=True)
        if key not in indexes:
            indexes[key] = len(states)
            states.append(state)
            nodes.append({"view": {name: intern(value) for name, value in view.items()}, "next": {}})
        return indexes[key]

    add_state(Harness())
    for index, current in enumerate(states):
        for command, action_id in ACTIONS:
            key = f"{command}:{action_id}" if action_id else command
            candidate = copy.deepcopy(current)
            try:
                candidate.apply(command, candidate.revision, action_id)
            except ReviewError as error:
                nodes[index]["next"][key] = str(error)
                continue
            events = [
                {name: event[name] for name in ("actor", "summary", "sources")}
                for event in candidate.audit
            ]
            version_delta = candidate.triage.version - current.triage.version
            nodes[index]["next"][key] = [add_state(candidate), version_delta, events]
    return {"values": values, "nodes": nodes}


def build():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    html = (ROOT / "web/index.html").read_text()
    html = html.replace('href="/style.css"', 'href="./style.css"')
    html = html.replace('<script defer src="/app.js"></script>', '<script type="module" src="./app.js"></script>')
    html = html.replace("LOCAL PRACTICE", "INTERACTIVE DEMO")
    html = html.replace(
        "Synthetic case, simulated evidence, and local reviewer decisions.",
        "Fictional case. Decisions stay in this browser tab.",
    )
    html = html.replace(
        '<div><a href="/integrations.html">Sample tool replay</a> · '
        '<a href="https://github.com/itskeeeyin/runbook-copilot">',
        '<div><a href="./integrations.html">Sample tool replay</a> · '
        '<a href="https://github.com/itskeeeyin/escalation-learning-harness">Source code</a> · '
        '<a href="https://github.com/itskeeeyin/escalation-learning-harness/blob/main/docs/demo-guide.md">'
        'Walkthrough</a> · <a href="https://github.com/itskeeeyin/escalation-learning-harness/blob/main/docs/iteration.md">'
        'What changed</a> · <a href="https://github.com/itskeeeyin/runbook-copilot">',
    )
    (dist / "index.html").write_text(html, encoding="utf-8")
    (dist / "style.css").write_bytes((ROOT / "web/style.css").read_bytes())
    app = (ROOT / "web/app.js").read_text()
    start = app.index('  const method = command ?')
    end = app.index('    render();', start)
    app = app[:start] + (
        '  app.setAttribute("aria-busy", "true");\n'
        '  try {\n'
        '    view = await hostedSession(command, id, view?.revision);\n'
    ) + app[end:]
    (dist / "app.js").write_text('import {hostedSession} from "./replay.mjs";\n\n' + app, encoding="utf-8")
    (dist / "replay.mjs").write_bytes((ROOT / "hosted/replay.mjs").read_bytes())
    graph = replay_graph()
    (dist / "case.json").write_text(json.dumps(graph, separators=(",", ":")), encoding="utf-8")
    page = (ROOT / "web/integrations.html").read_text(encoding="utf-8")
    page = page.replace('href="/style.css"', 'href="./style.css"')
    (dist / "integrations.html").write_text(page, encoding="utf-8")
    (dist / "integrations.json").write_text(
        json.dumps(cross_tool_replay(DATA["actions"])), encoding="utf-8"
    )
    print(f"Generated {len(graph['nodes'])} reachable states.")


if __name__ == "__main__":
    build()
