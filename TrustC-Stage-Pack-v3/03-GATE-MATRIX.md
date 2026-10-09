# Required stage gates and evidence

This supplements, never replaces, the detailed test cases in each stage and C. Convert each compound row into individual rows in acceptance.csv. No mandatory row may be silently omitted.

| Stage | Required checks | Evidence to save |
|---|---|---|
| 0/1 | Audit corrections; exact F fixtures; X scenario definitions; source normalization/byte limit; contracts positive/negative unions; version-2 exported schema and TypeScript drift; lint/typecheck; source and wheel installs outside repo; locked extras; CLI help/version; unimplemented stage rejection | Contract/schema/types files, fixture provenance, locks/tool versions, install manifests, command logs, actual Git state |
| 2 | All F parser cases; F4 exact span; F7/F7b preserved for verifier; X03/X04 rejection; Unicode/CRLF/no-final-newline spans; names/path/shape validation; immutable IR; wheel grammar inclusion | IR and error examples, independent expected spans, installed-wheel parse logs |
| 3 | Five rules and all F outcomes; X01/X02/X05/X06/X07/X14; exact-context/base-hash fixes; F1→F2; independent patch application; JSON/human/SARIF conformance; CLI codes | Rule table, diagnostic comparisons, dry-run and temporary-file patch logs, schema validation |
| 4 | Real generated app/database; all supported methods; owner assignment/list filtering/self-access; denied writes unchanged; accepted writes persist; request injection/extra fields; exact projections/null rules; JWT rejection; publication rollback; template wheel inclusion | Actual HTTP and database assertions, sanitized generated-app logs, independent generated dependency environment |
| 5 | Real loopback harness; F2 6 expected/F3 8 expected+1 review; test-only ownership mutation detected; X08/X11; isolated destructive cases; refusal never starts app; crash/cancel/timeout cleanup; one terminal event | Per-actor assertions, coverage/exclusions, mutated-vs-original result, child/temp cleanup checks, secret-redaction checks |
| 6 | All ten A API operations; CLI parity; real SSE/replay/reconnect; concurrent 409; cancellation/publication races; deadlines; Host/Origin/body/path rejection; build/hash identity; download isolation; restart invalidation | API/SSE logs, smoke-server output, lifecycle and artifact integrity evidence |
| 7 | Typecheck/lint/build/unit tests; real-server browser flows; required D states; stale edit/fix/build handling; offline/cancel/timeout/restart; evidence joins; keyboard/axe; 1440×900, 1024px, narrow and zoom layouts | Browser traces/failure reports, screenshots, accessibility results, Live/Mock isolation checks, agent visual observations |
| 8 | Fresh release install from locks; cumulative checks; wheel contents; generated app standalone install; production UI; live demo rehearsal; installed network-disabled demo; failure recovery; sanitized archive | Release report, exact revision, measured demo timing, artifact manifest, limitations, final review ZIP |
| Optional 9 | Adapter unit tests and malicious/invalid output rejection; bounded requests; absent-key/timeout handling; deterministic core regression; optional separately authorized provider smoke | Separate optional status, mocked-vs-live labels, no secrets or paid-call claims |

## Evidence rules

PASS requires a successful assertion on observed behavior. NOT RUN is not PASS. A product command expected to exit 1/2/3/124/130 passes its test only if the checker explicitly asserts that code and relevant output/side effects. A test suite that collects zero tests fails its gate. A skipped mandatory test blocks completion.

Independent golden decisions are authored from A/B/C before implementing the relevant behavior, not copied from current output. Review a changed golden against the specification and record why. Runtime tests inspect DB state where relevant, not only status codes. Test counts provide traceability, not a coverage percentage.

Stage 1 may create scenario descriptors for runtime-only X cases; do not claim execution until the designated runtime stage. Preserve all F fixture bytes. Add variants under distinct names.
