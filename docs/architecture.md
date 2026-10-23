# Implementation architecture

## Reasoning from the product's purpose

An engineer needs to decide whether a statement about a system is trustworthy
and whether a proposed change is worth investigating. A diagram alone cannot
answer either question. The application centers on a durable model whose
statements point to inspectable evidence.

The first release needs three independent layers:

1. **Observation:** read bounded source input and extract structural facts
   without trusting or running the target repository.
2. **Interpretation:** derive candidate gaps and bounded properties while
   preserving their assumptions and uncertainty.
3. **Review:** show source behind claims, record human intent, compare versions,
   and export scoped follow-up work.

This separation lets later AI and formal tools contribute to the same model
without changing the meaning of an observed fact.

## Core and language adapter

`codeform/analyzer.py` captures eligible source text and hashes, parses Python
ASTs, and builds a canonical JSON bundle. Target modules are never imported.
The only target-associated subprocess is Git metadata lookup, with filesystem
monitoring and optional locks disabled and a timeout.

The adapter extracts modules, classes, functions, methods, imports, explicit
call edges, direct test calls, literal HTTP-method decorators, precise Markdown
API contracts, and literal finite transition tables.

Call sequences preserve lexical order without simulating branches or scheduling.
Nested function execution and most dynamic binding are not resolved. Imports
inside functions can form dependency cycles, but findings explain that deferred
imports may be harmless.

Initial rules report parser errors, direct test-reference gaps, import cycles,
silent broad exception handlers, documented route gaps, and terminal-state
counterexamples. Rule IDs and scopes produce stable finding identifiers.

## Identity and evidence

Every source has a normalized relative path, UTF-8 content, and SHA-256 hash.
The repository content hash combines sorted path/hash pairs. Snapshot IDs
combine repository path, source content hash, Git commit, analyzer version,
implementation hash, and Python runtime version. Analysis timestamps are stored
outside the bundle to keep repeated analysis deterministic.

Git SHA identifies the baseline, not necessarily the exact working tree.
Captured sources and content hashes identify what was actually analyzed.
Pointers include their commit field and line range; the containing bundle
carries the content identity. Uncommitted modifications are visible.

Component IDs derive from paths and qualified names. Claim IDs also include
their precise statement. Relationship IDs derive from type and endpoints.
Changes to source positions or evidence appear as changed entities; new
statements appear as additions/removals.

`codeform/model.py` validates structure, hashes, source ranges, identifiers,
entity references, model checks, and summary counts.
`schemas/bundle.schema.json` documents the format and reuses the claim schema.
Imported bundles undergo integrity checks before storage. Validation
establishes internal consistency, not authenticity or truth.

## Persistence and review

`codeform/store.py` saves immutable bundles under `.codeform/`. Writes use a
temporary file and atomic replacement. Re-saving the same bundle is idempotent;
different content with the same snapshot ID is rejected.

Annotations are separate per-snapshot files containing status, note, author,
and time. Accepting a finding permits export of a task containing its snapshot,
commit/content identity, evidence files, uncertainty, suggested test, and
acceptance criteria.

Task export does not execute the task. The execution policy has an empty
command allowlist, no network access, isolation required, and human merge review.

## Local HTTP and UI

`codeform/server.py` serves the frontend and JSON API using Python's standard
library and binds to `127.0.0.1`. Analysis uses two workers and a bounded queue.
The UI polls jobs and surfaces failures.

The allowed workspace bounds repository paths after resolution. Storage
defaults to the workspace and can be configured with `--data-dir`.
Source inspection reads captured text, not live paths.

Mutations require a random session token. Host and Origin checks reject
cross-site requests; there is no CORS access. A restrictive content policy
and escaped rendering keep repository strings as data.

The frontend uses local HTML, CSS, JavaScript, and SVG. It needs no CDN,
Node build process, or remote service. Node is optional for syntax checks and
browser acceptance tests. The graph caps visible nodes at 30 for readability
while retaining the complete model.

This is a local reviewer application, not an authenticated multi-user service.

## Formal boundary

The finite checker enumerates transitions and checks whether a declared
terminal state can change. Results carry case counts and counterexamples.
Successful checks use `tested` with a finite-model boundary; failures use
`contradicted`.

Lean candidates encode the table and propose a theorem with a visible proof
placeholder. They are always `proposed`, with checker status `not_run`.
Implementation refinement, persistence, concurrency, and unmodeled events
remain outside the artifact.

## Extensions

The next central milestone is
[mathematical verification and repair](formal-verification.md): contracts,
supported source semantics, symbolic obligations, checked Lean proofs,
counterexamples, and re-verification of repairs. This document describes the
implemented observation/review foundation; the linked design describes the
proof engine still to build.

Another language adapter can produce the same bundle. AI reconstruction can
consume structural facts and emit separately labeled interpretations. Proof
checking needs a controlled runner with exact toolchain and checker evidence.

Incremental extraction, broader resolution, evaluation metrics, isolated patch
execution, and reviewed PR creation remain future work. The current release
provides the observation and review loop those features need.
