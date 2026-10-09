# TrustC — complete implementation pack v3

Prepared 7 October 2026. This is an implementation-instruction pack, not built application code.
Workflow version: 3. Wire contract remains schemaVersion: 2. Language remains the limited MVP described in B.

## What to do

1. Extract this archive and copy its contents into `docs/handoff-v3/` in your existing TrustC project. Keep existing code and earlier instructions intact.
2. Open the project root in Antigravity.
3. Copy the prompt from `prompts/00-BUILD-ALL.md` into Antigravity.
4. Let it repair Stage 1 and complete Stages 2–8 sequentially. You do not need to return to ChatGPT after each stage.
5. If Antigravity ends a session or hits a context/usage limit, use `prompts/99-RESUME.md` in a new session.
6. When finished, upload its `TrustC-final-review.zip` here for an independent review. The build agent's self-check is not an independent review.

Stage 9's optional AI extension has its own file and prompt. It is not required for the core project. No provider account, paid call or secret is needed for Stages 1–8.

## Reading order and authority

Explicit user instructions → A (wire contracts), B (compiler), C (fixtures), D (UI) → `02-EXECUTION-RULES.md` for workflow → current stage → gate matrix.
`stage-0-recover-stage-1.md` corrects observed report discrepancies; it does not invent evidence about unuploaded source.
`01-REVIEW-AND-DECISIONS.md` is the inherited v2 design rationale, not a review of the current code.

This pack supersedes earlier instructions to wait for ChatGPT at each stage. Implement one stage at a time, but automatically advance after its mandatory gates and completed-stage regression checks pass. Record routine choices and continue. Do not skip a mandatory failed or unrun gate and call its dependent stage complete.

## Files

- A/B/C/D: full behavior and design contracts, unchanged from the selected v2 baseline.
- stage-0: repair and audit the existing foundation.
- stage-1 through stage-8: implementation tasks, required tests and handoffs.
- optional-9: isolated AI extension.
- 02: execution, checkpoint and resume rules.
- 03: gate and evidence matrix.
- 04: final review packaging requirements.
- 05: verified pack changes and unresolved implementation details.
- prompts/: master, stage-specific and resume prompts.
- templates/: progress, acceptance and final review templates.
- fixtures/: eight canonical specifications, preserved byte-for-byte.
- PACK-MANIFEST.json: per-file SHA-256 values excluding the manifest itself.

## Completion standard

Core complete means Stages 1–8 passed at the recorded source revision, the installed generated application and real UI were exercised, and remaining limitations are explicit. Tests are never replaced by screenshots or confident prose. If tools or credentials prevent a required check, record BLOCKED/NOT RUN and prepare a partial review bundle with that status.
