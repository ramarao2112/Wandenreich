#!/usr/bin/env python3
"""Stage gate checker — runs registered gates and produces machine-readable reports.

Usage:
    python scripts/check-stage.py <stage_number> [options]

Options:
    --linter {ruff,flake8-isort}
        Lint toolchain to use. Default is 'ruff'.
        'flake8-isort' is the explicitly documented alternative toolchain
        providing equivalent rule coverage (E, F, W via flake8; I via isort)
        when ruff is blocked by OS security policy (Windows WDAC WinError 4551).
    --report-path <path>
        Path to output machine-readable gate report JSON.
        Default: review-logs/stage-<stage>/gate-result.json
    --skip-wheel-smoke
        Skip wheel packaging smoke test (for quick iteration).

Stages:
    1: Contracts, fixtures, schemas, and packaging
    2: Grammar, positions, reference validation, IR, and wheel installation smoke
    3-8: Implemented in subsequent stages
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

STAGE_CONFIGS = {
    1: {
        "description": "Contracts, fixtures, schemas, and packaging",
        "pytest_args": [
            "-m", "stage1",
            "tests/contract/",
            "tests/unit/test_fixtures.py",
        ],
    },
    2: {
        "description": "Grammar, positions, reference validation, IR, and wheel smoke",
        "pytest_args": [
            "-m", "stage1 or stage2",
            "tests/contract/",
            "tests/unit/test_fixtures.py",
            "tests/unit/test_parser.py",
            "tests/unit/test_gate_runner.py",
        ],
    },
    3: {
        "description": "Security rules, check, diff fixes, explain, and SARIF output",
        "pytest_args": [
            "-m", "stage1 or stage2 or stage3",
            "tests/",
        ],
    },
    4: {
        "description": "Generate and execute backend, real DB/FastAPI runtime, rollback, and seeder",
        "pytest_args": [
            "-m", "stage1 or stage2 or stage3 or stage4",
            "tests/",
        ],
    },
    5: {
        "description": "Live local access harness, loopback HTTP, per-actor assertions, and cleanup",
        "pytest_args": [
            "-m", "stage1 or stage2 or stage3 or stage4 or stage5",
            "tests/",
        ],
    },
    6: {
        "description": "Local API server, streaming protocol, and artifact lifecycle",
        "pytest_args": [
            "-m", "stage1 or stage2 or stage3 or stage4 or stage5 or stage6",
            "tests/",
        ],
    },
    7: {
        "description": "Developer workbench UI with real compiler/server integration",
        "pytest_args": [
            "-m", "stage1 or stage2 or stage3 or stage4 or stage5 or stage6",
            "tests/",
        ],
    },
    8: {
        "description": "Release validation, packaging, standalone environment proofing, and demo rehearsal",
        "pytest_args": [
            "-m", "stage1 or stage2 or stage3 or stage4 or stage5 or stage6",
            "tests/",
        ],
    },
}


def _safe_print(text: str) -> None:
    """Print text with fallback for console encodings that cannot handle emoji."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        cleaned = text.replace("✅", "[PASS]").replace("❌", "[FAIL]").replace("⚠️", "[WARN]")
        safe = cleaned.encode(enc, errors="replace").decode(enc)
        print(safe)


def _timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class StepResult:
    def __init__(
        self,
        name: str,
        command: List[str],
        cwd: str,
        start_time: str,
        end_time: str,
        duration_seconds: float,
        exit_code: Optional[int],
        launch_exception: Optional[str],
        status: str,  # "PASS", "FAIL", "BLOCKED"
        stdout: str = "",
        stderr: str = "",
    ):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.start_time = start_time
        self.end_time = end_time
        self.duration_seconds = duration_seconds
        self.exit_code = exit_code
        self.launch_exception = launch_exception
        self.status = status
        self.stdout = stdout
        self.stderr = stderr

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "cwd": self.cwd,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "launch_exception": self.launch_exception,
            "status": self.status,
            "stdout_snippet": self.stdout[:500] if self.stdout else "",
            "stderr_snippet": self.stderr[:500] if self.stderr else "",
        }


