import copy
import subprocess
import unittest
from pathlib import Path

from codeform.analyzer import analyze_repository
from codeform.model import canonical_json, compare_bundles, validate_bundle
from codeform.store import Store, task_spec
from workspace import TemporaryWorkspace

ROOT = Path(__file__).resolve().parents[1]


class AnalyzerTests(unittest.TestCase):
    def test_examples_have_expected_findings_and_valid_evidence(self):
        cases = {
            "payment-service": {"documented-route-gap", "test-gap", "swallowed-exception"},
            "order-workflow": {"terminal-transition"},
            "cyclic-service": {"import-cycle", "test-gap", "swallowed-exception"},
        }
        for example, expected in cases.items():
            with self.subTest(example=example):
                bundle = analyze_repository(ROOT / "examples" / example)
                validate_bundle(bundle)
                self.assertTrue(expected.issubset({f["rule"] for f in bundle["findings"]}))
                self.assertFalse(any(c["status"] in {"tested", "proved"} for c in bundle["claims"]))
                self.assertTrue(all(c["evidence"] for c in bundle["claims"]))
        self.assertEqual(2, len(analyze_repository(ROOT / "examples/payment-service")["interfaces"]))

    def test_repeat_runs_are_identical(self):
        path = ROOT / "examples/order-workflow"
        self.assertEqual(canonical_json(analyze_repository(path)), canonical_json(analyze_repository(path)))

    def test_target_code_is_never_executed_and_sensitive_files_are_excluded(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            marker = root / "executed"
            (root / "danger.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('oops')\ndef safe():\n    return 1\n")
            (root / ".env").write_text("TOKEN=example")
            (root / "credentials.txt").write_text("example-secret")
            (root / ".aws").mkdir()
            (root / ".aws" / "settings.py").write_text("SECRET = 'example'")
            (root / "huge.py").write_text("#" * 256_001)
            bundle = analyze_repository(root)
            self.assertFalse(marker.exists())
            self.assertEqual(["danger.py"], [source["path"] for source in bundle["sources"]])
            self.assertTrue(any(s["path"] == "credentials.txt" for s in bundle["skipped_files"]))

    def test_syntax_errors_are_evidence_linked_findings(self):
        with TemporaryWorkspace() as temporary:
            (Path(temporary) / "broken.py").write_text("def broken(:\n    pass\n")
            bundle = analyze_repository(temporary)
            self.assertEqual("parse-error", bundle["findings"][0]["rule"])
            validate_bundle(bundle)

    def test_import_aliases_relative_imports_and_local_calls(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            (root / "src" / "pkg").mkdir(parents=True)
            (root / "src/pkg/__init__.py").write_text("")
            (root / "src/pkg/a.py").write_text("from .b import helper as assist\n\ndef run():\n    return assist()\n")
            (root / "src/pkg/b.py").write_text("def helper():\n    return 2\n")
            (root / "tests").mkdir()
            (root / "tests/test_a.py").write_text("from pkg.a import run as execute\n\ndef test_run():\n    assert execute() == 2\n")
            bundle = analyze_repository(root)
            by_id = {c["id"]: c["name"] for c in bundle["components"]}
            calls = [(by_id[r["source"]], by_id[r["target"]], r["kind"]) for r in bundle["relationships"]]
            self.assertIn(("pkg.a.run", "pkg.b.helper", "calls"), calls)
            self.assertIn(("tests.test_a.test_run", "pkg.a.run", "tests"), calls)
            ref_claim = next(c for c in bundle["claims"] if c["statement"] == "A test function directly references pkg.a.run.")
            self.assertTrue(any(e["reference"] == "tests/test_a.py" for e in ref_claim["evidence"]))

    def test_repeated_imports_and_handlers_preserve_all_evidence(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            (root / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
            (root / "main.py").write_text(
                "from helper import helper\n"
                "def run():\n"
                "    from helper import helper\n"
                "    try:\n"
                "        helper()\n"
                "    except Exception:\n"
                "        pass\n"
                "    try:\n"
                "        helper()\n"
                "    except Exception:\n"
                "        pass\n", encoding="utf-8")
            bundle = analyze_repository(root)
            validate_bundle(bundle)
            claim = next(c for c in bundle["claims"] if c["statement"] == "main imports helper.helper.")
            self.assertEqual([1, 3], [e["line_start"] for e in claim["evidence"]])
            finding = next(f for f in bundle["findings"] if f["rule"] == "swallowed-exception")
            self.assertEqual(2, len(finding["evidence_ids"]))
            edge = next(r for r in bundle["relationships"] if r["kind"] == "imports")
            self.assertEqual(2, len(edge["evidence_ids"]))
            call_edge = next(r for r in bundle["relationships"] if r["kind"] == "calls")
            self.assertEqual(2, len(call_edge["evidence_ids"]))

    def test_model_counterexample_and_snapshot_comparison(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            source = (ROOT / "examples/order-workflow/workflow.py").read_text()
            (root / "workflow.py").write_text(source)
            before = analyze_repository(root)
            self.assertFalse(before["invariants"][0]["check"]["passed"])
            self.assertIn("sorry", before["formal_candidates"][0]["source"])
            self.assertEqual("not_run", before["formal_candidates"][0]["checker_status"])
            (root / "workflow.py").write_text(source.replace('    ("cancelled", "reopen"): "pending",\n', ""))
            after = analyze_repository(root)
            self.assertTrue(after["invariants"][0]["check"]["passed"])
            diff = compare_bundles(before, after)
            self.assertEqual(["workflow.py"], diff["files"]["changed"])
            self.assertTrue(any(f["rule"] == "terminal-transition" for f in diff["changes"]["findings"]["removed"]))
            self.assertEqual(before["components"][0]["id"], after["components"][0]["id"])

    def test_import_validation_rejects_tampered_evidence_and_paths(self):
        original = analyze_repository(ROOT / "examples/order-workflow")
        for mutate in (
            lambda b: b["sources"][0].update(path="../outside.py"),
            lambda b: b["sources"][0].update(content="tampered"),
            lambda b: b["claims"][0]["evidence"][0].update(line_end=999999),
            lambda b: b["relationships"][0].update(target="missing"),
            lambda b: b["findings"][0].update(evidence_ids=["missing"]),
            lambda b: b.update(components=[None]),
            lambda b: b["summary"].update(files=999),
            lambda b: b["repository"].update(content_sha256="0" * 64),
            lambda b: b["formal_candidates"][0].update(status="proved", checker_status="passed"),
        ):
            bundle = copy.deepcopy(original)
            mutate(bundle)
            with self.assertRaises(ValueError):
                validate_bundle(bundle)

    def test_store_keeps_original_source_and_requires_accepted_tasks(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            (root / "module.py").write_text("def public():\n    return 1\n")
            store = Store(root / ".codeform")
            bundle = analyze_repository(root)
            store.save(bundle)
            round_tripped = copy.deepcopy(bundle)
            round_tripped["claims"][0]["confidence"] = 1
            store.save(round_tripped)
            (root / "module.py").write_text("def public():\n    return 2\n")
            self.assertIn("return 1", store.get(bundle["id"])["bundle"]["sources"][0]["content"])
            finding_id = bundle["findings"][0]["id"]
            with self.assertRaises(ValueError):
                task_spec(bundle, finding_id, store.annotations(bundle["id"]))
            store.annotate(bundle["id"], finding_id, "accepted", "Exercise the return contract.")
            task = task_spec(bundle, finding_id, store.annotations(bundle["id"]))
            self.assertEqual(["module.py"], task["scope"])
            self.assertFalse(task["execution"]["target_code_executed"])
            self.assertEqual(1, len(store.list()))
            self.assertEqual("accepted", Store(root / ".codeform").annotations(bundle["id"])[finding_id]["status"])
            altered = copy.deepcopy(bundle)
            altered["limitations"].append("Different bundle with the same ID")
            with self.assertRaises(ValueError):
                store.save(altered)

    def test_snapshot_cache_is_copy_safe_and_revalidates_changed_content(self):
        with TemporaryWorkspace() as temporary:
            store = Store(Path(temporary))
            bundle = analyze_repository(ROOT / "examples/order-workflow")
            store.save(bundle)
            mutable = store.get(bundle["id"])
            mutable["bundle"]["claims"][0]["statement"] = "Changed only in caller copy"
            self.assertNotEqual(mutable, store.get(bundle["id"]))
            path = store.path / f"{bundle['id']}.json"
            import json
            record = json.loads(path.read_text(encoding="utf-8"))
            record["bundle"]["sources"][0]["content"] = "tampered"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.get(bundle["id"])

    def test_git_commit_and_working_tree_content_are_separate(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "module.py").write_text("def public():\n    return 1\n")
            subprocess.run(["git", "-C", str(root), "add", "module.py"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture"], check=True)
            before = analyze_repository(root)
            (root / "module.py").write_text("def public():\n    return 2\n")
            after = analyze_repository(root)
            self.assertEqual(before["repository"]["commit_sha"], after["repository"]["commit_sha"])
            self.assertNotEqual(before["id"], after["id"])
            self.assertTrue(after["repository"]["dirty"])

    def test_subdirectory_snapshot_ignores_unrelated_git_changes(self):
        with TemporaryWorkspace() as temporary:
            parent = Path(temporary)
            target = parent / "project"
            target.mkdir()
            (target / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(parent)], check=True)
            subprocess.run(["git", "-C", str(parent), "add", "project/main.py"], check=True)
            subprocess.run(["git", "-C", str(parent), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture"], check=True)
            before = analyze_repository(target)
            (parent / "unrelated.txt").write_text("outside analysis scope", encoding="utf-8")
            after = analyze_repository(target)
            self.assertEqual(canonical_json(before), canonical_json(after))
            (target / "unsupported.bin").write_bytes(b"untracked metadata change")
            dirty = analyze_repository(target)
            self.assertTrue(dirty["repository"]["dirty"])
            self.assertEqual(before["repository"]["content_sha256"], dirty["repository"]["content_sha256"])
            self.assertNotEqual(before["id"], dirty["id"])
            store = Store(parent / ".codeform")
            store.save(before)
            store.save(dirty)


if __name__ == "__main__":
    unittest.main()
