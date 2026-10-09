#!/usr/bin/env python3
"""Stage 6 — Local API server, streaming, and artifact lifecycle smoke tester.

Validates the TrustC local API server against A-contracts.md requirements:
1. Meta & Rules Catalog: GET /api/meta, GET /api/examples, GET /api/rules/{id}
2. Specification Checking: POST /api/check (JSON & SARIF formats)
3. Build Execution & Worker Lifecycle: POST /api/build (202 RunAccepted, staging isolation)
4. SSE Streaming: GET /api/runs/{runId}/events (event: trustc, id: <runId>:<seq>, replay)
5. Artifact Delivery: GET /api/builds/{buildId}/out.zip (relative paths only)
6. Attack Execution with Build Link: POST /api/attack (buildId hash verification, live harness)
7. Run Status & Cancellation: GET /api/runs/{runId}, DELETE /api/runs/{runId}
8. Security Middleware: Host header validation, Origin check, size limits, 404 isolation.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def find_free_port() -> int:
    """Find an available port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 12.0) -> bool:
    """Poll /api/meta until server is ready."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = httpx.get(f"{base_url}/api/meta", timeout=0.5)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(0.1)
    return False


def run_server_smoke() -> int:
    """Run full Stage 6 server smoke verification suite."""
    print("=== TrustC Stage 6 Server Smoke Test ===")
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    temp_dir = tempfile.TemporaryDirectory(prefix="trustc_smoke_server_")
    ws_dir = Path(temp_dir.name) / "workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    f2_path = REPO_ROOT / "tests" / "fixtures" / "F2.trust"
    f1_path = REPO_ROOT / "tests" / "fixtures" / "F1.trust"
    f2_spec = f2_path.read_text(encoding="utf-8")
    f1_spec = f1_path.read_text(encoding="utf-8")

    server_proc = None
    try:
        # Launch server subprocess
        print(f"[*] Starting 'trustc serve' on {base_url}...")
        cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workspace",
            str(ws_dir),
        ]
        server_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(REPO_ROOT),
        )

        if not wait_for_server(base_url, timeout=15.0):
            stdout, stderr = "", ""
            if server_proc.poll() is not None:
                stdout, stderr = server_proc.communicate()
            raise RuntimeError(
                f"Server failed to start on {base_url} within 15 seconds. "
                f"stdout: {stdout}, stderr: {stderr}"
            )
        print("  [+] Server is ready and accepting requests.")

        client = httpx.Client(base_url=base_url, timeout=30.0)

        # ---------------------------------------------------------------------
        # 1. GET /api/meta
        # ---------------------------------------------------------------------
        print("[*] Testing GET /api/meta...")
        r = client.get("/api/meta")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        meta = r.json()
        assert meta.get("schemaVersion") == 2, f"Expected schemaVersion 2, got {meta}"
        assert meta.get("version") == "0.1.0"
        assert meta.get("port") == port
        assert meta.get("target") == "fastapi"
        assert len(meta.get("rules", [])) == 5
        print("  [+] /api/meta verified (schemaVersion 2, 5 rules).")

        # ---------------------------------------------------------------------
        # 2. GET /api/examples
        # ---------------------------------------------------------------------
        print("[*] Testing GET /api/examples...")
        r = client.get("/api/examples")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        examples = r.json()
        assert len(examples) == 6, f"Expected 6 examples (F1..F6), got {len(examples)}"
        ex_ids = [e["id"] for e in examples]
        assert ex_ids == ["F1", "F2", "F3", "F4", "F5", "F6"], f"Unexpected IDs: {ex_ids}"
        for ex in examples:
            assert "spec" in ex and len(ex["spec"]) > 0
            assert ex.get("expectedCheck") in ("pass", "fail")
        print("  [+] /api/examples verified (F1..F6 with valid specs).")

        # ---------------------------------------------------------------------
        # 3. GET /api/rules/TC-001
        # ---------------------------------------------------------------------
        print("[*] Testing GET /api/rules/TC-001...")
        r = client.get("/api/rules/TC-001")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        rule_doc = r.json()
        assert rule_doc["id"] == "TC-001"
        assert rule_doc["name"] == "AUTH-REQUIRED"
        assert rule_doc["fixType"] == "diff"
        assert len(rule_doc["checks"]) > 0

        # Invalid rule ID -> 404
        r_bad = client.get("/api/rules/TC-999")
        assert r_bad.status_code == 404
        print("  [+] /api/rules/TC-001 verified and 404 on unknown rule.")

        # ---------------------------------------------------------------------
        # 4. POST /api/check (F1, F2, SARIF)
        # ---------------------------------------------------------------------
        print("[*] Testing POST /api/check...")
        # Check F2 (pass, exitCode 0)
        r = client.post("/api/check", json={"spec": f2_spec, "specVersion": 0})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        res_f2 = r.json()
        assert res_f2.get("ok") is True
        assert res_f2.get("exitCode") == 0
        assert len(res_f2.get("diagnostics", [])) == 0

        # Check F1 (refused, exitCode 1)
        r = client.post("/api/check", json={"spec": f1_spec, "specVersion": 0})
        assert r.status_code == 200
        res_f1 = r.json()
        assert res_f1.get("ok") is False
        assert res_f1.get("exitCode") == 1
        assert len(res_f1.get("diagnostics", [])) > 0

        # Check SARIF output
        r = client.post(
            "/api/check?format=sarif",
            json={"spec": f1_spec, "specVersion": 0},
        )
        assert r.status_code == 200
        sarif = r.json()
        assert sarif.get("version") == "2.1.0"
        assert len(sarif.get("runs", [])) == 1
        print("  [+] /api/check verified (F2 pass, F1 refuse, SARIF export).")

        # ---------------------------------------------------------------------
        # 5. POST /api/build & SSE streaming
        # ---------------------------------------------------------------------
        print("[*] Testing POST /api/build and SSE streaming...")
        r = client.post("/api/build", json={"spec": f2_spec, "specVersion": 0})
        assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
        build_acc = r.json()
        run_id = build_acc.get("runId")
        assert run_id is not None
        print(f"  [+] Build job accepted: runId={run_id}")

        # Stream SSE events
        sse_events = []
        terminal_result = None
        t0 = time.time()
        with client.stream("GET", f"/api/runs/{run_id}/events") as sse_stream:
            buffer = ""
            for chunk in sse_stream.iter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    raw_event, buffer = buffer.split("\n\n", 1)
                    ev_lines = raw_event.strip().splitlines()
                    data_str = ""
                    event_type = ""
                    event_id = ""
                    for line in ev_lines:
                        if line.startswith("event:"):
                            event_type = line[len("event:"):].strip()
                        elif line.startswith("id:"):
                            event_id = line[len("id:"):].strip()
                        elif line.startswith("data:"):
                            data_str = line[len("data:"):].strip()

                    if event_type == "trustc" and data_str:
                        payload = json.loads(data_str)
                        sse_events.append((event_id, payload))
                        p_type = payload.get("payload", {}).get("type")
                        if p_type == "result":
                            terminal_result = payload.get("payload", {}).get("result")
                            break
                if terminal_result is not None:
                    break
                if time.time() - t0 > 25.0:
                    break

        assert len(sse_events) >= 3, f"Expected >=3 SSE events, got {len(sse_events)}"
        assert terminal_result is not None, "Did not receive terminal result event"
        assert terminal_result.get("exitCode") == 0, f"Build failed: {terminal_result}"
        build_id = terminal_result.get("buildId")
        assert build_id is not None, f"Expected buildId in result: {terminal_result}"
        print(f"  [+] Build SSE completed: {len(sse_events)} events, buildId={build_id}")

        # Test Last-Event-ID replay cursor
        r = client.get(
            f"/api/runs/{run_id}/events",
            headers={"Last-Event-ID": f"{run_id}:2"},
        )
        assert r.status_code == 200
        replay_lines = [line_str for line_str in r.text.splitlines() if line_str.startswith("id:")]
        for line_item in replay_lines:
            seq_val = int(line_item.split(":")[-1])
            assert seq_val > 2, f"Replay violation: got event with seq {seq_val} <= 2"
        print("  [+] Last-Event-ID cursor replay verified.")

        # ---------------------------------------------------------------------
        # 6. GET /api/runs/{runId} status
        # ---------------------------------------------------------------------
        print("[*] Testing GET /api/runs/{runId}...")
        r = client.get(f"/api/runs/{run_id}")
        assert r.status_code == 200
        st = r.json()
        assert st.get("state") == "terminal"
        assert st.get("runId") == run_id
        assert st.get("result", {}).get("exitCode") == 0
        print("  [+] Run status verified (state: terminal).")

        # ---------------------------------------------------------------------
        # 7. GET /api/builds/{buildId}/out.zip
        # ---------------------------------------------------------------------
        print("[*] Testing GET /api/builds/{buildId}/out.zip...")
        r = client.get(f"/api/builds/{build_id}/out.zip")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        assert "application/zip" in r.headers.get("content-type", "")

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        for name in names:
            assert not name.startswith("/"), f"Absolute path in ZIP: {name}"
            assert ".." not in name, f"Path traversal in ZIP: {name}"
            assert "\\" not in name, f"Windows backslash in ZIP: {name}"
        assert "trustc-manifest.json" in names
        assert "trustc-report.json" in names
        assert "main.py" in names
        assert "models.py" in names
        print(f"  [+] out.zip verified ({len(names)} entries, clean relative paths).")

        # ---------------------------------------------------------------------
        # 8. POST /api/attack with buildId
        # ---------------------------------------------------------------------
        print("[*] Testing POST /api/attack with buildId...")
        r = client.post(
            "/api/attack",
            json={"spec": f2_spec, "specVersion": 0, "buildId": build_id},
        )
        assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
        atk_acc = r.json()
        atk_run_id = atk_acc.get("runId")
        assert atk_run_id is not None
        print(f"  [+] Attack job accepted: runId={atk_run_id}")

        # Poll until terminal
        t0 = time.time()
        atk_result = None
        while time.time() - t0 < 30.0:
            r = client.get(f"/api/runs/{atk_run_id}")
            if r.status_code == 200 and r.json().get("state") == "terminal":
                atk_result = r.json().get("result")
                break
            time.sleep(0.5)

        assert atk_result is not None, "Attack did not reach terminal state within 30s"
        assert atk_result.get("exitCode") == 0, f"Attack failed: {atk_result}"
        assert atk_result.get("asExpected") == 6, f"Expected 6 as_expected: {atk_result}"
        assert atk_result.get("review") == 0, f"Expected 0 review: {atk_result}"
        assert atk_result.get("unexpected") == 0, f"Expected 0 unexpected: {atk_result}"
        print("  [+] Attack completed: 6 as_expected, 0 review, 0 unexpected (exitCode 0).")

        # ---------------------------------------------------------------------
        # 9. DELETE /api/runs/{runId}
        # ---------------------------------------------------------------------
        print("[*] Testing DELETE /api/runs/{runId}...")
        # Terminal run -> 204
        r = client.delete(f"/api/runs/{atk_run_id}")
        assert r.status_code == 204, f"Expected 204, got {r.status_code}"
        # Unknown run -> 404
        r = client.delete("/api/runs/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        print("  [+] DELETE lifecycle verified (204 on terminal, 404 on unknown).")

        # ---------------------------------------------------------------------
        # 10. Security Middleware Checks
        # ---------------------------------------------------------------------
        print("[*] Testing Security Middleware...")
        # Malicious Host -> 403
        r = client.get("/api/meta", headers={"Host": "attacker.local"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"

        # Malicious Origin on mutating POST -> 403
        r = client.post(
            "/api/check",
            json={"spec": "x"},
            headers={"Origin": "http://evil-website.com"},
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"

        # Oversized body -> 413
        r = client.post(
            "/api/check",
            content=b"x" * 1048577,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413, f"Expected 413, got {r.status_code}"

        # Oversized spec -> 413
        r = client.post(
            "/api/check",
            json={"spec": "x" * 262145},
        )
        assert r.status_code == 413, f"Expected 413, got {r.status_code}"

        # Invalid Content-Type -> 400
        r = client.post(
            "/api/check",
            content=b"{}",
            headers={"Content-Type": "text/plain"},
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"

        # Unknown /api path -> 404 JSON (NOT html)
        r = client.get("/api/unknown/endpoint")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        assert "application/json" in r.headers.get("content-type", "")
        print("  [+] Security middleware verified (Host, Origin, limits, 404 JSON).")

        print("\n[PASS] [ALL PASS] TrustC Stage 6 Server Smoke Suite Succeeded 100%.")
        return 0

    finally:
        if server_proc is not None:
            print("[*] Terminating server subprocess...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                server_proc.kill()
        temp_dir.cleanup()


if __name__ == "__main__":
    sys.exit(run_server_smoke())
