# TrustC — staged build pack v2

Prepared 6 October 2026. Status: proposed replacement build specification, not implemented software.

## Start here

Keep the eight-stage sequence. This pack repairs contracts, narrows ambiguous language features, and adds the missing failure-path and security tests. It is self-contained for the MVP; the unavailable Master Build Document and mockup ZIP are not prerequisites.

Copy this folder into `docs/handoff-v2/` inside your TrustC repository. Open the repository in Antigravity. Read `01-REVIEW-AND-DECISIONS.md` once, then use the prompt below. Run one stage at a time and bring its handoff back for review if desired. Do not paste all stages into one implementation request.

```text
Build TrustC Stage 1 using docs/handoff-v2/00-START-HERE.md,
A-contracts.md, B-compiler-spec.md, C-fixtures-and-tests.md,
and stage-1-setup-and-fixtures.md in that folder.
Treat this v2 pack as the selected proposal. Inspect the existing repository
first and preserve unrelated work. Implement Stage 1 only, run its gates,
and write docs/progress/stage-1.md with actual commands, results, changed
files, limitations, and the next-stage prompt. Do not claim checks passed
unless you ran them. Do not proceed to Stage 2 in this turn.
```

For later stages change the number and stage filename. Each stage specifies prerequisites, outputs, tasks, gates and a handoff. If a prerequisite fails, repair it before advancing. Do not silently rewrite contracts to make a failing test pass.

## Authority

1. Explicit user decisions recorded in the repository.
2. This pack: A for wire contracts; B for language/compiler behavior; C for fixtures and behavioral expectations; D for UI behavior and presentation.
3. Stage files for implementation order and gates.
4. Original UI PDF for additional visual references where compatible.
5. Original patch/contracts, project overview and pitch deck as historical context only.

This is an intentional proposed contract revision to `schemaVersion: 2`. Do not merge v1 result types or its frozen golden files into v2 without migration. The review lists every consequential change. Once the user starts implementation with this pack, it is the selected baseline; routine choices within it do not need repeated approval.

## MVP scope

Python CLI, TrustSpec parser, typed IR, five security rules, FastAPI code generation, real local HTTP access tests, a local orchestration server, one-screen web UI, honest build evidence and demo instructions. User identities are seeded for testing; a production signup/login service is outside the MVP.

Optional natural-language input is a separately gated extension in `optional-9-ai-front-door.md`. No production deployment, arbitrary-code execution service, alternate backend target, RBAC, or unsafe-build CLI is part of the MVP.

| Stage | Result | Required predecessor | Planning allowance* |
|---|---|---|---|
| 1 | Runnable packaging, contracts, reference fixtures | None | 1–2 days |
| 2 | Grammar, positions, validation, typed IR | 1 | 2–3 days |
| 3 | Check, diagnostics, fixes, explain | 2 | 2 days |
| 4 | Runnable generated backend with verified behavior | 3 | 3–4 days |
| 5 | Real HTTP access tests and bounded cleanup | 4 | 2 days |
| 6 | Local API, streaming, cancellation, immutable artifacts | 5 | 2 days |
| 7 | Improved workbench connected to real results | 6 | 3–4 days |
| 8 | Release validation, demo, documentation | 7 | 1–2 days |

*Planning estimates, not delivery promises. A roughly 20-day build needs tight scope and relevant experience. Finish the runnable core before optional polish. Stage 7 is split into small milestones; do not postpone real wiring until every screen is finished.

## Repository layout to establish

```text
src/trustc/       CLI, contracts, parser, IR, verifier, fixes, codegen, attack, server
tests/           unit, contract, generated-app, harness, server and integration tests
tests/fixtures/  checked-in TrustSpec samples
tests/expected/  independently specified reference expectations
ui/              React/TypeScript workbench and Playwright tests
scripts/         scoped smoke, reset and release-check commands
docs/progress/   one factual handoff per completed stage
docs/decisions/  explicit departures from this baseline
docs/handoff-v2/ this pack
```

## Toolchain policy

Use Python 3.12 and a supported Node LTS compatible with the selected Vite/React packages. Stage 1 checks official package requirements, resolves compatible stable versions and records exact locks; this document does not pretend to know which pins will work on your machine. Do not upgrade dependencies in every stage. Keep runtime, generated-app, server, and development dependencies explicit; include `email-validator` if using Pydantic EmailStr. FastAPI/uvicorn are required for the server as well as generated apps.

Default UI stack: React, TypeScript, Vite, CodeMirror 6, Zustand, lucide-react, bundled IBM Plex fonts, Playwright and axe integration. No chart library or component framework is needed.

## Stage completion standard

- List the tests actually executed, their outcomes, skips and reasons.
- Demonstrate the stage's user-visible command or interaction.
- Keep completed-stage regressions passing. Do not add broad xfails that can hide import errors.
- Record changed files, contract effects, known limits and next prompt in `docs/progress/stage-N.md`.
- Tag `stage-N-done` only after its required gates pass; never overwrite an existing tag.
- Use repository-local temp directories and tracked child process handles. Never kill every uvicorn process or delete arbitrary `/tmp` directories.
- The implementation agent may work autonomously within the selected stage. Sub-agents are not required.

## Included reference material

`fixtures/` contains F1–F7b reconstructed from the uploaded specifications. A/C define revised v2 expectations; do not assume the original attack counts still apply. `01-REVIEW-AND-DECISIONS.md` explains the missing source assets and the proposed changes.

The supplied documents were reviewed; no TrustC implementation, live security run, or performance benchmark has been completed by preparing this pack.
