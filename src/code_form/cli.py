"""Command-line interface."""
import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .analyzer import analyze_repository, write_bundle

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-form", description="Read-only structural repository analysis.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="inventory a repository without executing its code")
    analyze.add_argument("path", nargs="?", default=".", help="repository directory (default: current directory)")
    analyze.add_argument("--output", "-o", default="-", help="JSON output path; '-' means stdout")
    args = parser.parse_args(argv)
    try:
        bundle = analyze_repository(args.path)
        if args.output == "-":
            json.dump(bundle, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            output = Path(args.output).expanduser()
            write_bundle(bundle, output)
            print(f"Wrote {bundle['summary']['file_count']} file records to {output}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"code-form: error: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
