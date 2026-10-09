# v3 changes and implementation clarifications

## Preserved

A, B, C, D and canonical F1–F7b bytes remain identical to the supplied v2 pack. This is a workflow revision, not schemaVersion 3. The full eight implementation stage documents and optional AI stage are included, with automatic-progression addenda.

## New

- Master/resume/stage prompts and durable state/acceptance templates.
- Stage 0 source audit based on the supplied Stage 1 report/logs.
- Mandatory lint/packaging/schema/types/X-case evidence and cumulative gate registration.
- Review deferred to the final ZIP, with provisional agent-reviewed visual baselines.
- Final archive reproducibility and honest incomplete-status requirements.

## Clarifications to record in repository decisions

1. Source byte limit is 262144 before normalization. Normalization replaces CRLF/CR only; preserve final-newline presence and other whitespace. Hash normalized UTF-8 bytes. This resolves the report's conflicting 64-KiB and trailing-newline statements.
2. `apply-fix` is canonical; `fix` may be a compatibility alias. Compiler rule meanings are fixed in B5; rate limiting is not TC-003.
3. Artifact identity needs a concrete manifest. A's BuildEvidence does not itself define an artifactHash field. Implement a build manifest stored with the artifact and keyed by buildId; the server uses it to compare AttackCompleted.artifactHash. Hash sorted relative executable file paths and bytes using an unambiguous length-prefixed encoding documented in code/tests. Exclude the manifest and report from the digest to avoid self-reference. For UI joins, buildId/specHash/compiler/template consistency plus the server's manifest check establishes the match; never compare to a nonexistent BuildEvidence.artifactHash property. Any new public wire field requires an explicit documented compatible extension or version decision, not a silent type change.
4. B's F2 11-file count names the base application files. A separately required manifest may increase the delivered count; record the actual list. Do not omit the manifest to satisfy an obsolete fixed count. Test required paths and manifest consistency rather than count alone.
5. The detailed stage gates remain mandatory even where an old handoff lists only a subset. A passing Stage 1 pytest selection does not waive lint, schema/type drift or wheel installation.
6. Inherited v1 mentions in B refer to the initial language/MVP scope, not the result schema; every result continues to use schemaVersion 2.

No source implementation has been independently inspected by this pack's author. Existing report discrepancies are audit targets, not a claim that every corresponding code path is wrong.
