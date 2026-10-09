"""Unit and integration tests for Stage 5 live access harness."""

from __future__ import annotations

import io
import json
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, List
from unittest.mock import patch

import httpx
import pytest

from trustc.contracts import (
    Actor,
    ActorPayload,
    AttackCompleted,
    Outcome,
    PhasePayload,
    RunEvent,
    RunFailure,
)
from trustc.generator import build_app
from trustc.harness import (
    _print_result,
    attack_spec,
    mutate_and_attack_f2,
    run_attack_harness,
)
from trustc.manifest import verify_manifest
from trustc.parser import parse_file
from trustc.seeder import DEFAULT_TEST_SECRET


@pytest.mark.stage5
def test_f2_attack_harness_counts_and_exit_code() -> None:
    """Gate 5: F2 produces exactly 6 as_expected, 0 review, 0 unexpected, exitCode 0."""
    res = attack_spec("tests/fixtures/F2.trust", fmt="json")
    assert isinstance(res, AttackCompleted), f"Expected AttackCompleted, got {type(res).__name__}"
    assert res.exit_code == 0
    assert res.as_expected == 6
    assert res.review == 0
    assert res.unexpected == 0
    assert res.total == 6
    assert len(res.steps) == 6
    assert res.coverage.tested_endpoints == ["GET /trips/{id}", "GET /users/{id}"]
    assert len(res.coverage.excluded_endpoints) == 1
    assert res.coverage.excluded_endpoints[0]["endpoint"] == "POST /trips"


@pytest.mark.stage5
def test_f3_attack_harness_counts_and_declarations() -> None:
    """Gate 5: F3 produces 8 as_expected, 1 review, 0 unexpected, total 9, exitCode 0."""
    res = attack_spec("tests/fixtures/F3.trust", fmt="json")
    assert isinstance(res, AttackCompleted), f"Expected AttackCompleted, got {type(res).__name__}"
    assert res.exit_code == 0
    assert res.as_expected == 8
    assert res.review == 1
    assert res.unexpected == 0
    assert res.total == 9
    assert len(res.steps) == 9

    # Find waived step for second_user on PUT /trips/{id}/visibility
    waived_steps = [
        s for s in res.steps
        if s.endpoint == "PUT /trips/{id}/visibility" and s.actor == Actor.SECOND_USER
    ]
    assert len(waived_steps) == 1
    w_step = waived_steps[0]
    assert w_step.got == 200
    assert w_step.expect == 200
    assert w_step.outcome == Outcome.REVIEW

    # Confirm declaration observation is marked observed
    assert len(res.declaration_observations) >= 1
    obs = res.declaration_observations[0]
    assert obs.state == "observed"
    assert len(obs.step_ids) == 3


@pytest.mark.stage5
def test_mutation_testing_f2_detects_flaw_and_preserves_user_self() -> None:
    """Gate 5: Mutating Trip owner-check in F2 causes second-user read 200
    instead of 403, unexpected 1, exit 1, while User route remains self-protected."""
    with tempfile.TemporaryDirectory(prefix="trustc_test_mut_") as td:
        app_dir = Path(td) / "app"
        build_app("tests/fixtures/F2.trust", app_dir)
        prog = parse_file("tests/fixtures/F2.trust")

        # Read original manifest digest
        orig_manifest = json.loads((app_dir / "trustc-manifest.json").read_text(encoding="utf-8"))
        orig_digest = orig_manifest.get("artifactDigest")

        res = mutate_and_attack_f2(app_dir, prog)
        assert isinstance(res, AttackCompleted)
        assert res.exit_code == 1
        assert res.as_expected == 5
        assert res.review == 0
        assert res.unexpected == 1
        assert res.total == 6

        # Check that mutated artifact has a distinct digest reflecting executed bytes
        assert res.artifact_hash != orig_digest

        # Check original app_dir was left untouched
        ok_orig, _ = verify_manifest(app_dir)
        assert ok_orig is True, "Original artifact directory was modified by mutation helper"

        # Check the failing step is specifically second_user GET /trips/{id}
        unexp_steps = [s for s in res.steps if s.outcome == Outcome.UNEXPECTED]
        assert len(unexp_steps) == 1
        bad_step = unexp_steps[0]
        assert bad_step.endpoint == "GET /trips/{id}"
        assert bad_step.actor == Actor.SECOND_USER
        assert bad_step.got == 200
        assert bad_step.expect == 403

        # User endpoint remains protected with all 3 actors as_expected
        user_steps = [s for s in res.steps if s.endpoint == "GET /users/{id}"]
        assert len(user_steps) == 3
        assert all(s.outcome == Outcome.AS_EXPECTED for s in user_steps)


