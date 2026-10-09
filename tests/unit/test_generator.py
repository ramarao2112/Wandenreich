"""Stage 4 — Generator and Build System Unit Tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trustc.cli import main as cli_main
from trustc.contracts import BuildSuccess, DeclarationKind
from trustc.generator import BuildError, build_app
from trustc.manifest import verify_manifest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
F1_PATH = FIXTURES_DIR / "F1.trust"
F2_PATH = FIXTURES_DIR / "F2.trust"
F3_PATH = FIXTURES_DIR / "F3.trust"
F4_PATH = FIXTURES_DIR / "F4.trust"


@pytest.mark.stage4
def test_build_f2_files_count_and_syntax(tmp_path: Path) -> None:
    """Build F2 and verify required files, 8 Python files, and valid manifest."""
    out_dir = tmp_path / "f2_app"
    result: BuildSuccess = build_app(F2_PATH, out_dir)

    assert result.exit_code == 0
    assert result.status == "completed"
    assert result.schema_version == 2
    # Verify all expected files are present
    assert (out_dir / "trustc-manifest.json").is_file()
    assert (out_dir / "trustc-report.json").is_file()
    assert (out_dir / "requirements.txt").is_file()
    assert (out_dir / "README.md").is_file()

    # Exactly 8 Python files
    py_files = [f for f in result.files if f.path.endswith(".py")]
    assert len(py_files) == 8

    expected_py_paths = {
        "db.py",
        "models.py",
        "schemas.py",
        "auth.py",
        "routers/__init__.py",
        "routers/trips.py",
        "routers/users.py",
        "main.py",
    }
    actual_py_paths = {f.path for f in py_files}
    assert actual_py_paths == expected_py_paths

    # Compile every generated python file
    for f in py_files:
        code = (out_dir / f.path).read_text(encoding="utf-8")
        compiled = compile(code, f.path, "exec")
        assert compiled is not None

    # Cryptographically verify the artifact manifest
    ok, reason = verify_manifest(out_dir)
    assert ok, f"Manifest verification failed: {reason}"

    # Check report JSON
    report_data = json.loads((out_dir / "trustc-report.json").read_text(encoding="utf-8"))
    assert report_data["schemaVersion"] == 2
    assert report_data["status"] == "completed"
    assert report_data["exitCode"] == 0
    assert report_data["buildId"] == result.build_id
    assert len(report_data["evidence"]["rules"]) == 5


@pytest.mark.stage4
def test_build_f2_provenance_and_forced_lines(tmp_path: Path) -> None:
    """Verify source provenance annotations and forced line mappings."""
    out_dir = tmp_path / "f2_app"
    result = build_app(F2_PATH, out_dir)

    trips_router = next(f for f in result.files if f.path == "routers/trips.py")
    assert any(forced.kind == "route" for forced in trips_router.forced)
    assert any(forced.kind == "auth" for forced in trips_router.forced)
    assert any(forced.kind == "owner-set" for forced in trips_router.forced)

    users_router = next(f for f in result.files if f.path == "routers/users.py")
    assert any(forced.kind == "self-check" for forced in users_router.forced)


@pytest.mark.stage4
def test_build_f1_refusal_leaves_dir_byte_identical(tmp_path: Path) -> None:
    """Building F1 must fail security verification (exit 1) and leave target untouched."""
    out_dir = tmp_path / "f1_target"
    out_dir.mkdir(parents=True, exist_ok=True)
    canary = out_dir / "canary.txt"
    canary.write_text("untouched sentinel data", encoding="utf-8")

    with pytest.raises(BuildError) as exc_info:
        build_app(F1_PATH, out_dir, replace=True)

    assert exc_info.value.exit_code == 1
    assert canary.read_text(encoding="utf-8") == "untouched sentinel data"
    assert len(list(out_dir.iterdir())) == 1


@pytest.mark.stage4
def test_build_f4_syntax_error_leaves_dir_byte_identical(tmp_path: Path) -> None:
    """Building F4 must fail syntax parsing (exit 2) and leave target untouched."""
    out_dir = tmp_path / "f4_target"
    out_dir.mkdir(parents=True, exist_ok=True)
    canary = out_dir / "canary.txt"
    canary.write_text("untouched sentinel data", encoding="utf-8")

    with pytest.raises(BuildError) as exc_info:
        build_app(F4_PATH, out_dir, replace=True)

    assert exc_info.value.exit_code == 2
    assert canary.read_text(encoding="utf-8") == "untouched sentinel data"
    assert len(list(out_dir.iterdir())) == 1


@pytest.mark.stage4
def test_destination_safety_and_replace_flow(tmp_path: Path) -> None:
    """Directory safety: refuse nonempty non-TrustC directories; require --replace for overwrite."""
    out_dir = tmp_path / "unsafe_dir"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "foreign.txt").write_text("do not overwrite me", encoding="utf-8")

    # 1. Non-empty non-TrustC directory refused even with replace=False
    with pytest.raises(BuildError) as exc_info:
        build_app(F2_PATH, out_dir, replace=False)
    assert exc_info.value.exit_code == 1
    assert "Refusing to overwrite nonempty non-TrustC directory" in str(exc_info.value)

    # Clean foreign file
    (out_dir / "foreign.txt").unlink()

    # 2. Build F2 into clean dir
    res1 = build_app(F2_PATH, out_dir)
    assert res1.exit_code == 0

    # 3. Overwrite without replace=True is refused
    with pytest.raises(BuildError) as exc_info:
        build_app(F2_PATH, out_dir, replace=False)
    assert exc_info.value.exit_code == 1
    assert "Use --replace to overwrite" in str(exc_info.value)

    # 4. Overwrite with replace=True succeeds
    res2 = build_app(F2_PATH, out_dir, replace=True)
    assert res2.exit_code == 0


@pytest.mark.stage4
def test_build_f3_waivers_and_put(tmp_path: Path) -> None:
    """Build F3 and verify waiver declarations and suffixed PUT route."""
    out_dir = tmp_path / "f3_app"
    result = build_app(F3_PATH, out_dir)
    assert result.exit_code == 0

    # Trips router must have update_trip_visibility
    trips_code = (out_dir / "routers" / "trips.py").read_text(encoding="utf-8")
    assert "update_trip_visibility" in trips_code
    assert "/visibility" in trips_code

    # Evidence has waiver declaration
    declarations = result.evidence.declarations
    waivers = [d for d in declarations if d.kind == DeclarationKind.OWNERSHIP_WAIVER]
    assert len(waivers) >= 1


@pytest.mark.stage4
def test_cli_build_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI build command assertions for F2 (exit 0), F1 (exit 1), and F4 (exit 2)."""
    # 1. F2 build exit 0
    f2_out = tmp_path / "cli_f2"
    ret = cli_main(["build", str(F2_PATH), "-o", str(f2_out), "--target=fastapi", "--format=json"])
    assert ret == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["status"] == "completed"
    assert data["exitCode"] == 0

    # 2. F1 build exit 1
    f1_out = tmp_path / "cli_f1"
    ret = cli_main(["build", str(F1_PATH), "-o", str(f1_out), "--format=json"])
    assert ret == 1
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["status"] == "refused"
    assert data["exitCode"] == 1

    # 3. F4 build exit 2
    f4_out = tmp_path / "cli_f4"
    ret = cli_main(["build", str(F4_PATH), "-o", str(f4_out), "--format=json"])
    assert ret == 2
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["status"] == "invalid_spec"
    assert data["exitCode"] == 2


