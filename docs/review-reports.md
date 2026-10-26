# Reviewing the system as a report

Open **Review report** in the local app, then **Open readable report**. It
joins the documented purpose, requirements, submitted system model,
architecture review, proposed LaTeX specifications, counterexample candidates,
test plans, captured source excerpts, and actual supported Lean results.
The page explains the other tabs so reviewers can move from the whole system
to individual evidence.

The report is assembled deterministically from saved records. It does not
call a language model, analyze new source, run target tests, advance a DAG,
approve a gate, or modify a repository. External roles supply their analysis
through the workflow API. Empty stages stay absent; report generation does
not invent their results.

## Human and AI formats

- **Readable HTML** renders LaTeX locally and shows proposed system diagrams,
  Mermaid source, collapsible captured evidence, and Lean inputs when a
  supported model exists.
- **Save standalone HTML** embeds the math renderer, fonts, and complete JSON
  companion. Open the saved file offline. **Download JSON companion** extracts
  that exact report for an AI reviewer.
- **Markdown** contains the same narrative with LaTeX, Mermaid, and Lean fences.
- **JSON for AI review** includes the complete captured source and structural
  ledger, selected workflow artifacts/prompts/input hashes, owner review
  status, annotations, standalone agent history, and checker records.
- **Print / save PDF** opens evidence sections before printing.

Human reports aggregate direct test-reference gaps instead of presenting
hundreds of them as confirmed defects. Source excerpts longer than 48 lines
are explicitly truncated. Complete source and all findings remain in JSON.
All source excerpts come from the captured snapshot, not current disk files.
The saved report can therefore differ from source edited after capture.

## Select and pin a workflow

The default report chooses the latest complete preview, otherwise the latest
active workflow, otherwise the latest historical run. The selected ID, mode,
state, and specification hash are displayed. Active owner review runs are
listed separately. Each DAG run has **Read this run as a report** to pin that
specific run, including partial or superseded history.

Preview completion means its stages produced artifacts. It does not mean the
model was owner-approved or the implementation was formally verified.

```text
GET /reports/{snapshot_id}?workflow_id={workflow_id}
GET /api/v1/snapshots/{snapshot_id}/report?format=json&workflow_id={workflow_id}
GET /api/v1/snapshots/{snapshot_id}/report?format=markdown&workflow_id={workflow_id}
GET /api/v1/snapshots/{snapshot_id}/report?format=html&download=1&workflow_id={workflow_id}
```

All routes are read-only and retain the server's loopback Host/Origin checks.
An unknown workflow or one belonging to another snapshot is rejected.

Use the project virtual environment to export all three formats:

```powershell
.\.venv\Scripts\python.exe -m codeform api --url http://127.0.0.1:7334 report snapshot_8e536d260e2a4645 --workflow-id workflow_607611575da431a6 --output .codeform/exports/inference-exchange
```

This produces `review-report.html`, `review-report.md`, and
`review-report.json`. Replace the URL and identifiers with your running
server and captured analysis. The Python client provides
`CodeFormClient(url).report(snapshot_id, workflow_id=None)`.

## Why the proof view may be empty

There are distinct states:

| State | Meaning |
| --- | --- |
| Unsupported | No supported source-to-model obligation exists. Running Lean cannot create one. |
| Not run | Supported obligations exist but have not been checked. |
| Checker unavailable | Supported obligations exist; install/configure pinned Lean 4.19.0. |
| No accepted results | A run produced no accepted certificates; inspect diagnostics. |
| Stale | The saved verification belongs to different captured source and is excluded. |
| Results available | Exact checker certificates match supported emitted obligations. |

Inference-exchange currently has proposed billing, lifecycle, and routing
specifications in its preview, but **zero supported Lean obligations** for its
actual SQLite/async/routing functions. Integer-transfer and literal finite
transition-table examples demonstrate the supported checker path. A general
repository needs reviewed operational semantics, explicit mathematical
requirements, and source-to-model adapters.

Observed source, documented intent, inferred candidates, proposed
specifications, test plans, and checked theorems have different meanings.
Numerical reproduction of a copied expression is not a Lean proof or a
runtime reproduction of the target application.

## Provenance and review

Every export includes its snapshot/content hash, generation time, selected
workflow/specification hashes, and a report hash. The SHA-256 covers UTF-8
`canonical_json(report_without_sha256)`, using `codeform.model.canonical_json`.
Each request captures current saved review state; freeze one export for a
reproducible review rather than comparing hashes from different requests.

Complete-snapshot certificates count only when snapshot, content, emitted
Lean input, obligation ID/hash, and declaration verification match.
Standalone attempts stay separate. Unaccepted raw checker records remain in
JSON for diagnostics. No proposed formula becomes a proved theorem merely
because an agent supplied it or all DAG stages completed.

For an AI reviewer, give it the JSON or Markdown and ask it to trace each
conclusion through its assumptions and captured source, identify missing
implementation bridges, and separate policy choices from proof obligations.
The JSON contains review instructions that make these distinctions explicit.
