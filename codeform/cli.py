"""CLI shares the same analyzer and persistence as the local web app."""

import argparse
import json
from pathlib import Path

from .analyzer import analyze_repository
from .model import compare_bundles, report_markdown, validate_bundle
from .server import Application, make_server
from .store import Store


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
    compare = commands.add_parser("compare", help="Compare two exported bundle JSON files.")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    validate = commands.add_parser("validate", help="Validate a bundle's schema, references, hashes, and evidence ranges.")
    validate.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
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
            app = Application(args.workspace, args.data_dir)
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
        return 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"code-form: {error}\n")
