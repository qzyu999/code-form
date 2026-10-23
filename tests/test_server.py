import json
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from codeform.analyzer import analyze_repository
from codeform.server import Application, make_server
from workspace import TemporaryWorkspace

ROOT = Path(__file__).resolve().parents[1]


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryWorkspace()
        self.app = Application(ROOT, Path(self.temporary.name))
        self.server = make_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.close()
        self.thread.join()
        self.temporary.cleanup()

    def request(self, path, payload=None, headers=None):
        defaults = {}
        if payload is not None:
            defaults = {"Content-Type": "application/json", "X-Codeform-Token": self.app.token}
        request = Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={**defaults, **(headers or {})})
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                return response.status, json.loads(raw) if "application/json" in response.headers["Content-Type"] else raw
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read())
            finally:
                error.close()

    def test_full_analysis_review_export_import_journey(self):
        status, bootstrap = self.request("/api/bootstrap")
        self.assertEqual(200, status)
        self.assertEqual(3, len(bootstrap["examples"]))
        status, job = self.request("/api/analyze", {"path": "examples/order-workflow"})
        self.assertEqual(202, status)
        for _ in range(100):
            _, result = self.request(f"/api/jobs/{job['id']}")
            if result["status"] in {"complete", "failed"}:
                break
            time.sleep(.02)
        self.assertEqual("complete", result["status"])
        identifier = result["snapshot_id"]
        _, record = self.request(f"/api/snapshots/{identifier}")
        finding = record["bundle"]["findings"][0]
        self.assertEqual(400, self.request(f"/api/snapshots/{identifier}/tasks", {"finding_id": finding["id"]})[0])
        self.assertEqual(200, self.request(f"/api/snapshots/{identifier}/annotations",
                                        {"entity_id": finding["id"], "status": "accepted", "note": "Fix terminal state semantics."})[0])
        _, task = self.request(f"/api/snapshots/{identifier}/tasks", {"finding_id": finding["id"]})
        self.assertEqual("human_review", task["execution"]["merge"])
        _, exported = self.request(f"/api/snapshots/{identifier}/export?format=json")
        self.assertEqual(identifier, exported["id"])
        self.assertEqual(201, self.request("/api/import", {"bundle": exported})[0])
        self.assertEqual(200, self.request(f"/api/snapshots/{identifier}/export?format=markdown")[0])
        self.assertEqual(200, self.request(f"/api/snapshots/{identifier}/export?format=architecture")[0])
        self.assertEqual(1, len(self.request("/api/snapshots")[1]))

    def test_mutations_reject_cross_origin_missing_token_and_outside_paths(self):
        self.assertEqual(403, self.request("/api/analyze", {"path": "examples/order-workflow"},
                                         {"X-Codeform-Token": ""})[0])
        self.assertEqual(403, self.request("/api/analyze", {"path": "examples/order-workflow"},
                                         {"Origin": "http://example.invalid"})[0])
        self.assertEqual(403, self.request("/api/bootstrap", headers={"Host": "example.invalid"})[0])
        self.assertEqual(400, self.request("/api/analyze", {"path": "../"})[0])
        self.assertEqual(400, self.request("/api/snapshots/not-an-id")[0])
        self.assertEqual(404, self.request("/api/jobs/missing")[0])

    def test_invalid_import_is_rejected_and_static_assets_load(self):
        bundle = analyze_repository(ROOT / "examples/order-workflow")
        bundle["sources"][0]["content"] = "invalid"
        self.assertEqual(400, self.request("/api/import", {"bundle": bundle})[0])
        self.assertEqual(400, self.request("/api/import", {"bundle": None})[0])
        for path in ("/", "/app.js", "/style.css", "/api/health"):
            self.assertEqual(200, self.request(path)[0])
        self.assertEqual(404, self.request("/../../README.md")[0])


if __name__ == "__main__":
    unittest.main()
