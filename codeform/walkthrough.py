"""Evidence-linked mathematical explanations of the supported model excerpts.

This is a deterministic presentation of existing adapters, not AI reconstruction
of arbitrary programs. Scenario evaluation operates on emitted model data and
never imports or executes the target repository.
"""

import hashlib
import re

from .model import stable_id
from .proofs import proof_plan

WALKTHROUGH_VERSION = "1.0.0"


def _purpose(bundle):
    readme = next((s for s in bundle["sources"] if s["path"].lower() == "readme.md"), None)
    if readme:
        lines = readme["content"].splitlines()
        for index, line in enumerate(lines):
            text = line.strip()
            if not text or text.startswith(("#", "```", ">", "[!", "<", "|", "- ", "* ")):
                continue
            paragraph = [text]
            end = index
            while end + 1 < len(lines) and lines[end + 1].strip() and not lines[end + 1].startswith(("#", "```")):
                end += 1
                paragraph.append(lines[end].strip())
            text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", " ".join(paragraph)).replace("**", "")
            return {"text": text[:1400], "status": "documented", "evidence": {
                "reference": readme["path"], "line_start": index + 1, "line_end": end + 1,
                "source_sha256": readme["sha256"],
            }}
    return {"text": "The captured repository does not state a purpose in a root README. Establish its intended behavior before interpreting structure as a design.",
            "status": "unknown", "evidence": None}


def _requirements(bundle):
    items = []
    for source in bundle["sources"]:
        if not source["path"].startswith("docs/requirements/") or not source["path"].endswith(".md"):
            continue
        lines = source["content"].splitlines()
        headings = [(i, re.match(r"### ([A-Z]+-\d+): (.+)", line)) for i, line in enumerate(lines)]
        headings = [(i, match) for i, match in headings if match]
        for n, (start, match) in enumerate(headings):
            end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
            block = lines[start:end]
            requirement = next((line for line in block if line.startswith(("MUST:", "MUST NOT:"))), "")
            status = next((line.removeprefix("- Status:").strip() for line in block if line.startswith("- Status:")), "unknown")
            items.append({"id": match[1], "title": match[2], "statement": requirement,
                          "declared_status": status, "status": "documented",
                          "evidence": {"reference": source["path"], "line_start": start + 1,
                                       "line_end": max(start + 1, end), "source_sha256": source["sha256"]}})
    return items


def _checked(artifact, report, bundle):
    if not report or report.get("snapshot_id") != bundle["id"] or report.get("repository_content_sha256") != bundle["repository"]["content_sha256"]:
        return None
    checked = next((a for a in report.get("artifacts", []) if a["id"] == artifact["id"]), None)
    if not checked or checked.get("status") not in {"proved", "disproved"}:
        return None
    expected_hash = hashlib.sha256(artifact["lean_source"].encode()).hexdigest()
    if (checked.get("checker") or {}).get("source_sha256") != expected_hash:
        return None
    return checked


def _latex(artifact):
    if artifact["kind"] == "finite-workflow":
        return r"\operatorname{terminal}(q)\ \Longrightarrow\ \forall es\in\mathcal E^*,\ \operatorname{run}(q,es)=q"
    assumption = r"s\ge0\land d\ge0\land " if artifact["property"] != "conservation" else ""
    result = {
        "conservation": r"x+y=s+d",
        "nonnegative": r"x\ge0\land y\ge0",
        "safety": r"x+y=s+d\land x\ge0\land y\ge0",
    }[artifact["property"]]
    return assumption + r"T(s,d,a)=(x,y)\ \Longrightarrow\ " + result


