"""Record all Stage 3 execution logs in UTF-8 to review-logs/stage-3/."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

out_dir = Path("review-logs/stage-3")
out_dir.mkdir(parents=True, exist_ok=True)

ENV = {**os.environ, "PYTHONUTF8": "1"}


def run_and_save(cmd: list[str], outfile: str, raw_stdout: bool = False) -> int:
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV,
    )
    if raw_stdout:
        content = res.stdout or ""
    else:
        content = (
            f"Command: {' '.join(cmd)}\n"
            f"Exit Code: {res.returncode}\n\n"
            f"STDOUT:\n{res.stdout or ''}\n"
            f"STDERR:\n{res.stderr or ''}\n"
        )
    (out_dir / outfile).write_text(content, encoding="utf-8")
    print(f"{outfile}: exit {res.returncode}")
    return res.returncode


def main() -> None:
    print(f"Recording Stage 3 logs into {out_dir.resolve()}...")

    # 1. Gate execution with flake8-isort
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "3", "--linter", "flake8-isort"],
        "check-stage-3.log",
    )

    # 2. Strict SARIF 2.1.0 schema validation
    run_and_save(
        [sys.executable, "scripts/validate_sarif_schema.py"],
        "sarif-schema-validation.txt",
        raw_stdout=True,
    )

    # 3. Flake8
    run_and_save(
        [
            sys.executable,
            "-m",
            "flake8",
            "src/",
            "tests/",
            "scripts/",
            "--max-line-length=100",
            "--extend-ignore=E203,W503",
        ],
        "flake8.txt",
    )

    # 4. Isort with explicit UTF-8 mode
    run_and_save(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "isort",
            "--check",
            "--diff",
            "src/",
            "tests/",
            "scripts/",
        ],
        "isort.txt",
    )

    # 5. Mypy
    run_and_save(
        [sys.executable, "-m", "mypy", "src/", "tests/", "scripts/"],
        "mypy.txt",
    )

    # 6. Full pytest suite
    run_and_save(
        [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "-m",
            "stage1 or stage2 or stage3",
            "tests/",
        ],
        "pytest.txt",
    )

    # 7. CLI check F1 (exit 1 expected)
    run_and_save(
        [
            sys.executable,
            "-m",
            "trustc.cli",
            "check",
            "tests/fixtures/F1.trust",
            "--format",
            "json",
        ],
        "cli-check-f1.txt",
        raw_stdout=True,
    )

    # 8. CLI check F2 (exit 0 expected)
    run_and_save(
        [
            sys.executable,
            "-m",
            "trustc.cli",
            "check",
            "tests/fixtures/F2.trust",
            "--format",
            "json",
        ],
        "cli-check-f2.txt",
        raw_stdout=True,
    )

    # 9. CLI check F4 (exit 2 expected)
    run_and_save(
        [
            sys.executable,
            "-m",
            "trustc.cli",
            "check",
            "tests/fixtures/F4.trust",
            "--format",
            "json",
        ],
        "cli-check-f4.txt",
        raw_stdout=True,
    )

    # 10. CLI apply-fix F1 dry-run
    run_and_save(
        [
            sys.executable,
            "-m",
            "trustc.cli",
            "apply-fix",
            "tests/fixtures/F1.trust",
            "--rule",
            "TC-001",
            "--dry-run",
        ],
        "cli-apply-fix.txt",
        raw_stdout=True,
    )

    # 11. CLI explain TC-002
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "explain", "TC-002"],
        "cli-explain.txt",
        raw_stdout=True,
    )

    # 12. Wheel smoke test outside repo
    run_and_save(
        [sys.executable, "scripts/wheel_smoke_test.py"],
        "wheel-smoke.log",
    )

    print("Stage 3 log recording completed.")


if __name__ == "__main__":
    main()
