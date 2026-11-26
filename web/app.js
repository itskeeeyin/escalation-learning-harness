const app = document.querySelector("#app");
const notice = document.querySelector("#notice");
const dialog = document.querySelector("#source-dialog");
const stages = ["Engage", "Coordinate", "Learn", "Verify", "Closed", "Measure"];
const ownerClass = {
  "Support": "owner-sup",
  "Customer Success": "owner-cs",
  "Technical Account Managers (including Strategic TAMs)": "owner-tam",
  "Solutions Architects": "owner-sa",
  "Data center / hardware operations": "owner-dc",
  "Product management": "owner-docs",
  "Field / professional services engineers": "owner-field",
  "Engineering": "owner-eng",
};
let view;
let pending = false;
let noticeTimer;

const showNotice = (text) => {
  notice.textContent = text || "";
  clearTimeout(noticeTimer);
  if (text) noticeTimer = setTimeout(() => { notice.textContent = ""; }, 6000);
};

const escape = (value) => String(value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[char]);

const button = (command, label, primary = false, id = "") =>
  `<button type="button" data-command="${command}" data-id="${id}" class="${primary ? "primary" : ""}">${label}</button>`;

const sources = (ids) => ids.length ? `<div class="chips" aria-label="Evidence references">${ids.map(id =>
  `<button type="button" class="chip" data-source="${escape(id)}" aria-label="Read evidence ${escape(id)}">${escape(id)}</button>`
).join("")}</div>` : "";

function picker() {
  const phase = view.picker_stage;
  const next = {
    Reported: button("inspect_picker", "Inspect publish and filter evidence", true),
    Evidence: button("route_picker", "Route to launch-picker Support", true) +
      button("route_as_discard", "Try routing as a draft discard"),
    Routed: button("recover_picker", "Confirm launch readiness", true),
    Recovered: "",
  };
  const details = {
    Reported: "An administrator cannot find a template before a planned launch.",
    Evidence: "The template was published in Compliance. Support found it after correcting the launch picker’s solution filter.",
    Routed: "Launch-picker Support owns the follow-up. Replay the customer’s test launch before confirming recovery.",
    Recovered: "The customer completed a test launch with the correct filter. This case stays separate from draft-discard recurrence.",
  };
  return `<section class="panel"><div class="label">${escape(view.case_id)} / ${escape(view.customer)}</div>
    <h2>Missing template in the launch picker</h2><p>${details[phase]}</p>
    ${sources(Object.keys(view.evidence))}
    <div class="controls">${next[phase]}</div></section>`;
}

