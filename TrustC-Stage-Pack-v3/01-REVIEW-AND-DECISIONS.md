# Review of the uploaded stage pack

## Assessment

The original sequence is good: contracts → parser → verifier → codegen → attack → server → UI → demo. Keep its diagnostic positions, independent fixtures, source provenance, real HTTP tests, labelled mock mode and stale-result behavior. The main work is resolving semantics and lifecycle gaps before implementing them.

Reviewed all ten uploaded Markdown files and the previously supplied UI PDF, project overview and pitch deck. The Master Build Document, `00-START-HERE.md` and `trustc-ui-mockups.zip` were referenced but not supplied. This pack does not claim to have read those missing assets.

## Findings and proposed resolutions

| Priority | Source finding | v2 resolution |
|---|---|---|
| Blocker | Stage 1/2 depend on missing start/master files; UI requires absent HTML/PNG/fonts | Supply a self-contained language contract and UI addendum. Establish new visual baselines; no claim of a 2% match to unavailable screenshots. |
| Blocker | Build/attack exit types allow 0/1, while syntax/reference errors require 2 | A defines all result statuses, including refusal, invalid input, cancellation and execution error. |
| Blocker | `run_attack -> AttackResult` cannot represent its documented refusal | Use a discriminated RunResult union with a common identity and explicit terminal statuses. |
| Blocker | SSE has no specified terminal error/cancel event; nested attack-build callbacks can finish the stream early | One event envelope, one terminal `result`, explicit phases, exactly one terminal event per run. |
| High | B-P3 rejects role_only early; B-P4/F7 require TC-002 later | Parse it, diagnose TC-002 for every role_only declaration, never generate it in v1. |
| High | Login-only `/users/{id}` can reveal another user's email; harness skips it | Proposed self-access restriction for User GET and real three-actor testing. F2 increases from 3 to 6 actor tests. |
| High | Public POST on an owned resource still needs current_user.id | Reject public owned-resource creation through TC-002. No anonymous ownership model in v1. |
| High | Multiple/non-User ownership edges have undefined meaning | One direct UUID edge to User.id per owned resource; reject unsupported relationships. |
| High | Report says zero sensitive fields even when expose allows them; owner counts ignore waivers | Count protected endpoints, waivers and selected sensitive fields separately. Never label declarations as proof of correct policy. |
| High | Secret held in subprocess environment conflicts with a test demanding absence from an environment dump | Ephemeral secrets may be passed only to the child environment; no environment dump, argv secret, token output, artifact or log disclosure. Do not claim resistance to local process inspection. |
| High | Refusal preserves old out/, but download means last successful build without identity | Immutable build IDs, spec hash, run ID and versioned downloads; failed current build cannot silently download old files. |
| High | Cancellation of a background thread may leave compilation/writes running | Supervised worker lifecycle, bounded termination, and publish only after successful current-run completion. |
| High | Sabotage by deleting tagged text can leave invalid Python or stop before the attack | Test-only AST mutation removes a complete owner-check statement; syntax-check, then require a real 200/403 mismatch. No exposed bypass flag. |
| Medium | A claims two actor steps for every public endpoint; B says one for auth:public | v2 tests all three actors on every eligible item endpoint, each against isolated state. |
| Medium | F3 UI displays “4/5 as expected” although the reviewed result also matched its declared behavior | Keep outcome categories, but show matched count separately from policy-review count. |
| Medium | `auth: required` is labelled “one correct fix,” though public is also expressible | Label as a proposed restrictive default; show diff and require a human click. |
| Medium | Only pass-path UI screens are required, while final demo requires missing failure states | Errors, refusal, stale results, cancellation, timeout, offline and amber review are MVP gates. |
| Medium | All UI screens mocked before real integration | Connect real Check at the first functional UI milestone, then Build and Attack incrementally. |
| Medium | Whole-report confirmation can falsely confirm sensitive exposure | Confirm each declaration only with relevant observed response/status evidence. Others remain untested. |
| Medium | Mutable model update/body rules, POST completeness and route return behavior are underspecified | B defines operation types, projection, missing returns, PATCH semantics and server-only fields. |
| Medium | Unused enum means string with no explicit constraint | v2 rejects enum until value syntax exists, instead of silently dropping its meaning. |
| Medium | Secret fields such as password_hash may be explicitly exposed | v2 permits reviewable exposure of ordinary marked-sensitive data but prohibits known credential fields in responses or writable bodies. |

These are proposed product decisions, not claims that the original code is vulnerable: no implementation was provided.

## Preserved fixture facts

F1 has 30 lines; F2 has 31; F3 has 38. F1 TC-001 points at 23:1 and TC-003 at 30:3. F4's insertion column is correctly 25; F5 owner_id starts at column 23. These were checked directly against the provided text, not guessed. F7 and F7b remain TC-002 tests.

## Security claim boundary

TrustC can enforce a restricted language and tested template behavior. No raw-query construct reduces a class of generation mistakes; field-name reflection tests do not prove arbitrary Python is safe. A malicious identifier, template defect, misconfigured token validator, inaccurate ownership model, or explicit public declaration needs separate handling. v2 tests those boundaries and avoids claims that any complete specification is necessarily secure.

## Implementation references consulted

These support implementation details, not a certification of this design. Stage 1 must check selected package versions against their own documentation.

- PyJWT API: fixed allowed algorithms and explicit required claims: https://pyjwt.readthedocs.io/en/stable/api.html
- SQLAlchemy async documentation: a separate AsyncSession for each concurrent task: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Starlette middleware documentation: configured allowed hosts and origins: https://www.starlette.io/middleware/

JWT policy in B (issuer, audience and expiry) is a design choice using these mechanisms. Local-server restrictions in Stage 6 are explicit product requirements, not a claim that CORS alone protects a local service.
