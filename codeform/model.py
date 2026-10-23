"""Bundle integrity and deterministic artifact generation."""

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = "1.0.0"
STATUSES = {"observed", "inferred", "proposed", "tested", "proved", "contradicted", "unknown"}


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:16]
    return f"{prefix}_{digest}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_bundle(bundle: dict) -> None:
    """Validate references and source boundaries, including imported snapshots."""
    if not isinstance(bundle, dict) or bundle.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported bundle schema; expected 1.0.0.")
    if not isinstance(bundle.get("id"), str) or not re.fullmatch(r"snapshot_[0-9a-f]{16}", bundle["id"]):
        raise ValueError("Invalid snapshot identifier.")
    if not isinstance(bundle.get("repository"), dict):
        raise ValueError("Missing repository metadata.")
    if any(not isinstance(bundle["repository"].get(key), str) for key in ("name", "path", "content_sha256")):
        raise ValueError("Invalid repository metadata.")
    if not re.fullmatch(r"[0-9a-f]{64}", bundle["repository"]["content_sha256"]):
        raise ValueError("Invalid repository content hash.")
    for key in ("components", "relationships", "claims", "findings", "sources", "evidence",
                "assumptions", "invariants", "formal_candidates", "flows", "state_machines", "interfaces"):
        if not isinstance(bundle.get(key), list):
            raise ValueError(f"Missing or invalid {key}.")
        if any(not isinstance(item, dict) for item in bundle[key]):
            raise ValueError(f"Invalid entity in {key}.")
    for key in ("limitations", "open_questions"):
        if not isinstance(bundle.get(key), list) or any(not isinstance(item, str) for item in bundle[key]):
            raise ValueError(f"Invalid {key}.")
    sources = {}
    for source in bundle["sources"]:
        path = source.get("path", "")
        if not isinstance(path, str) or not path or path.startswith(("/", "\\")) or ":" in path:
            raise ValueError("Source paths must be relative.")
        if ".." in path.replace("\\", "/").split("/") or "\\" in path or path in sources:
            raise ValueError("Invalid or duplicate source path.")
        if not isinstance(source.get("content"), str):
            raise ValueError("Source content must be text.")
        if hashlib.sha256(source["content"].encode()).hexdigest() != source.get("sha256"):
            raise ValueError(f"Source hash mismatch: {path}")
        sources[path] = source["content"]
    content_hash = hashlib.sha256(canonical_json(
        sorted((s["path"], s["sha256"]) for s in bundle["sources"])
    ).encode()).hexdigest()
    if bundle["repository"]["content_sha256"] != content_hash:
        raise ValueError("Repository content hash does not match captured sources.")
    ids = {}
    for key in ("components", "relationships", "claims", "findings", "evidence",
                "assumptions", "invariants", "formal_candidates", "flows", "state_machines"):
        if any(not isinstance(item.get("id"), str) or not item["id"] for item in bundle[key]):
            raise ValueError(f"Missing {key} identifier.")
        ids[key] = {item["id"] for item in bundle[key]}
        if len(ids[key]) != len(bundle[key]):
            raise ValueError(f"Duplicate {key} identifiers.")

    def check_evidence(evidence: dict) -> None:
        reference = evidence.get("reference")
        if reference not in sources:
            raise ValueError(f"Evidence references missing source: {reference}")
        start, end = evidence.get("line_start"), evidence.get("line_end")
        if not isinstance(start, int) or not isinstance(end, int) or not (
            1 <= start <= end <= max(1, len(sources[reference].splitlines()))
        ):
            raise ValueError(f"Invalid evidence range: {reference}")

    for evidence in bundle["evidence"]:
        check_evidence(evidence)
    for item in bundle["components"]:
        check_evidence({"reference": item.get("path"), "line_start": item.get("line_start"),
                        "line_end": item.get("line_end")})
        if item.get("kind") not in {"module", "test_module", "class", "function", "method"} or not isinstance(item.get("name"), str):
            raise ValueError("Invalid component.")
    for claim in bundle["claims"]:
        if claim.get("status") not in STATUSES or not isinstance(claim.get("statement"), str) or not claim["statement"]:
            raise ValueError("Invalid claim.")
        if claim.get("scope") not in ids["components"]:
            raise ValueError("Claim references missing component.")
        if not isinstance(claim.get("evidence"), list) or not claim["evidence"] or any(not isinstance(e, dict) for e in claim["evidence"]):
            raise ValueError("Claims must carry evidence.")
        for evidence in claim["evidence"]:
            check_evidence(evidence)
    for relation in bundle["relationships"]:
        if relation.get("source") not in ids["components"] or relation.get("target") not in ids["components"]:
            raise ValueError("Relationship references missing component.")
        if relation.get("kind") not in {"contains", "imports", "calls", "tests"}:
            raise ValueError("Invalid relationship kind.")
        if not isinstance(relation.get("evidence_ids"), list) or any(ref not in ids["evidence"] for ref in relation["evidence_ids"]):
            raise ValueError("Relationship references missing evidence.")
    for finding in bundle["findings"]:
        if finding.get("severity") not in {"high", "medium", "low", "info"}:
            raise ValueError("Invalid finding severity.")
        if any(not isinstance(finding.get(key), str) for key in
               ("title", "rule", "rationale", "uncertainty", "suggested_validation", "suggested_test")):
            raise ValueError("Invalid finding content.")
        if not isinstance(finding.get("evidence_ids"), list) or not finding["evidence_ids"] or any(ref not in ids["evidence"] for ref in finding["evidence_ids"]):
            raise ValueError("Finding references missing evidence.")
    for key in ("flows", "state_machines", "invariants", "formal_candidates"):
        for item in bundle[key]:
            if not isinstance(item.get("evidence_ids"), list) or any(ref not in ids["evidence"] for ref in item["evidence_ids"]):
                raise ValueError(f"{key} references missing evidence.")
            if item.get("status") not in STATUSES:
                raise ValueError(f"Invalid {key} status.")
    for flow in bundle["flows"]:
        if not isinstance(flow.get("name"), str) or flow.get("entry_component_id") not in ids["components"]:
            raise ValueError("Invalid flow entry point.")
        if not isinstance(flow.get("steps"), list) or any(
            not isinstance(step, dict) or step.get("target") not in ids["components"]
            or not isinstance(step.get("line"), int) or not isinstance(step.get("name"), str)
            for step in flow["steps"]
        ):
            raise ValueError("Invalid flow steps.")
    for machine in bundle["state_machines"]:
        if not isinstance(machine.get("name"), str) or machine.get("component_id") not in ids["components"]:
            raise ValueError("Invalid state machine.")
        if not isinstance(machine.get("states"), list) or any(not isinstance(s, str) for s in machine["states"]):
            raise ValueError("Invalid states.")
        if not isinstance(machine.get("terminal_states"), list) or any(s not in machine["states"] for s in machine["terminal_states"]):
            raise ValueError("Invalid terminal states.")
        if not isinstance(machine.get("transitions"), list) or any(
            not isinstance(t, dict) or t.get("from") not in machine["states"] or t.get("to") not in machine["states"]
            or not isinstance(t.get("event"), str) for t in machine["transitions"]
        ):
            raise ValueError("Invalid transitions.")
    for invariant in bundle["invariants"]:
        check = invariant.get("check")
        if invariant.get("scope") not in ids["components"] or not isinstance(invariant.get("statement"), str):
            raise ValueError("Invalid invariant.")
        if not isinstance(check, dict) or not isinstance(check.get("counterexamples"), list) or not isinstance(check.get("passed"), bool):
            raise ValueError("Invalid bounded check.")
    for candidate in bundle["formal_candidates"]:
        if candidate.get("invariant_id") not in ids["invariants"] or not isinstance(candidate.get("source"), str):
            raise ValueError("Invalid formal candidate.")
        if candidate.get("status") != "proposed" or candidate.get("checker_status") != "not_run":
            raise ValueError("This analyzer only supports unchecked formal candidates.")
    for item in bundle["assumptions"]:
        if item.get("status") not in STATUSES or any(not isinstance(item.get(k), str) for k in ("statement", "rationale", "owner")):
            raise ValueError("Invalid assumption.")
    for route in bundle["interfaces"]:
        if route.get("component_id") not in ids["components"] or not isinstance(route.get("path"), str):
            raise ValueError("Invalid route.")
        if route.get("method") not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            raise ValueError("Invalid route method.")
    if not isinstance(bundle.get("summary"), dict) or not isinstance(bundle.get("diagrams"), dict):
        raise ValueError("Missing summary or diagrams.")
    for key in ("architecture", "sequence"):
        if not isinstance(bundle["diagrams"].get(key), str):
            raise ValueError("Invalid diagram.")
    for key in ("files", "modules", "symbols", "claims", "findings", "routes", "test_modules",
                "directly_referenced_interfaces", "public_interfaces"):
        if not isinstance(bundle["summary"].get(key), int) or bundle["summary"][key] < 0:
            raise ValueError("Invalid summary counts.")
    for key, count in (("files", len(bundle["sources"])), ("claims", len(bundle["claims"])),
                       ("findings", len(bundle["findings"])), ("routes", len(bundle["interfaces"]))):
        if bundle["summary"][key] != count:
            raise ValueError(f"Summary does not match {key}.")
    if not isinstance(bundle["summary"].get("severity"), dict) or any(
        bundle["summary"]["severity"].get(key) != sum(f["severity"] == key for f in bundle["findings"])
        for key in ("high", "medium", "low", "info")
    ):
        raise ValueError("Invalid severity summary.")