function engagement() {
  if (view.picker_stage) return picker();
  const t = view.triage;
  if (view.recovered) {
    return `<details class="panel"><summary><strong>Customer recovery confirmed</strong></summary>
      <p>Support validated the rebuilt template and the customer accepted the outcome.</p>${sources(["R1", "R2"])}
      <blockquote>${escape(t.preview)}</blockquote></details>`;
  }
  const currentDraft = t.draft;
  const invalid = currentDraft.validation.find(check => !check.approval_allowed);
  return `<section class="panel" aria-labelledby="recovery-heading">
    <div class="label">${escape(view.case_id)} / ${escape(view.customer)}</div>
    <h2 id="recovery-heading">${escape(t.case.symptom)}</h2>
    <p>${t.confirmed ? "Telemetry confirms a draft discard. Rebuild from the requirements worksheet and validate routing." :
      "The administrator’s report is the starting point. Confirm the event and rollout impact before assigning priority."}</p>
    ${sources(t.confirmed ? ["E1", "E2", "E3", "KB1-F1", "KB1-F2"] : ["E1", "KB2-F1", "KB2-F2", "KB2-F3"])}
    ${!t.confirmed ? `<div class="controls">${button("reveal", "Run triage agent", true)}${button("start_picker", "Try the launch-picker case")}</div>` : `
      <div class="note sub"><strong>Rebuild owner</strong> · ${escape(t.follow_up.owner)} with Support validation. Functional escalation to Support.
      <br><strong>Open scope question</strong> · Impact on previously launched assessments.</div>
      ${t.triage.priority ? `<div class="note"><strong>Example priority</strong> · ${escape(t.triage.priority)} from impact ${escape(t.triage.impact)} × urgency ${escape(t.triage.urgency)}. ${escape(t.triage.priority_basis)} P1 on this matrix is the major-incident cell and is not this case.</div>` : `<div class="warning">${escape(t.triage.failure_message || "Impact or urgency is still unverified.")}</div>`}
      <h3>Customer update · v${currentDraft.version}</h3>
      <p>${escape(currentDraft.claims.map(claim => claim.text).join(" "))}</p>
      <p class="sub">${escape(currentDraft.commitment.text)}</p>
      ${invalid ? `<div class="warning" role="alert">Approval blocked · ${escape(invalid.failure_code.replaceAll("_", " ").toLowerCase())}.${sources(invalid.supporting_citation_ids || [])}</div>` : ""}
      ${t.preview ? `<p class="success sub">Approved customer preview · v${currentDraft.version}</p>` :
        `<p class="note sub">Customer preview locked · ${t.priority_confirmed ? "awaiting draft approval" : "awaiting priority confirmation"}</p>`}
      <div class="controls">
        ${!t.priority_confirmed ? button("confirm_priority", "Confirm P2", true) : ""}
        ${!invalid && t.priority_confirmed && !t.preview ? button("approve", "Approve customer draft", true) : ""}
        ${invalid ? button("original", "Restore supported wording", true) :
          button("inject_restore", "Try unsupported restore claim") + (t.preview ? button("revise", "Revise wording") : "")}
        ${t.preview && !view.resolution_available ? button("load_resolution", "Replay recovery evidence", true) : ""}
      </div>
      ${view.resolution_available ? `<div class="note"><h3>Recovery evidence</h3>
        <p class="sub">Support validated 18 questions and both routing paths. The customer accepted the outcome.</p>${sources(["R1", "R2"])}
        ${t.preview ? `<div class="controls">${button("confirm_recovery", "Confirm customer recovery", true)}</div>` : ""}</div>` : ""}
    `}
  </section>`;
}

function verificationControl(action) {
  if (!view.proof_available || action.state === "Verified") return "";
  if (action.state === "Needs rework") {
    return button("resubmit_proof", "Replay revised Engineering evidence", true);
  }
  if (action.id === "ENG" && !action.proof_ready) {
    return button("return_proof", "Return incomplete Engineering proof", true);
  }
  if (action.id === "EXEC" && view.actions.some(row => row.id !== "EXEC" && row.state !== "Verified")) {
    return '<span class="sub muted">Waiting for team verification</span>';
  }
  return button("verify", `Verify ${escape(action.team)}`, false, escape(action.id));
}

function actionCard(action) {
  const control = verificationControl(action);
  return `<article class="action">
    <div class="row"><span class="label">${escape(action.team)}</span><span class="status ${action.state !== "Verified" ? "pending" : ""}">${escape(action.state)}</span></div>
    <h3>${escape(action.title)}</h3>
    <p><strong>${escape(action.kind)}</strong> · ${escape(action.escalation === "hierarchical" ? "Hierarchical escalation" : "Functional escalation")} · ${escape(action.owner)} · Due ${escape(action.due)}</p>
    ${action.change_id ? `<p><strong>${escape(action.change_id)}</strong> · ${escape(String(action.change_state).replaceAll("_", " "))} · effectiveness is required before close</p>` : ""}
    <p><strong>Acceptance</strong> · ${escape(action.criterion)}</p>
    ${sources(action.sources)}
    ${action.proof ? `<p class="proof"><strong>Simulated evidence</strong> · ${escape(action.proof)}</p>` : ""}
    ${action.proof_source ? sources([action.proof_source]) : ""}
    ${control ? `<div class="controls">${control}</div>` : ""}
  </article>`;
}

