"""Focused gate-runner tests using an injected/stubbed subprocess runner.

Verifies:
1. Required check returns nonzero -> overall status FAIL, exit nonzero, no PASS marker.
2. Required tool fails to launch (e.g. WinError 4551 WDAC block) -> overall status BLOCKED,
   exit nonzero, no PASS marker.
3. Pytest collects no tests -> overall status FAIL, exit nonzero, no PASS marker.
4. Wheel smoke test fails -> overall status FAIL, exit nonzero, no PASS marker.
5. All required checks succeed -> overall status PASS, exit 0, PASS marker emitted.
6. Machine-readable gate report schema is complete and valid.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_CHECK_STAGE_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "check-stage.py"
_spec = importlib.util.spec_from_file_location("check_stage", _CHECK_STAGE_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
run_stage_gate = _module.run_stage_gate

pytestmark = pytest.mark.stage2


class DummyProcessResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_required_check_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When a required check (e.g. mypy) exits nonzero, gate fails without PASS marker."""
    captured_out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)

    def stub_runner(cmd, **kwargs):
        if "-m" in cmd and "mypy" in cmd:
            return DummyProcessResult(returncode=1, stdout="Found 3 errors in 2 files")
        if any("F4.trust" in str(arg) for arg in cmd):
            return DummyProcessResult(returncode=2, stderr="syntax error")
        return DummyProcessResult(returncode=0, stdout="100 passed")

    report_path = tmp_path / "gate-result.json"
    rc, report = run_stage_gate(
        stage=2,
        repo_root=tmp_path,
        linter="flake8-isort",
        runner=stub_runner,
        report_path=report_path,
        smoke_test_runner=lambda root: (0, {"steps": []}),
    )

    output = captured_out.getvalue()
    assert rc != 0
    assert report["overall_status"] == "FAIL"
    assert "Stage 2 gates passed" not in output
    assert "Stage 2 gates FAILED" in output
    assert report_path.exists()


def test_required_tool_launch_failure_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a tool cannot be launched (e.g. WDAC WinError 4551), status is BLOCKED and non-zero."""
    captured_out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)

    def stub_runner(cmd, **kwargs):
        if "-m" in cmd and "ruff" in cmd:
            raise OSError(4551, "An Application Control policy has blocked this file")
        if any("F4.trust" in str(arg) for arg in cmd):
            return DummyProcessResult(returncode=2, stderr="syntax error")
        return DummyProcessResult(returncode=0, stdout="all passed")

    report_path = tmp_path / "gate-result.json"
    rc, report = run_stage_gate(
        stage=2,
        repo_root=tmp_path,
        linter="ruff",
        runner=stub_runner,
        report_path=report_path,
        smoke_test_runner=lambda root: (0, {"steps": []}),
    )

    output = captured_out.getvalue()
    assert rc != 0
    assert report["overall_status"] == "BLOCKED"
    assert "Stage 2 gates passed" not in output
    assert "BLOCKED by environment/policy" in output

    # Check step details
    ruff_step = next(s for s in report["steps"] if s["name"] == "lint_ruff")
    assert ruff_step["status"] == "BLOCKED"
    assert "4551" in (ruff_step["launch_exception"] or "")


def test_pytest_collects_no_tests_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When pytest collects 0 tests (exit code 5), gate fails without PASS marker."""
    captured_out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)

    def stub_runner(cmd, **kwargs):
        if "-m" in cmd and "pytest" in cmd:
            return DummyProcessResult(returncode=5, stdout="collected 0 items\nNO TESTS RAN")
        if any("F4.trust" in str(arg) for arg in cmd):
            return DummyProcessResult(returncode=2, stderr="syntax error")
        return DummyProcessResult(returncode=0)

    report_path = tmp_path / "gate-result.json"
    rc, report = run_stage_gate(
        stage=2,
        repo_root=tmp_path,
        linter="flake8-isort",
        runner=stub_runner,
        report_path=report_path,
        smoke_test_runner=lambda root: (0, {"steps": []}),
    )

    output = captured_out.getvalue()
    assert rc != 0
    assert report["overall_status"] == "FAIL"
    assert "Stage 2 gates passed" not in output


def test_wheel_smoke_failure_fails_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When wheel smoke test fails, gate fails without PASS marker."""
    captured_out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)

    def stub_runner(cmd, **kwargs):
        if any("F4.trust" in str(arg) for arg in cmd):
            return DummyProcessResult(returncode=2, stderr="syntax error")
        return DummyProcessResult(returncode=0, stdout="passed")

    report_path = tmp_path / "gate-result.json"
    rc, report = run_stage_gate(
        stage=2,
        repo_root=tmp_path,
        linter="flake8-isort",
        runner=stub_runner,
        report_path=report_path,
        smoke_test_runner=lambda root: (1, {"steps": [{"name": "smoke", "status": "FAIL"}]}),
    )

    output = captured_out.getvalue()
    assert rc != 0
    assert report["overall_status"] == "FAIL"
    assert "Stage 2 gates passed" not in output


def test_all_required_checks_succeed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When all checks pass, overall status is PASS, exit 0, and PASS marker emitted."""
    captured_out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)

    def stub_runner(cmd, **kwargs):
        if any("F4.trust" in str(arg) for arg in cmd):
            return DummyProcessResult(returncode=2, stderr='{"exitCode": 2}')
        return DummyProcessResult(returncode=0, stdout="100 passed")

    report_path = tmp_path / "gate-result.json"
    rc, report = run_stage_gate(
        stage=2,
        repo_root=tmp_path,
        linter="flake8-isort",
        runner=stub_runner,
        report_path=report_path,
        smoke_test_runner=lambda root: (0, {"steps": [{"name": "smoke", "status": "PASS"}]}),
    )

    output = captured_out.getvalue()
    assert rc == 0
    assert report["overall_status"] == "PASS"
    assert "Stage 2 gates passed" in output
    assert report_path.exists()

    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_data["stage"] == 2
    assert report_data["overall_status"] == "PASS"
    assert len(report_data["steps"]) >= 5
    for s in report_data["steps"]:
        assert "command" in s
        assert "status" in s
        assert "start_time" in s
        assert "end_time" in s
