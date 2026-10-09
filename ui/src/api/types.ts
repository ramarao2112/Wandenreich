/**
 * Canonical v2 wire contracts for TrustC UI.
 *
 * Generated/mirrored from A-contracts.md and src/trustc/contracts.py.
 * Schema Version: 2
 */

export type ExitCode = 0 | 1 | 2 | 3 | 124 | 130;

export type RuleId = "TC-001" | "TC-002" | "TC-003" | "TC-004" | "TC-005";

export type Severity = "error" | "warn";

export type Actor = "anonymous" | "second_user" | "owner";

export type Outcome = "as_expected" | "review" | "unexpected";

export type EndpointMode = "owner" | "self" | "login_only" | "public";

export type SpecErrorKind = "syntax" | "reference" | "unsupported";

export type ForcedLineKind =
  | "route"
  | "auth"
  | "owner-set"
  | "query"
  | "owner-check"
  | "self-check";

export type DeclarationKind =
  | "public_auth"
  | "ownership_waiver"
  | "sensitive_exposure";

export type DeclarationObservationState = "observed" | "not_tested";

export type RunStatus =
  | "completed"
  | "refused"
  | "invalid_spec"
  | "error"
  | "cancelled"
  | "timed_out";

export type PhaseType =
  | "verify"
  | "render"
  | "publish"
  | "start"
  | "seed"
  | "request"
  | "cleanup";

export type PhaseState = "started" | "finished";

export interface Span {
  line: number;
  col: number;
  endLine: number;
  endCol: number;
}

export interface SpecRequest {
  spec: string;
  specVersion: number;
}

export interface ResultIdentity {
  schemaVersion: 2;
  specVersion: number;
  specHash: string;
  command: string;
  ms: number;
}

export interface SpecError {
  kind: SpecErrorKind;
  code: string;
  message: string;
  span: Span;
  snippet: string;
}

export type Fix =
  | { type: "diff"; baseSpecHash: string; diff: string; label: string }
  | { type: "prompt"; text: string };

export interface Diagnostic {
  ruleId: RuleId;
  ruleName: string;
  severity: Severity;
  span: Span;
  location: string;
  endpoint?: string;
  message: string;
  why: string;
  fix: Fix;
}

export interface RuleResult {
  ruleId: RuleId;
  ruleName: string;
  status: "passed" | "failed" | "not_applicable";
  checked: number;
  violations: number;
  summary: string;
}

export interface CheckResult extends ResultIdentity {
  kind: "check";
  ok: boolean;
  exitCode: 0 | 1 | 2;
  specErrors: SpecError[];
  diagnostics: Diagnostic[];
  rules: RuleResult[];
  rulesRun: number;
  endpoints: number;
}

export interface ForcedLine {
  line: number;
  specSpan: Span;
  kind: ForcedLineKind;
}

export interface GeneratedFile {
  path: string;
  content: string;
  forced: ForcedLine[];
}

export interface Declaration {
  id: string;
  endpoint: string;
  span: Span;
  kind: DeclarationKind;
  reason: string;
}

export interface EndpointPolicy {
  endpoint: string;
  mode: EndpointMode;
  ownerWaived: boolean;
  sensitiveFields: string[];
}

export interface BuildEvidence {
  schemaVersion: 2;
  buildId: string;
  specHash: string;
  specVersion: number;
  compilerVersion: string;
  templateVersion: string;
  rules: RuleResult[];
  endpointPolicies: EndpointPolicy[];
  structuralRestrictions: string[];
  declarations: Declaration[];
  limitations: string[];
}

export interface BuildSuccess extends ResultIdentity {
  kind: "build";
  status: "completed";
  exitCode: 0;
  buildId: string;
  files: GeneratedFile[];
  evidence: BuildEvidence;
}

export interface AttackCheck {
  name: string;
  expected: string;
  actual: string;
  passed: boolean;
}

export interface AttackStep {
  stepId: string;
  endpoint: string;
  actor: Actor;
  method: string;
  path: string;
  expect: number;
  got: number | null;
  outcome: Outcome | null;
  reason?: string;
  declarationIds: string[];
  checks: AttackCheck[];
}

export interface AttackCoverage {
  testedEndpoints: string[];
  excludedEndpoints: { endpoint: string; reason: string }[];
}

export interface DeclarationObservation {
  declarationId: string;
  stepIds: string[];
  state: DeclarationObservationState;
}

export interface AttackCompleted extends ResultIdentity {
  kind: "attack";
  status: "completed";
  exitCode: 0 | 1;
  buildId: string;
  artifactHash: string;
  steps: AttackStep[];
  asExpected: number;
  review: number;
  unexpected: number;
  total: number;
  coverage: AttackCoverage;
  declarationObservations: DeclarationObservation[];
}

export interface RunFailure extends ResultIdentity {
  kind: "build" | "attack";
  status: RunStatus;
  exitCode: 1 | 2 | 3 | 124 | 130;
  specErrors: SpecError[];
  diagnostics: Diagnostic[];
  error?: { code: string; message: string };
}

export type RunResult = BuildSuccess | AttackCompleted | RunFailure;

export interface LogLine {
  t: number;
  phase: string;
  text: string;
  ms?: number;
}

export type EventPayload =
  | { type: "phase"; phase: PhaseType; state: PhaseState }
  | { type: "log"; log: LogLine }
  | { type: "actor"; step: AttackStep }
  | { type: "result"; result: RunResult };

export interface RunEvent {
  schemaVersion: 2;
  runId: string;
  specVersion: number;
  specHash: string;
  seq: number;
  payload: EventPayload;
}

export interface RunAccepted {
  runId: string;
  specVersion: number;
  specHash: string;
}

export interface ApiError {
  error: { code: string; message: string };
}

export interface RuleMeta {
  id: RuleId;
  name: string;
}

export interface ServerMeta {
  schemaVersion: 2;
  sessionId: string;
  version: string;
  port: number;
  target: string;
  rules: RuleMeta[];
}

export interface ExampleSpec {
  id: string;
  title: string;
  subtitle: string;
  expectedCheck: "pass" | "fail";
  expectedReview: boolean;
  spec: string;
}

export interface RuleDocResponse {
  id: string;
  name: string;
  checks: string[];
  flaw: string;
  fixType: string;
  refused: string;
  accepted: string;
}

export interface RunStatusResponse {
  runId: string;
  state: "running" | "terminal";
  result: RunResult | null;
}

