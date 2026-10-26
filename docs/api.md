# Agent API

code-form exposes a local, versioned HTTP API so an external reasoning agent
can inspect a repository, read evidence, obtain exact proof obligations, try
checker strategies, and save reviewable proposals. The UI, CLI, Python client,
and future MCP/model adapters can build on this service.

The API calls no model and needs no OpenAI API key. An external agent supplies
reasoning using its own configured model connection. This release provides
tools and records, not an automatic model-driven research agent.

`GET /api/v1/snapshots/{snapshot_id}/report` joins the saved analysis,
selected workflow, review state, and checker coverage for human/AI review.
Use `format=json|markdown|html`, optional `workflow_id`, and `download=1`
for standalone HTML. The client exposes `report(snapshot_id, workflow_id)`;
the CLI exposes `api report ... --output DIRECTORY`.
See [review-reports.md](review-reports.md) for selection, provenance, and exports.

## Start

Use the checkout's local virtual environment:

```powershell
.\scripts\setup.ps1
.\scripts\setup-lean.ps1
.\.venv\Scripts\python.exe -m codeform serve --demo --data-dir .codeform/api-demo --port 7332
```

The Lean setup is optional for evidence and proposals, and required for proof
attempts. On Linux/macOS, use `.venv/bin/python` and pinned Lean 4.19.0 as
described in [proof-checking.md](proof-checking.md).

- UI: http://127.0.0.1:7332
- OpenAPI 3.1 contract: http://127.0.0.1:7332/api/v1/openapi.json
- Capabilities and limits: http://127.0.0.1:7332/api/v1/capabilities

Stop with Ctrl+C in the server terminal. Reload clients after restart.
The service is loopback-only and intended for one local reviewer. Use one
server per data directory.

## Session access

Read operations are local HTTP GET requests. Mutations require JSON and the
session-local `X-Codeform-Token` header. Obtain the token from
`GET /api/bootstrap`; the Python client does this automatically.
Tokens change when the process restarts. Recreate the client after a restart.
Do not publish tokens or add them to repository files.

Host and Origin checks reject cross-site access. There is no CORS access,
remote authentication, or multi-user reviewer identity verification. The token
protects local mutations; it does not establish who authored a review.

PowerShell example:

```powershell
$serviceUrl = 'http://127.0.0.1:7332'
$bootstrap = Invoke-RestMethod -Uri "$serviceUrl/api/bootstrap"
$headers = @{ 'X-Codeform-Token' = $bootstrap.token }
$body = @{ path = 'examples/verified-transfer' } | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri "$serviceUrl/api/v1/snapshots" -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri "$serviceUrl/api/v1/jobs/$($job.id)"
```

Repeat the job GET until status is `complete` or `failed`. Elapsed time alone
does not establish that analysis finished.

## Operations

| Method and path | Behavior |
| --- | --- |
| `GET /api/v1/capabilities` | Checker availability, strategies, operations, and unsupported features. |
| `GET /api/v1/openapi.json` | Machine-readable API contract. |
| `GET /api/v1/snapshots` | Snapshot summaries. |
| `POST /api/v1/snapshots` | Analyze `{ "path": "..." }` inside the allowed workspace; returns a job. |
| `GET /api/v1/jobs/{job_id}` | Poll an analysis, full-verification, or proof-attempt job. |
| `GET /api/v1/snapshots/{snapshot_id}` | Captured model, annotations, and latest complete verification. |
| `GET /api/v1/snapshots/{snapshot_id}/sources?path=...` | Captured source text and hash; optional `line_start`/`line_end`. |
| `GET /api/v1/snapshots/{snapshot_id}/context` | Versioned agent instructions, assumptions, obligations, and history. |
| `GET /api/v1/snapshots/{snapshot_id}/walkthrough` | Purpose, notation, mathematical model excerpts, default scenarios, and proof support. |
| `POST /api/v1/snapshots/{snapshot_id}/scenarios` | Evaluate a captured model example without executing target code or recording a new proof. |
| `GET /api/v1/snapshots/{snapshot_id}/obligations` | Immutable contexts, declarations, IDs/hashes, proof scope, and reference source. |
| `POST /api/v1/snapshots/{snapshot_id}/attempts` | Try a controlled strategy against an exact obligation. |
| `GET /api/v1/snapshots/{snapshot_id}/attempts` | Immutable attempt history, including unsuccessful checks. |
| `GET /api/v1/snapshots/{snapshot_id}/attempts/{attempt_id}` | Detailed result and Lean diagnostics. |
| `POST /api/v1/snapshots/{snapshot_id}/proposals` | Save a requirement, contract draft, explanation, or repair suggestion. |
| `GET /api/v1/snapshots/{snapshot_id}/proposals` | Immutable proposals with their latest review. |
| `POST /api/v1/snapshots/{snapshot_id}/proposals/{proposal_id}/reviews` | Append a separate review decision and reasoning. |
| `GET /api/v1/snapshots/{snapshot_id}/proposals/{proposal_id}/reviews` | Complete immutable review history for a proposal. |
| `POST /api/v1/snapshots/{snapshot_id}/verify` | Check the complete generated proof set using `{}`. |
| `GET /api/v1/snapshots/{snapshot_id}/verification` | Latest complete verification report. |
| `GET /api/v1/compare?before=...&after=...` | Compare captured source and structural model entities. |

