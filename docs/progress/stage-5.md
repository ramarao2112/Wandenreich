# TrustC Stage 5 — Live Local Access Harness Completion Report

**Completed Date:** 8 October 2026  
**Status:** PASS (Exit 0 across all gates)  
**Schema Version:** 2 (`AttackCompleted` & `AttackStep` v2 wire format)  
**Spec References:** `stage-5-attack.md`, `03-GATE-MATRIX.md`, `B-compiler-spec.md §B2`, `A-contracts.md`, `C-fixtures-and-tests.md`

---

## 1. Executive Summary

Stage 5 delivers the live local access harness for generated TrustC backends, exposed via the `trustc attack` CLI command and internal Python API `run_attack_harness` / `attack_spec`. 

The harness builds and runs verified TrustC FastAPI applications against a child ASGI server (`uvicorn`) over loopback HTTP (`127.0.0.1`) using an OS-assigned dynamic port. Each test run executes against an isolated, run-owned temporary SQLite database with a fresh, ephemeral cryptographic JWT secret (>= 32 bytes). It seeds two test users (`USER_1` as owner, `USER_2` as second user) and a test resource instance, and deterministically executes requests across three actors (`anonymous`, `second_user`, `owner`).

Critical properties enforced by Stage 5:
1. **Isolated State per Actor**: Prior to every actor's request, the database state is cleanly restored, ensuring destructive operations (e.g., allowed DELETE or updates) never contaminate subsequent actor requests.
2. **Side-Effect Verification**: Confirms allowed writes and deletions persist in SQLite, and denied writes and unauthorized deletions do not alter the database state.
3. **Strict Credential Protection**: No JWT tokens, secrets, or `password_hash` values are emitted in logs, console output, SSE events, or reports.
4. **Deterministic Exit Codes**:
   - Clean verification matches expectations: Exit 0.
   - Refused specifications (e.g., F1): Exit 1 (application never started).
   - Syntax error specifications (e.g., F4): Exit 2 (application never started).
   - Flaw detection / unexpected policy violations: Exit 1.
5. **Mutation Testing**: An AST transformer removes the owner-check statement in `routers/trips.py` on an isolated copy of the F2 artifact; the harness cleanly detects the flaw on `second_user` read (returning 200 instead of 403) and terminates with Exit 1 while the `User` identity endpoint remains self-protected.
6. **Robust Lifecycle Cleanup**: Guarantees termination of child server process trees (`kill_process_tree`) and complete removal of run-owned temporary directories across normal completion, cancellations (130), timeouts (124), and errors (3).

---

## 2. Implemented Architecture & Components

### 2.1 Live Attack Harness (`src/trustc/harness.py`)
- **`find_free_loopback_port()`**: Binds to port 0 on loopback (`127.0.0.1`) to obtain an OS-assigned ephemeral port, eliminating port collisions and hardcoded port assumptions.
- **`wait_for_server_ready()`**: Actively polls the `/health` endpoint with a bounded readiness deadline (up to 5.0s with exponential backoff and connection retries).
- **`reset_sqlite_database()`**: Connects directly to SQLite to restore seed rows (`users` and test resource items) before each actor request, guaranteeing state isolation.
- **`run_attack_harness()`**:
  - Sets up run-owned isolated temporary directories.
  - Spawns child ASGI process (`python -m uvicorn app:app --host 127.0.0.1 --port <port>`).
  - Emits real-time streaming `RunEvent` objects (`PhasePayload`, `ActorPayload`, `LogPayload`, `ResultPayload`).
  - Executes HTTP requests via `httpx.Client` for all actors in deterministic order: `anonymous`, `second_user`, `owner`.
  - Asserts response HTTP status codes, response JSON projections, and persistent database modifications.
  - Generates `AttackCoverage` distinguishing tested item endpoints from excluded collection/create routes with rationale.
  - Guarantees child process termination and temporary directory deletion in `finally` blocks on all terminal paths.
- **`attack_spec()`**: High-level entry point accepting spec path or source string, parsing, pre-verifying, building into temporary directory, and running harness.
- **`mutate_and_attack_f2()`**: AST-based mutation test helper. Copies F2 artifact, removes owner-check `If` statement from `routers/trips.py`, re-manifests, and runs harness to confirm flaw detection.

### 2.2 CLI Integration (`src/trustc/cli.py`)
- Registered `trustc attack` subcommand with `--format` (`human` or `json`) and `--revision` options.
- Formats streaming events and outputs structured results according to `AttackCompleted` and `RunFailure` schema specifications.

