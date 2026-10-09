# TrustC Stage 4 — Backend Generation & Execution Completion Report

**Completed Date:** 8 October 2026  
**Status:** PASS (Exit 0 across all gates)  
**Schema Version:** 2 (`BuildSuccess` & `BuildEvidence` v2 wire format)  
**Spec References:** `stage-4-generate.md`, `B-compiler-spec.md §B6-B7`, `A-contracts.md`, `C-fixtures-and-tests.md`

---

## 1. Executive Summary

Stage 4 implements backend code generation and runtime execution for TrustSpec specifications. The compiler lowers verified TrustSpec specifications into fully runnable, production-structured FastAPI applications backed by SQLAlchemy 2.0 Async ORM with SQLite (`aiosqlite`). 

The implementation was validated against real database persistence and live ASGI HTTP request execution. All security properties—including owner auto-assignment, owner list filtering, item ownership enforcement, strict user self-access, sensitive field exclusion, request field allowlisting with HTTP 422 rejections, fixed HS256 JWT claims validation, and database safety against SQL injection—were proven through live runtime smoke assertions with zero token or secret leaks.

All cumulative gates in `python scripts/check-stage.py 4` passed cleanly with exit code 0, including flake8, isort, mypy, 200 pytest tests, CLI build commands, runtime smoke testing, and isolated wheel installation packaging outside the repository.

---

## 2. Implemented Architecture & Components

### 2.1 FastAPI & SQLAlchemy 2.0 Template Engine (`src/trustc/templates/fastapi/`)
The backend is generated from high-fidelity Jinja2 templates:
1. **`db.py.jinja`**:
   - Manages async SQLAlchemy engine (`create_async_engine`) and sessionmaker (`async_sessionmaker`).
   - Injects `check_same_thread=False` when running on SQLite.
   - Yields `AsyncSession` per request with automatic rollback on error.
2. **`models.py.jinja`**:
   - Defines SQLAlchemy 2.0 mapped models with `DeclarativeBase`.
   - Uses `Mapped[uuid.UUID]` with `sa.Uuid` and `ForeignKey` relationships.
   - Defines boolean defaults (`server_default=sa.text("0")`) for omitted fields.
3. **`schemas.py.jinja`**:
   - Generates Pydantic v2 request and response schemas with `model_config = ConfigDict(extra="forbid")`.
   - Request schemas allowlist only declared body fields; extra fields or injected IDs trigger HTTP 422.
   - Response schemas enforce exact declared projections; credential fields (`password_hash`) are strictly excluded.
   - PATCH request schemas validate non-empty payload updates via `@model_validator(mode="after")`.
4. **`auth.py.jinja`**:
   - Implements fixed HS256 JWT validation using `pyjwt`.
   - Strictly enforces required claims: `sub`, `exp`, `iat`, `iss="trustc-local"`, and `aud="trustc-api"`.
   - Queries database for active user existence before authenticating.
   - Returns sanitized HTTP 401 Unauthorized on any token or lookup failure.
5. **`router.py.jinja`**:
   - Generates resource routers implementing CREATE (201), LIST (200), READ (200), UPDATE (200/{}), PATCH (200/{}), and DELETE (204).
   - Injects current user via `Depends(get_current_user)`.
   - On CREATE: automatically sets resource ownership field to `current_user.id`.
   - On LIST: filters items where `owner_id == current_user.id` unless ownership is waived.
   - On READ/UPDATE/PATCH/DELETE: verifies item exists (404) and checks ownership (403 Forbidden).
   - For User resource: strictly enforces self-access (`current_user.id == id`).
6. **`main.py.jinja`**:
   - Configures FastAPI app with lifespan event creating database tables on startup.
   - Mounts resource routers with prefix paths.
   - Provides `/health` endpoint returning compilation spec hash.
