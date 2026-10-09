# Stage 2 — Grammar, positions, reference validation and IR

## Goal and dependencies

`trustc parse file.trust` produces a typed IR or a precise plain-language specification error. Stage 1 must pass. Read B1–B4, A positions and C expectations.

## Work

1. Build a minimal Lark LALR spike, then implement `grammar/trustspec.lark` with explicit indentation/newline treatment, keyword positions and B's fixed declaration order. Test grammar construction with available strict conflict checks. Do not replace TrustSpec with YAML silently.
2. Implement a source module for normalization, UTF-8 byte limit, hashes and spans. Test CRLF, final-newline absence, comment-only lines, tabs and non-ASCII comments. Missing colon F4 points to 23:25; unrelated errors retain their true location.
3. Create frozen typed IR nodes with operation enums and validated symbols. Track absent auth separately from public/required. Retain source spans for fields and endpoint attributes. No raw executable expression, SQL string or secret literal node.
4. Separate syntax parsing from reference/shape validation. Enforce B1/B2 names, one UUID ownership edge, identity resource, path patterns, return/body rules and no duplicates. Avoid reserved output names and case-insensitive router/schema collisions.
5. Resolve default owner and User self policies in IR while preserving explicit declarations. Wrong existing ownership fields and role_only must survive to Stage 3; unknown fields are reference errors. Never insert missing auth into source or silently select public.
6. Add `parse_text` returning Program or structured TrustSpecError. CLI parse JSON contains spans and inferred policies; malformed source exits 2 without traceback. Other implementation exceptions remain internal errors, not mislabelled syntax problems.
7. Include grammar and resource files in a built-wheel smoke test so an installed CLI works outside the repository cwd.

## Gates

```bash
python scripts/check-stage.py 2
trustc parse tests/fixtures/F2.trust
trustc parse tests/fixtures/F4.trust
```

Stage checker runs Stages 1–2 tests and asserts F4 exits 2. Do not infer success from the final command alone.

Required tests: all F inputs except F4 parse; F7 retains role_only; F7b retains wrong-field authorization; F2 has owner policy for Trip and self policy for User; F3 waiver span is 37:3. X03/X04 fail deterministically. Check duplicate endpoint attribute, malicious identifier/path, unsupported type, nested/ambiguous edge and source after endpoints. Use table-driven expected policies; snapshots are a supplement.

## Handoff

Record public interfaces, IR decisions, supported syntax, tested error positions and parser limitations. Explain why parsing a policy does not approve it. No claims of SQL injection safety solely from checking dataclass field names. Next: Stage 3 verification and fixes.

## v3 autonomous completion and handoff

Follow 02-EXECUTION-RULES.md and register every applicable row in 03-GATE-MATRIX.md. Use the full stage requirements, not a subset summarized by an earlier report. Save actual command output and exit codes in review-logs/stage-2/; update docs/progress/stage-2.md, acceptance.csv and state.json. PASS requires current-stage mandatory gates and completed-stage regression checks. Fix failures locally; do not wait for ChatGPT review. If a mandatory gate cannot run, mark BLOCKED and preserve a resumable checkpoint.

On PASS, automatically continue to Stage 3 using its stage document.
