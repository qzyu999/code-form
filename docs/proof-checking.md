# Operating the Lean proof demo

## What is implemented

The optional checker supports two models:

1. Integer transfers matching an exact documented AST shape, selected by
   data-only `contracts.toml` declarations.
2. Explicit finite workflow tables with declared terminal states.

It emits complete Lean source from fixed templates, runs pinned Lean 4.19.0,
checks its exit status and transitive theorem axiom dependencies, and saves
the proof report separately from the immutable source snapshot.

The demo has universal arithmetic theorems and an induction theorem over
every finite event sequence. Counterexamples are also checked by Lean.
The implementation does not include an open-ended AI mathematician, a general
SMT solver, arbitrary Python semantics, a formally verified translator, or
automatic patch execution.

## Install and start

Windows / PowerShell, from the checkout:

```powershell
.\scripts\setup.ps1
.\scripts\setup-lean.ps1
.\.venv\Scripts\python.exe -m codeform serve --demo --data-dir .codeform/math-demo --port 7332
```

The Lean setup downloads the official v4.19.0 Windows release into
`.codeform/tools`. It installs nothing globally. The download needs network
access, and the archive/toolchain requires disk space.

The pinned version is recorded in `lean-toolchain`. On Linux/macOS, use a
Lean installer such as elan to provision that version or extract the matching
official release for your platform. Run with the environment's Python:

```bash
.venv/bin/python -m codeform serve --demo --data-dir .codeform/math-demo --port 7332 --lean /absolute/path/to/lean
```

An existing pinned `lean` on `PATH` is detected. An explicit `--lean` overrides
auto-detection. If the checker is missing or its reported version differs from
4.19.0, the app remains usable for static analysis and shows why checking is
unavailable. It never upgrades unchecked results to proved.

Open http://127.0.0.1:7332. Stop with Ctrl+C and reload the browser after a
restart, as described in [operations.md](operations.md).

## Explore the mathematics

Select `verified-transfer`, open **Proofs & mathematics**, then click
**Check proofs with Lean**. The check produces:

| Implementation | Conservation | Nonnegative successful outputs | Composed safety |
| --- | --- | --- | --- |
| `transfer_unchecked` | Proved | Disproved | Disproved |
| `transfer_guarded` | Proved | Proved | Proved |

The counterexample is source=10, destination=0, amount=11, yielding (-1, 11).
The guarded implementation rejects this amount. Its composed theorem uses
conservation and nonnegativity as lemmas.

For each card, inspect:

- the exact mathematical formula and scope;
- assumptions, preconditions, definitions, and the translator trust boundary;
- the reasoning steps and lemma dependencies;
- the captured Python declaration;
- the Lean proof and `#print axioms` output;
- checker version, source hash, exit code, and diagnostics.

Select `verified-workflow` and check its proof. Lean checks that a single
modeled event preserves terminal states, then uses induction to establish
preservation through arbitrary finite lists of events. Select `order-workflow`
to check its violating `cancelled --reopen→ pending` transition.

**Export proof report** downloads the verification record. Each proof card
also offers the exact Lean input for independent inspection.

## Contracts and supported source

`contracts.toml` contains data, never evaluated expressions:

```toml
schema_version = "1.0.0"
adapter = "integer-transfer-v1"

[[contracts]]
function = "transfer.transfer_guarded"
properties = ["conservation", "nonnegative", "safety"]
```

The function must have exactly `source`, `destination`, `amount` arguments,
an `amount <= 0` guard raising a built-in `ValueError`, an optional
`amount > source` guard, and the exact return
`source - amount, destination + amount`. A docstring is allowed.
Decorators, defaults, imports, shared state, arbitrary expressions, side effects,
name shadowing, and additional executable statements are unsupported.

The contract assumes exact built-in integers; annotations do not enforce this
at runtime. Resource exhaustion and Python runtime/module mutation are outside
the model. Rejected outcomes become `none`, successful pairs become `some`.
The translator is an explicit trusted adapter. Its tests exercise behavior,
but do not establish a formal proof of translation equivalence.

Workflow checking concerns the extracted finite table. Unlisted pairs are
identity transitions in the model; a runtime implementation may reject them.
That difference remains visible in the proof assumptions. Workflow functions
themselves are not translated or universally verified.

The initial feasibility diagnostic has witnesses for these fixed contracts.
There is no general consistency solver or support for arbitrary assumptions.
A user-supplied theorem or Lean program is not accepted as checker input.

## Commands and persistence

```powershell
.\.venv\Scripts\python.exe -m codeform verify examples/verified-transfer --store .codeform/math-demo --output .codeform/transfer-proofs.json
.\.venv\Scripts\python.exe -m codeform verify examples/verified-workflow --store .codeform/math-demo --output .codeform/workflow-proofs.json
```

CLI exit codes:

- `0`: nonempty generated obligation set, all proved.
- `2`: at least one checked counterexample, no unsupported/unfinished checks.
- `1`: missing checker, unsupported obligations, checker error/timeout, or no obligations.

Reports are written as `snapshot_<id>.verification.json` beside their snapshot.
Generated Lean inputs are under `proof-runs/inputs`. Re-checking refreshes the
latest report without modifying the source snapshot. A UI bundle import does
not import proof authority: the receiving instance must check captured source
locally. Bundle exports omit verification reports; export the proof report
separately or back up the data directory.

One proof job runs at a time. Each generated input has a 30-second wall timeout
and a 400,000-heartbeat Lean bound; finite model sizes are capped. Shutdown
waits for running proof checks.

## Proof acceptance and trusted computing base

The checker rejects source placeholders and unapproved constructs, requires a
successful checker exit and axiom report, and rejects warnings or unexpected
transitive axioms. The permitted foundational dependencies are `propext`,
`Classical.choice`, and `Quot.sound`. These are reported on each theorem,
including when no axiom dependencies are used. Business requirements are not
invented as Lean axioms. No `native_decide` is used.

The trusted base includes the local Lean kernel/compiler and bundled `Std`,
the fixed code-form generator and source adapter, and the local operating
environment. The setup pins the release URL and version; it does not currently
verify a separately published archive checksum.

Lean input is generated from validated data; repository Lean files, lake
configuration, plugins, arbitrary imports, and target Python are never run.
Custom Lean library-path environment variables are removed from the process.
There is no OS-level filesystem/network/memory sandbox around the compiler.
The runner's safety boundary is its fixed generated code, bounded input size,
heartbeat limit, and process timeout. Do not extend it to arbitrary Lean
execution without adding isolation.

## Verify the checker

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

When the pinned Lean exists, integration tests actually check the arithmetic
and induction proofs, validate counterexamples, reject false/incomplete proofs
and invented axioms, and verify report persistence. Without Lean, those
integration tests are explicitly skipped; structural tests still run.

The optional proof UI test uses the Playwright setup in [testing.md](testing.md):

```powershell
$env:CODEFORM_URL = 'http://127.0.0.1:7332'
node tests/proofs-browser.cjs
```

It checks the UI-triggered Lean run, proof cards, axiom ledger, downloads,
induction, reload persistence, and mobile layout.
