"""TrustC Stage 6 Unit Tests — Local API Server, SSE Streaming & Lifecycle."""

from __future__ import annotations

import io
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trustc.server import create_app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
F1_SPEC = (FIXTURES_DIR / "F1.trust").read_text(encoding="utf-8")
F2_SPEC = (FIXTURES_DIR / "F2.trust").read_text(encoding="utf-8")
F4_SPEC = (FIXTURES_DIR / "F4.trust").read_text(encoding="utf-8")


@pytest.fixture
def client_app():
    """Create a test client backed by an isolated temporary workspace."""
    with tempfile.TemporaryDirectory(prefix="trustc_test_server_") as td:
        ws_dir = Path(td) / "workspace"
        ws_dir.mkdir(parents=True, exist_ok=True)
        app = create_app(workspace_dir=ws_dir, port=8787)
        with TestClient(app) as test_client:
            yield test_client, app


@pytest.mark.stage6
def test_server_meta(client_app):
    """GET /api/meta returns schemaVersion 2, sessionId, target, and 5 rules."""
    client, _ = client_app
    res = client.get("/api/meta")
    assert res.status_code == 200
    meta = res.json()
    assert meta["schemaVersion"] == 2
    assert "sessionId" in meta and len(meta["sessionId"]) > 0
    assert meta["version"] == "0.1.0"
    assert meta["port"] == 8787
    assert meta["target"] == "fastapi"
    rules = meta["rules"]
    assert len(rules) == 5
    rule_ids = [r["id"] for r in rules]
    assert rule_ids == ["TC-001", "TC-002", "TC-003", "TC-004", "TC-005"]


@pytest.mark.stage6
def test_server_examples(client_app):
    """GET /api/examples returns 6 examples F1..F6 with valid specs."""
    client, _ = client_app
    res = client.get("/api/examples")
    assert res.status_code == 200
    examples = res.json()
    assert len(examples) == 6
    assert [e["id"] for e in examples] == ["F1", "F2", "F3", "F4", "F5", "F6"]
    for ex in examples:
        assert len(ex["title"]) > 0
        assert len(ex["subtitle"]) > 0
        assert ex["expectedCheck"] in ("pass", "fail")
        assert isinstance(ex["expectedReview"], bool)
        assert len(ex["spec"]) > 0


@pytest.mark.stage6
def test_server_rules_catalog(client_app):
    """GET /api/rules/{id} returns rule documentation or 404 for unknown rules."""
    client, _ = client_app
    for r_id in ["TC-001", "TC-002", "TC-003", "TC-004", "TC-005"]:
        res = client.get(f"/api/rules/{r_id}")
        assert res.status_code == 200
        doc = res.json()
        assert doc["id"] == r_id
        assert "name" in doc
        assert "checks" in doc
        assert "flaw" in doc
        assert doc["fixType"] in ("diff", "prompt")
        assert "refused" in doc
        assert "accepted" in doc

    # Unknown rule ID -> 404 JSON
    res_bad = client.get("/api/rules/TC-999")
    assert res_bad.status_code == 404
    err = res_bad.json()["error"]
    assert err["code"] == "UNKNOWN_RULE"


@pytest.mark.stage6
def test_server_check_valid_and_refused(client_app):
    """POST /api/check verifies valid spec (F2 -> 0) and refused spec (F1 -> 1)."""
    client, _ = client_app
    # F2: pass
    res_f2 = client.post("/api/check", json={"spec": F2_SPEC, "specVersion": 0})
    assert res_f2.status_code == 200
    data_f2 = res_f2.json()
    assert data_f2["ok"] is True
    assert data_f2["exitCode"] == 0
    assert len(data_f2["diagnostics"]) == 0

    # F1: refuse
    res_f1 = client.post("/api/check", json={"spec": F1_SPEC, "specVersion": 0})
    assert res_f1.status_code == 200
    data_f1 = res_f1.json()
    assert data_f1["ok"] is False
    assert data_f1["exitCode"] == 1
    assert len(data_f1["diagnostics"]) > 0


