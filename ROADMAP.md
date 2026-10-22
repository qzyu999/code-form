# Roadmap

This roadmap is exploratory. Validate the core model before expanding into autonomous code changes.

## Phase 0 — Define the model

- [x] Choose Python for the initial prototype.
- [x] Define an initial versioned JSON analysis bundle.
- [x] Anchor extracted evidence to file paths and line ranges where available, plus Git commit SHA when available.
- [ ] Create a small hand-labeled evaluation repository.

## Phase 1 — Read-only repository analyzer

- [x] Capture repository identity, commit SHA, branch, working-tree status, languages, and file inventory.
- [x] Extract Python imports and class/function declarations with source evidence.
- [x] Generate a best-effort internal import graph and Mermaid diagram.
- [x] Produce an evidence-linked ledger for narrow structural observations.
- [x] Label Python parse errors as observations, not automatically confirmed defects.
- [ ] Improve import resolution for relative imports and package submodules.
- [ ] Extract routes/API endpoints and test references with language-specific adapters.
- [ ] Add schema validation and golden-file tests for the bundle format.
- [ ] Record dependency manifests and test commands.
- [ ] Add a hand-labeled evaluation corpus and measure precision, evidence validity, graph coverage, and repeat-run stability.

## Phase 2 — Quality and evaluation

- [ ] Compare generated model against a human-reviewed reference model.
- [ ] Measure claim precision, evidence validity, graph coverage, and repeat-run stability.
- [ ] Test whether findings are actionable and non-duplicative.
- [ ] Add incremental analysis for changed files and commits.
- [ ] Track false positives and allow engineers to dismiss or correct findings.

## Phase 3 — Interactive UI

- [ ] Browse components, edges, flows, and state machines.
- [ ] Click a model claim to view supporting code and tests.
- [ ] Filter findings by severity, confidence, evidence strength, and subsystem.
- [ ] Compare architecture models across commits.
- [ ] Edit/annotate assumptions and requirements, with provenance.

## Phase 4 — Formal methods

- [ ] Select a small class of properties with clear semantics.
- [ ] Generate candidate formal statements for human review.
- [ ] Build a Lean 4 model for one bounded subsystem.
- [ ] Compile and check proofs in CI.
- [ ] Distinguish proof of a model from proof that implementation refines that model.
- [ ] Explore refinement checks or executable model tests where feasible.

## Phase 5 — Bounded agent workflows

- [ ] Convert accepted findings into scoped task specifications.
- [ ] Give agents isolated worktrees, minimal credentials, and bounded tool access.
- [ ] Require a proposed test and clear acceptance criterion before editing.
- [ ] Run formatters, tests, static analysis, and relevant proofs.
- [ ] Produce a patch summary linking changes to the original finding and model claims.
- [ ] Open draft PRs only; require human review and normal branch protections.
- [ ] Add cancellation, cost limits, timeouts, and audit logs.

## Initial-release non-goals

- Full formal verification of arbitrary programs.
- Automatically inferring product intent without human input.
- Unrestricted self-modification or auto-merge.
- Supporting every language and framework.