function recurrenceReview() {
  const review = view.learning_review;
  if (!review) return "";
  const reports = [["a", "A"], ["b", "B"]];
  return `<section class="panel" aria-labelledby="recurrence-heading">
    <div class="label">POST-CLOSURE CHECK</div><h2 id="recurrence-heading">30-day recurrence review</h2>
    <p>Compare the product surface and confirmed mechanism before reopening preventive work.</p>
    ${reports.map(([key, label]) => review.decisions[key] ?
      `<p><strong>Report ${label}</strong> · ${escape(review.decisions[key])}</p>` : "").join("")}
    ${review.reopened ? '<p class="note">The original customer stays recovered. Engineering and executive sign-off are open again.</p>' : ""}
    ${review.active ? `<div class="note">${escape(view.evidence[review.active][1])}${sources([review.active])}</div>
      <div class="controls">${button("decide_signal", "Keep as a separate issue", false, "separate")}
      ${button("decide_signal", "Confirm repeat and reopen", false, "repeat")}</div>` : ""}
    ${view.stage === "Closed" && !review.active ? `<div class="controls">${reports.map(([key, label]) =>
      review.decisions[key] ? "" : button("load_signal", `Load report ${label}`, false, key)).join("")}</div>` : ""}
  </section>`;
}

function recordsPanel() {
  const records = view.records;
  if (!records || view.picker_stage) return "";
  const problem = records.problem;
  const known = records.known_error;
  const database = records.known_error_database || [];
  return `<section class="panel" aria-labelledby="records-heading">
    <div class="label">EXAMPLE RECORDS · HOW THIS FLOW MAPS TO ITIL 4</div>
    <h2 id="records-heading">Incident closed, problem still open</h2>
    <p>${escape(records.label)}</p>
    <p><strong>${escape(records.incident.id)}</strong> · ${escape(records.incident.state)} · ServiceNow ${escape(records.incident.servicenow_number || "")}</p>
    ${problem ? `<p><strong>${escape(problem.id)}</strong> · ${escape(problem.state)} · ${escape(problem.phase.replaceAll("_", " "))}</p>` :
      `<p>The problem record opens when recovery closes the incident.</p>`}
    ${known ? `<p><strong>${escape(known.id)}</strong> · ${escape(known.status.replaceAll("_", " "))} · ${escape(known.workaround)}</p>` : ""}
    ${database.length ? `<p class="sub"><strong>${escape(database[0].id)}</strong> · ${escape(database[0].title)}</p>` : ""}
    ${(view.changes || []).length ? `<ul class="clean">${view.changes.map(change => `<li><strong>${escape(change.id)}</strong> · ${escape(change.kind)} · ${escape(change.state.replaceAll("_", " "))}</li>`).join("")}</ul>` : ""}
    ${(view.handoffs || []).length ? `<p class="sub">${view.handoffs.filter(row => row.escalation === "hierarchical").length} hierarchical and ${view.handoffs.filter(row => row.escalation === "functional").length} functional handoffs in this replay.</p>` : ""}
  </section>`;
}

function learning() {
  if (!view.recovered || view.picker_stage) return "";
  const havePlan = view.actions.length > 0;
  const outstanding = view.actions.filter(row => row.state !== "Verified").length;
  return `<section class="panel" aria-labelledby="learning-heading">
    <div class="label">CROSS-FUNCTIONAL FOLLOW-UP</div><h2 id="learning-heading">Turn the incident into improvements</h2>
    ${!havePlan ? `<p>Review the cause, look for earlier cases with the same mechanism, and route the findings to accountable owners.</p>
      <div class="controls">${button("learn", "Run learning agents", true)}</div>` : `
      <p><strong>Confirmed cause</strong> · The draft was discarded. <strong>Contributing factor</strong> · The prompt omitted the draft name and the permanent loss of configuration in a test copy.</p>
      ${sources(["E2", "R3"])}
      <details class="note" open><summary><strong>${view.history.filter(row => row.match).length} prior matches</strong> · confirmed discard in template authoring</summary>
        <ul class="clean">${view.history.map(row => `<li><strong>${escape(row.id)}</strong> · ${row.match ? "Same mechanism" : "Excluded · similar symptom, mechanism unconfirmed"}${sources([row.source])}</li>`).join("")}</ul>
      </details>
      <div class="actions">${view.actions.map(actionCard).join("")}</div>
      <div class="controls">
        ${view.stage === "Learn" ? button("approve_plan", "Approve follow-up plan", true) : ""}
        ${view.stage === "Verify" && !view.proof_available ? button("load_proof", "Replay completion evidence", true) : ""}
        ${view.stage === "Verify" && !outstanding ? button("close", "Close learning loop", true) : ""}
        ${view.stage === "Verify" && outstanding ? `<span class="sub muted">Closure locked · ${outstanding} actions await verification</span>` : ""}
      </div>
      ${view.stage === "Closed" ? `<p class="success">Learning closed · owners verified that the changes were effective, not only completed. The problem can close. ${escape(view.learning_review.owner)} will review recurrence in ${view.learning_review.interval_days} days. The influence scorecard below is example data from this decision record.</p>` : ""}
    `}
  </section>`;
}