@pytest.mark.stage6
def test_server_check_sarif_format(client_app):
    """POST /api/check?format=sarif returns valid OASIS SARIF 2.1.0 report."""
    client, _ = client_app
    res = client.post(
        "/api/check?format=sarif",
        json={"spec": F1_SPEC, "specVersion": 0},
    )
    assert res.status_code == 200
    sarif = res.json()
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "trustc"
    assert len(run["results"]) > 0


@pytest.mark.stage6
def test_server_check_validation_errors(client_app):
    """POST /api/check enforces Content-Type, valid JSON, and spec size limit."""
    client, _ = client_app
    # Non-JSON content type -> 400
    r1 = client.post(
        "/api/check",
        content=b"raw text",
        headers={"Content-Type": "text/plain"},
    )
    assert r1.status_code == 400
    assert r1.json()["error"]["code"] == "INVALID_CONTENT_TYPE"

    # Malformed JSON -> 400
    r2 = client.post(
        "/api/check",
        content=b"{bad json",
        headers={"Content-Type": "application/json"},
    )
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "MALFORMED_JSON"

    # Spec exceeds 256 KiB -> 413
    oversized = "a" * (262144 + 1)
    r3 = client.post("/api/check", json={"spec": oversized})
    assert r3.status_code == 413
    assert r3.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.stage6
def test_server_build_worker_lifecycle(client_app):
    """POST /api/build accepts job (202), executes build, and updates status to terminal."""
    client, app = client_app
    res = client.post("/api/build", json={"spec": F2_SPEC, "specVersion": 0})
    assert res.status_code == 202
    acc = res.json()
    run_id = acc["runId"]
    assert acc["specVersion"] == 0
    assert len(acc["specHash"]) == 64

    # Wait for completion
    deadline = time.time() + 10.0
    st_data = None
    while time.time() < deadline:
        st_res = client.get(f"/api/runs/{run_id}")
        assert st_res.status_code == 200
        st_data = st_res.json()
        if st_data["state"] == "terminal":
            break
        time.sleep(0.1)

    assert st_data is not None and st_data["state"] == "terminal"
    result = st_data["result"]
    assert result["status"] == "completed"
    assert result["exitCode"] == 0
    assert "buildId" in result
    build_id = result["buildId"]
    assert build_id in app.state.trustc.builds


@pytest.mark.stage6
def test_server_build_refusal_and_syntax_error(client_app):
    """POST /api/build terminal failure events on flawed and syntax error specs."""
    client, _ = client_app
    # Flawed spec F1 -> terminal refusal (exit 1)
    r_f1 = client.post("/api/build", json={"spec": F1_SPEC})
    assert r_f1.status_code == 202
    run_id_f1 = r_f1.json()["runId"]

    st = None
    deadline = time.time() + 5.0
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id_f1}").json()
        if st["state"] == "terminal":
            break
        time.sleep(0.05)

    assert st is not None and st["state"] == "terminal"
    assert st["result"]["exitCode"] == 1
    assert st["result"]["status"] == "refused"

    # Syntax error spec F4 -> terminal invalid_spec (exit 2)
    r_f4 = client.post("/api/build", json={"spec": F4_SPEC})
    assert r_f4.status_code == 202
    run_id_f4 = r_f4.json()["runId"]

    st_f4 = None
    deadline = time.time() + 5.0
    while time.time() < deadline:
        st_f4 = client.get(f"/api/runs/{run_id_f4}").json()
        if st_f4["state"] == "terminal":
            break
        time.sleep(0.05)

    assert st_f4 is not None and st_f4["state"] == "terminal"
    assert st_f4["result"]["exitCode"] == 2
    assert st_f4["result"]["status"] == "invalid_spec"


@pytest.mark.stage6
def test_server_worker_busy_lock_409(client_app):
    """Worker lock rejects concurrent jobs with 409 SERVER_BUSY."""
    client, app = client_app
    # Artificially acquire lock
    assert app.state.trustc.worker_lock.acquire(blocking=False)
    try:
        res_build = client.post("/api/build", json={"spec": F2_SPEC})
        assert res_build.status_code == 409
        assert res_build.json()["error"]["code"] == "SERVER_BUSY"

        res_atk = client.post("/api/attack", json={"spec": F2_SPEC})
        assert res_atk.status_code == 409
        assert res_atk.json()["error"]["code"] == "SERVER_BUSY"
    finally:
        app.state.trustc.worker_lock.release()


