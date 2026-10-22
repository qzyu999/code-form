# Roadmap

This roadmap is exploratory. Prioritize validating the core model before expanding into autonomous code changes.

## Phase 0 — Define the model

- [ ] Choose the first language and target repository type.
- [ ] Define a versioned schema for components, interfaces, flows, claims, assumptions, invariants, evidence, and findings.
- [ ] Define epistemic labels: observed, inferred, proposed, tested, proved, contradicted, unknown.
- [ ] Specify evidence pointers using commit SHA plus file path and line/symbol range.
- [ ] Create a small hand-labeled evaluation repository.

## Phase 1 — Read-only repository analyzer

- [ ] Capture repository identity, commit SHA, languages, dependencies, and test commands.
- [ ] Extract imports, declarations, call edges where supported, routes/API endpoints, and test references.
- [ ] Generate dependency graph and Mermaid diagrams.
- [ ] Produce an evidence-linked claim ledger.
- [ ] Identify untested public interfaces and documented-vs-implemented mismatches as *candidates*, not automatically confirmed defects.
- [ ] Make output deterministic where possible and record model/tool versions.

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
- [ ] Require a proposed test and a clear acceptance criterion before editing.
- [ ] Run formatters, tests, static analysis, and relevant proofs.
- [ ] Produce a patch summary linking changes to the original finding and model claims.
- [ ] Open draft PRs only; require human review and normal branch protections.
- [ ] Add cancellation, cost limits, timeouts, and audit logs.

## Non-goals for the first release

- Full formal verification of arbitrary programs.
- Automatically inferring product intent without human input.
- Unrestricted self-modification or auto-merge.
- Supporting every language and framework.