7. **`requirements.txt.jinja` & `README.md.jinja`**:
   - Lists runtime dependencies (`fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `aiosqlite`, `pyjwt`, `pydantic`).
   - Documents usage, environment variables (`DB_URL`, `JWT_SECRET`), and route layout.

### 2.2 Compiler Lowering & Build Generator (`src/trustc/generator.py`)
- **Pre-Verification**: Pre-verifies input specification against all 5 security rules. Refuses invalid or insecure specs (F1 exits 1, F4 exits 2).
- **Source Provenance Annotations**: Emits `# [trustc:provenance kind=... span=...]` comments for routes, auth, ownership assignments, queries, and self checks.
- **ForcedLine Mapping**: Scans generated source files to populate exact generated line mappings (`ForcedLine`) for audit traceability in `BuildEvidence`.
- **In-Memory Syntax Compilation**: Compiles every generated Python file via `compile(..., "exec")` before disk write.
- **Atomic Staging & Directory Safety**:
  - Writes files to an isolated temporary staging directory.
  - Generates manifest `trustc-report.json` adhering to `BuildSuccess` v2 schema.
  - Refuses to overwrite non-TrustC non-empty directories.
  - Requires `--replace` to overwrite existing TrustC builds.
  - Guarantees byte-identical rollback on any build failure or refusal.

### 2.3 Internal Test Seeder (`src/trustc/seeder.py`)
- Provides deterministic test fixtures (`USER_1_ID`, `USER_2_ID`, `DEFAULT_TEST_SECRET`).
- `create_access_token(...)`: In-memory HS256 JWT generator supporting configurable expiration, issuer, audience, and secret.
- `seed_test_users(...)`: Seeds initial user rows directly into the database session without public seeding routes or printed secrets.
- `SeededContext`: Dataclass with token redaction in `__repr__` to prevent sensitive credential leaks in test logs.

### 2.4 Runtime Smoke Runner (`scripts/smoke-generated.py`)
- Executes live HTTP requests against ASGI application and real SQLite database via `httpx.AsyncClient`.
- Reports clean, sanitized assertion outcomes with zero secret/token leakage.

---

## 3. Verified Runtime Behaviors

| Check | Target / Condition | Observed Behavior | Status |
|---|---|---|---|
| **Health Check** | `GET /health` | 200 OK with `status: ok` and spec hash | PASS |
| **Anonymous Rejection** | `POST /trips`, `GET /trips/{id}`, `GET /users/{id}` | 401 Unauthorized with sanitized header | PASS |
| **JWT Expiration** | Expired token | 401 Unauthorized | PASS |
| **JWT Signature** | Bad secret key | 401 Unauthorized | PASS |
| **JWT Claims** | Bad issuer / bad audience | 401 Unauthorized | PASS |
| **Unknown User** | Valid token with unregistered sub | 401 Unauthorized | PASS |
| **Owner Creation** | User 1 `POST /trips` | 201 Created with `owner_id` set to User 1 | PASS |
| **Owner Read** | User 1 `GET /trips/{id}` | 200 OK returning User 1 trip | PASS |
| **Cross-User Protection** | User 2 `GET /trips/{id}` | 403 Forbidden | PASS |
| **Nonexistent Item** | User 1 `GET /trips/{random_uuid}` | 404 Not Found | PASS |
| **Self User Access** | User 1 `GET /users/{USER_1_ID}` | 200 OK returning exact projected fields `[id, email]` | PASS |
| **Sensitive Exclusion** | User 1 profile response | `password_hash` strictly excluded from JSON | PASS |
| **Cross-User Self Check**| User 2 `GET /users/{USER_1_ID}` | 403 Forbidden | PASS |
| **Mass Assignment Rejected**| `owner_id` injection in body | 422 Unprocessable Entity | PASS |
| **ID Injection Rejected** | `id` injection in body | 422 Unprocessable Entity | PASS |
| **Extra Field Rejected** | `extra_param` in body | 422 Unprocessable Entity | PASS |
| **Zero DB Mutation** | Rejected write attempts | Database row count remains completely unchanged | PASS |
| **SQL Injection Safety** | `Tokyo'; DROP TABLE users; --` | Verbatim literal storage; tables intact | PASS |
| **F3 Default Values** | Omitted `is_public` field | Persisted as `False` default in DB | PASS |
| **F3 Ownership Waiver** | `authorize: public` on PUT `/trips/{id}/visibility` | User 2 update accepted (200 OK) and persisted | PASS |
| **F3 Omitted Return** | PUT route with omitted return | Returns empty dictionary `{}` | PASS |
| **F3 Unauthenticated Update**| Anonymous PUT to waived route | 401 Unauthorized (waiver does not bypass auth) | PASS |

---

## 4. Build System, File Integrity & Correction Details

1. **S4-01 — Zero Fallback Signing Key & Minimum Key Size**:
   - `auth.py.jinja` removed all fallback signing keys.
   - Requires `JWT_SECRET` via environment; missing, empty, or whitespace key halts startup with a sanitized `RuntimeError`.
   - Enforces minimum 32 bytes (`len(_raw_jwt_secret.encode("utf-8")) >= 32`) for HS256 security.
   - `db.py.jinja` removed fallback `app.db` path; missing `DB_URL` halts startup with a sanitized `RuntimeError`.
   - Secret values are strictly prevented from appearing in logs or error messages.
2. **S4-02 — Consistent Spec Revision**:
   - Originating spec revision is passed through CLI (`--revision`), `check_file`, `generate_app_files`, `BuildSuccess`, and serialized into `trustc-report.json`.
   - Verified that `build_success.specVersion == evidence.specVersion == report.specVersion` for both revision 0 and nonzero revisions.
3. **S4-03 — Exact Pinned Runtime Dependencies**:
   - `requirements.txt.jinja` specifies exact compatible runtime versions with `==`: `fastapi==0.142.4`, `uvicorn[standard]==0.54.0`, `sqlalchemy[asyncio]==2.1.4`, `aiosqlite==0.22.1`, `pyjwt==2.15.1`, `pydantic==2.13.5`, `email-validator==2.3.0`.
   - Verified clean installation in an isolated virtual environment (`scripts/test_generated_install.py`) with successful import and health/auth/DB operations.
4. **S4-04 — Cryptographic Artifact Manifest & Rollback Safety**:
   - Implemented `trustc-manifest.json` using unambiguous length-prefixed hashing (`sha256-length-prefixed-v1`) per v3 Clarification 3.
   - Excludes `trustc-report.json` and `trustc-manifest.json` from their own digest.
   - Cryptographically verifies all files on disk, detecting modified bytes, deleted files, and unexpected unmanifested files.
   - Publication flow includes atomic backup and rollback, ensuring existing directories remain 100% byte-identical on publication failure (verified with fault injection).
   - Generates 12 base files for F2: 8 Python files, `requirements.txt`, `README.md`, `trustc-manifest.json`, `trustc-report.json`.
5. **S4-05 — User Lookup 404/403 Ordering**:
   - `routers/users.py` queries database first (`select(User).where(User.id == id)`).
   - Returns 404 Not Found if user is absent from DB.
   - Returns 403 Forbidden if user exists but `current_user.id != id`.
   - Returns 200 OK with projected `[id, email]` and no `password_hash` if self.

---

## 5. Stage Gate Evidence & Review Logs

All evidence recorded in UTF-8 in `review-logs/stage-4/`:
- `check-stage-4.log`: Output of cumulative gate runner (Exit 0).
- `flake8.txt`: Flake8 linter report (Exit 0, 0 issues).
- `isort.txt`: Import sorting verification (Exit 0, 0 issues).
- `mypy.txt`: Mypy type-checker report across 27 source files (Exit 0, 0 issues).
- `pytest.txt`: Pytest full suite run of 206 tests across stages 1–4 (Exit 0).
- `cli-build-f2.txt`: `trustc build F2.trust` execution log (Exit 0, 12 files).
- `cli-build-f1.txt`: `trustc build F1.trust` refusal log (Exit 1).
- `cli-build-f4.txt`: `trustc build F4.trust` syntax error log (Exit 2).
- `smoke-generated.txt`: Runtime ASGI, database, and mutation smoke tester log (Exit 0).
- `trustc-manifest.json`: Actual verified cryptographic artifact manifest.
- `generated-app-install.txt`: Standalone clean virtualenv installation and exercise report (Exit 0).
- `sarif-schema-validation.txt`: Official OASIS SARIF 2.1.0 schema validation report (Exit 0).
- `traceability.txt`: Tested commit, working-tree status, and Python platform metadata.
- `gate-result.json`: Machine-readable gate execution record.
