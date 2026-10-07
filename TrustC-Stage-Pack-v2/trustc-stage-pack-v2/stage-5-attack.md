# Stage 5 — Live local access harness

## Goal and dependencies

`trustc attack` produces real HTTP observations and cleans up on every terminal path. Stage 4 passes. Read A events/results and C revised counts. Harness is limited to locally generated artifacts; no remote URL target or arbitrary user code input.

## Work

1. Implement a harness accepting a verified program and matching generated artifact, an event callback and a cancellation/deadline context. CLI builds first; server can later supply an immutable matching build. Keep nested build events nonterminal. Exactly one top-level RunResult ends the operation.
2. Create a run-owned temporary working directory, SQLite database and random test JWT secret. Pass only needed configuration to the generated-app child. Bind loopback on an OS-assigned port using a prebound socket where supported; otherwise bounded collision retry with readiness checks. No unbounded sleep and no hardcoded port assumption.
3. Start the generated app, wait for bounded readiness, seed User A/User B and a resource instance. Use real httpx loopback requests with connect/read deadlines. Record pending actor event before the request and resolved event immediately afterward.
4. Test every supported owned or User-self item endpoint. Execute all three actors in a deterministic order, but use fresh/restored resource state for each actor to handle allowed DELETE/update without contaminating the next request. Confirm denied writes did not persist and allowed writes did. Do not rely only on response codes.
5. Default owner/self policy expects 401/403/200 (DELETE owner 204). Waived owner policy expects 401/200/200 with second user review. Public item policy expects success for all, anonymous/second user review and owner as_expected. A mismatched response or failed body/persistence assertion is unexpected. Exact operation success codes come from B2, not a vague numeric 2xx expectation.
6. Assert selected response fields and relevant exposure observations without logging sensitive values. Coverage lists tested and excluded endpoint IDs. Item-only scope excludes collection/create routes with reasons; Stage 4 tests those separately. Empty coverage is explicit.
7. Cancellation and deadlines terminate/reap only the owned process (and its process group if applicable), close HTTP/DB handles, remove only the run-owned temp directory, and emit terminal status after cleanup. A worker crash/readiness/transport failure exits 3; timeout 124; cancel 130. Cleanup failure is a sanitized execution error with a scoped recovery path, never a success.
8. CLI displays real events and counts. Do not add a general --against flag. Mutation testing uses an internal test helper with an artifact copy; remove an entire owner-check AST statement, syntax-check it, then run the ordinary harness against that isolated copy.

## Gates

```bash
python scripts/check-stage.py 5
trustc attack tests/fixtures/F2.trust
trustc attack tests/fixtures/F3.trust
```

F2: six as_expected. F3: eight as_expected plus one review, nine total, exit 0. Modified Trip owner check: second-user request gets 200 instead of 403; exit 1 with real evidence. The unchanged User endpoint remains self-protected.

Test refused/invalid inputs never start an app; public DELETE with isolated actor state; zero eligible endpoint coverage; timeout/startup failure/cancel/KeyboardInterrupt; no active owned process/temp dir after termination; emitted event order and exactly one terminal result. Search captured logs, artifact contents and sanitized stdout/stderr for test secret/token values. Never dump a process environment merely to search it.

## Handoff

Record actual F2/F3/mutation outcomes, precise coverage, cleanup behavior and what remains untested. Explain why a policy review can match the specification and still require a human decision. Next: Stage 6 local server.