@pytest.mark.stage6
def test_server_build_out_zip(client_app):
    """GET /api/builds/{buildId}/out.zip downloads zip with relative paths only."""
    client, _ = client_app
    b_res = client.post("/api/build", json={"spec": F2_SPEC})
    run_id = b_res.json()["runId"]

    deadline = time.time() + 10.0
    build_id = None
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id}").json()
        if st["state"] == "terminal":
            build_id = st["result"]["buildId"]
            break
        time.sleep(0.1)

    assert build_id is not None
    zip_res = client.get(f"/api/builds/{build_id}/out.zip")
    assert zip_res.status_code == 200
    assert "application/zip" in zip_res.headers.get("content-type", "")

    zf = zipfile.ZipFile(io.BytesIO(zip_res.content))
    names = zf.namelist()
    for name in names:
        assert not name.startswith("/")
        assert ".." not in name
        assert "\\" not in name
    assert "trustc-manifest.json" in names
    assert "trustc-report.json" in names
    assert "main.py" in names
    assert "models.py" in names


@pytest.mark.stage6
def test_server_attack_worker_lifecycle_with_build_id(client_app):
    """POST /api/attack with valid buildId executes harness and returns 6 asExpected."""
    client, _ = client_app
    b_res = client.post("/api/build", json={"spec": F2_SPEC})
    run_id = b_res.json()["runId"]

    deadline = time.time() + 10.0
    build_id = None
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id}").json()
        if st["state"] == "terminal":
            build_id = st["result"]["buildId"]
            break
        time.sleep(0.1)

    assert build_id is not None
    atk_res = client.post("/api/attack", json={"spec": F2_SPEC, "buildId": build_id})
    assert atk_res.status_code == 202
    atk_run = atk_res.json()["runId"]

    deadline = time.time() + 20.0
    atk_st = None
    while time.time() < deadline:
        st = client.get(f"/api/runs/{atk_run}").json()
        if st["state"] == "terminal":
            atk_st = st
            break
        time.sleep(0.5)

    assert atk_st is not None and atk_st["state"] == "terminal"
    res = atk_st["result"]
    assert res["status"] == "completed"
    assert res["exitCode"] == 0
    assert res["asExpected"] == 6
    assert res["review"] == 0
    assert res["unexpected"] == 0


@pytest.mark.stage6
def test_server_attack_build_id_mismatch(client_app):
    """POST /api/attack validates buildId presence and specHash identity."""
    client, _ = client_app
    # Unknown buildId -> 404
    r1 = client.post(
        "/api/attack",
        json={"spec": F2_SPEC, "buildId": "00000000-0000-0000-0000-000000000000"},
    )
    assert r1.status_code == 404
    assert r1.json()["error"]["code"] == "UNKNOWN_BUILD"

    # Build F2
    b_res = client.post("/api/build", json={"spec": F2_SPEC})
    run_id = b_res.json()["runId"]
    deadline = time.time() + 10.0
    build_id = None
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id}").json()
        if st["state"] == "terminal":
            build_id = st["result"]["buildId"]
            break
        time.sleep(0.1)

    assert build_id is not None

    # Mismatched spec with existing buildId -> 409
    r2 = client.post("/api/attack", json={"spec": F1_SPEC, "buildId": build_id})
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "SPEC_HASH_MISMATCH"


