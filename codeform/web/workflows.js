"use strict";

window.CodeFormWorkflows = (() => {
  const runs = new Map(), selections = new Map();
  const E = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  let busy = false;
  const badge = value => `<span class="badge ${E(value)}">${E(value.replaceAll("_", " "))}</span>`;
  const math = latex => `<span data-latex="${E(latex)}" data-display="true"></span>`;
  const current = record => {
    const [, snapshot, view, linkedRun] = location.hash.split(/[#/]/);
    const requested = snapshot === record.bundle.id && view === "workflow" ? linkedRun : null;
    return record.workflow_runs?.find(r => r.id === (requested || runs.get(record.bundle.id))) ||
      record.workflow_runs?.filter(r => r.mode !== "preview").at(-1) || record.workflow_runs?.at(-1);
  };

  function graph(run) {
    const ranks = {};
    function rank(id) {
      if (ranks[id] !== undefined) return ranks[id];
      const node = run.nodes.find(n => n.id === id);
      ranks[id] = node.depends_on.length ? Math.max(...node.depends_on.map(rank)) + 1 : 0;
      return ranks[id];
    }
    run.nodes.forEach(n => rank(n.id));
    const counts = {}, positions = {};
    for (const node of run.nodes) {
      const level = ranks[node.id], row = counts[level] || 0;
      counts[level] = row + 1;
      positions[node.id] = { x: 20 + level * 178, y: 25 + row * 104 };
    }
    const width = (Math.max(...Object.values(ranks)) + 1) * 178 + 18;
    const height = Math.max(...Object.values(counts)) * 104 + 20;
    const selected = selections.get(run.id);
    return `<div class="flow-map"><div class="flow-map-head"><strong>Analysis DAG</strong><span>Parallel branches share the same snapshot and specification</span></div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Dependency-controlled analysis DAG">
    <defs><marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 10 5 0 10Z" fill="#a394bd"/></marker></defs>
    ${run.nodes.flatMap(n => n.depends_on.map(d => {
      const a = positions[d], b = positions[n.id];
      return `<path d="M${a.x + 150} ${a.y + 33} C${a.x + 168} ${a.y + 33},${b.x - 17} ${b.y + 33},${b.x} ${b.y + 33}" fill="none" stroke="#b9afca" stroke-width="1.4" marker-end="url(#flow-arrow)"/>`;
    })).join("")}
    ${run.nodes.map(n => {
      const p = positions[n.id], words = n.label.split(" "), cut = Math.ceil(words.length / 2);
      return `<g transform="translate(${p.x},${p.y})" class="flow-node ${E(n.status)} ${selected === n.id ? "selected" : ""}" data-flow-node="${n.id}" tabindex="0" role="button" aria-label="Inspect ${E(n.label)}">
      <rect width="150" height="70" rx="8"/><text x="10" y="18">${E(words.slice(0, cut).join(" "))}</text><text x="10" y="32">${E(words.slice(cut).join(" "))}</text><text x="10" y="49" class="flow-executor">${E(n.executor)}</text><text x="10" y="62" class="flow-status">${E(n.status.replaceAll("_", " "))}</text><title>${E(n.prompt)}</title></g>`;
    }).join("")}</svg><div class="flow-legend"><span>Built-in: deterministic tools</span><span>External: agent submission</span><span>Human: exact-artifact review</span></div></div>`;
  }

  function render(record) {
    const run = current(record);
    const intro = `<section class="panel padded"><div class="section-heading"><div><h2>One run, one source revision, one specification</h2><p>Agents work when dependencies are ready. The join collects evidence and unknowns, not votes.</p></div><span class="badge proposed">External model executor</span></div><p class="model-note">This controller calls no model automatically. Built-in tasks run here; external roles submit artifacts through the API. Target code, tests, patches, merges, and deployments are not executed.</p>
    <form id="flow-create"><div class="field"><label for="flow-objective">Analysis objective</label><textarea id="flow-objective" name="objective" required maxlength="4000">Explain this repository's purpose, state, requirements, trust and failure boundaries, and candidate mathematical obligations from captured evidence.</textarea></div><button class="btn primary" type="submit" ${busy ? "disabled" : ""}>Create and prepare analysis DAG</button></form></section>`;
    if (!run) return intro + '<div class="panel empty agent-section">No workflow run for this snapshot. Create a run to pin its objective and prepare source facts and requirements.</div>';
    const selected = selections.get(run.id) || (["complete", "preview_complete"].includes(run.state) ? "synthesis" : null) ||
      run.nodes.find(n => n.status === "awaiting_review")?.id || run.nodes.find(n => n.status === "awaiting_agent")?.id || run.nodes[0].id;
    selections.set(run.id, selected);
    const node = run.nodes.find(n => n.id === selected);
    const reportLink = `<div class="agent-links"><a href="/reports/${record.bundle.id}?workflow_id=${run.id}" target="_blank" rel="noopener">Read this run as a report</a><a href="/api/v1/snapshots/${record.bundle.id}/report?format=json&workflow_id=${run.id}">JSON for AI review</a></div>`;
    const readyBuiltins = run.state !== "superseded" && run.nodes.some(n => n.executor === "builtin" && ["ready", "interrupted"].includes(n.status));
    const controls = `<div class="flow-controls"><select id="flow-select" aria-label="Workflow run">${record.workflow_runs.map(r => `<option value="${r.id}" ${r.id === run.id ? "selected" : ""}>${E(r.id)} · ${E(r.state.replaceAll("_", " "))}</option>`).join("")}</select>${badge(run.state)}<button class="btn" data-flow-action="refresh">Refresh</button><button class="btn primary" data-flow-action="advance" ${!readyBuiltins || busy ? "disabled" : ""}>Run ready built-in steps</button><button class="btn" data-flow-action="export">Export run</button></div><div class="flow-pins"><span>Snapshot <code>${E(run.snapshot_id)}</code></span><span>Specification <code>${E(run.spec_sha256.slice(0, 16))}</code></span><span>Template <code>${E(run.version)}</code></span></div><p class="model-note">${E(run.objective)}</p>`;
    return intro + controls + (run.mode === "preview" ? `<div class="notice flow-preview"><span><strong>Read-only E2E preview — not owner-approved</strong><br>Preview checkpoints replace human gates only in this separate demonstration. The live review run remains gated. Claims, proposed tests, and completed stages are not implementation proofs.</span></div>` : "") +
      (run.state === "superseded" ? `<div class="notice"><span>This run is preserved as history and superseded by ${run.superseded_by.map(E).join(", ")}. New work and reviews must use the replacement.</span></div>` : "") + graph(run) + `<div class="flow-ready">Ready in parallel: ${run.parallel_ready.map(id => `<button data-flow-node="${id}" class="btn small">${E(run.nodes.find(n => n.id === id).label)}</button>`).join("") || "No ready work."}</div>` +
      reportLink + nodePanel(run, node, record) + `<details class="panel flow-events"><summary>Immutable event history · ${run.events.length}</summary><ol>${run.events.map(e => `<li><code>${e.sequence}</code> ${E(e.node_id)} → <strong>${E(e.status)}</strong><small>${E(e.created_at)}</small></li>`).join("")}</ol></details>`;
  }

  function sourceLink(ref) {
    return `<button class="btn small" data-walk-captured-source="${E(JSON.stringify({
      reference: ref.path, line_start: ref.line_start, line_end: ref.line_end,
    }))}">Inspect ${E(ref.path)}:${ref.line_start}</button>`;
  }

  function diagram(data) {
    const positions = Object.fromEntries(data.nodes.map((n, i) => [n.id, { x: 18 + (i % 3) * 235, y: 22 + Math.floor(i / 3) * 105 }]));
    return `<div class="flow-model-diagram"><svg viewBox="0 0 730 ${Math.ceil(data.nodes.length / 3) * 105 + 20}" role="img" aria-label="Proposed system diagram">
    ${data.edges.map(e => { const a = positions[e.source], b = positions[e.target]; return `<path d="M${a.x + 95},${a.y + 28} L${b.x + 95},${b.y + 28}" stroke="#b5a8ce" stroke-width="1.4" marker-end="url(#flow-arrow)"/>`; }).join("")}
    ${data.nodes.map(n => { const p = positions[n.id]; return `<g transform="translate(${p.x},${p.y})"><rect width="195" height="58" rx="7" fill="#f8f5ff" stroke="#d3c7e6"/><text x="12" y="31" font-size="11" fill="#807193">${E(n.label)}</text></g>`; }).join("")}</svg><details><summary>Mermaid source for this proposed diagram</summary><pre class="proposal-content">${E(data.mermaid)}</pre></details></div>`;
  }

  function artifactView(artifact) {
    if (!artifact) return '<p class="model-note">This node has no output yet.</p>';
    const content = artifact.content;
    const validation = content.validation || (content.checked_attempts ? content : null);
    return `<section class="flow-artifact"><div class="flow-artifact-id"><code>${E(artifact.id)}</code><span>${E(artifact.actor)}</span><code>${E(artifact.sha256.slice(0, 16))}</code></div><p>${E(content.summary)}</p>${content.diagram ? diagram(content.diagram) : ""}
    ${validation ? `<div class="notice flow-validation"><span><strong>Verification coverage</strong><br>${validation.checked_attempts.length} checked proof/counterexample references · ${validation.supported_obligations} supported adapter obligations.<br>${E(validation.scope)}<br>Target tests executed: ${validation.target_tests_executed ? "yes" : "no"}.</span></div>` : ""}
    ${content.purpose ? `<h3>Documented purpose</h3><p class="model-note">${E(content.purpose.text)}</p>` : ""}
    ${content.requirements ? `<h3>Captured requirements · ${content.requirements.length}</h3><div class="panel">${content.requirements.slice(0, 12).map(r => `<div class="walk-requirement"><div><code>${E(r.id)}</code><h3>${E(r.title)}</h3><p>${E(r.statement)}</p><small>Documentation status: ${E(r.declared_status)}</small></div></div>`).join("")}</div>` : ""}
    ${content.claims?.length ? `<h3>Source-linked claims and proposed mathematics</h3>${content.claims.map(c => `<div class="flow-claim">${badge(c.status)}<p>${E(c.statement)}</p>${c.latex ? `<div class="math-formula">${math(c.latex)}</div>` : ""}<div class="proof-evidence-bar">${c.evidence.map(sourceLink).join("")}</div></div>`).join("")}` : ""}
    ${content.assumptions?.length ? `<h3>Assumptions</h3><ul class="summary-list">${content.assumptions.map(a => `<li>${E(a)}</li>`).join("")}</ul>` : ""}
    ${content.limitations?.length ? `<h3>Unresolved boundaries</h3><ul class="summary-list">${content.limitations.map(a => `<li>${E(a)}</li>`).join("")}</ul>` : ""}
    ${content.test_plan?.length ? `<h3>Proposed tests · not executed</h3><ul class="summary-list">${content.test_plan.map(a => `<li>${E(a)}</li>`).join("")}</ul>` : ""}
    ${content.checked_attempts ? `<h3>Checked evidence · ${content.checked_attempts.length}</h3><p class="model-note">Fixed adapter obligations supported: ${content.supported_obligations}. Checked references do not prove the whole proposed model.</p>${content.checked_attempts.map(a => `<p>${badge(a.status)} ${E(a.obligation_id)}</p>`).join("")}` : ""}
    ${content.unresolved?.length ? `<h3>Remaining gaps</h3><ul class="summary-list">${content.unresolved.map(a => `<li>${E(typeof a === "string" ? a : a.text)}</li>`).join("")}</ul>` : ""}
    <details class="proof-details"><summary>Complete artifact data</summary><pre class="proposal-content">${E(JSON.stringify(content, null, 2))}</pre></details></section>`;
  }

  function nodePanel(run, node, record) {
    if (run.state === "superseded") node = { ...node, status: "superseded" };
    const reviewed = node.executor === "human" ? run.nodes.find(n => n.id === node.depends_on[0])?.artifact : null;
    const artifact = node.artifact || reviewed;
    return `<section class="panel flow-node-panel"><div class="panel-header"><div><div class="eyebrow">${E(node.executor)} · ${E(node.prompt_version)}</div><h2>${E(node.label)}</h2></div>${badge(node.status)}</div><div class="padded"><p class="model-note">Depends on: ${node.depends_on.map(E).join(", ") || "Pinned snapshot"}${node.blocked_by.length ? `<br>Waiting for: ${node.blocked_by.map(E).join(", ")}` : ""}</p><details class="proof-details"><summary>Role prompt and fixed input context</summary><p class="model-note">${E(node.prompt)}</p><button class="btn small" data-flow-action="context">Export task context</button></details>
    ${artifactView(artifact)}
    ${node.executor === "human" && node.status === "awaiting_review" ? `<div class="notice"><span>Review the artifact above before releasing dependencies. Approval records model/proposal review; it does not prove claims, edit requirements, or execute source.</span></div><form id="flow-review" data-node="${node.id}" data-snapshot="${run.snapshot_id}" data-workflow="${run.id}" data-artifact="${reviewed.id}" data-artifact-sha="${reviewed.sha256}"><div class="field"><label for="flow-note">Your review reasoning</label><textarea id="flow-note" name="note" required maxlength="4000"></textarea></div><div class="field"><label for="flow-decision">Decision</label><select id="flow-decision" name="decision"><option value="approved">Approve this draft for the next stages</option><option value="needs_changes">Needs changes — preserve this run and revise</option></select></div><button class="btn primary" type="submit">Record human review</button></form>` : ""}
    ${node.executor === "external" && node.status === "awaiting_agent" ? `<div class="notice"><span>Waiting for an external agent. No model is running automatically. Export the context, use the API, or submit an evidence-linked JSON output here.</span></div><form id="flow-output" data-node="${node.id}" data-snapshot="${run.snapshot_id}" data-workflow="${run.id}"><div class="field"><label for="flow-output-json">External artifact JSON</label><textarea id="flow-output-json" name="output" required placeholder="Use the snapshot/specification/input hashes from the context."></textarea></div><button class="btn" type="submit">Submit external output</button></form>` : ""}
    </div></section>`;
  }

  async function refresh() {
    state.record = await api(`/api/snapshots/${state.record.bundle.id}`);
    window.CodeFormRender();
  }
  async function advance(run) {
    let job = await api(`/api/v1/snapshots/${run.snapshot_id}/workflows/${run.id}/advance`, {});
    while (["queued", "running"].includes(job.status)) {
      await new Promise(resolve => setTimeout(resolve, 350));
      job = await api(`/api/v1/jobs/${job.id}`);
    }
    if (job.status === "failed") throw new Error(job.error);
  }
  document.addEventListener("click", async event => {
    const target = event.target.closest("[data-flow-node],[data-flow-action]");
    if (!target) return;
    const run = current(state.record);
    try {
      if (target.dataset.flowNode) { selections.set(run.id, target.dataset.flowNode); window.CodeFormRender(); }
      else if (target.dataset.flowAction === "refresh") await refresh();
      else if (target.dataset.flowAction === "export") download(`${run.id}.json`, JSON.stringify(run, null, 2));
      else if (target.dataset.flowAction === "context") {
        const id = selections.get(run.id);
        const context = await api(`/api/v1/snapshots/${run.snapshot_id}/workflows/${run.id}/nodes/${id}/context`);
        download(`${run.id}-${id}-context.json`, JSON.stringify(context, null, 2));
      } else if (target.dataset.flowAction === "advance") {
        busy = true; window.CodeFormRender();
        await advance(run); await refresh();
      }
    } catch (error) { toast(error.message); }
    finally {
      const refreshControls = busy;
      busy = false;
      if (refreshControls && state.view === "workflow") window.CodeFormRender();
    }
  });
  document.addEventListener("change", event => {
    if (event.target.id === "flow-select") {
      runs.set(state.record.bundle.id, event.target.value);
      history.replaceState(null, "", `/#${state.record.bundle.id}/workflow/${event.target.value}`);
      window.CodeFormRender();
    }
  });
  document.addEventListener("submit", async event => {
    if (!["flow-create", "flow-review", "flow-output"].includes(event.target.id)) return;
    event.preventDefault();
    const form = event.target, snapshot = state.record.bundle.id, run = current(state.record);
    const button = form.querySelector("button[type=submit]"); button.disabled = true;
    try {
      if (form.id !== "flow-create") {
        const [, urlSnapshot] = location.hash.split(/[#/]/);
        if (state.loadingSnapshot || form.dataset.snapshot !== snapshot || form.dataset.workflow !== run?.id ||
            (urlSnapshot && urlSnapshot !== snapshot)) {
          throw new Error("This form belongs to a different snapshot or run. Refresh before reviewing.");
        }
      }
      if (form.id === "flow-create") {
        const created = await api(`/api/v1/snapshots/${snapshot}/workflows`, { objective: form.elements.objective.value });
        runs.set(snapshot, created.id);
        await advance(created);
      } else if (form.id === "flow-review") {
        const node = run.nodes.find(n => n.id === form.dataset.node);
        const artifact = run.nodes.find(n => n.id === node.depends_on[0]).artifact;
        if (form.dataset.artifact !== artifact.id || form.dataset.artifactSha !== artifact.sha256) {
          throw new Error("The reviewed artifact changed. Reload the exact draft before submitting.");
        }
        await api(`/api/v1/snapshots/${snapshot}/workflows/${run.id}/nodes/${node.id}/reviews`, {
          snapshot_id: snapshot, spec_sha256: run.spec_sha256, artifact_id: artifact.id,
          artifact_sha256: artifact.sha256, actor: "local reviewer",
          decision: form.elements.decision.value, note: form.elements.note.value,
        });
      } else {
        const output = JSON.parse(form.elements.output.value);
        await api(`/api/v1/snapshots/${snapshot}/workflows/${run.id}/nodes/${form.dataset.node}/outputs`, output);
      }
      await refresh();
    } catch (error) { toast(error.message); button.disabled = false; }
  });
  document.addEventListener("keydown", event => {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches(".flow-node")) {
      event.preventDefault(); event.target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    }
  });
  return { render };
})();