def build_walkthrough(bundle, report=None):
    artifacts = proof_plan(bundle)
    models = {}
    for artifact in artifacts:
        if artifact["status"] == "unsupported":
            continue
        key = artifact["name"]
        if key not in models:
            model_id = stable_id("walkmodel", bundle["id"], key)
            transfer = artifact["kind"] == "integer-transfer"
            if transfer:
                guarded = "reject amount > source;" in artifact["semantics"]
                models[key] = {
                    "id": model_id, "name": key, "kind": "integer-transfer", "guarded": guarded,
                    "purpose": "Move an integer amount between two balance values while preserving the intended accounting and safety properties.",
                    "purpose_status": "adapter interpretation", "state_latex": r"S=(s,d)\in\mathbb Z^2",
                    "transition_latex": r"T(s,d,a)=\begin{cases}\bot & a\le0\\"
                        + (r"\bot & a>s\\" if guarded else "")
                        + r"(s-a,d+a)&\text{otherwise}\end{cases}",
                    "notation": [
                        {"symbol": "s", "name": "Source balance", "domain": r"\mathbb Z", "unit": "integer balance units", "meaning": "Balance before subtracting the transfer amount."},
                        {"symbol": "d", "name": "Destination balance", "domain": r"\mathbb Z", "unit": "integer balance units", "meaning": "Balance before receiving the transfer amount."},
                        {"symbol": "a", "name": "Transfer amount", "domain": r"\mathbb Z", "unit": "integer balance units", "meaning": "Input amount; nonpositive amounts are rejected."},
                        {"symbol": "x,y", "name": "Returned balances", "domain": r"\mathbb Z^2", "unit": "integer balance units", "meaning": "The successful result is (source − amount, destination + amount)."},
                        {"symbol": r"\bot", "name": "Rejected outcome", "domain": "no successful pair", "unit": "outcome", "meaning": "Modeled rejection corresponds to ValueError in the supported source shape."},
                    ],
                    "scenarios": [
                        {"id": "normal", "name": "Transfer within balance", "inputs": {"source": "10", "destination": "4", "amount": "3"}},
                        {"id": "overdraft", "name": "Amount exceeds balance", "inputs": {"source": "10", "destination": "0", "amount": "11"}},
                        {"id": "zero", "name": "Rejected zero amount", "inputs": {"source": "10", "destination": "0", "amount": "0"}},
                        {"id": "assumption", "name": "Negative initial destination", "inputs": {"source": "10", "destination": "-5", "amount": "1"}},
                    ],
                    "boundary": "Exact built-in integers and independent balance values. The source adapter is trusted, not a formally verified Python compiler. No persistence, concurrency, aliasing, or resource failures are modeled.",
                    "evidence": artifact["evidence"],
                    "principles": [],
                }
            else:
                machine = next(m for m in bundle["state_machines"] if m["name"] == key)
                events = sorted({t["event"] for t in machine["transitions"]})
                normal = [e for e in ("pay", "ship") if e in events]
                models[key] = {
                    "id": model_id, "name": key, "kind": "finite-workflow",
                    "purpose": "Describe legal state progression and test the requirement that declared terminal states remain unchanged.",
                    "purpose_status": "adapter interpretation", "state_latex": r"q\in\mathcal Q,\quad e\in\mathcal E",
                    "transition_latex": r"q_{i+1}=\delta(q_i,e_i)",
                    "notation": [
                        {"symbol": "q", "name": "Current state", "domain": r"\mathcal Q", "unit": "state", "meaning": "One constructor in the captured finite state set."},
                        {"symbol": "e", "name": "Event", "domain": r"\mathcal E", "unit": "event", "meaning": "One event name represented by the transition table."},
                        {"symbol": r"\delta", "name": "Step function", "domain": r"\mathcal Q\times\mathcal E\to\mathcal Q", "unit": "transition", "meaning": "Uses the captured table; an unlisted pair leaves the state unchanged in the mathematical model."},
                        {"symbol": "es", "name": "Event sequence", "domain": r"\mathcal E^*", "unit": "finite list", "meaning": "The induction theorem quantifies over every finite list length, not just the scenario displayed."},
                    ],
                    "states": machine["states"], "events": events,
                    "terminal_states": machine["terminal_states"], "transitions": machine["transitions"],
                    "scenarios": [
                        {"id": "normal", "name": "Follow the workflow", "inputs": {"state": "pending" if "pending" in machine["states"] else machine["states"][0], "events": normal or events[:1]}},
                        {"id": "terminal", "name": "Start in a terminal state", "inputs": {"state": machine["terminal_states"][0], "events": events[:2]}},
                    ],
                    "boundary": "This is the finite table model. Unlisted pairs are identity transitions in Lean, while runtime Python may reject them. The workflow function's implementation refinement is not proved.",
                    "evidence": artifact["evidence"], "principles": [],
                }
        checked = _checked(artifact, report, bundle)
        model = models[key]
        model["principles"].append({
            "id": artifact["id"], "title": artifact["statement"], "latex": _latex(artifact),
            "status": checked["status"] if checked else "not_run", "scope": artifact["scope"],
            "assumptions": artifact["assumptions"], "reasoning": artifact["reasoning"],
            "dependencies": artifact["dependencies"],
            "lean_source": artifact["lean_source"], "theorem": artifact["theorem"],
            "axioms": checked["axioms"] if checked else None,
            "checker": checked["checker"] if checked else None, "evidence": artifact["evidence"],
            "counterexample": checked["counterexample"] if checked else artifact["counterexample"],
            "support": "checked mathematical model" if checked else "stated obligation; checker not run for this exact source",
        })
    requirements = _requirements(bundle)
    for model in models.values():
        model["default_result"] = _simulate_model(bundle, model, model["scenarios"][0]["inputs"])
    return {
        "schema_version": WALKTHROUGH_VERSION, "snapshot_id": bundle["id"],
        "repository_content_sha256": bundle["repository"]["content_sha256"],
        "purpose": _purpose(bundle), "models": list(models.values()),
        "requirements": requirements,
        "model_status": "supported model excerpts" if models else "semantic reconstruction unavailable",
        "unsupported": [a for a in artifacts if a["status"] == "unsupported"],
        "guidance": [
            "Start with the documented purpose and a concrete modeled operation.",
            "Inspect notation, hypotheses, intended properties, and source evidence.",
            "Change an example input or event sequence to challenge the model.",
            "Distinguish a simulated example from a checked theorem and from implementation refinement.",
            "Use findings and agent proposals only after understanding the requirement and its boundary.",
        ],
    }


