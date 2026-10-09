# TrustC Stage 6 — Local API Server, Streaming Protocol & Artifact Lifecycle Completion Report

**Completed Date:** 9 October 2026  
**Status:** PASS (Exit 0 across all gates)  
**Schema Version:** 2 (All v2 wire models and event schemas enforced)  
**Spec References:** `stage-6-server.md`, `A-contracts.md`, `03-GATE-MATRIX.md`, `C-fixtures-and-tests.md`

---

## 1. Executive Summary

Stage 6 delivers the local HTTP API server for TrustC (`trustc serve --port 8787 --static ./ui/dist`), providing interactive web and workbench clients with full access to the verification engine, code generator, and live access harness.

The server is built with FastAPI and runs on loopback HTTP (`127.0.0.1`). It implements all ten operations specified in `A-contracts.md`, supports server-sent event (SSE) streaming for long-running builds and attacks, delivers immutable build zip archives, manages worker concurrency with atomic locking, and enforces strict security middleware against DNS rebinding and cross-origin attacks.

Key guarantees enforced by Stage 6:
1. **Loopback & Host Binding Security**: Default bind host is strictly `127.0.0.1`. Security middleware validates the `Host` header against loopback addresses (`localhost`, `127.0.0.1`, `[::1]`) and rejects external hosts with `403 FORBIDDEN_HOST`.
2. **Cross-Origin Protection**: Validates the `Origin` header on mutating requests (`POST`, `PUT`, `DELETE`). Requests from foreign browser origins are rejected with `403 FORBIDDEN_ORIGIN`. Local developer tools and CLI clients without `Origin` headers remain permitted.
3. **Payload & Size Constraints**: Rejects request bodies exceeding 1 MiB (`413 PAYLOAD_TOO_LARGE`) and raw specification UTF-8 text exceeding 256 KiB (`413 PAYLOAD_TOO_LARGE`). Requires `Content-Type: application/json` for mutation endpoints (`400 INVALID_CONTENT_TYPE`).
4. **Structured API 404 Routing**: All `/api/*` routes are registered before any static file fallback mounts. Unknown API routes return structured JSON (`404 NOT_FOUND`), never `index.html`.
5. **SSE Streaming & Cursor Replay**: `GET /api/runs/{runId}/events` streams events formatted as `event: trustc\nid: <runId>:<seq>\ndata: <json>\n\n`, emits periodic `: heartbeat\n\n` comments, caps buffer memory (4096 events / 4 MiB), and supports resumption via `Last-Event-ID`.
6. **Immutable Artifact Delivery**: `GET /api/builds/{buildId}/out.zip` packages the generated application files, `trustc-manifest.json`, and `trustc-report.json`. All archive entries use normalized relative forward-slash paths with zero leading slashes, backslashes, or directory traversal (`..`).
7. **Supervised Worker Concurrency**: An atomic lock guarantees that only one build or attack worker executes at a time. Concurrent job requests return `409 SERVER_BUSY`.
8. **Clean Cancellation Lifecycle**: Active runs can be cancelled via `DELETE /api/runs/{runId}` returning `202 RunCancelResponse` with state `cancelling`, terminating child processes and cleaning temporary directories. Terminal runs return `204 No Content`.

---

## 2. Implemented Architecture & Components

### 2.1 Server Application Factory (`src/trustc/server.py`)
- **`create_app(workspace_dir, port, static_dir)`**: FastAPI application factory configuring middleware, routes, and state.
- **`run_server(host, port, static_dir, workspace_dir)`**: Subprocess entrypoint invoking `uvicorn.run`.
- **`ServerState`**: Thread-safe server state managing the active session ID, worker lock, run history, and published build catalog with a 15-minute retention window.
- **`RunRecord`**: State tracking for build and attack jobs, holding the event buffer, atomic listener queues, completion timestamp, and cancellation events.
- **`BuildRecord`**: Metadata and immutable artifact paths for completed builds.

### 2.2 Implemented API Operations (All 10 Endpoints)

| Operation | Method & Path | Status Codes | Description |
|---|---|---|---|
| 1. Server Meta | `GET /api/meta` | 200 | Returns schemaVersion 2, sessionId, compiler version, port, target, and all 5 rule descriptors. |
| 2. Spec Examples | `GET /api/examples` | 200 | Returns catalog of 6 canonical example specs (F1..F6) with expectedCheck and expectedReview flags. |
| 3. Rule Documentation | `GET /api/rules/{id}` | 200, 404 | Returns checks, flaw description, fixType, and refused/accepted examples for rules TC-001..TC-005. |
| 4. Verify Spec | `POST /api/check` | 200, 400, 413, 500 | Evaluates specification with all 5 security rules within a 5.0s deadline. Supports `?format=sarif`. |
| 5. Build Application | `POST /api/build` | 202, 400, 409, 413 | Accepts build job, acquires worker lock, executes compilation in staging, and publishes build with `out.zip`. |
| 6. Attack Application | `POST /api/attack` | 202, 400, 404, 409, 413 | Accepts attack job, verifies `buildId` and `specHash` if provided, executes live harness, and emits events. |
| 7. SSE Event Stream | `GET /api/runs/{runId}/events` | 200, 400, 404, 410 | Streams SSE `event: trustc` with sequence IDs. Replays from `Last-Event-ID` cursor. Sends 5s heartbeats. |
| 8. Run Status | `GET /api/runs/{runId}` | 200, 404, 410 | Returns current status (`running` or `terminal`) and full `result` model upon completion. |
| 9. Cancel / Delete Run | `DELETE /api/runs/{runId}` | 202, 204, 404 | Cancels active running job (202), or cleans up completed terminal run (204). |
| 10. Download Build Archive | `GET /api/builds/{buildId}/out.zip` | 200, 404, 410 | Downloads immutable ZIP archive containing all generated application files, manifest, and report. |

