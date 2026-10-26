import copy
import hashlib
import json
import threading
import unittest
from pathlib import Path
from urllib.request import Request

from codeform.analyzer import analyze_repository
from codeform.client import ApiError, CodeFormClient
from codeform.model import canonical_json
from codeform.proofs import proof_plan
from codeform.reports import build_report, report_html, report_markdown, verification_status
from codeform.server import Application, make_server
from workspace import TemporaryWorkspace

ROOT = Path(__file__).resolve().parents[1]


class ReviewReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryWorkspace()
        self.app = Application(ROOT, Path(self.temporary.name))
        self.bundle = analyze_repository(ROOT / "examples/verified-transfer")
        self.app.store.save(self.bundle)
        self.snapshot = self.bundle["id"]

    def tearDown(self):
        self.app.close()
        self.temporary.cleanup()

    def draft(self, mode):
        run = self.app.workflows.create(self.snapshot, {"objective": "Review the captured operation.", "mode": mode})
        self.app.workflows.advance(self.snapshot, run["id"])
        context = self.app.workflows.context(self.snapshot, run["id"], "model")
        self.app.workflows.complete(self.snapshot, run["id"], "model", {
            "snapshot_id": self.snapshot, "spec_sha256": context["spec_sha256"],
            "input_sha256": context["input_sha256"], "actor": "manual fixture",
            "summary": "Source-linked proposed model.",
            "claims": [{"status": "proposed", "statement": "</script><script>window.compromised=true</script>",
                        "latex": r"x+y=s+d", "evidence": [{"path": "transfer.py", "line_start": 4, "line_end": 8}]}],
        })
        return run["id"]

    def test_report_pins_analysis_and_preserves_live_gate_and_source(self):
        owner = self.draft("review")
        preview = self.draft("preview")
        before = self.app.workflows.get(self.snapshot, owner)
        report = build_report(self.app, self.snapshot, preview)
        self.assertEqual(preview, report["workflow"]["id"])
        self.assertEqual("awaiting_review", report["owner_review"][0]["state"])
        self.assertEqual(before, self.app.workflows.get(self.snapshot, owner))
        self.assertEqual(self.bundle, report["analysis"])
        self.assertEqual(6, report["verification_coverage"]["supported_obligations"])
        self.assertEqual(0, report["verification_coverage"]["proved"])
        unhashed = {k: v for k, v in report.items() if k != "sha256"}
        self.assertEqual(report["sha256"], hashlib.sha256(canonical_json(unhashed).encode()).hexdigest())
        html = report_html(report)
        self.assertIn("not owner-approved", html)
        self.assertIn("&lt;/script&gt;&lt;script&gt;", html)
        self.assertNotIn("<script>window.compromised", html)
        self.assertIn("Captured evidence", html)
        self.assertIn("transfer_unchecked", html)
        self.assertIn("language-lean", html)
        self.assertIn("$$\nx+y=s+d\n$$", report_markdown(report))
        offline = report_html(report, standalone=True)
        self.assertIn("data:font/woff2;base64,", offline)
        self.assertNotIn('src="/', offline)
        self.assertIn("\\u003c/script>", offline)

    def test_unsupported_is_distinct_from_not_run_and_checker_missing(self):
        bundle = analyze_repository(ROOT / "examples/cyclic-service")
        self.assertEqual("unsupported", verification_status(bundle, None)["state"])
        self.assertEqual("not_run", verification_status(self.bundle, None)["state"])
        self.assertEqual("checker_unavailable", verification_status(self.bundle, None, {"available": False})["state"])

    def test_default_prefers_completed_preview_and_keeps_live_owner_visible(self):
        owner = self.draft("review")
        preview = self.draft("preview")
        while True:
            run = self.app.workflows.advance(self.snapshot, preview)
            node = next((n for n in run["nodes"] if n["executor"] == "external" and n["status"] == "awaiting_agent"), None)
            if not node:
                break
            context = self.app.workflows.context(self.snapshot, preview, node["id"])
            self.app.workflows.complete(self.snapshot, preview, node["id"], {
                "snapshot_id": self.snapshot, "spec_sha256": context["spec_sha256"],
                "input_sha256": context["input_sha256"], "actor": "manual preview fixture",
                "summary": "Proposed analysis with no checked result.",
                "claims": [{"statement": "The implementation subtracts the amount.", "status": "observed",
                            "evidence": [{"path": "transfer.py", "line_start": 4, "line_end": 8}]}],
            })
        self.assertEqual("preview_complete", run["state"])
        newer = self.draft("review")
        report = build_report(self.app, self.snapshot)
        self.assertEqual(preview, report["workflow"]["id"])
        self.assertEqual({owner, newer}, {r["id"] for r in report["owner_review"]})
        self.assertEqual(0, report["verification_coverage"]["proved"])
        self.assertIn("checked standalone attempt references: 0", report_markdown(report))
        self.assertEqual(newer, build_report(self.app, self.snapshot, newer)["workflow"]["id"])

    def test_wrong_snapshot_statement_or_checker_input_cannot_be_promoted(self):
        # Construct certificate metadata to exercise matching; this fixture is not a real proof.
        artifact = proof_plan(self.bundle)[0]
        result = {**artifact, "statement": "Misleading changed prose", "status": "proved", "axioms": [],
                  "checker": {"declaration_verified": True,
                              "source_sha256": hashlib.sha256(artifact["lean_source"].encode()).hexdigest(),
                              "obligation_sha256": artifact["obligation"]["sha256"],
                              "obligation_id": artifact["obligation"]["id"]}}
        record = {"snapshot_id": self.snapshot, "repository_content_sha256": self.bundle["repository"]["content_sha256"],
                  "artifacts": [result]}
        accepted = verification_status(self.bundle, record)
        self.assertEqual(1, accepted["proved"])
        self.assertEqual(artifact["statement"], accepted["results"][0]["statement"])
        for field in ("source_sha256", "obligation_sha256", "obligation_id", "declaration_verified"):
            bad = copy.deepcopy(record)
            bad["artifacts"][0]["checker"][field] = "wrong"
            self.assertEqual(0, verification_status(self.bundle, bad)["proved"])
        bad = {**record, "repository_content_sha256": "wrong"}
        self.assertEqual("stale", verification_status(self.bundle, bad)["state"])
        self.assertEqual(0, verification_status(self.bundle, bad)["proved"])

    def test_report_api_formats_selection_and_snapshot_isolation(self):
        workflow = self.draft("review")
        server = make_server(self.app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = CodeFormClient(f"http://127.0.0.1:{server.server_port}")
        try:
            report = client.report(self.snapshot, workflow)
            self.assertEqual(workflow, report["workflow"]["id"])
            self.assertEqual(self.bundle, report["analysis"])
            for kind, mime in (("json", "application/json"), ("markdown", "text/markdown"), ("html", "text/html")):
                path = f"{client.base_url}/api/v1/snapshots/{self.snapshot}/report?format={kind}&workflow_id={workflow}"
                with client.opener.open(Request(path)) as response:
                    self.assertEqual(mime, response.headers["Content-Type"].split(";")[0])
                    self.assertIn(b"Source-linked proposed model.", response.read())
            with client.opener.open(client.base_url + f"/reports/{self.snapshot}") as response:
                self.assertIn(b"code-form review report", response.read())
            with self.assertRaises(ApiError) as wrong_run:
                client.report(self.snapshot, "workflow_0000000000000000")
            self.assertEqual(404, wrong_run.exception.status)
            with self.assertRaises(ApiError):
                client._request(f"/api/v1/snapshots/{self.snapshot}/report?format=unknown")
            other = analyze_repository(ROOT / "examples/cyclic-service")
            self.app.store.save(other)
            with self.assertRaises(ApiError):
                client.report(other["id"], workflow)
            self.assertEqual("awaiting_review", self.app.workflows.get(self.snapshot, workflow)["state"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
