import copy
import threading
import unittest
from pathlib import Path

from codeform.analyzer import analyze_repository
from codeform.server import Application
from codeform.proofs import checker_info, find_lean
from codeform.workflows import WorkflowService, template, validate_dag
from workspace import TemporaryWorkspace

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryWorkspace()
        self.app = Application(ROOT, Path(self.temporary.name))
        self.bundle = analyze_repository(ROOT / "examples/verified-transfer")
        self.app.store.save(self.bundle)
        self.snapshot = self.bundle["id"]
        self.service = self.app.workflows
        self.run = self.service.create(self.snapshot, {"objective": "Review transfer integrity and its source/model boundary."})

    def tearDown(self):
        self.app.close()
        self.temporary.cleanup()

    def output(self, node, **extra):
        context = self.service.context(self.snapshot, self.run["id"], node)
        payload = {
            "snapshot_id": self.snapshot, "spec_sha256": context["spec_sha256"],
            "input_sha256": context["input_sha256"], "actor": "fixture external agent",
            "summary": "Source-linked fixture analysis; no runtime proof is asserted.",
            "claims": [{"statement": "The transfer update subtracts from source and adds to destination.",
                        "status": "observed", "evidence": [{"path": "transfer.py", "line_start": 4, "line_end": 8}]}],
            "limitations": ["Only the exact adapter semantics are supported."], **extra,
        }
        return self.service.complete(self.snapshot, self.run["id"], node, payload)

    def review(self, node, decision="approved"):
        run = self.service.get(self.snapshot, self.run["id"])
        definition = next(n for n in run["nodes"] if n["id"] == node)
        artifact = next(n for n in run["nodes"] if n["id"] == definition["depends_on"][0])["artifact"]
        return self.service.review(self.snapshot, run["id"], node, {
            "snapshot_id": self.snapshot, "spec_sha256": run["spec_sha256"],
            "artifact_id": artifact["id"], "artifact_sha256": artifact["sha256"],
            "actor": "fixture reviewer", "decision": decision, "note": "Fixture review of the exact draft, not proof or deployment approval.",
        })

    def test_dag_validation_rejects_cycles_and_missing_dependencies(self):
        nodes = template()
        self.assertLess(validate_dag(nodes).index("facts"), validate_dag(nodes).index("model"))
        cyclic = copy.deepcopy(nodes)
        cyclic[0]["depends_on"] = ["synthesis"]
        with self.assertRaises(ValueError):
            validate_dag(cyclic)
        missing = copy.deepcopy(nodes)
        missing[0]["depends_on"] = ["missing"]
        with self.assertRaises(ValueError):
            validate_dag(missing)

    def test_initial_tasks_execute_in_parallel_and_stop_at_external_model(self):
        barrier = threading.Barrier(2)
        original = self.service._builtin
        participants = []
        def synchronized(run, node):
            if node in {"facts", "requirements"}:
                participants.append(threading.current_thread().name)
                barrier.wait(timeout=3)
            return original(run, node)
        self.service._builtin = synchronized
        result = self.service.advance(self.snapshot, self.run["id"])
        self.assertEqual(2, len(set(participants)))
        self.assertEqual(["model"], result["parallel_ready"])
        self.assertEqual("awaiting_agent", result["state"])
        self.assertEqual(4, len(result["events"]))
        self.assertTrue(all(n["status"] == "complete" for n in result["nodes"] if n["id"] in {"facts", "requirements"}))

    def test_gates_input_hashes_and_immutable_outputs(self):
        with self.assertRaises(ValueError):
            self.output("model")
        stale = self.service.context(self.snapshot, self.run["id"], "model")
        self.service.advance(self.snapshot, self.run["id"])
        context = self.service.context(self.snapshot, self.run["id"], "model")
        self.assertNotEqual(stale["input_sha256"], context["input_sha256"])
        for field in ("snapshot_id", "spec_sha256", "input_sha256"):
            with self.assertRaises(ValueError):
                self.output("model", **{field: "wrong"})
        self.output("model")
        with self.assertRaises(ValueError):
            self.output("model")
        before_review = self.service.get(self.snapshot, self.run["id"])
        self.assertEqual("awaiting_review", before_review["state"])
        self.assertEqual("blocked", next(n for n in before_review["nodes"] if n["id"] == "architecture")["status"])
        released = self.review("model_review")
        self.assertTrue({"architecture", "formalization"} <= set(released["parallel_ready"]))
        with self.assertRaises(ValueError):
            self.review("model_review")
        self.assertEqual(self.bundle, self.app.store.get(self.snapshot)["bundle"])

    def test_synthesis_preserves_unknowns_and_does_not_execute_tests(self):
        self.service.advance(self.snapshot, self.run["id"])
        self.output("model")
        self.review("model_review")
        self.output("architecture")
        goal = self.app.agents.obligations(self.snapshot)["obligations"][0]
        self.output("formalization", obligation_ids=[goal["id"]])
        ready = self.service.get(self.snapshot, self.run["id"])
        self.assertTrue({"proof", "counterexample", "tests"} <= set(ready["parallel_ready"]))
        for node in ("proof", "counterexample", "tests"):
            self.output(node, test_plan=["Exercise the stated counterexample without weakening its contract."] if node == "tests" else [])
        result = self.service.advance(self.snapshot, self.run["id"])
        validation = next(n for n in result["nodes"] if n["id"] == "validation")["artifact"]["content"]
        self.assertEqual([], validation["checked_attempts"])
        self.assertEqual([goal["id"]], validation["unverified_selected_obligations"])
        self.assertFalse(validation["target_tests_executed"])
        synthesis = next(n for n in result["nodes"] if n["id"] == "synthesis")["artifact"]["content"]
        self.assertTrue(synthesis["unresolved"])
        self.assertFalse(synthesis["source_changes"])
        self.assertEqual("awaiting_review", result["state"])
        final = self.review("solution_review")
        self.assertEqual("complete", final["state"])
        self.assertFalse(final["execution_policy"]["target_code_executed"])
        reopened = WorkflowService(self.app).get(self.snapshot, final["id"])
        self.assertEqual("complete", reopened["state"])
        self.assertEqual(final["events"], reopened["events"])

    def test_prose_cannot_assert_proofs_and_review_requires_exact_artifact(self):
        self.service.advance(self.snapshot, self.run["id"])
        with self.assertRaises(ValueError):
            self.output("model", claims=[{"statement": "Everything is correct.", "status": "proved",
                                          "evidence": [{"path": "transfer.py", "line_start": 4, "line_end": 8}]}])
        self.output("model")
        run = self.service.get(self.snapshot, self.run["id"])
        artifact = next(n for n in run["nodes"] if n["id"] == "model")["artifact"]
        with self.assertRaises(ValueError):
            self.service.review(self.snapshot, run["id"], "model_review", {
                "snapshot_id": self.snapshot, "spec_sha256": run["spec_sha256"],
                "artifact_id": artifact["id"], "artifact_sha256": "wrong", "actor": "fixture reviewer",
                "decision": "approved", "note": "Wrong artifact must fail.",
            })
        rejected = self.review("model_review", "needs_changes")
        self.assertEqual("needs_changes", rejected["state"])
        child = self.service.create(self.snapshot, {"objective": "Revise the model after fixture review.", "parent_id": run["id"]})
        self.assertEqual(run["id"], child["parent_id"])
        self.assertNotEqual(run["spec_sha256"], child["spec_sha256"])
        self.assertEqual("needs_changes", self.service.get(self.snapshot, run["id"])["state"])

    def test_interrupted_builtin_can_resume_without_mutating_history(self):
        self.service._event(self.run, "facts", "running", instance="old process")
        interrupted = self.service.get(self.snapshot, self.run["id"])
        self.assertEqual("interrupted", next(n for n in interrupted["nodes"] if n["id"] == "facts")["status"])
        result = self.service.advance(self.snapshot, self.run["id"])
        self.assertEqual("awaiting_agent", result["state"])
        self.assertEqual("old process", result["events"][0]["instance"])
        self.assertEqual("complete", next(n for n in result["nodes"] if n["id"] == "facts")["status"])

    def test_explicit_supersession_preserves_history_and_blocks_old_work(self):
        self.service.advance(self.snapshot, self.run["id"])
        self.output("model")
        self.review("model_review")
        before = self.service.get(self.snapshot, self.run["id"])
        child = self.service.create(self.snapshot, {
            "objective": before["objective"], "parent_id": before["id"], "supersede_parent": True,
        })
        old = self.service.get(self.snapshot, before["id"])
        self.assertEqual("superseded", old["state"])
        self.assertEqual(before["events"], old["events"])
        self.assertEqual([], old["parallel_ready"])
        self.assertEqual([child["id"]], old["superseded_by"])
        with self.assertRaises(ValueError):
            self.output("architecture")
        with self.assertRaises(ValueError):
            self.service.advance(self.snapshot, before["id"])

    @unittest.skipUnless(checker_info(find_lean())["available"], "Pinned Lean is optional.")
    def test_validation_resolves_only_real_selected_checker_evidence(self):
        self.service.advance(self.snapshot, self.run["id"])
        self.output("model")
        self.review("model_review")
        self.output("architecture")
        goals = self.app.agents.obligations(self.snapshot)["obligations"]
        goal = next(g for g in goals if g["property"] == "conservation")
        self.output("formalization", obligation_ids=[goal["id"]])
        record, artifact = self.app.agents.prepare_attempt(self.snapshot, {
            "obligation_id": goal["id"], "obligation_sha256": goal["sha256"],
            "strategy": "generated", "agent": "fixture prover",
        })
        checked = self.app.agents.execute_attempt(record, artifact)
        self.assertEqual("proved", checked["status"])
        with self.assertRaises(KeyError):
            self.output("proof", proof_attempt_ids=["attempt_" + "0" * 16])
        self.output("proof", proof_attempt_ids=[checked["id"]])
        self.output("counterexample")
        self.output("tests")
        run = self.service.advance(self.snapshot, self.run["id"])
        validation = next(n for n in run["nodes"] if n["id"] == "validation")["artifact"]["content"]
        self.assertEqual(1, len(validation["checked_attempts"]))
        self.assertEqual(goal["id"], validation["checked_attempts"][0]["obligation_id"])
        self.assertEqual([], validation["unverified_selected_obligations"])
        self.assertFalse(validation["target_tests_executed"])
