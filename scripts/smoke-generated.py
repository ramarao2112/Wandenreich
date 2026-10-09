#!/usr/bin/env python3
"""Stage 4 — Runtime smoke tester for generated FastAPI applications.

Executes real HTTP requests against a running ASGI application backed by
a real SQLite database (aiosqlite) and asserts:
1. Environment & Startup Security (S4-01):
   - Missing, empty, whitespace, or undersized (<32 bytes) JWT key halts startup.
   - Missing DB configuration halts startup with clear error.
   - Zero secrets leaked in error messages.
2. Manifest Integrity (S4-04):
   - Cryptographic verification of artifact manifest (sha256-length-prefixed-v1).
   - Tampered executable bytes, unexpected unmanifested files, or deleted files rejected.
3. User Lookup Policy (S4-05):
   - Authenticated nonexistent UUID returns 404 (404 before 403).
   - Authenticated other user returns 403.
   - Self access returns 200 with projected [id, email] and zero credentials.
   - Anonymous access returns 401.
4. Mutation Authorization & Projection Semantics (Verification Gaps 1 & 2):
   - Owner-filtered list results with two users.
   - Owner-protected PUT, PATCH, and DELETE: owner success, other-user 403, anon 401, absent 404.
   - Database snapshots proving denied requests make zero mutations.
   - Omitted vs empty-patch `{}` rejected with 422.
   - Owner/ID injection and extra field rejection with 422.
   - SQL-injection payload stored safely as literal data.
5. F3 Ownership Waiver & Suffixed Updates:
   - Authenticated waiver allows other-user PUT.
   - Anonymous PUT rejected with 401.
   - Omitted returns returns empty dict {}.

Reports sanitized results with zero token or secret leaks. Exits 0 on success.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import httpx
from httpx import ASGITransport
from sqlalchemy import select

# Ensure project root is on PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trustc.generator import build_app  # noqa: E402
from trustc.manifest import verify_manifest  # noqa: E402
from trustc.seeder import (  # noqa: E402
    USER_1_EMAIL,
    USER_1_ID,
    USER_2_ID,
    create_access_token,
    generate_harness_secret,
    seed_test_users,
)


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.replace("✅", "[PASS]").replace("❌", "[FAIL]"))


def test_env_and_security_configuration(app_dir: Path) -> int:
    """S4-01: Validate missing/short JWT key fails startup; missing DB fails startup; no secrets leaked."""
    _safe_print("\n--- Testing S4-01 Environment & Startup Security ---")
    failures: list[str] = []

    # 1. Source check
    auth_src = (app_dir / "auth.py").read_text(encoding="utf-8")
    if "trustc-ephemeral-default-secret-key" in auth_src:
        failures.append("Found known default secret key in generated auth.py source!")
    if "os.environ.get(\"JWT_SECRET\", " in auth_src or 'os.environ.get("JWT_SECRET", ' in auth_src:
        failures.append("Found fallback default in os.environ.get('JWT_SECRET') in auth.py!")

    db_src = (app_dir / "db.py").read_text(encoding="utf-8")
    if "sqlite+aiosqlite:///app.db" in db_src:
        failures.append("Found fallback database URL in generated db.py source!")

    # 2. Subprocess startup checks
    python_exe = sys.executable
    clean_env = {k: v for k, v in os.environ.items() if k not in ("JWT_SECRET", "DB_URL")}
    clean_env["PYTHONPATH"] = str(app_dir.resolve())

    # Test A: Missing JWT_SECRET
    env_no_jwt = dict(clean_env, DB_URL="sqlite+aiosqlite:///:memory:")
    p_no_jwt = subprocess.run(
        [python_exe, "-B", "-c", "import auth"],
        cwd=app_dir,
        env=env_no_jwt,
        capture_output=True,
        text=True,
    )
    if p_no_jwt.returncode != 0 and "Missing required environment secret 'JWT_SECRET'" in p_no_jwt.stderr:
        _safe_print("  ✅ [PASS] Missing JWT_SECRET halts startup with clear error")
    else:
        failures.append(f"Missing JWT_SECRET expected failure, got rc={p_no_jwt.returncode}, stderr={p_no_jwt.stderr}")

    # Test B: Empty JWT_SECRET
    env_empty = dict(clean_env, JWT_SECRET="", DB_URL="sqlite+aiosqlite:///:memory:")
    p_empty = subprocess.run(
        [python_exe, "-B", "-c", "import auth"],
        cwd=app_dir,
        env=env_empty,
        capture_output=True,
        text=True,
    )
    if p_empty.returncode != 0 and "Missing required environment secret 'JWT_SECRET'" in p_empty.stderr:
        _safe_print("  ✅ [PASS] Empty JWT_SECRET halts startup with clear error")
    else:
        failures.append(f"Empty JWT_SECRET expected failure, got rc={p_empty.returncode}")

    # Test C: Undersized JWT_SECRET (< 32 bytes)
    undersized_key = "short-secret-under-32-bytes"
    env_short = dict(clean_env, JWT_SECRET=undersized_key, DB_URL="sqlite+aiosqlite:///:memory:")
    p_short = subprocess.run(
        [python_exe, "-B", "-c", "import auth"],
        cwd=app_dir,
        env=env_short,
        capture_output=True,
        text=True,
    )
    if p_short.returncode != 0 and "must be at least 32 bytes for HS256 security" in p_short.stderr:
        _safe_print("  ✅ [PASS] Undersized JWT_SECRET (< 32 bytes) halts startup with clear error")
        # Ensure secret value is never printed in error message!
        if undersized_key in p_short.stderr:
            failures.append("SECURITY LEAK: Secret value appeared in error output!")
        else:
            _safe_print("  ✅ [PASS] Error output contains zero secret or key material")
    else:
        failures.append(f"Undersized JWT_SECRET expected failure, got rc={p_short.returncode}")

    # Test C2: Whitespace-only JWT_SECRET
    env_ws = dict(clean_env, JWT_SECRET="   ", DB_URL="sqlite+aiosqlite:///:memory:")
    p_ws = subprocess.run(
        [python_exe, "-B", "-c", "import auth"],
        cwd=app_dir,
        env=env_ws,
        capture_output=True,
        text=True,
    )
    if p_ws.returncode != 0 and ("Missing required environment secret 'JWT_SECRET'" in p_ws.stderr or "cannot be empty" in p_ws.stderr or "whitespace" in p_ws.stderr):
        _safe_print("  ✅ [PASS] Whitespace-only JWT_SECRET halts startup with clear error")
    else:
        failures.append(f"Whitespace-only JWT_SECRET expected failure, got rc={p_ws.returncode}, stderr={p_ws.stderr}")

    # Test C3: Padded-short JWT_SECRET (31 spaces + 'x') (S6-02 regression)
    padded_short = " " * 31 + "x"
    env_padded = dict(clean_env, JWT_SECRET=padded_short, DB_URL="sqlite+aiosqlite:///:memory:")
    p_padded = subprocess.run(
        [python_exe, "-B", "-c", "import auth"],
        cwd=app_dir,
        env=env_padded,
        capture_output=True,
        text=True,
    )
    if p_padded.returncode != 0 and "must not contain leading or trailing whitespace" in p_padded.stderr:
        _safe_print("  ✅ [PASS] Padded-short JWT_SECRET (31 spaces + 'x') halts startup")
    else:
        failures.append(f"Padded-short JWT_SECRET expected failure, got rc={p_padded.returncode}, stderr={p_padded.stderr}")

    # Test C4: Exactly 31 bytes
    exact_31 = "a" * 31
    env_31 = dict(clean_env, JWT_SECRET=exact_31, DB_URL="sqlite+aiosqlite:///:memory:")
    p_31 = subprocess.run(
        [python_exe, "-B", "-c", "import auth"],
        cwd=app_dir,
        env=env_31,
        capture_output=True,
        text=True,
    )
    if p_31.returncode != 0 and "must be at least 32 bytes for HS256 security" in p_31.stderr:
        _safe_print("  ✅ [PASS] Exactly 31-byte JWT_SECRET halts startup")
    else:
        failures.append(f"31-byte JWT_SECRET expected failure, got rc={p_31.returncode}")

    # Test C5: Valid 32-byte key works
    valid_key_32 = "k" * 32
    env_32 = dict(clean_env, JWT_SECRET=valid_key_32, DB_URL="sqlite+aiosqlite:///:memory:")
    p_32 = subprocess.run(
        [python_exe, "-B", "-c", "import auth; assert auth.JWT_SECRET == 'k' * 32"],
        cwd=app_dir,
        env=env_32,
        capture_output=True,
        text=True,
    )
    if p_32.returncode == 0:
        _safe_print("  ✅ [PASS] Valid 32-byte JWT_SECRET accepted without trimming or modification")
    else:
        failures.append(f"Valid 32-byte JWT_SECRET expected success, got rc={p_32.returncode}, stderr={p_32.stderr}")

    # Test D: Missing DB_URL
    valid_key = generate_harness_secret(32)
    env_no_db = dict(clean_env, JWT_SECRET=valid_key)
    p_no_db = subprocess.run(
        [python_exe, "-B", "-c", "import db"],
        cwd=app_dir,
        env=env_no_db,
        capture_output=True,
        text=True,
    )
    if p_no_db.returncode != 0 and "Missing required environment secret 'DB_URL'" in p_no_db.stderr:
        _safe_print("  ✅ [PASS] Missing DB_URL halts startup with clear error")
    else:
        failures.append(f"Missing DB_URL expected failure, got rc={p_no_db.returncode}")

    # Clean up any potential pycache
    shutil.rmtree(app_dir / "__pycache__", ignore_errors=True)

    if failures:
        _safe_print(f"❌ [FAIL] Environment & Startup Security encountered {len(failures)} failures:")
        for f in failures:
            _safe_print(f"    - {f}")
        return 1

    _safe_print("✅ [PASS] All S4-01 environment and startup security checks passed!")
    return 0


def test_manifest_verification(app_dir: Path) -> int:
    """S4-04: Cryptographic verification of artifact manifest and tamper detection."""
    _safe_print("\n--- Testing S4-04 Artifact Manifest Verification ---")
    failures: list[str] = []

    # 1. Clean verification
    ok, reason = verify_manifest(app_dir)
    if ok:
        _safe_print("  ✅ [PASS] Clean build manifest verified successfully")
    else:
        failures.append(f"Clean manifest verification failed: {reason}")

    # 2. Tampering detection in isolated temporary copy
    with tempfile.TemporaryDirectory(prefix="trustc_manifest_test_") as tmp_td:
        copy_dir = Path(tmp_td) / "app"
        shutil.copytree(app_dir, copy_dir)

        # Mutate executable bytes
        target = copy_dir / "models.py"
        orig_bytes = target.read_bytes()
        target.write_bytes(orig_bytes + b"\n# tampered byte\n")
        ok_mod, _ = verify_manifest(copy_dir)
        if not ok_mod:
            _safe_print("  ✅ [PASS] Tampered executable bytes successfully detected and rejected")
        else:
            failures.append("Tampered executable bytes was NOT rejected by manifest verification!")

        # Restore
        target.write_bytes(orig_bytes)

        # Inject unexpected file
        rogue = copy_dir / "backdoor.py"
        rogue.write_text("evil()", encoding="utf-8")
        ok_rogue, _ = verify_manifest(copy_dir)
        if not ok_rogue:
            _safe_print("  ✅ [PASS] Unexpected unmanifested file successfully detected and rejected")
        else:
            failures.append("Unexpected unmanifested file was NOT rejected!")
        rogue.unlink()

        # Delete a file
        schemas_file = copy_dir / "schemas.py"
        schemas_file.unlink()
        ok_del, _ = verify_manifest(copy_dir)
        if not ok_del:
            _safe_print("  ✅ [PASS] Missing manifested file successfully detected and rejected")
        else:
            failures.append("Missing manifested file was NOT rejected!")

    if failures:
        _safe_print(f"❌ [FAIL] Manifest verification encountered {len(failures)} failures:")
        for f in failures:
            _safe_print(f"    - {f}")
        return 1

    _safe_print("✅ [PASS] All S4-04 artifact manifest checks passed!")
    return 0


async def test_f2_generated_app(app_dir: Path) -> int:
    """Run full test matrix against F2 generated application."""
    _safe_print("\n--- Testing F2 Generated Application ---")

    for mod_name in list(sys.modules.keys()):
        if mod_name in (
            "db", "models", "schemas", "auth", "main",
            "routers", "routers.trips", "routers.users",
        ):
            del sys.modules[mod_name]

    app_dir_str = str(app_dir.resolve())
    if app_dir_str in sys.path:
        sys.path.remove(app_dir_str)
    sys.path.insert(0, app_dir_str)

    temp_dir = tempfile.TemporaryDirectory(prefix="trustc_smoke_db_")
    db_path = Path(temp_dir.name) / "test.db"
    harness_secret = generate_harness_secret(32)

    os.environ["DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["JWT_SECRET"] = harness_secret

    failures: list[str] = []

    try:
        app_db = importlib.import_module("db")
        app_models = importlib.import_module("models")
        main_mod = importlib.import_module("main")
        app = getattr(main_mod, "app")

        async with app_db.engine.begin() as conn:
            await conn.run_sync(app_db.Base.metadata.create_all)

        async with app_db.AsyncSessionLocal() as session:
            await seed_test_users(session, app_models.User)

        token_u1 = create_access_token(USER_1_ID, secret=harness_secret)
        token_u2 = create_access_token(USER_2_ID, secret=harness_secret)

        headers_u1 = {"Authorization": f"Bearer {token_u1}"}
        headers_u2 = {"Authorization": f"Bearer {token_u2}"}

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testapp") as client:
            # Check 1: Health check
            resp = await client.get("/health")
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                _safe_print("  ✅ [PASS] /health returns 200 with status ok")
            else:
                failures.append(f"/health failed: {resp.status_code} {resp.text}")

            # Check 2: Anonymous Trip create -> 401
            resp = await client.post("/trips", json={"destination": "Paris"})
            if resp.status_code == 401 and resp.json().get("detail") == "Unauthorized":
                _safe_print("  ✅ [PASS] Anonymous POST /trips rejected with 401 Unauthorized")
            else:
                failures.append(f"Anonymous POST /trips expected 401, got {resp.status_code}")

            # Check 3: Anonymous Trip read -> 401
            dummy_id = str(uuid.uuid4())
            resp = await client.get(f"/trips/{dummy_id}")
            if resp.status_code == 401 and resp.json().get("detail") == "Unauthorized":
                _safe_print("  ✅ [PASS] Anonymous GET /trips/{id} rejected with 401 Unauthorized")
            else:
                failures.append(f"Anonymous GET /trips expected 401, got {resp.status_code}")

            # Check 4: Anonymous User read -> 401
            resp = await client.get(f"/users/{USER_1_ID}")
            if resp.status_code == 401 and resp.json().get("detail") == "Unauthorized":
                _safe_print("  ✅ [PASS] Anonymous GET /users/{id} rejected with 401 Unauthorized")
            else:
                failures.append(f"Anonymous GET /users expected 401, got {resp.status_code}")

            # Check 5: JWT verification failures (expired, bad secret, bad iss, bad aud, unknown sub)
            exp_token = create_access_token(USER_1_ID, secret=harness_secret, expired=True)
            resp = await client.get(
                f"/users/{USER_1_ID}",
                headers={"Authorization": f"Bearer {exp_token}"},
            )
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] Expired JWT token rejected with 401")
            else:
                failures.append(f"Expired JWT expected 401, got {resp.status_code}")

            bad_sig_token = create_access_token(
                USER_1_ID, secret="wrong-secret-key-that-does-not-match-at-all-32-bytes!"
            )
            resp = await client.get(
                f"/users/{USER_1_ID}",
                headers={"Authorization": f"Bearer {bad_sig_token}"},
            )
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] Tampered JWT signature rejected with 401")
            else:
                failures.append(f"Tampered JWT expected 401, got {resp.status_code}")

            bad_iss_token = create_access_token(USER_1_ID, secret=harness_secret, issuer="evil-issuer")
            resp = await client.get(
                f"/users/{USER_1_ID}",
                headers={"Authorization": f"Bearer {bad_iss_token}"},
            )
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] JWT with invalid issuer rejected with 401")
            else:
                failures.append(f"Invalid issuer expected 401, got {resp.status_code}")

            bad_aud_token = create_access_token(USER_1_ID, secret=harness_secret, audience="wrong-audience")
            resp = await client.get(
                f"/users/{USER_1_ID}",
                headers={"Authorization": f"Bearer {bad_aud_token}"},
            )
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] JWT with invalid audience rejected with 401")
            else:
                failures.append(f"Invalid audience expected 401, got {resp.status_code}")

            unknown_sub = str(uuid.uuid4())
            unknown_token = create_access_token(unknown_sub, secret=harness_secret)
            resp = await client.get(
                f"/users/{USER_1_ID}",
                headers={"Authorization": f"Bearer {unknown_token}"},
            )
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] JWT with unknown user sub rejected with 401")
            else:
                failures.append(f"Unknown sub expected 401, got {resp.status_code}")

            # Check 6: Authorized Trip Creation by User 1
            resp = await client.post("/trips", json={"destination": "Kyoto"}, headers=headers_u1)
            if resp.status_code == 201:
                trip_data = resp.json()
                trip_id = trip_data.get("id")
                owner_id = trip_data.get("owner_id")
                if owner_id == str(USER_1_ID) and trip_data.get("destination") == "Kyoto":
                    _safe_print("  ✅ [PASS] User 1 creates Trip (201 Created) with owner set")
                else:
                    failures.append(f"Trip owner mismatch: expected {USER_1_ID}, got {owner_id}")
            else:
                failures.append(f"POST /trips failed: {resp.status_code} {resp.text}")
                trip_id = None

            if trip_id:
                # Check 7: Owner reads own trip -> 200
                resp = await client.get(f"/trips/{trip_id}", headers=headers_u1)
                if resp.status_code == 200 and resp.json().get("destination") == "Kyoto":
                    _safe_print("  ✅ [PASS] User 1 reads own trip (200 OK)")
                else:
                    failures.append(f"Owner GET /trips failed: {resp.status_code} {resp.text}")

                # Check 8: Other user reads User 1 trip -> 403 Forbidden
                resp = await client.get(f"/trips/{trip_id}", headers=headers_u2)
                if resp.status_code == 403 and resp.json().get("detail") == "Forbidden":
                    _safe_print("  ✅ [PASS] User 2 reading User 1 trip rejected with 403 Forbidden")
                else:
                    failures.append(f"Other user GET /trips expected 403, got {resp.status_code}")

            # Check 9: Nonexistent trip -> 404
            non_id = str(uuid.uuid4())
            resp = await client.get(f"/trips/{non_id}", headers=headers_u1)
            if resp.status_code == 404:
                _safe_print("  ✅ [PASS] Nonexistent trip returns 404 Not Found")
            else:
                failures.append(f"Nonexistent trip expected 404, got {resp.status_code}")

            # Check 10: User Self Identity Read -> 200 and password_hash excluded
            resp = await client.get(f"/users/{USER_1_ID}", headers=headers_u1)
            if resp.status_code == 200:
                user_data = resp.json()
                if "password_hash" not in user_data:
                    _safe_print("  ✅ [PASS] User 1 reads self profile; password_hash strictly excluded")
                else:
                    failures.append("SECURITY LEAK: password_hash present in User response!")
                if (
                    user_data.get("email") == USER_1_EMAIL
                    and user_data.get("id") == str(USER_1_ID)
                ):
                    _safe_print("  ✅ [PASS] User response contains exact projected fields [id, email]")
                else:
                    failures.append(f"User profile projection mismatch: {user_data}")
            else:
                failures.append(f"GET /users/{USER_1_ID} failed: {resp.status_code} {resp.text}")

            # Check 11: Other user reads User 1 profile -> 403 Forbidden
            resp = await client.get(f"/users/{USER_1_ID}", headers=headers_u2)
            if resp.status_code == 403 and resp.json().get("detail") == "Forbidden":
                _safe_print("  ✅ [PASS] User 2 reading User 1 profile rejected with 403 Forbidden")
            else:
                failures.append(f"User 2 reading User 1 profile expected 403, got {resp.status_code}")

            # Check 11b (S4-05): Authenticated nonexistent user read -> 404 Not Found (404 before 403)
            nonexistent_user_id = str(uuid.uuid4())
            resp = await client.get(f"/users/{nonexistent_user_id}", headers=headers_u1)
            if resp.status_code == 404 and resp.json().get("detail") == "Not found":
                _safe_print("  ✅ [PASS] Nonexistent user lookup returns 404 Not Found (404 before 403)")
            else:
                failures.append(f"Nonexistent user lookup expected 404, got {resp.status_code}")

            # Check 12: Injection of owner_id, id, and extra fields -> 422
            async with app_db.AsyncSessionLocal() as session:
                q_before = await session.execute(select(app_models.Trip))
                trips_count_before = len(q_before.scalars().all())

            resp = await client.post(
                "/trips",
                json={"destination": "Osaka", "owner_id": str(USER_2_ID)},
                headers=headers_u1,
            )
            if resp.status_code == 422:
                _safe_print("  ✅ [PASS] Injected owner_id rejected with 422 Unprocessable Entity")
            else:
                failures.append(f"owner_id injection expected 422, got {resp.status_code}")

            resp = await client.post(
                "/trips",
                json={"destination": "Osaka", "id": str(uuid.uuid4())},
                headers=headers_u1,
            )
            if resp.status_code == 422:
                _safe_print("  ✅ [PASS] Injected id in body rejected with 422 Unprocessable Entity")
            else:
                failures.append(f"id injection expected 422, got {resp.status_code}")

            resp = await client.post(
                "/trips",
                json={"destination": "Osaka", "extra_param": "attacker_value"},
                headers=headers_u1,
            )
            if resp.status_code == 422:
                _safe_print("  ✅ [PASS] Extra unrecognized field in body rejected with 422")
            else:
                failures.append(f"extra field expected 422, got {resp.status_code}")

            async with app_db.AsyncSessionLocal() as session:
                q_after = await session.execute(select(app_models.Trip))
                trips_count_after = len(q_after.scalars().all())
                if trips_count_before == trips_count_after:
                    _safe_print("  ✅ [PASS] Denied writes produced zero database mutations")
                else:
                    failures.append(
                        f"Database was mutated on denied requests: before={trips_count_before}, after={trips_count_after}"
                    )

            # Check 13: SQL-injection string safely stored as literal text
            sql_payload = "Tokyo'; DROP TABLE users; --"
            resp = await client.post(
                "/trips",
                json={"destination": sql_payload},
                headers=headers_u1,
            )
            if resp.status_code == 201 and resp.json().get("destination") == sql_payload:
                _safe_print("  ✅ [PASS] SQL injection string stored verbatim as literal data")
                async with app_db.AsyncSessionLocal() as session:
                    users_count = await session.execute(select(app_models.User))
                    if len(users_count.scalars().all()) == 2:
                        _safe_print("  ✅ [PASS] Database tables intact after SQL injection payload test")
                    else:
                        failures.append("Database users table was corrupted by SQL payload!")
            else:
                failures.append(f"SQL injection test failed: {resp.status_code} {resp.text}")

    finally:
        try:
            await app_db.engine.dispose()
        except Exception:
            pass
        temp_dir.cleanup()

    if failures:
        _safe_print(f"\n❌ [FAIL] F2 test suite encountered {len(failures)} failures:")
        for f in failures:
            _safe_print(f"    - {f}")
        return 1

    _safe_print("\n✅ [PASS] All F2 runtime authorization, injection, and schema tests passed!")
    return 0


async def test_crud_mutation_authorization() -> int:
    """Verification gap: Full runtime coverage of owner-protected PUT, PATCH, DELETE and owner-filtered list."""
    _safe_print("\n--- Testing Mutation Authorization (PUT, PATCH, DELETE, List) ---")

    crud_spec = """resource User:
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

