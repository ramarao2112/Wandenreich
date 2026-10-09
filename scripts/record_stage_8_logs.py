"""Record all Stage 8 execution logs in UTF-8 to review-logs/stage-8/."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

out_dir = Path("review-logs/stage-8")
out_dir.mkdir(parents=True, exist_ok=True)

repo_root = Path(__file__).resolve().parent.parent
ENV = {**os.environ, "PYTHONUTF8": "1"}


def run_and_save(cmd: list[str], outfile: str, cwd: Path = repo_root) -> int:
    res = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV,
    )
    content = (
        f"Command: {' '.join(cmd)}\n"
        f"Exit Code: {res.returncode}\n\n"
        f"STDOUT:\n{res.stdout or ''}\n"
        f"STDERR:\n{res.stderr or ''}\n"
    )
    (out_dir / outfile).write_text(content, encoding="utf-8")
    print(f"{outfile}: exit {res.returncode}")
    return res.returncode


def record_stage_8_artifacts() -> None:
    # 1. Release check suite
    print("Running scripts/release-check.py...")
    run_and_save([sys.executable, "scripts/release-check.py"], "release-check.log")

    # 2. Full Gate Check for Stage 8
    print("Running scripts/check-stage.py 8 --linter flake8-isort...")
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "8", "--linter", "flake8-isort"],
        "check-stage-8.log",
    )


if __name__ == "__main__":
    record_stage_8_artifacts()