function executive() {
  const brief = view.executive;
  return `<section class="panel brief"><div class="label">STAKEHOLDER BRIEF · INTERNAL DRAFT</div><h2>Executive update</h2>
    <p><strong>${escape(brief.priority)}</strong> · ${escape(brief.status)}</p>
    <p class="sub"><strong>Decision</strong> · ${escape(brief.decision)}</p>
    <p class="sub"><strong>Next checkpoint</strong> · ${escape(brief.next)}</p>
    ${sources(brief.sources)}</section>`;
}

function audit() {
  return `<section class="panel"><div class="header-row"><div><div class="label">DECISION HISTORY</div><h2>Agent & reviewer trace</h2></div>
    ${button("export", "Export JSON")}</div>
    <p class="sub">The export includes the incident, the problem, the known error, the known error database entry, and the change requests.</p>
    ${view.audit.length ? `<ol class="clean">${[...view.audit].reverse().map(event => `<li class="event">
      <span class="step-id">${String(event.step).padStart(2, "0")}</span><div><strong>${escape(event.actor)}</strong>
      <p>${escape(event.summary)}</p>${sources(event.sources)}</div></li>`).join("")}</ol>` :
      '<p class="sub">Evidence reads, proposals, approvals, and verification decisions will appear here.</p>'}
  </section>`;
}

function lessonLine(lesson) {
  const missed = lesson.recurrence === "reopened";
  const quiet = lesson.status === "Verified" || lesson.status === "Held";
  const link = lesson.accepted_link ? `<p class="sub">Link back <code class="example-link">${escape(lesson.accepted_link)}</code></p>` : "";
  return `<li><strong>${escape(lesson.title)}</strong>
    <p><span class="status${quiet && !missed ? "" : " pending"}">${escape(lesson.status)}</span>
    <span class="scope-chip">${escape(lesson.scope_label)}</span> · ${escape(lesson.action_type)} · ${escape(lesson.when)}</p>${link}</li>`;
}

function teamFact(label, fact) {
  return `<p><span class="scope-chip">${escape(label)}</span> ${escape(fact.current)} <span class="muted">baseline ${escape(fact.baseline)}</span>
    · <span class="status${fact.held ? "" : " pending"}">${fact.held ? "Held" : "Not held"}</span></p>`;
}

function metricNumbers(metric) {
  if (metric.areas) {
    return `<ul class="clean">${metric.areas.map(area => `<li><strong>${escape(area.name)}</strong>
      <p>Baseline ${escape(area.baseline)}</p>
      <p>${escape(metric.current_caption)} ${escape(area.current)} · ${escape(area.change)}</p></li>`).join("")}</ul>`;
  }
  return `<dl>
    <div><dt>Baseline</dt><dd>${escape(metric.baseline)}</dd></div>
    <div><dt>${escape(metric.current_caption)}</dt><dd>${escape(metric.current)}</dd></div>
    <div><dt>Change</dt><dd>${escape(metric.change)}</dd></div>
  </dl>`;
}

