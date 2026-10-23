"""Generate and check a narrow, explicit mathematical model of captured source.

Only code produced by these fixed templates is sent to Lean. Target Lean files,
imports, project configuration, and Python code are never executed.
"""

import ast
import hashlib
import os
import re
import shutil
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from .model import canonical_json, stable_id

LEAN_VERSION = "4.19.0"
PINNED_TOOLCHAIN = f"leanprover/lean4:v{LEAN_VERSION}"
PROOF_VERSION = "integer-transfer-and-finite-model-v1"
OBLIGATION_VERSION = "fixed-declaration-v1"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
TIMEOUT_SECONDS = 30
MAX_HEARTBEATS = 400_000


def find_lean(explicit: Path | None = None) -> Path | None:
    if explicit:
        executable = explicit.expanduser().resolve()
        if not executable.is_file():
            raise ValueError("Lean executable does not exist.")
        return executable
    root = Path(__file__).resolve().parents[1]
    local = root / ".codeform/tools/lean-4.19.0-windows/bin/lean.exe"
    return local if local.is_file() else Path(shutil.which("lean")).resolve() if shutil.which("lean") else None


def checker_info(executable: Path | None) -> dict:
    if executable is None:
        return {"available": False, "toolchain": PINNED_TOOLCHAIN, "error": "Lean is not installed. Run scripts/setup-lean.ps1 or configure --lean."}
    try:
        result = subprocess.run([str(executable), "--version"], capture_output=True, encoding="utf-8",
                                errors="replace", timeout=10, check=False)
        text = result.stdout.strip()
        compatible = result.returncode == 0 and re.search(rf"\bversion {re.escape(LEAN_VERSION)}(?:\b|,)", text) is not None
        return {"available": compatible, "toolchain": PINNED_TOOLCHAIN, "version": text,
                "executable": str(executable),
                **({} if compatible else {"error": f"Expected Lean {LEAN_VERSION}; configure the pinned toolchain."})}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "toolchain": PINNED_TOOLCHAIN, "error": str(error)}


def _evidence(bundle: dict, component: dict) -> dict:
    return {"reference": component["path"], "line_start": component["line_start"],
            "line_end": component["line_end"], "commit_sha": bundle["repository"]["commit_sha"],
            "source_sha256": next(s["sha256"] for s in bundle["sources"] if s["path"] == component["path"])}


def _transfer_shape(content: str, name: str) -> tuple[bool, str]:
    """Require every executable statement to match an audited adapter shape."""
    tree = ast.parse(content)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(functions) != 1:
        raise ValueError("Expected exactly one top-level function.")
    node = functions[0]
    if node.decorator_list or node.args.posonlyargs or node.args.kwonlyargs or node.args.vararg or node.args.kwarg or node.args.defaults:
        raise ValueError("Decorators, defaults, and extended argument binding are unsupported.")
    if [arg.arg for arg in node.args.args] != ["source", "destination", "amount"]:
        raise ValueError("This adapter requires source, destination, amount arguments in that order.")
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    guarded = len(body) == 3
    template = """
def expected(source, destination, amount):
    if amount <= 0:
        raise ValueError("rejected")
    return source - amount, destination + amount
"""
    if guarded:
        template = template.replace("    return", '    if amount > source:\n        raise ValueError("rejected")\n    return')
    expected = ast.parse(template).body[0].body
    if len(body) != len(expected):
        raise ValueError("Unsupported statements: only amount guards and the exact balance update are modeled.")
    for actual, wanted in zip(body, expected):
        if isinstance(actual, ast.If) and isinstance(wanted, ast.If):
            if ast.dump(actual.test) != ast.dump(wanted.test) or actual.orelse or len(actual.body) != 1:
                raise ValueError("Only the documented positive-amount and overdraft guards are supported.")
            rejection = actual.body[0]
            if not isinstance(rejection, ast.Raise) or rejection.cause is not None or not isinstance(rejection.exc, ast.Call):
                raise ValueError("Rejection must be an explicit ValueError.")
            call = rejection.exc
            if not isinstance(call.func, ast.Name) or call.func.id != "ValueError" or call.keywords or len(call.args) > 1:
                raise ValueError("Only a built-in ValueError with a literal message is supported.")
            if call.args and (not isinstance(call.args[0], ast.Constant) or not isinstance(call.args[0].value, str)):
                raise ValueError("Dynamic exception construction is unsupported.")
        elif ast.dump(actual) != ast.dump(wanted):
            raise ValueError("Unsupported return or expression; the source-to-model adapter must represent the entire function.")
    # Names used by the semantics must not be shadowed at module scope.
    for item in tree.body:
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            raise ValueError("Imports in transfer modules are unsupported.")
        if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.ClassDef)):
            raise ValueError("Module mutation or classes are unsupported by this adapter.")
        if isinstance(item, ast.FunctionDef) and item.name in {"ValueError", name} and item is not node:
            raise ValueError("Shadowed modeled names are unsupported.")
        if not isinstance(item, ast.FunctionDef) and not (
            isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)
        ):
            raise ValueError("Executable module-level statements are unsupported.")
    semantic = "reject amount ≤ 0; " + ("reject amount > source; " if guarded else "") + "return (source − amount, destination + amount)"
    return guarded, semantic


