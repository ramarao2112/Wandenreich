# Stage 0 — audit and repair the existing Stage 1

## Evidence available

The supplied handoff and logs reported 43 tests passing, mypy passing, Ruff failing with 12 errors, and untracked review-logs despite a clean-tree claim. Actual implementation source was not supplied for independent review. Inspect it now; do not recreate an existing project blindly. If no implementation exists, proceed to Stage 1 from scratch using these corrections.

## Mandatory repairs and audits

1. Fix Ruff errors without disabling configured rules. Stage 1's gate must run lint as well as pytest and fail if lint fails.
2. Audit code, rule registry placeholders, expected decisions, fixtures and prose against this mapping:

| ID | Meaning | Key fixture |
|---|---|---|
| TC-001 | AUTH-REQUIRED | F1 at 23:1 |
| TC-002 | OWNERSHIP-CHECK | F7/F7b at 26:3 |
| TC-003 | SENSITIVE-LEAK | F1 at 30:3 |
| TC-004 | MASS-ASSIGNMENT | F5 at 20:23 |
| TC-005 | SECRET-SCOPE | F6 at 13:1 |

Rate limiting is outside this MVP. A report-only mislabel requires a report fix; wrong code/expectations require implementation correction and independent tests.

3. Audit source normalization. A permits only CRLF/CR→LF conversion; no trimming, whitespace reformatting or forced final newline. The prior report claims a single trailing newline is enforced; verify and remove that behavior if present. Both newline-present and newline-absent specs parse, but their content hashes differ. CRLF versus LF equivalent input hashes match. Preserve multiple final newlines. Add focused regression cases.
4. Use A's 262144-byte UTF-8 source limit, not the report's 64 KiB. Check raw UTF-8 input size before normalization so normalization cannot shrink oversized input past the boundary. Test ASCII and multibyte boundaries. The server's 1 MiB request cap is a separate envelope limit.
5. Inspect all Stage 1 requirements, not only the report's nine acceptance rows: schemaVersion-2 JSON Schema, UI TypeScript types/drift test, pinned locks, dependency groups, source/wheel installation, X01–X16 case definitions and independent expectations, provenance and progress/decision/dependency docs. Runtime checks for later-stage X cases activate later; author their inputs/scenarios now without pretending they ran.
6. Check all A result/event variants, including positive BuildSuccess and AttackCompleted and negative discriminated-union cases. The previous test list alone does not establish complete contract conformance.
7. Align CLI names to stage specifications: `apply-fix` is the canonical Stage 3 command; a legacy `fix` alias may remain with identical behavior. Do not implement a different fix contract just to preserve a stub. Add parse in Stage 2 and serve in Stage 6.
8. Record the actually supported runtime and dependency metadata. Do not promise Python 3.9+ merely because one machine ran 3.9.6. Choose a supported compatible runtime at implementation time, lock tooling, and update prerequisites consistently. Verify required extras as well as dev-only installation.
9. Correct the Git status statement and report exact tested source identity. Logs may remain untracked if accurately recorded and included in review packaging.

## Exit

Run the full Stage 1 gate after repairs and produce `docs/progress/stage-0.md` and updated `stage-1.md`. If all requirements pass, continue automatically to Stage 2. No external ChatGPT approval is required. If blocked, preserve evidence and use 02's blocker rules.
