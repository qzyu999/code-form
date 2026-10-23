"""Loopback-only HTTP application with a bounded read-only analysis queue."""

import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analyzer import analyze_repository
from .model import compare_bundles, report_markdown, validate_bundle
from .store import Store, task_spec, utc_now

WEB = Path(__file__).parent / "web"
MAX_REQUEST_BYTES = 20_000_000


class Application:
    def __init__(self, workspace: Path, data_dir: Path | None = None):
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise ValueError("Workspace must be an existing directory.")
        self.store = Store(data_dir or self.workspace / ".codeform")
        self.token = secrets.token_urlsafe(32)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()
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

        def do_GET(self):
            try:
                self._guard()
                parsed = urlparse(self.path)
                path, query = parsed.path, parse_qs(parsed.query)
                static = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8")}
                if path in static:
                    filename, content_type = static[path]
                    self._send(200, (WEB / filename).read_bytes(), content_type)
                elif path == "/api/health":
                    self._json(200, {"status": "ok", "version": "0.1.0"})
                elif path == "/api/bootstrap":
                    self._json(200, {"token": app.token, "workspace": str(app.workspace),
                                     "examples": app.examples, "snapshots": app.store.list()})
                elif path == "/api/snapshots":
                    self._json(200, app.store.list())
                elif path.startswith("/api/jobs/"):
                    identifier = path.removeprefix("/api/jobs/")
                    with app.lock:
                        job = app.jobs.get(identifier)
                        if not job:
                            raise KeyError("Analysis job not found.")
                        self._json(200, dict(job))
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
                        self._json(200, {**record, "annotations": app.store.annotations(parts[0])})
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
                if path == "/api/analyze":
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
