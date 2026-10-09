# C — Fixtures and meaningful tests

## Canonical source fixtures

Copy `fixtures/*.trust` into repository `tests/fixtures/` without reformatting. They were reconstructed from the uploaded A document. F1/F2 source stays unchanged; v2 changes some expectations intentionally.

| Fixture | Expected check | Essential location/result |
|---|---|---|
| F1 | exit 1; TC-001 + TC-003 | 23:1 and 30:3; five rules run |
| F2 | exit 0 | Three endpoints; User GET now self-only |
| F3 | exit 0 | Four endpoints; authorize: public at 37:3; one ownership waiver |
| F4 | exit 2 | Missing colon at 23:25; no rules run |
| F5 | exit 1; TC-004 | owner_id in body at 20:23 |
| F6 | exit 1; TC-005 | JWT_SECRET undeclared, secrets at 13:1 |
| F7 | exit 1; TC-002 | role_only at 26:3; parser accepts for diagnostic |
| F7b | exit 1; TC-002 | wrong existing authorization field at 26:3 |

F1/F2/F3 line counts are 30/31/38. A final newline is present in this pack. Generate expected checks independently from A/B/C, with explicit reviewed messages and spans. Do not execute the implementation under test to invent its expected answer. Keep timestamps, random IDs and durations out of exact comparisons, but validate their types and cross-result consistency.

## Required fixed flow

F1 → apply proposed TC-001 diff → only TC-003 remains at line 31 → manually project User [id, email] → source exactly F2 → check → build → attack → export matching evidence.

| Fixture | v2 item routes tested | Completed attack summary |
|---|---|---|
| F2 | GET /trips/{id}; GET /users/{id} | 6 as_expected, 0 review, 0 unexpected, total 6 |
| F3 | F2 routes plus PUT /trips/{id}/visibility | 8 as_expected, 1 review, 0 unexpected, total 9 |

Every tested item endpoint gets anonymous, second_user and owner requests. For F3's waived PUT: anonymous 401 as_expected; second user 200 review; owner 200 as_expected. UI says “9 matched expectations · 1 policy review · 0 failed,” not “8/9 passed.” POST /trips is excluded from the item harness and explicitly listed in coverage; it is exercised by the generated-app integration tests.

## Additional fixtures to author in Stage 1 and enable at the indicated stage

| ID | Case | Expected behavior |
|---|---|---|
| X01 | Owned POST with auth: public | TC-002; no generated files |
| X02 | User GET with auth: public or authorize public | TC-002; never a public profile response |
| X03 | Multiple ownership edges / non-UUID edge / target other than User.id | reference/unsupported error, no rules |
| X04 | Unknown projected field; duplicate attributes; reserved identifiers | spec error with exact offending span |
| X05 | Ordinary non-credential sensitive field explicitly exposed | Check/build succeed, declaration names field; corresponding response assertion observes it |
| X06 | password_hash exposed | TC-003 despite expose declaration |
| X07 | id or owner in input; PATCH with extra JSON field | Compiler TC-004 for declared field; runtime 422 for undeclared field |
| X08 | Public owned GET/DELETE | Anonymous and second user allowed but review; owner allowed; isolated row per actor |
| X09 | Owner-filtered list containing rows from both actors | Returns caller's rows only |
| X10 | Same content, different specVersion; different content, same specVersion | Hash-driven identity works; mismatched evidence never joins |
| X11 | No eligible item endpoint | Empty coverage shown explicitly; no “all secure” message |
| X12 | Optional returns omitted on PUT | 200 with `{}`, still verifies persistent mutation |
| X13 | Valid narrow projection plus another route returning more fields | No schema collision or projection leak |
| X14 | Missing secrets block and multiple missing secrets | One coherent patch; no duplicated blocks |
| X15 | CRLF and non-ASCII comment before diagnostic token | Normalized hash and correct editor span |
| X16 | Invalid/expired/wrong-signature/wrong-audience JWT and nonexistent sub | 401; no traceback or token echo |

## Test levels and stop rules

Unit tests cover parsing edge cases, symbol validation, policy decisions, fix-context matching and selectors. Integration tests execute generated applications with real database effects. Harness tests use real loopback HTTP and process cleanup. Server tests cover streaming/replay, lifecycle and artifact identity. UI tests exercise real-server flows plus isolated visual states in clearly labelled mock mode.

Pattern searches and dataclass reflection are secondary lint checks, not security proofs. For denied PUT/PATCH/DELETE, inspect persistence afterward to ensure no unauthorized side effect. Verify authorized mutation actually occurs. Test generated Python syntax before running the mutation test.

When comparing API and CLI results normalize only documented transport identity/duration differences. Do not strip diagnostics, policies, hashes or coverage until a comparison passes.

Run completed-stage regression gates and the current meaningful tests. Do not run ten full rehearsals automatically or re-run unrelated suites without a remaining risk. No skipped mandatory security test at final release; optional Stage 9 may remain unimplemented and labelled as such.