@pytest.mark.stage4
def test_build_list_filtering_and_delete(tmp_path: Path) -> None:
    """Verify router generation for list filtering and delete operations."""
    spec_content = """resource User:
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

endpoint GET /trips:
  resource: Trip
  auth: required
  returns: Trip

endpoint DELETE /trips/{id}:
  resource: Trip
  auth: required
"""
    spec_file = tmp_path / "list_del.trust"
    spec_file.write_text(spec_content, encoding="utf-8")
    out_dir = tmp_path / "list_del_app"

    res = build_app(spec_file, out_dir)
    assert res.exit_code == 0

    trips_code = (out_dir / "routers" / "trips.py").read_text(encoding="utf-8")
    # List endpoint has owner filtering
    assert "async def list_trips" in trips_code
    assert "Trip.owner_id == current_user.id" in trips_code

    # Delete endpoint has 204 response
    assert "async def delete_trip" in trips_code
    assert "status.HTTP_204_NO_CONTENT" in trips_code


@pytest.mark.stage4
def test_build_patch_endpoint(tmp_path: Path) -> None:
    """Verify router and schema generation for PATCH operations."""
    spec_content = """resource User:
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

endpoint PATCH /trips/{id}:
  resource: Trip
  auth: required
  body: [destination]
  returns: Trip
"""
    spec_file = tmp_path / "patch.trust"
    spec_file.write_text(spec_content, encoding="utf-8")
    out_dir = tmp_path / "patch_app"

    res = build_app(spec_file, out_dir)
    assert res.exit_code == 0

    trips_code = (out_dir / "routers" / "trips.py").read_text(encoding="utf-8")
    assert "async def patch_trip" in trips_code

    schemas_code = (out_dir / "schemas.py").read_text(encoding="utf-8")
    assert "validate_non_empty_patch" in schemas_code