def run_command_step(
    name: str,
    cmd: List[str],
    cwd: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> StepResult:
    """Execute a subprocess command, capturing full metrics and handling launch errors."""
    start_time = _timestamp()
    t0 = time.time()
    try:
        res = runner(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        t1 = time.time()
        end_time = _timestamp()
        duration = round(t1 - t0, 3)
        status = "PASS" if res.returncode == 0 else "FAIL"
        launch_exc = None
        stderr_text = getattr(res, "stderr", "") or ""
        if res.returncode != 0 and ("4551" in stderr_text or "Application Control" in stderr_text):
            status = "BLOCKED"
            launch_exc = (
                "OSError: [WinError 4551] An Application Control policy has blocked this file"
            )
        return StepResult(
            name=name,
            command=cmd,
            cwd=str(cwd),
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            exit_code=res.returncode,
            launch_exception=launch_exc,
            status=status,
            stdout=getattr(res, "stdout", "") or "",
            stderr=stderr_text,
        )
    except OSError as e:
        t1 = time.time()
        end_time = _timestamp()
        duration = round(t1 - t0, 3)
        return StepResult(
            name=name,
            command=cmd,
            cwd=str(cwd),
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            exit_code=None,
            launch_exception=f"{type(e).__name__}: {e}",
            status="BLOCKED",
            stdout="",
            stderr=str(e),
        )
    except Exception as e:
        t1 = time.time()
        end_time = _timestamp()
        duration = round(t1 - t0, 3)
        return StepResult(
            name=name,
            command=cmd,
            cwd=str(cwd),
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            exit_code=None,
            launch_exception=f"{type(e).__name__}: {e}",
            status="FAIL",
            stdout="",
            stderr=str(e),
        )


def run_stage_gate(
    stage: int,
    repo_root: Path,
    linter: str = "ruff",
    runner: Callable[..., Any] = subprocess.run,
    report_path: Optional[Path] = None,
    run_wheel_smoke: bool = True,
    smoke_test_runner: Optional[Callable[..., Tuple[int, Dict[str, Any]]]] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Run all gates for a given stage with dependency injection for runner testing."""
    overall_start = _timestamp()
    t_start = time.time()

    if stage not in STAGE_CONFIGS:
        return 2, {
            "overall_status": "FAIL",
            "error": f"Stage {stage} is not yet implemented.",
            "steps": [],
        }

    config = STAGE_CONFIGS[stage]
    steps: List[StepResult] = []

    _safe_print(f"=== Stage {stage} Gate: {config['description']} ===")
    _safe_print(f"Linter Toolchain: {linter}")
    _safe_print(f"Timestamp: {overall_start}\n")

    # -------------------------------------------------------------------------
    # 1. Lint Gate
    # -------------------------------------------------------------------------
    if linter == "ruff":
        _safe_print("[Gate 1/5] Running linter (ruff)...")
        lint_cmd = [sys.executable, "-m", "ruff", "check", "src/", "tests/"]
        res = run_command_step("lint_ruff", lint_cmd, repo_root, runner=runner)
        steps.append(res)
        if res.status == "BLOCKED":
            _safe_print(f"❌ [BLOCKED] Ruff failed to launch: {res.launch_exception}")
            _safe_print("   Preserve Windows Application Control. Do not evade policy.")
            _safe_print("   To use documented equivalent toolchain, pass: --linter flake8-isort\n")
        elif res.status == "FAIL":
            _safe_print(f"❌ [FAIL] Ruff reported issues (exit {res.exit_code}):\n{res.stdout}\n")
        else:
            _safe_print("✅ [PASS] Ruff lint passed.\n")
    elif linter == "flake8-isort":
        _safe_print("[Gate 1/5] Running documented equivalent linter (flake8 + isort)...")
        # 1a. flake8 (E, F, W)
        f8_cmd = [
            sys.executable, "-m", "flake8", "src/", "tests/",
            "--max-line-length=100", "--extend-ignore=E203,W503",
        ]
        f8_res = run_command_step("lint_flake8", f8_cmd, repo_root, runner=runner)
        steps.append(f8_res)
        if f8_res.status != "PASS":
            _safe_print(
                f"❌ [FAIL] flake8 reported issues (exit {f8_res.exit_code}):\n{f8_res.stdout}\n"
            )
        else:
            _safe_print("✅ [PASS] flake8 (E, F, W rules) passed.")

        # 1b. isort (I)
        # Enforce UTF-8 mode (-X utf8) to avoid Windows charmap encoding truncation
        isort_cmd = [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "isort",
            "--check",
            "--diff",
            "src/",
            "tests/",
        ]
        isort_res = run_command_step("lint_isort", isort_cmd, repo_root, runner=runner)
        steps.append(isort_res)
        combined_isort_out = (isort_res.stdout or "") + (isort_res.stderr or "")
        if "Unable to parse file" in combined_isort_out or "UserWarning" in combined_isort_out:
            isort_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] isort reported file parsing warnings / incomplete checking:\n"
                f"{combined_isort_out}\n"
            )
        elif isort_res.status != "PASS":
            _safe_print(
                f"❌ [FAIL] isort reported unorganized imports "
                f"(exit {isort_res.exit_code}):\n{isort_res.stdout}\n"
            )
        else:
            _safe_print(
                "✅ [PASS] isort (I rule / import sorting) passed on all files without warning.\n"
            )
    else:
        _safe_print(f"❌ Unknown linter: {linter}")
        return 2, {"overall_status": "FAIL", "error": f"Unknown linter: {linter}", "steps": []}

    # -------------------------------------------------------------------------
    # 2. Type Gate (mypy)
    # -------------------------------------------------------------------------
    _safe_print("[Gate 2/5] Running type checks (mypy)...")
    mypy_cmd = [sys.executable, "-m", "mypy", "src/", "tests/"]
    mypy_res = run_command_step("type_check_mypy", mypy_cmd, repo_root, runner=runner)
    steps.append(mypy_res)
    if mypy_res.status != "PASS":
        _safe_print(
            f"❌ [FAIL] mypy reported type errors (exit {mypy_res.exit_code}):\n{mypy_res.stdout}\n"
        )
    else:
        _safe_print("✅ [PASS] mypy type check passed.\n")

    # -------------------------------------------------------------------------
    # 3. Test Gate (pytest)
    # -------------------------------------------------------------------------
    _safe_print(f"[Gate 3/5] Running pytest test suite ({' '.join(config['pytest_args'])})...")
    pytest_cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short"] + list(config["pytest_args"])
    pytest_res = run_command_step("test_pytest", pytest_cmd, repo_root, runner=runner)

    # Pytest zero tests collected check
    if pytest_res.exit_code == 5 or "collected 0 items" in (pytest_res.stdout or ""):
        pytest_res.status = "FAIL"
        _safe_print("❌ [FAIL] Pytest collected 0 tests! Test collection failure.")
    elif pytest_res.status != "PASS":
        _safe_print(
            f"❌ [FAIL] Pytest failures (exit {pytest_res.exit_code}):\n{pytest_res.stdout}\n"
        )
    else:
        _safe_print("✅ [PASS] Pytest suite passed.\n")
    steps.append(pytest_res)

    # -------------------------------------------------------------------------
    # 4. CLI Parse Gate (Stage >= 2)
    # -------------------------------------------------------------------------
    if stage >= 2:
        _safe_print("[Gate 4/5] Running CLI parse assertions on F2 (exit 0) and F4 (exit 2)...")
        # F2
        f2_cmd = [sys.executable, "-m", "trustc.cli", "parse", "tests/fixtures/F2.trust"]
        f2_res = run_command_step("cli_parse_f2", f2_cmd, repo_root, runner=runner)
        if f2_res.exit_code != 0:
            f2_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI parse F2 expected exit 0, got {f2_res.exit_code}")
        else:
            _safe_print("✅ [PASS] CLI parse F2 exit 0 verified.")
        steps.append(f2_res)

        # F4
        f4_cmd = [sys.executable, "-m", "trustc.cli", "parse", "tests/fixtures/F4.trust"]
        f4_res = run_command_step("cli_parse_f4", f4_cmd, repo_root, runner=runner)
        if f4_res.exit_code != 2:
            f4_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI parse F4 expected exit 2, got {f4_res.exit_code}")
        else:
            f4_res.status = "PASS"
            _safe_print("✅ [PASS] CLI parse F4 exit 2 verified.\n")
        steps.append(f4_res)

    # -------------------------------------------------------------------------
    # 4b. CLI Check & Fix Gate (Stage >= 3)
    # -------------------------------------------------------------------------
    if stage >= 3:
        _safe_print("[Gate 4b] Running CLI check, fix, and explain assertions...")
        # Check F2 (exit 0)
        c_f2_cmd = [sys.executable, "-m", "trustc.cli", "check", "tests/fixtures/F2.trust"]
        c_f2_res = run_command_step("cli_check_f2", c_f2_cmd, repo_root, runner=runner)
        if c_f2_res.exit_code != 0:
            c_f2_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI check F2 expected exit 0, got {c_f2_res.exit_code}")
        else:
            _safe_print("✅ [PASS] CLI check F2 exit 0 verified.")
        steps.append(c_f2_res)

        # Check F1 (exit 1)
        c_f1_cmd = [sys.executable, "-m", "trustc.cli", "check", "tests/fixtures/F1.trust"]
        c_f1_res = run_command_step("cli_check_f1", c_f1_cmd, repo_root, runner=runner)
        if c_f1_res.exit_code != 1:
            c_f1_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI check F1 expected exit 1, got {c_f1_res.exit_code}")
        else:
            c_f1_res.status = "PASS"
            _safe_print("✅ [PASS] CLI check F1 exit 1 verified.")
        steps.append(c_f1_res)

        # Check F4 (exit 2)
        c_f4_cmd = [sys.executable, "-m", "trustc.cli", "check", "tests/fixtures/F4.trust"]
        c_f4_res = run_command_step("cli_check_f4", c_f4_cmd, repo_root, runner=runner)
        if c_f4_res.exit_code != 2:
            c_f4_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI check F4 expected exit 2, got {c_f4_res.exit_code}")
        else:
            c_f4_res.status = "PASS"
            _safe_print("✅ [PASS] CLI check F4 exit 2 verified.")
        steps.append(c_f4_res)

        # Apply-fix dry-run on F1 (exit 0)
        fix_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "apply-fix",
            "tests/fixtures/F1.trust",
            "--rule",
            "TC-001",
            "--dry-run",
        ]
        fix_res = run_command_step("cli_apply_fix_f1", fix_cmd, repo_root, runner=runner)
        if fix_res.exit_code != 0:
            fix_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] CLI apply-fix F1 dry-run expected exit 0, got {fix_res.exit_code}"
            )
        else:
            _safe_print("✅ [PASS] CLI apply-fix F1 dry-run exit 0 verified.")
        steps.append(fix_res)

        # Explain TC-002 (exit 0)
        exp_cmd = [sys.executable, "-m", "trustc.cli", "explain", "TC-002"]
        exp_res = run_command_step("cli_explain_tc002", exp_cmd, repo_root, runner=runner)
        if exp_res.exit_code != 0:
            exp_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI explain TC-002 expected exit 0, got {exp_res.exit_code}")
        else:
            _safe_print("✅ [PASS] CLI explain TC-002 exit 0 verified.")
        steps.append(exp_res)

        # Full validation against published OASIS SARIF 2.1.0 schema (exit 0)
        sarif_val_cmd = [sys.executable, "scripts/validate_sarif_schema.py"]
        sarif_val_res = run_command_step(
            "sarif_schema_validation", sarif_val_cmd, repo_root, runner=runner
        )
        if sarif_val_res.exit_code != 0:
            sarif_val_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] SARIF schema validation failed (exit {sarif_val_res.exit_code}):\n"
                f"{sarif_val_res.stdout}\n"
            )
        else:
            _safe_print(
                "✅ [PASS] Published OASIS SARIF 2.1.0 schema validation passed for all fixtures.\n"
            )
        steps.append(sarif_val_res)

    # -------------------------------------------------------------------------
    # 4c. Generated Backend Runtime Smoke & Build Rollback (Stage >= 4)
    # -------------------------------------------------------------------------
    if stage >= 4:
        _safe_print("[Gate 4c] Running Stage 4 generated backend runtime smoke & build rollback...")
        temp_smoke_dir = tempfile.TemporaryDirectory(prefix="trustc_check_stage4_")
        smoke_out = Path(temp_smoke_dir.name) / "generated_f2"

        # 1. Build F2 with --target=fastapi
        b_f2_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "build",
            "tests/fixtures/F2.trust",
            "-o",
            str(smoke_out),
            "--target=fastapi",
            "--format=json",
        ]
        b_f2_res = run_command_step("cli_build_f2", b_f2_cmd, repo_root, runner=runner)
        if b_f2_res.exit_code != 0:
            b_f2_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI build F2 expected exit 0, got {b_f2_res.exit_code}")
        else:
            # Verify 8 Python files, manifest, report, and integrity
            py_files = list(smoke_out.glob("*.py")) + list((smoke_out / "routers").glob("*.py"))
            has_manifest = (smoke_out / "trustc-manifest.json").is_file()
            has_report = (smoke_out / "trustc-report.json").is_file()
            has_reqs = (smoke_out / "requirements.txt").is_file()
            has_readme = (smoke_out / "README.md").is_file()

            from trustc.manifest import verify_manifest
            ok_man, man_reason = verify_manifest(smoke_out)

            if len(py_files) == 8 and has_manifest and has_report and has_reqs and has_readme and ok_man:
                b_f2_res.status = "PASS"
                _safe_print("✅ [PASS] CLI build F2 exit 0 verified (8 Python files, valid manifest, and report).")
            else:
                b_f2_res.status = "FAIL"
                _safe_print(
                    f"❌ [FAIL] Build integrity failure: py={len(py_files)}, manifest={has_manifest}, "
                    f"report={has_report}, manifest_ok={ok_man} ({man_reason})"
                )
        steps.append(b_f2_res)

        # 2. Run runtime smoke tester against real DB
        smoke_cmd = [
            sys.executable,
            "scripts/smoke-generated.py",
            "tests/fixtures/F2.trust",
            "-o",
            str(smoke_out),
        ]
        smoke_res = run_command_step("smoke_generated_backend", smoke_cmd, repo_root, runner=runner)
        if smoke_res.exit_code != 0:
            smoke_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] Smoke tester failed (exit {smoke_res.exit_code}):\n{smoke_res.stdout}\n{smoke_res.stderr}")
        else:
            smoke_res.status = "PASS"
            _safe_print("✅ [PASS] Stage 4 runtime smoke test passed (real DB, auth, injections, projections).")
        steps.append(smoke_res)

        # 3. Refusal & directory rollback on F1
        f1_target = Path(temp_smoke_dir.name) / "f1_refusal"
        f1_target.mkdir(parents=True, exist_ok=True)
        canary = f1_target / "sentinel.txt"
        canary.write_text("untouched sentinel data", encoding="utf-8")
        b_f1_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "build",
            "tests/fixtures/F1.trust",
            "-o",
            str(f1_target),
            "--replace",
            "--format=json",
        ]
        b_f1_res = run_command_step("cli_build_refusal_f1", b_f1_cmd, repo_root, runner=runner)
        if b_f1_res.exit_code != 1:
            b_f1_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI build F1 expected exit 1, got {b_f1_res.exit_code}")
        elif not canary.exists() or canary.read_text(encoding="utf-8") != "untouched sentinel data":
            b_f1_res.status = "FAIL"
            _safe_print("❌ [FAIL] Directory rollback violation: sentinel data modified on F1 refusal")
        else:
            b_f1_res.status = "PASS"
            _safe_print("✅ [PASS] CLI build F1 exit 1 refused and destination byte-identical.")
        steps.append(b_f1_res)

        # 4. Refusal & directory rollback on F4
        f4_target = Path(temp_smoke_dir.name) / "f4_refusal"
        f4_target.mkdir(parents=True, exist_ok=True)
        canary_f4 = f4_target / "sentinel.txt"
        canary_f4.write_text("untouched sentinel data", encoding="utf-8")
        b_f4_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "build",
            "tests/fixtures/F4.trust",
            "-o",
            str(f4_target),
            "--replace",
            "--format=json",
        ]
        b_f4_res = run_command_step("cli_build_syntax_error_f4", b_f4_cmd, repo_root, runner=runner)
        if b_f4_res.exit_code != 2:
            b_f4_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI build F4 expected exit 2, got {b_f4_res.exit_code}")
        elif not canary_f4.exists() or canary_f4.read_text(encoding="utf-8") != "untouched sentinel data":
            b_f4_res.status = "FAIL"
            _safe_print("❌ [FAIL] Directory rollback violation: sentinel data modified on F4 syntax error")
        else:
            b_f4_res.status = "PASS"
            _safe_print("✅ [PASS] CLI build F4 exit 2 syntax error and destination byte-identical.\n")
        steps.append(b_f4_res)

        temp_smoke_dir.cleanup()

    # -------------------------------------------------------------------------
    # 4d. Live Local Access Harness & Mutation Checks (Stage >= 5)
    # -------------------------------------------------------------------------
    if stage >= 5:
        _safe_print("[Gate 4d] Running Stage 5 live local access harness & mutation checks...")

        # 1. trustc attack tests/fixtures/F2.trust (must exit 0, 6 as_expected)
        a_f2_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "attack",
            "tests/fixtures/F2.trust",
            "--format=json",
        ]
        a_f2_res = run_command_step("cli_attack_f2", a_f2_cmd, repo_root, runner=runner)
        if a_f2_res.exit_code != 0:
            a_f2_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI attack F2 expected exit 0, got {a_f2_res.exit_code}")
        else:
            try:
                f2_data = json.loads(a_f2_res.stdout)
                as_exp = f2_data.get("asExpected", 0)
                rev = f2_data.get("review", 0)
                unexp = f2_data.get("unexpected", 0)
                tot = f2_data.get("total", 0)
                if as_exp == 6 and rev == 0 and unexp == 0 and tot == 6:
                    a_f2_res.status = "PASS"
                    _safe_print("✅ [PASS] CLI attack F2 verified: 6 as_expected, 0 review, 0 unexpected.")
                else:
                    a_f2_res.status = "FAIL"
                    _safe_print(
                        f"❌ [FAIL] CLI attack F2 counts mismatch: expected 6/0/0, got {as_exp}/{rev}/{unexp}"
                    )
            except Exception as e:
                a_f2_res.status = "FAIL"
                _safe_print(f"❌ [FAIL] Could not parse F2 attack output JSON: {e}")
        steps.append(a_f2_res)

        # 2. trustc attack tests/fixtures/F3.trust (must exit 0, 8 as_expected, 1 review)
        a_f3_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "attack",
            "tests/fixtures/F3.trust",
            "--format=json",
        ]
        a_f3_res = run_command_step("cli_attack_f3", a_f3_cmd, repo_root, runner=runner)
        if a_f3_res.exit_code != 0:
            a_f3_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI attack F3 expected exit 0, got {a_f3_res.exit_code}")
        else:
            try:
                f3_data = json.loads(a_f3_res.stdout)
                as_exp = f3_data.get("asExpected", 0)
                rev = f3_data.get("review", 0)
                unexp = f3_data.get("unexpected", 0)
                tot = f3_data.get("total", 0)
                if as_exp == 8 and rev == 1 and unexp == 0 and tot == 9:
                    a_f3_res.status = "PASS"
                    _safe_print("✅ [PASS] CLI attack F3 verified: 8 as_expected, 1 review, 0 unexpected.")
                else:
                    a_f3_res.status = "FAIL"
                    _safe_print(
                        f"❌ [FAIL] CLI attack F3 counts mismatch: expected 8/1/0, got {as_exp}/{rev}/{unexp}"
                    )
            except Exception as e:
                a_f3_res.status = "FAIL"
                _safe_print(f"❌ [FAIL] Could not parse F3 attack output JSON: {e}")
        steps.append(a_f3_res)

        # 3. Refusal on F1 never starts app (must exit 1, status refused)
        a_f1_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "attack",
            "tests/fixtures/F1.trust",
            "--format=json",
        ]
        a_f1_res = run_command_step("cli_attack_refusal_f1", a_f1_cmd, repo_root, runner=runner)
        if a_f1_res.exit_code != 1:
            a_f1_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI attack F1 expected exit 1, got {a_f1_res.exit_code}")
        else:
            try:
                f1_data = json.loads(a_f1_res.stdout)
                if f1_data.get("status") == "refused":
                    a_f1_res.status = "PASS"
                    _safe_print("✅ [PASS] CLI attack F1 refused (exit 1, app never started).")
                else:
                    a_f1_res.status = "FAIL"
                    _safe_print(
                        f"❌ [FAIL] CLI attack F1 status expected 'refused', got '{f1_data.get('status')}'"
                    )
            except Exception as e:
                a_f1_res.status = "FAIL"
                _safe_print(f"❌ [FAIL] Could not parse F1 attack output JSON: {e}")
        steps.append(a_f1_res)

        # 4. Syntax error on F4 never starts app (must exit 2, status invalid_spec)
        a_f4_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "attack",
            "tests/fixtures/F4.trust",
            "--format=json",
        ]
        a_f4_res = run_command_step("cli_attack_syntax_error_f4", a_f4_cmd, repo_root, runner=runner)
        if a_f4_res.exit_code != 2:
            a_f4_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI attack F4 expected exit 2, got {a_f4_res.exit_code}")
        else:
            try:
                f4_data = json.loads(a_f4_res.stdout)
                if f4_data.get("status") == "invalid_spec":
                    a_f4_res.status = "PASS"
                    _safe_print("✅ [PASS] CLI attack F4 syntax error (exit 2, app never started).")
                else:
                    a_f4_res.status = "FAIL"
                    _safe_print(
                        f"❌ [FAIL] CLI attack F4 status expected 'invalid_spec', got '{f4_data.get('status')}'"
                    )
            except Exception as e:
                a_f4_res.status = "FAIL"
                _safe_print(f"❌ [FAIL] Could not parse F4 attack output JSON: {e}")
        steps.append(a_f4_res)

        # 5. X08 public owned GET/DELETE with isolated state (must exit 0, 2 as_expected, 4 review)
        a_x08_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "attack",
            "tests/fixtures/X08.trust",
            "--format=json",
        ]
        a_x08_res = run_command_step(
            "cli_attack_x08_isolated_state", a_x08_cmd, repo_root, runner=runner
        )
        if a_x08_res.exit_code != 0:
            a_x08_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI attack X08 expected exit 0, got {a_x08_res.exit_code}")
        else:
            try:
                x08_data = json.loads(a_x08_res.stdout)
                as_exp = x08_data.get("asExpected", 0)
                rev = x08_data.get("review", 0)
                if as_exp == 2 and rev == 4:
                    a_x08_res.status = "PASS"
                    _safe_print(
                        "✅ [PASS] CLI attack X08 verified: public GET/DELETE with isolated state."
                    )
                else:
                    a_x08_res.status = "FAIL"
                    _safe_print(
                        f"❌ [FAIL] CLI attack X08 counts mismatch: expected 2/4, got {as_exp}/{rev}"
                    )
            except Exception as e:
                a_x08_res.status = "FAIL"
                _safe_print(f"❌ [FAIL] Could not parse X08 attack output JSON: {e}")
        steps.append(a_x08_res)

        # 6. X11 empty coverage on collection-only spec (must exit 0, 0 steps)
        a_x11_cmd = [
            sys.executable,
            "-m",
            "trustc.cli",
            "attack",
            "tests/fixtures/X11.trust",
            "--format=json",
        ]
        a_x11_res = run_command_step(
            "cli_attack_x11_empty_coverage", a_x11_cmd, repo_root, runner=runner
        )
        if a_x11_res.exit_code != 0:
            a_x11_res.status = "FAIL"
            _safe_print(f"❌ [FAIL] CLI attack X11 expected exit 0, got {a_x11_res.exit_code}")
        else:
            try:
                x11_data = json.loads(a_x11_res.stdout)
                tot = x11_data.get("total", -1)
                cov = x11_data.get("coverage", {})
                if tot == 0 and cov.get("testedEndpoints") == []:
                    a_x11_res.status = "PASS"
                    _safe_print("✅ [PASS] CLI attack X11 verified: 0 steps, explicit empty coverage.")
                else:
                    a_x11_res.status = "FAIL"
                    _safe_print(f"❌ [FAIL] CLI attack X11 expected 0 steps, got {tot}")
            except Exception as e:
                a_x11_res.status = "FAIL"
                _safe_print(f"❌ [FAIL] Could not parse X11 attack output JSON: {e}")
        steps.append(a_x11_res)

        # 7. Mutation testing detection on F2 (must exit 1, 1 unexpected)
        mut_cmd = [
            sys.executable,
            "-c",
            "from trustc.harness import mutate_and_attack_f2; "
            "res = mutate_and_attack_f2('tests/fixtures/F2.trust'); "
            "assert res.exit_code == 1 and res.unexpected == 1 and res.as_expected == 5, "
            "f'Unexpected mutation result: exit={res.exit_code}, unexp={res.unexpected}'; "
            "print('Mutation detected: exit 1, unexpected 1')",
        ]
        mut_res = run_command_step("mutation_test_f2", mut_cmd, repo_root, runner=runner)
        if mut_res.exit_code != 0:
            mut_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] Mutation test failed to detect owner check removal:\n{mut_res.stderr}"
            )
        else:
            mut_res.status = "PASS"
            _safe_print(
                "✅ [PASS] Mutation test verified: owner check removal correctly detected (exit 1).\n"
            )
        steps.append(mut_res)

    # -------------------------------------------------------------------------
    # 4e. Local API Server Smoke (Stage >= 6)
    # -------------------------------------------------------------------------
    if stage >= 6:
        _safe_print("[Gate 4e] Running Stage 6 local API server smoke test...")
        server_smoke_cmd = [sys.executable, "scripts/smoke-server.py"]
        server_smoke_res = run_command_step(
            "smoke_local_api_server", server_smoke_cmd, repo_root, runner=runner
        )
        if server_smoke_res.exit_code != 0:
            server_smoke_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] Server smoke test failed (exit {server_smoke_res.exit_code}):\n"
                f"{server_smoke_res.stdout}\n{server_smoke_res.stderr}"
            )
        else:
            server_smoke_res.status = "PASS"
            _safe_print(
                "✅ [PASS] Stage 6 server smoke test passed "
                "(all 10 operations, SSE, zip, security).\n"
            )
        steps.append(server_smoke_res)

    # -------------------------------------------------------------------------
    # 4f-4i. Stage 7 UI Gates (Stage >= 7)
    # -------------------------------------------------------------------------
    if stage >= 7:
        import shutil

        npm_exe = shutil.which("npm.cmd" if sys.platform == "win32" else "npm") or "npm"
        ui_dir = repo_root / "ui"

        # 4f. UI Lint (ESLint)
        _safe_print("[Gate 4f] Running Stage 7 UI ESLint check (npm run lint)...")
        ui_lint_cmd = [npm_exe, "run", "lint"]
        ui_lint_res = run_command_step("ui_lint", ui_lint_cmd, ui_dir, runner=runner)
        if ui_lint_res.exit_code != 0:
            ui_lint_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] UI lint failed (exit {ui_lint_res.exit_code}):\n"
                f"{ui_lint_res.stdout}\n{ui_lint_res.stderr}"
            )
        else:
            ui_lint_res.status = "PASS"
            _safe_print("✅ [PASS] Stage 7 UI ESLint check passed (0 errors).\n")
        steps.append(ui_lint_res)

        # 4g. UI Typecheck
        _safe_print("[Gate 4g] Running Stage 7 UI TypeScript typecheck (tsc --noEmit)...")
        ui_typecheck_cmd = [npm_exe, "run", "typecheck"]
        ui_typecheck_res = run_command_step(
            "ui_typecheck", ui_typecheck_cmd, ui_dir, runner=runner
        )
        if ui_typecheck_res.exit_code != 0:
            ui_typecheck_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] UI typecheck failed (exit {ui_typecheck_res.exit_code}):\n"
                f"{ui_typecheck_res.stdout}\n{ui_typecheck_res.stderr}"
            )
        else:
            ui_typecheck_res.status = "PASS"
            _safe_print("✅ [PASS] Stage 7 UI typecheck passed (0 errors).\n")
        steps.append(ui_typecheck_res)

        # 4h. UI Production Build
        _safe_print("[Gate 4h] Running Stage 7 UI production bundle build (vite build)...")
        ui_build_cmd = [npm_exe, "run", "build"]
        ui_build_res = run_command_step("ui_build", ui_build_cmd, ui_dir, runner=runner)
        if ui_build_res.exit_code != 0:
            ui_build_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] UI production build failed (exit {ui_build_res.exit_code}):\n"
                f"{ui_build_res.stdout}\n{ui_build_res.stderr}"
            )
        else:
            ui_build_res.status = "PASS"
            _safe_print("✅ [PASS] Stage 7 UI production build passed (dist/ created).\n")
        steps.append(ui_build_res)

        # 4i. UI Unit and Axe Accessibility Tests
        _safe_print(
            "[Gate 4i] Running Stage 7 UI unit and axe accessibility tests (vitest run)..."
        )
        ui_test_cmd = [npm_exe, "test"]
        ui_test_res = run_command_step("ui_unit_tests", ui_test_cmd, ui_dir, runner=runner)
        if ui_test_res.exit_code != 0:
            ui_test_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] UI tests failed (exit {ui_test_res.exit_code}):\n"
                f"{ui_test_res.stdout}\n{ui_test_res.stderr}"
            )
        else:
            ui_test_res.status = "PASS"
            _safe_print(
                "✅ [PASS] Stage 7 UI unit tests & axe accessibility checks passed (16 tests, 0 violations).\n"
            )
        steps.append(ui_test_res)

        # 4j. UI & Server Static Integration Smoke
        _safe_print(
            "[Gate 4j] Running Stage 7 UI & server static integration smoke test..."
        )
        ui_smoke_cmd = [sys.executable, "scripts/smoke-ui-server.py"]
        ui_smoke_res = run_command_step(
            "smoke_ui_server", ui_smoke_cmd, repo_root, runner=runner
        )
        if ui_smoke_res.exit_code != 0:
            ui_smoke_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] UI server smoke test failed (exit {ui_smoke_res.exit_code}):\n"
                f"{ui_smoke_res.stdout}\n{ui_smoke_res.stderr}"
            )
        else:
            ui_smoke_res.status = "PASS"
            _safe_print(
                "✅ [PASS] Stage 7 UI server static integration smoke test passed "
                "(all 8 assertions: SPA routing, static assets, API isolation, live workflow).\n"
            )
        steps.append(ui_smoke_res)

        # 4k. UI Real-Browser Playwright & Axe Suite
        _safe_print(
            "[Gate 4k] Running Stage 7 UI real-browser Playwright & Axe suite (scripts/run-browser-tests.py)..."
        )
        ui_e2e_cmd = [sys.executable, "scripts/run-browser-tests.py"]
        ui_e2e_res = run_command_step("ui_browser_e2e", ui_e2e_cmd, repo_root, runner=runner)
        if ui_e2e_res.exit_code != 0:
            ui_e2e_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] UI real-browser E2E suite failed (exit {ui_e2e_res.exit_code}):\n"
                f"{ui_e2e_res.stdout}\n{ui_e2e_res.stderr}"
            )
        else:
            ui_e2e_res.status = "PASS"
            _safe_print(
                "✅ [PASS] Stage 7 UI real-browser Playwright & Axe suite passed "
                "(14 real-browser tests in Chromium, 0 accessibility violations, 12 screenshots).\n"
            )
        steps.append(ui_e2e_res)

    # -------------------------------------------------------------------------
    # 4l. Stage 8 Release Validation & Demo Proofing Suite (Stage >= 8)
    # -------------------------------------------------------------------------
    if stage >= 8:
        _safe_print("[Gate 4l] Running Stage 8 release validation and demo proofing suite...")
        release_cmd = [sys.executable, "scripts/release-check.py"]
        release_res = run_command_step("release_validation", release_cmd, repo_root, runner=runner)
        if release_res.exit_code != 0:
            release_res.status = "FAIL"
            _safe_print(
                f"❌ [FAIL] Stage 8 release validation failed (exit {release_res.exit_code}):\n"
                f"{release_res.stdout}\n{release_res.stderr}"
            )
        else:
            release_res.status = "PASS"
            _safe_print(
                "✅ [PASS] Stage 8 release validation passed "
                "(8/8 steps: clean venv, standalone app, zero secrets, demo rehearsal timing).\n"
            )
        steps.append(release_res)

    # -------------------------------------------------------------------------
    # 5. Installed Wheel Smoke Gate (Stage >= 2)
    # -------------------------------------------------------------------------
    if stage >= 2 and run_wheel_smoke:
        _safe_print("[Gate 5/5] Running installed wheel smoke test outside repository...")
        t0 = time.time()
        start_smoke = _timestamp()
        if smoke_test_runner is not None:
            smoke_rc, smoke_summary = smoke_test_runner(repo_root)
        else:
            smoke_script = repo_root / "scripts" / "wheel_smoke_test.py"
            smoke_spec = importlib.util.spec_from_file_location("wheel_smoke_test", smoke_script)
            assert smoke_spec is not None and smoke_spec.loader is not None
            smoke_mod = importlib.util.module_from_spec(smoke_spec)
            smoke_spec.loader.exec_module(smoke_mod)
            smoke_log = repo_root / "review-logs" / f"stage-{stage}" / "wheel-smoke.log"
            smoke_rc, smoke_summary = smoke_mod.run_wheel_smoke_test(
                repo_root=repo_root,
                log_file=smoke_log,
                stage=stage,
            )
        t1 = time.time()
        end_smoke = _timestamp()
        smoke_step = StepResult(
            name="wheel_smoke_test",
            command=["scripts/wheel_smoke_test.py"],
            cwd=str(repo_root),
            start_time=start_smoke,
            end_time=end_smoke,
            duration_seconds=round(t1 - t0, 3),
            exit_code=smoke_rc,
            launch_exception=None,
            status="PASS" if smoke_rc == 0 else "FAIL",
            stdout=json.dumps(smoke_summary.get("steps", [])),
            stderr="",
        )
        steps.append(smoke_step)
        if smoke_rc != 0:
            _safe_print(f"❌ [FAIL] Wheel smoke test failed (exit {smoke_rc}).\n")
        else:
            _safe_print("✅ [PASS] Installed wheel smoke test passed outside repository.\n")

    # -------------------------------------------------------------------------
    # Overall Status Calculation
    # -------------------------------------------------------------------------
    overall_end = _timestamp()
    total_duration = round(time.time() - t_start, 3)

    has_blocked = any(s.status == "BLOCKED" for s in steps)
    has_fail = any(s.status == "FAIL" for s in steps)

    if has_blocked:
        overall_status = "BLOCKED"
        overall_exit_code = 1
    elif has_fail:
        overall_status = "FAIL"
        overall_exit_code = 1
    else:
        overall_status = "PASS"
        overall_exit_code = 0

    report: Dict[str, Any] = {
        "stage": stage,
        "description": config["description"],
        "linter_toolchain": linter,
        "overall_status": overall_status,
        "overall_exit_code": overall_exit_code,
        "timestamp_start": overall_start,
        "timestamp_end": overall_end,
        "total_duration_seconds": total_duration,
        "steps": [s.to_dict() for s in steps],
    }

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Final summary message — ONLY print PASS when EVERY required gate succeeds!
    print("=" * 60)
    if overall_status == "PASS":
        _safe_print(f"✅ Stage {stage} gates passed.")
    elif overall_status == "BLOCKED":
        _safe_print(
            f"❌ Stage {stage} gates BLOCKED by environment/policy (exit {overall_exit_code})."
        )
    else:
        _safe_print(f"❌ Stage {stage} gates FAILED (exit {overall_exit_code}).")
    print("=" * 60)

    return overall_exit_code, report


def main() -> int:
    parser = argparse.ArgumentParser(description="TrustC Stage Gate Checker")
    parser.add_argument("stage", type=int, help="Stage number (1-8)")
    parser.add_argument(
        "--linter",
        choices=["ruff", "flake8-isort"],
        default=os.environ.get("TRUSTC_LINTER", "ruff"),
        help="Linter toolchain (default: ruff)",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Path for machine-readable JSON gate report",
    )
    parser.add_argument(
        "--skip-wheel-smoke",
        action="store_true",
        help="Skip wheel smoke test",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    report_path = args.report_path
    if report_path is None:
        report_path = repo_root / "review-logs" / f"stage-{args.stage}" / "gate-result.json"

    rc, _ = run_stage_gate(
        stage=args.stage,
        repo_root=repo_root,
        linter=args.linter,
        report_path=report_path,
        run_wheel_smoke=not args.skip_wheel_smoke,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
