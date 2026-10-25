"use strict";

const icons = {
  cube: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  graph: '<rect x="8" y="2" width="8" height="6" rx="1.5"/><rect x="2" y="16" width="7" height="6" rx="1.5"/><rect x="15" y="16" width="7" height="6" rx="1.5"/><path d="M12 8v4M5.5 16v-4h13v4"/>',
  ledger: '<path d="M6 3h12a2 2 0 0 1 2 2v15H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M8 3v17M12 8h5M12 12h5M12 16h3"/>',
  warning: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 17h.01"/>',
  activity: '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  compare: '<path d="M4 7h15l-4-4M20 17H5l4 4M19 7l-4 4M5 17l4-4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2M18 18a8 8 0 0 1-13-2"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  git: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="6" r="2"/><path d="M6 7v10M18 8v3c0 4-12 1-12 6"/>',
};
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.file}</svg>`;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const badge = (value) => `<span class="badge ${esc(value)}">${esc(value)}</span>`;
const state = { view: "walkthrough", snapshots: [], examples: [], record: null, token: "", workspace: "", search: "", severity: "all", status: "all", graphKind: "imports", selectedComponent: null, busy: false, proofBusy: false, diff: null, error: "", drawer: null, proof_checker: null };
const titles = { walkthrough: "System walkthrough", workflow: "Analysis workflow", overview: "System overview", architecture: "Architecture", claims: "Claim ledger", findings: "Findings", behavior: "Behavior & invariants", proofs: "Proofs & mathematics", agents: "Agent workspace", compare: "Snapshot comparison" };
let toastTimer, lastFocus;
let snapshotLoadGeneration = 0;

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-Codeform-Token": state.token }, body: JSON.stringify(payload) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
function toast(message) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("visible"), 5000);
}
function download(name, content, type = "application/json") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function timeLabel(value) {
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function repoName() { return state.record?.bundle.repository.name || "Your workspace"; }
function entityName(entity) { return entity.name || entity.title || entity.statement || entity.id; }
function component(id) { return state.record?.bundle.components.find(c => c.id === id); }
function sourceRef(id) { return state.record?.bundle.evidence.find(e => e.id === id); }
function annotation(id) { return state.record?.annotations[id] || { status: "open", note: "" }; }
function notice(text) { return `<div class="notice">${icon("info")}<span>${esc(text)}</span></div>`; }

function shell(content) {
  const findings = state.record?.bundle.summary.findings;
  const nav = [["walkthrough", "activity", "Start here"], ["workflow", "graph", "Analysis DAG"], ["overview", "grid", "Overview"], ["architecture", "graph", "Architecture"], ["claims", "ledger", "Claim ledger"], ["findings", "warning", "Findings"], ["behavior", "activity", "Behavior"], ["proofs", "shield", "Proofs & mathematics"], ["agents", "code", "Agent workspace"], ["compare", "compare", "Compare"]];
  return `<div class="app-shell"><aside class="sidebar">
    <a class="brand" href="/" aria-label="code-form home"><span class="brand-mark">${icon("cube")}</span><span class="brand-name">code-form<span class="muted">.</span></span></a>
    <div class="workspace-label">SYSTEM EXPLORER</div>
    <nav aria-label="Main navigation">${nav.map(([view, name, label]) => `<button class="nav-item ${state.view === view ? "active" : ""}" data-view="${view}" title="${label}" ${state.view === view ? 'aria-current="page"' : ""}>${icon(name)}<span class="nav-label">${label}</span>${view === "findings" && findings ? `<span class="nav-count">${findings}</span>` : ""}</button>`).join("")}</nav>
    <div class="sidebar-bottom"><button class="nav-item" data-action="new">${icon("plus")}<span class="nav-label">Analyze repository</span></button><button class="nav-item" data-action="import">${icon("upload")}<span class="nav-label">Import a snapshot</span></button>
      <div class="workspace-card"><strong><span class="live-dot"></span>Local workspace</strong><p class="muted">Your code stays on this machine.</p></div>
      <div class="sidebar-foot">Python AST adapter · v0.1.0<br>Evidence before confidence.</div>
    </div></aside>
    <div class="main-shell"><header class="topbar"><div class="breadcrumb">Workspace ${icon("chevron")} <strong>${esc(repoName())}</strong></div><div class="topbar-right"><span class="local-pill"><span class="live-dot"></span>Read-only analysis</span><span class="avatar" title="Local reviewer">LR</span></div></header>
      <main class="content">${content}<footer class="footer"><span>Every claim has a source. Every inference has a boundary.</span><span>code-form / local system explorer</span></footer></main>
    </div><input class="import-input" id="import-file" type="file" accept=".json,application/json" aria-label="Import analysis bundle"></div>`;
}
function header() {
  const subtitles = {
    walkthrough: "Connect purpose, examples, mathematical objects, and the implementation that gives them meaning.",
    workflow: "One versioned DAG: parallel work, pinned evidence, and explicit human review gates.",
    overview: "A traceable view of your codebase, from structure to the questions worth asking.",
    architecture: "Follow the dependencies. Inspect the components. Trace relationships to code.",
    claims: "What the system model says, how it knows, and where the evidence lives.",
    findings: "Prioritized questions and concrete counterexamples for your next review.",
    behavior: "Explore call flows, explicit state machines, and carefully bounded properties.",
    proofs: "Given these assumptions, these conclusions follow. Inspect the mathematics and its proof evidence.",
    agents: "Review evidence-linked proposals and immutable checker attempts from external agents.",
    compare: "See what changed in the code and its evidence-linked model.",
  };
  const id = state.record?.bundle.id;
  return `<div class="page-header"><div><div class="eyebrow">Repository intelligence</div><h1>${titles[state.view]}</h1><p class="subtitle">${subtitles[state.view]}</p></div>
    <div class="header-actions">${id ? `<div class="export-wrap"><button class="btn" data-action="export">${icon("download")}Export ${icon("down")}</button><div class="export-menu hidden" id="export-menu">
      <a href="/api/snapshots/${id}/export?format=json">Analysis bundle · JSON</a><a href="/api/snapshots/${id}/export?format=markdown">Review report · Markdown</a><a href="/api/snapshots/${id}/export?format=architecture">Architecture · Mermaid</a><a href="/api/snapshots/${id}/export?format=sequence">Call flow · Mermaid</a></div></div>` : ""}
      <button class="btn primary" data-action="new" ${state.busy ? "disabled" : ""}>${icon("plus")}Analyze repository</button></div></div>`;
}
function snapshotBar() {
  if (!state.record) return "";
  const repo = state.record.bundle.repository;
  return `<div class="snapshot-bar"><span class="repo-mark">${icon("folder")}</span><select class="snapshot-select" id="snapshot-select" aria-label="Selected repository snapshot">
    ${state.snapshots.map(s => `<option value="${s.id}" ${s.id === state.record.bundle.id ? "selected" : ""}>${esc(s.repository.name)} · ${timeLabel(s.created_at)}</option>`).join("")}</select>
    <span class="snapshot-meta"><span class="optional">${icon("git")}</span><code>${esc(repo.commit_sha?.slice(0, 8) || "no commit")}</code>${repo.dirty ? '<span class="badge proposed">working tree</span>' : ""}<span class="optional">${state.record.bundle.summary.files} captured files</span><button class="btn small" data-action="reanalyze" ${state.busy ? "disabled" : ""}>${icon("refresh")}Re-analyze</button></span></div>`;
}
function metrics() {
  const s = state.record.bundle.summary;
  const items = [
    ["cube", "Components", s.modules + s.symbols, `${s.modules} modules · ${s.symbols} declarations`, "STRUCTURE"],
    ["ledger", "Evidence-linked claims", s.claims, "Source locations, not unsupported guesses", "TRACEABLE"],
    ["warning", "Findings to review", s.findings, `${s.severity.high} high · ${s.severity.medium} medium · ${s.severity.low} low`, "ACTIONABLE"],
    ["shield", "Direct test references", `${s.directly_referenced_interfaces}/${s.public_interfaces}`, `${s.test_modules} test modules · static links only`, "STATIC"],
  ];
  return `<div class="metrics">${items.map(([name, label, value, detail, tag]) => `<div class="metric"><div class="metric-label">${icon(name)}${label}</div><span class="metric-tag">${tag}</span><div class="metric-value">${value}</div><div class="metric-detail">${detail}</div></div>`).join("")}</div>`;
}
function graph(large = false) {
  const bundle = state.record.bundle;
  const relations = bundle.relationships.filter(r => r.kind === state.graphKind);
  const nodeIds = new Set(relations.flatMap(r => [r.source, r.target]));
  let nodes = state.graphKind === "imports" ? bundle.components.filter(c => ["module", "test_module"].includes(c.kind)) : bundle.components.filter(c => nodeIds.has(c.id));
  if (!nodes.length) nodes = bundle.components.filter(c => ["module", "test_module"].includes(c.kind));
  // A readable deterministic grid, capped visually without dropping model facts.
  const total = nodes.length;
  nodes = nodes.slice(0, 30);
  const width = 820, columns = nodes.length <= 4 ? 2 : nodes.length <= 9 ? 3 : 4;
  const rows = Math.max(1, Math.ceil(nodes.length / columns));
  const height = Math.max(300, rows * 115 + 55);
  const positions = new Map(nodes.map((node, i) => [node.id, { x: 45 + (i % columns) * (width - 80) / columns, y: 45 + Math.floor(i / columns) * (height - 60) / rows }]));
  const boxWidth = Math.min(180, (width - 110) / columns - 20), boxHeight = 58;
  const edges = relations.filter(r => positions.has(r.source) && positions.has(r.target)).map(r => {
    const a = positions.get(r.source), b = positions.get(r.target);
    const ax = a.x + boxWidth / 2, ay = a.y + boxHeight / 2, bx = b.x + boxWidth / 2, by = b.y + boxHeight / 2;
    const dx = bx - ax, dy = by - ay, length = Math.max(1, Math.hypot(dx, dy));
    const offset = Math.min(boxWidth / 2, boxHeight / 2 + 13);
    const x1 = ax + dx / length * offset, y1 = ay + dy / length * offset;
    const x2 = bx - dx / length * offset, y2 = by - dy / length * offset;
    const bend = r.source > r.target ? 23 : -23;
    return `<path class="graph-edge ${r.kind}" d="M${x1},${y1} Q${(x1 + x2) / 2 - dy / length * bend},${(y1 + y2) / 2 + dx / length * bend} ${x2},${y2}" marker-end="url(#arrowhead)"><title>${esc(component(r.source).name)} ${r.kind} ${esc(component(r.target).name)}</title></path>`;
  }).join("");
  return `<div class="graph-panel"><div class="graph-top"><h2>Dependency map</h2><span>${relations.length} ${state.graphKind} relationships</span></div>
    <svg class="graph-svg ${large ? "large" : ""}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Interactive repository dependency graph">
      <defs><marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10Z" fill="#8893b3"/></marker></defs>
      ${edges}${nodes.map(n => {
        const p = positions.get(n.id), name = n.name.length > 23 ? "…" + n.name.slice(-22) : n.name;
        return `<g class="graph-node ${n.kind === "test_module" ? "test" : ""} ${state.selectedComponent === n.id ? "selected" : ""}" data-component="${n.id}" tabindex="0" role="button" aria-label="Inspect ${esc(n.name)}" transform="translate(${p.x},${p.y})">
          <rect width="${boxWidth}" height="${boxHeight}" rx="8"/><text class="node-icon" x="12" y="22">◇</text><text x="29" y="22">${esc(name)}</text><text class="node-kind" x="13" y="42">${esc(n.kind.replace("_", " "))} · ${n.line_end - n.line_start + 1} lines</text><title>${esc(n.name)}</title></g>`;
      }).join("")}
    </svg><div class="graph-footer"><div class="graph-legend"><span><i class="legend-dot"></i>Source</span><span><i class="legend-dot test"></i>Tests</span></div><span>${total > 30 ? `Showing 30 of ${total} nodes · ` : ""}Select a node to inspect its source</span></div></div>`;
}
function rankedFindings() {
  const order = { high: 0, medium: 1, low: 2, info: 3 };
  return [...state.record.bundle.findings].sort((a, b) => order[a.severity] - order[b.severity] || a.title.localeCompare(b.title));
}
function overview() {
  const bundle = state.record.bundle;
  const claims = [...bundle.claims].sort((a, b) => (a.evidence[0]?.reference || "").localeCompare(b.evidence[0]?.reference || "")).slice(0, 5);
  return `${metrics()}<div class="overview-grid"><div>${graph()}</div><div class="panel"><div class="panel-header"><h2>Priority findings</h2><button class="text-link" data-view="findings">View all ${icon("arrow")}</button></div>
    ${rankedFindings().slice(0, 4).map(f => `<button class="finding-row" data-finding="${f.id}"><span class="severity-dot ${f.severity}"></span><div><h3>${esc(f.title)}</h3><p>${esc(f.rule.replaceAll("-", " "))} · ${esc(sourceRef(f.evidence_ids[0])?.reference || "model")}</p></div>${badge(f.severity)}</button>`).join("") || '<div class="empty">No findings from the supported static checks.</div>'}
    <div class="finding-footer">Candidates for review. Validate intent before changing code.</div></div></div>
    <div class="section-heading"><div><h2>A model you can verify</h2><p>Every statement links to a captured source location.</p></div><button class="text-link" data-view="claims">Explore claim ledger ${icon("arrow")}</button></div>
    <div class="panel table-scroll"><table class="table"><thead><tr><th>Claim</th><th>Status</th><th>Evidence</th><th></th></tr></thead><tbody>
      ${claims.map(c => claimRow(c)).join("")}</tbody></table></div>
    ${state.record.proof_plan?.length ? `<div class="notice">${icon("shield")}<span>This repository has mathematical obligations. <button class="text-link" data-view="proofs">Explore assumptions, checked proofs, and counterexamples ${icon("arrow")}</button></span></div>` : ""}
    ${notice("A test reference means a test calls an interface. It does not mean the test passed or that the interface is fully covered. Analyze, inspect, then validate.")}`;
}
function claimRow(c) {
  const ref = c.evidence[0];
  return `<tr class="clickable" data-claim="${c.id}"><td class="statement">${esc(c.statement)}</td><td>${badge(c.status)}</td><td><span class="evidence-link">${esc(ref.reference)}:${ref.line_start}</span></td><td>${icon("chevron")}</td></tr>`;
}
function welcome() {
  return `<div class="welcome"><div class="eyebrow">From code to understanding</div><h1>Understand the system.<br>Follow the evidence.</h1><p>Turn a Python repository into an inspectable system model. Explore its architecture, trace claims to source, and find the questions your tests have yet to answer.</p><button class="btn primary" data-action="new">${icon("plus")}Analyze a repository</button> <button class="btn" data-action="import">${icon("upload")}Import a snapshot</button></div>
    <div class="section-heading"><div><h2>Start with a small system</h2><p>Purpose-built example repositories with real source, tests, and discoverable findings.</p></div><span class="badge proposed">No API key required</span></div>
    <div class="example-grid">${state.examples.map((e, i) => `<div class="example-card"><div class="example-icon">${icon(["cube", "activity", "graph"][i % 3])}</div><h3>${esc(e.name)}</h3><p>${esc(e.description)}</p><button class="btn" data-example="${i}" ${state.busy ? "disabled" : ""}>Explore example ${icon("arrow")}</button></div>`).join("")}</div>
    ${notice("Analysis is static and read-only: source is parsed, never imported or executed. Evidence is stored with the source content hash, so a later edit cannot silently change an existing snapshot.")}`;
}
function toolbar(type) {
  return `<div class="toolbar"><label class="search">${icon("search")}<input id="search" value="${esc(state.search)}" placeholder="${type === "claims" ? "Search statements or source files…" : "Search findings or rules…"}" aria-label="Search ${type}"></label>
    ${type === "findings" ? `<select class="filter" id="severity-filter" aria-label="Filter severity">${["all", "high", "medium", "low", "info"].map(s => `<option value="${s}" ${state.severity === s ? "selected" : ""}>${s === "all" ? "All severities" : s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select><select class="filter" id="review-filter" aria-label="Filter review status">${["all", "open", "accepted", "dismissed", "resolved"].map(s => `<option value="${s}" ${state.status === s ? "selected" : ""}>${s === "all" ? "All review states" : s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select>` :
    `<select class="filter" id="claim-filter" aria-label="Filter claim status">${["all", "observed", "inferred", "proposed", "tested", "proved", "contradicted", "unknown"].map(s => `<option value="${s}" ${state.status === s ? "selected" : ""}>${s === "all" ? "All epistemic statuses" : s[0].toUpperCase() + s.slice(1)}</option>`).join("")}</select>`}<span class="result-count" id="result-count"></span></div><div id="filtered-results"></div>`;
}
function renderFiltered() {
  const target = document.getElementById("filtered-results");
  if (!target) return;
  const needle = state.search.toLowerCase();
  const claims = state.view === "claims";
  const items = claims ? state.record.bundle.claims.filter(c => (state.status === "all" || c.status === state.status) && `${c.statement} ${c.evidence.map(e => e.reference).join(" ")}`.toLowerCase().includes(needle)) :
    rankedFindings().filter(f => (state.severity === "all" || f.severity === state.severity) && (state.status === "all" || annotation(f.id).status === state.status) && `${f.title} ${f.rule} ${f.rationale}`.toLowerCase().includes(needle));
  document.getElementById("result-count").textContent = `${items.length} ${claims ? "claims" : "findings"}`;
  if (!items.length) { target.innerHTML = '<div class="panel empty">No matches. Adjust your search or filters.</div>'; return; }
  target.innerHTML = claims ? `<div class="panel table-scroll"><table class="table"><thead><tr><th>Statement</th><th>Status</th><th>Source evidence</th><th></th></tr></thead><tbody>${items.map(claimRow).join("")}</tbody></table></div>` :
    `<div class="finding-cards">${items.map(f => {
      const ref = sourceRef(f.evidence_ids[0]);
      return `<button class="finding-card" data-finding="${f.id}"><div class="finding-card-top">${badge(f.severity)}${badge(annotation(f.id).status)}</div><h3>${esc(f.title)}</h3><p>${esc(f.rationale)}</p><div class="finding-card-foot"><span class="evidence-link">${esc(ref?.reference || "model")}${ref ? `:${ref.line_start}` : ""}</span><span class="text-link">Inspect evidence ${icon("arrow")}</span></div></button>`;
    }).join("")}</div>`;
}
function architecture() {
  const selected = component(state.selectedComponent);
  const modules = state.record.bundle.components.filter(c => ["module", "test_module"].includes(c.kind));
  return `<div class="toolbar"><div class="tab-buttons">${["imports", "calls", "tests"].map(k => `<button class="btn ${state.graphKind === k ? "active" : ""}" data-graph="${k}">${k[0].toUpperCase() + k.slice(1)}</button>`).join("")}</div><span class="result-count">Explicit static relationships</span></div>
    <div class="architecture-layout">${graph(true)}<div class="panel component-details"><div class="eyebrow">${selected ? "Selected component" : "Component directory"}</div>
    ${selected ? `<h3>${esc(selected.name)}</h3>${badge(selected.kind)}<div class="detail-label">Source</div><div class="detail-value mono">${esc(selected.path)}:${selected.line_start}–${selected.line_end}</div><div class="detail-label">Description</div><div class="detail-value">${esc(selected.docstring || "No docstring found. Intent remains an open question.")}</div><button class="btn small" data-source-component="${selected.id}">${icon("code")}View captured source</button>` : '<h3>Explore the structure</h3><p class="model-note">Select a node to see its declaration and the code behind it.</p>'}
    <div class="detail-label">Modules · ${modules.length}</div><div class="component-list">${modules.map(c => `<button data-component="${c.id}">${icon(c.kind === "test_module" ? "shield" : "file")} ${esc(c.name)}</button>`).join("")}</div></div></div>
    ${notice("Import edges are dependencies, not runtime data flows. Call edges resolve explicit names only; dynamic dispatch and framework wiring remain outside the current model.")}`;
}
function behavior() {
  const bundle = state.record.bundle;
  const machines = bundle.state_machines.map(machine => {
    const invariant = bundle.invariants.find(i => i.scope === machine.component_id);
    const formal = bundle.formal_candidates.find(f => f.invariant_id === invariant?.id);
    return `<div class="panel padded"><div class="section-heading"><h2>${esc(machine.name)}</h2>${badge(machine.status)}</div><p class="model-note">Literal transition table. Green states are declared terminal.</p>
      <div class="state-list">${machine.states.map(s => `<span class="state-chip ${machine.terminal_states.includes(s) ? "terminal" : ""}">${esc(s)}</span>`).join("")}</div>
      <div class="transition-list">${machine.transitions.map(t => `${esc(t.from)} <span class="muted">── ${esc(t.event)} →</span> ${esc(t.to)}<br>`).join("")}</div>
      ${invariant ? `<div class="detail-label">Bounded invariant check ${badge(invariant.status)}</div><p class="model-note">${esc(invariant.statement)}<br>${invariant.check.cases} literal transitions checked.</p>${invariant.check.counterexamples.map(t => `<div class="counterexample"><strong>Counterexample</strong><br>${esc(t.from)} ── ${esc(t.event)} → ${esc(t.to)}<br>A declared terminal state changes to a different state.</div>`).join("")}` : ""}
      <button class="btn small" data-evidence="${machine.evidence_ids[0]}">${icon("code")}Inspect transition table</button>
      ${formal ? `<div class="detail-label">Formalization candidate ${badge("proposed")}</div><p class="model-note">Lean 4 · checker not run · proof contains a placeholder.</p><pre class="lean-preview">${esc(formal.source)}</pre><button class="btn small" data-formal="${formal.id}">${icon("download")}Download Lean candidate</button>` : ""}</div>`;
  }).join("");
  return `<div class="behavior-grid"><div>${machines || `<div class="panel padded"><h2>No explicit state machine found</h2><p class="model-note">This adapter recognizes a literal <code>TRANSITIONS = {("state", "event"): "next"}</code> table and optional <code>TERMINAL_STATES</code>. Explore the order-workflow example to see the full flow.</p><button class="btn small" data-action="new">${icon("plus")}Analyze another repository</button></div>`}</div>
    <div><div class="panel"><div class="panel-header"><h2>Static call flows</h2><span class="muted">${bundle.flows.length} entry points</span></div>${bundle.flows.slice(0, 20).map(f => `<div class="padded"><h3 class="mono">${esc(f.name)}</h3>${f.steps.map(s => `<div class="flow-step"><button data-source-component="${s.target}">${esc(s.name)}</button> <span class="muted">at line ${s.line}</span></div>`).join("")}<p class="model-note">${esc(f.note)}</p></div>`).join("") || '<div class="empty">No explicitly resolved internal call flows.</div>'}</div></div></div>
    <div class="section-heading"><h2>Assumptions & open questions</h2></div><div class="panel">${bundle.assumptions.map(a => `<div class="assumption"><button data-assumption="${a.id}"><p><strong>${esc(a.statement)}</strong> ${badge(a.status)}</p><p>${esc(a.rationale)}</p></button></div>`).join("")}${bundle.open_questions.map(q => `<div class="assumption"><p>${icon("info")} ${esc(q)}</p></div>`).join("")}</div>
    ${notice("A bounded check can establish a property of an extracted finite table. Connecting that table to production behavior requires its own tests or refinement argument. Lean candidates are never marked proved.")}`;
}
function proofs() {
  const report = state.record.verification;
  const artifacts = report?.artifacts || state.record.proof_plan || [];
  const summary = report?.summary;
  const checker = state.proof_checker;
  return `<div class="proof-intro panel padded"><div><div class="eyebrow">Mathematical reasoning</div><h2>Assumptions → definitions → checked conclusions</h2><p class="model-note">Proofs are tied to this snapshot. Each result states what it establishes, how it was checked, and which assumptions remain.</p></div><div class="proof-actions"><button class="btn primary" data-action="verify" ${state.proofBusy || !checker?.available || !artifacts.length ? "disabled" : ""}>${icon("shield")}${state.proofBusy ? "Checking with Lean…" : "Check proofs with Lean"}</button>${report ? `<button class="btn" data-action="proof-report">${icon("download")}Export proof report</button>` : ""}<span class="model-note">${checker?.available ? `Local Lean ${esc(checker.version)}` : esc(checker?.error || "Lean unavailable")}</span></div></div>
    ${state.proofBusy ? '<div class="progress-panel"><span class="loading-pulse"></span>Lean is checking complete proofs and their transitive axiom dependencies…</div>' : ""}
    ${summary ? `<div class="metrics">${[["proved", "Checked conclusions"], ["disproved", "Checked counterexamples"], ["unsupported", "Unsupported obligations"], ["error", "Checker errors"]].map(([key, label]) => `<div class="metric"><div class="metric-label">${icon(key === "proved" ? "shield" : "info")}${label}</div><div class="metric-value">${summary[key]}</div><div class="metric-detail">${key === "proved" ? "Accepted by Lean under the stated scope" : key === "disproved" ? "Concrete witness accepted by Lean" : "No correctness conclusion established"}</div></div>`).join("")}</div>` : ""}
    ${!artifacts.length ? `<div class="panel empty"><h3>No supported proof obligations in this snapshot</h3><p>Analyze verified-transfer for integer theorems and a repair comparison,<br>or verified-workflow for induction over every finite event sequence.</p><button class="btn" data-action="new">${icon("plus")}Analyze a proof example</button></div>` : `<div class="proof-artifacts">${artifacts.map(proofCard).join("")}</div>`}
    ${notice("Lean checks the emitted mathematical model. The source adapter is a stated trusted boundary; arbitrary Python, persistence, concurrent updates, and runtime type enforcement are outside these proofs.")}`;
}
function proofCard(artifact) {
  if (artifact.status === "unsupported") return `<article class="panel padded"><div class="section-heading"><h2>${esc(artifact.name)}</h2>${badge("unsupported")}</div><p class="model-note">${esc(artifact.reason)}</p></article>`;
  const checked = ["proved", "disproved"].includes(artifact.status);
  const dependencyNames = artifact.dependencies.map(id => (state.record.verification?.artifacts || state.record.proof_plan).find(a => a.id === id)?.property || id);
  const mathematical = state.record.walkthrough?.models.flatMap(m => m.principles).find(p => p.id === artifact.id);
  return `<article class="panel proof-card" id="${artifact.id}"><div class="panel-header"><div><div class="eyebrow">${esc(artifact.name)} · ${esc(artifact.property)}</div><h2>${esc(artifact.statement)}</h2></div>${badge(artifact.status)}</div><div class="padded">
    <div class="math-formula">${mathematical ? window.CodeFormWalkthrough.math(mathematical.latex, true) : esc(artifact.formula)}</div><div class="proof-scope">${icon("info")}Scope: ${esc(artifact.scope.replaceAll("-", " "))}</div>
    <div class="proof-columns"><div><h3>Given these assumptions</h3><div class="proof-assumptions">${artifact.assumptions.map(a => `<div class="proof-assumption"><span>${esc(a.kind)}</span><p>${esc(a.statement)}</p></div>`).join("")}</div><p class="model-note"><strong>Feasibility: ${esc(artifact.feasibility.status)}</strong><br>${esc(artifact.feasibility.note)}</p></div>
    <div><h3>${artifact.status === "disproved" ? "This conclusion fails" : "How the conclusion follows"}</h3><ol class="proof-steps">${artifact.reasoning.map(s => `<li><strong>${esc(s.title)}</strong><p>${esc(s.detail)}</p></li>`).join("")}</ol>
    ${dependencyNames.length ? `<div class="dependency-links"><span>Composes checked lemmas:</span>${artifact.dependencies.map((id, i) => `<a href="#${id}" data-proof-dependency="${id}">${esc(dependencyNames[i])}</a>`).join("")}</div>` : ""}
    ${artifact.counterexample ? `<div class="counterexample"><strong>${artifact.counterexample.checked ? "Lean-checked counterexample" : "Candidate counterexample"}</strong><div class="mono">Input: ${esc(JSON.stringify(artifact.counterexample.inputs))}<br>Output: ${esc(JSON.stringify(artifact.counterexample.output))}</div>${esc(artifact.counterexample.violated)}</div>${artifact.repair ? `<div class="repair-proposal"><h3>Proposed repair</h3><p class="model-note">${esc(artifact.repair.description)}</p>${artifact.repair.replacement ? `<pre>${esc(artifact.repair.replacement)}</pre>` : ""}<p class="model-note">${esc(artifact.repair.status)}${artifact.repair.reference_implementation ? `<br>Compare with ${esc(artifact.repair.reference_implementation)} in this snapshot.` : ""}</p></div>` : ""}` : ""}</div></div>
    <div class="proof-evidence-bar">${artifact.evidence.map(e => {
      const comp = state.record.bundle.components.find(c => c.path === e.reference && c.line_start === e.line_start && c.line_end === e.line_end);
      return comp ? `<button class="btn small" data-source-component="${comp.id}">${icon("code")}${esc(e.reference)}:${e.line_start}</button>` : `<span class="mono">${esc(e.reference)}</span>`;
    }).join("")}<span class="evidence-strength">Captured source → ${esc(artifact.semantics)}</span></div>
    <details class="proof-details"><summary>Inspect Lean proof and axiom dependencies ${checked ? "· checked" : "· not established"}</summary><div class="axiom-ledger"><strong>Transitive axiom dependencies</strong><p>${checked ? artifact.axioms.length ? artifact.axioms.map(a => `<code>${esc(a)}</code>`).join(" ") : "None — Lean reports no axiom dependencies for this theorem." : "No accepted proof result yet."}</p><p class="model-note">Foundational axioms belong to the proof logic. Business requirements remain obligations, not added axioms.</p></div><pre class="lean-preview">${esc(artifact.lean_source)}</pre><button class="btn small" data-proof-download="${artifact.id}">${icon("download")}Download checked input</button>${artifact.checker ? `<div class="checker-record"><strong>${esc(artifact.checker.version)}</strong><p class="model-note">Exit code ${artifact.checker.exit_code} · source ${artifact.checker.source_sha256.slice(0, 16)}<br>${esc(artifact.checker.trust)}</p><pre>${esc(artifact.checker.stdout)}</pre></div>` : ""}${artifact.error ? `<p class="error-message">${esc(artifact.error)}</p>` : ""}</details></div></article>`;
}
function agentWorkspace() {
  const work = state.record.agent_work || { attempts: [], proposals: [] };
  const id = state.record.bundle.id;
  return `<div class="panel padded"><div class="section-heading"><div><h2>One API for reasoning tools</h2><p>External agents inspect evidence, choose proof strategies, and submit drafts for review.</p></div><button class="btn" data-action="refresh-agents">${icon("refresh")}Refresh agent work</button></div><div class="agent-links"><a href="/api/v1/openapi.json" target="_blank" rel="noopener">OpenAPI contract ${icon("arrow")}</a><a href="/api/v1/snapshots/${id}/context" target="_blank" rel="noopener">Agent context ${icon("arrow")}</a><a href="/api/v1/snapshots/${id}/obligations" target="_blank" rel="noopener">Fixed obligations ${icon("arrow")}</a></div><p class="model-note">The agent supplies reasoning. The server owns the source snapshot, exact theorem statements, checker execution, and review history.</p></div>
    <div class="section-heading agent-section"><h2>Proof attempts · ${work.attempts.length}</h2></div><div class="panel">
    ${work.attempts.map(attempt => `<details class="agent-attempt"><summary><span class="mono">${esc(attempt.strategy)}</span> ${badge(attempt.status)}<span>${esc(attempt.statement)}</span><small class="muted">${esc(attempt.agent)}</small></summary><div class="padded"><p class="model-note">Fixed obligation <code>${esc(attempt.obligation_id)}</code><br>Attempt <code>${esc(attempt.id)}</code> · ${timeLabel(attempt.created_at)}<br>${esc(attempt.scope)}</p>${attempt.checker?.stdout ? `<pre class="lean-preview">${esc(attempt.checker.stdout)}</pre>` : ""}${attempt.error ? `<p class="error-message">${esc(attempt.error)}</p>` : ""}<p class="model-note">This attempt is recorded separately from the complete snapshot verification report.</p></div></details>`).join("") || '<div class="empty">No agent proof attempts yet. Use the API client or CLI to submit a strategy against a fixed obligation.</div>'}</div>
    <div class="section-heading agent-section"><h2>Proposals · ${work.proposals.length}</h2></div><div class="proof-artifacts">
    ${work.proposals.map(proposal => `<article class="panel"><div class="panel-header"><div><div class="eyebrow">${esc(proposal.kind)} · ${esc(proposal.agent)}</div><h2>${esc(proposal.title)}</h2></div>${badge(proposal.review?.decision === "rejected" ? "dismissed" : proposal.review?.decision === "accepted" ? "accepted" : "proposed")}</div><div class="padded"><h3>Rationale</h3><p class="model-note">${esc(proposal.rationale)}</p><h3>Proposed content</h3><pre class="proposal-content">${esc(proposal.content)}</pre><div class="proof-evidence-bar">${proposal.evidence.map(e => `<span class="evidence-link">${esc(e.path)}:${e.line_start}–${e.line_end}</span>`).join("")}</div><p class="model-note">Draft proposal · ${timeLabel(proposal.created_at)} · checked: false · applied: false</p>${proposal.review ? `<div class="notice"><div>Latest review: <strong>${esc(proposal.review.decision)}</strong> by ${esc(proposal.review.reviewer)}<p class="proposal-review-note">${esc(proposal.review.note)}</p></div></div>` : ""}<form class="proposal-review" data-proposal="${proposal.id}"><div class="field"><label for="decision-${proposal.id}">Review decision</label><select id="decision-${proposal.id}" name="decision"><option value="accepted">Accept intent</option><option value="needs_changes">Request changes</option><option value="rejected">Reject</option></select></div><div class="field"><label for="note-${proposal.id}">Review reasoning</label><textarea id="note-${proposal.id}" name="note" required maxlength="4000" placeholder="Record requirements, validation needed, or why this proposal should change…"></textarea></div><button class="btn primary small" type="submit">${icon("check")}Save proposal review</button></form></div></article>`).join("") || '<div class="panel empty">No proposals yet. Agents can save requirements, contract drafts, explanations, and repair suggestions with captured-source evidence.</div>'}</div>
    ${notice("Accepting a proposal records intent and review reasoning. It does not prove a theorem, alter a checked contract, apply a patch, or run target code.")}`;
}
function compareView() {
  const snapshots = state.snapshots.filter(s => s.repository.path === state.record.bundle.repository.path);
  const options = snapshots.map(s => `<option value="${s.id}">${timeLabel(s.created_at)} · ${esc(s.repository.commit_sha?.slice(0, 8) || s.repository.content_sha256.slice(0, 8))}</option>`).join("");
  return `<div class="compare-selects"><div class="field"><label for="compare-before">Earlier snapshot</label><select id="compare-before">${options}</select></div><div class="field"><label for="compare-after">Later snapshot</label><select id="compare-after">${options}</select></div><button class="btn primary" data-action="compare">${icon("compare")}Compare snapshots</button></div>
    <div id="comparison-results">${state.diff ? diffView(state.diff) : `<div class="panel empty comparison-empty"><h3>${snapshots.length < 2 ? "Capture a second snapshot to see the change" : "Compare the system, not just the files"}</h3><p>Modify a repository, re-analyze it, then compare the snapshots.<br>Stable identifiers distinguish additions, removals, and changed evidence.</p><button class="btn" data-action="reanalyze">${icon("refresh")}Re-analyze current repository</button></div>`}</div>
    ${notice("Comparisons use immutable captured sources and stable entity IDs. Annotation history remains tied to its original snapshot; review decisions are not silently carried across changes.")}`;
}
function diffView(diff) {
  return `<div class="diff-grid">${Object.entries(diff.changes).map(([key, value]) => `<div class="panel padded"><h3>${key[0].toUpperCase() + key.slice(1)}</h3><div class="diff-number">${value.added.length + value.removed.length + value.changed.length}</div><div class="diff-stats"><span class="added">+${value.added.length}</span><span class="removed">−${value.removed.length}</span><span class="changed">~${value.changed.length}</span></div></div>`).join("")}</div>
    <div class="panel"><div class="panel-header"><h2>Source changes</h2><span class="muted">${diff.files.added.length + diff.files.removed.length + diff.files.changed.length} files</span></div>${Object.entries(diff.files).flatMap(([kind, files]) => files.map(file => `<div class="diff-item">${badge(kind === "added" ? "observed" : kind === "removed" ? "contradicted" : "proposed")}<span class="mono">${esc(file)}</span> <span class="muted">· ${kind}</span></div>`)).join("") || '<div class="empty">Source contents are identical.</div>'}</div>
    ${Object.entries(diff.changes).filter(([, value]) => value.added.length + value.removed.length + value.changed.length).map(([key, value]) => `<div class="section-heading"><h2>${key[0].toUpperCase() + key.slice(1)}</h2></div><div class="panel">${["added", "removed", "changed"].flatMap(kind => value[kind].slice(0, 50).map(entity => `<div class="diff-item"><span class="${kind}">${kind === "added" ? "+" : kind === "removed" ? "−" : "~"} ${kind}</span> · ${esc(entityName(entity.after || entity))}</div>`)).join("")}</div>`).join("")}`;
}
function render() {
  const content = state.loadingSnapshot ? '<div class="boot">Loading the selected captured snapshot…</div>' : !state.record ? welcome() : header() + snapshotBar() + (state.busy ? '<div class="progress-panel"><span class="loading-pulse"></span>Parsing repository and linking evidence…</div>' : "") + ({
    walkthrough: () => window.CodeFormWalkthrough.render(state.record),
    workflow: () => window.CodeFormWorkflows.render(state.record),
    overview, architecture, claims: () => toolbar("claims") + notice("Epistemic status describes the kind of support, not a confidence score. Observed source, proposed behavior, test results, and checked proofs are different claims."),
    findings: () => toolbar("findings") + notice("Accept a finding to export a bounded task specification with evidence and acceptance criteria. Review notes do not alter the original analysis."),
    behavior, proofs, agents: agentWorkspace, compare: compareView,
  }[state.view] || overview)();
  document.getElementById("app").innerHTML = shell(content);
  document.title = `code-form — ${state.record ? repoName() + " / " + titles[state.view] : "System explorer"}`;
  renderFiltered();
  window.CodeFormMath?.render(document.getElementById("app"));
  if (state.view === "compare" && state.record && !state.loadingSnapshot) {
    const select = document.getElementById("compare-before");
    if (select && select.options.length > 1) select.selectedIndex = 1;
    const after = document.getElementById("compare-after");
    if (after) after.value = state.record.bundle.id;
  }
}
window.CodeFormRender = render;
async function selectSnapshot(id) {
  const generation = ++snapshotLoadGeneration;
  state.loadingSnapshot = true;
  render();
  let record;
  try { record = await api(`/api/snapshots/${id}`); }
  catch (error) { if (generation === snapshotLoadGeneration) { state.loadingSnapshot = false; state.record = null; render(); } throw error; }
  if (generation !== snapshotLoadGeneration) return;
  state.record = record;
  state.loadingSnapshot = false;
  state.selectedComponent = null;
  state.diff = null;
  state.search = ""; state.status = "all"; state.severity = "all";
  const [, previousSnapshot, previousView, workflowRun] = location.hash.split(/[#/]/);
  const suffix = state.view === "workflow" && previousSnapshot === id && previousView === "workflow" &&
    /^workflow_[0-9a-f]{16}$/.test(workflowRun || "") ? `/${workflowRun}` : "";
  history.replaceState(null, "", `/#${id}/${state.view}${suffix}`);
  render();
}
function navigate(view) {
  state.view = view;
  state.search = ""; state.status = "all"; state.severity = "all";
  if (state.record) history.replaceState(null, "", `/#${state.record.bundle.id}/${view}`);
  render();
}
async function analyze(path) {
  if (state.busy) return;
  state.busy = true;
  closeOverlay(); render();
  try {
    const job = await api("/api/analyze", { path });
    let result = job;
    while (["queued", "running"].includes(result.status)) {
      await new Promise(resolve => setTimeout(resolve, 450));
      result = await api(`/api/jobs/${job.id}`);
    }
    if (result.status !== "complete") throw new Error(result.error || "Analysis failed.");
    state.snapshots = await api("/api/snapshots");
    if (!state.record || state.record.bundle.repository.path !== path) state.view = "walkthrough";
    await selectSnapshot(result.snapshot_id);
    toast("Snapshot saved. Every claim is linked to captured source.");
  } catch (error) { toast(error.message); }
  finally { state.busy = false; render(); }
}
function openOverlay(html, selector = "input,button") {
  lastFocus = document.activeElement;
  document.getElementById("overlay").innerHTML = html;
  document.body.classList.add("overlay-open");
  document.querySelector(`#overlay ${selector}`)?.focus();
}
function closeOverlay() {
  document.getElementById("overlay").innerHTML = "";
  document.body.classList.remove("overlay-open");
  state.drawer = null;
  lastFocus?.focus();
}
function analyzeModal() {
  openOverlay(`<div class="modal-backdrop" data-dismiss="modal"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-head"><div><div class="eyebrow">New system model</div><h2 id="modal-title">Analyze a repository</h2></div><button class="close-button" data-action="close" aria-label="Close dialog">${icon("close")}</button></div><p>Select a local Python repository. code-form reads source and configuration, builds a model, and saves an immutable snapshot.</p><form id="analyze-form"><div class="field"><label for="repository-path">Repository directory</label><input id="repository-path" name="path" placeholder="examples/payment-service" required autocomplete="off" value="${esc(state.record?.bundle.repository.path || "")}"></div><div class="path-hint">Allowed workspace<br><span class="mono">${esc(state.workspace)}</span></div><p class="model-note">Relative paths start at the workspace. To analyze repositories elsewhere, start the server with a broader <code>--workspace</code> directory.</p><div class="modal-actions"><button class="btn" type="button" data-action="close">Cancel</button><button class="btn primary" type="submit">${icon("graph")}Build system model</button></div></form></section></div>`, "#repository-path");
}
function sourceCode(ref) {
  const source = state.record.bundle.sources.find(s => s.path === ref.reference);
  if (!source) return '<div class="empty">Source is absent from this snapshot.</div>';
  const lines = source.content.split("\n"), from = Math.max(1, ref.line_start - 8), to = Math.min(lines.length, Math.max(ref.line_start + 35, Math.min(ref.line_end + 8, ref.line_start + 100)));
  return `<div class="source-header"><span class="mono">${esc(ref.reference)}</span><span>Captured · ${source.sha256.slice(0, 8)} · lines ${from}–${to}</span></div><pre class="source-code">${lines.slice(from - 1, to).map((line, i) => `<span class="source-line ${from + i >= ref.line_start && from + i <= ref.line_end ? "highlight" : ""}"><span class="line-no">${from + i}</span><span class="line-text">${esc(line)}</span></span>`).join("")}</pre>`;
}
function reviewBox(entityId) {
  const review = annotation(entityId);
  return `<div class="review-box"><h3>Review & annotate</h3><form id="review-form" data-entity="${entityId}"><div class="field"><label for="review-status">Review status</label><select id="review-status">${["open", "accepted", "dismissed", "resolved"].map(status => `<option ${review.status === status ? "selected" : ""}>${status}</option>`).join("")}</select></div><div class="field"><label for="review-note">Your reasoning</label><textarea id="review-note" maxlength="4000" placeholder="Record intent, uncertainty, or a validation result…">${esc(review.note)}</textarea></div><div class="review-actions"><button class="btn primary small" type="submit">${icon("check")}Save review</button>${state.drawer?.kind === "finding" ? `<button class="btn small" type="button" data-task="${entityId}" ${review.status === "accepted" ? "" : "disabled"}>${icon("download")}Export task specification</button>` : ""}</div></form>${review.updated_at ? `<div class="review-provenance">${esc(review.author)} · ${timeLabel(review.updated_at)}</div>` : '<div class="review-provenance">Review decisions are separate from generated model claims.</div>'}</div>`;
}
function showDrawer(kind, id, evidenceIndex = 0) {
  const bundle = state.record.bundle;
  let entity, refs = [], title = "", body = "", reviewable = false;
  if (kind === "finding") {
    entity = bundle.findings.find(f => f.id === id); if (!entity) return;
    title = entity.title; refs = entity.evidence_ids.map(sourceRef);
    body = `${badge(entity.severity)} ${badge(entity.status)}<h3>Why this was flagged</h3><p>${esc(entity.rationale)}</p><h3>What remains uncertain</h3><p>${esc(entity.uncertainty)}</p><h3>Suggested validation</h3><p>${esc(entity.suggested_validation)}</p>`;
    reviewable = true;
  } else if (kind === "claim") {
    entity = bundle.claims.find(c => c.id === id); if (!entity) return;
    title = entity.statement; refs = entity.evidence;
    body = `${badge(entity.status)}<h3>Scope & provenance</h3><p>${esc(component(entity.scope)?.name)}<br>Created by ${esc(entity.created_by)}. ${entity.confidence === 1 ? "Directly extracted from the captured source." : "Interpretation requires review."}</p>`;
    reviewable = true;
  } else if (kind === "assumption") {
    entity = bundle.assumptions.find(a => a.id === id); if (!entity) return;
    title = entity.statement; body = `${badge(entity.status)}<h3>Rationale</h3><p>${esc(entity.rationale)}</p><p>Owner: ${esc(entity.owner)}</p>`;
    reviewable = true;
  } else if (kind === "component") {
    entity = component(id); if (!entity) return;
    title = entity.name; refs = [{ reference: entity.path, line_start: entity.line_start, line_end: entity.line_end }];
    body = `${badge(entity.kind)}<h3>Declaration</h3><p class="mono">${esc(entity.signature || entity.path)}</p><p>${esc(entity.docstring || "No declared documentation.")}</p>`;
  } else {
    const ref = sourceRef(id); if (!ref) return;
    title = ref.note || ref.reference; refs = [ref];
  }
  state.drawer = { kind, id, evidenceIndex };
  const chosen = refs[evidenceIndex] || refs[0];
  openOverlay(`<div class="drawer-backdrop" data-dismiss="drawer"></div><section class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><header class="drawer-head"><div><div class="eyebrow">Evidence inspector</div><h2 id="drawer-title">${esc(title)}</h2></div><button class="close-button" data-action="close" aria-label="Close inspector">${icon("close")}</button></header><div class="drawer-body">${body}${refs.length ? `<h3>Source evidence</h3><div class="source-list">${refs.map((ref, i) => `<button class="btn small ${i === evidenceIndex ? "primary" : ""}" data-ref-index="${i}">${esc(ref.reference)}:${ref.line_start}</button>`).join("")}</div>${sourceCode(chosen)}` : ""}${reviewable ? reviewBox(id) : ""}</div></section>`, ".close-button");
}

document.addEventListener("click", async event => {
  const target = event.target.closest("button,a,[data-dismiss],[data-claim],[data-component]");
  if (!target) return;
  try {
    if (target.dataset.view) navigate(target.dataset.view);
    else if (target.dataset.action === "refresh-agents") {
      state.record = await api(`/api/snapshots/${state.record.bundle.id}`);
      render();
      toast("Agent work refreshed from the local API.");
    }
    else if (target.dataset.action === "verify") {
      if (state.proofBusy) return;
      const snapshot = state.record.bundle.id;
      state.proofBusy = true; render();
      try {
        let job = await api(`/api/snapshots/${snapshot}/verify`, {});
        while (["queued", "running"].includes(job.status)) {
          await new Promise(resolve => setTimeout(resolve, 450));
          job = await api(`/api/jobs/${job.id}`);
        }
        if (job.status !== "complete") throw new Error(job.error || "Proof check failed.");
        if (state.record.bundle.id === snapshot) state.record = await api(`/api/snapshots/${snapshot}`);
        toast(`Lean checked ${job.summary.proved} conclusions and ${job.summary.disproved} counterexamples.`);
      } finally { state.proofBusy = false; render(); }
    }
    else if (target.dataset.action === "proof-report") download(`${state.record.verification.id}.json`, JSON.stringify(state.record.verification, null, 2));
    else if (target.dataset.proofDownload) {
      const artifact = (state.record.verification?.artifacts || state.record.proof_plan).find(a => a.id === target.dataset.proofDownload);
      download(`${artifact.id}.lean`, artifact.lean_source, "text/plain");
    }
    else if (target.dataset.proofDependency) {
      event.preventDefault();
      document.getElementById(target.dataset.proofDependency)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    else if (target.dataset.action === "new") analyzeModal();
    else if (target.dataset.action === "close" || target.dataset.dismiss) {
      if (target.dataset.dismiss && event.target !== target) return;
      closeOverlay();
    } else if (target.dataset.action === "reanalyze") await analyze(state.record.bundle.repository.path);
    else if (target.dataset.action === "export") document.getElementById("export-menu").classList.toggle("hidden");
    else if (target.dataset.action === "import") document.getElementById("import-file").click();
    else if (target.dataset.example !== undefined) await analyze(state.examples[Number(target.dataset.example)].path);
    else if (target.dataset.finding) showDrawer("finding", target.dataset.finding);
    else if (target.dataset.claim) showDrawer("claim", target.dataset.claim);
    else if (target.dataset.assumption) showDrawer("assumption", target.dataset.assumption);
    else if (target.dataset.evidence) showDrawer("evidence", target.dataset.evidence);
    else if (target.dataset.sourceComponent) showDrawer("component", target.dataset.sourceComponent);
    else if (target.dataset.component) {
      state.selectedComponent = target.dataset.component;
      if (state.view === "architecture") render(); else { state.view = "architecture"; render(); }
    } else if (target.dataset.graph) { state.graphKind = target.dataset.graph; state.selectedComponent = null; render(); }
    else if (target.dataset.refIndex !== undefined && state.drawer) showDrawer(state.drawer.kind, state.drawer.id, Number(target.dataset.refIndex));
    else if (target.dataset.formal) {
      const formal = state.record.bundle.formal_candidates.find(f => f.id === target.dataset.formal);
      download(`${formal.id}.lean`, formal.source, "text/plain");
    } else if (target.dataset.task) {
      const task = await api(`/api/snapshots/${state.record.bundle.id}/tasks`, { finding_id: target.dataset.task });
      download(`${task.id}.json`, JSON.stringify(task, null, 2));
      toast("Task exported with source scope, evidence, and acceptance criteria.");
    } else if (target.dataset.action === "compare") {
      const before = document.getElementById("compare-before").value, after = document.getElementById("compare-after").value;
      if (before === after) { toast("Choose two different snapshots of this repository."); return; }
      state.diff = await api(`/api/compare?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`);
      document.getElementById("comparison-results").innerHTML = diffView(state.diff);
    }
  } catch (error) { toast(error.message); }
});
document.addEventListener("input", event => {
  if (event.target.id === "search") { state.search = event.target.value; renderFiltered(); }
});
document.addEventListener("change", async event => {
  try {
    if (event.target.id === "snapshot-select") await selectSnapshot(event.target.value);
    else if (event.target.id === "severity-filter") { state.severity = event.target.value; renderFiltered(); }
    else if (["review-filter", "claim-filter"].includes(event.target.id)) { state.status = event.target.value; renderFiltered(); }
    else if (event.target.id === "import-file") {
      const file = event.target.files[0]; if (!file) return;
      if (file.size > 20_000_000) throw new Error("Snapshot exceeds the 20 MB import limit.");
      const result = await api("/api/import", { bundle: JSON.parse(await file.text()) });
      state.snapshots = await api("/api/snapshots");
      await selectSnapshot(result.snapshot_id);
      toast("Snapshot imported and evidence integrity validated.");
    }
  } catch (error) { toast(error.message); }
});
document.addEventListener("submit", async event => {
  event.preventDefault();
  try {
    if (event.target.id === "analyze-form") await analyze(document.getElementById("repository-path").value);
    else if (event.target.id === "review-form") {
      const id = event.target.dataset.entity;
      const result = await api(`/api/snapshots/${state.record.bundle.id}/annotations`, { entity_id: id, status: document.getElementById("review-status").value, note: document.getElementById("review-note").value });
      state.record.annotations[id] = result;
      const drawer = state.drawer;
      render();
      showDrawer(drawer.kind, drawer.id, drawer.evidenceIndex);
      toast("Review saved to this snapshot.");
    }
    else if (event.target.matches(".proposal-review")) {
      const form = event.target;
      await api(`/api/v1/snapshots/${state.record.bundle.id}/proposals/${form.dataset.proposal}/reviews`, {
        decision: form.elements.decision.value, note: form.elements.note.value, reviewer: "local reviewer",
      });
      state.record = await api(`/api/snapshots/${state.record.bundle.id}`);
      render();
      toast("Proposal review saved. The draft and original evidence remain intact.");
    }
  } catch (error) { toast(error.message); }
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") closeOverlay();
  if ((event.key === "Enter" || event.key === " ") && event.target.matches(".graph-node")) { event.preventDefault(); event.target.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
  if (event.key === "Tab" && document.getElementById("overlay").children.length) {
    const focusable = [...document.querySelectorAll("#overlay button:not(:disabled), #overlay input, #overlay select, #overlay textarea, #overlay a[href]")];
    if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable.at(-1)?.focus(); }
    else if (!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0]?.focus(); }
  }
});
window.addEventListener("hashchange", async () => {
  const [, id, view] = location.hash.split(/[#/]/);
  if (state.snapshots.some(s => s.id === id)) { state.view = titles[view] ? view : "walkthrough"; await selectSnapshot(id); }
});
(async function init() {
  try {
    const initial = await api("/api/bootstrap");
    Object.assign(state, initial);
    const [, id, view] = location.hash.split(/[#/]/);
    state.view = titles[view] ? view : "walkthrough";
    const selected = state.snapshots.find(s => s.id === id) || state.snapshots[0];
    if (selected) await selectSnapshot(selected.id); else render();
  } catch (error) {
    document.getElementById("app").innerHTML = `<div class="boot"><h1>Workspace unavailable</h1><p>${esc(error.message)}</p><p>Start the local server with <code>python -m codeform serve --demo</code>.</p></div>`;
  }
})();