Existing `/api/...` UI endpoints continue working. New agent integrations
should use `/api/v1/...`.

## Python client

`codeform.client.CodeFormClient` uses the standard library and talks only to a
configured loopback service. Running from the checkout needs no installation.

```python
from codeform.client import CodeFormClient

client = CodeFormClient("http://127.0.0.1:7332")
job = client.wait(client.analyze("examples/verified-transfer"))
snapshot_id = job["snapshot_id"]

context = client.context(snapshot_id)
goals = client.obligations(snapshot_id)["obligations"]
goal = next(g for g in goals
            if g["name"].endswith("guarded") and g["property"] == "conservation")

job = client.wait(client.submit_attempt(
    snapshot_id, goal, strategy="generated", agent="my reasoning agent",
    request_id="conservation-attempt-1",
))
result = client.attempt(snapshot_id, job["attempt_id"])
print(result["status"], result.get("checker", {}).get("stdout"))
```

The client exposes discovery, snapshots, analysis, jobs, context, obligations,
sources, attempts, proposals, complete review history, snapshot comparison,
and complete verification.
It also exposes the [math-first walkthrough](math-first-walkthrough.md) and
model scenario evaluation.
`ApiError.status` contains a rejected request's HTTP status.
`wait()` times out after 120 seconds by default; a client timeout does not
cancel server execution. Poll the same job to inspect it later.

The authored demonstration shows the whole request loop:

```powershell
.\.venv\Scripts\python.exe examples/agent_client_demo.py --url http://127.0.0.1:7332
```

It analyzes the transfer example, attempts a weak strategy, retries the fixed
goal with the generated strategy, checks a counterexample, and saves a draft
repair. It neither calls a model nor edits source. Open **Agent workspace** in
the UI and refresh to inspect the records and review the proposal.

## CLI client

These commands call the running service:

```powershell
.\.venv\Scripts\python.exe -m codeform api --url http://127.0.0.1:7332 capabilities
.\.venv\Scripts\python.exe -m codeform api snapshots
.\.venv\Scripts\python.exe -m codeform api analyze examples/verified-transfer --wait
.\.venv\Scripts\python.exe -m codeform api context snapshot_REPLACE_WITH_ID
.\.venv\Scripts\python.exe -m codeform api obligations snapshot_REPLACE_WITH_ID
.\.venv\Scripts\python.exe -m codeform api attempt snapshot_REPLACE_WITH_ID obligation_REPLACE_WITH_ID --strategy generated --wait
.\.venv\Scripts\python.exe -m codeform api source snapshot_REPLACE_WITH_ID transfer.py --start 4 --end 8
```

Replace identifiers with returned values. `--url` defaults to
`http://127.0.0.1:7332` and belongs before the action. Use
`python -m codeform api --help` and each action's `--help` for complete options.

Save a proposal with `api propose SNAPSHOT --file proposal.json`. Record
review with `api review SNAPSHOT PROPOSAL --decision accepted --note "..."
--reviewer "..."`. Proposal content is read from the JSON file literally.

## Fixed proof obligations and attempts

An obligation consists of captured-source identity, the immutable generated
Lean context, exact theorem declaration, expected result kind, and a hash.
An attempt supplies:

```json
{
  "obligation_id": "obligation_REPLACE_WITH_ID",
  "obligation_sha256": "REPLACE_WITH_RETURNED_SHA256",
  "strategy": "generated",
  "agent": "external reasoning agent",
  "request_id": "attempt-1"
}
```

Strategies:

- `generated`: the complete proof from the trusted adapter.
- `simplify`: try `simp_all` against the same declaration.
- `decide`: try `decide` against the same declaration.

