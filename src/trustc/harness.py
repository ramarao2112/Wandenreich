"""Stage 5 — Live local access harness for generated TrustC backends.

Executes real HTTP loopback requests against a locally running ASGI child process
backed by an isolated temporary SQLite database and ephemeral test secret.
Enforces per-actor authorization checks, verifies persistent DB side effects,
asserts response projections without leaking credentials, and guarantees
complete resource and process cleanup on all terminal paths.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

import httpx

from trustc.contracts import (
    SCHEMA_VERSION,
    Actor,
    ActorPayload,
    AttackCheck,
    AttackCompleted,
    AttackCoverage,
    AttackStep,
    DeclarationObservation,
    DeclarationObservationState,
    LogLine,
    LogPayload,
    Outcome,
    PhasePayload,
    ResultPayload,
    RunEvent,
    RunFailure,
    RunResult,
    SpecErrorKind,
)
from trustc.generator import build_app
from trustc.ir import Endpoint, Program, Resource, is_reserved_name
from trustc.manifest import generate_manifest, verify_manifest
from trustc.parser import TrustSpecError, parse_file
from trustc.seeder import (
    USER_1_EMAIL,
    USER_1_HASH,
    USER_1_ID,
    USER_2_EMAIL,
    USER_2_HASH,
    USER_2_ID,
    create_access_token,
    generate_harness_secret,
)
from trustc.source import (
    SourceError,
    check_input_size,
    normalize_source,
)
from trustc.source import spec_hash as compute_spec_hash
from trustc.verifier import check_file

ITEM_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
ACTORS: List[Actor] = [Actor.ANONYMOUS, Actor.SECOND_USER, Actor.OWNER]


def find_free_loopback_port() -> int:
    """Bind to an OS-assigned loopback port and return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    """Terminate and reap child process and its process tree."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass
    finally:
        try:
            proc.wait(timeout=1.0)
        except Exception:
            pass


class EventEmitter:
    """Manages sequential RunEvent emission and callback forwarding."""

    def __init__(
        self,
        run_id: str,
        spec_version: int,
        spec_hash: str,
        callback: Optional[Callable[[RunEvent], None]] = None,
    ):
        self.run_id = run_id
        self.spec_version = spec_version
        self.spec_hash = spec_hash
        self.callback = callback
        self.seq = 0
        self.start_time = time.time()
        self.events: List[RunEvent] = []

    def emit_phase(self, phase: str, state: str) -> None:
        self.seq += 1
        event = RunEvent(
            schemaVersion=SCHEMA_VERSION,
            runId=self.run_id,
            specVersion=self.spec_version,
            specHash=self.spec_hash,
            seq=self.seq,
            payload=PhasePayload(phase=phase, state=state),  # type: ignore[arg-type]
        )
        self.events.append(event)
        if self.callback:
            self.callback(event)

    def emit_log(self, phase: str, text: str) -> None:
        self.seq += 1
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        log = LogLine(t=int(time.time()), phase=phase, text=text, ms=elapsed_ms)
        event = RunEvent(
            schemaVersion=SCHEMA_VERSION,
            runId=self.run_id,
            specVersion=self.spec_version,
            specHash=self.spec_hash,
            seq=self.seq,
            payload=LogPayload(log=log),
        )
        self.events.append(event)
        if self.callback:
            self.callback(event)

    def emit_actor(self, step: AttackStep) -> None:
        self.seq += 1
        event = RunEvent(
            schemaVersion=SCHEMA_VERSION,
            runId=self.run_id,
            specVersion=self.spec_version,
            specHash=self.spec_hash,
            seq=self.seq,
            payload=ActorPayload(step=step),
        )
        self.events.append(event)
        if self.callback:
            self.callback(event)

    def emit_result(self, result: RunResult) -> None:
        self.seq += 1
        event = RunEvent(
            schemaVersion=SCHEMA_VERSION,
            runId=self.run_id,
            specVersion=self.spec_version,
            specHash=self.spec_hash,
            seq=self.seq,
            payload=ResultPayload(result=result),
        )
        self.events.append(event)
        if self.callback:
            self.callback(event)


def reset_sqlite_database(
    db_file: Path,
    program: Program,
) -> None:
    """Reset database tables to fresh known state for test actors.

    Stores User A (owner), User B (second user), and standard instances
    of non-User resources owned by User A.
    """
    conn = sqlite3.connect(str(db_file), timeout=10.0)
    cur = conn.cursor()
    try:
        # 1. Reset and reseed users
        cur.execute("DELETE FROM users;")
        cur.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?);",
            (USER_1_ID.hex, USER_1_EMAIL, USER_1_HASH),
        )
        cur.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?);",
            (USER_2_ID.hex, USER_2_EMAIL, USER_2_HASH),
        )

        # 2. Reset and reseed non-User resources
        for res in program.resources:
            if res.name == "User":
                continue
            table_name = res.name.lower() + "s"
            cur.execute(f"DELETE FROM {table_name};")  # nosec B608

            # Build row
            cols = ["id"]
            vals: List[Any] = [ITEM_ID.hex]

            if res.ownership:
                cols.append(res.ownership.field_name)
                vals.append(USER_1_ID.hex)

            for f in res.fields:
                if f.name == "id" or (res.ownership and f.name == res.ownership.field_name):
                    continue
                cols.append(f.name)
                ftype = f.field_type.value if hasattr(f.field_type, "value") else str(f.field_type)
                if ftype == "bool":
                    vals.append(0)
                elif ftype == "int":
                    vals.append(100)
                elif ftype == "string":
                    vals.append("Paris")
                elif ftype == "text":
                    vals.append("Sample text description")
                elif ftype == "email":
                    vals.append("test@example.com")
                elif ftype == "uuid":
                    vals.append(uuid.uuid4().hex)
                else:
                    vals.append("Sample value")

            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            cur.execute(
                f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders});",  # nosec B608
                tuple(vals),
            )

        conn.commit()
    finally:
        conn.close()


def inspect_db_resource_state(
    db_file: Path,
    table_name: str,
    item_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    """Query current row values for a specific resource instance."""
    conn = sqlite3.connect(str(db_file), timeout=10.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {table_name} WHERE id = ?;", (item_id.hex,))  # nosec B608
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def determine_expected_policy(
    ep: Endpoint,
    actor: Actor,
) -> Tuple[int, Outcome, Optional[str]]:
    """Determine expected HTTP status code and review/expected outcome for an actor.

    Returns (expected_code, expected_outcome, reason_if_review).
    """
    is_delete = ep.method.upper() == "DELETE"
    success_code = 204 if is_delete else 200

    # User identity endpoint is self-only
    if ep.resource == "User":
        if actor == Actor.ANONYMOUS:
            return 401, Outcome.AS_EXPECTED, None
        elif actor == Actor.SECOND_USER:
            return 403, Outcome.AS_EXPECTED, None
        else:  # owner
            return success_code, Outcome.AS_EXPECTED, None

    # Public endpoint
    if ep.auth.value == "public":
        if actor == Actor.ANONYMOUS:
            return success_code, Outcome.REVIEW, "Public endpoint permits unauthenticated access"
        elif actor == Actor.SECOND_USER:
            return success_code, Outcome.REVIEW, "Public endpoint permits second user access"
        else:  # owner
            return success_code, Outcome.AS_EXPECTED, None

    # Auth required
    if actor == Actor.ANONYMOUS:
        return 401, Outcome.AS_EXPECTED, None

    # Authenticated actors
    if ep.owner_waived:
        if actor == Actor.SECOND_USER:
            return (
                success_code,
                Outcome.REVIEW,
                "Ownership waived via 'authorize: public'; second user access permitted by design.",
            )
        else:
            return success_code, Outcome.AS_EXPECTED, None

    # Standard owned or login_only
    mode = ep.inferred_mode.value if ep.inferred_mode else "owner"
    if mode in ("owner", "self"):
        if actor == Actor.SECOND_USER:
            return 403, Outcome.AS_EXPECTED, None
        else:
            return success_code, Outcome.AS_EXPECTED, None
    else:  # login_only
        return success_code, Outcome.AS_EXPECTED, None


def run_attack_harness(
    program: Program,
    artifact_dir: Path,
    event_callback: Optional[Callable[[RunEvent], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    timeout_seconds: float = 30.0,
    spec_version: int = 0,
    spec_hash: str = "",
    run_id: Optional[str] = None,
    command: str = "trustc attack",
) -> RunResult:
    """Execute live access harness against an ASGI artifact child process."""
    t_start = time.time()
    run_id = run_id or str(uuid.uuid4())
    emitter = EventEmitter(run_id, spec_version, spec_hash, event_callback)

    # 1. Verify manifest
    manifest_path = artifact_dir / "trustc-manifest.json"
    if not manifest_path.is_file():
        err_msg = "Artifact manifest trustc-manifest.json not found"
        emitter.emit_log("verify", err_msg)
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="error",
            exitCode=3,
            error={"code": "MANIFEST_MISSING", "message": err_msg},
        )
        emitter.emit_result(failure)
        return failure

    ok_man, man_reason = verify_manifest(artifact_dir)
    if not ok_man:
        err_msg = f"Artifact manifest verification failed: {man_reason}"
        emitter.emit_log("verify", err_msg)
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="error",
            exitCode=3,
            error={"code": "MANIFEST_INVALID", "message": err_msg},
        )
        emitter.emit_result(failure)
        return failure

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    build_id = manifest_data.get("buildId", str(uuid.uuid4()))
    artifact_hash = manifest_data.get("artifactDigest") or manifest_data.get("artifactHash", "")

    # Read declarations from report if present
    report_path = artifact_dir / "trustc-report.json"
    declarations_data: List[Dict[str, Any]] = []
    if report_path.is_file():
        try:
            report_json = json.loads(report_path.read_text(encoding="utf-8"))
            declarations_data = (
                report_json.get("evidence", {}).get("declarations", [])
            )
        except Exception:
            pass

    # 2. Setup run-owned temporary directory and child environment
    temp_run_dir = tempfile.TemporaryDirectory(prefix="trustc_attack_harness_")
    run_temp_path = Path(temp_run_dir.name)
    db_file = run_temp_path / "attack.db"
    harness_secret = generate_harness_secret(32)

    # 3. Categorize endpoints
    tested_endpoints: List[str] = []
    excluded_endpoints: List[Dict[str, str]] = []
    eligible_eps: List[Endpoint] = []

    for ep in program.endpoints:
        ep_id = f"{ep.method} {ep.path}"
        if "{id}" in ep.path:
            tested_endpoints.append(ep_id)
            eligible_eps.append(ep)
        else:
            excluded_endpoints.append({
                "endpoint": ep_id,
                "reason": "collection/create endpoint excluded from item-only access harness",
            })

    coverage = AttackCoverage(
        testedEndpoints=tested_endpoints,
        excludedEndpoints=excluded_endpoints,
    )

    proc: Optional[subprocess.Popen[Any]] = None
    final_result: RunResult
    try:
        emitter.emit_phase("start", "started")

        # Port binding with bounded collision retry
        port: Optional[int] = None
        for _ in range(5):
            candidate_port = find_free_loopback_port()
            child_env = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "PYTHONPATH": str(artifact_dir.resolve()),
                "JWT_SECRET": harness_secret,
                "DB_URL": f"sqlite+aiosqlite:///{db_file.as_posix()}",
            }

            p = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(candidate_port),
                    "--log-level",
                    "warning",
                ],
                cwd=str(artifact_dir.resolve()),
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for readiness
            ready = False
            t_probe_start = time.time()
            while time.time() - t_probe_start < 6.0:
                if cancel_event and cancel_event.is_set():
                    kill_process_tree(p)
                    raise KeyboardInterrupt()

                if p.poll() is not None:
                    # Process died early (port clash or startup error)
                    break

                try:
                    r = httpx.get(
                        f"http://127.0.0.1:{candidate_port}/health",
                        timeout=0.4,
                    )
                    if r.status_code == 200 and r.json().get("status") == "ok":
                        ready = True
                        break
                except Exception:
                    time.sleep(0.05)

            if ready:
                port = candidate_port
                proc = p
                break
            else:
                kill_process_tree(p)

        if not ready or proc is None or port is None:
            emitter.emit_phase("start", "finished")
            err_msg = "Application child process failed bounded readiness check"
            emitter.emit_log("start", err_msg)
            raise RuntimeError(err_msg)

        emitter.emit_phase("start", "finished")

        # 4. Seeding phase
        emitter.emit_phase("seed", "started")
        reset_sqlite_database(db_file, program)
        emitter.emit_phase("seed", "finished")

        token_user1 = create_access_token(USER_1_ID, secret=harness_secret)
        token_user2 = create_access_token(USER_2_ID, secret=harness_secret)

        actor_tokens: Dict[Actor, Optional[str]] = {
            Actor.ANONYMOUS: None,
            Actor.SECOND_USER: token_user2,
            Actor.OWNER: token_user1,
        }

        # 5. Request phase
        emitter.emit_phase("request", "started")
        steps: List[AttackStep] = []
        as_expected = 0
        review = 0
        unexpected = 0

        # Map declarations to step IDs
        decl_step_map: Dict[str, List[str]] = {}
        for d in declarations_data:
            decl_step_map[d["id"]] = []

        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
            for ep in eligible_eps:
                ep_str = f"{ep.method} {ep.path}"

                # Match declarations
                matched_decl_ids: List[str] = [
                    d["id"]
                    for d in declarations_data
                    if d.get("endpoint") == ep_str
                ]

                # Determine target URL
                if ep.resource == "User":
                    target_id = USER_1_ID
                    path_str = ep.path.replace("{id}", str(target_id))
                    table_name = "users"
                else:
                    target_id = ITEM_ID
                    path_str = ep.path.replace("{id}", str(target_id))
                    table_name = ep.resource.lower() + "s"

                # Find resource definition
                res_def: Optional[Resource] = next(
                    (r for r in program.resources if r.name == ep.resource), None
                )

                for actor in ACTORS:
                    if cancel_event and cancel_event.is_set():
                        raise KeyboardInterrupt()

                    if time.time() - t_start > timeout_seconds:
                        raise TimeoutError("Attack harness execution deadline exceeded")

                    step_id = str(uuid.uuid4())
                    for d_id in matched_decl_ids:
                        decl_step_map[d_id].append(step_id)

                    expect_code, expected_outcome, expected_reason = determine_expected_policy(
                        ep, actor
                    )

                    # Reset state before each actor for clean isolation
                    reset_sqlite_database(db_file, program)

                    # Emit pending actor event
                    pending_step = AttackStep(
                        stepId=step_id,
                        endpoint=ep_str,
                        actor=actor,
                        method=ep.method,
                        path=path_str,
                        expect=expect_code,
                        got=None,
                        outcome=None,
                        reason=expected_reason,
                        declarationIds=matched_decl_ids,
                        checks=[],
                    )
                    emitter.emit_actor(pending_step)

                    # Prepare headers
                    headers: Dict[str, str] = {}
                    tok = actor_tokens[actor]
                    if tok:
                        headers["Authorization"] = f"Bearer {tok}"

                    # Prepare body payload if needed
                    payload: Optional[Dict[str, Any]] = None
                    if ep.method.upper() in ("PUT", "PATCH") and ep.body:
                        payload = {}
                        for bfield in ep.body:
                            if res_def:
                                f_obj = next(
                                    (f for f in res_def.fields if f.name == bfield), None
                                )
                                f_type_str = (
                                    f_obj.field_type.value
                                    if f_obj and hasattr(f_obj.field_type, "value")
                                    else ""
                                )
                                if f_type_str == "bool":
                                    payload[bfield] = True
                                elif f_type_str == "int":
                                    payload[bfield] = 999
                                else:
                                    payload[bfield] = "Updated value"
                            else:
                                payload[bfield] = "Updated value"

                    # Execute loopback request
                    checks: List[AttackCheck] = []
                    try:
                        req_method = ep.method.upper()
                        if req_method == "GET":
                            resp = client.get(path_str, headers=headers)
                        elif req_method == "PUT":
                            resp = client.put(path_str, headers=headers, json=payload or {})
                        elif req_method == "PATCH":
                            resp = client.patch(path_str, headers=headers, json=payload or {})
                        elif req_method == "DELETE":
                            resp = client.delete(path_str, headers=headers)
                        else:
                            resp = client.request(
                                req_method, path_str, headers=headers, json=payload
                            )
                        got_code = resp.status_code
                    except Exception as exc:
                        got_code = 0
                        checks.append(AttackCheck(
                            name="transport",
                            expected="HTTP response",
                            actual=f"Exception: {type(exc).__name__}",
                            passed=False,
                        ))

                    # 1. Status code check
                    code_passed = (got_code == expect_code)
                    checks.append(AttackCheck(
                        name="status_code",
                        expected=str(expect_code),
                        actual=str(got_code),
                        passed=code_passed,
                    ))

                    # 2. Database persistence check for mutating actions
                    db_persistence_passed = True
                    if ep.method.upper() in ("PUT", "PATCH", "DELETE"):
                        db_state = inspect_db_resource_state(db_file, table_name, target_id)
                        if expect_code in (401, 403):
                            # Denied writes must NOT persist
                            if ep.method.upper() == "DELETE":
                                if db_state is None:
                                    db_persistence_passed = False
                                    checks.append(AttackCheck(
                                        name="denied_write_persistence",
                                        expected="row exists in DB",
                                        actual="row was deleted",
                                        passed=False,
                                    ))
                                else:
                                    checks.append(AttackCheck(
                                        name="denied_write_persistence",
                                        expected="row exists in DB",
                                        actual="row retained",
                                        passed=True,
                                    ))
                            else:
                                # PUT / PATCH: verify fields did not change to payload
                                if payload and db_state:
                                    for pk, pv in payload.items():
                                        if pk in db_state and db_state[pk] == pv:
                                            db_persistence_passed = False
                                            checks.append(AttackCheck(
                                                name="denied_write_persistence",
                                                expected="field unmodified",
                                                actual=f"field {pk} was modified",
                                                passed=False,
                                            ))
                                if db_persistence_passed:
                                    checks.append(AttackCheck(
                                        name="denied_write_persistence",
                                        expected="unmodified in DB",
                                        actual="unmodified in DB",
                                        passed=True,
                                    ))
                        elif expect_code in (200, 204):
                            # Allowed writes MUST persist
                            if ep.method.upper() == "DELETE":
                                if db_state is not None:
                                    db_persistence_passed = False
                                    checks.append(AttackCheck(
                                        name="allowed_write_persistence",
                                        expected="row deleted from DB",
                                        actual="row still present in DB",
                                        passed=False,
                                    ))
                                else:
                                    checks.append(AttackCheck(
                                        name="allowed_write_persistence",
                                        expected="row deleted from DB",
                                        actual="row deleted",
                                        passed=True,
                                    ))
                            else:
                                # PUT / PATCH: verify updated fields
                                if payload and db_state:
                                    for pk, pv in payload.items():
                                        expected_val = 1 if isinstance(pv, bool) and pv else pv
                                        if pk in db_state and db_state[pk] != expected_val:
                                            db_persistence_passed = False
                                            checks.append(AttackCheck(
                                                name="allowed_write_persistence",
                                                expected=f"{pk}={pv}",
                                                actual=f"{pk}={db_state[pk]}",
                                                passed=False,
                                            ))
                                if db_persistence_passed:
                                    checks.append(AttackCheck(
                                        name="allowed_write_persistence",
                                        expected="persisted in DB",
                                        actual="persisted in DB",
                                        passed=True,
                                    ))

                    # 3. Projection check for successful responses
                    projection_passed = True
                    if got_code == 200:
                        try:
                            body = resp.json()
                        except Exception as exc:
                            body = None
                            projection_passed = False
                            checks.append(AttackCheck(
                                name="response_json_decode",
                                expected="valid JSON body",
                                actual=f"decode error: {type(exc).__name__}",
                                passed=False,
                            ))

                        if isinstance(body, dict):
                            # Credential protection check
                            leaked_creds = [k for k in body.keys() if is_reserved_name(k)]
                            if leaked_creds:
                                projection_passed = False
                                checks.append(AttackCheck(
                                    name="credential_protection",
                                    expected="no credentials in body",
                                    actual=f"credentials leaked: {leaked_creds}",
                                    passed=False,
                                ))
                            else:
                                checks.append(AttackCheck(
                                    name="credential_protection",
                                    expected="no credentials in body",
                                    actual="clean body",
                                    passed=True,
                                ))

                            # Field projection verification
                            if ep.returns_resource:
                                ret_res = program.get_resource(ep.returns_resource)
                                if ep.returns_projection is not None:
                                    expected_fields = [
                                        f for f in ep.returns_projection
                                        if ret_res
                                        and (fn := ret_res.get_field(f))
                                        and not fn.is_credential
                                    ]
                                else:
                                    expected_fields = [
                                        f.name for f in ret_res.fields if not f.is_credential
                                    ] if ret_res else []

                                expected_set = set(expected_fields)
                                actual_set = set(body.keys())
                                expected_sorted = sorted(list(expected_set))
                                actual_sorted = sorted(list(actual_set))

                                if actual_set == expected_set:
                                    checks.append(AttackCheck(
                                        name="response_projection",
                                        expected=f"exact fields: {expected_sorted}",
                                        actual=f"exact fields: {actual_sorted}",
                                        passed=True,
                                    ))
                                else:
                                    projection_passed = False
                                    missing = sorted(list(expected_set - actual_set))
                                    extra = sorted(list(actual_set - expected_set))
                                    err_parts: List[str] = []
                                    if missing:
                                        err_parts.append(f"missing: {missing}")
                                    if extra:
                                        err_parts.append(f"unexpected extra: {extra}")
                                    checks.append(AttackCheck(
                                        name="response_projection",
                                        expected=f"exact fields: {expected_sorted}",
                                        actual=", ".join(err_parts),
                                        passed=False,
                                    ))
                            elif ep.method.upper() in ("PUT", "PATCH") and not ep.returns_resource:
                                is_empty_dict = (body == {})
                                if not is_empty_dict:
                                    projection_passed = False
                                checks.append(AttackCheck(
                                    name="response_projection",
                                    expected="{}",
                                    actual=str(body),
                                    passed=is_empty_dict,
                                ))

                    elif ep.method.upper() == "DELETE" and got_code == 204:
                        is_empty_body = (resp.text == "" or resp.content == b"")
                        if not is_empty_body:
                            projection_passed = False
                        checks.append(AttackCheck(
                            name="empty_response",
                            expected="empty body",
                            actual="empty body" if is_empty_body else resp.text,
                            passed=is_empty_body,
                        ))

                    # Compute final outcome
                    all_passed = code_passed and db_persistence_passed and projection_passed
                    if not all_passed:
                        resolved_outcome: Outcome = Outcome.UNEXPECTED
                        reason: Optional[str] = (
                            f"Assertion failed: expected code {expect_code}, got {got_code}"
                        )
                        unexpected += 1
                    else:
                        resolved_outcome = expected_outcome
                        reason = expected_reason
                        if resolved_outcome == Outcome.AS_EXPECTED:
                            as_expected += 1
                        elif resolved_outcome == Outcome.REVIEW:
                            review += 1
                        else:
                            unexpected += 1

                    # Emit resolved actor event
                    resolved_step = AttackStep(
                        stepId=step_id,
                        endpoint=ep_str,
                        actor=actor,
                        method=ep.method,
                        path=path_str,
                        expect=expect_code,
                        got=got_code,
                        outcome=resolved_outcome,
                        reason=reason,
                        declarationIds=matched_decl_ids,
                        checks=checks,
                    )
                    steps.append(resolved_step)
                    emitter.emit_actor(resolved_step)

        emitter.emit_phase("request", "finished")

        # 6. Build declaration observations
        declaration_observations: List[DeclarationObservation] = []
        for d in declarations_data:
            d_id = d["id"]
            d_kind = d.get("kind")
            associated_steps = decl_step_map.get(d_id, [])
            if not associated_steps:
                obs_state = DeclarationObservationState.NOT_TESTED
            elif d_kind == "sensitive_exposure":
                field_tested = any(
                    any(
                        "exposed" in c.name or "projection" in c.name
                        for c in s.checks
                        if c.passed
                    )
                    for s in steps
                    if s.step_id in associated_steps
                )
                obs_state = (
                    DeclarationObservationState.OBSERVED
                    if field_tested
                    else DeclarationObservationState.NOT_TESTED
                )
            else:
                obs_state = DeclarationObservationState.OBSERVED
            declaration_observations.append(
                DeclarationObservation(
                    declarationId=d_id,
                    stepIds=associated_steps,
                    state=obs_state,
                )
            )

        # 7. Exit code calculation
        final_exit_code: Literal[0, 1] = 1 if unexpected > 0 else 0
        total_steps = len(steps)

        completed_result = AttackCompleted(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="completed",
            exitCode=final_exit_code,
            buildId=build_id,
            artifactHash=artifact_hash,
            steps=steps,
            asExpected=as_expected,
            review=review,
            unexpected=unexpected,
            total=total_steps,
            coverage=coverage,
            declarationObservations=declaration_observations,
        )

        final_result = completed_result

    except KeyboardInterrupt:
        final_result = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="cancelled",
            exitCode=130,
            error={"code": "CANCELLED", "message": "Operation cancelled by user"},
        )

    except TimeoutError as exc:
        final_result = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="timed_out",
            exitCode=124,
            error={"code": "TIMED_OUT", "message": str(exc)},
        )

    except Exception as exc:
        final_result = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="error",
            exitCode=3,
            error={"code": "EXECUTION_ERROR", "message": f"{type(exc).__name__}: {exc}"},
        )

    finally:
        # Guarantee cleanup of all process and file handles on every exit path
        emitter.emit_phase("cleanup", "started")
        if proc is not None:
            kill_process_tree(proc)
        cleanup_error = None
        try:
            temp_run_dir.cleanup()
        except Exception as exc:
            cleanup_error = str(exc)
        emitter.emit_phase("cleanup", "finished")

        # Cleanup failure overrides success with sanitized execution error (exit 3)
        if cleanup_error is not None:
            final_result = RunFailure(
                schemaVersion=SCHEMA_VERSION,
                specVersion=spec_version,
                specHash=spec_hash,
                command=command,
                ms=int((time.time() - t_start) * 1000),
                kind="attack",
                status="error",
                exitCode=3,
                error={
                    "code": "CLEANUP_FAILED",
                    "message": f"Harness cleanup failed: {cleanup_error}",
                },
            )

        # Exactly one top-level terminal result event emitted following cleanup
        if final_result is not None:
            emitter.emit_result(final_result)

    assert final_result is not None
    return final_result


def attack_spec(
    spec_path: str | Path,
    spec_version: int = 0,
    fmt: str = "human",
    event_callback: Optional[Callable[[RunEvent], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    timeout_seconds: float = 30.0,
) -> RunResult:
    """CLI/API entry point to check, build, and attack a TrustSpec file."""
    t_start = time.time()
    spec_file = Path(spec_path)
    command = f"trustc attack {spec_file.as_posix()}"

    # 1. Read and normalize source
    try:
        raw_source = spec_file.read_bytes()
    except Exception as exc:
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash="",
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="error",
            exitCode=3,
            error={"code": "FILE_READ_ERROR", "message": str(exc)},
        )
        _print_result(failure, fmt)
        return failure

    try:
        check_input_size(raw_source)
        text_source = raw_source.decode("utf-8")
        norm_source = normalize_source(text_source)
        spec_hash = compute_spec_hash(norm_source)
    except UnicodeDecodeError as exc:
        from trustc.contracts import Span, SpecError
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash="",
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="invalid_spec",
            exitCode=2,
            specErrors=[
                SpecError(
                    kind=SpecErrorKind.SYNTAX,
                    code="INVALID_ENCODING",
                    message=f"Invalid UTF-8 encoding: {exc}",
                    span=Span(line=1, col=1, endLine=1, endCol=1),
                    snippet="",
                )
            ],
            error={"code": "INVALID_ENCODING", "message": str(exc)},
        )
        _print_result(failure, fmt)
        return failure
    except SourceError as exc:
        from trustc.contracts import Span, SpecError
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash="",
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="invalid_spec",
            exitCode=2,
            specErrors=[
                SpecError(
                    kind=SpecErrorKind.UNSUPPORTED,
                    code="SOURCE_LIMIT",
                    message=exc.message,
                    span=Span(line=1, col=1, endLine=1, endCol=1),
                    snippet="",
                )
            ],
            error={"code": "SOURCE_LIMIT", "message": exc.message},
        )
        _print_result(failure, fmt)
        return failure

    # 2. Parse file
    try:
        program = parse_file(spec_file)
    except TrustSpecError as exc:
        from trustc.contracts import Span, SpecError
        spec_errs = [
            SpecError(
                kind=e.kind,  # type: ignore[arg-type]
                code=e.code,
                message=e.message,
                span=Span(
                    line=e.span.line,
                    col=e.span.col,
                    endLine=e.span.end_line,
                    endCol=e.span.end_col,
                ),
                snippet=e.snippet,
            )
            for e in exc.errors
        ]
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="invalid_spec",
            exitCode=2,
            specErrors=spec_errs,
        )
        _print_result(failure, fmt)
        return failure
    except Exception as exc:
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="error",
            exitCode=3,
            error={"code": "PARSE_ERROR", "message": str(exc)},
        )
        _print_result(failure, fmt)
        return failure

    check_res = check_file(spec_file, spec_version=spec_version)
    if not check_res.ok:
        # Refused or invalid spec: application is NEVER generated or started
        failure = RunFailure(
            schemaVersion=SCHEMA_VERSION,
            specVersion=spec_version,
            specHash=spec_hash,
            command=command,
            ms=int((time.time() - t_start) * 1000),
            kind="attack",
            status="refused" if check_res.exit_code == 1 else "invalid_spec",
            exitCode=check_res.exit_code,  # type: ignore[arg-type]
            diagnostics=check_res.diagnostics,
            specErrors=check_res.spec_errors,
        )
        _print_result(failure, fmt)
        return failure

    # 4. Generate app into run-owned temporary directory
    with tempfile.TemporaryDirectory(prefix="trustc_attack_artifact_") as artifact_dir:
        app_path = Path(artifact_dir) / "app"
        try:
            build_app(spec_file, app_path, spec_version=spec_version)
        except Exception as exc:
            failure = RunFailure(
                schemaVersion=SCHEMA_VERSION,
                specVersion=spec_version,
                specHash=spec_hash,
                command=command,
                ms=int((time.time() - t_start) * 1000),
                kind="attack",
                status="error",
                exitCode=3,
                error={"code": "BUILD_FAILED", "message": str(exc)},
            )
            _print_result(failure, fmt)
            return failure

        # 5. Run live harness
        def cli_event_listener(event: RunEvent) -> None:
            if fmt == "human":
                payload = event.payload
                if payload.type == "phase":
                    pass
                elif payload.type == "actor":
                    step = payload.step
                    if step.got is not None:
                        # Resolved step
                        act_str = (
                            step.actor.value
                            if hasattr(step.actor, "value")
                            else str(step.actor)
                        )
                        oc_str = (
                            step.outcome.value
                            if step.outcome and hasattr(step.outcome, "value")
                            else str(step.outcome or "unknown")
                        )
                        try:
                            print(
                                f"  [actor: {act_str:11s}] {step.method} {step.path} "
                                f"-> {step.got} (expected {step.expect}) [{oc_str}]"
                            )
                        except UnicodeEncodeError:
                            pass
            if event_callback:
                event_callback(event)

        result = run_attack_harness(
            program=program,
            artifact_dir=app_path,
            event_callback=cli_event_listener,
            cancel_event=cancel_event,
            timeout_seconds=timeout_seconds,
            spec_version=spec_version,
            spec_hash=spec_hash,
            command=command,
        )

        _print_result(result, fmt)
        return result


def _print_result(result: RunResult, fmt: str) -> None:
    """Format and print RunResult according to chosen output style."""
    if fmt == "json":
        print(json.dumps(result.model_dump(by_alias=True), indent=2))
    elif fmt == "human":
        if isinstance(result, AttackCompleted):
            matched = result.as_expected + result.review
            review_label = (
                "1 policy review" if result.review == 1 else f"{result.review} policy reviews"
            )
            summary_msg = (
                f"\nAttack complete:\n"
                f"  {matched} matched expectations · "
                f"{review_label} · "
                f"{result.unexpected} failed"
            )
            try:
                print(summary_msg)
            except UnicodeEncodeError:
                print(summary_msg.replace("·", "*"))
            if result.total == 0:
                print("  No eligible endpoints tested.")
        elif isinstance(result, RunFailure):
            print(f"\nAttack failed ({result.status}):", file=sys.stderr)
            for err in result.spec_errors:
                kind_str = err.kind.value if hasattr(err.kind, "value") else str(err.kind)
                if kind_str == "syntax":
                    kind_display = "Syntax error"
                elif kind_str == "reference":
                    kind_display = "Reference error"
                else:
                    kind_display = kind_str.capitalize()
                msg = err.message.replace("\n", "\\n").replace("\r", "\\r")
                print(f"  {kind_display}: {msg} at line {err.span.line}", file=sys.stderr)
            for diag in result.diagnostics:
                rule_val = diag.rule_id
                rule_str = rule_val.value if hasattr(rule_val, "value") else str(rule_val)
                print(f"  {rule_str}: {diag.message} at {diag.location}", file=sys.stderr)
            if result.error:
                print(f"  Error: {result.error.get('message')}", file=sys.stderr)


class OwnerCheckRemover(ast.NodeTransformer):
    """AST transformer that removes the Trip owner-check statement."""

    def __init__(self) -> None:
        super().__init__()
        self.removed = False

    def visit_If(self, node: ast.If) -> Any:
        # Check if node is `if item.owner_id != current_user.id:`
        test_source = ast.unparse(node.test)
        if "owner_id != current_user.id" in test_source:
            self.removed = True
            return None  # Remove statement from body
        return self.generic_visit(node)


def mutate_and_attack_f2(
    target: str | Path,
    program: Optional[Program] = None,
    spec_version: int = 0,
    spec_hash: str = "",
) -> AttackCompleted:
    """Test helper: mutate routers/trips.py by removing the owner check AST statement,

    syntax-check the mutated file, update the manifest, and run the ordinary harness.
    Must produce unexpected=1 on second_user read and exitCode=1.
    Target can be either an already-built artifact directory or a spec path (e.g. F2.trust).
    """
    p_target = Path(target)
    temp_build_dir = None
    if p_target.is_file():
        temp_build_dir = tempfile.TemporaryDirectory(prefix="trustc_f2_build_")
        original_artifact_dir = Path(temp_build_dir.name) / "app"
        build_app(p_target, original_artifact_dir)
        if program is None:
            program = parse_file(p_target)
    else:
        original_artifact_dir = p_target
        if program is None:
            for candidate in (
                Path("tests/fixtures/F2.trust"),
                Path("TrustC-Stage-Pack-v3/fixtures/F2.trust"),
            ):
                if candidate.is_file():
                    program = parse_file(candidate)
                    break
            if program is None:
                raise ValueError("Program must be provided when target is a directory")

    try:
        with tempfile.TemporaryDirectory(prefix="trustc_mutated_artifact_") as td:
            copy_dir = Path(td) / "app"
            shutil.copytree(original_artifact_dir, copy_dir)

            trips_router_path = copy_dir / "routers" / "trips.py"
            source = trips_router_path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            remover = OwnerCheckRemover()
            mutated_tree = remover.visit(tree)
            ast.fix_missing_locations(mutated_tree)

            if not remover.removed:
                raise RuntimeError("Failed to find and remove owner-check in routers/trips.py")

            mutated_source = ast.unparse(mutated_tree)
            ast.parse(mutated_source)  # Verify clean syntax
            trips_router_path.write_text(mutated_source, encoding="utf-8")

            # Read build_id and update manifest
            manifest_path = copy_dir / "trustc-manifest.json"
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            build_id = manifest_data.get("buildId", str(uuid.uuid4()))

            # Regenerate manifest for mutated artifact
            files_dict: Dict[str, bytes] = {}
            for file_p in copy_dir.rglob("*"):
                if (
                    file_p.is_file()
                    and not any(part in ("__pycache__", ".git") for part in file_p.parts)
                    and not file_p.name.endswith(".pyc")
                ):
                    rel_posix = file_p.relative_to(copy_dir).as_posix()
                    files_dict[rel_posix] = file_p.read_bytes()
            man_json, _ = generate_manifest(
                files_dict=files_dict,
                build_id=build_id,
                spec_hash=spec_hash,
                spec_version=spec_version,
                compiler_version="0.1.0",
                template_version="1.0.0",
            )
            (copy_dir / "trustc-manifest.json").write_text(man_json, encoding="utf-8")

            # Run ordinary harness against isolated mutated copy
            res = run_attack_harness(
                program=program,
                artifact_dir=copy_dir,
                spec_version=spec_version,
                spec_hash=spec_hash,
                command="trustc attack tests/fixtures/F2.trust (mutated)",
            )

            if not isinstance(res, AttackCompleted):
                raise RuntimeError(
                    f"Expected AttackCompleted from mutated harness, got {type(res).__name__}"
                )

            return res
    finally:
        if temp_build_dir is not None:
            temp_build_dir.cleanup()
