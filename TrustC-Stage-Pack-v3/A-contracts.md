# A — Canonical v2 wire contracts

## Conventions

JSON is camelCase. Python uses Pydantic models with aliases and rejects unknown request fields. TypeScript is generated from the checked-in JSON Schema or maintained with a schema-conformance gate; do not maintain two drifting handwritten sources. Stage 1 converts these definitions to executable schema models. Unknown syntax is a specification error, not a compiler crash.

UTF-8 input is limited to 262144 bytes. Normalize CRLF/CR to LF before hashing, parsing and fixing; do not trim or reformat. `specHash` is lowercase SHA-256 of normalized UTF-8 text. Positions are 1-based Unicode code-point columns; browser adapters convert CodeMirror offsets accordingly. `specVersion` is a nonnegative client edit counter, echoed but never trusted as content identity. CLI uses 0. UUID strings identify sessions, runs, builds and attack steps.

## Types

```ts
type ExitCode = 0 | 1 | 2 | 3 | 124 | 130;
type RuleId = 'TC-001'|'TC-002'|'TC-003'|'TC-004'|'TC-005';
interface Span { line: number; col: number; endLine: number; endCol: number }
interface SpecRequest { spec: string; specVersion: number }
interface ResultIdentity {
  schemaVersion: 2; specVersion: number; specHash: string;
  command: string; ms: number;
}
interface SpecError {
  kind: 'syntax'|'reference'|'unsupported'; code: string;
  message: string; span: Span; snippet: string;
}
type Fix =
  | {type:'diff'; baseSpecHash:string; diff:string; label:string}
  | {type:'prompt'; text:string};
interface Diagnostic {
  ruleId: RuleId; ruleName: string; severity:'error'|'warn';
  span:Span; location:string; endpoint?:string;
  message:string; why:string; fix:Fix;
}
interface RuleResult {
  ruleId:RuleId; ruleName:string;
  status:'passed'|'failed'|'not_applicable';
  checked:number; violations:number; summary:string;
}
interface CheckResult extends ResultIdentity {
  kind:'check'; ok:boolean; exitCode:0|1|2;
  specErrors:SpecError[]; diagnostics:Diagnostic[];
  rules:RuleResult[]; rulesRun:number; endpoints:number;
}
interface ForcedLine {
  line:number; specSpan:Span;
  kind:'route'|'auth'|'owner-set'|'query'|'owner-check'|'self-check';
}
interface GeneratedFile {path:string; content:string; forced:ForcedLine[]}
interface Declaration {
  id:string; endpoint:string; span:Span;
  kind:'public_auth'|'ownership_waiver'|'sensitive_exposure';
  reason:string;
}
interface BuildEvidence {
  schemaVersion:2; buildId:string; specHash:string; specVersion:number;
  compilerVersion:string; templateVersion:string; rules:RuleResult[];
  endpointPolicies:{endpoint:string; mode:'owner'|'self'|'login_only'|'public';
    ownerWaived:boolean; sensitiveFields:string[]}[];
  structuralRestrictions:string[]; declarations:Declaration[];
  limitations:string[];
}
interface BuildSuccess extends ResultIdentity {
  kind:'build'; status:'completed'; exitCode:0; buildId:string;
  files:GeneratedFile[]; evidence:BuildEvidence;
}
type Actor = 'anonymous'|'second_user'|'owner';
type Outcome = 'as_expected'|'review'|'unexpected';
interface AttackStep {
  stepId:string; endpoint:string; actor:Actor; method:string; path:string;
  expect:number; got:number|null; outcome:Outcome|null;
  reason?:string; declarationIds:string[];
  checks:{name:string; expected:string; actual:string; passed:boolean}[];
}
interface AttackCoverage {
  testedEndpoints:string[];
  excludedEndpoints:{endpoint:string; reason:string}[];
}
interface AttackCompleted extends ResultIdentity {
  kind:'attack'; status:'completed'; exitCode:0|1;
  buildId:string; artifactHash:string; steps:AttackStep[];
  asExpected:number; review:number; unexpected:number; total:number;
  coverage:AttackCoverage;
  declarationObservations:{declarationId:string; stepIds:string[];
    state:'observed'|'not_tested'}[];
}
interface RunFailure extends ResultIdentity {
  kind:'build'|'attack';
  status:'refused'|'invalid_spec'|'error'|'cancelled'|'timed_out';
  exitCode:1|2|3|124|130;
  specErrors:SpecError[]; diagnostics:Diagnostic[];
  error?:{code:string; message:string};
}
type RunResult = BuildSuccess | AttackCompleted | RunFailure;
interface LogLine {t:number; phase:string; text:string; ms?:number}
type EventPayload =
  | {type:'phase'; phase:'verify'|'render'|'publish'|'start'|'seed'|'request'|'cleanup'; state:'started'|'finished'}
  | {type:'log'; log:LogLine}
  | {type:'actor'; step:AttackStep}
  | {type:'result'; result:RunResult};
interface RunEvent {
  schemaVersion:2; runId:string; specVersion:number; specHash:string;
  seq:number; payload:EventPayload;
}
interface RunAccepted {runId:string; specVersion:number; specHash:string}
interface ApiError {error:{code:string; message:string}}
```

