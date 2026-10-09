"""Record all Stage 4 execution logs in UTF-8 to review-logs/stage-4/."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

out_dir = Path("review-logs/stage-4")
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
    print(f"Recording Stage 4 logs into {out_dir.resolve()}...")

    # 1. Gate execution with flake8-isort
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "4", "--linter", "flake8-isort"],
        "check-stage-4.log",
    )

    # 2. Flake8
    run_and_save(
        [
            sys.executable,
            "-m",
            "flake8",
            "--max-line-length=100",
            "--extend-ignore=E203,W503",
            "src/",
            "tests/",
        ],
        "flake8.txt",
    )

    # 3. isort
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
        ],
        "isort.txt",
    )

    # 4. mypy
    run_and_save(
        [sys.executable, "-m", "mypy", "src/", "tests/"],
        "mypy.txt",
    )

    # 5. pytest
    run_and_save(
        [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "--tb=short",
            "-m",
            "stage1 or stage2 or stage3 or stage4",
            "tests/",
        ],
        "pytest.txt",
    )

    # 6. CLI build F2 (exit 0)
    run_and_save(
        [
            sys.executable,
            "-m",
            "trustc.cli",
            "build",
            "tests/fixtures/F2.trust",
            "-o",
            ".trustc-smoke/generated",
            "--target=fastapi",
            "--replace",
            "--format=json",
        ],
        "cli-build-f2.txt",
    )

    # 7. CLI build F1 refusal (exit 1)
    run_and_save(
        [
            sys.executable,
            "-m",
            "trustc.cli",
            "build",
            "tests/fixtures/F1.trust",
            "-o",
            ".trustc-smoke/refusal_f1",
            "--replace",
            "--format=json",
        ],
        "cli-build-f1.txt",
    )

    # 8. CLI build F4 invalid spec (exit 2)
    run_and_save(
        [
            sys.executable,
            "-m",
            "trustc.cli",
            "build",
            "tests/fixtures/F4.trust",
            "-o",
            ".trustc-smoke/refusal_f4",
            "--replace",
            "--format=json",
        ],
        "cli-build-f4.txt",
    )

    # 9. Runtime smoke test
    run_and_save(
        [
            sys.executable,
            "scripts/smoke-generated.py",
            "tests/fixtures/F2.trust",
            "-o",
            ".trustc-smoke/generated",
        ],
        "smoke-generated.txt",
    )

    # 10. Copy generated artifact manifest into review logs
    manifest_source = Path(".trustc-smoke/generated/trustc-manifest.json")
    if manifest_source.is_file():
        shutil.copy2(manifest_source, out_dir / "trustc-manifest.json")
        print("trustc-manifest.json copied to review-logs/stage-4/")

    # 11. Standalone clean environment installation test
    run_and_save(
        [
            sys.executable,
            "scripts/test_generated_install.py",
        ],
        "generated-app-install-run.txt",
    )

    # 12. SARIF schema validation
    run_and_save(
        [
            sys.executable,
            "scripts/validate_sarif_schema.py",
        ],
        "sarif-schema-validation.txt",
    )

    # 13. Traceability metadata
    git_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    git_status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout.strip()
    python_ver = sys.version
    traceability_content = (
        f"Git Commit: {git_head}\n"
        f"Working Tree Status:\n{git_status}\n\n"
        f"Python Version: {python_ver}\n"
        f"Platform: {sys.platform}\n"
    )
    (out_dir / "traceability.txt").write_text(traceability_content, encoding="utf-8")
    print("traceability.txt recorded")

    print("Stage 4 review logs recorded successfully.")


if __name__ == "__main__":
    main()
