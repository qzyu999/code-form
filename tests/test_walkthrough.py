import copy
import hashlib
import unittest
from pathlib import Path

from codeform.analyzer import analyze_repository
from codeform.proofs import proof_plan
from codeform.walkthrough import build_walkthrough, simulate_scenario
from workspace import TemporaryWorkspace

ROOT = Path(__file__).resolve().parents[1]


class WalkthroughTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transfer = analyze_repository(ROOT / "examples/verified-transfer")
        cls.workflow = analyze_repository(ROOT / "examples/order-workflow")

    def test_walkthrough_binds_purpose_notation_lean_and_source(self):
        before = copy.deepcopy(self.transfer)
        report = build_walkthrough(self.transfer)
        self.assertEqual("documented", report["purpose"]["status"])
        self.assertEqual("README.md", report["purpose"]["evidence"]["reference"])
        self.assertEqual(2, len(report["models"]))
        for model in report["models"]:
            self.assertTrue(model["state_latex"])
            self.assertTrue(model["transition_latex"])
            self.assertEqual(5, len(model["notation"]))
            self.assertTrue(model["evidence"][0]["source_sha256"])
            for p in model["principles"]:
                self.assertEqual("not_run", p["status"])
                self.assertIn("theorem", p["lean_source"])
                self.assertIn(r"\Longrightarrow", p["latex"])
        self.assertEqual(before, self.transfer)

    def test_checked_support_requires_matching_snapshot_and_lean_input(self):
        artifacts = proof_plan(self.transfer)
        for p in artifacts:
            p["status"] = p["expected_result"]
            p["checker"] = {"source_sha256": hashlib.sha256(p["lean_source"].encode()).hexdigest()}
            p["axioms"] = []
        checked = {"snapshot_id": self.transfer["id"],
                   "repository_content_sha256": self.transfer["repository"]["content_sha256"], "artifacts": artifacts}
        report = build_walkthrough(self.transfer, checked)
        self.assertEqual(4, sum(p["status"] == "proved" for m in report["models"] for p in m["principles"]))
        stale = copy.deepcopy(checked)
        stale["artifacts"][0]["checker"]["source_sha256"] = "0" * 64
        actual = build_walkthrough(self.transfer, stale)
        self.assertEqual("not_run", actual["models"][0]["principles"][0]["status"])
        stale["snapshot_id"] = "snapshot_" + "0" * 16
        actual = build_walkthrough(self.transfer, stale)
        self.assertTrue(all(p["status"] == "not_run" for m in actual["models"] for p in m["principles"]))

    def _scenario(self, guarded, inputs):
        model = next(m for m in build_walkthrough(self.transfer)["models"] if m["guarded"] == guarded)
        return simulate_scenario(self.transfer, {"model_id": model["id"], "inputs": inputs})

    def test_transfer_examples_expose_counterexample_and_rejected_repair(self):
        inputs = {"source": "10", "destination": "0", "amount": "11"}
        faulty = self._scenario(False, inputs)
        self.assertEqual(["-1", "11"], faulty["output"])
        self.assertTrue(faulty["checks"][0]["holds"])
        self.assertFalse(faulty["checks"][1]["holds"])
        self.assertTrue(faulty["checks"][1]["applicable"])
        repaired = self._scenario(True, inputs)
        self.assertEqual("rejected", repaired["outcome"])
        self.assertIsNone(repaired["output"])
        self.assertEqual([], repaired["checks"])
        for result in (faulty, repaired):
            self.assertFalse(result["proved"])
            self.assertFalse(result["target_executed"])

    def test_integer_examples_are_exact_and_failed_assumptions_are_visible(self):
        big = "1" + "0" * 60
        result = self._scenario(True, {"source": big, "destination": "0", "amount": "1"})
        self.assertEqual(str(int(big) - 1), result["output"][0])
        outside = self._scenario(True, {"source": "10", "destination": "-5", "amount": "1"})
        self.assertFalse(outside["assumptions_hold"])
        self.assertFalse(outside["checks"][1]["applicable"])
        for bad in ("1.5", "not an integer", True, 1.5):
            with self.assertRaises(ValueError):
                self._scenario(True, {"source": bad, "destination": "0", "amount": "1"})

    def test_workflow_uses_model_convention_and_validates_event_domain(self):
        model = build_walkthrough(self.workflow)["models"][0]
        result = simulate_scenario(self.workflow, {"model_id": model["id"], "inputs": {"state": "cancelled", "events": ["reopen"]}})
        self.assertEqual("pending", result["output"])
        self.assertEqual([{"from": "cancelled", "event": "reopen", "to": "pending"}], result["counterexamples"])
        identity = simulate_scenario(self.workflow, {"model_id": model["id"], "inputs": {"state": "shipped", "events": ["pay"]}})
        self.assertEqual("shipped", identity["output"])
        self.assertIn("runtime may reject", identity["trace"][-1]["detail"])
        with self.assertRaises(ValueError):
            simulate_scenario(self.workflow, {"model_id": model["id"], "inputs": {"state": "pending", "events": ["unmodeled"]}})
        with self.assertRaises(ValueError):
            simulate_scenario(self.workflow, {"model_id": model["id"], "inputs": {"state": "pending", "events": ["pay"] * 33}})

    def test_unsupported_repository_reports_documented_requirements_without_inventing_models(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            (root / "main.py").write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
            (root / "README.md").write_text("# Product\n\nA product with an explicitly documented purpose.\n", encoding="utf-8")
            (root / "docs/requirements").mkdir(parents=True)
            (root / "docs/requirements/safety.md").write_text(
                "### SAFE-001: Preserve state\n\nMUST: State remains valid.\n\n- Status: implemented\n", encoding="utf-8")
            bundle = analyze_repository(root)
            report = build_walkthrough(bundle)
            self.assertEqual([], report["models"])
            self.assertEqual("semantic reconstruction unavailable", report["model_status"])
            self.assertEqual("documented", report["requirements"][0]["status"])
            self.assertEqual("implemented", report["requirements"][0]["declared_status"])
            self.assertIn("documented purpose", report["purpose"]["text"])
            with self.assertRaises(KeyError):
                simulate_scenario(bundle, {"model_id": "unknown", "inputs": {}})
