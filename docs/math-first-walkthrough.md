# Math-first repository walkthrough

The default analysis view now starts with documented purpose and a mathematical
model excerpt, before the structural metrics and finding lists. The first
implementation supports the existing integer-transfer and finite-workflow
adapters. Other repositories receive documented purpose and requirement evidence
with an explicit semantic-model gap.

Tracking: [issue #4](https://github.com/qzyu999/code-form/issues/4).
This walkthrough builds on the checker/API foundation in PR #3.

## The reading sequence

1. Read the purpose captured from the root README. It is documentation evidence,
   not a proof that the implementation satisfies that purpose.
2. Select a supported model excerpt. Inspect its state and transition formulas.
3. Select a symbol to inspect its meaning, unit, mathematical domain, and source.
4. Read the intended propositions and their checker status.
5. Run an example, rejection, counterexample, or failed-assumption scenario.
6. Follow the argument from assumptions through lemmas to a composed conclusion.
7. Open the Lean statement/proof, axiom dependencies, and captured implementation.
8. Review findings or agent proposals after understanding the model boundary.

Existing Overview, Architecture, Claim ledger, Findings, Proofs, and Agent
workspace deep links remain available.

## Run locally

Use the existing project-local environment:

```powershell
.\scripts\setup.ps1
.\scripts\setup-lean.ps1
.\.venv\Scripts\python.exe -m codeform serve --demo --data-dir .codeform/walkthrough-demo --port 7333
```

Open http://127.0.0.1:7333. On macOS/Linux use `.venv/bin/python` and configure
pinned Lean as described in [proof-checking.md](proof-checking.md).
Stop with Ctrl+C in the server terminal.

Lean is optional for reading the model and evaluating examples. Proof status
remains unverified until the checker has accepted the exact generated input.
Open Proofs & mathematics and run the checker to establish the supported
theorems, then return to Start here.

## Transfer example

The model uses exact integers for source balance, destination balance, and
transfer amount:

```text
S = (s, d)
successful transition: (s, d) -> (s - a, d + a)
```

Conservation requires `x + y = s + d`.
Nonnegativity additionally requires `x >= 0` and `y >= 0` under the stated
initial-balance assumptions.

Use the same overdraft input on the unchecked and guarded models. The unchecked
model returns a negative source balance. The guarded model rejects it.
The scenario does not weaken the requirement to make the guarded version pass.

Try a negative initial destination balance. The UI shows that the example is
outside the advertised nonnegativity assumptions. The raw predicate may fail,
but that does not disprove a theorem whose hypotheses do not apply.

The UI submits integer decimal strings to the scenario API. Arithmetic remains
exact even beyond JavaScript's safe integer range. Values are limited to 80
digits for the interactive display. Decimal fractions, booleans, and malformed
values are rejected.

## Workflow example

The walkthrough uses the captured state set, event set, transition table, and
declared terminal states. Pick an initial state and an ordered event list.
The trace shows each modeled transition and any terminal-state violation.

The scenario display permits at most 32 modeled events. That UI limit does not
limit the Lean induction theorem, which quantifies over every finite list.
Events not present in the modeled event type are rejected as unsupported input.
Unlisted state/event pairs use identity transitions in the mathematical model;
the source implementation may reject them. That boundary stays visible.

## Math, proof, and implementation boundaries

LaTeX describes the supported model. Its readable explanations are authored
adapter descriptions, not generated theorem discoveries.
The argument diagram shows the known assumptions and lemma relationships;
it does not infer whole-repository proof composition.

The walkthrough distinguishes:

- documented purpose and requirements;
- stated mathematical obligations;
- locally checked model theorems and counterexamples;
- one simulated model example;
- the source-to-model translator's trusted boundary;
- unsupported or unmodeled implementation behavior.

Scenario execution never imports or runs target Python, invokes a provider,
edits files, or promotes an example to a proof result. Checker support is
shown only when the report's snapshot, repository hash, and exact Lean input
hash match the displayed obligation.

For unsupported repositories, the UI presents captured README purpose and
structured `docs/requirements/*.md` statements. A declared `implemented`
status remains documentation evidence; code-form has not run the linked
tests or verified that requirement.

## API and exported artifact

```text
GET  /api/v1/snapshots/{snapshot_id}/walkthrough
POST /api/v1/snapshots/{snapshot_id}/scenarios
```

Scenario requests contain only `model_id` and `inputs`. Models are resolved from
the captured snapshot. A request cannot inject a program or alternate semantics.
Mutation requests use the normal local session token.

The Python client exposes `walkthrough(snapshot_id)` and
`scenario(snapshot_id, model_id, inputs)`. The walkthrough JSON export contains
the purpose, definitions, notation, propositions, proof support, and default
model examples. It is a separate generated view, not a replacement for the
canonical bundle or checker report.

## LaTeX assets and rendering

KaTeX 0.16.11, its MIT license, and required fonts are vendored under
`codeform/web/vendor/katex`. There is no runtime CDN or npm build dependency.
Rendering uses `trust: false`, strict parsing, and expansion/size limits.
Invalid formulas fall back visibly to escaped LaTeX source.

Repository text is escaped rather than interpreted as HTML. The content policy
allows style attributes needed by locally generated KaTeX layout, while scripts,
stylesheets, fonts, and network access remain restricted to the local origin.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check codeform/web/walkthrough.js
node --check codeform/web/math.js
```

Backend tests exercise exact arithmetic, normal/rejected outcomes, failed
assumptions, model-only execution, event-domain limits, stale proof evidence,
documented requirement fallback, and the scenario API.

With the optional Playwright setup from [testing.md](testing.md):

```powershell
$env:CODEFORM_URL = 'http://127.0.0.1:7333'
node tests/walkthrough-browser.cjs
```

The browser check covers the default entry, local math/font loading, notation,
scenario comparison, invalid input, Lean/source access, export, workflow,
unsupported fallback, and mobile layout.
