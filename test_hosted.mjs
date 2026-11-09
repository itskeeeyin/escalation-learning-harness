import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {advance, caseView} from "./dist/replay.mjs";

const graph = JSON.parse(readFileSync(new URL("./dist/case.json", import.meta.url)));
const report = JSON.parse(readFileSync(process.argv[2]));
assert.equal(report.passed, report.total);
const timestamp = "2026-01-01T00:00:00+00:00";
const stripTimes = events => events.map(({at, step, ...event}) => event);

for (const replay of report.cases) {
  let state = {node: 0, revision: 0, version: 0, audit: [], reviews: []};
  for (const step of replay.steps) {
    const [command, target] = step.command.split(":");
    const apply = () => advance(graph, state, command, target, state.revision, timestamp);
    const label = `${replay.id} / ${step.command}`;
    if (step.error) {
      assert.throws(apply, error => error.message === step.error, label);
    } else {
      const next = apply();
      assert.deepEqual(stripTimes(next.audit.slice(state.audit.length)), stripTimes(step.events), label);
      state = next;
    }
    const view = caseView(graph, state);
    assert.equal(view.stage, step.actual.stage, label);
    assert.equal(view.recovered, step.actual.recovered, label);
    for (const event of view.audit) {
      for (const source of event.sources) assert.ok(view.evidence[source], `${label} / ${source}`);
    }
  }
}
console.log(`Browser replay matches Python for ${report.cases.length} cases.`);
