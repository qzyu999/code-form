"""Static Python adapter. Target code is read and parsed, never imported."""

import ast
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from . import __version__
from .model import SCHEMA_VERSION, canonical_json, stable_id, validate_bundle

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".codeform", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build",
    ".agents", ".codex", ".aws", ".ssh", ".idea",
}
MAX_FILES = 2000
MAX_FILE_BYTES = 256_000
MAX_TOTAL_BYTES = 16_000_000


def _junction(path: Path) -> bool:
    return getattr(path, "is_junction", lambda: False)()


def _git(root: Path, *args: str) -> str | None:
    try:
        # No repository scripts, hooks, credential helpers, or target commands.
        proc = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or "__root__"


def _expr(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_expr(node.value)}.{node.attr}"
    return ""


def _declarations(tree: ast.AST, prefix: str = ""):
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = f"{prefix}.{node.name}" if prefix else node.name
            yield name, node
            if isinstance(node, ast.ClassDef):
                yield from _declarations(node, name)


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's algorithm: report strongly connected module groups once."""
    index, indices, low, stack, on_stack, result = 0, {}, {}, [], set(), []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph.get(node, set())):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            group = []
            while True:
                target = stack.pop()
                on_stack.remove(target)
                group.append(target)
                if target == node:
                    break
            if len(group) > 1 or node in graph.get(node, set()):
                result.append(sorted(group))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(result)


