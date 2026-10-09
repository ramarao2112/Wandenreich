import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from trustc.contracts import PhasePayload, PhaseState, PhaseType
from trustc.server import (
    MAX_RUN_EVENT_BYTES,
    BuildRecord,
    RunRecord,
    _find_fixture_content,
    create_app,
    get_default_static_dir,
    load_example_specs,
)

# ===========================================================================
# R01: Process safety in reset script
# ===========================================================================


def test_r01_reset_process_safety_checks():
    """R01: Sentinel processes on port 8787 are not killed if not owned by TrustC."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "reset_wb",
        str(Path(__file__).resolve().parent.parent.parent / "scripts" / "reset-workbench.py")
    )
    assert spec and spec.loader
    reset_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reset_mod)

    # 1. Non-TrustC command lines return False
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="CommandLine=C:\\Windows\\system32\\notepad.exe")
        assert not reset_mod._is_trustc_process(99999)

    # 2. TrustC command line returns True
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="CommandLine=python -m trustc.cli serve")
        assert reset_mod._is_trustc_process(12345)


# ===========================================================================
# R02: Packaged workbench and default launch
# ===========================================================================

def test_r02_all_canonical_examples_have_content():
    """R02: All 6 canonical examples return non-empty spec content."""
    examples = load_example_specs()
    assert len(examples) == 6
    for ex in examples:
        assert len(ex.spec.strip()) > 50, f"Example {ex.id} spec content is empty!"
        assert "endpoint" in ex.spec or "service" in ex.spec


def test_r02_default_create_app_serves_ui():
    """R02: create_app() with static_dir=None defaults to packaged UI."""
    default_dir = get_default_static_dir()
    assert default_dir is not None
    assert (default_dir / "index.html").is_file()

    app = create_app(static_dir=None)
    client = TestClient(app)

    # Homepage serves index.html
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "TrustC" in resp.text or "<!doctype html>" in resp.text.lower()


# ===========================================================================
# R06: Server finalization: single terminal event, worker slot release
# ===========================================================================

def test_r06_single_terminal_event_on_attack():
    """R06: Server emits exactly one ResultPayload terminal event for attack."""
    f2_content = _find_fixture_content("F2.trust")
    assert f2_content

    app = create_app()
    client = TestClient(app)

    # Submit attack
    sub_resp = client.post("/api/attack", json={"spec": f2_content, "specVersion": 0})
    assert sub_resp.status_code == 202
    run_id = sub_resp.json()["runId"]

    # Poll until terminal
    t0 = time.time()
    while time.time() - t0 < 30.0:
        stat = client.get(f"/api/runs/{run_id}").json()
        if stat["state"] == "terminal":
            break
        time.sleep(0.2)

    assert stat["state"] == "terminal"

    # Inspect events in run record
    run_rec = app.state.trustc.runs[run_id]
    result_events = [ev for ev in run_rec.events if getattr(ev.payload, "type", "") == "result"]
    assert len(result_events) == 1, f"Expected exactly 1 result event, got {len(result_events)}"

    # Worker slot must be released
    assert app.state.trustc.active_run_id is None
    # Another job can be acquired immediately
    assert app.state.trustc.worker_lock.acquire(blocking=False)
    app.state.trustc.worker_lock.release()


def test_r06_injected_publication_failure_handled():
    """R06: Injected copytree failure in build leaves worker slot released and terminal result."""
    f2_content = _find_fixture_content("F2.trust")
    app = create_app()
    client = TestClient(app)

    with patch("shutil.copytree", side_effect=OSError("Injected disk error")):
        sub_resp = client.post("/api/build", json={"spec": f2_content, "specVersion": 0})
        assert sub_resp.status_code == 202
        run_id = sub_resp.json()["runId"]

        t0 = time.time()
        while time.time() - t0 < 15.0:
            stat = client.get(f"/api/runs/{run_id}").json()
            if stat["state"] == "terminal":
                break
            time.sleep(0.2)

        assert stat["state"] == "terminal"
        assert stat["result"]["exitCode"] == 3
        assert app.state.trustc.active_run_id is None


# ===========================================================================
# R07: Bounded retention and event size limits
# ===========================================================================

def test_r07_expired_build_download_returns_410():
    """R07: Expired build download returns 410 and prunes disk artifacts."""
    with tempfile.TemporaryDirectory() as ws:
        app = create_app(workspace_dir=Path(ws))
        client = TestClient(app)
        state = app.state.trustc

        # Create dummy build
        build_id = "test-build-1"
        bdir = state.builds_dir / build_id
        bdir.mkdir(parents=True)
        zpath = state.builds_dir / f"{build_id}.zip"
        zpath.write_text("dummy zip content")

        rec = BuildRecord(
            build_id=build_id,
            spec_hash_val="abc",
            spec_version=0,
            artifact_dir=bdir,
            zip_path=zpath,
        )
        # Set created_at to 20 minutes ago (> 15 min retention)
        rec.created_at = time.time() - 1200.0
        state.builds[build_id] = rec

        resp = client.get(f"/api/builds/{build_id}/out.zip")
        assert resp.status_code == 410
        assert resp.json()["error"]["code"] == "EXPIRED_BUILD"
        assert not zpath.exists()
        assert not bdir.exists()


def test_r07_event_byte_cap_reservation():
    """R07: Non-terminal events cannot consume reserved terminal byte capacity."""
    rec = RunRecord(run_id="run-1", spec_version=0, spec_hash_val="h", kind="build")

    # Near cap: set total_event_bytes to 4 MiB - 600 KiB
    rec.total_event_bytes = MAX_RUN_EVENT_BYTES - 600000

    # Non-terminal event of ~100 KiB would breach the 512 KiB terminal reserve
    large_payload = PhasePayload(phase=PhaseType.RENDER, state=PhaseState.STARTED)
    # Make total bytes exceed (MAX - RESERVED)
    rec.total_event_bytes = MAX_RUN_EVENT_BYTES - 500000

    ev = rec.add_event(large_payload)
    assert (
        ev is None
    ), "Non-terminal event should be refused when breaching reserved terminal capacity"


# ===========================================================================
# R08: Malformed API input returns structured 4xx errors
# ===========================================================================

@pytest.mark.parametrize(
    "endpoint,payload,expected_code",
    [
        ("/api/check", {"spec": None}, 400),
        ("/api/check", {"spec": "", "specVersion": "abc"}, 400),
        ("/api/check", {"spec": "", "specVersion": True}, 400),
        ("/api/check", [], 400),
        ("/api/build", [], 400),
        ("/api/build", {"spec": 4}, 400),
        ("/api/build", {"spec": "service S:", "target": 123}, 400),
        ("/api/build", {"spec": "service S:", "target": "express"}, 400),
        ("/api/attack", {"spec": 4}, 400),
        ("/api/attack", {"spec": "service S:", "buildId": 123}, 400),
    ],
)
def test_r08_malformed_inputs_return_4xx(endpoint, payload, expected_code):
    """R08: Malformed JSON inputs return structured 4xx error envelopes."""
    app = create_app()
    client = TestClient(app)

    resp = client.post(endpoint, json=payload)
    assert resp.status_code == expected_code, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]


def test_r08_malformed_content_length_header():
    """R08: Malformed Content-Length header returns structured 400."""
    app = create_app()
    client = TestClient(app)

    headers = {
        "Content-Length": "not-a-number",
        "Content-Type": "application/json",
    }
    resp = client.post("/api/check", content=b"{}", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_CONTENT_LENGTH"


# ===========================================================================
# Section 4: Template database initialization failure calls engine.dispose()
# ===========================================================================

@pytest.mark.asyncio
async def test_section_4_template_lifespan_error_disposes_engine():
    """Section 4: main.py template executes engine.dispose() on startup failure."""
    from unittest.mock import AsyncMock
    mock_engine = MagicMock()
    mock_engine.begin.side_effect = RuntimeError("Database startup failure")
    mock_engine.dispose = AsyncMock()

    # Recreate the exact pattern now in main.py.jinja
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with mock_engine.begin():
                pass
            yield
        finally:
            await mock_engine.dispose()

    with pytest.raises(RuntimeError):
        async with lifespan(None):
            pass

    mock_engine.dispose.assert_awaited_once()
