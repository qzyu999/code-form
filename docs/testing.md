# Testing code-form

## Start the application

From the checkout, create a local environment and run the seeded demo:

```powershell
python -m venv --without-pip .venv
.\.venv\Scripts\python.exe -m codeform serve --demo
```

Open http://127.0.0.1:7331. Five example repositories appear in the snapshot
selector. The app uses captured source; edits appear after re-analysis.
Stop with Ctrl+C in the server terminal and wait for the prompt.
See [operations.md](operations.md) for restart, storage, and troubleshooting.

For a unified human/AI review, open **Review report**. On inference-exchange,
confirm that proposed LaTeX is visible while supported Lean obligations remain
zero and the live owner gate stays unapproved. Save standalone HTML, stop the
server, and confirm its mathematics and embedded JSON work offline.
`tests/reports-browser.cjs` checks these behaviors on the existing preview
without submitting reviews or running target code.

## Inspect a repository

Select **payment-service**:

1. Open Architecture, select a module, and inspect its captured source.
2. Open Claim ledger, search for `route`, and inspect a decorator claim.
3. Open Findings and search for `refunds`. The README documents
   `POST /refunds`; no matching literal decorator was found.
4. Inspect the suggested validation and uncertainty. Check framework wiring
   before deciding that a runtime route is absent.
5. Accept a finding, add reasoning, and save the review.
6. Export its task specification with source scope and acceptance criteria.
7. Reload and confirm the review persisted. Export and re-import its bundle.

Select **cyclic-service** to inspect the dependency cycle and deferred import.
Whether the cycle causes a runtime issue needs separate validation.

## Edit, re-analyze, compare

Use a copy to preserve the intentional example:

```powershell
Copy-Item -LiteralPath examples/order-workflow -Destination .codeform/order-workflow-playground -Recurse
```

1. Analyze `.codeform/order-workflow-playground`.
2. Open Behavior. `cancelled --reopen→ pending` contradicts the declared
   terminal-state invariant.
3. Download the Lean candidate. It contains an unchecked `sorry` placeholder.
4. Remove `("cancelled", "reopen"): "pending",` from the copied `workflow.py`.
5. Re-analyze. The terminal-state finding disappears and the finite check passes.
6. Open Compare and choose the earlier and later snapshots.
7. Select the original snapshot. Its captured counterexample remains available.

The result applies to the finite table. Add a runtime regression test before
assuming the application implements the requirement.

## Core suite

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check codeform/web/app.js
```

On macOS/Linux use `.venv/bin/python`. No test dependencies are required.
Temporary directories stay under `.codeform/test-tmp` and their resolved
paths are checked before recursive cleanup.

## Example tests

These repositories were authored for this project; tests use the standard
library. Run them with the same local environment:

```powershell
$examplePython = (Resolve-Path .venv/Scripts/python.exe).Path
Push-Location examples/payment-service
& $examplePython -m unittest discover -s tests -v
Pop-Location
```

Repeat for `examples/order-workflow` and `examples/cyclic-service`.
Tests pass despite intentionally omitted requirements. The analyzer never
runs repository tests automatically.

## Optional browser acceptance suite

The optional UI suite requires Node 20+, Playwright Core, and its Chromium.
The application itself has no Node dependencies.

If these tools are not installed, install them into a disposable local directory:

```powershell
npm install --prefix .codeform/browser-tools playwright-core
.\.codeform\browser-tools\node_modules\.bin\playwright-core.cmd install chromium
$env:PLAYWRIGHT_MODULE = (Resolve-Path .codeform/browser-tools/node_modules/playwright-core).Path
node tests/browser.cjs
```

Keep the server running with `--demo` in another terminal. `CODEFORM_URL`
selects a different local port. An existing Playwright Core installation can
be used by pointing `PLAYWRIGHT_MODULE` at it.

The suite verifies source inspection, graph interaction, persisted review,
task and Lean downloads, UI-driven analysis, editing, comparison, imports,
reload, filters, and mobile overflow. It edits its own
`.codeform/browser-fixture` and records a review note on the order example.
Artifacts are written under `.codeform/browser-artifacts`:

- `overview-desktop.png`
- `finding-evidence.png`
- `snapshot-comparison.png`
- `overview-mobile.png`
- downloaded JSON and Lean files

The checked-proof examples and optional real Lean/browser tests are described
in [proof-checking.md](proof-checking.md). Core proof integration tests run when
the pinned Lean toolchain is available; otherwise they are explicitly skipped.

The [agent API](api.md) is tested through its Python HTTP client, including
exact obligation binding, Lean failure/retry, idempotent requests, captured
evidence validation, proposal reviews, and persisted history. The optional
`node tests/agents-browser.cjs` checks Agent workspace against a seeded server
after running `examples/agent_client_demo.py`.

The [math-first walkthrough](math-first-walkthrough.md) has model/API tests
for exact integer examples, rejection, failed assumptions, workflow events,
proof-input matching, and unsupported fallback. The optional
`node tests/walkthrough-browser.cjs` verifies local LaTeX, notation, scenarios,
Lean/source links, export, and mobile layout against a seeded server.
