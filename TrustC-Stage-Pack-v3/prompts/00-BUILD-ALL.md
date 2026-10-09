# Paste this into Antigravity

Implement TrustC using the complete docs/handoff-v3 pack. I authorize you to complete the local core project stage by stage without waiting for ChatGPT review between stages. I will request independent review later.

Read 00-START-HERE.md, 02-EXECUTION-RULES.md, 03-GATE-MATRIX.md and 05-CHANGELOG-AND-CLARIFICATIONS.md. Use A/B/C/D as the shared behavioral contracts; preserve schemaVersion 2 and the canonical fixtures.

Inspect the existing repository. First execute stage-0-recover-stage-1.md to audit and repair the existing Stage 1, including lint, rule/fixture mapping, source normalization and limits, schema/types/locks/fixtures/packaging evidence. Do not throw away working code. Then complete stage-1 through stage-8 in order, using each complete stage file. Automatically advance after every mandatory current/prior-stage gate passes and the progress record is saved. Do not ask me to paste the next stage after each success.

Maintain docs/progress/state.json, acceptance.csv, stage reports and sanitized review-logs. Create meaningful tests, run real generated-app/database/HTTP/browser checks where required, and fix failures. Never weaken security policy, tests or lint to claim success. Report blocked mandatory checks honestly and keep independent review PENDING.

If a session limit stops you, save a checkpoint with the exact next action. Avoid unnecessary questions for routine implementation choices. Ask only if a genuine unresolved requirement or environment/authorization blocker cannot be safely resolved. Do not deploy, publish, push or invoke a paid AI provider.

Finish with Stage 8 release validation and 04-FINAL-REVIEW-HANDOFF.md. Create TrustC-final-review.zip and FINAL-REVIEW.md, give me the local demo commands and archive location. Defer optional Stage 9 unless I use its separate prompt. Start now by inspecting the current project and repairing Stage 1.
