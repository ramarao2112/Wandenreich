# TrustC Stage 3 — Security Verification & Fixes Completion Report

**Completed Date:** 8 October 2026  
**Status:** PASS (Exit 0 across all gates)  
**Schema Version:** 2 (`CheckResult` v2 wire format)  
**Spec References:** `stage-3-verify-and-fixes.md`, `B-compiler-spec.md §B4-B5`, `A-contracts.md`, `C-fixtures-and-tests.md`

---

## 1. Executive Summary

Stage 3 implements the TrustC security verification engine, automated unified diff fixes, rule documentation explain subsystem, and SARIF 2.1.0 reporting. The compiler now statically evaluates all five required security rules (`TC-001` through `TC-005`), provides exact unified diff patches that pass `git apply --check`, supports dry-run and atomic patch application, and exports standardized diagnostics for IDEs and CI/CD security workflows.

All stage requirements, tests, CLI assertions, and isolated wheel smoke tests have passed cleanly with zero linter or type-checker issues.

---

## 2. Implemented Architecture & Components

### 2.1 Security Rules Engine (`src/trustc/verifier.py`)
Evaluates the five mandatory B5 security rules in deterministic order:
1. **`TC-001` (AUTH-REQUIRED):** Flags endpoints missing an explicit authentication declaration (`auth: required` or `auth: public`). Generates automated unified diff inserting `auth: required`.
2. **`TC-002` (OWNERSHIP-CHECK):** Enforces ownership policies across endpoints. Flags unsupported `role_only`, public POST on owned resources, public or waived User endpoints (User is strictly self-only), contradictory `auth: public` with `authorize:`, `authorize:` on unowned resources, `authorize:` on POST creation endpoints, and invalid field equality references.
3. **`TC-003` (SENSITIVE-LEAK):** Rejects credential fields (`password`, `password_hash`, tokens, keys) in response projections under all conditions. Rejects unexposed sensitive fields unless explicitly declared via `expose: [...]`.
4. **`TC-004` (MASS-ASSIGNMENT):** Flags primary keys (`id`), ownership foreign keys (e.g. `owner_id`), and credential fields in endpoint request bodies. Generates automated unified diff removing the server-controlled field from `body: [...]`.
5. **`TC-005` (SECRET-SCOPE):** Flags missing environment secrets (`DB_URL`, `JWT_SECRET`). Generates automated unified diff declaring the missing secrets in `secrets:`.

### 2.2 Unified Diff & Patch Engine (`src/trustc/fixes.py`)
- Standard unified diffs generated with `--- a/<filename>`, `+++ b/<filename>`, and exact line context.
- Diffs embed `baseSpecHash` to guarantee patches are only applied to the exact spec version they were generated against.
- Line endings strictly enforced as LF (`\n`) for byte-level determinism and cross-platform `git apply --check` compatibility on Windows.
- Batch edits preserve line alignment without duplicating content blocks.
- `apply_fix_to_file`: Atomic file replacement via temporary files, supporting `--rule`, `--line`, `--all`, and `--dry-run`. Rejects ambiguous multiple fixes when `--line` or `--all` is omitted.

### 2.3 Rule Explanation Subsystem (`src/trustc/rules_doc.py` & `src/trustc/rule_docs/*.md`)
- Markdown documentation authored for all 5 rules (`TC-001.md` through `TC-005.md`), detailing description, security rationale, bad examples, good examples, and automated fix behaviors.
- `trustc explain <rule_id>` outputs detailed guidance with support for `--json`.

### 2.4 Command Line Interface (`src/trustc/cli.py`)
- `trustc check <file>`: Evaluates security rules. Supports `--format {json,sarif,human}`, `--json`, and `--sarif`. Returns exit 0 on clean pass, 1 on security violations, 2 on invalid spec / file error.
- `trustc apply-fix <file>` (alias `trustc fix`): Applies automated diffs to disk or previews with `--dry-run`.
- `trustc explain <rule_id>`: Displays rule documentation.

---

## 3. Fixture Behavior Verification

