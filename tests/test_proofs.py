import copy
import unittest
from pathlib import Path

from codeform.analyzer import analyze_repository
from codeform.proofs import (
    _check_generated, _transfer_shape, checker_info, find_lean, proof_plan, verify_bundle,
)
from codeform.store import Store
from workspace import TemporaryWorkspace

ROOT = Path(__file__).resolve().parents[1]


class ProofPlanTests(unittest.TestCase):
    def test_entire_transfer_function_must_match_semantics(self):
        valid = """def transfer(source, destination, amount):
    if amount <= 0:
        raise ValueError("positive")
    return source - amount, destination + amount
"""
        self.assertFalse(_transfer_shape(valid, "transfer")[0])
        invalid_sources = [
            valid.replace("source - amount", "source + amount"),
            valid.replace('    return', '    print("side effect")\n    return'),
            valid.replace("if amount <= 0:", "if amount < 0:"),
            valid.replace('raise ValueError("positive")', "pass"),
            "import os\n" + valid,
            "ValueError = RuntimeError\n" + valid,
            "def ValueError(message):\n    return RuntimeError(message)\n" + valid,
            valid.replace("def transfer", "@wrapper\ndef transfer"),
        ]
        for source in invalid_sources:
            with self.subTest(source=source), self.assertRaises(ValueError):
                _transfer_shape(source, "transfer")

    def test_plans_have_no_placeholder_and_preserve_contract(self):
        bundle = analyze_repository(ROOT / "examples/verified-transfer")
        plans = proof_plan(bundle)
        self.assertEqual(6, len(plans))
        self.assertEqual(4, sum(p["expected_result"] == "proved" for p in plans))
        self.assertEqual(2, sum(p["expected_result"] == "disproved" for p in plans))
        for plan in plans:
            self.assertEqual("not_run", plan["status"])
            self.assertNotIn("sorry", plan["lean_source"])
            self.assertIn("#print axioms", plan["lean_source"])
            self.assertTrue(plan["evidence"][0]["source_sha256"])
            self.assertEqual("established", plan["feasibility"]["status"])
        for property_name in ("conservation", "nonnegative", "safety"):
            statements = {p["statement"] for p in plans if p["property"] == property_name}
            self.assertEqual(1, len(statements), "The guard repair must not weaken the contract.")
        safety = next(p for p in plans if p["name"].endswith("guarded") and p["property"] == "safety")
        self.assertEqual(2, len(safety["dependencies"]))
        conservation = next(p for p in plans if p["name"].endswith("unchecked") and p["property"] == "conservation")
        self.assertEqual("Model the outcome", conservation["reasoning"][0]["title"])

    def test_missing_checker_never_proves_anything(self):
        with TemporaryWorkspace() as temporary:
            report = verify_bundle(analyze_repository(ROOT / "examples/verified-transfer"), None, Path(temporary))
            self.assertEqual(6, report["summary"]["not_run"])
            self.assertEqual(0, report["summary"]["proved"])
            self.assertFalse(report["checker"]["available"])
            self.assertTrue(all(not p.get("counterexample") or not p["counterexample"]["checked"] for p in report["artifacts"]))

    def test_workflow_proof_inducts_over_arbitrary_event_sequences(self):
        plan = proof_plan(analyze_repository(ROOT / "examples/verified-workflow"))[0]
        self.assertIn("induction es", plan["lean_source"])
        self.assertEqual("finite-abstract-model", plan["scope"])
        self.assertIn("identity", " ".join(a["statement"] for a in plan["assumptions"]).replace("unchanged", "identity"))

    def test_invalid_contracts_fail_explicitly(self):
        with TemporaryWorkspace() as temporary:
            root = Path(temporary)
            (root / "transfer.py").write_text((ROOT / "examples/verified-transfer/transfer.py").read_text(), encoding="utf-8")
            for contract in (
                'schema_version="1.0.0"\nadapter="integer-transfer-v1"\n[[contracts]]\nfunction="transfer.transfer_guarded"\nproperties=[["invalid"]]',
                'schema_version="1.0.0"\nadapter="integer-transfer-v1"\n[[contracts]]\nfunction=12\nproperties=["safety"]',
                'schema_version="1.0.0"\nadapter="unrecognized"\ncontracts=[]',
            ):
                (root / "contracts.toml").write_text(contract, encoding="utf-8")
                plans = proof_plan(analyze_repository(root))
                self.assertEqual("unsupported", plans[0]["status"])


@unittest.skipUnless(checker_info(find_lean())["available"], "Pinned Lean 4.19.0 is optional; install it to run proof integration tests.")
class LeanIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryWorkspace()
        cls.executable = find_lean()
        cls.info = checker_info(cls.executable)
        cls.bundle = analyze_repository(ROOT / "examples/verified-transfer")
        cls.report = verify_bundle(cls.bundle, cls.executable, Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_lean_checks_positive_and_negative_obligations(self):
        self.assertEqual(4, self.report["summary"]["proved"])
        self.assertEqual(2, self.report["summary"]["disproved"])
        self.assertEqual(0, self.report["summary"]["error"])
        for artifact in self.report["artifacts"]:
            self.assertEqual(0, artifact["checker"]["exit_code"])
            self.assertNotIn("sorryAx", artifact["axioms"])
            self.assertTrue(set(artifact["axioms"]) <= {"propext", "Quot.sound", "Classical.choice"})
            if artifact["counterexample"]:
                self.assertTrue(artifact["counterexample"]["checked"])

    def test_false_theorem_and_incomplete_proof_are_rejected(self):
        original = self.report["artifacts"][0]
        for source in (
            "import Std\ntheorem incomplete : False := by sorry\n#print axioms incomplete\n",
            "import Std\ntheorem false_arithmetic : (1 : Int) = 2 := by omega\n#print axioms false_arithmetic\n",
            "import Std\naxiom invented : False\ntheorem hidden : False := invented\n#print axioms hidden\n",
        ):
            artifact = {**original, "lean_source": source}
            result = _check_generated(artifact, self.executable, self.info, Path(self.temporary.name))
            self.assertEqual("error", result["status"])

    def test_workflow_induction_is_checked_by_lean(self):
        report = verify_bundle(analyze_repository(ROOT / "examples/verified-workflow"),
                               self.executable, Path(self.temporary.name))
        self.assertEqual(1, report["summary"]["proved"])
        self.assertEqual([], report["artifacts"][0]["axioms"])

    def test_verification_is_saved_separately_from_immutable_snapshot(self):
        store = Store(Path(self.temporary.name) / "store")
        store.save(self.bundle)
        store.save_verification(self.bundle["id"], self.report)
        self.assertEqual(4, store.verification(self.bundle["id"])["summary"]["proved"])
        self.assertEqual(1, len(store.list()))
        self.assertEqual(self.bundle, store.get(self.bundle["id"])["bundle"])
        bad = copy.deepcopy(self.report)
        bad["repository_content_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            store.save_verification(self.bundle["id"], bad)
