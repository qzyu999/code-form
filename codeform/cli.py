"""CLI shares the same analyzer and persistence as the local web app."""

import argparse
import json
from pathlib import Path

from .analyzer import analyze_repository
from .model import compare_bundles, report_markdown, validate_bundle
from .server import Application, make_server
from .store import Store
from .proofs import find_lean, verify_bundle
from .client import CodeFormClient, ApiError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-form", description="Evidence-linked Python repository analysis.")
    parser.add_argument("--version", action="version", version="code-form 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Read and parse a Python repository without executing it.")
    analyze.add_argument("repository", nargs="?", default=".")
    analyze.add_argument("--output", "-o", type=Path, help="Export directory for JSON, Markdown, Mermaid, and Lean candidates.")
    analyze.add_argument("--store", type=Path, default=Path(".codeform"))
    serve = commands.add_parser("serve", help="Start the local interactive application.")
    serve.add_argument("--workspace", type=Path, default=Path.cwd(), help="Allowed root for repositories selected through the UI.")
    serve.add_argument("--data-dir", type=Path, help="Snapshot/review storage; defaults to <workspace>/.codeform.")
    serve.add_argument("--port", type=int, default=7331, help="Loopback HTTP port; 0 chooses an available port (default: 7331).")
    serve.add_argument("--demo", action="store_true", help="Analyze all bundled example repositories on startup.")
    serve.add_argument("--lean", type=Path, help="Pinned Lean 4.19.0 executable for the proof checker.")
    verify = commands.add_parser("verify", help="Check generated transfer/workflow proofs with pinned Lean.")
    verify.add_argument("repository", nargs="?", default=".")
    verify.add_argument("--store", type=Path, default=Path(".codeform"))
    verify.add_argument("--output", "-o", type=Path, default=Path(".codeform/verification.json"))
    verify.add_argument("--lean", type=Path)
    compare = commands.add_parser("compare", help="Compare two exported bundle JSON files.")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    validate = commands.add_parser("validate", help="Validate a bundle's schema, references, hashes, and evidence ranges.")
    validate.add_argument("bundle", type=Path)
    api = commands.add_parser("api", help="Call the running v1 agent API; no model credentials required.")
    api.add_argument("--url", default="http://127.0.0.1:7332")
    actions = api.add_subparsers(dest="api_action", required=True)
    actions.add_parser("capabilities", help="Show available tools and limits.")
    actions.add_parser("snapshots", help="List saved snapshots.")
    api_analyze = actions.add_parser("analyze", help="Queue analysis through the service.")
    api_analyze.add_argument("path")
    api_analyze.add_argument("--wait", action="store_true")
    for action in ("snapshot", "context", "walkthrough", "obligations", "attempts", "proposals", "workflows"):
        command = actions.add_parser(action)
        command.add_argument("snapshot_id")
    source = actions.add_parser("source", help="Read captured evidence.")
    source.add_argument("snapshot_id")
    source.add_argument("path")
    source.add_argument("--start", type=int)
    source.add_argument("--end", type=int)
    attempt = actions.add_parser("attempt", help="Try a controlled strategy against the exact goal.")
    attempt.add_argument("snapshot_id")
    attempt.add_argument("obligation_id")
    attempt.add_argument("--strategy", choices=("generated", "simplify", "decide"), default="generated")
    attempt.add_argument("--agent", default="CLI agent")
    attempt.add_argument("--request-id")
    attempt.add_argument("--wait", action="store_true")
    proposal = actions.add_parser("propose", help="Save an evidence-linked draft from a JSON file.")
    proposal.add_argument("snapshot_id")
    proposal.add_argument("--file", type=Path, required=True)
    review = actions.add_parser("review", help="Record a separate proposal review.")
    review.add_argument("snapshot_id")
    review.add_argument("proposal_id")
    review.add_argument("--decision", choices=("accepted", "rejected", "needs_changes"), required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--reviewer", required=True)
    workflow = actions.add_parser("workflow", help="Read a dependency-controlled workflow run.")
    workflow.add_argument("snapshot_id")
    workflow.add_argument("workflow_id")
    wf_context = actions.add_parser("workflow-context", help="Read a node's pinned role prompt and input artifacts.")
    wf_context.add_argument("snapshot_id")
    wf_context.add_argument("workflow_id")
    wf_context.add_argument("node_id")
    wf_create = actions.add_parser("workflow-create", help="Create an immutable analysis DAG.")
    wf_create.add_argument("snapshot_id")
    wf_create.add_argument("--objective", required=True)
    wf_advance = actions.add_parser("workflow-advance", help="Run ready read-only built-ins.")
    wf_advance.add_argument("snapshot_id")
    wf_advance.add_argument("workflow_id")
    wf_advance.add_argument("--wait", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "api":
            client = CodeFormClient(args.url)
            action = args.api_action
            if action in {"capabilities", "snapshots"}:
                result = getattr(client, action)()
            elif action == "analyze":
                result = client.analyze(args.path)
                if args.wait:
                    result = client.wait(result)
            elif action in {"snapshot", "context", "walkthrough", "obligations", "attempts", "proposals", "workflows"}:
                result = getattr(client, action)(args.snapshot_id)
            elif action == "source":
                result = client.source(args.snapshot_id, args.path, args.start, args.end)
            elif action == "attempt":
                obligation = next((o for o in client.obligations(args.snapshot_id)["obligations"]
                                   if o["id"] == args.obligation_id), None)
                if obligation is None:
                    raise ValueError("Obligation not found in this snapshot.")
                result = client.submit_attempt(args.snapshot_id, obligation, args.strategy, args.agent, args.request_id)
                if args.wait:
                    job = client.wait(result)
                    result = client.attempt(args.snapshot_id, job["attempt_id"])
            elif action == "propose":
                payload = json.loads(args.file.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Proposal file must contain a JSON object.")
                result = client.propose(args.snapshot_id, payload)
            elif action == "review":
                result = client.review(args.snapshot_id, args.proposal_id, args.decision, args.note, args.reviewer)
            elif action == "workflow":
                result = client.workflow(args.snapshot_id, args.workflow_id)
            elif action == "workflow-context":
                result = client.workflow_context(args.snapshot_id, args.workflow_id, args.node_id)
            elif action == "workflow-create":
                result = client.create_workflow(args.snapshot_id, args.objective)
            elif action == "workflow-advance":
                result = client.advance_workflow(args.snapshot_id, args.workflow_id)
                if args.wait:
                    result = client.wait(result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "analyze":
            bundle = analyze_repository(args.repository)
            Store(args.store).save(bundle)
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                (args.output / "bundle.json").write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                (args.output / "report.md").write_text(report_markdown(bundle), encoding="utf-8")
                for name, diagram in bundle["diagrams"].items():
                    (args.output / f"{name}.mmd").write_text(diagram + "\n", encoding="utf-8")
                for candidate in bundle["formal_candidates"]:
                    (args.output / f"{candidate['id']}.lean").write_text(candidate["source"], encoding="utf-8")
            print(f"Analyzed {bundle['repository']['name']}: {bundle['summary']['modules']} modules, "
                  f"{bundle['summary']['claims']} evidence-linked claims, {bundle['summary']['findings']} findings.")
            print(f"Snapshot: {bundle['id']}")
            if args.output:
                print(f"Export: {args.output.resolve()}")
        elif args.command == "serve":
            if not 0 <= args.port <= 65535:
                raise ValueError("Port must be between 0 and 65535.")
            app = Application(args.workspace, args.data_dir, args.lean)
            try:
                if args.demo:
                    app.seed_examples()
                server = make_server(app, args.port)
                print(f"code-form is running at http://127.0.0.1:{server.server_port}", flush=True)
                print(f"Workspace: {app.workspace}\nPress Ctrl+C to stop.", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
            finally:
                app.close()
        elif args.command == "validate":
            bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
            validate_bundle(bundle)
            print(f"Valid bundle: {bundle['id']}")
        elif args.command == "compare":
            bundles = [json.loads(path.read_text(encoding="utf-8")) for path in (args.before, args.after)]
            for bundle in bundles:
                validate_bundle(bundle)
            print(json.dumps(compare_bundles(*bundles), indent=2, ensure_ascii=False))
        elif args.command == "verify":
            bundle = analyze_repository(args.repository)
            store = Store(args.store)
            store.save(bundle)
            report = verify_bundle(bundle, find_lean(args.lean), store.path / "proof-runs")
            store.save_verification(bundle["id"], report)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Verification: {report['summary']}")
            print(f"Snapshot: {bundle['id']}\nReport: {args.output.resolve()}")
            if not report["artifacts"] or any(report["summary"][key] for key in ("unsupported", "not_run", "error", "timeout")):
                return 1
            if report["summary"]["disproved"]:
                return 2
        return 0
    except (ValueError, OSError, KeyError, ApiError, RuntimeError) as error:
        parser.exit(1, f"code-form: {error}\n")
