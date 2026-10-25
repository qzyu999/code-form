"""Dependency-free OpenAPI description of the agent service."""

from copy import deepcopy

from .agent_api import API_VERSION


def openapi_document() -> dict:
    snapshot = {"name": "snapshot_id", "in": "path", "required": True, "schema": {"type": "string"}}
    workflow = {"name": "workflow_id", "in": "path", "required": True, "schema": {"type": "string"}}
    node = {"name": "node_id", "in": "path", "required": True, "schema": {"type": "string"}}
    json_response = {"description": "JSON response", "content": {"application/json": {"schema": {"type": "object"}}}}

    def operation(name, description, mutation=False, schema=None, parameters=None):
        op = {"operationId": name, "summary": description, "responses": {
            "200": deepcopy(json_response), "400": {"description": "Invalid input"},
            "403": {"description": "Local access or token rejected"}, "404": {"description": "Not found"},
        }, "parameters": parameters or []}
        if mutation:
            op["security"] = [{"LocalToken": []}]
            op["requestBody"] = {"required": True, "content": {"application/json": {
                "schema": schema or {"type": "object"}}}}
            op["responses"]["202"] = {**deepcopy(json_response), "description": "Queued job or reused completed attempt"}
        return op

    attempt = {"type": "object", "additionalProperties": False,
               "required": ["obligation_id", "obligation_sha256"],
               "properties": {
                   "obligation_id": {"type": "string"}, "obligation_sha256": {"type": "string"},
                   "strategy": {"enum": ["generated", "simplify", "decide"], "default": "generated"},
                   "agent": {"type": "string", "maxLength": 120},
                   "request_id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]{1,80}$"},
               }}
    evidence = {"type": "object", "additionalProperties": False, "required": ["path", "line_start", "line_end"],
                "properties": {"path": {"type": "string"}, "line_start": {"type": "integer", "minimum": 1},
                               "line_end": {"type": "integer", "minimum": 1}}}
    proposal = {"type": "object", "additionalProperties": False,
                "required": ["kind", "title", "rationale", "content", "evidence"],
                "properties": {
                    "kind": {"enum": ["requirement", "contract", "explanation", "repair"]},
                    **{k: {"type": "string", "minLength": 1, "maxLength": 12000}
                       for k in ("title", "rationale", "content")},
                    "evidence": {"type": "array", "minItems": 1, "maxItems": 30, "items": evidence},
                    "obligation_id": {"type": "string"}, "agent": {"type": "string"},
                    "parent_id": {"type": "string"},
                }}
    paths = {
        "/api/v1/workflow-templates": {"get": operation("getWorkflowTemplates", "DAG template, prompts, executor types, and limits")},
        "/api/v1/capabilities": {"get": operation("capabilities", "Available operations, checker, and limitations")},
        "/api/v1/snapshots": {
            "get": operation("listSnapshots", "List immutable repository snapshots"),
            "post": operation("analyzeRepository", "Queue read-only repository analysis", True,
                              {"type": "object", "required": ["path"], "additionalProperties": False,
                               "properties": {"path": {"type": "string"}}}),
        },
        "/api/v1/jobs/{job_id}": {"get": operation("getJob", "Poll analysis or proof execution",
            parameters=[{"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}])},
        "/api/v1/snapshots/{snapshot_id}": {"get": operation("getSnapshot", "Read captured model, evidence, and verification", parameters=[snapshot])},
        "/api/v1/snapshots/{snapshot_id}/sources": {"get": operation("getCapturedSource", "Read source from the immutable snapshot", parameters=[
            snapshot, {"name": "path", "in": "query", "required": True, "schema": {"type": "string"}},
            *[{"name": k, "in": "query", "schema": {"type": "integer", "minimum": 1}} for k in ("line_start", "line_end")],
        ])},
        "/api/v1/snapshots/{snapshot_id}/context": {"get": operation("getAgentContext", "Versioned instructions and reasoning context", parameters=[snapshot])},
        "/api/v1/snapshots/{snapshot_id}/walkthrough": {"get": operation(
            "getWalkthrough", "Read purpose, mathematical model excerpts, notation, and proof support", parameters=[snapshot])},
        "/api/v1/snapshots/{snapshot_id}/scenarios": {"post": operation(
            "simulateScenario", "Evaluate an example in the captured mathematical model without executing target code", True,
            {"type": "object", "additionalProperties": False, "required": ["model_id", "inputs"],
             "properties": {"model_id": {"type": "string"}, "inputs": {"type": "object"}}}, [snapshot])},
        "/api/v1/snapshots/{snapshot_id}/obligations": {"get": operation("getObligations", "Read fixed theorem contexts, statements, IDs, and hashes", parameters=[snapshot])},
        "/api/v1/snapshots/{snapshot_id}/attempts": {
            "get": operation("listAttempts", "Read immutable proof-attempt history", parameters=[snapshot]),
            "post": operation("attemptProof", "Try a controlled strategy against an exact obligation", True, attempt, [snapshot]),
        },
        "/api/v1/snapshots/{snapshot_id}/attempts/{attempt_id}": {"get": operation("getAttempt", "Read checker result and diagnostics", parameters=[
            snapshot, {"name": "attempt_id", "in": "path", "required": True, "schema": {"type": "string"}},
        ])},
        "/api/v1/snapshots/{snapshot_id}/proposals": {
            "get": operation("listProposals", "Read draft proposals and latest review"),
            "post": operation("createProposal", "Save an evidence-linked draft; does not execute or prove it", True, proposal, [snapshot]),
        },
        "/api/v1/snapshots/{snapshot_id}/proposals/{proposal_id}/reviews": {"post": operation(
            "reviewProposal", "Append review without changing the immutable proposal or source", True,
            {"type": "object", "additionalProperties": False, "required": ["decision", "note", "reviewer"],
             "properties": {"decision": {"enum": ["accepted", "rejected", "needs_changes"]},
                            "note": {"type": "string"}, "reviewer": {"type": "string"}}},
            [snapshot, {"name": "proposal_id", "in": "path", "required": True, "schema": {"type": "string"}}],
        )},
        "/api/v1/snapshots/{snapshot_id}/verify": {"post": operation(
            "verifySnapshot", "Check the generated complete obligation set", True, {"type": "object", "maxProperties": 0}, [snapshot])},
        "/api/v1/snapshots/{snapshot_id}/verification": {"get": operation("getVerification", "Read latest complete verification report", parameters=[snapshot])},
        "/api/v1/compare": {"get": operation("compareSnapshots", "Compare source and model entities from the same repository", parameters=[
            {"name": name, "in": "query", "required": True, "schema": {"type": "string"}} for name in ("before", "after")
        ])},
    }
    root = "/api/v1/snapshots/{snapshot_id}/workflows"
    paths[root] = {
        "get": operation("listWorkflows", "Read versioned DAG runs and their immutable artifact/event projections", parameters=[snapshot]),
        "post": operation("createWorkflow", "Pin objective, requirements, prompts, and snapshot in a new DAG run", True,
                          {"type": "object", "required": ["objective"], "additionalProperties": False,
                           "properties": {"objective": {"type": "string", "maxLength": 4000},
                                          "parent_id": {"type": "string"}, "parent_snapshot_id": {"type": "string"},
                                          "supersede_parent": {"type": "boolean"},
                                          "prompt_overrides": {"type": "object"}}}, [snapshot]),
    }
    paths[root + "/{workflow_id}"] = {"get": operation("getWorkflow", "Read live dependency statuses and recorded artifacts", parameters=[snapshot, workflow])}
    paths[root + "/{workflow_id}/advance"] = {"post": operation(
        "advanceWorkflow", "Run ready read-only built-in nodes; stop at external or human gates", True,
        {"type": "object", "maxProperties": 0}, [snapshot, workflow])}
    path = root + "/{workflow_id}/nodes/{node_id}"
    paths[path + "/context"] = {"get": operation("getWorkflowNodeContext", "Pinned role prompt, dependency artifacts, and input hash", parameters=[snapshot, workflow, node])}
    paths[path + "/outputs"] = {"post": operation(
        "submitWorkflowNodeOutput", "Submit an evidence-linked external-agent artifact against exact ready inputs", True,
        {"type": "object", "additionalProperties": False, "required": ["snapshot_id", "spec_sha256", "input_sha256", "actor", "summary", "claims"],
         "properties": {"snapshot_id": {"type": "string"}, "spec_sha256": {"type": "string"},
                        "input_sha256": {"type": "string"}, "actor": {"type": "string"},
                        "summary": {"type": "string"}, "claims": {"type": "array", "minItems": 1, "maxItems": 30,
                            "items": {"type": "object", "additionalProperties": False,
                                      "required": ["statement", "status", "evidence"],
                                      "properties": {"statement": {"type": "string"},
                                                     "status": {"enum": ["observed", "inferred", "proposed", "unknown"]},
                                                     "evidence": {"type": "array", "items": evidence},
                                                     "latex": {"type": ["string", "null"]}}}},
                        "diagram": {"type": "object"}, "limitations": {"type": "array", "items": {"type": "string"}},
                        "assumptions": {"type": "array", "items": {"type": "string"}},
                        "test_plan": {"type": "array", "items": {"type": "string"}},
                        "proposal_ids": {"type": "array", "items": {"type": "string"}},
                        "obligation_ids": {"type": "array", "items": {"type": "string"}},
                        "proof_attempt_ids": {"type": "array", "items": {"type": "string"}}}}, [snapshot, workflow, node])}
    paths[path + "/reviews"] = {"post": operation(
        "reviewWorkflowGate", "Review the exact model/synthesis artifact; no source execution is authorized", True,
        {"type": "object", "additionalProperties": False, "required": ["snapshot_id", "spec_sha256", "artifact_id", "artifact_sha256", "actor", "decision", "note"],
         "properties": {"snapshot_id": {"type": "string"}, "spec_sha256": {"type": "string"},
                        "artifact_id": {"type": "string"}, "artifact_sha256": {"type": "string"},
                        "actor": {"type": "string"}, "decision": {"enum": ["approved", "needs_changes"]},
                        "note": {"type": "string"}}}, [snapshot, workflow, node])}
    paths["/api/v1/snapshots/{snapshot_id}/proposals"]["get"]["parameters"] = [snapshot]
    review_path = "/api/v1/snapshots/{snapshot_id}/proposals/{proposal_id}/reviews"
    paths[review_path]["get"] = operation(
        "listProposalReviews", "Read complete immutable proposal review history",
        parameters=[snapshot, {"name": "proposal_id", "in": "path", "required": True, "schema": {"type": "string"}}],
    )
    for endpoint in ("/api/v1/snapshots",
                     "/api/v1/snapshots/{snapshot_id}/attempts",
                     "/api/v1/snapshots/{snapshot_id}/proposals", review_path):
        paths[endpoint]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {"type": "array", "items": {"type": "object"}}
    for endpoint in ("/api/v1/snapshots/{snapshot_id}/proposals",
                     "/api/v1/snapshots/{snapshot_id}/proposals/{proposal_id}/reviews"):
        paths[endpoint]["post"]["responses"]["201"] = {**deepcopy(json_response), "description": "Immutable record created"}
    scenario_path = "/api/v1/snapshots/{snapshot_id}/scenarios"
    paths[scenario_path]["post"]["responses"].pop("202", None)
    paths[scenario_path]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "object", "required": ["snapshot_id", "model_id", "result_kind", "proved", "target_executed", "trace"],
        "properties": {"snapshot_id": {"type": "string"}, "model_id": {"type": "string"},
                       "result_kind": {"const": "simulated_model_example"}, "proved": {"const": False},
                       "target_executed": {"const": False}, "trace": {"type": "array", "items": {"type": "object"}}},
    }
    schemas = {
        "Job": {
            "type": "object", "required": ["id", "status"],
            "properties": {
                "id": {"type": ["string", "null"]},
                "status": {"enum": ["queued", "running", "complete", "failed"]},
                "kind": {"enum": ["verification", "attempt", "workflow"]},
                "snapshot_id": {"type": "string"}, "attempt_id": {"type": "string"},
                "result_status": {"type": "string"}, "error": {"type": "string"}, "reused": {"type": "boolean"},
            },
        },
        "CapturedSource": {
            "type": "object", "required": ["snapshot_id", "path", "sha256", "line_start", "line_end", "content", "captured"],
            "properties": {
                "snapshot_id": {"type": "string"}, "path": {"type": "string"}, "sha256": {"type": "string"},
                "line_start": {"type": "integer"}, "line_end": {"type": "integer"},
                "content": {"type": "string"}, "captured": {"const": True},
                "commit_sha": {"type": ["string", "null"]},
            },
        },
        "Obligation": {
            "type": "object", "required": ["id", "sha256", "snapshot_id", "artifact_id", "declaration", "context_source", "statement", "scope", "strategies"],
            "properties": {
                **{k: {"type": "string"} for k in ("id", "sha256", "snapshot_id", "artifact_id", "declaration", "context_source",
                                                  "theorem", "statement", "formula", "scope", "reference_lean_source")},
                "expected_result": {"enum": ["proved", "disproved"]},
                "strategies": {"type": "array", "items": {"enum": ["generated", "simplify", "decide"]}},
                "assumptions": {"type": "array", "items": {"type": "object"}},
                "evidence": {"type": "array", "items": {"type": "object"}},
                "dependencies": {"type": "array", "items": {"type": "string"}},
            },
        },
        "ObligationSet": {
            "type": "object", "required": ["snapshot_id", "obligations", "unsupported"],
            "properties": {"snapshot_id": {"type": "string"},
                           "obligations": {"type": "array", "items": {"$ref": "#/components/schemas/Obligation"}},
                           "unsupported": {"type": "array", "items": {"type": "object"}}},
        },
        "Attempt": {
            "type": "object", "required": ["id", "snapshot_id", "obligation_id", "obligation_sha256", "strategy", "status", "created_at", "completed_at"],
            "properties": {
                **{k: {"type": "string"} for k in ("id", "snapshot_id", "obligation_id", "obligation_sha256", "agent",
                                                  "strategy", "created_at", "completed_at", "statement", "scope")},
                "status": {"enum": ["proved", "disproved", "error", "timeout", "not_run"]},
                "checker": {"type": "object"}, "axioms": {"type": "array", "items": {"type": "string"}},
                "error": {"type": "string"}, "counterexample": {"type": ["object", "null"]},
                "promoted_to_verification": {"const": False},
            },
        },
        "Proposal": {
            "type": "object", "required": ["id", "snapshot_id", "kind", "title", "rationale", "content", "status", "checked", "applied"],
            "properties": {
                **{k: {"type": "string"} for k in ("id", "snapshot_id", "title", "rationale", "content", "created_at", "agent")},
                "kind": {"enum": ["requirement", "contract", "explanation", "repair"]},
                "status": {"const": "draft"}, "checked": {"const": False}, "applied": {"const": False},
                "evidence": {"type": "array", "items": {"type": "object"}},
                "review": {"oneOf": [{"$ref": "#/components/schemas/Review"}, {"type": "null"}]},
            },
        },
        "Review": {
            "type": "object", "required": ["id", "snapshot_id", "proposal_id", "decision", "note", "reviewer", "created_at"],
            "properties": {
                **{k: {"type": "string"} for k in ("id", "snapshot_id", "proposal_id", "note", "reviewer", "created_at", "effect")},
                "decision": {"enum": ["accepted", "rejected", "needs_changes"]},
            },
        },
    }
    response_types = {
        ("/api/v1/jobs/{job_id}", "get", "200"): "Job",
        ("/api/v1/snapshots", "post", "202"): "Job",
        ("/api/v1/snapshots/{snapshot_id}/sources", "get", "200"): "CapturedSource",
        ("/api/v1/snapshots/{snapshot_id}/obligations", "get", "200"): "ObligationSet",
        ("/api/v1/snapshots/{snapshot_id}/attempts", "post", "202"): "Job",
        ("/api/v1/snapshots/{snapshot_id}/attempts/{attempt_id}", "get", "200"): "Attempt",
        ("/api/v1/snapshots/{snapshot_id}/proposals", "post", "201"): "Proposal",
        (review_path, "post", "201"): "Review",
        ("/api/v1/snapshots/{snapshot_id}/verify", "post", "202"): "Job",
    }
    for (path, method, status), name in response_types.items():
        paths[path][method]["responses"][status]["content"]["application/json"]["schema"] = {"$ref": f"#/components/schemas/{name}"}
    for path, name in (("/api/v1/snapshots/{snapshot_id}/attempts", "Attempt"),
                       ("/api/v1/snapshots/{snapshot_id}/proposals", "Proposal"), (review_path, "Review")):
        paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {
            "type": "array", "items": {"$ref": f"#/components/schemas/{name}"}}
    for path in ("/api/v1/snapshots/{snapshot_id}/verification",):
        paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {"type": ["object", "null"]}
    return {
        "openapi": "3.1.0", "info": {"title": "code-form Agent API", "version": API_VERSION,
                                    "description": "Local evidence and proof tools for externally orchestrated agents."},
        "servers": [{"url": "http://127.0.0.1:7332", "description": "Configure your actual local server port."}],
        "paths": paths, "components": {"schemas": schemas, "securitySchemes": {
            "LocalToken": {"type": "apiKey", "in": "header", "name": "X-Codeform-Token",
                           "description": "Session-local token from /api/bootstrap; refresh after restart."}}},
    }
