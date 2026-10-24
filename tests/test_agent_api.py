import copy
import threading
import unittest
from pathlib import Path

from codeform.analyzer import analyze_repository
from codeform.client import ApiError, CodeFormClient
from codeform.proofs import _check_generated, checker_info, find_lean, proof_plan
from codeform.server import Application, make_server
from codeform.store import Store
from workspace import TemporaryWorkspace

ROOT = Path(__file__).resolve().parents[1]


class AgentApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryWorkspace()
        self.app = Application(ROOT, Path(self.temporary.name))
        self.server = make_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = CodeFormClient(f"http://127.0.0.1:{self.server.server_port}")
        self.bundle = analyze_repository(ROOT / "examples/verified-transfer")
        self.app.store.save(self.bundle)
        self.snapshot = self.bundle["id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.close()
        self.thread.join()
        self.temporary.cleanup()

    def test_client_discovery_evidence_context_and_openapi(self):
        caps = self.client.capabilities()
        self.assertEqual("1.0.0", caps["api_version"])
        self.assertIn("attempt_proof", caps["operations"])
        context = self.client.context(self.snapshot)
        self.assertEqual("reasoning-agent-v1", context["prompt_version"])
        self.assertIn("Never weaken", context["instructions"])
        goals = self.client.obligations(self.snapshot)["obligations"]
        self.assertEqual(6, len(goals))
        self.assertTrue(all(g["sha256"] and g["declaration"].startswith("theorem ") for g in goals))
        source = self.client.source(self.snapshot, "transfer.py", 4, 8)
        self.assertTrue(source["captured"])
        self.assertIn("transfer_unchecked", source["content"])
        spec = self.client.openapi()
        self.assertEqual("3.1.0", spec["openapi"])
        self.assertIn("/api/v1/snapshots/{snapshot_id}/attempts", spec["paths"])
        operations = []
        for path, methods in spec["paths"].items():
            for operation in methods.values():
                operations.append(operation["operationId"])
                declared = {p["name"] for p in operation["parameters"] if p["in"] == "path"}
                for required in ("snapshot_id", "job_id", "attempt_id", "proposal_id"):
                    if "{" + required + "}" in path:
                        self.assertIn(required, declared)
        self.assertEqual(len(operations), len(set(operations)))
        self.assertIn("Obligation", spec["components"]["schemas"])
        self.assertIn("Attempt", spec["components"]["schemas"])
        self.assertEqual(self.bundle, self.client.snapshot(self.snapshot)["bundle"])
        with self.assertRaises(ApiError) as outside:
            self.client.source(self.snapshot, "../../README.md")
        self.assertEqual(404, outside.exception.status)

    def test_proposal_review_history_is_separate_from_snapshot_and_proof(self):
        goal = self.client.obligations(self.snapshot)["obligations"][0]
        payload = {
            "kind": "requirement", "title": "Review transfer safety",
            "rationale": "Business intent must be reviewed.", "content": "Successful transfer balances should be nonnegative.",
            "evidence": [{"path": "transfer.py", "line_start": 4, "line_end": 8}],
            "agent": "test agent", "obligation_id": goal["id"],
        }
        proposal = self.client.propose(self.snapshot, payload)
        self.assertFalse(proposal["checked"])
        self.assertFalse(proposal["applied"])
        self.client.review(self.snapshot, proposal["id"], "needs_changes", "Specify rejection behavior.", "local reviewer")
        self.client.review(self.snapshot, proposal["id"], "accepted", "Accepted as intent, not as proof.", "local reviewer")
        records = self.client.proposals(self.snapshot)
        self.assertEqual("accepted", records[0]["review"]["decision"])
        self.assertEqual(2, len(self.client.reviews(self.snapshot, proposal["id"])))
        reopened = Store(Path(self.temporary.name))
        self.assertEqual(2, len(reopened.agent_records(self.snapshot, "reviews")))
        self.assertEqual(self.bundle, reopened.get(self.snapshot)["bundle"])
        self.assertIsNone(reopened.verification(self.snapshot))
        bad = {**payload, "evidence": [{"path": "transfer.py", "line_start": 1, "line_end": 99999}]}
        with self.assertRaises(ApiError) as error:
            self.client.propose(self.snapshot, bad)
        self.assertEqual(400, error.exception.status)
        bad = {**payload, "status": "proved"}
        with self.assertRaises(ApiError):
            self.client.propose(self.snapshot, bad)

    def test_unknown_proof_fields_and_obligation_hash_are_rejected(self):
        goal = self.client.obligations(self.snapshot)["obligations"][0]
        base = f"/api/v1/snapshots/{self.snapshot}/attempts"
        for payload in (
            {"obligation_id": goal["id"], "obligation_sha256": "0" * 64, "strategy": "generated"},
            {"obligation_id": goal["id"], "obligation_sha256": goal["sha256"], "proof": "by trivial"},
            {"obligation_id": goal["id"], "obligation_sha256": goal["sha256"], "strategy": "unsafe"},
        ):
            with self.assertRaises(ApiError) as error:
                self.client._request(base, payload)
            self.assertEqual(400, error.exception.status)
        self.assertEqual([], self.client.attempts(self.snapshot))

    def test_walkthrough_and_scenarios_use_captured_models_only(self):
        report = self.client.walkthrough(self.snapshot)
        self.assertEqual(self.snapshot, report["snapshot_id"])
        model = next(m for m in report["models"] if not m["guarded"])
        example = self.client.scenario(self.snapshot, model["id"], {"source": "10", "destination": "0", "amount": "11"})
        self.assertEqual(["-1", "11"], example["output"])
        self.assertFalse(example["proved"])
        self.assertFalse(example["target_executed"])
        self.assertEqual(self.bundle, self.client.snapshot(self.snapshot)["bundle"])
        with self.assertRaises(ApiError) as rejected:
            self.client.scenario(self.snapshot, model["id"], {"source": 0.1, "destination": "0", "amount": "1"})
        self.assertEqual(400, rejected.exception.status)
        with self.assertRaises(ApiError):
            self.client._request(f"/api/v1/snapshots/{self.snapshot}/scenarios",
                                 {"model_id": model["id"], "inputs": {}, "execute": True})

    def test_versioned_mutations_require_token_and_origin_check(self):
        self.client.token = ""
        with self.assertRaises(ApiError) as error:
            self.client.analyze("examples/verified-transfer")
        self.assertEqual(403, error.exception.status)
        self.client.token = None
        job = self.client.wait(self.client.analyze("examples/verified-workflow"))
        self.assertEqual("complete", job["status"])
        with self.assertRaises(ValueError):
            CodeFormClient("https://example.invalid")
        with self.assertRaises(ValueError):
            CodeFormClient("http://127.0.0.1:7332/api")

    @unittest.skipUnless(checker_info(find_lean())["available"], "Pinned Lean is optional.")
    def test_real_attempt_failure_retry_and_idempotency(self):
        goal = next(o for o in self.client.obligations(self.snapshot)["obligations"]
                    if o["property"] == "conservation" and o["name"].endswith("guarded"))
        first_job = self.client.wait(self.client.submit_attempt(self.snapshot, goal, "simplify", "test agent", "first"))
        first = self.client.attempt(self.snapshot, first_job["attempt_id"])
        self.assertEqual("error", first["status"])
        self.assertIn("error:", first["checker"]["stdout"])
        self.assertNotEqual(0, first["checker"]["exit_code"])
        second_job = self.client.wait(self.client.submit_attempt(self.snapshot, goal, "generated", "test agent", "second"))
        second = self.client.attempt(self.snapshot, second_job["attempt_id"])
        self.assertEqual("proved", second["status"])
        self.assertTrue(second["checker"]["declaration_verified"])
        self.assertEqual(goal["sha256"], second["checker"]["obligation_sha256"])
        reused = self.client.submit_attempt(self.snapshot, goal, "generated", "test agent", "second")
        self.assertTrue(reused["reused"])
        self.assertEqual(2, len(self.client.attempts(self.snapshot)))
        with self.assertRaises(ApiError):
            self.client.submit_attempt(self.snapshot, goal, "decide", "test agent", "second")
        self.assertIsNone(self.app.store.verification(self.snapshot))
        self.assertFalse(second["promoted_to_verification"])
        bad_goal = next(o for o in self.client.obligations(self.snapshot)["obligations"]
                        if o["property"] == "nonnegative" and o["name"].endswith("unchecked"))
        witness_job = self.client.wait(self.client.submit_attempt(self.snapshot, bad_goal))
        witness = self.client.attempt(self.snapshot, witness_job["attempt_id"])
        self.assertEqual("disproved", witness["status"])
        self.assertTrue(witness["counterexample"]["checked"])
        with self.assertRaises(ValueError):
            self.app.store.save_agent_record(self.snapshot, "attempts", {**second, "status": "disproved"})


class ObligationBindingTests(unittest.TestCase):
    def test_unrelated_theorem_or_changed_hypothesis_is_never_accepted(self):
        bundle = analyze_repository(ROOT / "examples/verified-transfer")
        artifact = proof_plan(bundle)[0]
        for source in (
            "import Std\ntheorem unrelated : True := by trivial\n#print axioms unrelated\n",
            artifact["lean_source"].replace("x + y = s + d", "True"),
            artifact["lean_source"].replace("  unfold transfer at h", "  sorry"),
        ):
            with TemporaryWorkspace() as temporary:
                result = _check_generated({**artifact, "lean_source": source}, None, {}, Path(temporary))
                self.assertEqual("error", result["status"])
        another = copy.deepcopy(bundle)
        another["id"] = "snapshot_" + "0" * 16
        self.assertNotEqual(proof_plan(bundle)[0]["obligation"]["sha256"],
                            proof_plan(another)[0]["obligation"]["sha256"])