### 2.3 Router Template Hardening (`src/trustc/templates/fastapi/router.py.jinja`)
- **Public Routes with DB Dependency**: Ensured `Depends` is always imported from `fastapi` when database sessions are injected.
- **Public Owned Routes**: Guarded owner-check blocks with `{% if resource.is_owned and ep.auth_required and not ep.owner_waived %}` so that public routes (such as X08) do not reference nonexistent `current_user` dependencies.

---

## 3. Verified Fixture Outcomes

| Fixture | Endpoints Tested | Steps | As Expected | Review | Unexpected | Exit Code | Verified Details |
|---|---|---|---|---|---|---|---|
| **F2.trust** | `GET /trips/{id}`, `GET /users/{id}` | 6 | 6 | 0 | 0 | 0 | Deterministic 401/403/200 on Trip, 401/403/200 on User self |
| **F3.trust** | `GET /trips/{id}`, `GET /users/{id}`, `PUT /trips/{id}/visibility` | 9 | 8 | 1 | 0 | 0 | Waived ownership on visibility update permits second_user access by design (`review`) |
| **F1.trust** | N/A (Refused) | 0 | 0 | 0 | 0 | 1 | Rule violations (TC-001, TC-003); app never generated or started |
| **F4.trust** | N/A (Syntax Error) | 0 | 0 | 0 | 0 | 2 | Parser error at line 23 column 25; app never generated or started |
| **X08.trust** | `GET /notes/{id}`, `DELETE /notes/{id}` | 6 | 2 | 4 | 0 | 0 | Public owned GET/DELETE; anonymous and second_user succeed with `review`, owner succeeds with `as_expected`. State restored after DELETE |
| **X11.trust** | None (Collection routes only) | 0 | 0 | 0 | 0 | 0 | Collection-only routes excluded by scope; explicit empty coverage reported |
| **F2 Mutated**| `GET /trips/{id}`, `GET /users/{id}` | 6 | 5 | 0 | 1 | 1 | Trip owner-check removed; second_user gets 200 instead of 403 (`unexpected`); User endpoint remains self-protected |

---

## 4. Policy Review vs. Unexpected Explanations

In TrustC's security verification model, an outcome of **`review`** occurs when an endpoint behavior is strictly allowed according to the author's explicit specification but represents a heightened security or privacy posture requiring human awareness.

For example:
- In **F3.trust**, the author specified `authorize: public` on `PUT /trips/{id}/visibility`. Consequently, `second_user` is permitted to update the visibility of a trip they do not own. Because this matches the specification, it is not an implementation defect (`unexpected`), but it is classified as `review` so developers and auditors are explicitly notified that cross-user write access was permitted by design.
- In **X08.trust**, endpoints are configured with `auth: public`. Both anonymous and second users can read and delete notes. This matches the specification, producing `review` for non-owner actors and `as_expected` for the owner.
- In contrast, an **`unexpected`** outcome indicates a flaw: the implementation violated the expected security policy (e.g. an unauthenticated request succeeded when authentication was required, or cross-tenant data was exposed despite ownership restrictions).

---

## 5. Acceptance Matrix Mapping

All Stage 5 requirements are logged and verified in `docs/progress/acceptance.csv`:

| Req ID | Specification Clause | Component | Test Target | Status | Verification Evidence |
|---|---|---|---|---|---|
| `REQ-5-01` | stage-5-attack.md §Work 2-3 | `src/trustc/harness.py` | `test_run_attack_harness_secret_redaction` | PASS | `review-logs/stage-5/cli-attack-f2.txt` |
| `REQ-5-02` | stage-5-attack.md §Work 4-5 | `src/trustc/harness.py` | `test_attack_spec_f2_success` | PASS | `review-logs/stage-5/cli-attack-f2.txt` |
| `REQ-5-03` | stage-5-attack.md §Work 5 | `src/trustc/harness.py` | `test_attack_spec_f3_success_with_review` | PASS | `review-logs/stage-5/cli-attack-f3.txt` |
| `REQ-5-04` | stage-5-attack.md §Work 8 | `src/trustc/harness.py` | `test_mutation_testing_f2_detects_flaw` | PASS | `review-logs/stage-5/mutation-f2.txt` |
| `REQ-5-05` | stage-5-attack.md §Gates | `src/trustc/harness.py` | `test_x08_public_owned_get_delete_with_isolated_state` | PASS | `review-logs/stage-5/cli-attack-x08.txt` |
| `REQ-5-06` | stage-5-attack.md §Work 6 | `src/trustc/harness.py` | `test_x11_zero_eligible_item_endpoints_coverage` | PASS | `review-logs/stage-5/cli-attack-x11.txt` |
| `REQ-5-07` | stage-5-attack.md §Work 1 | `src/trustc/harness.py` | `test_refused_and_syntax_error_specs_never_start_app` | PASS | `review-logs/stage-5/cli-attack-f1.txt` |
| `REQ-5-08` | stage-5-attack.md §Work 7 | `src/trustc/harness.py` | `test_harness_cancellation_and_cleanup` | PASS | `review-logs/stage-5/pytest.txt` |
| `REQ-5-09` | Stage 5 Gate | `scripts/check-stage.py` | `python scripts/check-stage.py 5 --linter flake8-isort` | PASS | `review-logs/stage-5/check-stage-5.log` |