def analyze_repository(repository: str | Path) -> dict:
    root = Path(repository).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Repository path must be an existing directory.")
    sources, skipped, total, examined = [], [], 0, 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not d.endswith(".egg-info")
                         and not (Path(directory) / d).is_symlink()
                         and not _junction(Path(directory) / d))
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.suffix not in {".py", ".md", ".toml", ".txt", ".cfg", ".ini"}:
                continue
            if name.startswith(".env") or any(word in name.lower() for word in ("secret", "credential")):
                skipped.append({"path": relative, "reason": "sensitive filename"})
                continue
            examined += 1
            if examined > MAX_FILES:
                raise ValueError(f"Repository exceeds {MAX_FILES} eligible files; analyze a smaller directory.")
            try:
                if path.is_symlink() or _junction(path) or not path.resolve().is_relative_to(root):
                    skipped.append({"path": relative, "reason": "link outside snapshot"})
                    continue
                if path.stat().st_size > MAX_FILE_BYTES:
                    skipped.append({"path": relative, "reason": "file exceeds 256 KB"})
                    continue
                raw = path.read_bytes()
                total += len(raw)
                if total > MAX_TOTAL_BYTES:
                    raise ValueError("Repository exceeds the 16 MB analysis limit.")
                content = raw.decode("utf-8-sig")
            except (OSError, UnicodeError) as error:
                skipped.append({"path": relative, "reason": type(error).__name__})
                continue
            sources.append({"path": relative, "content": content,
                            "sha256": hashlib.sha256(content.encode()).hexdigest(),
                            "language": "python" if path.suffix == ".py" else "documentation" if path.suffix == ".md" else "configuration"})
    sources.sort(key=lambda s: s["path"])
    if not any(s["language"] == "python" for s in sources):
        raise ValueError("No Python source files found. This release analyzes Python repositories.")
    content_hash = hashlib.sha256(canonical_json([(s["path"], s["sha256"]) for s in sources]).encode()).hexdigest()
    implementation_hash = hashlib.sha256(
        Path(__file__).read_bytes() + Path(__file__).with_name("model.py").read_bytes()
    ).hexdigest()
    commit = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain", "--untracked-files=normal", "--", ".")
    dirty = bool(status) if status is not None else None
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "id": stable_id("snapshot", str(root), content_hash, commit or "", __version__, sys.version, implementation_hash, str(dirty)),
        "analyzer": {"name": "code-form", "version": __version__, "adapter": "python-ast",
                     "implementation_sha256": implementation_hash,
                     "python_version": ".".join(map(str, sys.version_info[:3])),
                     "configuration": {"max_files": MAX_FILES, "max_file_bytes": MAX_FILE_BYTES,
                                       "max_total_bytes": MAX_TOTAL_BYTES}},
        "repository": {"name": root.name, "path": str(root), "commit_sha": commit,
                       "dirty": dirty,
                       "content_sha256": content_hash, "languages": ["Python"],
                       "dependencies": [], "suggested_test_commands": []},
        "sources": sources, "skipped_files": skipped, "components": [], "relationships": [],
        "claims": [], "evidence": [], "findings": [], "assumptions": [], "invariants": [],
        "formal_candidates": [], "flows": [], "state_machines": [], "open_questions": [],
        "limitations": [
            "Target code and tests are never executed. Test references are static links, not coverage or passing results.",
            "Calls resolve only explicit local/imported names; dynamic dispatch, reflection, and runtime wiring remain unknown.",
            "Route extraction recognizes literal HTTP method decorators; decorators may be user-defined.",
            "Findings describe candidates for investigation, not confirmed defects.",
            "Bounded transition checks apply to extracted literal models, not the running implementation.",
            "Lean artifacts are proposed statements; no proof checker is invoked.",
            "Snapshots include eligible source text. Hidden environments, credential files, links, and oversized files are excluded.",
        ],
    }
    trees, modules, symbols, bindings, test_refs, test_evidence, routes = {}, {}, {}, {}, set(), {}, []
    evidence_map, relationships_by_id, claims_by_id, findings_by_id = {}, {}, {}, {}

    def evidence(path: str, start: int, end: int | None = None, note: str = "") -> dict:
        key = (path, start, end or start, note)
        if key not in evidence_map:
            item = {"id": stable_id("evidence", *map(str, key)), "kind": "source", "reference": path,
                    "commit_sha": commit or "", "line_start": start, "line_end": end or start, "note": note}
            evidence_map[key] = item
            bundle["evidence"].append(item)
        return evidence_map[key]

    def claim(kind: str, scope: str, statement: str, refs: list[dict], status: str = "observed", confidence: float = 1.0) -> None:
        identifier = stable_id("claim", kind, scope, statement)
        normalized = [{k: v for k, v in ref.items() if k != "id"} for ref in refs]
        if identifier in claims_by_id:
            existing = claims_by_id[identifier]["evidence"]
            existing.extend(ref for ref in normalized if ref not in existing)
            return
        item = {
            "id": identifier, "statement": statement, "status": status,
            "scope": scope, "confidence": confidence, "assumptions": [],
            "evidence": normalized,
            "contradictions": [], "created_by": f"python-ast/{__version__}",
        }
        claims_by_id[identifier] = item
        bundle["claims"].append(item)

    def finding(rule: str, scope: str, title: str, refs: list[dict], rationale: str,
                validation: str, severity: str = "medium", uncertainty: str = "Static evidence needs human validation.") -> None:
        identifier = stable_id("finding", rule, scope)
        evidence_ids = [ref["id"] for ref in refs]
        if identifier in findings_by_id:
            existing = findings_by_id[identifier]["evidence_ids"]
            existing.extend(ref for ref in evidence_ids if ref not in existing)
            return
        item = {
            "id": identifier, "rule": rule, "component_id": scope,
            "title": title, "severity": severity, "status": "inferred", "confidence": 0.8,
            "evidence_ids": evidence_ids, "rationale": rationale,
            "impact": "Reduced confidence in behavior or change safety.", "uncertainty": uncertainty,
            "suggested_validation": validation,
            "suggested_test": validation,
        }
        findings_by_id[identifier] = item
        bundle["findings"].append(item)

    def relationship(source: str, target: str, kind: str, ref: dict) -> None:
        identifier = stable_id("relation", kind, source, target)
        if identifier in relationships_by_id:
            refs = relationships_by_id[identifier]["evidence_ids"]
            if ref["id"] not in refs:
                refs.append(ref["id"])
        else:
            item = {"id": identifier, "source": source, "target": target,
                    "kind": kind, "evidence_ids": [ref["id"]]}
            relationships_by_id[identifier] = item
            bundle["relationships"].append(item)

    for source in sources:
        path, content = source["path"], source["content"]
        if source["language"] != "python":
            continue
        module = _module_name(path)
        module_id = stable_id("component", path)
        modules[module] = module_id
        is_test = any(part in {"tests", "test"} for part in Path(path).parts) or Path(path).name.startswith("test_") or Path(path).stem.endswith("_test")
        component = {"id": module_id, "name": module, "kind": "test_module" if is_test else "module",
                     "path": path, "line_start": 1, "line_end": max(1, len(content.splitlines())),
                     "public": not Path(path).stem.startswith("_"), "docstring": "", "signature": ""}
        bundle["components"].append(component)
        ref = evidence(path, 1, component["line_end"], "Module source")
        claim("module", module_id, f"{module} is a {'test ' if is_test else ''}Python module.", [ref])
        try:
            tree = ast.parse(content, filename=path)
        except (SyntaxError, ValueError, RecursionError) as error:
            line = max(1, min(getattr(error, "lineno", 1) or 1, component["line_end"]))
            finding("parse-error", module_id, f"Cannot parse {path}", [evidence(path, line)],
                    f"Python's parser rejected this module: {getattr(error, 'msg', str(error))}.",
                    "Check the required Python version and fix or isolate the syntax before relying on this model.", "high")
            continue
        trees[module] = (tree, component)
        component["docstring"] = ast.get_docstring(tree) or ""
        bindings[module] = {}
        for qualified, node in _declarations(tree):
            symbol_id = stable_id("component", path, qualified)
            kind = "class" if isinstance(node, ast.ClassDef) else "method" if "." in qualified else "function"
            symbol = {"id": symbol_id, "name": f"{module}.{qualified}", "kind": kind, "path": path,
                      "module_id": module_id, "line_start": node.lineno, "line_end": node.end_lineno,
                      "public": not node.name.startswith("_") and not is_test,
                      "docstring": ast.get_docstring(node) or "",
                      "signature": f"{node.name}({ast.unparse(node.args)})" if hasattr(node, "args") else node.name,
                      "async": isinstance(node, ast.AsyncFunctionDef)}
            symbols[f"{module}.{qualified}"] = (symbol, node)
            bundle["components"].append(symbol)
            ref = evidence(path, node.lineno, node.end_lineno, "Declaration")
            relationship(module_id, symbol_id, "contains", ref)
            claim("declaration", symbol_id, f"{symbol['name']} declares a {kind}: {symbol['signature']}.", [ref])
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        method = decorator.func.attr.upper()
                        if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"} and decorator.args:
                            route = decorator.args[0]
                            if isinstance(route, ast.Constant) and isinstance(route.value, str):
                                route_ref = evidence(path, decorator.lineno, decorator.end_lineno, "Route decorator")
                                routes.append({"method": method, "path": route.value, "component_id": symbol_id,
                                               "evidence_ids": [route_ref["id"]]})
                                claim("route", symbol_id, f"{symbol['name']} has a {method} {route.value} route decorator.", [route_ref])

    graph = {module_id: set() for module_id in modules.values()}
    for module, (tree, component) in trees.items():
        package = module.split(".") if Path(component["path"]).name == "__init__.py" else module.split(".")[:-1]
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            ref = evidence(component["path"], node.lineno, node.end_lineno, "Import")
            if isinstance(node, ast.Import):
                entries = [(alias.name, alias.asname or alias.name.split(".")[0],
                            alias.name if alias.asname else alias.name.split(".")[0]) for alias in node.names]
            else:
                base = ".".join(package[:len(package) - node.level + 1] + ([node.module] if node.module else [])) if node.level else node.module or ""
                entries = [(f"{base}.{alias.name}".strip("."), alias.asname or alias.name,
                            f"{base}.{alias.name}".strip(".")) for alias in node.names]
            for imported, bound, qualified in entries:
                bindings[module][bound] = qualified
                target_name = imported if imported in modules else imported.rsplit(".", 1)[0] if "." in imported else imported
                if target_name in modules and modules[target_name] != component["id"]:
                    target = modules[target_name]
                    graph[component["id"]].add(target)
                    relationship(component["id"], target, "imports", ref)
                    claim("import", component["id"], f"{module} imports {imported}.", [ref])

    for name, (symbol, node) in symbols.items():
        module = next(module for module, (_, comp) in trees.items() if comp["id"] == symbol["module_id"])
        is_test = next(comp["kind"] == "test_module" for _, comp in trees.values() if comp["id"] == symbol["module_id"])
        calls = []

        class Calls(ast.NodeVisitor):
            def visit_Call(self, call):
                raw = _expr(call.func)
                head, _, tail = raw.partition(".")
                bound = bindings[module].get(head)
                target_name = f"{bound}.{tail}" if bound and tail else bound if bound else f"{module}.{raw}"
                # Resolve self.method only within an explicitly declared class.
                if raw.startswith("self.") and symbol["kind"] == "method":
                    target_name = f"{name.rsplit('.', 1)[0]}.{raw[5:]}"
                if target_name in symbols:
                    target = symbols[target_name][0]
                    ref = evidence(symbol["path"], call.lineno, call.end_lineno, "Call expression")
                    relationship(symbol["id"], target["id"], "tests" if is_test else "calls", ref)
                    calls.append({"target": target["id"], "name": target["name"], "line": call.lineno})
                    if is_test:
                        test_refs.add(target["id"])
                        test_evidence.setdefault(target["id"], []).append(ref)
                self.generic_visit(call)

            def visit_FunctionDef(self, child):
                if child is node:
                    self.generic_visit(child)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, child):
                return

        if symbol["kind"] != "class":
            Calls().visit(node)
        if calls and not is_test:
            ref = evidence(symbol["path"], node.lineno, node.end_lineno, "Static call sequence")
            bundle["flows"].append({
                "id": stable_id("flow", symbol["id"]), "name": symbol["name"],
                "entry_component_id": symbol["id"], "steps": sorted(calls, key=lambda c: c["line"]),
                "status": "observed", "evidence_ids": [ref["id"]],
                "note": "Lexical call order; branches and runtime scheduling are not represented.",
            })
        if symbol["kind"] != "class" and not is_test:
            for child in ast.walk(node):
                if isinstance(child, ast.ExceptHandler) and (child.type is None or _expr(child.type) in {"Exception", "BaseException"}):
                    swallowed = all(isinstance(stmt, (ast.Pass, ast.Return)) for stmt in child.body)
                    if swallowed:
                        finding("swallowed-exception", symbol["id"], f"Broad exception handler in {symbol['name']}",
                                [evidence(symbol["path"], child.lineno, child.end_lineno, "Exception handler")],
                                "A broad handler returns or passes without recording or re-raising the failure.",
                                f"Test failure paths in {symbol['name']} and decide which exceptions should be visible.", "medium")

    for name, (symbol, _) in symbols.items():
        if symbol["public"] and symbol["kind"] in {"function", "method"}:
            ref = evidence(symbol["path"], symbol["line_start"], symbol["line_end"], "Public interface")
            if symbol["id"] not in test_refs:
                finding("test-gap", symbol["id"], f"No direct test reference to {name}", [ref],
                        "No statically resolved call from a test function targets this public interface.",
                        f"Add a test that calls {name}, including its boundary and failure cases.", "low",
                        "Indirect, integration, parametrized, or dynamically dispatched tests may already exercise it.")
            else:
                claim("test-reference", symbol["id"], f"A test function directly references {name}.",
                      [ref, *test_evidence[symbol["id"]]],
                      status="observed")
    for group in _cycles(graph):
        components = [next(c for c in bundle["components"] if c["id"] == key) for key in group]
        refs = [evidence(c["path"], 1, c["line_end"], "Module in import cycle") for c in components]
        finding("import-cycle", "|".join(group), "Import cycle: " + " ↔ ".join(c["name"] for c in components),
                refs, "These modules form a strongly connected group in the static import graph.",
                "Import each entry point in a controlled test environment; consider moving shared interfaces into a separate module.", "medium",
                "Conditional imports and deferred imports may make this cycle harmless.")

    for source in sources:
        if source["path"] == "pyproject.toml":
            try:
                config = tomllib.loads(source["content"])
                dependencies = config.get("project", {}).get("dependencies", [])
                bundle["repository"]["dependencies"].extend(str(d) for d in dependencies)
            except (tomllib.TOMLDecodeError, AttributeError, TypeError):
                bundle["open_questions"].append("pyproject.toml could not be interpreted; validate dependency metadata.")
        elif Path(source["path"]).name.startswith("requirements") and source["path"].endswith(".txt"):
            bundle["repository"]["dependencies"].extend(
                line.strip() for line in source["content"].splitlines()
                if line.strip() and not line.strip().startswith(("#", "-", "http", "git+"))
            )
        if source["language"] == "documentation":
            for line_no, line in enumerate(source["content"].splitlines(), 1):
                contract = re.search(r"\bAPI:\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s`]+)", line)
                if contract and not any(r["method"] == contract[1] and r["path"] == contract[2] for r in routes):
                    ref = evidence(source["path"], line_no, note="Explicit documented API contract")
                    finding("documented-route-gap", source["path"] + contract[0],
                            f"Documented route not found: {contract[1]} {contract[2]}", [ref],
                            "An explicit API contract in documentation has no matching literal route decorator.",
                            "Confirm router prefixes, generated routes, and framework wiring; add or correct the endpoint contract.", "medium",
                            "Framework prefixes and dynamically registered routes are outside this adapter.")
    bundle["repository"]["dependencies"] = sorted(set(bundle["repository"]["dependencies"]))
    if any(c["kind"] == "test_module" for c in bundle["components"]):
        bundle["repository"]["suggested_test_commands"] = ["python -m unittest discover -s tests", "python -m pytest"]
    else:
        bundle["open_questions"].append("No Python test modules were discovered. Where is behavior validated?")
    _extract_state_machines(trees, bundle, evidence, finding)
    bundle["assumptions"] = [
        {"id": stable_id("assumption", "static"), "statement": "Literal declarations represent the intended module structure.",
         "status": "inferred", "rationale": "Runtime monkey-patching and environment-dependent wiring are not resolved.", "owner": "reviewer"},
        {"id": stable_id("assumption", "tests"), "statement": "Test modules follow test_*.py, *_test.py, or tests/ conventions.",
         "status": "inferred", "rationale": "Test links use filenames and explicit calls, not an executed coverage report.", "owner": "reviewer"},
    ]
    bundle["open_questions"].append("Which product requirements and failure guarantees should become explicit invariants?")
    module_components = [c for c in bundle["components"] if c["kind"] in {"module", "test_module"}]
    node_labels = {c["id"]: f"n{i}" for i, c in enumerate(module_components)}
    diagram = ["flowchart LR"]
    for component in module_components:
        label = re.sub(r'[^a-zA-Z0-9_./ -]', "_", component["name"])
        diagram.append(f'  {node_labels[component["id"]]}["{label}"]')
    for rel in bundle["relationships"]:
        if rel["kind"] == "imports":
            diagram.append(f'  {node_labels[rel["source"]]} --> {node_labels[rel["target"]]}')
    sequence = ["sequenceDiagram", "  participant Entry", "  participant Target"]
    if bundle["flows"]:
        flow = bundle["flows"][0]
        sequence = ["sequenceDiagram", "  participant Entry"]
        participants = {}
        for step in flow["steps"][:12]:
            if step["target"] not in participants:
                participants[step["target"]] = f"P{len(participants)}"
                label = re.sub(r"[^a-zA-Z0-9_.]", "_", step["name"])
                sequence.append(f"  participant {participants[step['target']]} as {label}")
            sequence.append(f"  Entry->>{participants[step['target']]}: call at line {step['line']}")
    else:
        sequence.append("  Note over Entry,Target: No resolved internal call flow")
    bundle["diagrams"] = {"architecture": "\n".join(diagram), "sequence": "\n".join(sequence)}
    bundle["summary"] = {
        "files": len(sources), "modules": len(module_components), "symbols": len(symbols),
        "claims": len(bundle["claims"]), "findings": len(bundle["findings"]), "routes": len(routes),
        "test_modules": sum(c["kind"] == "test_module" for c in module_components),
        "directly_referenced_interfaces": sum(
            c["id"] in test_refs and c.get("public", False) and c["kind"] in {"function", "method"}
            for c in bundle["components"]
        ),
        "public_interfaces": sum(c.get("public", False) and c["kind"] in {"function", "method"} for c in bundle["components"]),
        "severity": {severity: sum(f["severity"] == severity for f in bundle["findings"]) for severity in ("high", "medium", "low", "info")},
    }
    bundle["interfaces"] = routes
    for key in ("components", "relationships", "claims", "findings", "evidence", "flows", "formal_candidates", "invariants", "state_machines"):
        bundle[key].sort(key=lambda item: item["id"])
    validate_bundle(bundle)
    return bundle


