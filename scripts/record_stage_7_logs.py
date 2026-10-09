"""Record all Stage 7 execution logs in UTF-8 to review-logs/stage-7/."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

out_dir = Path("review-logs/stage-7")
out_dir.mkdir(parents=True, exist_ok=True)

repo_root = Path(__file__).resolve().parent.parent
ui_dir = repo_root / "ui"
npm_exe = shutil.which("npm.cmd" if sys.platform == "win32" else "npm") or "npm"

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


def record_ui_artifacts() -> None:
    # 1. UI Lint (ESLint)
    run_and_save([npm_exe, "run", "lint"], "ui-lint.log", cwd=ui_dir)

    # 2. UI Typecheck
    run_and_save([npm_exe, "run", "typecheck"], "ui-typecheck.log", cwd=ui_dir)

    # 3. UI Build
    run_and_save([npm_exe, "run", "build"], "ui-build.log", cwd=ui_dir)

    # 4. UI Tests (Vitest + axe)
    run_and_save([npm_exe, "test"], "ui-tests.log", cwd=ui_dir)

    # 5. UI Server Smoke
    run_and_save([sys.executable, "scripts/smoke-ui-server.py"], "ui-server-smoke.log")

    # 6. UI Real-Browser Playwright & Axe Suite
    run_and_save([sys.executable, "scripts/run-browser-tests.py"], "ui-browser-e2e.log")

    # 5. UI Dist Manifest
    ui_dist = ui_dir / "dist"
    if ui_dist.exists():
        dist_files = []
        for p in ui_dist.rglob("*"):
            if p.is_file():
                rel = p.relative_to(ui_dist).as_posix()
                dist_files.append({
                    "path": rel,
                    "bytes": p.stat().st_size,
                })
        dist_files.sort(key=lambda x: x["path"])
        (out_dir / "ui-dist-manifest.json").write_text(
            json.dumps({"files": dist_files, "totalFiles": len(dist_files)}, indent=2),
            encoding="utf-8",
        )
        print("ui-dist-manifest.json: recorded")

    # 6. Full Gate Check
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "7", "--linter", "flake8-isort"],
        "check-stage-7.log",
    )


if __name__ == "__main__":
    record_ui_artifacts()