function scorecardPanel(score) {
  const owners = score.owners.map(owner => `<article class="owner-card ${ownerClass[owner.owner_type] || ""}">
    <div class="label">${escape(owner.owner_type)}</div>
    <p class="sub">${escape(owner.blurb)}</p>
    ${owner.lessons.length ? `<ul class="clean">${owner.lessons.map(lessonLine).join("")}</ul>` : `<p class="sub">No lesson in this example quarter.</p>`}
  </article>`).join("");
  const groups = score.groups.map(group => `<section class="score-group" aria-labelledby="group-${group.id}">
    <h3 id="group-${group.id}">${escape(group.title)}</h3>
    <p>${escape(group.question)}</p>
    <div class="metric-grid">${group.metrics.map(metric => `<article class="metric-card">
      <div class="row"><p class="metric-name">${escape(metric.label)}</p>
        <span class="statuses">${metric.example_only ? `<span class="status pending">Example figure</span>` : ""}
        <span class="status${metric.held ? "" : " pending"}">${metric.held ? "Held" : "Not held"}</span></span></div>
      ${metricNumbers(metric)}
      <p class="sub"><strong>How it is measured.</strong> ${escape(metric.how)}</p>
    </article>`).join("")}</div>
  </section>`).join("");
  const teams = score.teams.rows.map(team => `<article class="owner-card ${ownerClass[team.owner_type] || ""}">
    <div class="label">${escape(team.owner_type)}</div>
    ${teamFact("Acceptance", team.acceptance_rate)}
    ${teamFact("Time to accept", team.time_to_accept)}
    ${teamFact("Time to implement", team.time_to_implement)}
    ${teamFact("Verified", team.verified_pct)}
    ${teamFact("Repeats", team.repeats)}
  </article>`).join("");
  const systems = score.systems.rows.map(row => `<li><strong>${escape(row.label)}</strong> · ${escape(row.system)}<p class="sub">${escape(row.object)}</p></li>`).join("");
  const quarters = score.baseline.quarters.map(quarter => `<article class="quarter-card">
    <div class="label">${escape(quarter.label)}</div>
    <p>${escape(quarter.lessons_closed)} lessons closed</p>
    <p>${escape(quarter.repeats)} repeat${quarter.repeats === "1" ? "" : "s"}</p>
    <p>${escape(quarter.routed_on_time)} routed on time</p>
    <p>Template authoring ${escape(quarter.template_rate)}</p>
  </article>`).join("");
  return `<section class="panel scorecard" id="influence-scorecard" aria-labelledby="score-heading">
    <div class="label">EXAMPLE DATA · NOT A TRACK RECORD</div>
    <h2 id="score-heading">Influence scorecard</h2>
    <p>${escape(score.disclaimer)}</p>
    <p>${escape(score.summary)}</p>
    <p class="note">${escape(score.status_note)}</p>
    <p class="sub">${escape(score.lifecycle.note)}</p>
    <div class="route">
      <article class="owner-card owner-bank">
        <div class="label">LESSONS BANK</div>
        <h3>This example quarter</h3>
        <p>${escape(score.bank)}</p>
        <p class="sub">Earlier quarters stay in the baseline. A repeat of a closed lesson reopens it, and verifying the revised proof does not erase the repeat.</p>
      </article>
      <div class="owners">${owners}</div>
    </div>
    <section class="score-group" aria-labelledby="team-heading">
      <h3 id="team-heading">By owner team</h3>
      <p>${escape(score.teams.question)}</p>
      <div class="team-grid">${teams}</div>
      <p class="sub">${escape(score.teams.note)}</p>
    </section>
    ${groups}
    <section class="systems" aria-labelledby="systems-heading">
      <h3 id="systems-heading">Example systems mapping</h3>
      <p>${escape(score.systems.principle)}</p>
      <p class="sub">${escape(score.systems.disclaimer)}</p>
      <ul class="clean">${systems}</ul>
    </section>
    <div class="baseline">
      <h3>Example baseline</h3>
      <p>In the first 30–60 days, build the baseline this way. This example uses ${escape(score.baseline.window)} because those quarters already share the definitions.</p>
      <ol class="method">${score.baseline.method_steps.map(step => `<li>${escape(step)}</li>`).join("")}</ol>
      <div class="quarters">${quarters}</div>
      <h3>Definitions used for this example</h3>
      <ul class="clean">${score.baseline.definitions.map(item => `<li><strong>${escape(item.term)}</strong> · ${escape(item.means)}</li>`).join("")}</ul>
      <h3>Example conversations</h3>
      <ul class="clean">${score.baseline.conversations.map(item => `<li><strong>${escape(item.role)}</strong> · ${escape(item.note)}</li>`).join("")}</ul>
      <p class="sub">${escape(score.baseline.messy_data)}</p>
    </div>
  </section>`;
}

