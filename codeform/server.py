"""Loopback-only HTTP application with a bounded read-only analysis queue."""

import json
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analyzer import analyze_repository
from .model import compare_bundles, report_markdown, validate_bundle
from .store import Store, task_spec, utc_now
from .proofs import checker_info, find_lean, proof_plan, verify_bundle
from .agent_api import AgentService
from .api_spec import openapi_document
from .walkthrough import build_walkthrough, simulate_scenario

WEB = Path(__file__).parent / "web"
MAX_REQUEST_BYTES = 20_000_000


class Application:
    def __init__(self, workspace: Path, data_dir: Path | None = None, lean: Path | None = None):
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise ValueError("Workspace must be an existing directory.")
        self.store = Store(data_dir or self.workspace / ".codeform")
        self.token = secrets.token_urlsafe(32)
        self.lean = find_lean(lean)
        self.proof_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lean")
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.agents = AgentService(self)
        self.examples = []
        # Bundled examples stay available when the allowed workspace is broader.
        examples_dir = Path(__file__).resolve().parents[1] / "examples"
        if not examples_dir.resolve().is_relative_to(self.workspace):
            examples_dir = self.workspace / "examples"
        if examples_dir.is_dir():
            for path in sorted(examples_dir.iterdir()):
                if path.is_dir() and (path / "README.md").is_file():
                    descriptions = {
                        "payment-service": "Routes, persistence, test gaps, and a documented API mismatch.",
                        "order-workflow": "A finite order state machine with a terminal-state counterexample.",
                        "cyclic-service": "A dependency cycle, a swallowed error, and an untested interface.",
                        "verified-transfer": "Checked integer theorems, an overdraft counterexample, and a guarded repair.",
                        "verified-workflow": "A Lean induction proof over every finite event sequence.",
                    }
                    self.examples.append({"name": path.name, "path": str(path),
                                          "description": descriptions.get(path.name, "Example Python repository.")})

    def resolve_repository(self, value: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Enter a repository directory.")
        candidate = Path(value).expanduser()
        target = (candidate if candidate.is_absolute() else self.workspace / candidate).resolve()
        if not target.is_relative_to(self.workspace):
            raise ValueError(f"Choose a repository inside the allowed workspace: {self.workspace}")
        if not target.is_dir():
            raise ValueError("Repository directory does not exist.")
        return target

    def submit(self, repository: str) -> dict:
        target = self.resolve_repository(repository)
        with self.lock:
            active = sum(job["status"] in {"queued", "running"} for job in self.jobs.values())
            if active >= 4:
                raise ValueError("The analysis queue is full; wait for a running analysis.")
            if len(self.jobs) >= 100:
                for identifier in list(self.jobs):
                    if self.jobs[identifier]["status"] not in {"queued", "running"}:
                        del self.jobs[identifier]
                        break
            identifier = "job_" + secrets.token_hex(8)
            job = {"id": identifier, "status": "queued", "repository": str(target), "created_at": utc_now()}
            self.jobs[identifier] = job
        self.executor.submit(self._analyze, identifier, target)
        return dict(job)

    def _analyze(self, identifier: str, repository: Path) -> None:
        with self.lock:
            self.jobs[identifier]["status"] = "running"
        try:
            bundle = analyze_repository(repository)
            self.store.save(bundle)
            update = {"status": "complete", "snapshot_id": bundle["id"]}
        except Exception as error:
            update = {"status": "failed", "error": str(error)}
        with self.lock:
            self.jobs[identifier].update(update)

    def seed_examples(self) -> None:
        for example in self.examples:
            self.store.save(analyze_repository(example["path"]))

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.proof_executor.shutdown(wait=True, cancel_futures=True)

    def submit_verification(self, identifier: str) -> dict:
        bundle = self.store.get(identifier)["bundle"]
        info = checker_info(self.lean)
        if not info["available"]:
            raise ValueError(info["error"])
        with self.lock:
            if self._proof_busy():
                raise ValueError("A proof check is already running; wait for it to finish.")
            job_id = "job_" + secrets.token_hex(8)
            job = {"id": job_id, "kind": "verification", "status": "queued", "snapshot_id": identifier, "created_at": utc_now()}
            self.jobs[job_id] = job
        self.proof_executor.submit(self._verify, job_id, bundle)
        return dict(job)

    def _proof_busy(self) -> bool:
        return any(job.get("kind") in {"verification", "attempt"} and job["status"] in {"queued", "running"}
                   for job in self.jobs.values())

    def submit_attempt(self, snapshot_id: str, payload: dict) -> dict:
        record, artifact = self.agents.prepare_attempt(snapshot_id, payload)
        comparable = ("obligation_id", "obligation_sha256", "strategy", "agent", "request_id")
        with self.lock:
            try:
                existing = self.agents.attempt(snapshot_id, record["id"])
            except KeyError:
                existing = None
            pending = next((job for job in self.jobs.values() if job.get("attempt_id") == record["id"]), None)
            if existing:
                if any(existing[key] != record[key] for key in comparable):
                    raise ValueError("request_id was already used for a different attempt.")
                return {"id": None, "kind": "attempt", "status": "complete", "snapshot_id": snapshot_id,
                        "attempt_id": record["id"], "result_status": existing["status"], "reused": True}
            if pending:
                if any(pending["request"][key] != record[key] for key in comparable):
                    raise ValueError("request_id was already used for a different attempt.")
                return {k: v for k, v in pending.items() if k != "request"}
            if self._proof_busy():
                raise ValueError("A proof check is already running; wait for it to finish.")
            info = checker_info(self.lean)
            if not info["available"]:
                raise ValueError(info["error"])
            job_id = "job_" + secrets.token_hex(8)
            job = {"id": job_id, "kind": "attempt", "status": "queued", "snapshot_id": snapshot_id,
                   "attempt_id": record["id"], "created_at": utc_now(), "request": record}
            self.jobs[job_id] = job
        self.proof_executor.submit(self._attempt, job_id, record, artifact)
        return {k: v for k, v in job.items() if k != "request"}

    def _attempt(self, job_id: str, record: dict, artifact: dict) -> None:
        with self.lock:
            self.jobs[job_id]["status"] = "running"
        try:
            result = self.agents.execute_attempt(record, artifact)
            update = {"status": "complete", "result_status": result["status"]}
        except Exception as error:
            result = {**record, "status": "error", "error": str(error), "completed_at": utc_now(),
                      "promoted_to_verification": False}
            try:
                self.store.save_agent_record(record["snapshot_id"], "attempts", result)
            except Exception:
                pass
            update = {"status": "failed", "error": str(error)}
        with self.lock:
            self.jobs[job_id].update(update)

    def _verify(self, job_id: str, bundle: dict) -> None:
        with self.lock:
            self.jobs[job_id]["status"] = "running"
        try:
            report = verify_bundle(bundle, self.lean, self.store.path / "proof-runs")
            self.store.save_verification(bundle["id"], report)
            update = {"status": "complete", "summary": report["summary"]}
        except Exception as error:
            update = {"status": "failed", "error": str(error)}
        with self.lock:
            self.jobs[job_id].update(update)


def make_server(app: Application, port: int = 7331) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, format: str, *args) -> None:
            pass

        def _send(self, status: int, content: bytes, content_type: str = "application/json", filename: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "style-src-attr 'unsafe-inline'; font-src 'self'; "
                             "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content)

        def _json(self, status: int, value):
            self._send(status, json.dumps(value, ensure_ascii=False).encode())

        def _guard(self, mutation: bool = False) -> None:
            allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            host = self.headers.get("Host", "")
            if host not in allowed_hosts:
                raise PermissionError("Local host access only.")
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{item}" for item in allowed_hosts}:
                raise PermissionError("Cross-origin requests are not allowed.")
            if mutation and not secrets.compare_digest(self.headers.get("X-Codeform-Token", ""), app.token):
                raise PermissionError("Missing or invalid local request token.")

        def _v1_get(self, path: str, query: dict) -> None:
            if path == "/api/v1/openapi.json":
                self._json(200, openapi_document())
            elif path == "/api/v1/capabilities":
                self._json(200, app.agents.capabilities())
            elif path == "/api/v1/snapshots":
                self._json(200, app.store.list())
            elif path == "/api/v1/compare":
                before = app.store.get(query.get("before", [""])[0])["bundle"]
                after = app.store.get(query.get("after", [""])[0])["bundle"]
                if before["repository"]["path"] != after["repository"]["path"]:
                    raise ValueError("Choose snapshots of the same repository.")
                self._json(200, compare_bundles(before, after))
            elif path.startswith("/api/v1/jobs/"):
                with app.lock:
                    job = app.jobs.get(path.removeprefix("/api/v1/jobs/"))
                    if not job:
                        raise KeyError("Job not found.")
                    self._json(200, {k: v for k, v in job.items() if k != "request"})
            elif path.startswith("/api/v1/snapshots/"):
                parts = path.removeprefix("/api/v1/snapshots/").split("/")
                snapshot_id = parts[0]
                record = app.store.get(snapshot_id)
                if len(parts) == 1:
                    self._json(200, {**record, "annotations": app.store.annotations(snapshot_id),
                                     "verification": app.store.verification(snapshot_id)})
                elif len(parts) == 2:
                    endpoint = parts[1]
                    if endpoint == "sources":
                        start = int(query["line_start"][0]) if "line_start" in query else None
                        end = int(query["line_end"][0]) if "line_end" in query else None
                        result = app.agents.source(snapshot_id, query.get("path", [""])[0], start, end)
                    elif endpoint == "context":
                        result = app.agents.context(snapshot_id)
                    elif endpoint == "obligations":
                        result = app.agents.obligations(snapshot_id)
                    elif endpoint == "attempts":
                        result = app.agents.attempts(snapshot_id)
                    elif endpoint == "proposals":
                        result = app.agents.proposals(snapshot_id)
                    elif endpoint == "verification":
                        result = app.store.verification(snapshot_id)
                    elif endpoint == "walkthrough":
                        result = build_walkthrough(record["bundle"], app.store.verification(snapshot_id))
                    else:
                        raise KeyError("Endpoint not found.")
                    self._json(200, result)
                elif len(parts) == 3 and parts[1] == "attempts":
                    self._json(200, app.agents.attempt(snapshot_id, parts[2]))
                elif len(parts) == 4 and parts[1] == "proposals" and parts[3] == "reviews":
                    self._json(200, app.agents.reviews(snapshot_id, parts[2]))
                else:
                    raise KeyError("Endpoint not found.")
            else:
                raise KeyError("Endpoint not found.")

        def _v1_post(self, path: str, payload: dict) -> None:
            if path == "/api/v1/snapshots":
                if set(payload) != {"path"}:
                    raise ValueError("Repository analysis requires only path.")
                self._json(202, app.submit(payload["path"]))
            elif path.startswith("/api/v1/snapshots/"):
                parts = path.removeprefix("/api/v1/snapshots/").split("/")
                snapshot_id = parts[0]
                if len(parts) == 2 and parts[1] == "attempts":
                    self._json(202, app.submit_attempt(snapshot_id, payload))
                elif len(parts) == 2 and parts[1] == "proposals":
                    self._json(201, app.agents.save_proposal(snapshot_id, payload))
                elif len(parts) == 2 and parts[1] == "verify":
                    if payload:
                        raise ValueError("Full verification requires an empty object.")
                    self._json(202, app.submit_verification(snapshot_id))
                elif len(parts) == 2 and parts[1] == "scenarios":
                    bundle = app.store.get(snapshot_id)["bundle"]
                    self._json(200, simulate_scenario(bundle, payload))
                elif len(parts) == 4 and parts[1] == "proposals" and parts[3] == "reviews":
                    self._json(201, app.agents.review_proposal(snapshot_id, parts[2], payload))
                else:
                    raise KeyError("Endpoint not found.")
            else:
                raise KeyError("Endpoint not found.")

        def do_GET(self):
            try:
                self._guard()
                parsed = urlparse(self.path)
                path, query = parsed.path, parse_qs(parsed.query)
                static = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/math.js": ("math.js", "text/javascript; charset=utf-8"),
                          "/walkthrough.js": ("walkthrough.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8")}
                if path.startswith("/api/v1/"):
                    self._v1_get(path, query)
                elif path in static:
                    filename, content_type = static[path]
                    self._send(200, (WEB / filename).read_bytes(), content_type)
                elif path.startswith("/vendor/katex/"):
                    relative = path.removeprefix("/vendor/katex/")
                    types = {"katex.min.js": "text/javascript; charset=utf-8", "katex.min.css": "text/css; charset=utf-8"}
                    if relative in types:
                        target, kind = WEB / "vendor/katex" / relative, types[relative]
                    elif re.fullmatch(r"fonts/[A-Za-z0-9_-]+\.(woff2|woff|ttf)", relative):
                        target = WEB / "vendor/katex" / relative
                        kind = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf"}[target.suffix]
                    else:
                        raise KeyError("Vendor asset not found.")
                    if not target.is_file():
                        raise KeyError("Vendor asset not found.")
                    self._send(200, target.read_bytes(), kind)
                elif path == "/api/health":
                    self._json(200, {"status": "ok", "version": "0.1.0"})
                elif path == "/api/bootstrap":
                    self._json(200, {"token": app.token, "workspace": str(app.workspace),
                                     "examples": app.examples, "snapshots": app.store.list(),
                                     "proof_checker": checker_info(app.lean)})
                elif path == "/api/snapshots":
                    self._json(200, app.store.list())
                elif path.startswith("/api/jobs/"):
                    identifier = path.removeprefix("/api/jobs/")
                    with app.lock:
                        job = app.jobs.get(identifier)
                        if not job:
                            raise KeyError("Analysis job not found.")
                        self._json(200, {k: v for k, v in job.items() if k != "request"})
                elif path == "/api/compare":
                    before = app.store.get(query.get("before", [""])[0])["bundle"]
                    after = app.store.get(query.get("after", [""])[0])["bundle"]
                    if before["repository"]["path"] != after["repository"]["path"]:
                        raise ValueError("Choose snapshots of the same repository.")
                    self._json(200, compare_bundles(before, after))
                elif path.startswith("/api/snapshots/"):
                    parts = path.removeprefix("/api/snapshots/").split("/")
                    record = app.store.get(parts[0])
                    bundle = record["bundle"]
                    if len(parts) == 1:
                        self._json(200, {**record, "annotations": app.store.annotations(parts[0]),
                                         "verification": app.store.verification(parts[0]),
                                         "proof_plan": proof_plan(bundle),
                                         "walkthrough": build_walkthrough(bundle, app.store.verification(parts[0])),
                                         "agent_work": {"attempts": app.agents.attempts(parts[0]),
                                                        "proposals": app.agents.proposals(parts[0])}})
                    elif len(parts) == 2 and parts[1] == "verification":
                        self._json(200, app.store.verification(parts[0]))
                    elif len(parts) == 2 and parts[1] == "export":
                        kind = query.get("format", ["json"])[0]
                        if kind == "json":
                            self._send(200, json.dumps(bundle, indent=2, ensure_ascii=False).encode(),
                                       filename=f"{bundle['id']}.json")
                        elif kind == "markdown":
                            self._send(200, report_markdown(bundle).encode(), "text/markdown; charset=utf-8", f"{bundle['id']}.md")
                        elif kind in {"architecture", "sequence"}:
                            self._send(200, bundle["diagrams"][kind].encode(), "text/plain; charset=utf-8", f"{kind}.mmd")
                        else:
                            raise ValueError("Unknown export format.")
                    else:
                        raise KeyError("Endpoint not found.")
                else:
                    raise KeyError("Endpoint not found.")
            except PermissionError as error:
                self._json(403, {"error": str(error)})
            except KeyError as error:
                self._json(404, {"error": str(error).strip("'")})
            except (ValueError, TypeError) as error:
                self._json(400, {"error": str(error)})
            except Exception:
                self._json(500, {"error": "The local request failed. Check the saved bundle and workspace permissions."})

        def do_POST(self):
            try:
                self._guard(mutation=True)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Use application/json.")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_REQUEST_BYTES:
                    raise ValueError("Request must contain JSON and stay within 20 MB.")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object.")
                path = urlparse(self.path).path
                if path.startswith("/api/v1/"):
                    self._v1_post(path, payload)
                elif path == "/api/analyze":
                    self._json(202, app.submit(payload.get("path", "")))
                elif path == "/api/import":
                    bundle = payload.get("bundle")
                    validate_bundle(bundle)
                    app.store.save(bundle)
                    self._json(201, {"snapshot_id": bundle["id"]})
                elif path.startswith("/api/snapshots/"):
                    parts = path.removeprefix("/api/snapshots/").split("/")
                    if len(parts) != 2:
                        raise KeyError("Endpoint not found.")
                    if parts[1] == "annotations":
                        result = app.store.annotate(parts[0], payload.get("entity_id", ""),
                                                    payload.get("status", "open"), payload.get("note", ""))
                        self._json(200, result)
                    elif parts[1] == "tasks":
                        bundle = app.store.get(parts[0])["bundle"]
                        self._json(200, task_spec(bundle, payload.get("finding_id", ""), app.store.annotations(parts[0])))
                    elif parts[1] == "verify":
                        self._json(202, app.submit_verification(parts[0]))
                    else:
                        raise KeyError("Endpoint not found.")
                else:
                    raise KeyError("Endpoint not found.")
            except PermissionError as error:
                self._json(403, {"error": str(error)})
            except KeyError as error:
                self._json(404, {"error": str(error).strip("'")})
            except (ValueError, TypeError, AttributeError) as error:
                self._json(400, {"error": str(error)})
            except Exception:
                self._json(500, {"error": "Could not save this request."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