@pytest.mark.stage4
def test_s4_01_no_hardcoded_jwt_secret_in_generated_auth(tmp_path: Path) -> None:
    """S4-01: Verify generated auth.py has no fallback signing key and enforces >=32 bytes."""
    out_dir = tmp_path / "s4_01_app"
    build_app(F2_PATH, out_dir)

    auth_code = (out_dir / "auth.py").read_text(encoding="utf-8")
    # Assert no known fallback secret in source
    assert "trustc-ephemeral-default-secret-key" not in auth_code
    assert "os.environ.get(\"JWT_SECRET\", " not in auth_code
    assert 'os.environ.get("JWT_SECRET", ' not in auth_code
    assert 'len(_raw_jwt_secret.encode("utf-8")) < 32' in auth_code
    assert "Missing required environment secret 'JWT_SECRET'" in auth_code

    db_code = (out_dir / "db.py").read_text(encoding="utf-8")
    assert "sqlite+aiosqlite:///app.db" not in db_code
    assert "Missing required environment secret 'DB_URL'" in db_code


@pytest.mark.stage6
def test_s6_02_jwt_secret_byte_validation_and_whitespace_rejection(tmp_path: Path) -> None:
    """S6-02: Ensure auth.py validates exact bytes used and rejects whitespace-padded short keys."""
    out_dir = tmp_path / "s6_02_app"
    build_app(F2_PATH, out_dir)

    auth_code = (out_dir / "auth.py").read_text(encoding="utf-8")
    assert "_raw_jwt_secret != _raw_jwt_secret.strip()" in auth_code
    assert 'len(_raw_jwt_secret.encode("utf-8")) < 32' in auth_code
    assert "JWT_SECRET: str = _raw_jwt_secret" in auth_code

    python_exe = sys.executable
    clean_env = {k: v for k, v in os.environ.items() if k not in ("JWT_SECRET", "DB_URL")}
    clean_env["PYTHONPATH"] = str(out_dir.resolve())
    clean_env["DB_URL"] = "sqlite+aiosqlite:///:memory:"

    # 1. Padded-short key (31 spaces + 'x') -> must fail startup
    padded_env = dict(clean_env, JWT_SECRET=" " * 31 + "x")
    p_pad = subprocess.run(
        [python_exe, "-c", "import auth"],
        env=padded_env,
        capture_output=True,
        text=True,
    )
    assert p_pad.returncode != 0
    assert "must not contain leading or trailing whitespace" in p_pad.stderr

    # 2. Whitespace-only key -> must fail startup
    ws_env = dict(clean_env, JWT_SECRET="   ")
    p_ws = subprocess.run(
        [python_exe, "-c", "import auth"],
        env=ws_env,
        capture_output=True,
        text=True,
    )
    assert p_ws.returncode != 0

    # 3. Exactly 31-byte key -> must fail startup
    short_env = dict(clean_env, JWT_SECRET="a" * 31)
    p_short = subprocess.run(
        [python_exe, "-c", "import auth"],
        env=short_env,
        capture_output=True,
        text=True,
    )
    assert p_short.returncode != 0
    assert "must be at least 32 bytes for HS256 security" in p_short.stderr

    # 4. Valid 32-byte key -> must pass and preserve exact representation
    valid_key = "x" * 32
    valid_env = dict(clean_env, JWT_SECRET=valid_key)
    p_valid = subprocess.run(
        [python_exe, "-c", "import auth; assert auth.JWT_SECRET == 'x' * 32"],
        env=valid_env,
        capture_output=True,
        text=True,
    )
    assert p_valid.returncode == 0