def _integer(value, name):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,80}", value):
        raise ValueError(f"{name} must be an integer decimal string with at most 80 digits.")
    return int(value)


def simulate_scenario(bundle, payload):
    if not isinstance(payload, dict) or set(payload) != {"model_id", "inputs"}:
        raise ValueError("Scenarios require exactly model_id and inputs.")
    model = next((m for m in build_walkthrough(bundle)["models"] if m["id"] == payload["model_id"]), None)
    if model is None:
        raise KeyError("Supported scenario model not found in this snapshot.")
    return _simulate_model(bundle, model, payload["inputs"])


def _simulate_model(bundle, model, inputs):
    if not isinstance(inputs, dict):
        raise ValueError("Scenario inputs must be an object.")
    base = {"snapshot_id": bundle["id"], "model_id": model["id"], "kind": model["kind"],
            "result_kind": "simulated_model_example", "proved": False, "target_executed": False,
            "boundary": model["boundary"], "evidence": model["evidence"]}
    if model["kind"] == "integer-transfer":
        if set(inputs) != {"source", "destination", "amount"}:
            raise ValueError("Transfer inputs require source, destination, and amount.")
        s, d, a = (_integer(inputs[k], k) for k in ("source", "destination", "amount"))
        before = {"source": str(s), "destination": str(d)}
        assumptions = s >= 0 and d >= 0
        trace = [{"name": "Initial state", "state": before, "latex": f"S_0=({s},{d})", "detail": "Independent integer balances."}]
        trace.append({"name": "Positive-amount guard", "state": before, "latex": f"a={a}>0",
                      "holds": a > 0, "detail": "The modeled implementation rejects a nonpositive amount."})
        rejection = "Amount must be positive" if a <= 0 else None
        if rejection is None and model["guarded"]:
            trace.append({"name": "Sufficient-funds guard", "state": before, "latex": f"a={a}\\le s={s}",
                          "holds": a <= s, "detail": "The guarded model rejects an overdraft."})
            if a > s:
                rejection = "Insufficient funds"
        if rejection:
            trace.append({"name": "Rejected outcome", "state": before, "latex": r"T(s,d,a)=\bot",
                          "detail": rejection + "; no successful-return obligation is exercised."})
            return {**base, "outcome": "rejected", "inputs": {k: str(v) for k, v in zip(("source", "destination", "amount"), (s, d, a))},
                    "output": None, "assumptions_hold": assumptions, "trace": trace, "checks": []}
        x, y = s - a, d + a
        after = {"source": str(x), "destination": str(y)}
        trace.append({"name": "Apply balance update", "state": after, "latex": f"S_1=({x},{y})",
                      "detail": "Subtract the amount from source and add it to destination."})
        checks = [
            {"name": "Conservation", "latex": f"{x}+({y})={s}+({d})", "holds": x + y == s + d, "applicable": True},
            {"name": "Nonnegative outputs", "latex": f"{x}\\ge0\\land {y}\\ge0", "holds": x >= 0 and y >= 0, "applicable": assumptions},
        ]
        return {**base, "outcome": "success", "inputs": {k: str(v) for k, v in zip(("source", "destination", "amount"), (s, d, a))},
                "output": [str(x), str(y)], "assumptions_hold": assumptions, "trace": trace, "checks": checks}
    if set(inputs) != {"state", "events"} or inputs.get("state") not in model["states"]:
        raise ValueError("Workflow inputs require a known initial state and event list.")
    events = inputs["events"]
    if not isinstance(events, list) or len(events) > 32 or any(type(e) is not str or e not in model["events"] for e in events):
        raise ValueError("Use at most 32 modeled event names; this display limit does not bound the induction theorem.")
    initial = current = inputs["state"]
    trace = [{"name": "Initial state", "state": current, "detail": "The selected state in the captured finite model."}]
    violations = []
    for event in events:
        transition = next((t for t in model["transitions"] if t["from"] == current and t["event"] == event), None)
        following = transition["to"] if transition else current
        if current in model["terminal_states"] and following != current:
            violations.append({"from": current, "event": event, "to": following})
        trace.append({"name": event, "state": following, "from": current,
                      "detail": "Captured table transition." if transition else "Unlisted pair: identity in the mathematical model; runtime may reject."})
        current = following
    return {**base, "outcome": "completed", "inputs": inputs, "output": current,
            "assumptions_hold": initial in model["terminal_states"], "trace": trace,
            "checks": [{"name": "Initial terminal state preserved", "holds": current == initial,
                        "applicable": initial in model["terminal_states"]}],
            "counterexamples": violations}
