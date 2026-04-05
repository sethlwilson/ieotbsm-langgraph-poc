async function fetchState() {
  const r = await fetch("/api/state", { credentials: "same-origin" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function fetchScenarios() {
  const r = await fetch("/api/demo-scenarios", { credentials: "same-origin" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function heatColor(t) {
  if (t >= 0.55) return "#238636";
  if (t >= 0.35) return "#9e6a03";
  return "#da3633";
}

function renderMatrix(tm) {
  const wrap = document.getElementById("matrixWrap");
  const labels = tm.labels;
  const M = tm.matrix;
  let html = "<table class='matrix'><thead><tr><th></th>";
  for (const h of labels) {
    html += "<th title='" + escapeHtml(h) + "'>" + escapeHtml(h.slice(0, 9)) + "</th>";
  }
  html += "</tr></thead><tbody>";
  for (let i = 0; i < labels.length; i++) {
    html += "<tr><th class='rowhead' title='" + escapeHtml(labels[i]) + "'>" + escapeHtml(labels[i]) + "</th>";
    for (let j = 0; j < labels.length; j++) {
      if (i === j) {
        html += "<td class='cell-self'>\u2014</td>";
      } else {
        const v = M[i][j];
        const bg = heatColor(v);
        html += "<td style='background:" + bg + ";color:#fff' title='tau=" + v.toFixed(3) + "'>" + v.toFixed(2) + "</td>";
      }
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  wrap.innerHTML = html;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setPhase(text) {
  const el = document.getElementById("phaseBadge");
  if (el) el.textContent = text;
}

function humanLine(obj) {
  const t = obj.type || "event";
  switch (t) {
    case "demo_started":
      return "Started storyline: " + obj.count + " scenes. " + (obj.subtitle || "");
    case "demo_query":
      return "Scene " + (obj.index + 1) + ": \u201c" + (obj.title || "Untitled") + "\u201d \u2014 " + (obj.tagline || "");
    case "demo_complete":
      return "Storyline complete. Trust matrix reflects all scenes in this session.";
    case "scenario_started":
      return "Scenario: " + (obj.title || obj.id) + " \u2014 " + (obj.tagline || "");
    case "query_started":
      return "Query #" + (obj.cycle || "?") + " from " + (obj.requesting_org || "") + " [" + (obj.sensitivity || "") + "]";
    case "orchestrator":
      return "Org orchestrator signed: " + (obj.action || "") + " (" + (obj.agent_id || "") + ")";
    case "trust_check":
      return (
        "Trust gate \u2192 " +
        (obj.target_org || "") +
        ": tau=" +
        (obj.trust != null ? obj.trust : "?") +
        " vs threshold " +
        (obj.threshold != null ? obj.threshold : "?") +
        " \u2192 " +
        (obj.passed ? "PASS" : "FAIL")
      );
    case "boundary_spanner":
      return "Boundary spanner relay: " + (obj.target_org || "") + " (" + (obj.action || "") + ")";
    case "retrieval":
      return (
        "RAG " +
        (obj.org || "") +
        ": " +
        (obj.status || "") +
        ", docs=" +
        (obj.doc_count != null ? obj.doc_count : 0)
      );
    case "violation":
      return "Violation queued: " + (obj.target_org || "") + " (trust " + obj.trust + " < threshold)";
    case "human_review":
      return "Human review (TPM4): " + (obj.decision || "").toUpperCase() + " for " + (obj.target_org || "");
    case "matrix_updated":
      return "Trust matrix refreshed after partner interaction.";
    case "synthesize":
      return "Synthesizer merged retrievals (" + (obj.answer_length || 0) + " chars).";
    case "query_complete":
      return "Query complete \u2014 IA% " + (obj.results && obj.results.ia_pct != null ? obj.results.ia_pct.toFixed(1) : "?") +
        ", SM% " + (obj.results && obj.results.sm_pct != null ? obj.results.sm_pct.toFixed(1) : "?");
    case "stream_end":
      return "Stream finished.";
    case "error":
      return "Error: " + (obj.message || JSON.stringify(obj));
    case "session_reset":
      return "Session reset; new tau_0 draw.";
    default:
      return t;
  }
}

function showQueryComplete(res) {
  const panel = document.getElementById("resultsPanel");
  const block = document.getElementById("answerBlock");
  const pills = document.getElementById("metricsPills");
  const summary = document.getElementById("trustSummary");
  panel.hidden = false;
  block.textContent = res.final_answer || "(empty)";
  const ia = res.ia_pct != null ? res.ia_pct.toFixed(1) : "?";
  const sm = res.sm_pct != null ? res.sm_pct.toFixed(1) : "?";
  const hr = res.human_review_count != null ? res.human_review_count : 0;
  pills.innerHTML =
    "<span class='pill ok'>IA% " + ia + "</span>" +
    "<span class='pill warn'>SM% " + sm + "</span>" +
    "<span class='pill'>Human reviews (cycle) " + hr + "</span>";
  const checks = res.trust_checks || [];
  let pass = 0,
    fail = 0;
  for (const c of checks) {
    if (c.passed) pass++;
    else fail++;
  }
  summary.innerHTML =
    "<strong>Trust checks this query:</strong> " +
    "<span class='pass'>" +
    pass +
    " pass</span>, " +
    "<span class='fail'>" +
    fail +
    " fail</span>";
}

function logLine(obj) {
  const log = document.getElementById("log");
  const type = obj.type || "event";
  const verbose = document.getElementById("verboseLog") && document.getElementById("verboseLog").checked;
  const div = document.createElement("div");
  div.className = "ev ev-" + type.replace(/[^a-z0-9_]/g, "_");
  const human = document.createElement("div");
  human.className = "human";
  const span = document.createElement("span");
  span.className = "type";
  span.textContent = type;
  human.appendChild(span);
  human.appendChild(document.createTextNode(humanLine(obj)));
  div.appendChild(human);
  if (verbose) {
    const raw = document.createElement("div");
    raw.className = "raw";
    raw.textContent = JSON.stringify(obj);
    div.appendChild(raw);
  }
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;

  if (type !== "matrix_updated") setPhase(type.replace(/_/g, " "));

  if (type === "query_complete" && obj.results) {
    showQueryComplete(obj.results);
  }
}

function clearLog() {
  document.getElementById("log").innerHTML = "";
}

function updateStatsFromState(s) {
  document.getElementById("statCycle").textContent = s.cycle != null ? String(s.cycle) : "\u2014";
  document.getElementById("statHR").textContent =
    s.human_review_queue_size != null ? String(s.human_review_queue_size) : "\u2014";
}

async function refreshState() {
  const s = await fetchState();
  renderMatrix(s.trust_matrix);
  updateStatsFromState(s);
  document.getElementById("metaState").textContent =
    "Ledger cycle counter: " + s.cycle + " | Violations in human queue: " + s.human_review_queue_size;
  const sel = document.getElementById("orgSelect");
  const cur = sel.value;
  sel.innerHTML = "";
  for (const o of s.orgs) {
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = o.name + " (" + o.id + ")";
    sel.appendChild(opt);
  }
  if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
}

function getThrottle() {
  const v = parseInt(document.getElementById("throttle").value, 10);
  return Number.isFinite(v) ? Math.max(0, Math.min(5000, v)) : 0;
}

let activeEs = null;

function stopStream() {
  if (activeEs) {
    activeEs.close();
    activeEs = null;
  }
}

function startStream(url) {
  stopStream();
  clearLog();
  setPhase("streaming\u2026");
  const es = new EventSource(url);
  activeEs = es;
  es.onmessage = (e) => {
    try {
      const obj = JSON.parse(e.data);
      logLine(obj);
      if (obj.type === "matrix_updated" && obj.trust_matrix) {
        renderMatrix(obj.trust_matrix);
      }
      if (obj.type === "stream_end" || obj.type === "error") {
        es.close();
        activeEs = null;
        setPhase("Idle");
        refreshState().catch(console.error);
      }
    } catch (err) {
      console.error(err);
    }
  };
  es.onerror = () => {
    es.close();
    activeEs = null;
    setPhase("Idle");
    refreshState().catch(console.error);
  };
}

function renderScenarioGrid(scenarios) {
  const grid = document.getElementById("scenarioGrid");
  grid.innerHTML = "";
  for (const sc of scenarios) {
    const card = document.createElement("div");
    card.className = "scenario-card";
    card.innerHTML =
      "<h3>" +
      escapeHtml(sc.title) +
      "</h3>" +
      "<div class='sens'>" +
      escapeHtml(sc.sensitivity) +
      "</div>" +
      "<div class='tag'>" +
      escapeHtml(sc.tagline || "") +
      "</div>";
    const actions = document.createElement("div");
    actions.className = "actions";
    const load = document.createElement("button");
    load.type = "button";
    load.className = "btn";
    load.textContent = "Load";
    load.addEventListener("click", () => {
      document.getElementById("orgSelect").value = sc.requesting_org_id;
      document.getElementById("sensSelect").value = sc.sensitivity;
      document.getElementById("queryText").value = sc.query;
    });
    const run = document.createElement("button");
    run.type = "button";
    run.className = "btn primary";
    run.textContent = "Run";
    run.addEventListener("click", () => {
      const th = getThrottle();
      const params = new URLSearchParams({
        scenario_id: sc.id,
        throttle_ms: String(th),
      });
      startStream("/api/simulation/stream?" + params.toString());
    });
    actions.appendChild(load);
    actions.appendChild(run);
    card.appendChild(actions);
    grid.appendChild(card);
  }
}

document.getElementById("btnRefresh").addEventListener("click", () => {
  refreshState().catch(alert);
});

document.getElementById("btnReset").addEventListener("click", async () => {
  stopStream();
  const r = await fetch("/api/session/reset", {
    method: "POST",
    credentials: "same-origin",
  });
  if (!r.ok) return alert(await r.text());
  const s = await r.json();
  renderMatrix(s.trust_matrix);
  updateStatsFromState(s);
  document.getElementById("metaState").textContent =
    "Ledger cycle counter: " + s.cycle + " | Violations in human queue: " + s.human_review_queue_size;
  clearLog();
  document.getElementById("resultsPanel").hidden = true;
  logLine({ type: "session_reset", ok: true });
});

document.getElementById("btnClearLog").addEventListener("click", clearLog);

document.getElementById("qform").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const q = document.getElementById("queryText").value.trim();
  const org = document.getElementById("orgSelect").value;
  const sens = document.getElementById("sensSelect").value;
  const th = getThrottle();
  if (!q) return alert("Enter a query");
  const params = new URLSearchParams({
    query: q,
    requesting_org_id: org,
    sensitivity: sens,
    throttle_ms: String(th),
  });
  startStream("/api/simulation/stream?" + params.toString());
});

document.getElementById("btnDemo").addEventListener("click", () => {
  const th = getThrottle();
  const params = new URLSearchParams({
    demo: "1",
    throttle_ms: String(th),
  });
  startStream("/api/simulation/stream?" + params.toString());
});

Promise.all([refreshState(), fetchScenarios()])
  .then(([, scenarios]) => renderScenarioGrid(scenarios))
  .catch(console.error);
