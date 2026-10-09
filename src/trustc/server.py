"""TrustC Stage 6 — Local API server, streaming protocol, and artifact lifecycle."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Literal, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from trustc.contracts import (
    RULE_NAMES,
    ExampleSpec,
    PhasePayload,
    PhaseState,
    PhaseType,
    ResultPayload,
    RuleDocResponse,
    RuleId,
    RuleMeta,
    RunAccepted,
    RunCancelResponse,
    RunEvent,
    RunFailure,
    RunResult,
    RunStatusResponse,
    ServerMeta,
    normalize_source,
    spec_hash,
)
from trustc.generator import build_app
from trustc.harness import run_attack_harness
from trustc.parser import parse_text
from trustc.verifier import check_text, export_sarif

# Maximum allowed size for raw HTTP request body (1 MiB)
MAX_REQUEST_BODY_BYTES = 1048576
# Maximum allowed size for decoded specification UTF-8 text (256 KiB)
MAX_SPEC_TEXT_BYTES = 262144
# Maximum buffered events per run
MAX_RUN_EVENTS = 4096
# Maximum buffered bytes per run
MAX_RUN_EVENT_BYTES = 4194304
# Reserved bytes for terminal result payload (512 KiB)
RESERVED_TERMINAL_BYTES = 524288
# Retention time for completed runs/builds (15 minutes)
RETENTION_SECONDS = 900.0


# ---------------------------------------------------------------------------
# Server State & Storage Records
# ---------------------------------------------------------------------------

class BuildRecord:
    def __init__(
        self,
        build_id: str,
        spec_hash_val: str,
        spec_version: int,
        artifact_dir: Path,
        zip_path: Path,
        compiler_version: str = "0.1.0",
        template_version: str = "1.0.0",
    ):
        self.build_id = build_id
        self.spec_hash = spec_hash_val
        self.spec_version = spec_version
        self.artifact_dir = artifact_dir
        self.zip_path = zip_path
        self.compiler_version = compiler_version
        self.template_version = template_version
        self.created_at = time.time()


class RunRecord:
    def __init__(
        self,
        run_id: str,
        spec_version: int,
        spec_hash_val: str,
        kind: str,  # "build" | "attack"
    ):
        self.run_id = run_id
        self.spec_version = spec_version
        self.spec_hash = spec_hash_val
        self.kind = kind
        self.state: str = "running"  # "running" | "terminal"
        self.result: Optional[RunResult] = None
        self.events: List[RunEvent] = []
        self.total_event_bytes: int = 0
        self.seq_counter: int = 0
        self.created_at: float = time.time()
        self.completed_at: Optional[float] = None
        self.cancelled: bool = False
        self.cancel_event: threading.Event = threading.Event()
        self.lock = threading.Lock()
        self.listeners: List[asyncio.Queue] = []
        self.worker_thread: Optional[threading.Thread] = None

    def add_event(self, payload: Any) -> Optional[RunEvent]:
        with self.lock:
            is_result = getattr(payload, "type", "") == "result"
            candidate_seq = self.seq_counter + 1
            ev = RunEvent(
                schemaVersion=2,
                runId=self.run_id,
                specVersion=self.spec_version,
                specHash=self.spec_hash,
                seq=candidate_seq,
                payload=payload,
            )
            ev_bytes = len(ev.model_dump_json(by_alias=True).encode("utf-8"))

            if is_result:
                # Terminal result: enforce hard maximum cap
                if (self.total_event_bytes + ev_bytes) > MAX_RUN_EVENT_BYTES:
                    return None
            else:
                # Non-terminal event: enforce event count and byte budget
                # reserving space for terminal result
                over_budget = (
                    self.total_event_bytes + ev_bytes + RESERVED_TERMINAL_BYTES
                ) > MAX_RUN_EVENT_BYTES
                if len(self.events) >= MAX_RUN_EVENTS - 1 or over_budget:
                    return None

            self.seq_counter = candidate_seq
            self.total_event_bytes += ev_bytes
            self.events.append(ev)

            # Notify active listeners with bounded queue handling
            for q in list(self.listeners):
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                        q.put_nowait(ev)
                    except Exception:
                        pass
                except Exception:
                    pass
            return ev

    def is_expired(self, current_time: float) -> bool:
        if self.completed_at is not None:
            return (current_time - self.completed_at) > RETENTION_SECONDS
        return False


class ServerState:
    def __init__(self, workspace_dir: Optional[Path] = None, port: int = 8787):
        self.session_id: str = str(uuid.uuid4())
        self.port: int = port
        self.workspace_dir: Path = (
            workspace_dir or Path(tempfile.mkdtemp(prefix="trustc_server_workspace_"))
        )
        self.staging_dir: Path = self.workspace_dir / "staging"
        self.builds_dir: Path = self.workspace_dir / "builds"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.builds_dir.mkdir(parents=True, exist_ok=True)

        self.worker_lock: threading.Lock = threading.Lock()
        self.active_run_id: Optional[str] = None
        self.runs: Dict[str, RunRecord] = {}
        self.builds: Dict[str, BuildRecord] = {}
        self.expired_run_ids: Dict[str, float] = {}
        self.expired_build_ids: Dict[str, float] = {}

    def cleanup_expired(self, now: Optional[float] = None) -> None:
        """Enforce bounded retention on runs and builds, pruning disk artifacts."""
        if now is None:
            now = time.time()

        # Prune old tombstones (> 1 hour)
        cutoff_tombstones = now - 3600.0
        self.expired_run_ids = {
            rid: exp for rid, exp in self.expired_run_ids.items() if exp > cutoff_tombstones
        }
        self.expired_build_ids = {
            bid: exp for bid, exp in self.expired_build_ids.items() if exp > cutoff_tombstones
        }

        # 1. Prune expired runs
        expired_runs = [rid for rid, r in list(self.runs.items()) if r.is_expired(now)]
        for rid in expired_runs:
            self.runs.pop(rid, None)
            self.expired_run_ids[rid] = now

        # 2. Prune expired builds and delete their artifacts on disk
        expired_builds = [
            bid for bid, b in list(self.builds.items())
            if (now - b.created_at) > RETENTION_SECONDS
        ]
        for bid in expired_builds:
            b = self.builds.pop(bid, None)
            self.expired_build_ids[bid] = now
            if b:
                shutil.rmtree(b.artifact_dir, ignore_errors=True)
                try:
                    b.zip_path.unlink(missing_ok=True)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Rule Documentation & Fixtures Cache
# ---------------------------------------------------------------------------

RULES_DOC_DATA: Dict[str, Dict[str, Any]] = {
    "TC-001": {
        "id": "TC-001",
        "name": "AUTH-REQUIRED",
        "checks": (
            "Every endpoint must declare an explicit authentication policy "
            "('auth: required' or 'auth: public')."
        ),
        "flaw": "Missing explicit authentication decision ('auth: required' or 'auth: public').",
        "fixType": "diff",
        "refused": "endpoint GET /trips/{id}:\n  resource: Trip\n  returns: Trip",
        "accepted": (
            "endpoint GET /trips/{id}:\n  resource: Trip\n  auth: required\n  returns: Trip"
        ),
    },
    "TC-002": {
        "id": "TC-002",
        "name": "OWNERSHIP-CHECK",
        "checks": (
            "Authorization policies on owned resources must enforce owner equality or explicit "
            "waivers. Unsupported role checks, public owned creation, and waivers on User "
            "are rejected."
        ),
        "flaw": (
            "Broken object level authorization (BOLA/IDOR) allowing cross-tenant data leakage "
            "or tampering."
        ),
        "fixType": "prompt",
        "refused": (
            "endpoint GET /trips/{id}:\n"
            "  resource: Trip\n"
            "  auth: required\n"
            "  authorize: role == 'admin'\n"
            "  returns: Trip"
        ),
        "accepted": (
            "endpoint GET /trips/{id}:\n"
            "  resource: Trip\n"
            "  auth: required\n"
            "  authorize: owner == current_user.id\n"
            "  returns: Trip"
        ),
    },
    "TC-003": {
        "id": "TC-003",
        "name": "SENSITIVE-LEAK",
        "checks": (
            "Credential fields can never be returned in responses. Sensitive fields require "
            "explicit expose declarations in responses."
        ),
        "flaw": "Exposure of secrets, password hashes, or sensitive PII in API responses.",
        "fixType": "diff",
        "refused": "endpoint GET /users/{id}:\n  resource: User\n  auth: required\n  returns: User",
        "accepted": (
            "endpoint GET /users/{id}:\n"
            "  resource: User\n"
            "  auth: required\n"
            "  returns: {id, username, email}"
        ),
    },
    "TC-004": {
        "id": "TC-004",
        "name": "MASS-ASSIGNMENT",
        "checks": (
            "Primary keys, ownership edges, and credential fields cannot be client-writable "
            "in request bodies."
        ),
        "flaw": (
            "Mass assignment / parameter tampering allowing client to overwrite ID, owner, "
            "or credentials."
        ),
        "fixType": "diff",
        "refused": (
            "endpoint POST /trips:\n"
            "  resource: Trip\n"
            "  auth: required\n"
            "  body: {title, owner_id}\n"
            "  returns: Trip"
        ),
        "accepted": (
            "endpoint POST /trips:\n"
            "  resource: Trip\n"
            "  auth: required\n"
            "  body: {title}\n"
            "  returns: Trip"
        ),
    },
    "TC-005": {
        "id": "TC-005",
        "name": "SECRET-SCOPE",
        "checks": (
            "Generated services require DB_URL and JWT_SECRET references in the secrets block."
        ),
        "flaw": (
            "Missing environment secret references causing undeclared environment dependencies "
            "or hardcoded secrets."
        ),
        "fixType": "diff",
        "refused": "secrets:\n  env API_KEY",
        "accepted": "secrets:\n  env DB_URL\n  env JWT_SECRET",
    },
}


def _find_fixture_content(name: str) -> str:
    # 1. Try bundled package resources in trustc.examples
    try:
        from importlib.resources import files
        pkg_example = files("trustc").joinpath("examples").joinpath(name)
        if pkg_example.is_file():
            return pkg_example.read_text(encoding="utf-8")
    except Exception:
        pass

    # 2. Check candidate filesystem paths for local repo checkouts
    candidates = [
        Path(f"tests/fixtures/{name}"),
        Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / name,
        Path(__file__).resolve().parent / "examples" / name,
        Path(f"TrustC-Stage-Pack-v3/fixtures/{name}"),
        Path(__file__).resolve().parent.parent.parent / "TrustC-Stage-Pack-v3" / "fixtures" / name,
    ]
    for c in candidates:
        if c.is_file():
            return c.read_text(encoding="utf-8")
    return ""


def get_default_static_dir() -> Optional[Path]:
    """Locate bundled or repository static UI assets."""
    # 1. Check bundled package directory trustc/ui_dist
    try:
        from importlib.resources import files
        pkg_ui = files("trustc").joinpath("ui_dist")
        pkg_index = pkg_ui.joinpath("index.html")
        if pkg_index.is_file():
            p = Path(str(pkg_ui))
            if p.is_dir() and (p / "index.html").is_file():
                return p
    except Exception:
        pass

    # 2. Check trustc/ui_dist relative to server.py
    direct_ui = Path(__file__).resolve().parent / "ui_dist"
    if direct_ui.is_dir() and (direct_ui / "index.html").is_file():
        return direct_ui

    # 3. Check local repo checkout ui/dist
    repo_ui_dist = Path(__file__).resolve().parent.parent.parent / "ui" / "dist"
    if repo_ui_dist.is_dir() and (repo_ui_dist / "index.html").is_file():
        return repo_ui_dist

    return None


async def _read_json_body(request: Request) -> tuple[Any, Optional[JSONResponse]]:
    """Read request body safely enforcing MAX_REQUEST_BODY_BYTES and parse JSON."""
    try:
        body_bytes = await request.body()
    except Exception as exc:
        return None, JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "READ_ERROR",
                    "message": f"Failed to read request body: {exc}",
                }
            },
        )
    if len(body_bytes) > MAX_REQUEST_BODY_BYTES:
        return None, JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "Request body exceeds maximum size of 1 MiB",
                }
            },
        )
    try:
        data = json.loads(body_bytes.decode("utf-8"))
        return data, None
    except UnicodeDecodeError:
        return None, JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_ENCODING",
                    "message": "Request body must be valid UTF-8",
                }
            },
        )
    except Exception:
        return None, JSONResponse(
            status_code=400,
            content={"error": {"code": "MALFORMED_JSON", "message": "Invalid JSON body"}},
        )


def _validate_spec_payload(body: Any) -> tuple[str, int, Optional[JSONResponse]]:
    """Validate request JSON body shape and fields for check/build/attack."""
    if not isinstance(body, dict):
        return "", 0, JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_PAYLOAD",
                    "message": "Request body must be a JSON object",
                }
            },
        )
    if "spec" not in body:
        return "", 0, JSONResponse(
            status_code=400,
            content={"error": {"code": "MISSING_SPEC", "message": "Field 'spec' is required"}},
        )
    raw_spec = body.get("spec")
    if not isinstance(raw_spec, str):
        return "", 0, JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_SPEC_TYPE",
                    "message": "Field 'spec' must be a string",
                }
            },
        )
    if len(raw_spec.encode("utf-8")) > MAX_SPEC_TEXT_BYTES:
        return "", 0, JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": (
                        "Specification exceeds maximum allowed size of "
                        f"{MAX_SPEC_TEXT_BYTES} bytes"
                    ),
                }
            },
        )
    spec_ver = 0
    if "specVersion" in body:
        sv = body["specVersion"]
        if type(sv) is bool or not isinstance(sv, int) or sv < 0:
            return "", 0, JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_SPEC_VERSION",
                        "message": (
                            "Field 'specVersion' must be a non-negative integer"
                        ),
                    }
                },
            )
        spec_ver = sv
    return raw_spec, spec_ver, None


def load_example_specs() -> List[ExampleSpec]:
    return [
        ExampleSpec(
            id="F1",
            title="Trip Planner (Flawed)",
            subtitle="Missing auth (TC-001) & sensitive leak (TC-003)",
            expectedCheck="fail",
            expectedReview=False,
            spec=_find_fixture_content("F1.trust"),
        ),
        ExampleSpec(
            id="F2",
            title="Trip Planner (Owner-protected)",
            subtitle="Owner-protected Trip access and self-only User access",
            expectedCheck="pass",
            expectedReview=False,
            spec=_find_fixture_content("F2.trust"),
        ),
        ExampleSpec(
            id="F3",
            title="Trip Planner (Ownership Waiver)",
            subtitle="Explicit waiver on PUT /trips/{id}/visibility",
            expectedCheck="pass",
            expectedReview=True,
            spec=_find_fixture_content("F3.trust"),
        ),
        ExampleSpec(
            id="F4",
            title="Syntax Error Demo",
            subtitle="Syntax error at line 23 column 25",
            expectedCheck="fail",
            expectedReview=False,
            spec=_find_fixture_content("F4.trust"),
        ),
        ExampleSpec(
            id="F5",
            title="Trip Planner (Mass Assignment)",
            subtitle="Server-controlled owner_id in body (TC-004)",
            expectedCheck="fail",
            expectedReview=False,
            spec=_find_fixture_content("F5.trust"),
        ),
        ExampleSpec(
            id="F6",
            title="Trip Planner (Missing Secrets)",
            subtitle="Missing JWT_SECRET declaration (TC-005)",
            expectedCheck="fail",
            expectedReview=False,
            spec=_find_fixture_content("F6.trust"),
        ),
    ]


# ---------------------------------------------------------------------------
# FastAPI Application Factory
# ---------------------------------------------------------------------------

def create_app(
    workspace_dir: Optional[Path] = None,
    port: int = 8787,
    static_dir: Optional[Path] = None,
) -> FastAPI:
    if static_dir is None:
        static_dir = get_default_static_dir()

    state = ServerState(workspace_dir=workspace_dir, port=port)
    app = FastAPI(
        title="TrustC Local Server",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    app.state.trustc = state

    # -------------------------------------------------------------------------
    # Security Middleware
    # -------------------------------------------------------------------------
    @app.middleware("http")
    async def security_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 1. Host Validation
        raw_host = request.headers.get("host", "").split(":")[0].lower()
        allowed_hosts = {"localhost", "127.0.0.1", "::1", "[::1]", "testserver"}
        if raw_host and raw_host not in allowed_hosts:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "FORBIDDEN_HOST",
                        "message": f"Host '{raw_host}' not allowed",
                    }
                },
            )

        # 2. Origin Validation for mutating requests
        origin = request.headers.get("origin")
        if request.method in ("POST", "PUT", "DELETE"):
            if origin:
                parsed_origin_host = origin.split("://")[-1].split(":")[0].lower()
                if parsed_origin_host not in allowed_hosts:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": {
                                "code": "FORBIDDEN_ORIGIN",
                                "message": f"Origin '{origin}' not allowed",
                            }
                        },
                    )

        # 3. Content-Length Header check
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                cl_val = int(content_length)
                if cl_val < 0:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "INVALID_CONTENT_LENGTH",
                                "message": "Content-Length header must be non-negative",
                            }
                        },
                    )
                if cl_val > MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "Request body exceeds maximum size of 1 MiB",
                            }
                        },
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_CONTENT_LENGTH",
                            "message": "Malformed Content-Length header",
                        }
                    },
                )

        # Preflight OPTIONS handler
        if request.method == "OPTIONS":
            preflight = Response(status_code=204)
            if origin:
                preflight.headers["Access-Control-Allow-Origin"] = origin
                preflight.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
                preflight.headers["Access-Control-Allow-Headers"] = "Content-Type, Last-Event-ID"
            return preflight

        response = await call_next(request)

        # Add CORS headers if origin is valid loopback
        if origin:
            parsed_origin_host = origin.split("://")[-1].split(":")[0].lower()
            if parsed_origin_host in allowed_hosts:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Last-Event-ID"

        return response

    # -------------------------------------------------------------------------
    # Route: GET /api/meta
    # -------------------------------------------------------------------------
    @app.get("/api/meta")
    async def get_meta() -> ServerMeta:
        return ServerMeta(
            schemaVersion=2,
            sessionId=state.session_id,
            version="0.1.0",
            port=state.port,
            target="fastapi",
            rules=[RuleMeta(id=r, name=RULE_NAMES[r]) for r in RuleId],
        )

    # -------------------------------------------------------------------------
    # Route: GET /api/examples
    # -------------------------------------------------------------------------
    @app.get("/api/examples")
    async def get_examples() -> List[ExampleSpec]:
        return load_example_specs()

    # -------------------------------------------------------------------------
    # Route: GET /api/rules/{id}
    # -------------------------------------------------------------------------
    @app.get("/api/rules/{rule_id}")
    async def get_rule_details(rule_id: str) -> Any:
        norm_id = rule_id.upper()
        if norm_id not in RULES_DOC_DATA:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "UNKNOWN_RULE",
                        "message": f"Unknown rule ID '{rule_id}'",
                    }
                },
            )
        data = RULES_DOC_DATA[norm_id]
        return RuleDocResponse(
            id=data["id"],
            name=data["name"],
            checks=data["checks"],
            flaw=data["flaw"],
            fixType=data["fixType"],
            refused=data["refused"],
            accepted=data["accepted"],
        )

    # -------------------------------------------------------------------------
    # Route: POST /api/check
    # -------------------------------------------------------------------------
    @app.post("/api/check")
    async def post_check(request: Request) -> Any:
        ct = request.headers.get("content-type", "").lower()
        if "application/json" not in ct:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_CONTENT_TYPE",
                        "message": "Expected Content-Type: application/json",
                    }
                },
            )

        body, err_resp = await _read_json_body(request)
        if err_resp:
            return err_resp

        raw_spec, spec_ver, err_resp = _validate_spec_payload(body)
        if err_resp:
            return err_resp

        fmt = request.query_params.get("format", "json")

        # 5-second deadline for check
        try:
            res = await asyncio.wait_for(
                asyncio.to_thread(check_text, raw_spec, spec_ver),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "DEADLINE_EXCEEDED",
                        "message": "Check operation timed out after 5.0 seconds",
                    }
                },
            )

        if fmt == "sarif":
            sarif = export_sarif(res, "spec.trust")
            return JSONResponse(content=sarif)

        return JSONResponse(content=res.model_dump(by_alias=True))

    # -------------------------------------------------------------------------
    # Route: POST /api/build
    # -------------------------------------------------------------------------
    @app.post("/api/build", status_code=202)
    async def post_build(request: Request) -> Any:
        ct = request.headers.get("content-type", "").lower()
        if "application/json" not in ct:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_CONTENT_TYPE",
                        "message": "Expected Content-Type: application/json",
                    }
                },
            )

        body, err_resp = await _read_json_body(request)
        if err_resp:
            return err_resp

        raw_spec, spec_ver, err_resp = _validate_spec_payload(body)
        if err_resp:
            return err_resp

        target = body.get("target", "fastapi")
        if not isinstance(target, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_TARGET",
                        "message": "Field 'target' must be a string",
                    }
                },
            )
        if target != "fastapi":
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "UNSUPPORTED_TARGET",
                        "message": f"Unsupported target '{target}'",
                    }
                },
            )

        norm_spec = normalize_source(raw_spec)
        shash = spec_hash(norm_spec)

        # Acquire atomic worker lock
        acquired = state.worker_lock.acquire(blocking=False)
        if not acquired:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "SERVER_BUSY",
                        "message": "A build or attack job is currently executing",
                    }
                },
            )

        run_id = str(uuid.uuid4())
        state.active_run_id = run_id
        run_record = RunRecord(
            run_id=run_id,
            spec_version=spec_ver,
            spec_hash_val=shash,
            kind="build",
        )
        state.runs[run_id] = run_record

        # Worker thread for build job
        def build_worker() -> None:
            t0 = time.time()
            BUILD_TIMEOUT = 20.0
            staging_run_dir = state.staging_dir / run_id
            staging_run_dir.mkdir(parents=True, exist_ok=True)
            staging_app_dir = staging_run_dir / "app"
            final_result: Optional[RunResult] = None

            try:
                # 1. Pre-verify check
                run_record.add_event(
                    PhasePayload(phase=PhaseType.VERIFY, state=PhaseState.STARTED)
                )
                check_res = check_text(norm_spec, spec_ver)
                run_record.add_event(
                    PhasePayload(phase=PhaseType.VERIFY, state=PhaseState.FINISHED)
                )

                if not check_res.ok:
                    ms = int((time.time() - t0) * 1000)
                    fail_code: Literal[1, 2] = 1 if check_res.exit_code == 1 else 2
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="build",
                        ms=ms,
                        kind="build",
                        status="refused" if fail_code == 1 else "invalid_spec",
                        exitCode=fail_code,
                        specErrors=check_res.spec_errors,
                        diagnostics=check_res.diagnostics,
                    )
                    return

                # Check cancellation or timeout
                if run_record.cancelled or (time.time() - t0) > BUILD_TIMEOUT:
                    ms = int((time.time() - t0) * 1000)
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="build",
                        ms=ms,
                        kind="build",
                        status="cancelled",
                        exitCode=130,
                        specErrors=[],
                        diagnostics=[],
                    )
                    return

                # 2. Render phase
                run_record.add_event(
                    PhasePayload(phase=PhaseType.RENDER, state=PhaseState.STARTED)
                )
                spec_file = staging_run_dir / "spec.trust"
                spec_file.write_text(norm_spec, encoding="utf-8")
                build_res = build_app(
                    spec_file,
                    staging_app_dir,
                    spec_version=spec_ver,
                )
                run_record.add_event(
                    PhasePayload(phase=PhaseType.RENDER, state=PhaseState.FINISHED)
                )

                # Check cancellation or timeout before publish
                if run_record.cancelled or (time.time() - t0) > BUILD_TIMEOUT:
                    ms = int((time.time() - t0) * 1000)
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="build",
                        ms=ms,
                        kind="build",
                        status="cancelled",
                        exitCode=130,
                        specErrors=[],
                        diagnostics=[],
                    )
                    return

                # 3. Publish phase
                run_record.add_event(
                    PhasePayload(phase=PhaseType.PUBLISH, state=PhaseState.STARTED)
                )
                build_id = build_res.build_id
                published_build_dir = state.builds_dir / build_id
                if published_build_dir.exists():
                    shutil.rmtree(published_build_dir, ignore_errors=True)
                shutil.copytree(staging_app_dir, published_build_dir)

                # Generate out.zip with relative paths only
                zip_path = state.builds_dir / f"{build_id}.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    seen_entries: set[str] = set()
                    for f in build_res.files:
                        rel_path = f.path.replace("\\", "/").lstrip("/")
                        if rel_path not in seen_entries:
                            seen_entries.add(rel_path)
                            zf.writestr(rel_path, f.content)
                    man_path = published_build_dir / "trustc-manifest.json"
                    if man_path.exists() and "trustc-manifest.json" not in seen_entries:
                        seen_entries.add("trustc-manifest.json")
                        zf.writestr("trustc-manifest.json", man_path.read_text(encoding="utf-8"))
                    rep_path = published_build_dir / "trustc-report.json"
                    if rep_path.exists() and "trustc-report.json" not in seen_entries:
                        seen_entries.add("trustc-report.json")
                        zf.writestr("trustc-report.json", rep_path.read_text(encoding="utf-8"))

                # Check cancellation atomically right before committing build
                with run_record.lock:
                    if run_record.cancelled or (time.time() - t0) > BUILD_TIMEOUT:
                        shutil.rmtree(published_build_dir, ignore_errors=True)
                        try:
                            zip_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        ms = int((time.time() - t0) * 1000)
                        final_result = RunFailure(
                            schemaVersion=2,
                            specVersion=spec_ver,
                            specHash=shash,
                            command="build",
                            ms=ms,
                            kind="build",
                            status="cancelled",
                            exitCode=130,
                            specErrors=[],
                            diagnostics=[],
                        )
                        return

                    # Index published build
                    build_rec = BuildRecord(
                        build_id=build_id,
                        spec_hash_val=shash,
                        spec_version=spec_ver,
                        artifact_dir=published_build_dir,
                        zip_path=zip_path,
                    )
                    state.builds[build_id] = build_rec

                run_record.add_event(
                    PhasePayload(phase=PhaseType.PUBLISH, state=PhaseState.FINISHED)
                )
                final_result = build_res

            except Exception as exc:
                ms = int((time.time() - t0) * 1000)
                final_result = RunFailure(
                    schemaVersion=2,
                    specVersion=spec_ver,
                    specHash=shash,
                    command="build",
                    ms=ms,
                    kind="build",
                    status="error",
                    exitCode=3,
                    specErrors=[],
                    diagnostics=[],
                    error={"code": "BUILD_FAILED", "message": str(exc)},
                )
            finally:
                # 1. Clean staging directory
                shutil.rmtree(staging_run_dir, ignore_errors=True)
                # 2. Release worker lock and active run id FIRST
                state.active_run_id = None
                try:
                    state.worker_lock.release()
                except RuntimeError:
                    pass

                # 3. Atomically finalize run record and emit single terminal ResultPayload
                if final_result is None:
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="build",
                        ms=int((time.time() - t0) * 1000),
                        kind="build",
                        status="error",
                        exitCode=3,
                        specErrors=[],
                        diagnostics=[],
                        error={
                            "code": "UNKNOWN_ERROR",
                            "message": "Worker terminated unexpectedly",
                        },
                    )
                with run_record.lock:
                    run_record.result = final_result
                    run_record.completed_at = time.time()
                    run_record.state = "terminal"
                run_record.add_event(ResultPayload(result=final_result))

        th = threading.Thread(target=build_worker, daemon=True)
        run_record.worker_thread = th
        th.start()

        return JSONResponse(
            status_code=202,
            content=RunAccepted(
                runId=run_id,
                specVersion=spec_ver,
                specHash=shash,
            ).model_dump(by_alias=True),
        )

    # -------------------------------------------------------------------------
    # Route: POST /api/attack
    # -------------------------------------------------------------------------
    @app.post("/api/attack", status_code=202)
    async def post_attack(request: Request) -> Any:
        ct = request.headers.get("content-type", "").lower()
        if "application/json" not in ct:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_CONTENT_TYPE",
                        "message": "Expected Content-Type: application/json",
                    }
                },
            )

        body, err_resp = await _read_json_body(request)
        if err_resp:
            return err_resp

        raw_spec, spec_ver, err_resp = _validate_spec_payload(body)
        if err_resp:
            return err_resp

        norm_spec = normalize_source(raw_spec)
        shash = spec_hash(norm_spec)
        req_build_id = body.get("buildId")

        if req_build_id is not None and not isinstance(req_build_id, str):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_BUILD_ID",
                        "message": "Field 'buildId' must be a string",
                    }
                },
            )

        # Verify buildId if supplied
        if req_build_id:
            state.cleanup_expired()
            if req_build_id not in state.builds:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "code": "UNKNOWN_BUILD",
                            "message": f"Build '{req_build_id}' not found",
                        }
                    },
                )
            target_build = state.builds[req_build_id]
            if target_build.spec_hash != shash:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": {
                            "code": "SPEC_HASH_MISMATCH",
                            "message": (
                                f"Build specHash '{target_build.spec_hash}' does not match "
                                f"current specHash '{shash}'"
                            ),
                        }
                    },
                )

        # Acquire atomic worker lock
        acquired = state.worker_lock.acquire(blocking=False)
        if not acquired:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "SERVER_BUSY",
                        "message": "A build or attack job is currently executing",
                    }
                },
            )

        run_id = str(uuid.uuid4())
        state.active_run_id = run_id
        run_record = RunRecord(
            run_id=run_id,
            spec_version=spec_ver,
            spec_hash_val=shash,
            kind="attack",
        )
        state.runs[run_id] = run_record

        # Worker thread for attack job
        def attack_worker() -> None:
            t0 = time.time()
            ATTACK_TIMEOUT = 60.0
            staging_run_dir = state.staging_dir / run_id
            staging_run_dir.mkdir(parents=True, exist_ok=True)
            staging_app_dir = staging_run_dir / "app"
            final_result: Optional[RunResult] = None

            def on_event(ev: RunEvent) -> None:
                # Discard terminal result from harness callback; server owns terminal emission
                if getattr(ev.payload, "type", "") == "result":
                    return
                run_record.add_event(ev.payload)

            try:
                # 1. Pre-verify check
                check_res = check_text(norm_spec, spec_ver)
                if not check_res.ok:
                    ms = int((time.time() - t0) * 1000)
                    fail_code: Literal[1, 2] = 1 if check_res.exit_code == 1 else 2
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="attack spec.trust",
                        ms=ms,
                        kind="attack",
                        status="refused" if fail_code == 1 else "invalid_spec",
                        exitCode=fail_code,
                        specErrors=check_res.spec_errors,
                        diagnostics=check_res.diagnostics,
                    )
                    return

                if run_record.cancelled:
                    ms = int((time.time() - t0) * 1000)
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="attack spec.trust",
                        ms=ms,
                        kind="attack",
                        status="cancelled",
                        exitCode=130,
                        specErrors=[],
                        diagnostics=[],
                    )
                    return

                # Parse program
                program = parse_text(norm_spec)

                # 2. Prepare artifact in staging
                if req_build_id:
                    target_build = state.builds[req_build_id]
                    shutil.copytree(
                        target_build.artifact_dir,
                        staging_app_dir,
                        ignore=shutil.ignore_patterns("*.zip"),
                    )
                else:
                    spec_file = staging_run_dir / "spec.trust"
                    spec_file.write_text(norm_spec, encoding="utf-8")
                    build_app(
                        spec_file,
                        staging_app_dir,
                        spec_version=spec_ver,
                    )

                if run_record.cancelled:
                    ms = int((time.time() - t0) * 1000)
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="attack spec.trust",
                        ms=ms,
                        kind="attack",
                        status="cancelled",
                        exitCode=130,
                        specErrors=[],
                        diagnostics=[],
                    )
                    return

                # 3. Execute attack harness
                res = run_attack_harness(
                    program=program,
                    artifact_dir=staging_app_dir,
                    event_callback=on_event,
                    cancel_event=run_record.cancel_event,
                    timeout_seconds=ATTACK_TIMEOUT,
                    spec_version=spec_ver,
                    spec_hash=shash,
                    run_id=run_id,
                    command="attack spec.trust",
                )
                final_result = res

            except Exception as exc:
                ms = int((time.time() - t0) * 1000)
                final_result = RunFailure(
                    schemaVersion=2,
                    specVersion=spec_ver,
                    specHash=shash,
                    command="attack spec.trust",
                    ms=ms,
                    kind="attack",
                    status="error",
                    exitCode=3,
                    specErrors=[],
                    diagnostics=[],
                    error={"code": "ATTACK_FAILED", "message": str(exc)},
                )
            finally:
                # 1. Clean staging directory
                shutil.rmtree(staging_run_dir, ignore_errors=True)
                # 2. Release worker lock and clear active run id FIRST
                state.active_run_id = None
                try:
                    state.worker_lock.release()
                except RuntimeError:
                    pass

                # 3. Check cancellation atomically under lock
                if final_result is None:
                    final_result = RunFailure(
                        schemaVersion=2,
                        specVersion=spec_ver,
                        specHash=shash,
                        command="attack spec.trust",
                        ms=int((time.time() - t0) * 1000),
                        kind="attack",
                        status="error",
                        exitCode=3,
                        specErrors=[],
                        diagnostics=[],
                        error={
                            "code": "UNKNOWN_ERROR",
                            "message": "Worker terminated unexpectedly",
                        },
                    )
                with run_record.lock:
                    if run_record.cancelled and getattr(final_result, "status", "") != "cancelled":
                        final_result = RunFailure(
                            schemaVersion=2,
                            specVersion=spec_ver,
                            specHash=shash,
                            command="attack spec.trust",
                            ms=int((time.time() - t0) * 1000),
                            kind="attack",
                            status="cancelled",
                            exitCode=130,
                            specErrors=[],
                            diagnostics=[],
                        )
                    run_record.result = final_result
                    run_record.completed_at = time.time()
                    run_record.state = "terminal"

                # 4. Emit single terminal ResultPayload
                run_record.add_event(ResultPayload(result=final_result))

        th = threading.Thread(target=attack_worker, daemon=True)
        run_record.worker_thread = th
        th.start()

        return JSONResponse(
            status_code=202,
            content=RunAccepted(
                runId=run_id,
                specVersion=spec_ver,
                specHash=shash,
            ).model_dump(by_alias=True),
        )

    # -------------------------------------------------------------------------
    # Route: GET /api/runs/{runId}/events (SSE)
    # -------------------------------------------------------------------------
    @app.get("/api/runs/{run_id}/events")
    async def get_run_events(run_id: str, request: Request) -> Any:
        now = time.time()
        if run_id not in state.runs:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "UNKNOWN_RUN", "message": f"Run '{run_id}' not found"}},
            )

        run = state.runs[run_id]
        if run.is_expired(now):
            return JSONResponse(
                status_code=410,
                content={
                    "error": {
                        "code": "EXPIRED_RUN",
                        "message": f"Run '{run_id}' history has expired",
                    }
                },
            )

        last_event_id = request.headers.get("last-event-id")
        cursor_seq = 0
        if last_event_id:
            parts = last_event_id.split(":")
            if len(parts) == 2:
                cur_run, cur_seq_s = parts
                if cur_run != run_id:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "INVALID_CURSOR",
                                "message": "Last-Event-ID runId mismatch",
                            }
                        },
                    )
                try:
                    cursor_seq = int(cur_seq_s)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "INVALID_CURSOR",
                                "message": "Invalid sequence in Last-Event-ID",
                            }
                        },
                    )
            elif len(parts) == 1:
                try:
                    cursor_seq = int(parts[0])
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "INVALID_CURSOR",
                                "message": "Invalid sequence in Last-Event-ID",
                            }
                        },
                    )
            else:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_CURSOR",
                            "message": "Malformed Last-Event-ID header",
                        }
                    },
                )

        async def sse_generator() -> AsyncGenerator[str, None]:
            listener_queue: asyncio.Queue = asyncio.Queue(maxsize=256)
            with run.lock:
                run.listeners.append(listener_queue)
                replay_events = [ev for ev in run.events if ev.seq > cursor_seq]

            try:
                # 1. Replay buffered events
                for ev in replay_events:
                    payload_json = ev.model_dump_json(by_alias=True)
                    yield f"event: trustc\nid: {run_id}:{ev.seq}\ndata: {payload_json}\n\n"

                all_done = (
                    run.state == "terminal"
                    and (
                        not run.events
                        or (replay_events and replay_events[-1].seq == run.events[-1].seq)
                    )
                )
                if all_done:
                    return

                # 2. Stream live events with 5s heartbeats
                while True:
                    try:
                        ev = await asyncio.wait_for(listener_queue.get(), timeout=5.0)
                        if ev.seq > cursor_seq and (
                            not replay_events or ev.seq > replay_events[-1].seq
                        ):
                            payload_json = ev.model_dump_json(by_alias=True)
                            yield f"event: trustc\nid: {run_id}:{ev.seq}\ndata: {payload_json}\n\n"
                            if getattr(ev.payload, "type", "") == "result":
                                break
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        if run.state == "terminal":
                            break

            finally:
                with run.lock:
                    if listener_queue in run.listeners:
                        run.listeners.remove(listener_queue)

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # -------------------------------------------------------------------------
    # Route: GET /api/runs/{runId}
    # -------------------------------------------------------------------------
    @app.get("/api/runs/{run_id}")
    async def get_run_status(run_id: str) -> Any:
        now = time.time()
        state.cleanup_expired(now)
        if run_id in state.expired_run_ids:
            return JSONResponse(
                status_code=410,
                content={
                    "error": {"code": "EXPIRED_RUN", "message": f"Run '{run_id}' has expired"}
                },
            )
        if run_id not in state.runs:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {"code": "UNKNOWN_RUN", "message": f"Run '{run_id}' not found"}
                },
            )

        run = state.runs[run_id]
        if run.is_expired(now):
            return JSONResponse(
                status_code=410,
                content={
                    "error": {"code": "EXPIRED_RUN", "message": f"Run '{run_id}' has expired"}
                },
            )

        resp = RunStatusResponse(
            runId=run.run_id,
            state="terminal" if run.state == "terminal" else "running",
            result=run.result,
        )
        return JSONResponse(content=resp.model_dump(by_alias=True))

    # -------------------------------------------------------------------------
    # Route: DELETE /api/runs/{runId}
    # -------------------------------------------------------------------------
    @app.delete("/api/runs/{run_id}")
    async def delete_run(run_id: str) -> Any:
        if run_id not in state.runs:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "UNKNOWN_RUN", "message": f"Run '{run_id}' not found"}},
            )

        run = state.runs[run_id]
        if run.state == "terminal":
            return Response(status_code=204)

        # Signal cancellation
        run.cancelled = True
        run.cancel_event.set()
        return JSONResponse(
            status_code=202,
            content=RunCancelResponse(runId=run_id, state="cancelling").model_dump(by_alias=True),
        )

    # -------------------------------------------------------------------------
    # Route: GET /api/builds/{buildId}/out.zip
    # -------------------------------------------------------------------------
    @app.get("/api/builds/{build_id}/out.zip")
    async def get_build_zip(build_id: str) -> Any:
        now = time.time()
        state.cleanup_expired(now)

        if ".." in build_id or "/" in build_id or "\\" in build_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_BUILD_ID",
                        "message": "Invalid build ID format",
                    }
                },
            )

        if build_id in state.expired_build_ids:
            return JSONResponse(
                status_code=410,
                content={
                    "error": {
                        "code": "EXPIRED_BUILD",
                        "message": f"Build '{build_id}' artifacts have expired",
                    }
                },
            )

        if build_id not in state.builds:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "UNKNOWN_BUILD",
                        "message": f"Build '{build_id}' not found",
                    }
                },
            )

        build_rec = state.builds[build_id]
        if (now - build_rec.created_at) > RETENTION_SECONDS or not build_rec.zip_path.exists():
            shutil.rmtree(build_rec.artifact_dir, ignore_errors=True)
            try:
                build_rec.zip_path.unlink(missing_ok=True)
            except Exception:
                pass
            state.builds.pop(build_id, None)
            return JSONResponse(
                status_code=410,
                content={
                    "error": {
                        "code": "EXPIRED_BUILD",
                        "message": f"Build '{build_id}' artifacts have expired",
                    }
                },
            )

        zip_resolved = build_rec.zip_path.resolve()
        if (
            build_rec.zip_path.is_symlink()
            or not zip_resolved.is_relative_to(state.builds_dir.resolve())
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "FORBIDDEN_PATH",
                        "message": "Path traversal or symlink artifact forbidden",
                    }
                },
            )

        return FileResponse(
            path=str(build_rec.zip_path),
            media_type="application/zip",
            filename=f"trustc-build-{build_id}.zip",
        )

    # -------------------------------------------------------------------------
    # 404 Catch-All for unknown /api routes (MUST NOT return index.html)
    # -------------------------------------------------------------------------
    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    )
    async def catch_all_api(path: str) -> Any:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "NOT_FOUND",
                    "message": f"API endpoint '/api/{path}' not found",
                }
            },
        )

    # -------------------------------------------------------------------------
    # Optional Static Mount (for Stage 7 UI)
    # -------------------------------------------------------------------------
    if static_dir and Path(static_dir).exists():
        p_static = Path(static_dir).resolve()

        @app.get("/{full_path:path}")
        async def serve_static(full_path: str) -> Any:
            try:
                target = (p_static / full_path).resolve()
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"error": {"code": "INVALID_PATH", "message": "Invalid path"}},
                )
            if not target.is_relative_to(p_static) or target.is_symlink():
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "FORBIDDEN_PATH", "message": "Access denied"}},
                )
            if target.is_file():
                return FileResponse(str(target))
            # If path has an extension (.zip, .js, .css, etc.) and not found, return 404
            if Path(full_path).suffix:
                return JSONResponse(
                    status_code=404,
                    content={"error": {"code": "NOT_FOUND", "message": "File not found"}},
                )
            index_file = p_static / "index.html"
            if index_file.is_file():
                return FileResponse(str(index_file))
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "NOT_FOUND", "message": "File not found"}},
            )

    return app


def run_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    static_dir: Optional[str] = None,
    workspace_dir: Optional[str] = None,
) -> None:
    """Launch the TrustC local API server."""
    import uvicorn

    allowed_bind_hosts = {"127.0.0.1", "localhost", "::1"}
    if host not in allowed_bind_hosts:
        raise ValueError(
            f"Host '{host}' is forbidden. TrustC local server strictly binds "
            f"to loopback addresses only (127.0.0.1, localhost, ::1)."
        )

    p_workspace = Path(workspace_dir) if workspace_dir else None
    p_static = Path(static_dir) if static_dir else None
    app = create_app(workspace_dir=p_workspace, port=port, static_dir=p_static)

    # Record verified server process info in .trustc-server.pid
    pid_dir = p_workspace or Path.cwd()
    pid_file = pid_dir / ".trustc-server.pid"
    pid_record = {
        "pid": os.getpid(),
        "executable": sys.executable,
        "start_time": time.time(),
        "workspace": str(pid_dir.resolve()),
        "port": port,
        "sessionId": app.state.trustc.session_id,
    }
    try:
        pid_file.write_text(json.dumps(pid_record, indent=2), encoding="utf-8")
    except Exception:
        pass

    print(
        f"Starting TrustC server on http://{host}:{port} "
        f"(sessionId: {app.state.trustc.session_id})"
    )
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass
