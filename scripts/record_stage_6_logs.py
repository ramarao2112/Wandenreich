"""Record all Stage 6 execution logs in UTF-8 to review-logs/stage-6/."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from trustc.server import create_app

out_dir = Path("review-logs/stage-6")
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


def record_api_payloads() -> None:
    """Record direct API payloads from local server."""
    app = create_app()
    with TestClient(app) as client:
        f1_spec = Path("tests/fixtures/F1.trust").read_text(encoding="utf-8")
        f2_spec = Path("tests/fixtures/F2.trust").read_text(encoding="utf-8")

        # 1. /api/meta
        r_meta = client.get("/api/meta")
        (out_dir / "api-meta.json").write_text(
            json.dumps(r_meta.json(), indent=2), encoding="utf-8"
        )

        # 2. /api/examples
        r_ex = client.get("/api/examples")
        (out_dir / "api-examples.json").write_text(
            json.dumps(r_ex.json(), indent=2), encoding="utf-8"
        )

        # 3. /api/rules/TC-001
        r_rule = client.get("/api/rules/TC-001")
        (out_dir / "api-rules-tc001.json").write_text(
            json.dumps(r_rule.json(), indent=2), encoding="utf-8"
        )

        # 4. /api/check F2
        r_chk_f2 = client.post("/api/check", json={"spec": f2_spec, "specVersion": 0})
        (out_dir / "api-check-f2.json").write_text(
            json.dumps(r_chk_f2.json(), indent=2), encoding="utf-8"
        )

        # 5. /api/check F1
        r_chk_f1 = client.post("/api/check", json={"spec": f1_spec, "specVersion": 0})
        (out_dir / "api-check-f1.json").write_text(
            json.dumps(r_chk_f1.json(), indent=2), encoding="utf-8"
        )

        # 6. /api/check SARIF
        r_sarif = client.post(
            "/api/check?format=sarif",
            json={"spec": f1_spec, "specVersion": 0},
        )
        (out_dir / "api-check-sarif.json").write_text(
            json.dumps(r_sarif.json(), indent=2), encoding="utf-8"
        )

        # 7. /api/build F2
        r_b = client.post("/api/build", json={"spec": f2_spec, "specVersion": 0})
        b_run_id = r_b.json()["runId"]
        b_result = None
        for _ in range(50):
            st = client.get(f"/api/runs/{b_run_id}").json()
            if st.get("state") == "terminal":
                b_result = st.get("result")
                break
            time.sleep(0.1)
        if b_result:
            (out_dir / "api-build-f2.json").write_text(
                json.dumps(b_result, indent=2), encoding="utf-8"
            )
            build_id = b_result.get("buildId")

            # 8. /api/attack F2 with buildId
            if build_id:
                r_a = client.post(
                    "/api/attack",
                    json={"spec": f2_spec, "specVersion": 0, "buildId": build_id},
                )
                a_run_id = r_a.json()["runId"]
                a_result = None
                for _ in range(60):
                    st = client.get(f"/api/runs/{a_run_id}").json()
                    if st.get("state") == "terminal":
                        a_result = st.get("result")
                        break
                    time.sleep(0.5)
                if a_result:
                    (out_dir / "api-attack-f2.json").write_text(
                        json.dumps(a_result, indent=2), encoding="utf-8"
                    )

    print("API JSON payloads recorded.")


def main() -> None:
    print(f"Recording Stage 6 logs into {out_dir.resolve()}...")

    # 1. Gate execution with flake8-isort
    run_and_save(
        [sys.executable, "scripts/check-stage.py", "6", "--linter", "flake8-isort"],
        "check-stage-6.log",
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

    # 4. mypy
    run_and_save(
        [sys.executable, "-m", "mypy", "src/", "tests/"],
        "mypy.txt",
    )

    # 5. Cumulative Pytest (all 237 tests)
    run_and_save(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        "pytest.txt",
    )

    # 6. Focused Server Pytest (16 tests)
    run_and_save(
        [sys.executable, "-m", "pytest", "tests/unit/test_server.py", "-v"],
        "pytest-server.txt",
    )

    # 7. Smoke Server
    run_and_save(
        [sys.executable, "scripts/smoke-server.py"],
        "smoke-server.txt",
    )

    # 8. trustc serve --help
    run_and_save(
        [sys.executable, "-m", "trustc.cli", "serve", "--help"],
        "cli-serve-help.txt",
    )

    # 9. API JSON Payloads
    record_api_payloads()

    print("All Stage 6 logs successfully written.")


if __name__ == "__main__":
    main()
