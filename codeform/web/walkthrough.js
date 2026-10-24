"use strict";

window.CodeFormWalkthrough = (() => {
  const selections = new Map();
  const results = new Map();
  const E = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const math = (latex, display = false) => `<span data-latex="${E(latex)}" data-display="${display}"></span>`;
  const label = status => `<span class="badge ${E(status)}">${E(status === "not_run" ? "not checked" : status)}</span>`;
  const chapter = (number, title, subtitle = "") => `<div class="chapter-heading"><span>${number}</span><div><h2>${title}</h2>${subtitle ? `<p>${subtitle}</p>` : ""}</div></div>`;

  function evidence(ref, record) {
    if (!ref) return "";
    const component = record.bundle.components.find(c => c.path === ref.reference &&
      c.line_start === ref.line_start && c.line_end === ref.line_end);
    if (component) return `<button class="btn small" data-source-component="${component.id}">Inspect ${E(ref.reference)}:${ref.line_start}</button>`;
    const captured = record.bundle.evidence.find(e => e.reference === ref.reference &&
      e.line_start <= ref.line_start && e.line_end >= ref.line_end);
    if (captured) return `<button class="btn small" data-evidence="${captured.id}">Inspect ${E(ref.reference)}:${ref.line_start}</button>`;
    return `<button class="btn small" data-walk-captured-source="${E(JSON.stringify(ref))}">Inspect ${E(ref.reference)}:${ref.line_start}</button>`;
  }

  function render(record) {
    const report = record.walkthrough;
    if (!report) return '<div class="panel empty">Walkthrough data is unavailable. Refresh the snapshot from the current server.</div>';
    const chosen = selections.get(report.snapshot_id);
    const model = report.models.find(m => m.id === chosen) || report.models[0];
    const intro = `<section class="walk-intro"><div class="eyebrow">Purpose → model → implementation</div><h2>What must this system make true?</h2><p>${E(report.purpose.text)}</p><div class="walk-origin">${label(report.purpose.status)}<span>Purpose from captured documentation; it is not a proof of behavior.</span>${evidence(report.purpose.evidence, record)}<button class="btn small" data-walk-export="true">Export walkthrough</button></div></section>`;
    if (!model) return intro + fallback(report, record);
    const result = results.get(`${report.snapshot_id}/${model.id}`) || model.default_result;
    return `${intro}<div class="walk-model-selector" aria-label="Choose a model excerpt">${report.models.map(m => `<button class="btn ${m.id === model.id ? "primary" : ""}" data-walk-model="${m.id}">${E(m.name.split(".").at(-1))}</button>`).join("")}</div>
      <div class="walk-model-note"><strong>${E(model.name)}</strong><span>Supported model excerpt · ${E(model.purpose_status)}</span></div>
      ${chapter("01", "Define the objects", model.purpose)}
      <section class="panel walk-definition"><div class="walk-state"><span class="detail-label">State and domains</span>${math(model.state_latex, true)}</div><div class="walk-transition"><span class="detail-label">Engineering operation as a mathematical transition</span>${math(model.transition_latex, true)}</div>
      <div class="notation-grid">${model.notation.map((n, i) => `<button class="notation-tile" data-walk-notation="${i}" data-model="${model.id}"><span class="notation-symbol">${math(n.symbol)}</span><strong>${E(n.name)}</strong><small>${E(n.unit)}</small></button>`).join("")}</div><p class="walk-help">Select a symbol to see its domain, meaning, units, and source correspondence.</p></section>
      ${chapter("02", "State the intended properties", "An obligation expresses what should hold. Its checker status shows what has actually been established for this model.")}
      <section class="walk-properties">${model.principles.map(p => `<a class="walk-property" href="#walk-${p.id}" data-walk-goal="${p.id}"><div>${label(p.status)}<h3>${E(p.title)}</h3></div><div class="walk-property-math">${math(p.latex, true)}</div></a>`).join("")}</section>
      ${chapter("03", "Follow a concrete example", "Change the input or event ordering. This evaluates the captured mathematical model, not the target program.")}
      <section class="panel scenario-panel"><div class="scenario-presets">${model.scenarios.map(s => `<button class="btn small" data-walk-preset="${s.id}" data-model="${model.id}">${E(s.name)}</button>`).join("")}</div>${scenarioForm(model, result.inputs)}<div id="scenario-error" role="alert" class="error-message"></div><div id="scenario-result">${renderResult(result)}</div></section>
      ${chapter("04", "See how the argument fits together", "Definitions and assumptions support component lemmas; those lemmas support stronger conclusions.")}
      ${argument(model)}
      ${chapter("05", "Inspect the proof and the implementation", "Open the Lean artifact and supporting source. Keep the model theorem and implementation correspondence separate.")}
      <div class="walk-proofs">${model.principles.map(p => proof(p, record)).join("")}</div>
      <section class="walk-boundary"><h3>Where this explanation stops</h3><p>${E(model.boundary)}</p><div class="header-actions"><button class="btn" data-view="architecture">Explore architecture</button><button class="btn" data-view="findings">Review candidate gaps</button><button class="btn" data-view="agents">Discuss through agent proposals</button></div></section>`;
  }

  function fallback(report, record) {
    return `<section class="walk-boundary"><h3>Mathematical reconstruction is not available for this repository</h3><p>The current adapters do not supply a supported semantic model here. The application can show observed structure and documented requirements, but it cannot infer a whole-system proof from them.</p><div class="header-actions"><button class="btn" data-view="architecture">Inspect observed structure</button><button class="btn" data-view="claims">Follow source evidence</button><button class="btn" data-view="agents">Review analysis proposals</button></div></section>
      ${chapter("01", "Start from documented requirements", "Documentation status is a project claim; code-form has not run the named tests or proved those requirements.")}
      <div class="panel">${report.requirements.slice(0, 16).map(r => `<div class="walk-requirement"><div><code>${E(r.id)}</code> ${label(r.status)}<h3>${E(r.title)}</h3><p>${E(r.statement)}</p><small>Declared status: ${E(r.declared_status)}</small></div>${evidence(r.evidence, record)}</div>`).join("") || '<div class="empty">No structured requirements were captured. Establish purpose, important operations, and invariants with the project owner before treating inferred behavior as intent.</div>'}</div>
      ${report.requirements.length > 16 ? `<p class="model-note">Showing 16 of ${report.requirements.length} documented requirements. The walkthrough API contains the complete list.</p>` : ""}
      ${report.unsupported.map(a => `<div class="notice"><span>${E(a.name)}: ${E(a.reason)}</span></div>`).join("")}`;
  }

  function scenarioForm(model, inputs) {
    const fields = model.kind === "integer-transfer"
      ? ["source", "destination", "amount"].map(name => `<div class="field"><label for="walk-${name}">${name[0].toUpperCase() + name.slice(1)}</label><input id="walk-${name}" name="${name}" inputmode="numeric" required value="${E(inputs[name])}" maxlength="81"></div>`).join("")
      : `<div class="field"><label for="walk-state">Initial state</label><select id="walk-state" name="state">${model.states.map(s => `<option ${s === inputs.state ? "selected" : ""}>${E(s)}</option>`).join("")}</select></div><div class="field scenario-events"><label for="walk-events">Events in order</label><input id="walk-events" name="events" value="${E(inputs.events.join(", "))}" placeholder="${E(model.events.join(", "))}"><small>Modeled events: ${E(model.events.join(", "))}</small></div>`;
    return `<form id="walk-scenario-form" data-model="${model.id}" class="scenario-inputs">${fields}<button class="btn primary" type="submit">Run model example</button></form>`;
  }

  function renderResult(result) {
    const relevant = result.checks.filter(c => c.applicable);
    const violated = relevant.some(c => !c.holds) || result.counterexamples?.length;
    const title = result.outcome === "rejected" ? "The model rejects this request"
      : violated ? "This example violates an intended property"
      : !result.assumptions_hold ? result.kind === "finite-workflow"
        ? "This example follows the workflow; the initial terminal-state premise does not apply"
        : "This input is outside the stated invariant assumptions"
      : "The example preserves the applicable properties";
    return `<div class="scenario-summary ${violated ? "violated" : ""}"><strong>${title}</strong><span>Modeled example · no target execution · not a universal proof</span></div>
      <ol class="scenario-trace">${result.trace.map((step, i) => `<li><span class="trace-index">${i + 1}</span><div><strong>${E(step.name)}</strong><div class="trace-state">${step.latex ? math(step.latex) : E(String(step.state))}</div><p>${E(step.detail)}</p>${step.holds !== undefined ? `<span class="${step.holds ? "added" : "removed"}">${step.holds ? "Guard accepts" : "Guard rejects"}</span>` : ""}</div></li>`).join("")}</ol>
      ${result.counterexamples?.length ? `<div class="counterexample"><strong>Terminal-state violation in this example</strong>${result.counterexamples.map(t => `<p>${E(t.from)} ── ${E(t.event)} → ${E(t.to)}</p>`).join("")}<small>This is a model scenario witness, not a new checker result.</small></div>` : ""}
      ${result.checks.length ? `<div class="scenario-checks">${result.checks.map(c => `<div><strong>${E(c.name)}</strong><span class="${c.applicable ? c.holds ? "added" : "removed" : "muted"}">${!c.applicable ? "Outside assumptions" : c.holds ? "Holds for this example" : "Fails for this example"}</span>${c.latex ? math(c.latex) : ""}</div>`).join("")}</div>` : '<p class="model-note">No successful result was returned. Successful-return postconditions are not exercised by this example.</p>'}
      <p class="walk-help">${E(result.boundary)}</p>`;
  }

  function argument(model) {
    const assumptions = [...new Map(model.principles.flatMap(p => p.assumptions).map(a => [a.id, a])).values()];
    const composed = model.principles.filter(p => p.dependencies.length);
    const basic = model.principles.filter(p => !p.dependencies.length);
    return `<section class="argument-map"><div><span class="detail-label">Definitions and hypotheses</span>${assumptions.map(a => `<div class="argument-premise"><small>${E(a.kind)}</small><p>${E(a.statement)}</p></div>`).join("")}</div><span class="argument-arrow" aria-hidden="true">⇒</span><div><span class="detail-label">Model obligations / component lemmas</span>${basic.map(p => `<button data-walk-goal="${p.id}" class="argument-goal">${label(p.status)}<strong>${E(p.title)}</strong></button>`).join("")}</div>${composed.length ? `<span class="argument-arrow" aria-hidden="true">⇒</span><div><span class="detail-label">Composition</span>${composed.map(p => `<button data-walk-goal="${p.id}" class="argument-goal">${label(p.status)}<strong>${E(p.title)}</strong></button>`).join("")}</div>` : ""}</section><p class="model-note">This argument structure comes from the supported adapter. It does not claim whole-repository composition or that every listed hypothesis is logically necessary.</p>`;
  }

  function proof(p, record) {
    return `<article class="panel walk-proof" id="walk-${p.id}"><div class="panel-header"><h2>${E(p.title)}</h2>${label(p.status)}</div><div class="padded">${math(p.latex, true)}<p class="model-note">${E(p.support)} · ${E(p.scope.replaceAll("-", " "))}</p><div class="proof-columns"><div><h3>Given these hypotheses</h3>${p.assumptions.map(a => `<div class="proof-assumption"><span>${E(a.kind)}</span><p>${E(a.statement)}</p></div>`).join("")}</div><div><h3>Mathematical argument</h3><ol class="proof-steps">${p.reasoning.map(r => `<li><strong>${E(r.title)}</strong><p>${E(r.detail)}</p></li>`).join("")}</ol></div></div><div class="proof-evidence-bar">${p.evidence.map(ref => evidence(ref, record)).join("")}<button class="btn small" data-view="proofs">Open checker workspace</button></div><details class="proof-details"><summary>Lean statement, proof, and trusted dependencies</summary><pre class="lean-preview">${E(p.lean_source)}</pre><div class="axiom-ledger"><strong>Lean theorem: ${E(p.theorem)}</strong><p>${p.axioms === null ? "Not checked for this exact source yet." : p.axioms.length ? p.axioms.map(a => `<code>${E(a)}</code>`).join(" ") : "Lean reports no axiom dependencies."}</p><p class="model-note">Foundational axioms are dependencies of the proof logic. Requirements are obligations, not added axioms.</p></div>${p.checker ? `<p class="model-note">${E(p.checker.version)} · exit code ${p.checker.exit_code} · input ${E(p.checker.source_sha256.slice(0, 16))}</p><pre class="checker-output">${E(p.checker.stdout)}</pre>` : ""}<button class="btn small" data-proof-download="${p.id}">Download Lean input</button></details></div></article>`;
  }

  function selectedModel(id) {
    return state.record.walkthrough.models.find(m => m.id === id);
  }

  async function evaluate(model, inputs) {
    const snapshot = state.record.bundle.id;
    const result = await api(`/api/v1/snapshots/${snapshot}/scenarios`, { model_id: model.id, inputs });
    if (result.snapshot_id !== snapshot || result.model_id !== model.id) throw new Error("Scenario response does not match the selected model.");
    results.set(`${snapshot}/${model.id}`, result);
    return result;
  }

  document.addEventListener("click", async event => {
    const target = event.target.closest("[data-walk-model],[data-walk-preset],[data-walk-notation],[data-walk-goal],[data-walk-export],[data-walk-captured-source]");
    if (!target) return;
    event.preventDefault();
    try {
      if (target.dataset.walkCapturedSource) {
        const ref = JSON.parse(target.dataset.walkCapturedSource);
        openOverlay(`<div class="drawer-backdrop" data-dismiss="drawer"></div><section class="drawer" role="dialog" aria-modal="true" aria-labelledby="walk-source-title"><header class="drawer-head"><div><div class="eyebrow">Captured documentation</div><h2 id="walk-source-title">${E(ref.reference)}</h2></div><button class="close-button" data-action="close" aria-label="Close inspector">×</button></header><div class="drawer-body"><p class="model-note">This source establishes documented purpose or intent. It does not establish implementation correctness.</p>${sourceCode(ref)}</div></section>`, ".close-button");
      } else if (target.dataset.walkExport) {
        download(`${state.record.bundle.id}-walkthrough.json`, JSON.stringify(state.record.walkthrough, null, 2));
      } else if (target.dataset.walkModel) {
        selections.set(state.record.bundle.id, target.dataset.walkModel);
        renderApp();
      } else if (target.dataset.walkPreset) {
        const model = selectedModel(target.dataset.model);
        const preset = model.scenarios.find(s => s.id === target.dataset.walkPreset);
        const result = await evaluate(model, preset.inputs);
        if (state.record.bundle.id !== result.snapshot_id) return;
        renderApp();
        document.getElementById("walk-scenario-form")?.scrollIntoView({ block: "center", behavior: "smooth" });
      } else if (target.dataset.walkGoal) {
        document.getElementById(`walk-${target.dataset.walkGoal}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
      } else {
        const model = selectedModel(target.dataset.model);
        const notation = model.notation[Number(target.dataset.walkNotation)];
        openOverlay(`<div class="modal-backdrop" data-dismiss="modal"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="notation-title"><div class="modal-head"><h2 id="notation-title">${E(notation.name)}</h2><button class="close-button" data-action="close" aria-label="Close notation explanation">×</button></div><div class="notation-explanation">${math(notation.symbol, true)}<p>${E(notation.meaning)}</p><p>Domain: ${notation.domain.includes("\\") ? math(notation.domain) : E(notation.domain)}<br>Unit: ${E(notation.unit)}</p><p class="model-note">${E(model.boundary)}</p>${model.evidence.map(ref => evidence(ref, state.record)).join("")}</div></section></div>`, ".close-button");
        window.CodeFormMath.render(document.getElementById("overlay"));
      }
    } catch (error) {
      toast(error.message);
    }
  });

  document.addEventListener("submit", async event => {
    if (event.target.id !== "walk-scenario-form") return;
    event.preventDefault();
    const form = event.target, model = selectedModel(form.dataset.model);
    const inputs = model.kind === "integer-transfer"
      ? { source: form.elements.source.value, destination: form.elements.destination.value, amount: form.elements.amount.value }
      : { state: form.elements.state.value, events: form.elements.events.value.split(",").map(s => s.trim()).filter(Boolean) };
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    document.getElementById("scenario-error").textContent = "";
    try {
      const result = await evaluate(model, inputs);
      const selected = selections.get(state.record.bundle.id) || state.record.walkthrough.models[0]?.id;
      if (state.view !== "walkthrough" || state.record.bundle.id !== result.snapshot_id || selected !== result.model_id) return;
      document.getElementById("scenario-result").innerHTML = renderResult(result);
      window.CodeFormMath.render(document.getElementById("scenario-result"));
    } catch (error) {
      const target = document.getElementById("scenario-error");
      if (target) target.textContent = `Input rejected: ${error.message} No new example was evaluated; the previous result remains below.`;
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  });

  function renderApp() { window.CodeFormRender(); }
  // The application and this module load as ordinary scripts. The application
  // owns snapshot state, request tokens, overlays, and source inspection.
  return { render, math };
})();
