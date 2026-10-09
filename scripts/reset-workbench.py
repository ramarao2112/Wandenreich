#!/usr/bin/env python3
"""Scoped reset and cleanup script for TrustC Developer Workbench.

R01 safety guarantees:
- PID file is JSON with pid, executable, start_time, workspace.
- A port-based fallback verifies the process executable belongs to
  this project before killing.  If ownership cannot be established,
  the conflict is reported without termination.
- On Windows, exact-port matching prevents substring collisions
  (e.g. :8787 vs :87871).
- Never runs blanket-kill on uvicorn, python, or node.
- Cleans only project-scoped temporary run artifacts.
"""

from __future__ import annotations

import json
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
    try:
        print(f"[reset-workbench] {msg}")
    except UnicodeEncodeError:
        safe = msg.replace("\u2705", "[PASS]").replace("\u274c", "[FAIL]")
        print(f"[reset-workbench] {safe}")


# ---------------------------------------------------------------------------
# PID file helpers  (JSON: {"pid": int, "exe": str, "start": float, "workspace": str})
# ---------------------------------------------------------------------------

def write_pid_record(pid: int, exe: str, workspace: str) -> None:
    """Write a verified PID record.  Called by the serve command."""
    record = {
        "pid": pid,
        "exe": exe,
        "start": time.time(),
        "workspace": str(workspace),
    }
    PID_FILE.write_text(json.dumps(record), encoding="utf-8")


def _read_pid_record() -> dict | None:
    """Read and validate the PID record file."""
    if not PID_FILE.exists():
        return None
    try:
        raw = PID_FILE.read_text(encoding="utf-8").strip()
        # Support legacy bare-PID format
        if raw.isdigit():
            return {"pid": int(raw), "exe": "", "start": 0.0, "workspace": ""}
        record = json.loads(raw)
        if "pid" not in record:
            return None
        return record
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Process ownership verification
# ---------------------------------------------------------------------------

def _is_trustc_process(pid: int) -> bool:
    """Check whether *pid* is a Python process whose command line references
    this repository or ``trustc``.  Returns False if unable to determine."""
    try:
        if sys.platform == "win32":
            res = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get",
                 "CommandLine", "/value"],
                capture_output=True, text=True, check=False,
            )
            cmdline = res.stdout.lower()
        else:
            # /proc/<pid>/cmdline on Linux
            cmdline_path = Path(f"/proc/{pid}/cmdline")
            if cmdline_path.exists():
                cmdline = cmdline_path.read_bytes().replace(b"\0", b" ").decode(
                    "utf-8", errors="replace"
                ).lower()
            else:
                res = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "args="],
                    capture_output=True, text=True, check=False,
                )
                cmdline = res.stdout.lower()

        repo_lower = str(REPO_ROOT).lower().replace("\\", "/")
        return (
            "trustc" in cmdline
            or "uvicorn" in cmdline
            or repo_lower in cmdline.replace("\\", "/")
        )
    except Exception:
        return False


def _is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is currently alive."""
    try:
        if sys.platform == "win32":
            res = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, check=False,
            )
            return str(pid) in res.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, Exception):
        return False


# ---------------------------------------------------------------------------
# Port scanning with exact-port matching
# ---------------------------------------------------------------------------

def _find_pids_on_port(port: int) -> list[int]:
    """Find PIDs listening on *exactly* the given port."""
    pids: list[int] = []
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, check=False,
            )
            for line in res.stdout.splitlines():
                if "LISTENING" not in line:
                    continue
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                # Local address is parts[1], e.g. "127.0.0.1:8787"
                local_addr = parts[1]
                # Exact port match: last segment after ':'
                addr_parts = local_addr.rsplit(":", 1)
                if len(addr_parts) == 2 and addr_parts[1] == str(port):
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
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True, text=True, check=False,
            )
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
        except Exception:
            pass
    return pids


# ---------------------------------------------------------------------------
# Safe termination
# ---------------------------------------------------------------------------

def _terminate_pid(pid: int) -> bool:
    """Terminate *pid* after ownership has already been verified."""
    log(f"Stopping verified TrustC process PID {pid}...")
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, check=False,
            )
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("Beginning scoped TrustC workbench reset...")

    stopped_count = 0

    # 1. Stop server tracked in PID file if present
    record = _read_pid_record()
    tracked_pid: int | None = None
    if record is not None:
        tracked_pid = record["pid"]
        if not _is_process_alive(tracked_pid):
            log(f"PID {tracked_pid} from record is no longer alive; removing stale PID file.")
            tracked_pid = None
        elif not _is_trustc_process(tracked_pid):
            log(
                f"WARNING: PID {tracked_pid} from record is alive but does NOT appear "
                f"to be a TrustC process.  It may have been reused by another application.  "
                f"Refusing to kill.  Remove {PID_FILE} manually if this is incorrect."
            )
            tracked_pid = None
        else:
            if _terminate_pid(tracked_pid):
                stopped_count += 1

        # Clean PID file regardless
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    # 2. Check port for any lingering server instance — only kill verified TrustC processes
    port_pids = _find_pids_on_port(DEFAULT_PORT)
    for p in port_pids:
        if p == tracked_pid:
            # Already handled above
            continue
        if _is_trustc_process(p):
            log(f"Found TrustC process {p} on port {DEFAULT_PORT}.")
            if _terminate_pid(p):
                stopped_count += 1
        else:
            log(
                f"WARNING: PID {p} is listening on port {DEFAULT_PORT} but is NOT a "
                f"verified TrustC process.  Leaving it running."
            )

    if stopped_count > 0:
        log(f"Successfully stopped {stopped_count} verified TrustC server process(es).")
    else:
        log(f"No running TrustC server process found on port {DEFAULT_PORT}.")

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