---

## 6. Cumulative Gate Verification

The Stage 5 gate was executed with `--linter flake8-isort` and completed with Exit Code 0:
- **Gate 1/5 (Linters)**: flake8 passed (zero E/F/W violations), isort passed with zero diff.
- **Gate 2/5 (Typecheck)**: mypy passed across all 29 source and test files.
- **Gate 3/5 (Unit Tests)**: 214 pytest tests passed (100% pass rate).
- **Gate 4/5 (Parser CLI)**: F2 exit 0, F4 exit 2.
- **Gate 4b (Verifier CLI)**: F2 exit 0, F1 exit 1, F4 exit 2, dry-run fix exit 0, explain TC-002 exit 0, SARIF validation pass.
- **Gate 4c (Stage 4 Smoke)**: Real FastAPI/SQLite smoke tests passed, rollback byte-identical on F1/F4.
- **Gate 4d (Stage 5 Attack)**: F2 exit 0 (6/0/0), F3 exit 0 (8/1/0), F1 exit 1 (refused), F4 exit 2 (invalid_spec), X08 exit 0 (2/4/0), X11 exit 0 (0/0/0), mutation flaw detected (exit 1).
- **Gate 5/5 (Wheel Smoke)**: Built wheel installed in fresh isolated virtualenv outside repository; parse, check, and build entrypoints verified.

---

## 7. Stage 5 Review & Corrections Closure (9 October 2026)

All defects and evidence gaps identified in the Stage 5 review (`TrustC-Stage-5-Review-and-Corrections.md`) have been resolved and independently evidenced:

### S5-01 — Correct Matched-Expectation Totals
- **Resolution**: Updated `_format_human_summary` in `src/trustc/harness.py` to calculate `matched = result.as_expected + result.review` and `total = result.as_expected + result.review + result.unexpected`. Raw categories (`asExpected`, `review`, `unexpected`) remain untouched.
- **Verified Outcomes**:
  - **F2**: `6 matched expectations · 0 policy reviews · 0 failed` (`review-logs/stage-5/cli-attack-f2.txt`)
  - **F3**: `9 matched expectations · 1 policy review · 0 failed` (`review-logs/stage-5/cli-attack-f3.txt`)
  - **X08**: `6 matched expectations · 4 policy reviews · 0 failed` (`review-logs/stage-5/cli-attack-x08.txt`)
  - **X11**: `0 matched expectations · 0 policy reviews · 0 failed` (`review-logs/stage-5/cli-attack-x11.txt`)
  - **Mutated F2**: `5 matched expectations · 0 policy reviews · 1 failed` (`review-logs/stage-5/mutation-f2.txt`)
- **Automated Test**: `tests/unit/test_harness.py::test_s5_01_human_summary_matched_totals_rendering` (PASS).

### S5-02 — Canonical UUID Attack-Step Identifiers
- **Resolution**: Removed the `step-` prefix in `src/trustc/harness.py`, generating pure UUID strings (`str(uuid.uuid4())`).
- **Enforcement**: Added a `@model_validator(mode="after")` on `AttackStep` in `src/trustc/contracts.py` that validates each `stepId` with `uuid.UUID(self.step_id)`. Non-UUID identifiers (such as `"step-12345"` or `"s1"`) raise a `ValidationError`.
- **References**: Pending actor events, resolved actor events, final result steps, and `declarationObservations` share the exact identical UUIDs.
- **Automated Tests**: `tests/unit/test_harness.py::test_step_ids_are_canonical_unprefixed_uuids` and `tests/contract/test_contracts.py::TestAttackCompleted::test_rejects_non_uuid_step_id` (PASS).