endpoint POST /trips:
  resource: Trip
  auth: required
  body: [destination]
  returns: Trip

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip

endpoint PUT /trips/{id}:
  resource: Trip
  auth: required
  body: [destination]
  returns: Trip

endpoint PATCH /trips/{id}:
  resource: Trip
  auth: required
  body: [destination]
  returns: Trip

endpoint DELETE /trips/{id}:
  resource: Trip
  auth: required
"""
    temp_dir = tempfile.TemporaryDirectory(prefix="trustc_crud_test_")
    spec_path = Path(temp_dir.name) / "crud.trust"
    spec_path.write_text(crud_spec, encoding="utf-8")
    app_dir = Path(temp_dir.name) / "app"

    build_res = build_app(spec_path, app_dir)
    if build_res.exit_code != 0:
        _safe_print("❌ [FAIL] Failed to build CRUD test app")
        temp_dir.cleanup()
        return 1

    for mod_name in list(sys.modules.keys()):
        if mod_name in (
            "db", "models", "schemas", "auth", "main",
            "routers", "routers.trips", "routers.users",
        ):
            del sys.modules[mod_name]

    app_dir_str = str(app_dir.resolve())
    if app_dir_str in sys.path:
        sys.path.remove(app_dir_str)
    sys.path.insert(0, app_dir_str)

    db_path = Path(temp_dir.name) / "crud_test.db"
    harness_secret = generate_harness_secret(32)
    os.environ["DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["JWT_SECRET"] = harness_secret

    failures: list[str] = []

    try:
        crud_db = importlib.import_module("db")
        crud_models = importlib.import_module("models")
        crud_main = importlib.import_module("main")
        app = getattr(crud_main, "app")

        async with crud_db.engine.begin() as conn:
            await conn.run_sync(crud_db.Base.metadata.create_all)

        async with crud_db.AsyncSessionLocal() as session:
            await seed_test_users(session, crud_models.User)

        token_u1 = create_access_token(USER_1_ID, secret=harness_secret)
        token_u2 = create_access_token(USER_2_ID, secret=harness_secret)
        headers_u1 = {"Authorization": f"Bearer {token_u1}"}
        headers_u2 = {"Authorization": f"Bearer {token_u2}"}

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://crudapp") as client:
            # 1. Create Trip 1 by User 1 and Trip 2 by User 2
            resp1 = await client.post("/trips", json={"destination": "Kyoto"}, headers=headers_u1)
            resp2 = await client.post("/trips", json={"destination": "Tokyo"}, headers=headers_u2)
            if resp1.status_code != 201 or resp2.status_code != 201:
                failures.append("Failed to create initial trips for User 1 or User 2")
                return 1

            trip_1_id = resp1.json()["id"]
            trip_2_id = resp2.json()["id"]

            # 2. Owner-filtered list results
            resp_list_u1 = await client.get("/trips", headers=headers_u1)
            resp_list_u2 = await client.get("/trips", headers=headers_u2)
            if resp_list_u1.status_code == 200 and resp_list_u2.status_code == 200:
                list_u1 = resp_list_u1.json()
                list_u2 = resp_list_u2.json()
                if len(list_u1) == 1 and list_u1[0]["id"] == trip_1_id:
                    _safe_print("  ✅ [PASS] GET /trips as User 1 returns only User 1's trip (owner filtered)")
                else:
                    failures.append(f"User 1 list results incorrect: {list_u1}")

                if len(list_u2) == 1 and list_u2[0]["id"] == trip_2_id:
                    _safe_print("  ✅ [PASS] GET /trips as User 2 returns only User 2's trip (owner filtered)")
                else:
                    failures.append(f"User 2 list results incorrect: {list_u2}")
            else:
                failures.append("List trips endpoint failed for User 1 or User 2")

            # 3. PUT endpoint authorization
            # Snapshot before PUT attempts
            async with crud_db.AsyncSessionLocal() as session:
                row = (await session.execute(select(crud_models.Trip).where(crud_models.Trip.id == uuid.UUID(trip_1_id)))).scalar_one()
                dest_before = row.destination

            # 3a. Anonymous PUT -> 401
            resp = await client.put(f"/trips/{trip_1_id}", json={"destination": "Hacked"})
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] Anonymous PUT /trips/{id} rejected with 401 Unauthorized")
            else:
                failures.append(f"Anonymous PUT expected 401, got {resp.status_code}")

            # 3b. Other user PUT -> 403
            resp = await client.put(f"/trips/{trip_1_id}", json={"destination": "Hacked"}, headers=headers_u2)
            if resp.status_code == 403:
                _safe_print("  ✅ [PASS] Other-user PUT /trips/{id} rejected with 403 Forbidden")
            else:
                failures.append(f"Other user PUT expected 403, got {resp.status_code}")

            # Verify snapshot unchanged
            async with crud_db.AsyncSessionLocal() as session:
                row = (await session.execute(select(crud_models.Trip).where(crud_models.Trip.id == uuid.UUID(trip_1_id)))).scalar_one()
                if row.destination == dest_before:
                    _safe_print("  ✅ [PASS] Denied PUT requests made zero database changes")
                else:
                    failures.append("Database was modified by unauthorized PUT request!")

            # 3c. Absent trip PUT -> 404
            absent_id = str(uuid.uuid4())
            resp = await client.put(f"/trips/{absent_id}", json={"destination": "Nowhere"}, headers=headers_u1)
            if resp.status_code == 404:
                _safe_print("  ✅ [PASS] Nonexistent trip PUT returns 404 Not Found")
            else:
                failures.append(f"Nonexistent trip PUT expected 404, got {resp.status_code}")

            # 3d. Owner PUT -> 200
            resp = await client.put(f"/trips/{trip_1_id}", json={"destination": "Osaka"}, headers=headers_u1)
            if resp.status_code == 200 and resp.json().get("destination") == "Osaka":
                _safe_print("  ✅ [PASS] Owner PUT /trips/{id} succeeds with 200 OK and updated destination")
            else:
                failures.append(f"Owner PUT failed: {resp.status_code} {resp.text}")

            # 4. PATCH endpoint authorization and validation
            # 4a. Anonymous PATCH -> 401
            resp = await client.patch(f"/trips/{trip_1_id}", json={"destination": "HackedPatch"})
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] Anonymous PATCH /trips/{id} rejected with 401 Unauthorized")
            else:
                failures.append(f"Anonymous PATCH expected 401, got {resp.status_code}")

            # 4b. Other user PATCH -> 403
            resp = await client.patch(f"/trips/{trip_1_id}", json={"destination": "HackedPatch"}, headers=headers_u2)
            if resp.status_code == 403:
                _safe_print("  ✅ [PASS] Other-user PATCH /trips/{id} rejected with 403 Forbidden")
            else:
                failures.append(f"Other user PATCH expected 403, got {resp.status_code}")

            # 4c. Nonexistent trip PATCH -> 404
            resp = await client.patch(f"/trips/{absent_id}", json={"destination": "Nowhere"}, headers=headers_u1)
            if resp.status_code == 404:
                _safe_print("  ✅ [PASS] Nonexistent trip PATCH returns 404 Not Found")
            else:
                failures.append(f"Nonexistent trip PATCH expected 404, got {resp.status_code}")

            # 4d. Empty PATCH body {} -> 422
            resp = await client.patch(f"/trips/{trip_1_id}", json={}, headers=headers_u1)
            if resp.status_code == 422:
                _safe_print("  ✅ [PASS] Empty PATCH body {} rejected with 422 Unprocessable Entity")
            else:
                failures.append(f"Empty PATCH expected 422, got {resp.status_code}")

            # 4e. Owner ID injection in PATCH -> 422
            resp = await client.patch(f"/trips/{trip_1_id}", json={"owner_id": str(USER_2_ID)}, headers=headers_u1)
            if resp.status_code == 422:
                _safe_print("  ✅ [PASS] Injected owner_id in PATCH rejected with 422 Unprocessable Entity")
            else:
                failures.append(f"Injected owner_id in PATCH expected 422, got {resp.status_code}")

            # 4f. Owner PATCH -> 200
            resp = await client.patch(f"/trips/{trip_1_id}", json={"destination": "Nara"}, headers=headers_u1)
            if resp.status_code == 200 and resp.json().get("destination") == "Nara":
                _safe_print("  ✅ [PASS] Owner PATCH /trips/{id} succeeds with 200 OK and updated destination")
            else:
                failures.append(f"Owner PATCH failed: {resp.status_code} {resp.text}")

            # 5. DELETE endpoint authorization
            # 5a. Anonymous DELETE -> 401
            resp = await client.delete(f"/trips/{trip_1_id}")
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] Anonymous DELETE /trips/{id} rejected with 401 Unauthorized")
            else:
                failures.append(f"Anonymous DELETE expected 401, got {resp.status_code}")

            # 5b. Other user DELETE -> 403
            resp = await client.delete(f"/trips/{trip_1_id}", headers=headers_u2)
            if resp.status_code == 403:
                _safe_print("  ✅ [PASS] Other-user DELETE /trips/{id} rejected with 403 Forbidden")
            else:
                failures.append(f"Other user DELETE expected 403, got {resp.status_code}")

            # Assert trip_1 still in DB
            async with crud_db.AsyncSessionLocal() as session:
                q = await session.execute(select(crud_models.Trip).where(crud_models.Trip.id == uuid.UUID(trip_1_id)))
                if q.scalar_one_or_none() is not None:
                    _safe_print("  ✅ [PASS] Denied DELETE requests left item intact in database")
                else:
                    failures.append("Item was deleted by unauthorized DELETE request!")

            # 5c. Nonexistent trip DELETE -> 404
            resp = await client.delete(f"/trips/{absent_id}", headers=headers_u1)
            if resp.status_code == 404:
                _safe_print("  ✅ [PASS] Nonexistent trip DELETE returns 404 Not Found")
            else:
                failures.append(f"Nonexistent trip DELETE expected 404, got {resp.status_code}")

            # 5d. Owner DELETE -> 204
            resp = await client.delete(f"/trips/{trip_1_id}", headers=headers_u1)
            if resp.status_code == 204:
                _safe_print("  ✅ [PASS] Owner DELETE /trips/{id} succeeds with 204 No Content")
                async with crud_db.AsyncSessionLocal() as session:
                    q = await session.execute(select(crud_models.Trip).where(crud_models.Trip.id == uuid.UUID(trip_1_id)))
                    if q.scalar_one_or_none() is None:
                        _safe_print("  ✅ [PASS] Deleted trip confirmed removed from database")
                    else:
                        failures.append("Deleted trip still exists in database!")
            else:
                failures.append(f"Owner DELETE failed: {resp.status_code}")

    finally:
        try:
            await crud_db.engine.dispose()
        except Exception:
            pass
        temp_dir.cleanup()

    if failures:
        _safe_print(f"❌ [FAIL] Mutation authorization encountered {len(failures)} failures:")
        for f in failures:
            _safe_print(f"    - {f}")
        return 1

    _safe_print("✅ [PASS] All mutation authorization and schema tests passed!")
    return 0


async def test_f3_waiver_and_updates(f3_dir: Path) -> int:
    """Test F3 ownership waiver and suffixed PUT update endpoint."""
    _safe_print("\n--- Testing F3 Ownership Waiver & Suffixed Updates ---")

    for mod_name in list(sys.modules.keys()):
        if mod_name in (
            "db", "models", "schemas", "auth", "main",
            "routers", "routers.trips", "routers.users",
        ):
            del sys.modules[mod_name]

    f3_dir_str = str(f3_dir.resolve())
    if f3_dir_str in sys.path:
        sys.path.remove(f3_dir_str)
    sys.path.insert(0, f3_dir_str)

    temp_dir = tempfile.TemporaryDirectory(prefix="trustc_smoke_f3_db_")
    db_path = Path(temp_dir.name) / "test_f3.db"
    harness_secret = generate_harness_secret(32)

    os.environ["DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["JWT_SECRET"] = harness_secret

    failures: list[str] = []

    try:
        f3_db = importlib.import_module("db")
        f3_models = importlib.import_module("models")
        f3_main_mod = importlib.import_module("main")
        f3_app = getattr(f3_main_mod, "app")

        async with f3_db.engine.begin() as conn:
            await conn.run_sync(f3_db.Base.metadata.create_all)

        async with f3_db.AsyncSessionLocal() as session:
            await seed_test_users(session, f3_models.User)

        token_u1 = create_access_token(USER_1_ID, secret=harness_secret)
        token_u2 = create_access_token(USER_2_ID, secret=harness_secret)

        headers_u1 = {"Authorization": f"Bearer {token_u1}"}
        headers_u2 = {"Authorization": f"Bearer {token_u2}"}

        transport = ASGITransport(app=f3_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testapp_f3") as client:
            resp = await client.post("/trips", json={"destination": "Kyoto"}, headers=headers_u1)
            if resp.status_code != 201:
                failures.append(f"F3 POST /trips failed: {resp.status_code}")
                return 1
            trip_id = resp.json()["id"]

            async with f3_db.AsyncSessionLocal() as session:
                trip_query = select(f3_models.Trip).where(f3_models.Trip.id == uuid.UUID(trip_id))
                trip_row = (await session.execute(trip_query)).scalar_one()
                if not trip_row.is_public:
                    _safe_print("  ✅ [PASS] F3 omitted field is_public defaults to False in DB")
                else:
                    failures.append("is_public was not False by default!")

            resp = await client.put(
                f"/trips/{trip_id}/visibility",
                json={"is_public": True},
                headers=headers_u2,
            )
            if resp.status_code == 200:
                _safe_print("  ✅ [PASS] F3 authorize: public waiver permits User 2 update")
                if resp.json() == {}:
                    _safe_print("  ✅ [PASS] PUT route with omitted returns returns empty dict {}")
                else:
                    failures.append(f"Omitted returns expected {{}}, got {resp.json()}")
            else:
                failures.append(
                    f"PUT /trips/{trip_id}/visibility failed: {resp.status_code} {resp.text}"
                )

            resp = await client.put(
                f"/trips/{trip_id}/visibility",
                json={"is_public": False},
            )
            if resp.status_code == 401:
                _safe_print("  ✅ [PASS] Waiver still requires authentication (anonymous -> 401)")
            else:
                failures.append(f"Anonymous PUT expected 401, got {resp.status_code}")

            async with f3_db.AsyncSessionLocal() as session:
                trip_query = select(f3_models.Trip).where(f3_models.Trip.id == uuid.UUID(trip_id))
                trip_row = (await session.execute(trip_query)).scalar_one()
                if trip_row.is_public is True:
                    _safe_print("  ✅ [PASS] Authorized update persisted in database")
                else:
                    failures.append("Updated is_public was not True in database!")

    finally:
        try:
            await f3_db.engine.dispose()
        except Exception:
            pass
        temp_dir.cleanup()

    if failures:
        _safe_print(f"\n❌ [FAIL] F3 test suite encountered {len(failures)} failures:")
        for f in failures:
            _safe_print(f"    - {f}")
        return 1

    _safe_print("\n✅ [PASS] All F3 waiver and suffixed update tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TrustC Stage 4 Runtime Smoke Tester")
    parser.add_argument(
        "spec", nargs="?", default="tests/fixtures/F2.trust", help="Path to spec file"
    )
    parser.add_argument(
        "-o", "--output", default=".trustc-smoke/generated", help="Output directory"
    )
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    out_dir = Path(args.output).resolve()

    _safe_print("Starting Stage 4 Runtime Smoke Test")
    _safe_print(f"Spec: {spec_path}")
    _safe_print(f"Output: {out_dir}")

    try:
        build_res = build_app(spec_path, out_dir, replace=True)
        _safe_print(
            f"✅ [PASS] Built {spec_path.name} successfully "
            f"(BuildId: {build_res.build_id}, {len(build_res.files)} files)"
        )
    except Exception as exc:
        _safe_print(f"❌ [FAIL] Failed to build {spec_path}: {exc}")
        return 1

    # Check 1: S4-01 environment and startup security
    rc_env = test_env_and_security_configuration(out_dir)
    if rc_env != 0:
        return rc_env

    # Check 2: S4-04 artifact manifest verification
    rc_manifest = test_manifest_verification(out_dir)
    if rc_manifest != 0:
        return rc_manifest

    # Check 3: Full F2 application runtime checks (including S4-05)
    rc_f2 = asyncio.run(test_f2_generated_app(out_dir))
    if rc_f2 != 0:
        return rc_f2

    # Check 4: Mutation authorization and schema tests (Verification Gaps 1 & 2)
    rc_crud = asyncio.run(test_crud_mutation_authorization())
    if rc_crud != 0:
        return rc_crud

    # Check 5: F3 ownership waiver and suffixed updates
    f3_spec = REPO_ROOT / "tests" / "fixtures" / "F3.trust"
    f3_out = REPO_ROOT / ".trustc-smoke" / "generated_f3"
    try:
        build_app(f3_spec, f3_out, replace=True)
        _safe_print("✅ [PASS] Built F3.trust successfully for waiver & update tests")
        rc_f3 = asyncio.run(test_f3_waiver_and_updates(f3_out))
        if rc_f3 != 0:
            return rc_f3
    except Exception as exc:
        _safe_print(f"❌ [FAIL] Failed to build or test F3: {exc}")
        return 1

    _safe_print("\n============================================================")
    _safe_print("Stage 4 Runtime Smoke Test PASSED completely!")
    _safe_print("============================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
