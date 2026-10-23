# Roadmap

The local first release implements the observation and review loop for Python.
Unchecked items remain future work. See [docs/architecture.md](docs/architecture.md).

## Next priority — Mathematical verification and repair

The next product milestone is a real verification/repair loop over a documented
Python subset. See [the design and acceptance criteria](docs/formal-verification.md).
Existing structural analysis supports this work; UI expansion is secondary.
Track implementation in [issue #2](https://github.com/qzyu999/code-form/issues/2).

- [ ] Define reviewed contracts, environment assumptions, and explicit normal/exceptional semantics.
- [ ] Connect captured supported Python source to a versioned semantic representation with a stated trust boundary.
- [ ] Check assumption feasibility and generate symbolic verification obligations.
- [ ] Produce validated counterexamples, preserving the original specification.
- [ ] Run a pinned Lean checker and inspect transitive proof dependencies.
- [ ] Surface scoped proof results and their assumptions in CLI artifacts and the UI.
- [ ] Propose an isolated repair and regression test, then re-verify affected obligations.
- [ ] Demonstrate integer-transfer and workflow examples with valid, invalid, and unsupported cases in CI.

## Phase 0 — Define the model

- [x] Choose the first language and target repository type: local Python repositories.
- [x] Define a versioned schema for components, interfaces, flows, claims, assumptions, invariants, evidence, and findings.
- [x] Define epistemic labels: observed, inferred, proposed, tested, proved, contradicted, unknown.
- [x] Specify evidence pointers using commit SHA plus file path and line/symbol range, backed by captured source hashes.
- [ ] Create a small hand-labeled evaluation repository.

## Phase 1 — Read-only repository analyzer

- [x] Capture repository identity, commit SHA, languages, dependencies, and suggested test commands.
- [x] Extract imports, declarations, supported call edges, literal route decorators, and test references.
- [x] Generate dependency graph and Mermaid diagrams.
- [x] Produce an evidence-linked claim ledger.
- [x] Identify direct test-reference gaps and explicit documented API mismatches as candidates.
- [x] Make output deterministic and record model/tool/runtime versions.

## Phase 2 — Quality and evaluation

- [ ] Compare generated model against a human-reviewed reference model.
- [ ] Measure claim precision, evidence validity, graph coverage, and repeat-run stability.
- [ ] Test whether findings are actionable and non-duplicative.
- [ ] Add incremental analysis for changed files and commits.
- [x] Allow engineers to dismiss findings and record review reasoning per snapshot.
- [ ] Aggregate false-positive metrics across human-reviewed evaluation repositories.

## Phase 3 — Interactive UI

- [x] Browse components, edges, flows, and explicit state machines.
- [x] Click a model claim to view captured supporting code and direct test references.
- [x] Filter findings by severity, review status, and free-text search.
- [ ] Add confidence, evidence-strength, and subsystem filters.
- [x] Compare architecture models across snapshots, including commit or working-tree changes.
- [x] Annotate claims, assumptions, and findings with review provenance.
- [ ] Edit canonical assumptions and requirements through a versioned amendment model.

## Phase 4 — Formal methods

The checked items below describe limited capabilities in the current release.
Unchecked items and the priority milestone above are required for the intended
proof engine.

- [x] Select terminal-state invariants for explicit finite transition tables.
- [x] Exhaustively check the extracted literal model and show counterexamples.
- [x] Generate unchecked Lean statements for human review.
- [ ] Build a Lean 4 model for one bounded subsystem.
- [ ] Compile and check proofs in CI.
- [ ] Distinguish proof of a model from proof that implementation refines that model.
- [ ] Explore refinement checks or executable model tests where feasible.

## Phase 5 — Bounded agent workflows

- [x] Convert accepted findings into exported scoped task specifications.
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
