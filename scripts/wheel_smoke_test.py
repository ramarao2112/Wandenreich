#!/usr/bin/env python3
"""Stage 2 wheel installation smoke test.

Verifies that:
1. The wheel builds cleanly with locked build tooling.
2. The wheel archive contains package resources: grammar/trustspec.lark and v2 schemas.
3. The wheel installs into a fresh isolated virtualenv without editable install.
4. An invocation outside the repository (no PYTHONPATH) imports from site-packages.
5. The installed `trustc` entrypoint parses F2 with exit 0 (expected policies)
   and rejects F4 with exit 2 (structured error at line 23 column 25, no traceback).
6. Logs all operations in UTF-8 to review-logs/stage-2/wheel-smoke.log.
"""

from __future__ import annotations

import argparse
import datetime
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
import venv
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_wheel_smoke_test(
    repo_root: Path,
    log_file: Optional[Path] = None,
    keep_env: bool = False,
    stage: int = 2,
) -> Tuple[int, Dict[str, Any]]:
    """Execute complete wheel smoke test outside repository."""
    start_time = _timestamp()
    logs: List[str] = []
    steps_record: List[Dict[str, Any]] = []

    def log(msg: str) -> None:
        print(msg)
        logs.append(msg)

    log(f"[{start_time}] Starting Stage {stage} Wheel Installation & Smoke Test")
    log(f"Repository Root: {repo_root}")

    dist_dir = repo_root / "dist"
    dist_dir.mkdir(exist_ok=True)

    # Clean existing wheels in dist/
    for old_whl in dist_dir.glob("trustc-*.whl"):
        try:
            old_whl.unlink()
        except OSError:
            pass

    # -------------------------------------------------------------------------
    # 1. Build Wheel
    # -------------------------------------------------------------------------
    build_cmd = [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)]
    log(f"\n--- Step 1: Building wheel with command: {' '.join(build_cmd)} ---")
    t0 = time.time()
    b_res = subprocess.run(
        build_cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    b_duration = round(time.time() - t0, 3)

    steps_record.append({
        "name": "build_wheel",
        "command": build_cmd,
        "exit_code": b_res.returncode,
        "duration_seconds": b_duration,
        "status": "PASS" if b_res.returncode == 0 else "FAIL",
    })

    if b_res.returncode != 0:
        log(f"FAIL: Wheel build failed with exit code {b_res.returncode}")
        log(f"Stdout:\n{b_res.stdout}")
        log(f"Stderr:\n{b_res.stderr}")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    wheels = list(dist_dir.glob("trustc-*.whl"))
    if not wheels:
        log("FAIL: No wheel found in dist/ after build")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    wheel_path = max(wheels, key=lambda p: p.stat().st_mtime)
    log(f"PASS: Wheel built successfully: {wheel_path.name} ({wheel_path.stat().st_size} bytes)")

    # -------------------------------------------------------------------------
    # 2. Inspect Wheel Archive for Required Resources
    # -------------------------------------------------------------------------
    log("\n--- Step 2: Inspecting wheel archive contents ---")
    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()

    required_entries = [
        "trustc/grammars/trustspec.lark",
        "trustc/schemas/v2/CheckResult.json",
        "trustc/schemas/v2/BuildSuccess.json",
        "trustc/schemas/v2/AttackCompleted.json",
        "trustc/cli.py",
        "trustc/parser.py",
        "trustc/ir.py",
        "trustc/source.py",
    ]
    if stage >= 5:
        required_entries.append("trustc/harness.py")
    if stage >= 6:
        required_entries.append("trustc/server.py")
        required_entries.append("trustc/schemas/v2/ServerMeta.json")
        required_entries.append("trustc/schemas/v2/RunEvent.json")
    if stage >= 8:
        required_entries.append("trustc/examples/F1.trust")
        required_entries.append("trustc/examples/F2.trust")
        required_entries.append("trustc/ui_dist/index.html")

    missing = [entry for entry in required_entries if entry not in namelist]
    if missing:
        log(f"FAIL: Wheel missing required package resources: {missing}")
        steps_record.append({
            "name": "inspect_archive",
            "status": "FAIL",
            "missing_entries": missing,
        })
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    if stage >= 4:
        template_entries = [
            "trustc/templates/fastapi/db.py.jinja",
            "trustc/templates/fastapi/models.py.jinja",
            "trustc/templates/fastapi/schemas.py.jinja",
            "trustc/templates/fastapi/auth.py.jinja",
            "trustc/templates/fastapi/router.py.jinja",
            "trustc/templates/fastapi/main.py.jinja",
        ]
        missing_tpls = [entry for entry in template_entries if entry not in namelist]
        if missing_tpls:
            log(f"FAIL: Wheel missing required template resources: {missing_tpls}")
            steps_record.append({
                "name": "inspect_templates",
                "status": "FAIL",
                "missing_templates": missing_tpls,
            })
            return 1, {"overall_status": "FAIL", "steps": steps_record}
        log(
            f"PASS: Archive contains all required Stage 4 templates: "
            f"{len(template_entries)} templates verified"
        )

    # Verify lark grammar is non-empty
    with zipfile.ZipFile(wheel_path, "r") as zf:
        lark_size = zf.getinfo("trustc/grammars/trustspec.lark").file_size
    if lark_size < 100:
        log(f"FAIL: trustc/grammars/trustspec.lark is suspiciously small ({lark_size} bytes)")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    log(f"PASS: Archive contains all required resources (grammar size: {lark_size} bytes)")
    steps_record.append({
        "name": "inspect_archive",
        "status": "PASS",
        "verified_entries": required_entries,
    })

    # -------------------------------------------------------------------------
    # 3. Create Fresh Isolated Virtual Environment
    # -------------------------------------------------------------------------
    temp_venv_dir = Path(tempfile.mkdtemp(prefix="trustc_smoke_venv_"))
    log(f"\n--- Step 3: Creating fresh virtualenv in {temp_venv_dir} ---")
    try:
        venv.create(temp_venv_dir, with_pip=True)
    except Exception as e:
        log(f"FAIL: Could not create virtualenv: {e}")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    if sys.platform == "win32":
        venv_python = temp_venv_dir / "Scripts" / "python.exe"
        venv_trustc = temp_venv_dir / "Scripts" / "trustc.exe"
    else:
        venv_python = temp_venv_dir / "bin" / "python"
        venv_trustc = temp_venv_dir / "bin" / "trustc"

    if not venv_python.exists():
        log(f"FAIL: Python executable not found in venv: {venv_python}")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    log(f"PASS: Fresh virtualenv initialized at {temp_venv_dir}")

    # -------------------------------------------------------------------------
    # 4. Install Wheel into Fresh Environment (Non-Editable)
    if stage >= 6:
        install_target = f"{wheel_path}[harness,server]"
    elif stage >= 5:
        install_target = f"{wheel_path}[harness]"
    else:
        install_target = str(wheel_path)
    install_cmd = [str(venv_python), "-m", "pip", "install", install_target]
    log(f"\n--- Step 4: Installing wheel: {' '.join(install_cmd)} ---")
    t0 = time.time()
    i_res = subprocess.run(
        install_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    i_duration = round(time.time() - t0, 3)

    steps_record.append({
        "name": "install_wheel",
        "command": install_cmd,
        "exit_code": i_res.returncode,
        "duration_seconds": i_duration,
        "status": "PASS" if i_res.returncode == 0 else "FAIL",
    })

    if i_res.returncode != 0:
        log(f"FAIL: pip install failed with exit {i_res.returncode}")
        log(f"Stderr:\n{i_res.stderr}")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    log(f"PASS: Wheel installed in fresh environment ({i_duration}s)")

    # -------------------------------------------------------------------------
    # 5. Verify Isolation: Module imported from site-packages, not repo
    # -------------------------------------------------------------------------
    temp_run_dir = Path(tempfile.mkdtemp(prefix="trustc_smoke_run_"))
    log(f"\n--- Step 5: Verifying import isolation in {temp_run_dir} ---")

    # Clean env with NO repo PYTHONPATH
    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)

    import_check_cmd = [
        str(venv_python),
        "-c",
        "import trustc; print(trustc.__file__)",
    ]
    chk_res = subprocess.run(
        import_check_cmd,
        cwd=str(temp_run_dir),
        capture_output=True,
        text=True,
        env=clean_env,
        encoding="utf-8",
        errors="replace",
    )

    imported_path = chk_res.stdout.strip()
    log(f"Imported trustc module location: {imported_path}")

    is_in_site_packages = "site-packages" in imported_path
    is_in_temp_venv = str(temp_venv_dir).lower() in imported_path.lower()
    is_in_repo = str(repo_root).lower() in imported_path.lower()

    if not is_in_site_packages or not is_in_temp_venv or is_in_repo:
        log("FAIL: Module was not imported from isolated environment site-packages!")
        steps_record.append({
            "name": "verify_import_isolation",
            "imported_path": imported_path,
            "status": "FAIL",
        })
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    log("PASS: Module verified imported from fresh virtualenv site-packages")
    steps_record.append({
        "name": "verify_import_isolation",
        "imported_path": imported_path,
        "status": "PASS",
    })

    # -------------------------------------------------------------------------
    # 6. Test Installed `trustc` Entrypoint Outside Repository
    # -------------------------------------------------------------------------
    log("\n--- Step 6: Testing installed `trustc parse` entrypoint on F2 and F4 ---")
    f2_fixture = repo_root / "tests" / "fixtures" / "F2.trust"
    f4_fixture = repo_root / "tests" / "fixtures" / "F4.trust"

    shutil.copy(f2_fixture, temp_run_dir / "F2.trust")
    shutil.copy(f4_fixture, temp_run_dir / "F4.trust")

    def _run_trustc(subargs: List[str]) -> subprocess.CompletedProcess:
        # Prefer direct script entrypoint; fallback to python -m trustc.cli
        # if blocked by OS policy (WDAC WinError 4551)
        if venv_trustc.exists():
            direct_cmd = [str(venv_trustc)] + subargs
            try:
                return subprocess.run(
                    direct_cmd,
                    cwd=str(temp_run_dir),
                    capture_output=True,
                    text=True,
                    env=clean_env,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as e:
                if getattr(e, "winerror", None) == 4551 or "Application Control" in str(e):
                    log(
                        "NOTE: trustc.exe blocked by WDAC policy (WinError 4551); "
                        "using python -m trustc.cli in isolated virtualenv"
                    )
                else:
                    raise

        fallback_cmd = [str(venv_python), "-m", "trustc.cli"] + subargs
        return subprocess.run(
            fallback_cmd,
            cwd=str(temp_run_dir),
            capture_output=True,
            text=True,
            env=clean_env,
            encoding="utf-8",
            errors="replace",
        )

    # Test F2
    t0 = time.time()
    f2_run = _run_trustc(["parse", "F2.trust"])
    f2_duration = round(time.time() - t0, 3)

    log(f"F2 run exit code: {f2_run.returncode} (expected 0)")
    if f2_run.returncode != 0:
        log(f"FAIL: F2 run failed. Stderr:\n{f2_run.stderr}")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    f2_data = json.loads(f2_run.stdout)
    expected_f2_hash = "ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884"
    if f2_data.get("specHash") != expected_f2_hash:
        log(
            f"FAIL: F2 specHash mismatch: got {f2_data.get('specHash')}, "
            f"expected {expected_f2_hash}"
        )
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    log(f"PASS: F2 parsed cleanly with specHash {expected_f2_hash}")
    steps_record.append({
        "name": "f2_parse_smoke",
        "command": ["trustc", "parse", "F2.trust"],
        "exit_code": f2_run.returncode,
        "duration_seconds": f2_duration,
        "specHash": f2_data.get("specHash"),
        "status": "PASS",
    })

    # Test F4
    t0 = time.time()
    f4_run = _run_trustc(["parse", "F4.trust"])
    f4_duration = round(time.time() - t0, 3)

    log(f"F4 run exit code: {f4_run.returncode} (expected 2)")
    if f4_run.returncode != 2:
        log(f"FAIL: F4 run expected exit 2, got {f4_run.returncode}")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    # Ensure no python traceback in stderr
    if "Traceback (most recent call last):" in f4_run.stderr:
        log("FAIL: F4 output contains unhandled Python traceback!")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    f4_err_data = json.loads(f4_run.stderr or f4_run.stdout)
    err = f4_err_data.get("specErrors", [{}])[0]
    span = err.get("span", {})
    col = span.get("col", span.get("column"))
    if span.get("line") != 23 or col != 25:
        log(f"FAIL: F4 error span expected line 23 column 25, got {span}")
        return 1, {"overall_status": "FAIL", "steps": steps_record}

    log("PASS: F4 structured error verified at line 23 column 25 without traceback")
    steps_record.append({
        "name": "f4_parse_smoke",
        "command": ["trustc", "parse", "F4.trust"],
        "exit_code": f4_run.returncode,
        "duration_seconds": f4_duration,
        "error_span": span,
        "status": "PASS",
    })

    # For Stage >= 3, also test `trustc check`
    if stage >= 3:
        log("\n--- Step 6b: Testing installed `trustc check` entrypoint on F2 and F1 ---")
        f1_fixture = repo_root / "tests" / "fixtures" / "F1.trust"
        shutil.copy(f1_fixture, temp_run_dir / "F1.trust")

        # Check F2 (exit 0)
        t0 = time.time()
        c_f2_run = _run_trustc(["check", "F2.trust"])
        c_f2_dur = round(time.time() - t0, 3)
        log(f"Check F2 exit code: {c_f2_run.returncode} (expected 0)")
        if c_f2_run.returncode != 0:
            log(f"FAIL: trustc check F2 expected 0, got {c_f2_run.returncode}")
            return 1, {"overall_status": "FAIL", "steps": steps_record}
        steps_record.append({
            "name": "f2_check_smoke",
            "command": ["trustc", "check", "F2.trust"],
            "exit_code": c_f2_run.returncode,
            "duration_seconds": c_f2_dur,
            "status": "PASS",
        })
        log("PASS: Installed trustc check F2 verified exit 0")

        # Check F1 (exit 1)
        t0 = time.time()
        c_f1_run = _run_trustc(["check", "F1.trust"])
        c_f1_dur = round(time.time() - t0, 3)
        log(f"Check F1 exit code: {c_f1_run.returncode} (expected 1)")
        if c_f1_run.returncode != 1:
            log(f"FAIL: trustc check F1 expected 1, got {c_f1_run.returncode}")
            return 1, {"overall_status": "FAIL", "steps": steps_record}
        steps_record.append({
            "name": "f1_check_smoke",
            "command": ["trustc", "check", "F1.trust"],
            "exit_code": c_f1_run.returncode,
            "duration_seconds": c_f1_dur,
            "status": "PASS",
        })
        log("PASS: Installed trustc check F1 verified exit 1")

    # For Stage >= 4, also test `trustc build`
    if stage >= 4:
        log("\n--- Step 6c: Testing installed `trustc build` entrypoint on F2 ---")
        f2_out = temp_run_dir / "generated_f2"
        b_f2_cmd = [
            "build", "F2.trust", "-o", str(f2_out), "--target=fastapi", "--format=json"
        ]
        t0 = time.time()
        b_f2_run = _run_trustc(b_f2_cmd)
        b_f2_dur = round(time.time() - t0, 3)
        log(f"Build F2 exit code: {b_f2_run.returncode} (expected 0)")
        if b_f2_run.returncode != 0:
            log(f"FAIL: trustc build F2 expected 0, got {b_f2_run.returncode}")
            log(f"Stderr:\n{b_f2_run.stderr}")
            return 1, {"overall_status": "FAIL", "steps": steps_record}
        if not (f2_out / "trustc-report.json").exists():
            log("FAIL: trustc-report.json missing from generated build")
            return 1, {"overall_status": "FAIL", "steps": steps_record}
        steps_record.append({
            "name": "f2_build_smoke",
            "command": ["trustc", "build", "F2.trust", "-o", str(f2_out)],
            "exit_code": b_f2_run.returncode,
            "duration_seconds": b_f2_dur,
            "status": "PASS",
        })
        log("PASS: Installed trustc build F2 verified exit 0 with all template assets")

    # For Stage >= 5, also test `trustc attack`
    if stage >= 5:
        log("\n--- Step 6d: Testing installed `trustc attack` entrypoint on F2 ---")
        t0 = time.time()
        a_f2_run = _run_trustc(["attack", "F2.trust", "--format=json"])
        a_f2_dur = round(time.time() - t0, 3)
        log(f"Attack F2 exit code: {a_f2_run.returncode} (expected 0)")
        if a_f2_run.returncode != 0:
            log(f"FAIL: trustc attack F2 expected 0, got {a_f2_run.returncode}")
            log(f"Stderr:\n{a_f2_run.stderr}")
            log(f"Stdout:\n{a_f2_run.stdout}")
            return 1, {"overall_status": "FAIL", "steps": steps_record}

        a_f2_data = json.loads(a_f2_run.stdout)
        as_expected = a_f2_data.get("asExpected", 0)
        review = a_f2_data.get("review", 0)
        unexpected = a_f2_data.get("unexpected", 0)
        status = a_f2_data.get("status")

        if as_expected != 6 or review != 0 or unexpected != 0 or status != "completed":
            log(
                f"FAIL: Attack result mismatch: got asExpected={as_expected}, "
                f"review={review}, unexpected={unexpected}, status={status}"
            )
            return 1, {"overall_status": "FAIL", "steps": steps_record}

        log(
            f"PASS: Installed trustc attack F2 verified exit 0 with 6 expected, "
            f"0 review, 0 unexpected ({a_f2_dur}s)"
        )
        steps_record.append({
            "name": "f2_attack_smoke",
            "command": ["trustc", "attack", "F2.trust", "--format=json"],
            "exit_code": a_f2_run.returncode,
            "duration_seconds": a_f2_dur,
            "asExpected": as_expected,
            "review": review,
            "unexpected": unexpected,
            "status": "PASS",
        })

    # For Stage >= 6, also test `trustc serve --help`
    if stage >= 6:
        log("\n--- Step 6e: Testing installed `trustc serve --help` entrypoint ---")
        t0 = time.time()
        s_help_run = _run_trustc(["serve", "--help"])
        s_help_dur = round(time.time() - t0, 3)
        log(f"Serve help exit code: {s_help_run.returncode} (expected 0)")
        if s_help_run.returncode != 0:
            log(f"FAIL: trustc serve --help expected 0, got {s_help_run.returncode}")
            return 1, {"overall_status": "FAIL", "steps": steps_record}
        if "usage: trustc serve" not in s_help_run.stdout:
            log(f"FAIL: unexpected serve help output: {s_help_run.stdout}")
            return 1, {"overall_status": "FAIL", "steps": steps_record}
        steps_record.append({
            "name": "serve_help_smoke",
            "command": ["trustc", "serve", "--help"],
            "exit_code": s_help_run.returncode,
            "duration_seconds": s_help_dur,
            "status": "PASS",
        })
        log("PASS: Installed trustc serve --help entrypoint verified")

        log("\n--- Step 6f: Testing installed `trustc serve` outside repository ---")
        t0 = time.time()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            srv_port = int(s.getsockname()[1])

        temp_srv_ws = temp_run_dir / "srv_workspace"
        temp_srv_ws.mkdir(parents=True, exist_ok=True)

        serve_args = [
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(srv_port),
            "--workspace",
            str(temp_srv_ws),
        ]

        srv_proc: Optional[subprocess.Popen] = None
        if venv_trustc.exists():
            try:
                srv_proc = subprocess.Popen(
                    [str(venv_trustc)] + serve_args,
                    cwd=str(temp_run_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=clean_env,
                )
            except OSError as e:
                if getattr(e, "winerror", None) == 4551 or "Application Control" in str(e):
                    srv_proc = None
                else:
                    raise

        if srv_proc is None:
            srv_proc = subprocess.Popen(
                [str(venv_python), "-m", "trustc.cli"] + serve_args,
                cwd=str(temp_run_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=clean_env,
            )

        base_url = f"http://127.0.0.1:{srv_port}"
        try:
            # 1. Wait for server to be ready and poll /api/meta
            meta_ready = False
            meta_data: Dict[str, Any] = {}
            wait_t0 = time.time()
            while time.time() - wait_t0 < 15.0:
                if srv_proc.poll() is not None:
                    out, err = srv_proc.communicate()
                    log(f"FAIL: Server process terminated prematurely. stdout: {out}, stderr: {err}")
                    return 1, {"overall_status": "FAIL", "steps": steps_record}
                try:
                    req = urllib.request.Request(f"{base_url}/api/meta")
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        if resp.status == 200:
                            meta_data = json.loads(resp.read().decode("utf-8"))
                            meta_ready = True
                            break
                except Exception:
                    time.sleep(0.2)

            if not meta_ready:
                log(f"FAIL: Server did not respond on {base_url}/api/meta within 15 seconds")
                return 1, {"overall_status": "FAIL", "steps": steps_record}

            if not meta_data.get("sessionId"):
                log(f"FAIL: /api/meta response missing sessionId: {meta_data}")
                return 1, {"overall_status": "FAIL", "steps": steps_record}

            log(f"PASS: /api/meta returned valid sessionId {meta_data.get('sessionId')}")

            if stage >= 8:
                # Verify packaged UI root is served
                ui_req = urllib.request.Request(f"{base_url}/")
                with urllib.request.urlopen(ui_req, timeout=5.0) as resp:
                    if resp.status != 200:
                        log(f"FAIL: GET / expected status 200, got {resp.status}")
                        return 1, {"overall_status": "FAIL", "steps": steps_record}
                    ui_body = resp.read().decode("utf-8")
                    if "<!doctype html" not in ui_body.lower() and "<html" not in ui_body.lower():
                        log(f"FAIL: GET / did not return HTML markup: {ui_body[:200]}")
                        return 1, {"overall_status": "FAIL", "steps": steps_record}
                log("PASS: GET / verified serving packaged UI HTML")

                # Verify packaged examples via /api/examples
                ex_req = urllib.request.Request(f"{base_url}/api/examples")
                with urllib.request.urlopen(ex_req, timeout=5.0) as resp:
                    if resp.status != 200:
                        log(f"FAIL: GET /api/examples expected status 200, got {resp.status}")
                        return 1, {"overall_status": "FAIL", "steps": steps_record}
                    ex_data = json.loads(resp.read().decode("utf-8"))
                    f2_spec_obj = next((e for e in ex_data if e.get("id") == "F2"), None)
                    if not f2_spec_obj or "resource User" not in f2_spec_obj.get("spec", ""):
                        log(f"FAIL: /api/examples did not contain valid F2 example: {ex_data}")
                        return 1, {"overall_status": "FAIL", "steps": steps_record}
                log(f"PASS: GET /api/examples verified serving {len(ex_data)} packaged examples")

            # 2. Test /api/check with F2 spec
            f2_spec_content = (temp_run_dir / "F2.trust").read_text(encoding="utf-8")
            chk_payload = json.dumps({"spec": f2_spec_content, "specVersion": 0}).encode("utf-8")
            chk_req = urllib.request.Request(
                f"{base_url}/api/check",
                data=chk_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(chk_req, timeout=5.0) as resp:
                chk_data = json.loads(resp.read().decode("utf-8"))
                if chk_data.get("exitCode") != 0 or chk_data.get("specErrors") != []:
                    log(f"FAIL: /api/check returned unexpected result: {chk_data}")
                    return 1, {"overall_status": "FAIL", "steps": steps_record}

            log("PASS: /api/check verified cleanly via installed server")

            # 3. Test /api/build with F2 spec and poll /api/runs/{runId}
            bld_payload = json.dumps({
                "spec": f2_spec_content,
                "specVersion": 0,
                "target": "fastapi",
            }).encode("utf-8")
            bld_req = urllib.request.Request(
                f"{base_url}/api/build",
                data=bld_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(bld_req, timeout=5.0) as resp:
                if resp.status != 202:
                    log(f"FAIL: /api/build expected status 202, got {resp.status}")
                    return 1, {"overall_status": "FAIL", "steps": steps_record}
                bld_res = json.loads(resp.read().decode("utf-8"))
                run_id = bld_res.get("runId")

            poll_t0 = time.time()
            build_result: Optional[Dict[str, Any]] = None
            while time.time() - poll_t0 < 20.0:
                run_req = urllib.request.Request(f"{base_url}/api/runs/{run_id}")
                with urllib.request.urlopen(run_req, timeout=5.0) as resp:
                    run_info = json.loads(resp.read().decode("utf-8"))
                    if run_info.get("state") == "terminal":
                        build_result = run_info.get("result")
                        break
                time.sleep(0.3)

            if not build_result or build_result.get("exitCode") != 0:
                log(f"FAIL: /api/build failed or timed out: {build_result}")
                return 1, {"overall_status": "FAIL", "steps": steps_record}

            build_id = build_result.get("buildId")
            if not build_id:
                log(f"FAIL: /api/build result missing buildId: {build_result}")
                return 1, {"overall_status": "FAIL", "steps": steps_record}

            log(f"PASS: /api/build completed with buildId {build_id}")

            # 4. Test /api/builds/{buildId}/out.zip download and verify contents
            zip_req = urllib.request.Request(f"{base_url}/api/builds/{build_id}/out.zip")
            with urllib.request.urlopen(zip_req, timeout=10.0) as resp:
                if resp.status != 200:
                    log(f"FAIL: GET out.zip returned status {resp.status}")
                    return 1, {"overall_status": "FAIL", "steps": steps_record}
                zip_bytes = resp.read()

            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                zip_names = zf.namelist()
                for name in zip_names:
                    if name.startswith("/") or name.startswith("\\") or ".." in name:
                        log(f"FAIL: out.zip contains suspicious path: {name}")
                        return 1, {"overall_status": "FAIL", "steps": steps_record}
                if "trustc-report.json" not in zip_names:
                    log(f"FAIL: out.zip missing trustc-report.json. Names: {zip_names[:10]}")
                    return 1, {"overall_status": "FAIL", "steps": steps_record}

            log(f"PASS: /api/builds/{build_id}/out.zip verified ({len(zip_names)} files)")

            steps_record.append({
                "name": "server_live_smoke",
                "sessionId": meta_data.get("sessionId"),
                "buildId": build_id,
                "duration_seconds": round(time.time() - t0, 3),
                "status": "PASS",
            })
            log("PASS: Installed server verified outside repository (meta, check, build, download)")

        finally:
            if srv_proc is not None and srv_proc.poll() is None:
                srv_proc.terminate()
                try:
                    srv_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    srv_proc.kill()
                    srv_proc.wait(timeout=2)

    # -------------------------------------------------------------------------
    # 7. Cleanup
    # -------------------------------------------------------------------------
    if not keep_env:
        log("\n--- Step 7: Cleaning up test directories ---")
        try:
            shutil.rmtree(temp_venv_dir, ignore_errors=True)
            shutil.rmtree(temp_run_dir, ignore_errors=True)
            log("PASS: Cleaned up temporary virtualenv and test run directory")
        except Exception as e:
            log(f"WARNING: Cleanup encountered error: {e}")
    else:
        log(f"\nPreserving test environment at: {temp_venv_dir}")

    end_time = _timestamp()
    log(f"\n[{end_time}] Stage {stage} Wheel Installation & Smoke Test PASSED completely!")

    summary = {
        "overall_status": "PASS",
        "start_time": start_time,
        "end_time": end_time,
        "steps": steps_record,
    }

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("\n".join(logs) + "\n", encoding="utf-8")

    return 0, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="TrustC Wheel Smoke Test")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root directory",
    )
    parser.add_argument(
        "--stage",
        type=int,
        default=5,
        help="Pipeline stage number (default: 5)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Path to write log file (default: review-logs/stage-<stage>/wheel-smoke.log)",
    )
    parser.add_argument(
        "--keep-env",
        action="store_true",
        help="Do not delete temporary test virtualenv",
    )
    args = parser.parse_args()

    log_path = args.log_file
    if log_path is None:
        log_path = (
            args.repo_root
            / "review-logs"
            / f"stage-{args.stage}"
            / "wheel-smoke.log"
        )

    rc, _ = run_wheel_smoke_test(
        repo_root=args.repo_root,
        log_file=log_path,
        keep_env=args.keep_env,
        stage=args.stage,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
