"""Read-only structural inventory. Project code is parsed, never imported or executed."""
from __future__ import annotations
import ast
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any
from . import __version__

SCHEMA_VERSION = "0.1.0"
IGNORED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "node_modules", "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "site-packages"}
LANGUAGES = {".py":"Python", ".pyi":"Python", ".js":"JavaScript", ".jsx":"JavaScript", ".mjs":"JavaScript", ".ts":"TypeScript", ".tsx":"TypeScript", ".go":"Go", ".rs":"Rust", ".java":"Java", ".kt":"Kotlin", ".swift":"Swift", ".c":"C", ".h":"C/C++", ".cc":"C++", ".cpp":"C++", ".hpp":"C++", ".cs":"C#", ".rb":"Ruby", ".php":"PHP", ".sh":"Shell", ".md":"Markdown", ".toml":"TOML", ".yaml":"YAML", ".yml":"YAML", ".json":"JSON", ".sql":"SQL", ".html":"HTML", ".css":"CSS"}

def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, timeout=3)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None

def _git_metadata(root: Path) -> dict[str, Any]:
    commit, branch, status = _git(root, "rev-parse", "HEAD"), _git(root, "branch", "--show-current"), _git(root, "status", "--porcelain")
    return {"commit_sha": commit, "branch": branch or None, "working_tree_dirty": bool(status) if status is not None else None}

def _iter_files(root: Path):
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not d.startswith("."))
        for name in sorted(names):
            path = Path(current, name)
            if path.is_symlink() or path.name == ".DS_Store":
                continue
            yield path, path.relative_to(root).as_posix()

def _read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
        return None if b"\0" in raw else raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None

def _python_facts(relative: str, source: str, commit: str | None) -> dict[str, Any]:
    base = {"kind": "source", "reference": relative}
    if commit:
        base["commit_sha"] = commit
    facts: dict[str, Any] = {"imports": [], "symbols": [], "entrypoint": False, "parse_error": None}
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        facts["parse_error"] = {"message": exc.msg, "line": exc.lineno, "evidence": {**base, "line_start": exc.lineno, "line_end": exc.lineno}}
        return facts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = ["." * node.level + (node.module or "")]
        else:
            modules = []
        for module in modules:
            facts["imports"].append({"module": module, "line": node.lineno, "evidence": {**base, "line_start": node.lineno, "line_end": node.lineno}})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            facts["symbols"].append({"name": node.name, "kind": "class" if isinstance(node, ast.ClassDef) else "function", "line_start": node.lineno, "line_end": getattr(node, "end_lineno", node.lineno), "evidence": {**base, "line_start": node.lineno, "line_end": getattr(node, "end_lineno", node.lineno)}})
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            test = node.test
            if isinstance(test.left, ast.Name) and test.left.id == "__name__" and any(isinstance(op, ast.Eq) for op in test.ops) and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators):
                facts["entrypoint"] = True
    facts["imports"].sort(key=lambda x: (x["line"], x["module"]))
    facts["symbols"].sort(key=lambda x: (x["line_start"], x["name"]))
    return facts

def analyze_repository(target: str | Path) -> dict[str, Any]:
    """Analyze a directory without importing or executing project code."""
    root = Path(target).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Target must be an existing directory: {root}")
    git = _git_metadata(root)
    records, module_paths = [], {}
    for path, relative in _iter_files(root):
        suffix = path.suffix.lower()
        if suffix == ".py":
            module = relative[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[:-9]
            module_paths[module] = relative
        source = _read_text(path)
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        record = {"path": relative, "language": LANGUAGES.get(suffix, "Other"), "size_bytes": size,
                  "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest() if source is not None else None}
        if source is not None:
            record["line_count"] = len(source.splitlines())
        if suffix == ".py" and source is not None:
            record["python"] = _python_facts(relative, source, git["commit_sha"])
        records.append(record)

    relationships, claims = [], []
    for record in records:
        facts = record.get("python")
        if not facts:
            continue
        for item in facts["imports"]:
            module = item["module"].lstrip(".")
            target_path = module_paths.get(module)
            if target_path is None and module:
                parts = module.split(".")
                for end in range(len(parts) - 1, 0, -1):
                    if ".".join(parts[:end]) in module_paths:
                        target_path = module_paths[".".join(parts[:end])]
                        break
            if target_path:
                relationships.append({"type": "imports", "source": record["path"], "target": target_path, "evidence": item["evidence"]})
        if facts["entrypoint"]:
            claims.append({"id": "entrypoint:" + record["path"], "statement": record["path"] + " contains a __main__ guard.", "status": "observed",
                           "evidence": [{"kind":"source", "reference":record["path"], **({"commit_sha":git["commit_sha"]} if git["commit_sha"] else {})}]})
        if facts["parse_error"]:
            error = facts["parse_error"]
            claims.append({"id":"parse-error:" + record["path"], "statement":f"Python AST parsing failed for {record['path']}: {error['message']}.", "status":"observed", "evidence":[error["evidence"]]})

    counts = Counter(r["language"] for r in records)
    python_files = [r for r in records if "python" in r]
    tests = sorted(r["path"] for r in records if Path(r["path"]).name.startswith("test_") or "/tests/" in "/" + r["path"] + "/")
    components = [{"id":"file:" + r["path"], "name":r["path"], "kind":"source_file" if r["language"] != "Other" else "file", "path":r["path"], "language":r["language"],
                   "evidence":[{"kind":"source", "reference":r["path"], **({"commit_sha":git["commit_sha"]} if git["commit_sha"] else {})}]} for r in records]
    def node_id(path: str) -> str:
        return "f_" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
    diagram = ["flowchart LR"] + [f'  {node_id(p)}["{p.replace(chr(34), chr(39))}"]' for p in sorted(r["path"] for r in records)]
    for edge in sorted(relationships, key=lambda e:(e["source"],e["target"])):
        diagram.append(f"  {node_id(edge['source'])} -->|imports| {node_id(edge['target'])}")
    return {
        "schema_version":SCHEMA_VERSION, "repository":{"name":root.name,"root":str(root),**git},
        "analyzer":{"name":"code-form","version":__version__},
        "scope":{"read_only":True,"executed_project_code":False,"languages_with_structural_parsing":["Python"]},
        "summary":{"file_count":len(records),"language_counts":dict(sorted(counts.items())),"python_file_count":len(python_files),
                   "python_parse_error_count":sum(bool(r["python"]["parse_error"]) for r in python_files),"test_path_count":len(tests),
                   "component_count":len(components),"internal_import_edge_count":len(relationships),"claim_count":len(claims)},
        "components":components,"relationships":sorted(relationships,key=lambda e:(e["source"],e["target"],e["type"])),
        "claims":sorted(claims,key=lambda c:c["id"]),"files":records,"test_paths":tests,
        "diagrams":{"dependency_graph_mermaid":"\n".join(diagram)+"\n"},
        "limitations":["Only Python source is structurally parsed; other languages are inventoried by file.",
                       "Import resolution is best-effort and does not model dynamic imports or runtime behavior.",
                       "No AI-generated intent, defect, security, or correctness claims are produced.",
                       "Observed source structure is not proof that runtime behavior matches a design."]
    }

def write_bundle(bundle: dict[str, Any], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