def _success_proof(guarded: bool, goal: str) -> str:
    """The hypothesis encodes a successful normal return in the generated model."""
    lines = ["  unfold transfer at h", "  split at h", "  · simp_all"]
    if guarded:
        lines += ["  · split at h", "    · simp_all", "    · simp_all", f"      {goal}"]
    else:
        lines += ["  · simp_all", f"    {goal}"]
    return "\n".join(lines)


def _transfer_artifacts(bundle: dict) -> list[dict]:
    source = next((s for s in bundle["sources"] if s["path"] == "contracts.toml"), None)
    if source is None:
        return []
    try:
        config = tomllib.loads(source["content"])
    except tomllib.TOMLDecodeError as error:
        return [{"id": stable_id("proof", "invalid-contracts"), "name": "Contract configuration",
                 "status": "unsupported", "reason": str(error), "kind": "contract"}]
    if config.get("schema_version") != "1.0.0" or config.get("adapter") != "integer-transfer-v1" or not isinstance(config.get("contracts"), list):
        return [{"id": stable_id("proof", "unsupported-contracts"), "name": "Contract configuration",
                 "status": "unsupported", "reason": "Expected reviewed integer-transfer-v1 contracts.", "kind": "contract"}]
    if len(config["contracts"]) > 30:
        return [{"id": stable_id("proof", "contract-limit"), "name": "Contract configuration",
                 "status": "unsupported", "reason": "At most 30 contracts can be checked per snapshot.", "kind": "contract"}]
    artifacts = []
    seen = set()
    for contract in config["contracts"]:
        name = contract.get("function", "") if isinstance(contract, dict) else ""
        if not isinstance(name, str) or not name or name in seen:
            artifacts.append({"id": stable_id("proof", "invalid-entry", str(len(artifacts))), "name": "Contract",
                              "status": "unsupported", "reason": "Function names must be nonempty unique strings.", "kind": "contract"})
            continue
        seen.add(name)
        comp = next((c for c in bundle["components"] if c["name"] == name and c["kind"] == "function"), None)
        if not comp:
            artifacts.append({"id": stable_id("proof", name), "name": name or "Contract",
                              "status": "unsupported", "reason": "Contract function was not found.", "kind": "contract"})
            continue
        properties = contract.get("properties")
        if not isinstance(properties, list) or not properties or any(
            not isinstance(p, str) or p not in {"conservation", "nonnegative", "safety"} for p in properties
        ):
            artifacts.append({"id": stable_id("proof", name), "name": name, "kind": "contract",
                              "status": "unsupported", "reason": "Only conservation, nonnegative, and safety properties are supported."})
            continue
        content = next(s["content"] for s in bundle["sources"] if s["path"] == comp["path"])
        try:
            guarded, semantic = _transfer_shape(content, name.rsplit(".", 1)[-1])
        except (ValueError, SyntaxError) as error:
            artifacts.append({"id": stable_id("proof", name), "name": name, "status": "unsupported",
                              "reason": str(error), "kind": "contract", "evidence": [_evidence(bundle, comp)]})
            continue
        prefix = "P" + stable_id("model", name).split("_")[1]
        definition = [
            "import Std", f"set_option maxHeartbeats {MAX_HEARTBEATS}", f"namespace {prefix}",
            "def transfer (source destination amount : Int) : Option (Int × Int) :=",
            "  if amount ≤ 0 then none else",
            *(["  if amount > source then none else"] if guarded else []),
            "  some (source - amount, destination + amount)", "",
        ]
        assumptions = [
            {"id": "exact-integers", "kind": "semantic assumption", "statement": "Inputs are exact built-in integers, modeled as arbitrary-precision Lean Int."},
            {"id": "nonnegative-inputs", "kind": "precondition", "statement": "The source and destination balances start nonnegative."},
            {"id": "distinct-values", "kind": "model boundary", "statement": "Balances are independent values; no shared storage, aliasing, concurrency, or resource failure is modeled."},
            {"id": "translation", "kind": "trusted boundary", "statement": "A narrow audited AST adapter maps all statements in this function; its equivalence to Python is not formally proved."},
        ]
        explanation = [
            {"title": "Model the outcome", "detail": semantic + ". ValueError rejection is represented by none; successful return by some pair."},
            {"title": "Split the execution paths", "detail": "The proof splits on each modeled guard. Rejected paths cannot satisfy the successful-return hypothesis."},
            {"title": "Substitute the returned balances", "detail": "A successful return gives x = source − amount and y = destination + amount."},
            {"title": "Discharge integer arithmetic", "detail": "Lean's omega tactic constructs a proof for the remaining linear integer arithmetic."},
        ]
        for property_name in dict.fromkeys(properties):
            reasoning = list(explanation)
            counterexample = None
            dependencies = []
            if property_name == "conservation":
                theorem = "conservation"
                statement = "Every successful transfer preserves total funds."
                formula = "transfer(s,d,a) = some(x,y) ⇒ x + y = s + d"
                formal = f"theorem conservation (s d a x y : Int)\n    (h : transfer s d a = some (x, y)) : x + y = s + d := by\n{_success_proof(guarded, 'omega')}\n"
                expected = "proved"
            elif property_name == "nonnegative" and guarded:
                theorem = "nonnegative"
                statement = "Every successful transfer returns nonnegative balances."
                formula = "s ≥ 0 ∧ d ≥ 0 ∧ transfer(s,d,a) = some(x,y) ⇒ x ≥ 0 ∧ y ≥ 0"
                formal = f"theorem nonnegative (s d a x y : Int)\n    (_hs : 0 ≤ s) (hd : 0 ≤ d)\n    (h : transfer s d a = some (x, y)) : 0 ≤ x ∧ 0 ≤ y := by\n{_success_proof(guarded, 'constructor <;> omega')}\n"
                expected = "proved"
            elif property_name == "safety" and guarded:
                theorem = "safety"
                statement = "Successful transfers preserve funds and nonnegative balances."
                formula = "s ≥ 0 ∧ d ≥ 0 ∧ transfer(s,d,a) = some(x,y) ⇒ x+y=s+d ∧ x≥0 ∧ y≥0"
                formal = f"""theorem conservation (s d a x y : Int)
    (h : transfer s d a = some (x, y)) : x + y = s + d := by
{_success_proof(guarded, 'omega')}
theorem nonnegative (s d a x y : Int)
    (_hs : 0 ≤ s) (hd : 0 ≤ d)
    (h : transfer s d a = some (x, y)) : 0 ≤ x ∧ 0 ≤ y := by
{_success_proof(guarded, 'constructor <;> omega')}
theorem safety (s d a x y : Int) (hs : 0 ≤ s) (hd : 0 ≤ d)
    (h : transfer s d a = some (x, y)) :
    x + y = s + d ∧ 0 ≤ x ∧ 0 ≤ y := by
  exact ⟨conservation s d a x y h, nonnegative s d a x y hs hd h⟩
"""
                dependencies = [stable_id("proof", name, "conservation"), stable_id("proof", name, "nonnegative")]
                expected = "proved"
            else:
                theorem = "counterexample"
                statement = ("Every successful transfer returns nonnegative balances." if property_name == "nonnegative"
                             else "Successful transfers preserve funds and nonnegative balances.")
                formula = "s ≥ 0 ∧ d ≥ 0 ∧ transfer(s,d,a) = some(x,y) ⇒ " + ("x≥0 ∧ y≥0" if property_name == "nonnegative" else "x+y=s+d ∧ x≥0 ∧ y≥0")
                formal = """theorem counterexample :
    (0 : Int) ≤ 10 ∧ (0 : Int) ≤ 0 ∧
    transfer 10 0 11 = some (-1, 11) ∧ ¬ ((0 : Int) ≤ -1) := by
  decide
"""
                expected = "disproved"
                counterexample = {"inputs": {"source": 10, "destination": 0, "amount": 11},
                                  "output": [-1, 11], "violated": "The source balance is negative.",
                                  "checked": False}
                reasoning = [
                    {"title": "Choose an admissible input", "detail": "Both initial balances are nonnegative: source=10, destination=0."},
                    {"title": "Follow the actual modeled path", "detail": "amount=11 passes the positive-amount guard; no overdraft guard exists."},
                    {"title": "Exhibit the violation", "detail": "The returned pair is (−1, 11). Lean checks the witness by reduction."},
                ]
            full_source = "\n".join(definition) + formal + f"\n#print axioms {theorem}\nend {prefix}\n"
            artifacts.append({
                "id": stable_id("proof", name, property_name), "name": name, "property": property_name,
                "kind": "integer-transfer", "statement": statement, "formula": formula,
                "status": "not_run", "expected_result": expected, "scope": "abstract-model-with-trusted-source-translation",
                "assumptions": assumptions if property_name != "conservation" else [a for a in assumptions if a["id"] != "nonnegative-inputs"],
                "feasibility": {"status": "established", "witness": {"source": 10, "destination": 0, "amount": 1},
                                "note": "Witness of the fixed adapter's stated preconditions; no general consistency solver."},
                "evidence": [_evidence(bundle, comp)], "contract_sha256": source["sha256"],
                "semantics": semantic, "theorem": f"{prefix}.{theorem}", "lean_source": full_source,
                "dependencies": dependencies, "reasoning": reasoning, "counterexample": counterexample,
                "checker": None, "axioms": [],
                "repair": {"description": "Reject amount > source before returning the new balances.",
                           "replacement": "if amount > source:\n    raise ValueError(\"Insufficient funds\")",
                           "reference_implementation": "transfer.transfer_guarded",
                           "status": "proposal; source has not been changed"} if counterexample else None,
            })
    return artifacts