def _extract_state_machines(trees: dict, bundle: dict, evidence, finding) -> None:
    """Recognize explicit TRANSITIONS and TERMINAL_STATES literal fixtures."""
    for _, (tree, component) in trees.items():
        transitions, terminals, ref, terminal_ref = None, [], None, None
        for node in getattr(tree, "body", []):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [_expr(target) for target in targets]
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, RecursionError):
                continue
            if "TRANSITIONS" in names and isinstance(value, dict):
                entries = []
                for key, target in value.items():
                    if isinstance(key, tuple) and len(key) == 2 and all(isinstance(x, str) for x in (*key, target)):
                        entries.append({"from": key[0], "event": key[1], "to": target})
                if entries and len(entries) == len(value):
                    transitions = sorted(entries, key=lambda item: (item["from"], item["event"], item["to"]))
                    ref = evidence(component["path"], node.lineno, node.end_lineno, "Literal transition model")
            if "TERMINAL_STATES" in names and isinstance(value, (list, tuple, set)) and all(isinstance(x, str) for x in value):
                terminals = sorted(value)
                terminal_ref = evidence(component["path"], node.lineno, node.end_lineno, "Declared terminal states")
        if not transitions:
            continue
        states = sorted({t[key] for t in transitions for key in ("from", "to")} | set(terminals))
        identifier = stable_id("machine", component["path"])
        model_refs = [ref] + ([terminal_ref] if terminal_ref else [])
        evidence_ids = [item["id"] for item in model_refs]
        machine = {"id": identifier, "name": component["name"], "states": states,
                   "transitions": transitions, "terminal_states": terminals, "status": "observed",
                   "evidence_ids": evidence_ids, "component_id": component["id"]}
        bundle["state_machines"].append(machine)
        if not terminals:
            continue
        violating = [t for t in transitions if t["from"] in terminals and t["to"] != t["from"]]
        invariant_id = stable_id("invariant", identifier, "terminal-absorbing")
        bundle["invariants"].append({
            "id": invariant_id, "statement": "Terminal states cannot transition to a different state.",
            "scope": component["id"], "status": "contradicted" if violating else "tested",
            "evidence_ids": evidence_ids, "check": {"kind": "exhaustive-literal-model", "cases": len(transitions),
                                                 "passed": not violating, "counterexamples": violating},
            "note": "Checks the finite extracted table. Does not establish implementation conformance.",
        })
        lean_states = {s: f"s{i}" for i, s in enumerate(states)}
        lean_events = {s: f"e{i}" for i, s in enumerate(sorted({t["event"] for t in transitions}))}
        lean = [
            "-- Proposed abstract model generated by code-form. Review before checking.",
            "-- State mapping: " + canonical_json(lean_states),
            "-- Event mapping: " + canonical_json(lean_events),
            "-- This theorem concerns this table, not implementation conformance.",
            "namespace CodeForm", "",
            "inductive State where", *[f"  | {v}" for v in lean_states.values()], "  deriving DecidableEq, Repr", "",
            "inductive Event where", *[f"  | {v}" for v in lean_events.values()], "  deriving DecidableEq, Repr", "",
            "def step (state : State) (event : Event) : State :=",
            "  match state, event with",
            *[f"  | .{lean_states[t['from']]}, .{lean_events[t['event']]} => .{lean_states[t['to']]}" for t in transitions],
            "  | state, _ => state", "",
            "def terminal (state : State) : Prop :=",
            "  " + " ∨ ".join(f"state = .{lean_states[s]}" for s in terminals), "",
            "-- Unchecked candidate. `sorry` is a placeholder, never evidence of proof.",
            "theorem terminal_absorbing (state : State) (event : Event)",
            "    (h : terminal state) : step state event = state := by",
            "  sorry", "", "end CodeForm", "",
        ]
        bundle["formal_candidates"].append({
            "id": stable_id("formal", invariant_id), "name": f"{component['name']}: terminal-state invariant",
            "language": "Lean 4", "status": "proposed", "checker_status": "not_run",
            "invariant_id": invariant_id, "evidence_ids": evidence_ids, "source": "\n".join(lean),
            "model_boundary": "Finite transition table; runtime code, persistence and concurrency are not modeled.",
            "suggested_validation": "Review the model, replace sorry with a proof, and run Lean in an explicitly controlled environment.",
        })
        if violating:
            example = violating[0]
            finding("terminal-transition", component["id"], f"Terminal state can change in {component['name']}", model_refs,
                    f"The literal table permits {example['from']} --{example['event']}→ {example['to']}.",
                    "Confirm the terminal-state requirement and test the runtime transition function against this counterexample.", "high",
                    "The counterexample is confirmed for the literal model; intended runtime semantics still require review.")