@pytest.mark.stage5
def test_x08_public_owned_get_delete_with_isolated_state() -> None:
    """X08: Public owned GET and DELETE have review outcomes for anon and second_user."""
    res = attack_spec("tests/fixtures/X08.trust", fmt="json")
    assert isinstance(res, AttackCompleted), f"Expected AttackCompleted, got {type(res).__name__}"
    assert res.exit_code == 0
    assert res.as_expected == 2
    assert res.review == 4
    assert res.unexpected == 0
    assert res.total == 6

    # Verify all checks passed across actors
    for step in res.steps:
        for c in step.checks:
            assert c.passed is True, f"Check failed on {step.endpoint}: {c}"

    # Confirm DELETE requests all got 204 and verified persistence
    delete_steps = [s for s in res.steps if s.method == "DELETE"]
    assert len(delete_steps) == 3
    for ds in delete_steps:
        assert ds.got == 204
        assert any(c.name == "allowed_write_persistence" and c.passed for c in ds.checks)


@pytest.mark.stage5
def test_x11_zero_eligible_item_endpoints_coverage() -> None:
    """X11: Program with collection-only routes produces zero steps and explicit empty coverage."""
    res = attack_spec("tests/fixtures/X11.trust", fmt="json")
    assert isinstance(res, AttackCompleted)
    assert res.exit_code == 0
    assert res.as_expected == 0
    assert res.review == 0
    assert res.unexpected == 0
    assert res.total == 0
    assert res.steps == []
    assert res.coverage.tested_endpoints == []
    assert len(res.coverage.excluded_endpoints) == 2


@pytest.mark.stage5
def test_refused_and_syntax_error_specs_never_start_app() -> None:
    """Refused (F1) and syntax error (F4) specs never start an application child process."""
    with patch("subprocess.Popen") as mock_popen:
        res_f1 = attack_spec("tests/fixtures/F1.trust", fmt="json")
        assert isinstance(res_f1, RunFailure)
        assert res_f1.exit_code == 1
        assert res_f1.status == "refused"
        assert len(res_f1.diagnostics) >= 2
        mock_popen.assert_not_called()

    with patch("subprocess.Popen") as mock_popen:
        res_f4 = attack_spec("tests/fixtures/F4.trust", fmt="json")
        assert isinstance(res_f4, RunFailure)
        assert res_f4.exit_code == 2
        assert res_f4.status == "invalid_spec"
        assert len(res_f4.spec_errors) >= 1
        mock_popen.assert_not_called()


@pytest.mark.stage5
def test_step_ids_are_canonical_unprefixed_uuids() -> None:
    """S5-02: Step IDs must be valid unprefixed canonical UUID strings."""
    res = attack_spec("tests/fixtures/F2.trust", fmt="json")
    assert isinstance(res, AttackCompleted)

    seen_ids: set[str] = set()
    for step in res.steps:
        # Validate parses as valid UUID
        parsed_uuid = uuid.UUID(step.step_id)
        assert str(parsed_uuid) == step.step_id
        assert not step.step_id.startswith("step-")
        assert step.step_id not in seen_ids, f"Duplicate stepId found: {step.step_id}"
        seen_ids.add(step.step_id)

    # Check declaration observations reference valid step IDs
    for obs in res.declaration_observations:
        for s_id in obs.step_ids:
            assert s_id in seen_ids, f"Observation references unknown step ID: {s_id}"