def _workflow_artifacts(bundle: dict) -> list[dict]:
    artifacts = []
    for machine in bundle["state_machines"]:
        if not machine["terminal_states"]:
            continue
        if len(machine["states"]) > 100 or len(machine["transitions"]) > 300:
            artifacts.append({"id": stable_id("proof", machine["id"]), "name": machine["name"],
                              "status": "unsupported", "kind": "finite-workflow",
                              "reason": "Workflow proof limit: 100 states and 300 explicit transitions."})
            continue
        comp = next(c for c in bundle["components"] if c["id"] == machine["component_id"])
        states = {name: f"s{i}" for i, name in enumerate(machine["states"])}
        events = {name: f"e{i}" for i, name in enumerate(sorted({t["event"] for t in machine["transitions"]}))}
        prefix = "M" + stable_id("model", machine["id"]).split("_")[1]
        violations = [t for t in machine["transitions"] if t["from"] in machine["terminal_states"] and t["from"] != t["to"]]
        lines = [
            "import Std", f"set_option maxHeartbeats {MAX_HEARTBEATS}", f"namespace {prefix}",
            "-- State mapping: " + canonical_json(states), "-- Event mapping: " + canonical_json(events),
            "inductive State where", *[f"  | {v}" for v in states.values()], "  deriving DecidableEq, Repr",
            "inductive Event where", *[f"  | {v}" for v in events.values()], "  deriving DecidableEq, Repr",
            "def step (s : State) (e : Event) : State :=",
            "  match s, e with", *[f"  | .{states[t['from']]}, .{events[t['event']]} => .{states[t['to']]}" for t in machine["transitions"]],
            "  | s, _ => s",
            "def terminal (s : State) : Prop :=",
            "  " + " ∨ ".join(f"s = .{states[s]}" for s in machine["terminal_states"]),
            "instance (s : State) : Decidable (terminal s) := by unfold terminal; infer_instance",
            "def run : State → List Event → State",
            "  | s, [] => s",
            "  | s, e :: es => run (step s e) es",
        ]
        if violations:
            bad = violations[0]
            theorem = "counterexample"
            lines += [
                f"theorem counterexample : terminal .{states[bad['from']]} ∧",
                f"    run .{states[bad['from']]} [.{events[bad['event']]}] ≠ .{states[bad['from']]} := by decide",
            ]
        else:
            theorem = "terminal_forever"
            lines += [
                "theorem terminal_absorbing (s : State) (e : Event) : terminal s → step s e = s := by",
                "  cases s <;> cases e <;> decide",
                "theorem terminal_forever (s : State) (es : List Event) (h : terminal s) : run s es = s := by",
                "  induction es with",
                "  | nil => rfl",
                "  | cons e es ih =>",
                "    simp only [run, terminal_absorbing s e h]",
                "    exact ih",
            ]
        lines += [f"#print axioms {theorem}", f"end {prefix}", ""]
        artifacts.append({
            "id": stable_id("proof", machine["id"], "terminal"), "name": machine["name"],
            "kind": "finite-workflow", "property": "terminal_absorbing",
            "statement": "Declared terminal states remain unchanged through every finite sequence of modeled events.",
            "formula": "terminal(s) ⇒ ∀ events : List Event, run(s,events) = s",
            "status": "not_run", "expected_result": "disproved" if violations else "proved",
            "scope": "finite-abstract-model",
            "assumptions": [
                {"id": "finite-table", "kind": "definition", "statement": "The captured TRANSITIONS table defines the entire modeled step function."},
                {"id": "unlisted-events", "kind": "model convention", "statement": "Unlisted state/event pairs leave the state unchanged in this model; runtime rejection may differ."},
                {"id": "terminal-requirement", "kind": "requirement", "statement": "TERMINAL_STATES defines which states must be absorbing; this requirement is checked, not assumed true."},
            ],
            "feasibility": {"status": "established", "witness": machine["states"],
                            "note": "A finite nonempty state space; only extracted modeled events are quantified."},
            "semantics": f"{len(machine['states'])} states, {len(events)} events, {len(machine['transitions'])} explicit transitions.",
            "evidence": [_evidence(bundle, comp)], "contract_sha256": None,
            "theorem": f"{prefix}.{theorem}", "lean_source": "\n".join(lines), "dependencies": [],
            "reasoning": [
                {"title": "Define states and events", "detail": "The source table becomes finite Lean inductive types and a total step function."},
                {"title": "State the obligation", "detail": "Every declared terminal state must remain unchanged for every modeled event."},
                {"title": "Check one-step preservation", "detail": "Lean checks a concrete counterexample." if violations else "The proof considers every constructor pair; decide produces kernel-checked evidence."},
                *([] if violations else [{"title": "Induct over all finite executions", "detail": "The empty sequence preserves the state. Each event preserves a terminal state, and the induction hypothesis covers the remaining sequence."}]),
            ],
            "counterexample": {"inputs": {"state": violations[0]["from"], "event": violations[0]["event"]},
                              "output": violations[0]["to"], "violated": "The terminal state changes.", "checked": False} if violations else None,
            "checker": None, "axioms": [],
            "repair": {"description": "Remove or revise the terminal-state transition, then re-analyze and re-check.",
                       "status": "proposal; source has not been changed"} if violations else None,
        })
    return artifacts


