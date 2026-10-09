# Stage 3 — Verification, diagnostics and explicit fixes

## Goal and dependencies

Implement `check`, `explain` and `apply-fix` with the five B5 rules. Stage 2 passes. Read A, B4/B5 and C. Files: verifier/, fixes/, rules_doc/, check.py, CLI, tests; change contracts only through a recorded baseline correction.

## Work

1. Define Rule protocol and registry, evaluate every rule on valid IR and retain per-rule applicability counts. Invalid syntax/reference/shape stops before the registry with exit 2. Warnings do not masquerade as errors.
2. Implement TC-001 end to end, then TC-002 through TC-005. Use one declared policy table across the verifier and lowering. TC-002 must cover role_only on every resource, public owned creation, public User access, wrong field and contradictory declarations.
3. Validate response fields before lowering. Credential exposure stays TC-003 even with expose; ordinary sensitive exposure creates a later evidence declaration. Body id/owner/credential declarations trigger TC-004. Needed secrets derive from the fixed template contract.
4. Create structured text diagnostics with precise spans, why and Fix union. Prompt fixes must list only supported alternatives for that endpoint. TC-001 diff is a suggested restrictive default, not the only valid business decision.
5. Produce unified diffs with baseSpecHash; apply through exact-context matching. Multiple instances require --line or explicit --all. Batch secret edits cannot duplicate blocks. Atomic file replacement follows successful patch parsing. Dry run prints diff and changes nothing.
6. Create one rule-doc source for CLI and API. Implement JSON, human-readable and SARIF 2.1.0 outputs. Stage 3 validates SARIF against its chosen published schema and records the schema/version. Suggestions do not make network/LLM calls.
7. Export `check_text(text, spec_version=0)` returning A's CheckResult. Keep execution timing separate from semantic output. Error messages are sanitized; user text is never HTML.

## Gates

```bash
python scripts/check-stage.py 3
trustc check tests/fixtures/F2.trust --json
trustc apply-fix tests/fixtures/F1.trust --rule TC-001 --dry-run
trustc explain TC-002
```

The checker asserts F1/F4 exit codes, all fixture rule/spans, hash/refusal behavior, F1→F2 round trip, exact context rejection and output schema validation. Test fixes with `git apply --check` in isolated temp files as an independent compatibility check. Confirm X01/X02/X06 reject, X05 accepts with explicit exposure, and repeated/multiple secret fixes produce valid current text.

Do not change fixtures merely because code returns different diagnostics. Explain a genuine baseline correction in docs/decisions and update A/B/C/tests together if needed.

## Handoff

Record all five implemented triggers, runnable commands, expected-versus-actual results, supported fix options and residual limits. Explain the distinction between declared policy and correct policy. Next: Stage 4 runnable codegen.

## v3 autonomous completion and handoff

Follow 02-EXECUTION-RULES.md and register every applicable row in 03-GATE-MATRIX.md. Use the full stage requirements, not a subset summarized by an earlier report. Save actual command output and exit codes in review-logs/stage-3/; update docs/progress/stage-3.md, acceptance.csv and state.json. PASS requires current-stage mandatory gates and completed-stage regression checks. Fix failures locally; do not wait for ChatGPT review. If a mandatory gate cannot run, mark BLOCKED and preserve a resumable checkpoint.

On PASS, automatically continue to Stage 4 using its stage document.