### 2.3 CLI Integration (`src/trustc/cli.py`)
- Added `serve` subcommand:
  ```bash
  trustc serve --host 127.0.0.1 --port 8787 --static ./ui/dist --workspace ./workspace
  ```
- Flags supported:
  - `--host`: Host to bind (default: `127.0.0.1`).
  - `--port`: Port to bind (default: `8787`).
  - `--static`: Directory to serve static UI assets from.
  - `--workspace`: Directory for server staging and build persistence.

### 2.4 Security Middleware
- **Host Header Validation**: Rejects DNS rebinding attacks (`Host: attacker.com` -> `403 FORBIDDEN_HOST`).
- **Origin Validation**: Rejects cross-origin POST/PUT/DELETE from untrusted browser sites (`Origin: http://evil.com` -> `403 FORBIDDEN_ORIGIN`).
- **Preflight CORS**: Handles `OPTIONS` requests gracefully with appropriate loopback `Access-Control-*` headers.
- **Size Enforcements**: Request body capped at 1 MiB (`413 PAYLOAD_TOO_LARGE`); spec UTF-8 text capped at 256 KiB (`413 PAYLOAD_TOO_LARGE`).
- **Content-Type Check**: Enforces `application/json` on all incoming POST requests (`400 INVALID_CONTENT_TYPE`).
- **API 404 Isolation**: Catches all unhandled `/api/*` routes and returns JSON `404 NOT_FOUND` before static mounts can intercept them.

---

## 3. Verification & Evidence

### 3.1 Automated Test Suite (`tests/unit/test_server.py`)
16 comprehensive unit test cases covering all 10 operations, security middleware, and lifecycle transitions:
- `test_server_meta`: Validates `GET /api/meta` schemaVersion 2, sessionId, target, and 5 rules.
- `test_server_examples`: Validates `GET /api/examples` returns F1..F6 with non-empty specs and review flags.
- `test_server_rules_catalog`: Validates `GET /api/rules/{id}` for TC-001..TC-005 and 404 for TC-999.
- `test_server_check_valid_and_refused`: Validates `POST /api/check` with F2 (exit 0) and F1 (exit 1).
- `test_server_check_sarif_format`: Validates `POST /api/check?format=sarif` returns OASIS SARIF 2.1.0 JSON.
- `test_server_check_validation_errors`: Validates Content-Type check (400), malformed JSON (400), spec size limit (413).
- `test_server_build_worker_lifecycle`: Validates `POST /api/build` (202), worker completion, and `buildId` index.
- `test_server_build_refusal_and_syntax_error`: Validates build failure handling on F1 (refused) and F4 (syntax error).
- `test_server_worker_busy_lock_409`: Validates concurrent build/attack rejection with 409 SERVER_BUSY.
- `test_server_build_out_zip`: Validates `GET /api/builds/{buildId}/out.zip` clean relative paths and manifest presence.
- `test_server_attack_worker_lifecycle_with_build_id`: Validates `POST /api/attack` with buildId returns 6 asExpected.
- `test_server_attack_build_id_mismatch`: Validates 404 on unknown buildId and 409 on specHash mismatch.
- `test_server_sse_streaming_and_replay`: Validates SSE event format, sequence counting, and Last-Event-ID replay.
- `test_server_runs_status_and_cancellation`: Validates run querying and DELETE lifecycle (202 cancelling, 204 terminal).
- `test_server_security_middleware`: Validates Host (403), Origin (403), body limit (413), and `/api/*` 404 JSON.
- `test_server_static_fallback`: Validates static file delivery and SPA fallback while preserving `/api/*` 404 routing.

### 3.2 Smoke Verification (`scripts/smoke-server.py`)
End-to-end loopback smoke tester running `trustc serve` as a subprocess on a dynamic port:
- Probes `/api/meta` until server is ready.
- Verifies meta, examples, and rule docs.
- Checks F2 (pass) and F1 (refuse) and SARIF export.
- Initiates F2 build (202), streams SSE events to terminal completion, downloads and verifies `out.zip`.
- Initiates F2 attack using `buildId` (202), verifies 6 asExpected, 0 review, 0 unexpected.
- Tests DELETE lifecycle (204) and security middleware (403 on foreign host/origin, 413 on oversized body).
- Shuts down subprocess cleanly and exits 0.

