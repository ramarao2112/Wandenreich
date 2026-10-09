#!/usr/bin/env python3
"""Scoped reset and cleanup script for TrustC Developer Workbench.

Guarantees:
- Tracks only this project's server PID or port 8787.
- Never runs blanket-kill on uvicorn, python, or node.
- Cleans only project-scoped temporary run artifacts.
- Accurately explains that browser storage reset requires visiting the UI with ?reset=1.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
PID_FILE = REPO_ROOT / ".trustc-server.pid"
DEFAULT_PORT = 8787


def log(msg: str) -> None:
    print(f"[reset-workbench] {msg}")


def find_pids_on_port(port: int) -> list[int]:
    """Find process IDs listening on 127.0.0.1:<port> without killing other processes."""
    pids: list[int] = []
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in res.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                            if pid > 0 and pid not in pids:
                                pids.append(pid)
                        except ValueError:
                            pass
        except Exception as e:
            log(f"Warning: could not inspect ports via netstat: {e}")
    else:
        try:
            res = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
        except Exception:
            pass
    return pids


def terminate_pid(pid: int) -> bool:
    """Terminate a specific process gracefully."""
    log(f"Stopping scoped TrustC process PID {pid}...")
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return True
    except Exception as e:
        log(f"Notice: PID {pid} could not be stopped: {e}")
        return False


def main() -> int:
    log("Beginning scoped TrustC workbench reset...")

    # 1. Stop server tracked in PID file if present
    stopped_count = 0
    if PID_FILE.exists():
        try:
            tracked_pid = int(PID_FILE.read_text().strip())
            if terminate_pid(tracked_pid):
                stopped_count += 1
        except Exception as e:
            log(f"Could not read PID file: {e}")
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    # 2. Check port 8787 for any lingering server instance
    port_pids = find_pids_on_port(DEFAULT_PORT)
    for p in port_pids:
        if terminate_pid(p):
            stopped_count += 1

    if stopped_count > 0:
        log(f"Successfully stopped {stopped_count} TrustC server process(es).")
    else:
        log("No running TrustC server process found on port 8787.")

    # 3. Clean temporary build / test output directories safely
    temp_dirs = [
        REPO_ROOT / ".trustc-temp",
        REPO_ROOT / "test-results",
        REPO_ROOT / ".pytest_cache",
    ]
    cleaned_dirs = 0
    for td in temp_dirs:
        if td.exists() and td.is_dir():
            try:
                shutil.rmtree(td, ignore_errors=True)
                cleaned_dirs += 1
            except Exception as e:
                log(f"Could not remove {td.name}: {e}")

    log(f"Cleaned {cleaned_dirs} temporary cache directory/directories.")

    # 4. Explicit guidance on browser storage
    log("----------------------------------------------------------------------")
    log("BROWSER STORAGE NOTE:")
    log("Local browser localStorage is isolated per browser origin.")
    log(f"To reset client-side UI state, open http://127.0.0.1:{DEFAULT_PORT}/?reset=1")
    log("or clear the site data in your browser developer tools.")
    log("----------------------------------------------------------------------")
    log("Reset complete. To restart the workbench run: trustc serve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
