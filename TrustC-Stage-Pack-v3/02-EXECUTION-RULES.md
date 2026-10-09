# Execution rules — progress without repeated external review

## Authorization and boundaries

The user authorizes local implementation, routine bug fixes, dependency setup in project environments, testing, local demo processes, documentation and review packaging. Continue through the core stages without asking ChatGPT for approval. Preserve unrelated work; do not reset the repository or erase existing code. Do not deploy, publish, push commits, buy services, send messages or call a paid AI provider as part of this workflow. Local checkpoints may be committed only with scoped files; never `git add .` without reviewing the selection. A commit is optional; an inventory/hash checkpoint is sufficient.

Do not create a competing root instruction file automatically. Apply this pack within existing repository instructions; report real conflicts rather than hiding them.

## Repeated stage cycle

1. Read the current stage and its A/B/C/D dependencies; inspect existing implementation and last progress record.
2. Map each requirement to code, test, expected result and evidence. Preserve baseline fixtures and independently authored expectations.
3. Implement the smallest coherent milestone, including its real integration. Do not spend the whole stage building mocks.
4. Run targeted checks while developing. Fix implementation failures without weakening assertions, changing rule meaning, or moving required tests into optional groups.
5. Run the current cumulative stage gate once ready. Capture command, cwd, timestamps, source revision, stdout/stderr and actual exit code. Assert expected nonzero product exits explicitly; the overall checker exits 0 only when all required assertions pass.
6. Update `docs/progress/stage-N.md`, `docs/progress/acceptance.csv`, and `docs/progress/state.json`. Advance automatically when mandatory evidence is complete.

## Gate runner contract

`scripts/check-stage.py N` runs registered requirements for completed stages 1..N. Each stage has an explicit registry; an empty, missing or unimplemented selection fails. Lint, typing, schemas, packaging and browser checks cannot disappear merely because pytest passes. Propagate subprocess failure. Capture return codes before formatting/teeing output; a successful log command is not a successful test. Keep full logs in `review-logs/stage-N/` and a machine-readable gate result with each command and status. Required skips, collection errors and unavailable mandatory tools are failures/blocks, never PASS.

During development, stage-specific tests may run separately. At each stage boundary run the cumulative gate. Reuse a recent successful result only when its input/dependency/configuration fingerprint is unchanged and record that reuse; rerun after relevant edits. Final release uses fresh evidence for the final revision.

## Policy and contract decisions

Use B's policy table. In development fixtures, implement the documented F1→F2 correction; this is not permission to silently alter an end user's public/private policy in the running product. Product fixes still need explicit application and previews.

Routine internal choices may be recorded and implemented autonomously: directory naming, component decomposition, test helpers and compatible locked tools. For a genuine contradiction in observable behavior, record the conflicting clauses and proposed resolution. Use A for wire shape, B for language semantics, C for fixed fixture outcomes and D for presentation. If this cannot resolve a material conflict, block only dependent work and ask one focused question; do not invent a new security policy. Record implementation clarifications without silently changing schemaVersion 2.

## Failures and environment limits

Fix ordinary code/test problems locally. For missing tools, use supported installation in a project environment. Do not make global destructive changes or bypass permissions. For unavailable dependencies/browser binaries/network, record exact failure and reproducible commands. Work on independent tasks if useful, but do not claim downstream completion based on untested prerequisites. Never fabricate provider responses, HTTP observations, execution times or screenshots. Mock tests remain labelled and separate.

## Durable checkpoint

Use the state template in `templates/state.json`. Record last completed stage, active stage/milestone, source revision or content inventory, commands/results, blocker and exact next action. Do not store secrets. Update after meaningful milestones and before any session stop. Context/token limits cannot be solved by this prompt; the resume prompt rehydrates from files.

Stage statuses: NOT_STARTED, IN_PROGRESS, BLOCKED, PASS. PASS requires all mandatory stage rows in acceptance.csv to pass. Optional work may be DEFERRED in its own record. Human/independent review remains PENDING even when self-checks pass.

## UI review without waiting

At Stage 7, inspect actual screenshots and keyboard flows against D, fix clipping/contrast/state issues, and record observations. Adopt regression screenshots after this agent review, explicitly labelled provisional pending user/independent review. Do not claim the user approved a visual baseline. Keep before/after images for meaningful revisions.