### S5-03 — Lifecycle and Final-Event Guarantees
- **Coverage Mapping**:
  1. **Normal Completion**: HTTP client and SQLite connections closed, child process tree reaped via PID process tree kill, temporary directory unlinked. Verified in `test_normal_completion_lifecycle_and_single_final_event`.
  2. **Active Cancellation / KeyboardInterrupt**: Exit code 130 after full cleanup; no orphaned processes or writes. Verified in `test_active_cancellation_cleans_up_and_exits_130`.
  3. **Deadline Expiry**: Exit code 124 within bounded cleanup bound. Verified in `test_deadline_expiry_cleans_up_and_exits_124`.
  4. **Startup/Readiness Failure**: Exit code 3 with sanitized error message; no fake status codes. Verified in `test_startup_readiness_failure_cleans_up_and_exits_3`.
  5. **Cleanup Failure**: Reports sanitized execution error exit code 3 without completed success. Verified in `test_cleanup_failure_reports_sanitized_error_exit_3`.
  6. **F1 Refusal / F4 Invalid Input**: Pre-run check prevents server startup; process spawn spy asserts 0 processes started. Verified in `test_refused_and_syntax_error_specs_never_start_app`.
  7. **Event Ordering**: Pending actor update strictly precedes resolution; exactly one terminal result follows `cleanup: finished`. Verified in `test_normal_completion_lifecycle_and_single_final_event`.

### S5-04 — Full Results, Projections, Persistence & Mutation Evidence
- **Complete Schema-Valid JSON Exports**: Generated and saved to `review-logs/stage-5/`:
  - `attack-f2.json`: 6 steps, `coverage.testedEndpoints = ["GET /trips/{id}", "GET /users/{id}"]`, `coverage.excludedEndpoints = [{"endpoint": "POST /trips", "reason": "collection/create endpoint excluded from item-only access harness"}]`.
  - `attack-f3.json`: 9 steps, waiver linked to PUT steps via `declarationObservations[0].stepIds`.
  - `attack-x08.json`: 6 steps, state reset isolation verified with `allowed_write_persistence` checks on DELETE.
  - `attack-x11.json`: 0 steps, empty coverage with rationale for `POST /items` and `GET /items`.
  - `attack-f2-mutated.json`: exit 1, 1 unexpected step on second_user GET trip, user self-protection preserved.
- **Detailed Mutation Report (`mutation-f2.txt`)**: Documents original build hash vs mutated build hash (`b419...` vs `f999...`), isolated directory copy, removal of AST owner-check in `routers/trips.py`, syntax re-check via `ast.parse`, and exact step failure details.
- **Zero Live Secrets**: Random ephemeral secrets in memory; tokens redacted in all logs and outputs.

### S5-05 — Stage 4 Correction Closure
- **S4-01 (JWT Secret & Configuration)**: Hardcoded secrets removed. Startup halts immediately on missing or <32 byte secrets (`smoke-generated.txt`).
- **S4-02 (Revision Mismatch)**: Spec revision `specVersion` preserved through compiler, artifacts, manifests, and attack results (`test_s4_02_spec_version_consistency_cli_and_api`).
- **S4-03 (Dependency Pinning)**: Exact `==` pinned versions in `requirements.txt`; clean isolated venv install verified in `generated-app-install.txt`.
- **S4-04 (Cryptographic Manifest)**: `trustc-manifest.json` uses length-prefixed path/byte hashing; tamper detection and atomic rollback verified.
- **S4-05 (User 404 Before 403)**: Authenticated nonexistent user returns 404; other existing user returns 403; self returns 200 (`smoke-generated.txt`).

### S5-06 — Packaging and Handoff Checks
- **Extended Wheel Smoke**: `scripts/wheel_smoke_test.py` now installs the `harness` optional dependency group (`wheel[harness]`), runs installed `trustc attack F2.trust` outside the repository, and verifies 6 expected outcomes and cleanup (`review-logs/stage-5/wheel-smoke.log`).
- **Cumulative Test Results**: Complete `review-logs/stage-5/pytest.txt` captures all 221 tests passing in 52.18s; `pytest-harness.txt` captures all 14 focused harness tests passing.

### Diagnostic Presentation Cleanup
- Error presentation now prints stable rule ID `TC-001` (not `RuleId.TC_001`), `Syntax error` (not `SpecErrorKind.SYNTAX`), and escapes literal newlines as `\n` in error messages (`cli-attack-f1.txt`, `cli-attack-f4.txt`).
- Wheel smoke test title dynamically reflects the actual stage scope (`Stage 5 Wheel Installation & Smoke Test`).

---

## 8. Next Stage Handoff

Stage 5 is complete with all review corrections fully implemented, verified, and evidenced. Proceeding to **Stage 6 — Local server and streaming protocol** (`TrustC-Stage-Pack-v3/stage-6-server.md`).