@pytest.mark.stage6
def test_server_sse_streaming_and_replay(client_app):
    """GET /api/runs/{runId}/events supports event streaming and Last-Event-ID replay."""
    client, _ = client_app
    b_res = client.post("/api/build", json={"spec": F2_SPEC})
    run_id = b_res.json()["runId"]

    # Wait for completion
    deadline = time.time() + 10.0
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id}").json()
        if st["state"] == "terminal":
            break
        time.sleep(0.1)

    # Full replay
    r_full = client.get(f"/api/runs/{run_id}/events")
    assert r_full.status_code == 200
    assert "text/event-stream" in r_full.headers["content-type"]
    lines = [line_str for line_str in r_full.text.splitlines() if line_str.startswith("id:")]
    assert len(lines) >= 3

    # Partial replay using Last-Event-ID
    r_part = client.get(
        f"/api/runs/{run_id}/events",
        headers={"Last-Event-ID": f"{run_id}:2"},
    )
    assert r_part.status_code == 200
    part_lines = [line_str for line_str in r_part.text.splitlines() if line_str.startswith("id:")]
    assert len(part_lines) == len(lines) - 2
    for line_item in part_lines:
        seq_num = int(line_item.split(":")[-1])
        assert seq_num > 2

    # Malformed / mismatched Last-Event-ID
    r_bad_cursor = client.get(
        f"/api/runs/{run_id}/events",
        headers={"Last-Event-ID": "foreign-run-id:1"},
    )
    assert r_bad_cursor.status_code == 400

    # Unknown runId -> 404 JSON
    r_unknown = client.get("/api/runs/00000000-0000-0000-0000-000000000000/events")
    assert r_unknown.status_code == 404


@pytest.mark.stage6
def test_server_runs_status_and_cancellation(client_app):
    """GET and DELETE /api/runs/{runId} status and cancellation lifecycle."""
    client, _ = client_app
    b_res = client.post("/api/build", json={"spec": F2_SPEC})
    run_id = b_res.json()["runId"]

    # Delete while running or just started -> 202 or 204
    del_res = client.delete(f"/api/runs/{run_id}")
    assert del_res.status_code in (202, 204)

    # Wait until terminal
    deadline = time.time() + 5.0
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id}").json()
        if st["state"] == "terminal":
            break
        time.sleep(0.05)

    # Terminal deletion -> 204
    del_term = client.delete(f"/api/runs/{run_id}")
    assert del_term.status_code == 204

    # Unknown deletion -> 404
    del_unk = client.delete("/api/runs/00000000-0000-0000-0000-000000000000")
    assert del_unk.status_code == 404


@pytest.mark.stage6
def test_server_security_middleware(client_app):
    """Security middleware rejects invalid Host, Origin, payload size, and unknown routes."""
    client, _ = client_app
    # Host validation: loopback allowed, evil host rejected with 403
    r_host_bad = client.get("/api/meta", headers={"Host": "evil.com"})
    assert r_host_bad.status_code == 403
    assert r_host_bad.json()["error"]["code"] == "FORBIDDEN_HOST"

    # Origin validation: foreign origin on mutating POST -> 403
    r_origin_bad = client.post(
        "/api/check",
        json={"spec": "x"},
        headers={"Origin": "https://malicious.example.com"},
    )
    assert r_origin_bad.status_code == 403
    assert r_origin_bad.json()["error"]["code"] == "FORBIDDEN_ORIGIN"

    # Payload size limit: Content-Length > 1 MiB -> 413
    r_body_huge = client.post(
        "/api/check",
        content=b"x" * 1048577,
        headers={"Content-Type": "application/json"},
    )
    assert r_body_huge.status_code == 413
    assert r_body_huge.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

    # API 404 catch-all: /api/* routes must return 404 JSON, never HTML
    r_unknown_api = client.get("/api/nonexistent/sub/path")
    assert r_unknown_api.status_code == 404
    assert "application/json" in r_unknown_api.headers["content-type"]
    assert r_unknown_api.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.stage6
def test_server_static_fallback():
    """Server mounts static assets at root, but preserves structured 404 for /api."""
    with tempfile.TemporaryDirectory() as static_tmp:
        static_dir = Path(static_tmp)
        (static_dir / "index.html").write_text("<html>TrustC UI</html>", encoding="utf-8")
        (static_dir / "style.css").write_text("body { margin: 0; }", encoding="utf-8")

        app = create_app(static_dir=static_dir)
        with TestClient(app) as client:
            # Root serves index.html
            r_root = client.get("/")
            assert r_root.status_code == 200
            assert "TrustC UI" in r_root.text

            # Static asset serves file
            r_css = client.get("/style.css")
            assert r_css.status_code == 200
            assert "margin: 0" in r_css.text

            # SPA fallback serves index.html
            r_spa = client.get("/editor/specs/1")
            assert r_spa.status_code == 200
            assert "TrustC UI" in r_spa.text

            # /api/* unknown route must return 404 JSON, NOT index.html
            r_api = client.get("/api/nonexistent")
            assert r_api.status_code == 404
            assert "application/json" in r_api.headers["content-type"]
            assert r_api.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.stage6