def proof_plan(bundle: dict) -> list[dict]:
    artifacts = _transfer_artifacts(bundle) + _workflow_artifacts(bundle)
    for artifact in artifacts:
        if artifact["status"] != "unsupported":
            artifact["obligation"] = bind_obligation(bundle["id"], artifact)
    return artifacts


def bind_obligation(snapshot_id: str, artifact: dict) -> dict:
    """Bind the declaration before attempting its proof.

    This splits trusted templates; it is not a user-supplied Lean parser.
    """
    source = artifact["lean_source"]
    local_name = artifact["theorem"].rsplit(".", 1)[-1]
    start = source.index(f"theorem {local_name} ")
    match = re.search(r":= by(?:\n| )", source[start:])
    if match is None:
        raise ValueError("Generated theorem lacks a tactic proof.")
    body_start = start + match.end()
    footer_start = source.index(f"\n#print axioms {local_name}", body_start)
    context, declaration = source[:start], source[start:body_start]
    identity = {
        "version": OBLIGATION_VERSION, "snapshot_id": snapshot_id,
        "artifact_id": artifact["id"], "theorem": artifact["theorem"],
        "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
        "declaration": declaration, "expected_result": artifact["expected_result"],
        "source_evidence": artifact["evidence"], "contract_sha256": artifact.get("contract_sha256"),
        "formula": artifact["formula"],
    }
    digest = hashlib.sha256(canonical_json(identity).encode()).hexdigest()
    return {
        **identity, "id": stable_id("obligation", digest), "sha256": digest,
        "context_source": context,
        "reference_body": source[body_start:footer_start],
        "footer": source[footer_start:], "strategies": ["generated", "simplify", "decide"],
        "binding": "Fixed generated context and theorem declaration; only controlled tactic strategies may vary.",
    }