### 3.3 Full Cumulative Gate (`scripts/check-stage.py 6`)
- **Gate 1**: flake8 + isort clean (0 lint/import errors).
- **Gate 2**: mypy type check passes with 0 errors across 31 source files (S6-01 verified without type ignores).
- **Gate 3**: Pytest test suite across all stages (249 passed in 63.77s).
- **Gate 4**: CLI parse F2 (exit 0) and F4 (exit 2).
- **Gate 4b**: CLI check, fix, explain, and OASIS SARIF validation.
- **Gate 4c**: Stage 4 generated backend runtime smoke & build rollback.
- **Gate 4d**: Stage 5 live access harness & mutation testing.
- **Gate 4e**: Stage 6 local API server smoke test.
- **Gate 5**: Wheel installation, CLI smoke test, and live server test outside repo in isolated virtualenv.

---

## 4. Stage 6 Review Corrections Closure (S6-01 through S6-05)

| Item | Requirement & Review Feedback | Implementation & Verification | Status |
|---|---|---|---|
| **S6-01** | Resolve all mypy errors without blanket ignores, Any-casts, or disabling checks | Fixed ReturnsClause iteration, RunResult initialization, DeclarationObservationState mapping, literal fail_code types, and request middleware typing. `mypy src/ tests/` exits 0 across 31 source files. | **PASS** |
| **S6-02** | Generated JWT key validation must reject surrounding whitespace and verify exact assigned UTF-8 bytes >= 32 | Template `auth.py.jinja` rejects leading/trailing whitespace (`ValueError`) and enforces `len(_raw_jwt_secret.encode('utf-8')) >= 32` without modifying the assigned secret string. Tested in `test_generator.py` and `smoke-generated.py`. | **PASS** |
| **S6-03** | Access harness must assert exact response projections | Live harness generates explicit `AttackCheck(name="response_projection", expected=..., actual=..., passed=...)` verifying exact projected fields, sensitive exclusions, and empty responses. Verified across 4 new unit tests in `test_harness.py`. | **PASS** |
| **S6-04** | Server boundary and lifecycle hardening | Restricted `--host` to loopback addresses (`127.0.0.1`, `localhost`, `::1`), implemented active cancellation returning 202, hardened download traversal against symlinks/traversal, updated examples catalog and TC-001 flaw text. Verified in 23 unit tests. | **PASS** |
| **S6-05** | Extended wheel smoke test outside repository | Wheel smoke installs `[harness,server]`, starts the installed server outside the repo, verifies `sessionId`, tests `POST /api/check`, builds F2, downloads and inspects `out.zip`, and cleanly terminates. Exits 0 completely. | **PASS** |

---

## 5. Stage 6 Review Evidence Artifacts

All verification logs and outputs are stored in `review-logs/stage-6/`:

| Artifact | Size | Description |
|---|---|---|
| [`check-stage-6.log`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/check-stage-6.log) | 6,222 B | Full Stage 6 gate runner execution log across all gates (all 25 steps PASS, exit 0). |
| [`gate-result.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/gate-result.json) | 27,878 B | Machine-readable gate result metrics and step records. |
| [`mypy.txt`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/mypy.txt) | 212 B | Zero type errors across 31 source files (`Success: no issues found in 31 source files`). |
| [`smoke-server.txt`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/smoke-server.txt) | 1,617 B | Standalone server smoke tester output verifying all operations (exit 0). |
| [`pytest.txt`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/pytest.txt) | 25,120 B | Full cumulative test suite output (249 passed, 0 failed). |
| [`pytest-server.txt`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/pytest-server.txt) | 3,124 B | Focused Stage 6 unit test results (all 23 passed). |
| [`flake8.txt`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/flake8.txt) | 189 B | Zero lint errors across `src/` and `tests/`. |
| [`isort.txt`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/isort.txt) | 155 B | Zero import order violations across all files. |
| [`wheel-smoke.log`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/wheel-smoke.log) | 3,450 B | Wheel installation and live server execution smoke test outside repository. |
| [`cli-serve-help.txt`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/cli-serve-help.txt) | 602 B | CLI output of `trustc serve --help`. |
| [`api-meta.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-meta.json) | 514 B | Live JSON response from `GET /api/meta`. |
| [`api-examples.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-examples.json) | 4,452 B | Live JSON response from `GET /api/examples`. |
| [`api-rules-tc001.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-rules-tc001.json) | 456 B | Live JSON response from `GET /api/rules/TC-001`. |
| [`api-check-f2.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-check-f2.json) | 1,385 B | Live JSON response from `POST /api/check` with F2. |
| [`api-check-f1.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-check-f1.json) | 3,156 B | Live JSON response from `POST /api/check` with F1. |
| [`api-check-sarif.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-check-sarif.json) | 5,256 B | Live JSON response from `POST /api/check?format=sarif`. |
| [`api-build-f2.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-build-f2.json) | 44,508 B | Terminal `BuildSuccess` payload from `POST /api/build` F2. |
| [`api-attack-f2.json`](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/review-logs/stage-6/api-attack-f2.json) | 4,258 B | Terminal `AttackCompleted` payload from `POST /api/attack` F2. |
