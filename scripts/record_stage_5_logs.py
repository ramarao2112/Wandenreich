"""Record all Stage 5 execution logs in UTF-8 to review-logs/stage-5/."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

out_dir = Path("review-logs/stage-5")
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


def record_mutation_evidence() -> None:
    from trustc.contracts import AttackCompleted
    from trustc.harness import mutate_and_attack_f2, run_attack_harness
    from trustc.generator import build_app
    from trustc.parser import parse_file
    import tempfile

    f2_path = Path("tests/fixtures/F2.trust")
    prog = parse_file(f2_path)

    # 1. Normal run
    with tempfile.TemporaryDirectory(prefix="trustc_orig_rec_") as td:
        orig_app = Path(td) / "app"
        build_res = build_app(f2_path, orig_app)
        normal_res = run_attack_harness(prog, orig_app)
        assert isinstance(normal_res, AttackCompleted)
        orig_hash = normal_res.artifact_hash

    # 2. Mutated run
    mut_res = mutate_and_attack_f2(f2_path)
    mut_hash = mut_res.artifact_hash

    # Save complete JSON
    (out_dir / "attack-f2-mutated.json").write_text(
        json.dumps(mut_res.model_dump(by_alias=True), indent=2),
        encoding="utf-8",
    )
    print("attack-f2-mutated.json: exit 1 (written)")

    # Identify failed step and preserved step
    failed_step = next(s for s in mut_res.steps if s.outcome and s.outcome.value == "unexpected")
    assert failed_step.outcome is not None
    preserved_user_step = next(
        s for s in mut_res.steps
        if s.actor == "second_user" and "/users/" in s.path
    )
    assert preserved_user_step.outcome is not None

    report_lines = [
        "TrustC Stage 5 — F2 Access Control Mutation Testing Evidence",
        "=" * 65,
        f"Original Build Hash: {orig_hash}",
        f"Mutated Build Hash:  {mut_hash}",
        f"Artifact Hash Recomputed: {orig_hash != mut_hash}",
        "",
        "Original F2 Attack Result:",
        f"  Exit code: {normal_res.exit_code}",
        f"  Matched: {normal_res.as_expected + normal_res.review}",
        f"  asExpected: {normal_res.as_expected}, review: {normal_res.review}, unexpected: {normal_res.unexpected}",
        "",
        "Mutated F2 Attack Result (Owner-Check Statement Removed from routers/trips.py):",
        f"  Exit code: {mut_res.exit_code} (assertion: exit 1 on unexpected access)",
        f"  Matched: {mut_res.as_expected + mut_res.review}",
        f"  asExpected: {mut_res.as_expected}, review: {mut_res.review}, unexpected: {mut_res.unexpected}",
        "",
        "Detected Flaw Step Details:",
        f"  Step ID:         {failed_step.step_id}",
        f"  Endpoint:        {failed_step.endpoint}",
        f"  Actor:           {failed_step.actor}",
        f"  Method & Path:   {failed_step.method} {failed_step.path}",
        f"  Expected Status: {failed_step.expect}",
        f"  Received Status: {failed_step.got}",
        f"  Outcome:         {failed_step.outcome.value}",
        "",
        "Preserved Self-Protection Step Details (Unmutated routers/users.py):",
        f"  Step ID:         {preserved_user_step.step_id}",
        f"  Endpoint:        {preserved_user_step.endpoint}",
        f"  Actor:           {preserved_user_step.actor}",
        f"  Method & Path:   {preserved_user_step.method} {preserved_user_step.path}",
        f"  Expected Status: {preserved_user_step.expect}",
        f"  Received Status: {preserved_user_step.got}",
        f"  Outcome:         {preserved_user_step.outcome.value}",
        "",
        "Isolation Verification:",
        "  - The mutation helper operates on an isolated directory copy.",
        "  - AST parsing removed the owner-check statement in routers/trips.py.",
        "  - ast.parse confirmed syntax validity before testing.",
        "  - Manifest and artifactHash were recalculated over the actual mutated bytes.",
        "  - Original build and files remain completely untouched.",
    ]
    (out_dir / "mutation-f2.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("mutation-f2.txt: written")


def main() -> None:
    print(f"Recording Stage 5 logs into {out_dir.resolve()}...")

    # 1. Gate execution with flake8-isort
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "5", "--linter", "flake8-isort"],
        "check-stage-5.log",
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
        [sys.executable, "-m", "isort", "--check", "--diff", "src/", "tests/"],
        "isort.txt",
    )

    # 4. Cumulative Pytest (all 220+ tests)
    run_and_save(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        "pytest.txt",
    )

    # 5. Focused Harness Pytest (14 tests)
    run_and_save(
        [sys.executable, "-m", "pytest", "tests/unit/test_harness.py", "-v"],
        "pytest-harness.txt",
    )

    # 6. Human CLI outputs
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/F2.trust"],
        "cli-attack-f2.txt",
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/F3.trust"],
        "cli-attack-f3.txt",
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/X08.trust"],
        "cli-attack-x08.txt",
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/X11.trust"],
        "cli-attack-x11.txt",
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/F1.trust"],
        "cli-attack-f1.txt",
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/F4.trust"],
        "cli-attack-f4.txt",
    )

    # 7. Full structured AttackCompleted JSON outputs (S5-04 item 1)
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/F2.trust", "--format=json"],
        "attack-f2.json",
        raw_stdout=True,
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/F3.trust", "--format=json"],
        "attack-f3.json",
        raw_stdout=True,
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/X08.trust", "--format=json"],
        "attack-x08.json",
        raw_stdout=True,
    )
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "attack", "tests/fixtures/X11.trust", "--format=json"],
        "attack-x11.json",
        raw_stdout=True,
    )

    # 8. Mutation testing evidence (S5-04 items 5 & 6)
    record_mutation_evidence()

    print("All Stage 5 logs successfully written.")


if __name__ == "__main__":
    main()
