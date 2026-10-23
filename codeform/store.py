"""Workspace-local persistence; analysis bundles remain immutable."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .model import canonical_json, validate_bundle


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _path(self, identifier: str, suffix: str = ".json") -> Path:
        if not re.fullmatch(r"snapshot_[0-9a-f]{16}", identifier):
            raise ValueError("Invalid snapshot identifier.")
        target = self.path / (identifier + suffix)
        if target.is_symlink():
            raise ValueError("Linked storage files are not supported.")
        return target

    def _write(self, target: Path, value: dict) -> None:
        temporary = target.with_suffix(target.suffix + ".tmp")
        if temporary.is_symlink():
            raise ValueError("Linked storage files are not supported.")
        temporary.write_text(canonical_json(value) + "\n", encoding="utf-8")
        os.replace(temporary, target)

    def save(self, bundle: dict) -> dict:
        validate_bundle(bundle)
        with self.lock:
            target = self._path(bundle["id"])
            if target.exists():
                existing = self.get(bundle["id"])
                # JSON clients may round-trip 1.0 as 1; numeric values remain equal.
                if existing["bundle"] != bundle:
                    raise ValueError("Snapshot identifier collision: existing immutable content differs.")
            else:
                self._write(target, {"created_at": utc_now(), "bundle": bundle})
            return self.get(bundle["id"])

    def get(self, identifier: str) -> dict:
        try:
            record = json.loads(self._path(identifier).read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise KeyError("Snapshot not found.") from error
        validate_bundle(record["bundle"])
        return record

    def list(self) -> list[dict]:
        records = []
        for path in self.path.glob("snapshot_*.json"):
            if path.name.endswith((".annotations.json", ".verification.json")):
                continue
            try:
                record = self.get(path.stem)
                bundle = record["bundle"]
                records.append({"id": bundle["id"], "created_at": record["created_at"],
                                "repository": bundle["repository"], "summary": bundle["summary"]})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, OSError):
                continue
        return sorted(records, key=lambda record: (record["created_at"], record["id"]), reverse=True)

    def annotations(self, identifier: str) -> dict:
        self.get(identifier)
        target = self._path(identifier, ".annotations.json")
        return json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}

    def annotate(self, identifier: str, entity_id: str, status: str, note: str) -> dict:
        if status not in {"open", "accepted", "dismissed", "resolved"}:
            raise ValueError("Invalid review status.")
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError("Notes must contain at most 4000 characters.")
        bundle = self.get(identifier)["bundle"]
        entities = {item["id"] for key in ("findings", "claims", "assumptions", "invariants") for item in bundle[key]}
        if entity_id not in entities:
            raise ValueError("Annotation must reference a model entity.")
        with self.lock:
            annotations = self.annotations(identifier)
            annotations[entity_id] = {"status": status, "note": note, "updated_at": utc_now(), "author": "local reviewer"}
            self._write(self._path(identifier, ".annotations.json"), annotations)
            return annotations[entity_id]

    def verification(self, identifier: str) -> dict | None:
        self.get(identifier)
        target = self._path(identifier, ".verification.json")
        return json.loads(target.read_text(encoding="utf-8")) if target.exists() else None

    def save_verification(self, identifier: str, report: dict) -> None:
        bundle = self.get(identifier)["bundle"]
        if report.get("snapshot_id") != identifier or report.get("repository_content_sha256") != bundle["repository"]["content_sha256"]:
            raise ValueError("Verification report does not match the captured snapshot.")
        with self.lock:
            self._write(self._path(identifier, ".verification.json"), report)

    def _agent_directory(self, identifier: str, kind: str) -> Path:
        self.get(identifier)
        if kind not in {"attempts", "proposals", "reviews"}:
            raise ValueError("Invalid agent record collection.")
        target = self.path / "agents" / identifier / kind
        for part in (target.parent.parent, target.parent, target):
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                raise ValueError("Linked agent storage directories are not supported.")
        return target

    def agent_records(self, identifier: str, kind: str) -> list[dict]:
        target = self._agent_directory(identifier, kind)
        records = []
        prefix = {"attempts": "attempt", "proposals": "proposal", "reviews": "review"}[kind]
        for path in target.glob(f"{prefix}_*.json"):
            records.append(self.agent_record(identifier, kind, path.stem))
        return sorted(records, key=lambda r: (r["created_at"], r["id"]))

    def agent_record(self, identifier: str, kind: str, record_id: str) -> dict:
        directory = self._agent_directory(identifier, kind)
        prefix = {"attempts": "attempt", "proposals": "proposal", "reviews": "review"}[kind]
        if not isinstance(record_id, str) or not re.fullmatch(rf"{prefix}_[0-9a-f]{{16}}", record_id):
            raise ValueError("Invalid agent record identifier.")
        target = directory / f"{record_id}.json"
        if target.is_symlink():
            raise ValueError("Linked agent records are not supported.")
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise KeyError("Agent record not found.") from error
        if record.get("id") != record_id or record.get("snapshot_id") != identifier:
            raise ValueError("Agent record does not match its snapshot and identifier.")
        return record

    def save_agent_record(self, identifier: str, kind: str, record: dict) -> dict:
        directory = self._agent_directory(identifier, kind)
        prefix = {"attempts": "attempt", "proposals": "proposal", "reviews": "review"}[kind]
        record_id = record.get("id")
        if not isinstance(record_id, str) or not re.fullmatch(rf"{prefix}_[0-9a-f]{{16}}", record_id):
            raise ValueError("Invalid agent record identifier.")
        if record.get("snapshot_id") != identifier:
            raise ValueError("Agent record snapshot mismatch.")
        with self.lock:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{record_id}.json"
            if target.exists():
                existing = self.agent_record(identifier, kind, record_id)
                if existing != record:
                    raise ValueError("Immutable agent record already exists with different content.")
                return existing
            self._write(target, record)
            return record


def task_spec(bundle: dict, finding_id: str, annotations: dict) -> dict:
    finding = next((item for item in bundle["findings"] if item["id"] == finding_id), None)
    if not finding:
        raise ValueError("Finding not found.")
    review = annotations.get(finding_id, {})
    if review.get("status") != "accepted":
        raise ValueError("Accept the finding before exporting a task.")
    refs = [e for e in bundle["evidence"] if e["id"] in finding["evidence_ids"]]
    return {
        "schema_version": "1.0.0", "id": "task_" + finding_id.removeprefix("finding_"),
        "title": finding["title"], "finding_id": finding_id, "snapshot_id": bundle["id"],
        "base_commit": bundle["repository"]["commit_sha"],
        "base_content_sha256": bundle["repository"]["content_sha256"],
        "scope": sorted({e["reference"] for e in refs}),
        "problem": finding["rationale"], "uncertainty": finding["uncertainty"],
        "acceptance_criteria": [finding["suggested_validation"],
                                "Add or update a regression test that demonstrates the intended behavior.",
                                "Review the diff and re-analyze the repository against the original snapshot."],
        "suggested_test": finding["suggested_test"], "review_note": review.get("note", ""),
        "execution": {"status": "not_started", "target_code_executed": False,
                      "requires_isolation": True, "allowed_commands": [],
                      "network_access": False, "merge": "human_review", "deployment": False},
        "evidence": refs,
    }