@pytest.mark.stage5
def test_s5_01_human_summary_matched_totals_rendering() -> None:
    """S5-01: Verify human summary prints matched = asExpected + review and proper grammar."""
    # F2: 6 as_expected, 0 review -> 6 matched expectations · 0 policy reviews · 0 failed
    f2_res = attack_spec("tests/fixtures/F2.trust", fmt="json")
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        _print_result(f2_res, "human")
    out = buf.getvalue()
    assert "6 matched expectations · 0 policy reviews · 0 failed" in out

    # F3: 8 as_expected, 1 review -> 9 matched expectations · 1 policy review · 0 failed
    f3_res = attack_spec("tests/fixtures/F3.trust", fmt="json")
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        _print_result(f3_res, "human")
    out = buf.getvalue()
    assert "9 matched expectations · 1 policy review · 0 failed" in out

    # X08: 2 as_expected, 4 review -> 6 matched expectations · 4 policy reviews · 0 failed
    x08_res = attack_spec("tests/fixtures/X08.trust", fmt="json")
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        _print_result(x08_res, "human")
    out = buf.getvalue()
    assert "6 matched expectations · 4 policy reviews · 0 failed" in out

    # X11: 0 total -> 0 matched expectations · 0 policy reviews · 0 failed
    x11_res = attack_spec("tests/fixtures/X11.trust", fmt="json")
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        _print_result(x11_res, "human")
    out = buf.getvalue()
    assert "0 matched expectations · 0 policy reviews · 0 failed" in out
    assert "No eligible endpoints tested." in out


@pytest.mark.stage5
def test_normal_completion_lifecycle_and_single_final_event() -> None:
    """S5-03: Event ordering: pending precedes resolved,
    exactly one terminal event follows cleanup."""
    events: List[RunEvent] = []

    def on_event(ev: RunEvent) -> None:
        events.append(ev)

    with tempfile.TemporaryDirectory() as td:
        app_dir = Path(td) / "app"
        build_app("tests/fixtures/F2.trust", app_dir)
        prog = parse_file("tests/fixtures/F2.trust")

        res = run_attack_harness(
            program=prog,
            artifact_dir=app_dir,
            event_callback=on_event,
        )
        assert isinstance(res, AttackCompleted)

    # 1. Exactly one result event at the very end
    result_events = [ev for ev in events if ev.payload.type == "result"]
    assert len(result_events) == 1
    assert events[-1].payload.type == "result", (
        "Terminal result event must be the final event emitted"
    )

    # 2. Cleanup phase finishes before result event
    phase_payloads = [ev.payload for ev in events if isinstance(ev.payload, PhasePayload)]
    phase_names = [p.phase for p in phase_payloads]
    assert "cleanup" in phase_names
    cleanup_indices = [
        i for i, ev in enumerate(events)
        if isinstance(ev.payload, PhasePayload) and ev.payload.phase == "cleanup"
    ]
    assert max(cleanup_indices) < len(events) - 1

    # 3. For each step, pending event precedes resolved event with same stepId
    actor_events = [ev for ev in events if isinstance(ev.payload, ActorPayload)]
    # 6 steps * 2 (pending + resolved) = 12 actor events
    assert len(actor_events) == 12
    for i in range(0, 12, 2):
        p_act = actor_events[i].payload
        r_act = actor_events[i + 1].payload
        assert isinstance(p_act, ActorPayload)
        assert isinstance(r_act, ActorPayload)
        pending = p_act.step
        resolved = r_act.step
        assert pending.step_id == resolved.step_id
        assert pending.outcome is None
        assert resolved.outcome == Outcome.AS_EXPECTED


@pytest.mark.stage5
def test_active_cancellation_cleans_up_and_exits_130() -> None:
    """S5-03: Active cancellation reaps child process, cleans temp dir, and exits 130."""
    cancel_evt = threading.Event()

    def cancel_on_request_phase(ev: RunEvent) -> None:
        if ev.payload.type == "phase" and ev.payload.phase == "request":
            # Cancel during the request phase while child is actively running
            cancel_evt.set()

    with tempfile.TemporaryDirectory() as td:
        app_dir = Path(td) / "app"
        build_app("tests/fixtures/F2.trust", app_dir)
        prog = parse_file("tests/fixtures/F2.trust")

        res = run_attack_harness(
            program=prog,
            artifact_dir=app_dir,
            event_callback=cancel_on_request_phase,
            cancel_event=cancel_evt,
        )
        assert isinstance(res, RunFailure)
        assert res.exit_code == 130
        assert res.status == "cancelled"