| Fixture | Expected Behavior | Observed Result | Status |
|---|---|---|---|
| **F1** | Violates TC-001 (line 23), TC-003 (line 30), TC-004 (line 20), TC-005 (line 13) | Exactly 4 diagnostics at expected lines; exit 1 | PASS |
| **F2** | Fully hardened spec (Trip owner policy, User self policy, User projected `[id, email]`) | 0 diagnostics, exit 0 | PASS |
| **F3** | Valid ownership waiver (`authorize: public` on GET `/trips`) | TC-002 passes with waiver acknowledged; exit 0 | PASS |
| **F4** | Parse syntax error at line 23 column 25 | Spec error returned with exit 2 without application traceback | PASS |
| **F5** | Secret scope violation (missing `DB_URL`) | TC-005 diagnostic generated; exit 1 | PASS |
| **F6** | Mass assignment violation (`owner_id` in POST body) | TC-004 diagnostic generated; exit 1 | PASS |
| **F7** | Unsupported `role_only: admin` | TC-002 diagnostic generated; exit 1 | PASS |
| **F7b** | Invalid equality `authorize: id == current_user.id` on Trip | TC-002 diagnostic generated; exit 1 | PASS |
| **X01** | Missing `auth:` declaration | TC-001 diagnostic generated; exit 1 | PASS |
| **X02** | Contradictory `auth: public` with `authorize:` | TC-002 diagnostic generated; exit 1 | PASS |
| **X05** | Public POST on owned resource | TC-002 diagnostic generated; exit 1 | PASS |
| **X06** | Public User endpoint | TC-002 diagnostic generated; exit 1 | PASS |
| **X07** | Ownership waiver on User endpoint | TC-002 diagnostic generated; exit 1 | PASS |
| **X14** | `password_hash` in response projection | TC-003 diagnostic generated; exit 1 | PASS |
| **X15** | Sensitive field `phone` returned without `expose:` | TC-003 diagnostic generated; exit 1 | PASS |

### Required Fixed Flow Round-Trip
- Applying TC-001 automated diff to F1 yields a spec where only TC-003 remains at line 31.
- Manually projecting `User [id, email]` yields a file whose UTF-8 bytes and SHA-256 hash match canonical F2 byte-for-byte.

---

## 4. Gate Verification Evidence

The Stage 3 gate script (`python scripts/check-stage.py 3 --linter flake8-isort`) executed all 5 gates with overall exit code 0:

```
=== Stage 3 Gate: Security rules, check, diff fixes, explain, and SARIF output ===
Linter Toolchain: flake8-isort

[Gate 1/5] Running documented equivalent linter (flake8 + isort)...
[PASS] flake8 (E, F, W rules) passed.
[PASS] isort (I rule / import sorting) passed on all files without warning.

[Gate 2/5] Running type checks (mypy)...
[PASS] mypy type check passed (27 source files checked, 0 errors).

[Gate 3/5] Running pytest test suite (-m stage1 or stage2 or stage3 tests/)...
[PASS] Pytest suite passed (191 passed in 0.98s).

[Gate 4/5] Running CLI parse assertions on F2 (exit 0) and F4 (exit 2)...
[PASS] CLI parse F2 exit 0 verified.
[PASS] CLI parse F4 exit 2 verified.

[Gate 4b] Running CLI check, fix, and explain assertions...
[PASS] CLI check F2 exit 0 verified.
[PASS] CLI check F1 exit 1 verified.
[PASS] CLI check F4 exit 2 verified.
[PASS] CLI apply-fix F1 dry-run exit 0 verified.
[PASS] CLI explain TC-002 exit 0 verified.
[PASS] Published OASIS SARIF 2.1.0 schema validation passed for all fixtures.

[Gate 5/5] Running installed wheel smoke test outside repository...
PASS: Wheel built successfully: trustc-0.1.0-py3-none-any.whl (64394 bytes)
PASS: Archive contains all required resources (grammar size: 2517 bytes)
PASS: Fresh virtualenv initialized
PASS: Wheel installed in fresh environment
PASS: Module verified imported from fresh virtualenv site-packages
PASS: F2 parsed cleanly with specHash ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884
PASS: F4 structured error verified at line 23 column 25 without traceback
PASS: Installed trustc check F2 verified exit 0
PASS: Installed trustc check F1 verified exit 1
PASS: Cleaned up temporary virtualenv and test run directory
[PASS] Installed wheel smoke test passed outside repository.

============================================================
[PASS] Stage 3 gates passed.
============================================================
```

---

## 5. Review Findings & Corrections

Three independent review findings were identified and fully resolved:

### 5.1 Finding 1: isort Windows Encoding & Incomplete Checking
- **Issue:** Under Windows, default code page (cp1252) caused `isort` to emit `UserWarning: Unable to parse file` when reading UTF-8 characters, yet `isort` returned exit 0, allowing an incomplete check to receive PASS.
- **Resolution:**
  1. Replaced non-ASCII arrow/dash glyphs in `contracts.py`, `test_fixtures.py`, and `test_parser.py` with standard ASCII equivalents.
  2. Configured `isort` invocation in `scripts/check-stage.py` and log recording to force Python's UTF-8 mode via `[sys.executable, "-X", "utf8", "-m", "isort", "--check", "--diff", "src/", "tests/", "scripts/"]`.
  3. Hardened `scripts/check-stage.py`: inspects stdout/stderr for `"Unable to parse file"` or `"UserWarning"`. Any warning immediately forces `status = "FAIL"`, halting the gate and preventing incomplete checks from receiving PASS.
  4. Verified `isort` runs across all files with 0 warnings, 0 diffs, and exit 0. Retained in `review-logs/stage-3/isort.txt`.

### 5.2 Finding 2: TC-002 Overly Broad Advice & Waiver Scope
- **Issue:** Rule documentation suggested explicit equality checking for owned resources without excluding `POST`, and incorrectly stated waivers only apply to read/update.
- **Resolution:**
  1. **Excluded Owned POST:** Creating an owned resource (`POST`) assigns ownership to the authenticated caller automatically; `authorize:` equality predicates and waivers are strictly forbidden on `POST`.
  2. **Expanded Waiver Scope:** Aligned documentation with compiler specification §B4: ownership waivers (`authorize: public` on `auth: required` endpoints) are explicitly supported for list, read, update, and delete operations (`GET /collection`, `GET /collection/{id}`, `PUT /collection/{id}`, `PATCH /collection/{id}`, `DELETE /collection/{id}`).
  3. Updated `src/trustc/rule_docs/TC-002.md`, `src/trustc/rules_doc.py`, and `src/trustc/verifier.py` to maintain exact consistency between CLI explanation, documentation, and compiler diagnostics. Retained in `review-logs/stage-3/cli-explain.txt`.

### 5.3 Finding 3: Full Published SARIF 2.1.0 Schema Validation
- **Issue:** Verification only checked dictionary keys and regions, but did not demonstrate formal schema validation against the published OASIS SARIF 2.1.0 JSON schema.
- **Resolution:**
  1. Bundled the normative OASIS SARIF 2.1.0 JSON schema at `src/trustc/schemas/sarif-schema-2.1.0.json`.
  2. Added `jsonschema>=4.18` and `types-jsonschema>=4.20` dependencies.
  3. Implemented unit tests in `tests/unit/test_sarif.py` (`test_full_sarif_schema_validation_f1`, `test_full_sarif_schema_validation_all_canonical_fixtures`, and schema provenance verification).
  4. Created `scripts/validate_sarif_schema.py` and integrated strict schema validation into Gate 4b of `scripts/check-stage.py`.
  5. Retained validation log across all 17 canonical fixtures (F1-F7b, X01-X15) in `review-logs/stage-3/sarif-schema-validation.txt`.

---

## 6. Log Files & Artifacts

All verification logs are recorded in `review-logs/stage-3/`:
- `gate-result.json`: Machine-readable gate execution record (all gates PASS).
- `check-stage-3.log`: Full gate execution console output.
- `sarif-schema-validation.txt`: Retained evidence of full OASIS SARIF 2.1.0 schema validation for all 17 canonical fixtures.
- `flake8.txt`: Flake8 report (0 errors).
- `isort.txt`: Isort report (0 warnings, 0 diffs, exit 0).
- `mypy.txt`: Mypy report (27 source files checked, 0 errors).
- `pytest.txt`: Full test execution report (191 passed).
- `cli-check-f1.txt`: Captured JSON output for `trustc check F1.trust` (exit 1).
- `cli-check-f2.txt`: Captured JSON output for `trustc check F2.trust` (exit 0).
- `cli-check-f4.txt`: Captured JSON output for `trustc check F4.trust` (exit 2).
- `cli-apply-fix.txt`: Captured unified diff for `trustc apply-fix F1.trust --rule TC-001 --dry-run` (exit 0).
- `cli-explain.txt`: Captured documentation output for `trustc explain TC-002` (exit 0).
- `wheel-smoke.log`: Detailed isolated environment smoke test log (exit 0).