def compare_bundles(before: dict, after: dict) -> dict:
    result = {"before": before["id"], "after": after["id"], "changes": {}}
    for key in ("components", "relationships", "claims", "findings"):
        left = {item["id"]: item for item in before[key]}
        right = {item["id"]: item for item in after[key]}
        result["changes"][key] = {
            "added": [right[k] for k in sorted(right.keys() - left.keys())],
            "removed": [left[k] for k in sorted(left.keys() - right.keys())],
            "changed": [{"before": left[k], "after": right[k]} for k in sorted(left.keys() & right.keys())
                        if canonical_json(left[k]) != canonical_json(right[k])],
        }
    left = {s["path"]: s["sha256"] for s in before["sources"]}
    right = {s["path"]: s["sha256"] for s in after["sources"]}
    result["files"] = {
        "added": sorted(right.keys() - left.keys()),
        "removed": sorted(left.keys() - right.keys()),
        "changed": sorted(k for k in left.keys() & right.keys() if left[k] != right[k]),
    }
    return result


def report_markdown(bundle: dict) -> str:
    repo, summary = bundle["repository"], bundle["summary"]
    lines = [
        f"# {repo['name']} — system model", "",
        f"Snapshot: `{bundle['id']}` · commit: `{repo.get('commit_sha') or 'uncommitted'}`",
        f"Content hash: `{repo['content_sha256']}`", "",
        f"{summary['modules']} modules, {summary['symbols']} symbols, "
        f"{summary['claims']} claims, {summary['findings']} findings.", "",
        "## Architecture", "", "```mermaid", bundle["diagrams"]["architecture"], "```", "",
        "## Findings", "",
    ]
    for finding in bundle["findings"]:
        lines += [f"### {finding['severity'].upper()}: {finding['title']}", "",
                  finding["rationale"], "", f"Uncertainty: {finding['uncertainty']}", "",
                  f"Validate: {finding['suggested_validation']}", ""]
    lines += ["## Claim ledger", ""]
    for claim in bundle["claims"]:
        refs = ", ".join(f"{e['reference']}:{e['line_start']}" for e in claim["evidence"])
        lines += [f"- **{claim['status']}** {claim['statement']} ({refs})"]
    lines += ["", "## Analysis boundaries", ""]
    lines += [f"- {item}" for item in bundle["limitations"]]
    return "\n".join(lines) + "\n"