@pytest.mark.stage5
def test_deadline_expiry_cleans_up_and_exits_124() -> None:
    """S5-03: Timeout deadline expiry produces exitCode 124 and cleans up."""
    with tempfile.TemporaryDirectory() as td:
        app_dir = Path(td) / "app"
        build_app("tests/fixtures/F2.trust", app_dir)
        prog = parse_file("tests/fixtures/F2.trust")

        res = run_attack_harness(
            program=prog,
            artifact_dir=app_dir,
            timeout_seconds=0.0001,  # immediate deadline expiry
        )
        assert isinstance(res, RunFailure)
        assert res.exit_code == 124
        assert res.status == "timed_out"


@pytest.mark.stage5
def test_startup_readiness_failure_cleans_up_and_exits_3() -> None:
    """S5-03: Application startup failure produces exitCode 3 and cleans up."""
    import httpx

    with tempfile.TemporaryDirectory() as td:
        app_dir = Path(td) / "app"
        build_app("tests/fixtures/F2.trust", app_dir)
        prog = parse_file("tests/fixtures/F2.trust")

        with patch("httpx.get", side_effect=httpx.ConnectError("Connection refused")):
            res = run_attack_harness(
                program=prog,
                artifact_dir=app_dir,
            )
            assert isinstance(res, RunFailure)
            assert res.exit_code == 3
            assert res.status == "error"
            assert res.error is not None
            err_code = res.error.get("code", "")
            assert "STARTUP_FAILED" in err_code or "EXECUTION_ERROR" in err_code


@pytest.mark.stage5
def test_cleanup_failure_reports_sanitized_error_exit_3() -> None:
    """S5-03: Cleanup failure overrides completed success with execution error exit 3."""
    with tempfile.TemporaryDirectory() as td:
        app_dir = Path(td) / "app"
        build_app("tests/fixtures/F2.trust", app_dir)
        prog = parse_file("tests/fixtures/F2.trust")

        with patch(
            "tempfile.TemporaryDirectory.cleanup", side_effect=PermissionError("Locked file")
        ):
            res = run_attack_harness(
                program=prog,
                artifact_dir=app_dir,
            )
            assert isinstance(res, RunFailure)
            assert res.exit_code == 3
            assert res.status == "error"
            assert res.error is not None
            assert res.error.get("code") == "CLEANUP_FAILED"
            assert "Locked file" in res.error.get("message", "")


@pytest.mark.stage5
def test_secret_and_token_redaction_in_attack_outputs() -> None:
    """Search serialized result and step details to verify zero secret or token leakage."""
    res = attack_spec("tests/fixtures/F2.trust", fmt="json")
    assert isinstance(res, AttackCompleted)

    serialized = res.model_dump_json(by_alias=True)
    # Ensure sensitive credentials never appear
    assert "password_hash" not in serialized or '"password_hash": null' in serialized
    assert "hash_user_1_secret_value" not in serialized
    assert "hash_user_2_secret_value" not in serialized
    assert DEFAULT_TEST_SECRET not in serialized


@pytest.mark.stage6
def test_s6_03_exact_response_projections_f2() -> None:
    """S6-03: Live attack on F2 verifies exact field sets on User and Trip responses."""
    res = attack_spec("tests/fixtures/F2.trust", fmt="json")
    assert isinstance(res, AttackCompleted)

    # Find owner GET /users/{id}
    user_step = next(s for s in res.steps if s.endpoint == "GET /users/{id}" and s.actor == "owner")
    proj_check_user = next(c for c in user_step.checks if c.name == "response_projection")
    assert proj_check_user.passed is True
    assert proj_check_user.expected == "exact fields: ['email', 'id']"
    assert proj_check_user.actual == "exact fields: ['email', 'id']"

    # Find owner GET /trips/{id}
    trip_step = next(s for s in res.steps if s.endpoint == "GET /trips/{id}" and s.actor == "owner")
    proj_check_trip = next(c for c in trip_step.checks if c.name == "response_projection")
    assert proj_check_trip.passed is True
    assert proj_check_trip.expected == "exact fields: ['destination', 'id', 'owner_id']"
    assert proj_check_trip.actual == "exact fields: ['destination', 'id', 'owner_id']"