@pytest.mark.stage4
def test_s4_02_spec_version_consistency_cli_and_api(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S4-02: Propagate one consistent spec revision through result, evidence, and report."""
    # API build with revision 0
    out_dir_0 = tmp_path / "app_rev_0"
    res_0 = build_app(F2_PATH, out_dir_0, spec_version=0)
    assert res_0.spec_version == 0
    assert res_0.evidence.spec_version == 0
    report_0 = json.loads((out_dir_0 / "trustc-report.json").read_text(encoding="utf-8"))
    assert report_0["specVersion"] == 0
    assert report_0["evidence"]["specVersion"] == 0

    # API build with revision 5
    out_dir_5 = tmp_path / "app_rev_5"
    res_5 = build_app(F2_PATH, out_dir_5, spec_version=5)
    assert res_5.spec_version == 5
    assert res_5.evidence.spec_version == 5
    report_5 = json.loads((out_dir_5 / "trustc-report.json").read_text(encoding="utf-8"))
    assert report_5["specVersion"] == 5
    assert report_5["evidence"]["specVersion"] == 5

    # CLI build with --revision 9
    out_dir_cli = tmp_path / "app_rev_cli"
    ret = cli_main([
        "build",
        str(F2_PATH),
        "-o",
        str(out_dir_cli),
        "--revision",
        "9",
        "--format=json",
    ])
    assert ret == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["specVersion"] == 9
    assert data["evidence"]["specVersion"] == 9


@pytest.mark.stage4
def test_s4_03_pinned_runtime_dependencies(tmp_path: Path) -> None:
    """S4-03: Generated requirements.txt must contain exact pinned versions."""
    out_dir = tmp_path / "s4_03_app"
    build_app(F2_PATH, out_dir)

    req_text = (out_dir / "requirements.txt").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in req_text.splitlines() if ln.strip() and not ln.startswith("#")]

    assert len(lines) >= 6
    # No range operators
    for line in lines:
        assert ">=" not in line, f"Found unpinned range '>=' in {line}"
        assert "<" not in line, f"Found unpinned range '<' in {line}"
        assert "==" in line, f"Dependency must be pinned with '==': {line}"

    assert any(line.startswith("fastapi==") for line in lines)
    assert any(line.startswith("sqlalchemy[asyncio]==") for line in lines)
    assert any(line.startswith("aiosqlite==") for line in lines)
    assert any(line.startswith("pyjwt==") for line in lines)


@pytest.mark.stage4
def test_s4_04_artifact_manifest_integrity_and_tamper_detection(tmp_path: Path) -> None:
    """S4-04: Manifest verifies pristine build, catches modifications and unmanifested files."""
    out_dir = tmp_path / "s4_04_app"
    build_app(F2_PATH, out_dir)

    # 1. Clean verification succeeds
    ok, msg = verify_manifest(out_dir)
    assert ok is True
    assert msg == "Manifest verified"

    # 2. Tampering with an executable file fails
    models_file = out_dir / "models.py"
    orig_bytes = models_file.read_bytes()
    models_file.write_bytes(orig_bytes + b"\n# tampered\n")
    ok, msg = verify_manifest(out_dir)
    assert ok is False
    assert "File SHA-256 mismatch" in msg or "Artifact digest mismatch" in msg

    # Restore
    models_file.write_bytes(orig_bytes)
    ok, _ = verify_manifest(out_dir)
    assert ok is True

    # 3. Adding an unexpected rogue file fails
    rogue_file = out_dir / "backdoor.py"
    rogue_file.write_text("print('pwned')", encoding="utf-8")
    ok, msg = verify_manifest(out_dir)
    assert ok is False
    assert "Unexpected unmanifested file" in msg


@pytest.mark.stage4
def test_s4_04_fault_injection_rollback_leaves_target_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S4-04: Publication failure safely rolls back and leaves existing build byte-identical."""
    import shutil
    out_dir = tmp_path / "rollback_app"

    # Step 1: Initial valid build
    build_app(F2_PATH, out_dir)
    initial_files = {p: p.read_bytes() for p in out_dir.rglob("*") if p.is_file()}

    # Step 2: Fault injection during replace publication
    def failing_copytree(*args, **kwargs):
        raise OSError("Simulated disk write failure during publication")

    monkeypatch.setattr(shutil, "copytree", failing_copytree)

    with pytest.raises(OSError, match="Simulated disk write failure"):
        build_app(F2_PATH, out_dir, replace=True)

    # Step 3: Assert destination is byte-identical to initial build
    current_files = {p: p.read_bytes() for p in out_dir.rglob("*") if p.is_file()}
    assert current_files == initial_files


@pytest.mark.stage4
def test_s4_05_user_lookup_404_before_403_in_generated_code(tmp_path: Path) -> None:
    """S4-05: User lookup queries DB, returns 404 if absent, then 403 if not self."""
    out_dir = tmp_path / "s4_05_app"
    build_app(F2_PATH, out_dir)

    users_code = (out_dir / "routers" / "users.py").read_text(encoding="utf-8")
    # Verify DB query occurs before authorization check
    assert "select(User).where(User.id == id)" in users_code
    assert "status.HTTP_404_NOT_FOUND" in users_code
    assert "current_user.id != id" in users_code
    assert "status.HTTP_403_FORBIDDEN" in users_code