No HTML is trusted from diagnostics; render messages as text and endpoint names in separate components. Check results with specErrors have no diagnostics/rules and rulesRun=0. In a successfully parsed check all five rules run, including zero-applicability rules. A rule with zero applicable checks says not_applicable; never display it as tested protection.

Exit codes: 0 completed without unexpected behavior; 1 verifier refusal or completed test failure; 2 invalid specification; 3 execution/infrastructure error; 124 timeout; 130 cancelled. Warnings do not refuse a build. These codes have the same meaning in CLI JSON, API and SSE.

Result validation must enforce status/code combinations. A completed attack has no null outcomes; total equals the three outcome counts and the number of steps. Transport errors are execution errors with partial streamed evidence, not success or a fabricated received status. A zero-step attack has explicit empty coverage and UI says “No eligible endpoints tested.”

## HTTP API

The server binds 127.0.0.1. JSON mutation requests use Content-Type application/json and the configured allowed Origin. See Stage 6 for Host/Origin and request-limit enforcement.

| Method/path | Input | Response |
|---|---|---|
| GET /api/meta | — | {schemaVersion:2, sessionId, version, port, target, rules:[{id,name}]} |
| GET /api/examples | — | [{id,title,subtitle,expectedCheck:'pass' or 'fail',expectedReview:boolean,spec}] |
| GET /api/rules/{id} | — | {id,name,checks,flaw,fixType,refused,accepted} |
| POST /api/check | SpecRequest | CheckResult; query format=sarif returns SARIF |
| POST /api/build | SpecRequest | 202 RunAccepted |
| POST /api/attack | SpecRequest plus optional buildId | 202 RunAccepted |
| GET /api/runs/{runId}/events | Last-Event-ID header | SSE RunEvent stream |
| GET /api/runs/{runId} | — | {runId,state:'running' or 'terminal',result?:RunResult} |
| DELETE /api/runs/{runId} | — | 202 {runId,state:'cancelling'} until cleanup; 204 if already terminal |
| GET /api/builds/{buildId}/out.zip | — | Immutable artifact ZIP |

These are ten method/path operations. Syntax-only lint is optional and deferred; do not return a different shape from /api/check in the MVP. API errors: 400 malformed request, 403 forbidden origin/host, 404 unknown identifier, 409 busy or build/spec mismatch, 410 expired run/build, 413 too large, 500 sanitized internal error. Accepted compiler failures are results, not HTTP 500.

SSE uses `event: trustc`, `id: <runId>:<seq>`, `data: <RunEvent JSON>` followed by a blank line. Sequences start at 1. Keep replayable events for 15 minutes after termination, bounded to 4096 events or 4 MiB per run; exceeding the cap terminates with a sanitized resource-limit error after cleanup, never unbounded memory. Preserve capacity for the final event. A reconnect replays only later sequences for the same run. An invalid cursor is 400; expired history 410. Heartbeats are comment frames every 5 seconds and do not change sequence numbers.

One server build/attack runs at a time. Check remains available and is isolated from the active worker. Exactly one result event follows cleanup; CLI and server own top-level event emission so nested build work never emits an early terminal event. After terminal, the client closes EventSource and may query the retained result. Restart changes sessionId and invalidates old server run/build IDs.

## Evidence and identity

CLI attack builds and tests its own artifact. UI attack supplies a buildId, and the server requires a matching specHash/compiler/template version before testing an isolated copy of that exact artifact. Hash sorted relative paths and bytes for executable generated files; exclude the evidence file to avoid self-reference. Do not mutate stored builds during tests. Evidence joins require buildId, specHash and artifactHash to agree; specVersion alone is insufficient.

The downloaded build report is build evidence only. A combined UI export is a separate object `{build:BuildEvidence, attack:AttackCompleted|null}`. Never silently rewrite a downloaded build to claim runtime tests happened. A declaration becomes observed only when a named test checks that declaration's behavior; a passed unrelated request cannot confirm exposure.

CLI command strings use the actual input filename, shell-escaped for display. Web commands use `spec.trust` and explain that the current spec must first be saved with that name. Copying a diff or switching tabs does not pretend a CLI action was executed.