@pytest.mark.stage6
def test_s6_03_response_projection_extra_and_missing_field_detection() -> None:
    """S6-03: Extra field or missing field in response causes projection check failure."""
    with tempfile.TemporaryDirectory() as td:
        app_dir = Path(td) / "app"
        build_app("tests/fixtures/F2.trust", app_dir)
        prog = parse_file("tests/fixtures/F2.trust")

        # 1. Deliberately extra harmless field
        def mock_get_extra(url: str, **kwargs: Any) -> httpx.Response:
            if "/users/" in url:
                return httpx.Response(
                    200,
                    json={
                        "id": "11111111-1111-1111-1111-111111111111",
                        "email": "test@example.com",
                        "harmless_extra": "leak",
                    },
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(
                200,
                json={
                    "id": "33333333-3333-3333-3333-333333333333",
                    "destination": "Paris",
                    "owner_id": "11111111-1111-1111-1111-111111111111",
                },
                request=httpx.Request("GET", url),
            )

        with patch("httpx.Client.get", side_effect=mock_get_extra):
            res_extra = run_attack_harness(prog, app_dir)
            assert isinstance(res_extra, AttackCompleted)
            assert res_extra.unexpected > 0
            user_step = next(
                s for s in res_extra.steps
                if s.endpoint == "GET /users/{id}" and s.actor == "owner"
            )
            assert user_step.outcome == Outcome.UNEXPECTED
            fail_check = next(c for c in user_step.checks if c.name == "response_projection")
            assert fail_check.passed is False
            assert "unexpected extra" in fail_check.actual

        # 2. Deliberately missing projected field
        def mock_get_missing(url: str, **kwargs: Any) -> httpx.Response:
            if "/users/" in url:
                return httpx.Response(
                    200,
                    json={"id": "11111111-1111-1111-1111-111111111111"},  # missing email!
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(
                200,
                json={
                    "id": "33333333-3333-3333-3333-333333333333",
                    "destination": "Paris",
                    "owner_id": "11111111-1111-1111-1111-111111111111",
                },
                request=httpx.Request("GET", url),
            )

        with patch("httpx.Client.get", side_effect=mock_get_missing):
            res_missing = run_attack_harness(prog, app_dir)
            assert isinstance(res_missing, AttackCompleted)
            assert res_missing.unexpected > 0
            user_step = next(
                s for s in res_missing.steps
                if s.endpoint == "GET /users/{id}" and s.actor == "owner"
            )
            assert user_step.outcome == Outcome.UNEXPECTED
            fail_check = next(c for c in user_step.checks if c.name == "response_projection")
            assert fail_check.passed is False
            assert "missing" in fail_check.actual


@pytest.mark.stage6
def test_s6_03_x13_cross_route_schema_isolation(tmp_path: Path) -> None:
    """S6-03: Route with narrow projection and broader projection maintain schema isolation."""
    x13_spec = """
resource User:
  fields:
    id: uuid
    email: string
    password_hash: string [sensitive]

resource Trip:
  fields:
    id: uuid
    destination: string
    owner_id: uuid -> User.id

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip [id, destination]

endpoint GET /trips:
  resource: Trip
  auth: required
  returns: Trip
"""
    spec_file = tmp_path / "x13.trust"
    spec_file.write_text(x13_spec.strip(), encoding="utf-8")
    app_dir = tmp_path / "x13_app"
    build_res = build_app(spec_file, app_dir)
    assert build_res.exit_code == 0

    schemas_py = (app_dir / "schemas.py").read_text(encoding="utf-8")
    # Must declare distinct response schemas
    assert "class TripResponse(" in schemas_py
    assert "class TripIdDestinationResponse(" in schemas_py
    # Password hash must not be present in any response schema
    assert "password_hash" not in schemas_py


@pytest.mark.stage6
def test_s6_03_permitted_sensitive_exposure_declaration_observation(tmp_path: Path) -> None:
    """S6-03: Permitted sensitive exposure via expose: records observed declaration observation."""
    spec_content = """
resource User:
  fields:
    id: uuid
    email: string
    ssn: string [sensitive]
    password_hash: string [sensitive]

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User [id, email, ssn]
  expose: [ssn]
"""
    spec_file = tmp_path / "sens.trust"
    spec_file.write_text(spec_content.strip(), encoding="utf-8")
    app_dir = tmp_path / "sens_app"
    build_res = build_app(spec_file, app_dir)
    assert build_res.exit_code == 0

    prog = parse_file(spec_file)
    res = run_attack_harness(prog, app_dir)
    assert isinstance(res, AttackCompleted)
    # Check that declarationObservations includes the permitted sensitive exposure declaration
    obs = [o for o in res.declaration_observations if o.state == "observed"]
    assert len(obs) > 0
