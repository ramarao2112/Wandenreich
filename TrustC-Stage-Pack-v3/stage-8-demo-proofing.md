# Stage 8 — Release validation and the demo

## Goal and dependencies

Package a reproducible MVP and rehearse its real behavior. Stage 7 passes. No new core feature here. Optional AI input is separately scoped after this stage.

## Work

1. Implement `scripts/release-check.py`: clean environment installation from locks, wheel installation/data check, all mandatory stage gates, UI build and real-server end-to-end flow. Report exact environment and commands. Verify the generated project can run with its own requirements in a separate environment, not just because the compiler environment happens to contain packages.
2. Write root README: product scope, prerequisites, installation, CLI commands, local UI start, supported syntax, demo, limitations, five-rule catalog, ownership/self-access policy, public declarations and exposed-data behavior. Document generated-app identity seeding as test-only; no invented production login flow.
3. Create a scoped reset/start command tracking only this project's PIDs/workspace. Never blanket-kill uvicorn or clear unrelated temp files. Browser storage reset occurs through an explicit UI reset or `?reset=1`; a shell script cannot silently claim it cleared arbitrary browser storage.
4. Produce a demo script and Q&A sheet. Use observed results and source-to-generated-code trace. Include a clearly labelled recording only if recording capability exists; otherwise document how the presenter records it. Do not claim an unrecorded video exists.
5. Run one complete live rehearsal plus cold-start, network-disabled and failure-recovery checks. Repeat until concrete issues are resolved. The presenter should then practice enough to deliver smoothly; ten automated repeats are not a substitute for observation.
6. Package source, locks and docs without env files, JWTs, databases or temp artifacts. Run a secret-output check on release files. Do not publish or deploy unless separately requested. Mark optional/unimplemented features explicitly.

## Three-minute script

| Time | Action and point |
|---|---|
| 0:00–0:25 | Open F1. “This spec leaves authentication undeclared and returns a marked-sensitive field.” |
| 0:25–0:55 | Check, inspect diagnostic; apply restrictive auth diff; manually select id/email response. |
| 0:55–1:20 | Check passes; build; show ownership declaration forcing an actual generated check. |
| 1:20–2:05 | Test access; show Trip and User routes: anonymous blocked, another user blocked, owner allowed. |
| 2:05–2:35 | Open build evidence, test coverage and limits. Results are tied to this build. |
| 2:35–3:00 | Show equivalent CLI and explain the distinction between declared policy and tested behavior. |

Optional extra: F3's declared waiver, nine matches and one policy review. It is not evidence of an accidental compiler bypass. The sabotage integration test demonstrates a template failure separately; no unsafe production CLI is exposed.

## Failure drills and release gates

- Invalid spec refuses before publishing; existing build stays intact and visibly historical.
- Cancel/timeout cleans up child and temp files; no false pass state.
- Server disconnect produces Offline, reconnect resolves the existing run; restart requires rebuild.
- Network-disabled installed demo still works with bundled fonts and local assets. Dependency installation may require network beforehand.
- At 1440×900 and enlarged text the result and next action remain visible.
- Final report lists mandatory passes, any skipped optional work and exact tested commit.

```bash
python scripts/release-check.py
```

Do not quote the deck's security statistics unless their primary sources are independently verified for the presentation. The demo needs no external statistic to demonstrate its own behavior. Name prior art with accurate scope; avoid an unsupported novelty claim.

## Handoff

Write `docs/progress/stage-8.md` with release checklist, tests, installation smoke, observed rehearsal duration, limitations and release artifact paths. Tag stage-8-done only if gates pass. This is the MVP completion point; next steps are optional rather than hidden unfinished requirements.

## v3 autonomous completion and handoff

Follow 02-EXECUTION-RULES.md and register every applicable row in 03-GATE-MATRIX.md. Use the full stage requirements, not a subset summarized by an earlier report. Save actual command output and exit codes in review-logs/stage-8/; update docs/progress/stage-8.md, acceptance.csv and state.json. PASS requires current-stage mandatory gates and completed-stage regression checks. Fix failures locally; do not wait for ChatGPT review. If a mandatory gate cannot run, mark BLOCKED and preserve a resumable checkpoint.

On PASS, create the final review archive using 04-FINAL-REVIEW-HANDOFF.md. Independent review remains PENDING. Optional Stage 9 is separate.