def test_server_host_bind_loopback_restriction() -> None:
    """S6-05: run_server rejects non-loopback bind hosts (e.g. 0.0.0.0, external IPs)."""
    from trustc.server import run_server

    with pytest.raises(ValueError, match="forbidden"):
        run_server(host="0.0.0.0")

    with pytest.raises(ValueError, match="forbidden"):
        run_server(host="192.168.1.50")


@pytest.mark.stage6
def test_server_active_cancellation_202_and_cleanup(client_app):
    """S6-04: DELETE returns 202 while cleanup is pending, followed by terminal result."""
    client, app = client_app
    b_res = client.post("/api/build", json={"spec": F2_SPEC})
    assert b_res.status_code == 202
    run_id = b_res.json()["runId"]

    # Actively cancel while building
    del_res = client.delete(f"/api/runs/{run_id}")
    assert del_res.status_code in (202, 204)

    # Poll status until terminal
    deadline = time.time() + 5.0
    terminal_reached = False
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id}").json()
        if st["state"] == "terminal":
            terminal_reached = True
            break
        time.sleep(0.05)
    assert terminal_reached is True

    # Lock must be released
    assert not app.state.trustc.worker_lock.locked()
    assert app.state.trustc.active_run_id is None


@pytest.mark.stage6
def test_server_publication_race_cancellation(client_app):
    """S6-04: Cancellation before publication prevents broken artifacts from being indexed."""
    client, app = client_app
    b_res = client.post("/api/build", json={"spec": F2_SPEC})
    run_id = b_res.json()["runId"]

    # Mark run record cancelled immediately
    app.state.trustc.runs[run_id].cancelled = True

    # Wait for completion
    deadline = time.time() + 5.0
    while time.time() < deadline:
        st = client.get(f"/api/runs/{run_id}").json()
        if st["state"] == "terminal":
            break
        time.sleep(0.05)

    # Result must be cancelled (exitCode 130), and zero published builds added
    res_data = client.get(f"/api/runs/{run_id}").json()["result"]
    assert res_data["status"] == "cancelled"
    assert res_data["exitCode"] == 130
    assert len(app.state.trustc.builds) == 0


@pytest.mark.stage6
def test_server_spec_utf8_size_limit(client_app):
    """S6-05: Specification exceeding 256 KiB limit is rejected with 413."""
    client, _ = client_app
    huge_spec = "# " + ("A" * 262145)
    r = client.post("/api/check", json={"spec": huge_spec})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.stage6
def test_server_content_type_mutating_requests(client_app):
    """S6-05: Mutating API requests without application/json Content-Type are rejected."""
    client, _ = client_app
    # Mutating POST to /api/check with text/plain
    r_check = client.post(
        "/api/check",
        content=b"invalid text",
        headers={"Content-Type": "text/plain"},
    )
    assert r_check.status_code in (400, 415)

    # Mutating POST to /api/build without application/json
    r_build = client.post(
        "/api/build",
        content=b"invalid text",
        headers={"Content-Type": "text/plain"},
    )
    assert r_build.status_code in (400, 415)


@pytest.mark.stage6
def test_server_download_traversal_refusal(client_app):
    """S6-05: Directory traversal in buildId is refused with 400 or 403."""
    client, _ = client_app
    r_trav = client.get("/api/builds/../../etc/out.zip")
    assert r_trav.status_code in (400, 403, 404)


@pytest.mark.stage6
def test_server_restart_session_id_changes():
    """S6-04: Fresh server instance generates a fresh unique sessionId."""
    with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
        app1 = create_app(workspace_dir=Path(td1))
        app2 = create_app(workspace_dir=Path(td2))
        assert app1.state.trustc.session_id != app2.state.trustc.session_id