The service reconstructs the input from its own immutable declaration and
controlled strategy. Attempts cannot supply proof source, definitions, new
axioms, a replacement statement, or modified assumptions. Unknown fields and
hash mismatches are rejected. The checker requires an axiom report naming the
exact expected theorem. A valid unrelated theorem cannot prove the advertised
obligation.

This fixes the internal binding gap identified in the initial audit. It does
not create a formally verified source translator or permit arbitrary
LLM-generated Lean. Extending proof bodies requires an isolated execution
boundary and a richer tactic interface.

An attempt returns a job. After completion, read its immutable record.
Result statuses include `proved`, `disproved`, `error`, `timeout`, and `not_run`.
A checker error is a failed attempt to establish the result, not a proof
that the property is false. The current counterexample obligations are
generated by supported adapters, not discovered by a general solver.

Optional `request_id` provides idempotency per snapshot. Repeating the same
ID, goal/hash, strategy, and agent returns the pending job or completed result.
Reusing it with different inputs is rejected. Jobs live in memory and are lost
on restart; completed attempt records persist.

Attempts are not automatically promoted into the snapshot's full verification
report. Run full verification separately. Only one full-verification/attempt
job runs at a time.

## Proposals and review

Drafts must contain nonempty title, rationale, content, and captured evidence:

```json
{
  "kind": "repair",
  "title": "Reject overdrafts",
  "rationale": "The checked witness produces a negative source balance.",
  "content": "Add an insufficient-funds guard and a regression test, then re-verify the unchanged contract.",
  "agent": "external reasoning agent",
  "evidence": [
    { "path": "transfer.py", "line_start": 4, "line_end": 8 }
  ]
}
```

Optional `obligation_id` links a fixed goal. Optional `parent_id` links an
earlier proposal when revising a draft. Proposals are immutable and always
recorded as draft, unchecked, and unapplied. Requirement/contract drafts do not
change the actual contract or create new checker semantics.

Review is a separate append-only record:

```json
{
  "decision": "accepted",
  "note": "Accepted as intent; regression and verification are still required.",
  "reviewer": "local reviewer"
}
```

Decisions are `accepted`, `rejected`, or `needs_changes`. The UI shows the latest
review but preserves all earlier review records on disk. Accepting a proposal
does not apply a patch, prove the proposal, or authorize source execution.

## Records and limits

Agent records are stored under:

```text
<data-dir>/agents/<snapshot_id>/attempts/attempt_<id>.json
<data-dir>/agents/<snapshot_id>/proposals/proposal_<id>.json
<data-dir>/agents/<snapshot_id>/reviews/review_<id>.json
```

Records are immutable, snapshot-bound, and written atomically. Full data
directory backups preserve them; portable bundle exports omit them.
Generated attempt inputs are under `agent-proof-runs`.

Proposal text fields are limited to 12,000 characters; evidence uses 1–30
validated captured-source ranges. Proof execution retains the pinned toolchain,
30-second timeout, heartbeat limit, and fixed-source restriction documented in
[proof-checking.md](proof-checking.md). There is no OS sandbox for arbitrary
Lean execution, which is why the API does not accept arbitrary Lean.

The shared local token does not enforce an agent/reviewer separation. A
multi-user or remotely deployed service would require separate authentication,
authorization, storage concurrency, and runner isolation.

## External agent workflow

An external Codex session or another agent can use these tools:

1. Read capabilities and analyze a repository.
2. Read the versioned context, source evidence, and unsupported boundaries.
3. Select a fixed obligation and checker strategy.
4. Read diagnostics and retry the same goal without weakening it.
5. Save a proposal with evidence and uncertainty.
6. Let a reviewer inspect the proposal in the UI.
7. After an independently authorized source edit, re-analyze and compare.

The service does not launch Codex automatically or consume a model API key.
A future Codex CLI/SDK or MCP adapter can orchestrate these same operations
without duplicating analysis or checker semantics.

The [DAG workflow API](workflow-dag.md) pins these tasks to a dependency graph
with role prompts, immutable outputs, actual checker references, and exact
human review gates. It supports read-only parallel built-ins and external
agent submissions; it does not itself launch a model.

## Validation

Run the standard-library suite with the local environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check codeform/web/app.js
```

With pinned Lean available, API tests execute real failed/successful attempts
and checked counterexamples. They also verify immutable goal binding,
request idempotency, captured evidence, draft/review persistence, and the
OpenAPI paths. Without Lean, checker integration tests are explicitly skipped.

After running `examples/agent_client_demo.py`, the optional Playwright test
`node tests/agents-browser.cjs` verifies Agent workspace, proposal review,
diagnostics, reload persistence, and mobile layout. Use the browser-tool setup
in [testing.md](testing.md).