def attempt_source(artifact: dict, strategy: str) -> str:
    obligation = artifact["obligation"]
    if strategy not in obligation["strategies"]:
        raise ValueError("Unknown proof strategy. Choose generated, simplify, or decide.")
    body = {"generated": obligation["reference_body"], "simplify": "  simp_all\n", "decide": "  decide\n"}[strategy]
    return obligation["context_source"] + obligation["declaration"] + body + obligation["footer"]


def _check_generated(artifact: dict, executable: Path, info: dict, run_dir: Path) -> dict:
    source = artifact["lean_source"]
    obligation = artifact.get("obligation")
    if not isinstance(obligation, dict):
        return {"status": "error", "error": "Missing fixed proof obligation.", "axioms": []}
    prefix = obligation["context_source"] + obligation["declaration"]
    if not source.startswith(prefix) or not source.endswith(obligation["footer"]):
        return {"status": "error", "error": "Proof input changes the fixed context or theorem declaration.", "axioms": []}
    if source not in {attempt_source(artifact, strategy) for strategy in obligation["strategies"]}:
        return {"status": "error", "error": "Proof body is outside the controlled strategy set.", "axioms": []}
    # Defense in depth: fixed templates are the only callers. Do not expose this
    # as an endpoint accepting arbitrary source; Lean elaboration can execute code.
    if re.search(r"\b(sorry|admit|axiom|unsafe|run_cmd|native_decide)\b", re.sub(r"--[^\n]*", "", source)):
        return {"status": "error", "error": "Incomplete or unapproved proof source was rejected.", "axioms": []}
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / (hashlib.sha256(source.encode()).hexdigest() + ".lean")
    if target.is_symlink():
        raise ValueError("Linked proof input files are not supported.")
    target.write_text(source, encoding="utf-8")
    environment = dict(os.environ)
    # Do not load user/repository-provided Lean libraries or preload hooks.
    for key in ("LEAN_PATH", "LEAN_SRC_PATH", "LEAN_SYSROOT", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES"):
        environment.pop(key, None)
    # Lean 4.19's memory option is broken in its Windows build. The fixed
    # templates, table-size caps, heartbeat bound, and process timeout apply;
    # report the absence of an OS memory sandbox rather than claiming one.
    command = [str(executable), str(target)]
    try:
        process = subprocess.run(command, cwd=run_dir, env=environment, capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Lean exceeded {TIMEOUT_SECONDS} seconds.", "axioms": []}
    except OSError as error:
        return {"status": "error", "error": str(error), "axioms": []}
    diagnostic = (process.stdout + process.stderr)[:32_000]
    # #print axioms reports actual transitive dependencies, not lexical guesses.
    theorem = re.escape(artifact["theorem"])
    match = re.search(rf"'{theorem}' depends on axioms:\s*\[([^\]]*)\]", diagnostic, re.S)
    no_axioms = f"'{artifact['theorem']}' does not depend on any axioms" in diagnostic
    axioms = sorted(x.strip() for x in match[1].split(",") if x.strip()) if match else []
    accepted = process.returncode == 0 and (match is not None or no_axioms) and set(axioms) <= ALLOWED_AXIOMS
    accepted = accepted and "sorryAx" not in diagnostic and "warning:" not in diagnostic.lower()
    checker = {"toolchain": PINNED_TOOLCHAIN, "version": info["version"], "exit_code": process.returncode,
               "stdout": diagnostic, "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
               "obligation_id": obligation["id"], "obligation_sha256": obligation["sha256"],
               "theorem": artifact["theorem"], "declaration_verified": True,
               "command": command, "timeout_seconds": TIMEOUT_SECONDS, "max_heartbeats": MAX_HEARTBEATS,
               "os_memory_sandbox": False,
               "checked_at": datetime.now(timezone.utc).isoformat(),
               "trust": "Local Lean kernel, pinned Std library, fixed code-form generator, and operating environment.",
               "axiom_policy": sorted(ALLOWED_AXIOMS)}
    return {"status": artifact["expected_result"] if accepted else "error", "axioms": axioms,
            "checker": checker, **({} if accepted else {"error": "Lean did not accept a complete proof with the permitted dependencies."})}


def check_attempt(artifact: dict, strategy: str, executable: Path | None, output_dir: Path) -> dict:
    source = attempt_source(artifact, strategy)
    info = checker_info(executable)
    if not info["available"]:
        return {"status": "not_run", "error": info["error"], "axioms": [], "checker": info}
    return _check_generated({**artifact, "lean_source": source}, executable, info, output_dir)


def verify_bundle(bundle: dict, executable: Path | None, output_dir: Path) -> dict:
    info = checker_info(executable)
    artifacts = proof_plan(bundle)
    for artifact in artifacts:
        if artifact["status"] == "unsupported":
            continue
        if not info["available"]:
            artifact["reason"] = info["error"]
            continue
        checked = _check_generated(artifact, executable, info, output_dir.resolve() / "inputs")
        artifact.update(checked)
        if artifact.get("counterexample"):
            artifact["counterexample"]["checked"] = artifact["status"] == "disproved"
    fingerprint = hashlib.sha256(canonical_json(
        [(item["id"], item.get("lean_source", ""), item["status"]) for item in artifacts]
    ).encode()).hexdigest()
    return {
        "schema_version": "1.0.0", "id": stable_id("verification", bundle["id"], fingerprint, PROOF_VERSION),
        "snapshot_id": bundle["id"], "repository_content_sha256": bundle["repository"]["content_sha256"],
        "created_at": datetime.now(timezone.utc).isoformat(), "generator_version": PROOF_VERSION,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checker": info, "artifacts": artifacts,
        "summary": {status: sum(a["status"] == status for a in artifacts)
                    for status in ("proved", "disproved", "unsupported", "not_run", "error", "timeout")},
        "limitations": [
            "Only fixed integer-transfer shapes and explicit finite transition tables are supported.",
            "Proofs concern emitted mathematical semantics; the source translator is trusted, not formally verified.",
            "Input types, resource limits, persistence, concurrency, and runtime module changes are outside the model.",
            "Imported proof reports are not trusted; checking is local and generated from immutable captured source.",
        ],
    }
