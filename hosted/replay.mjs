const storageKey = "escalation-learning-demo:v2";
const fresh = (revision = 0) => ({node: 0, revision, version: 0, audit: [], reviews: []});
let graphPromise;
let session;

function restore(graph) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey));
    if (saved && graph.nodes[saved.node] && Number.isInteger(saved.revision) &&
        Number.isInteger(saved.version) && Array.isArray(saved.audit) && Array.isArray(saved.reviews)) {
      return saved;
    }
  } catch {
    // In-memory replay also works when browser storage is unavailable.
  }
  return fresh();
}

export function advance(graph, state, command, id, revision, at) {
  if (revision !== state.revision) {
    throw new Error("This view changed. Reload before applying an action.");
  }
  if (command === "reset") return fresh(state.revision + 1);
  const key = id ? `${command}:${id}` : command;
  const transition = graph.nodes[state.node].next[key];
  if (!Array.isArray(transition)) {
    throw new Error(typeof transition === "string" ? transition : "Unknown workflow action.");
  }
  const [node, versionDelta, events] = transition;
  const version = state.version + versionDelta;
  const audit = state.audit.concat(events.map((event, index) => ({
    ...event, at, step: state.audit.length + index + 1,
    summary: command === "approve" ? `Approved customer draft v${version} for preview.` : event.summary,
  })));
  const approval = graph.values[graph.nodes[node].view.triage]?.draft.decision;
  const reviews = command === "approve" ?
    state.reviews.concat({...approval, version, timestamp: at}) : state.reviews;
  return {node, version, revision: revision + 1, audit, reviews};
}

export function caseView(graph, state) {
  const view = Object.fromEntries(Object.entries(graph.nodes[state.node].view)
    .map(([key, index]) => [key, graph.values[index]]));
  const triage = view.triage;
  if (triage) view.triage = {
    ...triage, audit: state.reviews,
    draft: {
      ...triage.draft, version: state.version,
      decision: triage.draft.decision ? state.reviews.at(-1) : null,
    },
  };
  return {...view, revision: state.revision, audit: state.audit};
}

export async function hostedSession(command, id, revision) {
  graphPromise ??= fetch(new URL("./case.json", import.meta.url)).then(response => {
    if (!response.ok) throw new Error("Could not load the practice case. Reload to try again.");
    return response.json();
  });
  const graph = await graphPromise;
  session ??= restore(graph);
  if (command) {
    const at = new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
    session = advance(graph, session, command, id, revision, at);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(session));
    } catch {
      // If storage is disabled or full, keep the current session in memory.
    }
  }
  return caseView(graph, session);
}
