#!/usr/bin/env python3
"""Stage 7 smoke test: UI static file serving, SPA routing, API isolation, and live workflow."""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def http_get(url: str, timeout: float = 5.0) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "TrustC-UI-Smoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, resp.read()
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, headers, e.read()


def http_post(url: str, data: dict, timeout: float = 5.0) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "TrustC-UI-Smoke/1.0",
            "Content-Type": "application/json",
            "Origin": "http://127.0.0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, resp.read()
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, headers, e.read()


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ui_dist = repo_root / "ui" / "dist"
    index_html = ui_dist / "index.html"

    print("=== Stage 7 UI and Server Smoke Test ===")

    if not index_html.exists():
        print(f"FAIL: UI build artifact not found at {index_html}")
        return 1

    port = find_free_port()
    tmp_workspace = tempfile.mkdtemp(prefix="trustc_ui_smoke_")

    python_exe = sys.executable
    server_cmd = [
        python_exe,
        "-c",
        (
            f"import sys; sys.path.insert(0, {json.dumps(str(repo_root / 'src'))}); "
            f"from trustc.server import run_server; "
            f"run_server(host='127.0.0.1', port={port}, static_dir={json.dumps(str(ui_dist))}, "
            f"workspace_dir={json.dumps(tmp_workspace)})"
        ),
    ]

    print(f"Starting TrustC server on port {port} with static_dir={ui_dist}...")
    proc = subprocess.Popen(
        server_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    try:
        # 1. Wait for server readiness
        base_url = f"http://127.0.0.1:{port}"
        ready = False
        for _ in range(50):
            try:
                code, _, body = http_get(f"{base_url}/api/meta", timeout=1.0)
                if code == 200:
                    meta = json.loads(body.decode("utf-8"))
                    print(f"  [1/8] Server online. Session ID: {meta.get('sessionId')}")
                    ready = True
                    break
            except Exception:
                time.sleep(0.1)

        if not ready:
            print("FAIL: Server failed to start within 5 seconds.")
            return 1

        # 2. Test GET / serves index.html
        code, headers, body = http_get(f"{base_url}/")
        assert code == 200, f"Expected 200 for /, got {code}"
        text = body.decode("utf-8")
        assert '<div id="root">' in text, "index.html missing root element"
        assert "TrustC" in text, "index.html missing TrustC brand"
        print("  [2/8] Root path (/) serves UI index.html successfully.")

        # 3. Test GET static assets
        assets_dir = ui_dist / "assets"
        js_files = list(assets_dir.glob("*.js"))
        assert len(js_files) > 0, "No built JS asset found in ui/dist/assets"
        js_path = js_files[0].name
        code, headers, body = http_get(f"{base_url}/assets/{js_path}")
        assert code == 200, f"Expected 200 for /assets/{js_path}, got {code}"
        assert len(body) > 1000, "JS asset body too small"
        print(f"  [3/8] Static bundle /assets/{js_path} served with {len(body)} bytes.")

        # 4. Test SPA Client-Side Routing Fallback
        code, _, body = http_get(f"{base_url}/diagnostics")
        assert code == 200, f"Expected 200 fallback for /diagnostics, got {code}"
        assert '<div id="root">' in body.decode("utf-8"), "Fallback did not return index.html"
        print("  [4/8] Non-file route (/diagnostics) correctly falls back to SPA index.html.")

        # 5. Test API Path Isolation (must return JSON 404, NEVER index.html!)
        code, headers, body = http_get(f"{base_url}/api/some-nonexistent-endpoint")
        assert code == 404, f"Expected 404 for unknown API path, got {code}"
        assert headers.get("content-type", "").startswith("application/json"), (
            f"Expected JSON content-type for API 404, got {headers.get('content-type')}"
        )
        api_err = json.loads(body.decode("utf-8"))
        assert api_err.get("error", {}).get("code") == "NOT_FOUND", (
            f"Expected NOT_FOUND error code, got {api_err}"
        )
        print("  [5/8] API path isolation verified: /api/unknown returns JSON 404, not index.html.")

        # 6. Test GET /api/examples
        code, _, body = http_get(f"{base_url}/api/examples")
        assert code == 200, f"Expected 200 for /api/examples, got {code}"
        examples = json.loads(body.decode("utf-8"))
        assert len(examples) >= 6, f"Expected at least 6 examples, got {len(examples)}"
        print(f"  [6/8] Catalog /api/examples returned {len(examples)} examples.")

        # 7. Test POST /api/check with F1 and F2
        f1_ex = next(e for e in examples if e["id"].upper() == "F1")
        code, _, body = http_post(f"{base_url}/api/check", {"spec": f1_ex["spec"]})
        assert code == 200, f"Expected 200 for check, got {code}"
        check_f1 = json.loads(body.decode("utf-8"))
        assert check_f1["ok"] is False, "Expected F1 check to fail"
        assert len(check_f1["diagnostics"]) >= 2, "Expected at least 2 diagnostics for F1"

        f2_ex = next(e for e in examples if e["id"].upper() == "F2")
        code, _, body = http_post(f"{base_url}/api/check", {"spec": f2_ex["spec"]})
        assert code == 200, f"Expected 200 for check, got {code}"
        check_f2 = json.loads(body.decode("utf-8"))
        assert check_f2["ok"] is True, "Expected F2 check to pass"
        assert len(check_f2["diagnostics"]) == 0, "Expected 0 diagnostics for F2"
        print("  [7/8] Invariant checking (/api/check) verified for F1 (refused) and F2 (passed).")

        # 8. Test POST /api/build, SSE stream, and artifact zip download
        code, _, body = http_post(f"{base_url}/api/build", {"spec": f2_ex["spec"]})
        assert code == 202, f"Expected 202 for build, got {code}"
        build_job = json.loads(body.decode("utf-8"))
        run_id = build_job["runId"]

        # Read SSE events until terminal
        events_url = f"{base_url}/api/runs/{run_id}/events"
        req = urllib.request.Request(events_url, headers={"Accept": "text/event-stream"})
        terminal_result = None
        with urllib.request.urlopen(req, timeout=10.0) as sse_stream:
            buf = ""
            for line in sse_stream:
                decoded = line.decode("utf-8")
                if decoded.startswith("data:"):
                    raw_json = decoded[5:].strip()
                    if raw_json:
                        event = json.loads(raw_json)
                        payload = event.get("payload", {})
                        if payload.get("type") == "result":
                            terminal_result = payload.get("result")
                            break

        assert terminal_result is not None, "Did not receive terminal result from SSE stream"
        assert terminal_result["status"] == "completed", f"Build failed: {terminal_result}"
        build_id = terminal_result["buildId"]

        # Download out.zip
        zip_url = f"{base_url}/api/builds/{build_id}/out.zip"
        code, headers, zip_data = http_get(zip_url)
        assert code == 200, f"Expected 200 for zip download, got {code}"
        assert headers.get("content-type") == "application/zip", "Expected application/zip"

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            namelist = zf.namelist()
            assert "main.py" in namelist, "Zip missing main.py"
            assert any("router" in n for n in namelist), "Zip missing router module"
            assert "trustc-manifest.json" in namelist, "Zip missing trustc-manifest.json"

        print(f"  [8/8] Build execution and zip download verified ({len(namelist)} files in archive).")
        print("\nAll 8 smoke test assertions PASSED!")
        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp_workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
