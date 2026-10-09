#!/usr/bin/env python3
"""Run Playwright browser tests and axe checks against the live production UI server."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for_server(url: str, timeout: float = 15.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TrustC-Browser-Runner/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ui_dir = repo_root / "ui"
    ui_dist = ui_dir / "dist"
    index_html = ui_dist / "index.html"
    npm_exe = shutil.which("npm.cmd" if sys.platform == "win32" else "npm") or "npm"
    npx_exe = shutil.which("npx.cmd" if sys.platform == "win32" else "npx") or "npx"

    print("=== TrustC Real-Browser Playwright & Axe Suite ===")

    # Ensure UI production bundle is built
    if not index_html.exists():
        print("Building UI production bundle before running browser tests...")
        build_res = subprocess.run([npm_exe, "run", "build"], cwd=str(ui_dir))
        if build_res.returncode != 0:
            print("ERROR: Failed to build UI production bundle.")
            return build_res.returncode

    port = find_free_port()
    tmp_workspace = tempfile.mkdtemp(prefix="trustc_browser_test_")
    base_url = f"http://127.0.0.1:{port}"

    server_cmd = [
        sys.executable,
        "-c",
        (
            f"import sys; sys.path.insert(0, {json.dumps(str(repo_root / 'src'))}); "
            f"from trustc.server import run_server; "
            f"run_server(host='127.0.0.1', port={port}, static_dir={json.dumps(str(ui_dist))}, "
            f"workspace_dir={json.dumps(tmp_workspace)})"
        ),
    ]

    server_log_path = repo_root / "review-logs" / "stage-7" / "server-browser-test.log"
    server_log_file = open(server_log_path, "w", encoding="utf-8")
    server_proc = subprocess.Popen(
        server_cmd,
        cwd=str(repo_root),
        stdout=server_log_file,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    try:
        print(f"Starting live FastAPI UI server on {base_url}...")
        meta_url = f"{base_url}/api/meta"
        if not wait_for_server(meta_url, timeout=15.0):
            print("ERROR: Server did not become ready in time.")
            return 1
        print("Server is healthy! Launching Playwright tests in Chromium...")

        env = {
            **os.environ,
            "PLAYWRIGHT_BASE_URL": base_url,
        }

        # Run Playwright tests
        test_cmd = [npx_exe, "playwright", "test"]
        print(f"Running: {' '.join(test_cmd)}")
        res = subprocess.run(test_cmd, cwd=str(ui_dir), env=env)
        print(f"\nPlaywright test run finished with exit code: {res.returncode}")
        return res.returncode

    finally:
        print("Shutting down test UI server...")
        try:
            server_proc.terminate()
            server_proc.wait(timeout=3.0)
        except Exception:
            server_proc.kill()
        try:
            shutil.rmtree(tmp_workspace, ignore_errors=True)
        except Exception:
            pass
        try:
            server_log_file.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