function render() {
  const timeline = view.picker_stage ? ["Reported", "Evidence", "Routed", "Recovered"] : stages;
  let index = timeline.indexOf(view.stage);
  if (!view.picker_stage && view.stage === "Closed") index = timeline.indexOf("Measure");
  const verified = view.actions.filter(row => row.state === "Verified").length;
  const repeats = view.scorecard ? `<div class="metric"><span class="label">REPEATS</span><strong class="${view.scorecard.repeat_held ? "" : "miss"}">${view.scorecard.repeat_held ? "None" : `${view.scorecard.repeat_count} · missed`}</strong></div>` : "";
  app.innerHTML = `<ol class="steps" style="--steps:${timeline.length}" aria-label="Escalation lifecycle">${timeline.map((stage, i) => `<li class="${i === index ? "current" : i < index ? "past" : ""}" ${i === index ? 'aria-current="step"' : ""}><b>${i + 1}.</b> ${stage}</li>`).join("")}</ol>
    <div class="metrics${view.scorecard ? " with-score" : ""}"><div class="metric"><span class="label">CUSTOMER</span><strong>${view.recovered ? "Recovered" : "Open escalation"}</strong></div>
    <div class="metric"><span class="label">LEARNING</span><strong>${view.picker_stage ? "Separate issue" : view.stage === "Closed" ? "Closed" : "Open"}</strong></div>
    <div class="metric"><span class="label">VERIFIED ACTIONS</span><strong>${verified} / ${view.actions.length || "—"}</strong></div>${repeats}</div>
    <div class="layout"><div class="stack" id="workflow">${engagement()}${recordsPanel()}${learning()}${recurrenceReview()}</div>
    <aside class="stack">${executive()}${audit()}<div>${button("reset", "Restart practice case")}</div></aside></div>
    ${view.scorecard ? scorecardPanel(view.scorecard) : ""}`;
  app.setAttribute("aria-busy", "false");
}

async function request(command, id) {
  if (pending) return;
  pending = true;
  const method = command ? "POST" : "GET";
  app.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/api/session", command ? {
      method, headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action: command, revision: view.revision, action_id: id || null})
    } : {method});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The workflow request failed.");
    view = data;
    render();
    if (command) {
      const next = app.querySelector("#workflow button.primary, #workflow button[data-command=verify]");
      next?.focus({preventScroll: true});
      showNotice(view.audit.at(-1)?.summary || "Practice case restarted.");
    }
  } catch (error) {
    showNotice(error.message);
  } finally {
    app.setAttribute("aria-busy", "false");
    pending = false;
  }
}

app.addEventListener("click", event => {
  const target = event.target.closest("button");
  if (!target) return;
  const {source, command, id} = target.dataset;
  if (source) {
    const evidence = view.evidence[source];
    if (!evidence) {
      showNotice("This evidence is unavailable in the current case.");
      return;
    }
    const [title, observation, url] = evidence;
    document.querySelector("#source-content").innerHTML = `<div class="label">EVIDENCE / ${escape(source)}</div>
      <h2>${escape(title)}</h2><p>${escape(observation)}</p>
      ${url ? `<p><a href="${escape(url)}" target="_blank" rel="noopener noreferrer">Open source documentation</a></p>` : ""}`;
    dialog.showModal();
  } else if (command === "export") {
    const file = new Blob([JSON.stringify(view, null, 2)], {type: "application/json"});
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${view.case_id}-learning-record.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else if (command) {
    request(command, id);
  }
});

request();
