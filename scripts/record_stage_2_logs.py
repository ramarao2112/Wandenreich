"""Record all Stage 2 execution logs to review-logs/stage-2/."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

out_dir = Path("review-logs/stage-2")
out_dir.mkdir(parents=True, exist_ok=True)


def run_and_save(cmd: list[str], outfile: str) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    content = (
        f"Command: {' '.join(cmd)}\n"
        f"Exit Code: {res.returncode}\n\n"
        f"STDOUT:\n{res.stdout}\n"
        f"STDERR:\n{res.stderr}\n"
    )
    (out_dir / outfile).write_text(content, encoding="utf-8")
    print(f"{outfile}: exit {res.returncode}")


if __name__ == "__main__":
    # 1. Gate with ruff (demonstrating blocked policy detection, exit nonzero)
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "2", "--linter", "ruff"],
        "check-stage-2-ruff.log",
    )

    # 2. Gate with documented equivalent toolchain flake8-isort (exit 0)
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "2", "--linter", "flake8-isort"],
        "check-stage-2.log",
    )

    # 3. Dedicated pytest parser run
    run_and_save(
        [sys.executable, "-m", "pytest", "-v", "tests/unit/test_parser.py"],
        "pytest-stage-2.log",
    )

    # 4. Full pytest suite run
    run_and_save(
        [sys.executable, "-m", "pytest", "-v", "-m", "stage1 or stage2"],
        "pytest.log",
    )

    # 5. Type check
    run_and_save(
        [sys.executable, "-m", "mypy", "src/", "tests/"],
        "mypy.log",
    )

    # 6. Flake8
    run_and_save(
        [
            sys.executable, "-m", "flake8", "src/", "tests/",
            "--max-line-length=100", "--extend-ignore=E203,W503",
        ],
        "flake8.log",
    )

    # 7. Isort
    run_and_save(
        [sys.executable, "-m", "isort", "--check", "--diff", "src/", "tests/"],
        "isort.log",
    )

    # 8. CLI parse F2
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "parse", "tests/fixtures/F2.trust"],
        "cli-parse-f2.log",
    )

    # 9. CLI parse F4
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "parse", "tests/fixtures/F4.trust"],
        "cli-parse-f4.log",
    )

    # 10. Wheel smoke test outside repo
    run_and_save(
        [sys.executable, "scripts/wheel_smoke_test.py"],
        "wheel-smoke.log",
    )
