"""Small standard-library client for the local API; usable by any agent."""

import json
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, ProxyHandler


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class CodeFormClient:
    def __init__(self, base_url: str = "http://127.0.0.1:7332", token: str | None = None):
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.username or parsed.password:
            raise ValueError("Client requires an HTTP loopback URL without credentials.")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("Use the local server origin without a path, query, or fragment.")
        self.base_url, self.token = base_url.rstrip("/"), token
        self.opener = build_opener(ProxyHandler({}))

    def _request(self, path: str, payload=None):
        headers = {}
        if payload is not None:
            if self.token is None:
                self.token = self._request("/api/bootstrap")["token"]
            headers = {"Content-Type": "application/json", "X-Codeform-Token": self.token}
        request = Request(self.base_url + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers=headers)
        try:
            with self.opener.open(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                body = json.loads(error.read())
                raise ApiError(error.code, body.get("error", f"HTTP {error.code}")) from error
            finally:
                error.close()

    def capabilities(self):
        return self._request("/api/v1/capabilities")

    def openapi(self):
        return self._request("/api/v1/openapi.json")

    def snapshots(self):
        return self._request("/api/v1/snapshots")

    def analyze(self, path: str):
        return self._request("/api/v1/snapshots", {"path": path})

    def job(self, job_id: str):
        return self._request(f"/api/v1/jobs/{job_id}")

    def wait(self, job: dict, timeout: float = 120, poll_interval: float = .25):
        deadline = time.monotonic() + timeout
        while job["status"] in {"queued", "running"}:
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for the local job; execution may still be running.")
            time.sleep(poll_interval)
            job = self.job(job["id"])
        if job["status"] == "failed":
            raise RuntimeError(job.get("error", "Local job failed."))
        return job

    def snapshot(self, snapshot_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}")

    def context(self, snapshot_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/context")

    def obligations(self, snapshot_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/obligations")

    def source(self, snapshot_id: str, path: str, line_start=None, line_end=None):
        query = {"path": path}
        if line_start is not None:
            query["line_start"] = line_start
        if line_end is not None:
            query["line_end"] = line_end
        return self._request(f"/api/v1/snapshots/{snapshot_id}/sources?{urlencode(query)}")

    def submit_attempt(self, snapshot_id: str, obligation: dict, strategy="generated", agent="external agent", request_id=None):
        payload = {"obligation_id": obligation["id"], "obligation_sha256": obligation["sha256"],
                   "strategy": strategy, "agent": agent}
        if request_id is not None:
            payload["request_id"] = request_id
        return self._request(f"/api/v1/snapshots/{snapshot_id}/attempts", payload)

    def attempts(self, snapshot_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/attempts")

    def attempt(self, snapshot_id: str, attempt_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/attempts/{attempt_id}")

    def propose(self, snapshot_id: str, proposal: dict):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/proposals", proposal)

    def proposals(self, snapshot_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/proposals")

    def review(self, snapshot_id: str, proposal_id: str, decision: str, note: str, reviewer: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/proposals/{proposal_id}/reviews",
                             {"decision": decision, "note": note, "reviewer": reviewer})

    def reviews(self, snapshot_id: str, proposal_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/proposals/{proposal_id}/reviews")

    def verify(self, snapshot_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/verify", {})

    def verification(self, snapshot_id: str):
        return self._request(f"/api/v1/snapshots/{snapshot_id}/verification")

    def compare(self, before: str, after: str):
        return self._request(f"/api/v1/compare?{urlencode({'before': before, 'after': after})}")
