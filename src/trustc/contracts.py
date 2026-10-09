"""TrustC v2 wire contracts -- Pydantic models matching A-contracts.md.

All types use camelCase JSON aliases. Schema version 2 is enforced.
Discriminated unions validate status/exitCode combinations.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION: Literal[2] = 2
MAX_INPUT_BYTES = 262_144  # 256 KiB


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExitCode(int, Enum):
    OK = 0
    FAILURE = 1
    INVALID_SPEC = 2
    EXECUTION_ERROR = 3
    TIMEOUT = 124
    CANCELLED = 130


class RuleId(str, Enum):
    TC_001 = "TC-001"
    TC_002 = "TC-002"
    TC_003 = "TC-003"
    TC_004 = "TC-004"
    TC_005 = "TC-005"


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"


class Actor(str, Enum):
    ANONYMOUS = "anonymous"
    SECOND_USER = "second_user"
    OWNER = "owner"


class Outcome(str, Enum):
    AS_EXPECTED = "as_expected"
    REVIEW = "review"
    UNEXPECTED = "unexpected"


class EndpointMode(str, Enum):
    OWNER = "owner"
    SELF = "self"
    LOGIN_ONLY = "login_only"
    PUBLIC = "public"


class SpecErrorKind(str, Enum):
    SYNTAX = "syntax"
    REFERENCE = "reference"
    UNSUPPORTED = "unsupported"


class FixType(str, Enum):
    DIFF = "diff"
    PROMPT = "prompt"


class ForcedLineKind(str, Enum):
    ROUTE = "route"
    AUTH = "auth"
    OWNER_SET = "owner-set"
    QUERY = "query"
    OWNER_CHECK = "owner-check"
    SELF_CHECK = "self-check"


class DeclarationKind(str, Enum):
    PUBLIC_AUTH = "public_auth"
    OWNERSHIP_WAIVER = "ownership_waiver"
    SENSITIVE_EXPOSURE = "sensitive_exposure"


class RunStatus(str, Enum):
    COMPLETED = "completed"
    REFUSED = "refused"
    INVALID_SPEC = "invalid_spec"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class PhaseType(str, Enum):
    VERIFY = "verify"
    RENDER = "render"
    PUBLISH = "publish"
    START = "start"
    SEED = "seed"
    REQUEST = "request"
    CLEANUP = "cleanup"


class PhaseState(str, Enum):
    STARTED = "started"
    FINISHED = "finished"


class DeclarationObservationState(str, Enum):
    OBSERVED = "observed"
    NOT_TESTED = "not_tested"


# ---------------------------------------------------------------------------
# Shared models
# ---------------------------------------------------------------------------

class Span(BaseModel):
    """1-based source span with Unicode code-point columns."""

    line: int = Field(..., ge=1)
    col: int = Field(..., ge=1)
    end_line: int = Field(..., alias="endLine", ge=1)
    end_col: int = Field(..., alias="endCol", ge=1)

    class Config:
        populate_by_name = True
        from_attributes = True


class SpecRequest(BaseModel):
    spec: str
    spec_version: int = Field(..., alias="specVersion", ge=0)

    class Config:
        populate_by_name = True


class AttackRequest(BaseModel):
    spec: str
    spec_version: int = Field(..., alias="specVersion", ge=0)
    build_id: Optional[str] = Field(None, alias="buildId")

    class Config:
        populate_by_name = True


class SpecError(BaseModel):
    kind: SpecErrorKind
    code: str
    message: str
    span: Span
    snippet: str


class DiffFix(BaseModel):
    type: Literal["diff"] = "diff"
    base_spec_hash: str = Field(..., alias="baseSpecHash")
    diff: str
    label: str

    class Config:
        populate_by_name = True


class PromptFix(BaseModel):
    type: Literal["prompt"] = "prompt"
    text: str


Fix = Union[DiffFix, PromptFix]


class Diagnostic(BaseModel):
    rule_id: RuleId = Field(..., alias="ruleId")
    rule_name: str = Field(..., alias="ruleName")
    severity: Severity
    span: Span
    location: str
    endpoint: Optional[str] = None
    message: str
    why: str
    fix: Fix

    class Config:
        populate_by_name = True


class RuleResult(BaseModel):
    rule_id: RuleId = Field(..., alias="ruleId")
    rule_name: str = Field(..., alias="ruleName")
    status: Literal["passed", "failed", "not_applicable"]
    checked: int = Field(..., ge=0)
    violations: int = Field(..., ge=0)
    summary: str

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Result identity (common across results)
# ---------------------------------------------------------------------------

class ResultIdentity(BaseModel):
    schema_version: Literal[2] = Field(SCHEMA_VERSION, alias="schemaVersion")
    spec_version: int = Field(..., alias="specVersion", ge=0)
    spec_hash: str = Field(..., alias="specHash")
    command: str
    ms: int = Field(..., ge=0)

    class Config:
        populate_by_name = True

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(by_alias=True)


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------

class CheckResult(ResultIdentity):
    kind: Literal["check"] = "check"
    ok: bool
    exit_code: Literal[0, 1, 2] = Field(..., alias="exitCode")
    spec_errors: List[SpecError] = Field(default_factory=list, alias="specErrors")
    diagnostics: List[Diagnostic] = Field(default_factory=list, alias="diagnostics")
    rules: List[RuleResult] = Field(default_factory=list)
    rules_run: int = Field(..., alias="rulesRun", ge=0)
    endpoints: int = Field(..., ge=0)

    class Config:
        populate_by_name = True

    @model_validator(mode="after")
    def validate_check_consistency(self) -> "CheckResult":
        # ok <-> exitCode
        if self.ok and self.exit_code != 0:
            raise ValueError("ok=true requires exitCode=0")
        if not self.ok and self.exit_code == 0:
            raise ValueError("ok=false requires exitCode!=0")
        # specErrors present -> no diagnostics/rules, rulesRun=0, exitCode=2
        if self.spec_errors:
            if self.diagnostics:
                raise ValueError("specErrors present: diagnostics must be empty")
            if self.rules:
                raise ValueError("specErrors present: rules must be empty")
            if self.rules_run != 0:
                raise ValueError("specErrors present: rulesRun must be 0")
            if self.exit_code != 2:
                raise ValueError("specErrors present: exitCode must be 2")
        # Successfully parsed -> all 5 rules run
        if not self.spec_errors and self.exit_code != 2:
            if self.rules_run != 5:
                raise ValueError(f"Parsed spec must run all 5 rules, got {self.rules_run}")
            if len(self.rules) != 5:
                raise ValueError(f"Parsed spec must have 5 rule results, got {len(self.rules)}")
        return self


# ---------------------------------------------------------------------------
# Build types
# ---------------------------------------------------------------------------

class ForcedLine(BaseModel):
    line: int = Field(..., ge=1)
    spec_span: Span = Field(..., alias="specSpan")
    kind: ForcedLineKind

    class Config:
        populate_by_name = True


class GeneratedFile(BaseModel):
    path: str
    content: str
    forced: List[ForcedLine] = Field(default_factory=list)


class Declaration(BaseModel):
    id: str
    endpoint: str
    span: Span
    kind: DeclarationKind
    reason: str


class EndpointPolicy(BaseModel):
    endpoint: str
    mode: EndpointMode
    owner_waived: bool = Field(..., alias="ownerWaived")
    sensitive_fields: List[str] = Field(default_factory=list, alias="sensitiveFields")

    class Config:
        populate_by_name = True


class BuildEvidence(BaseModel):
    schema_version: Literal[2] = Field(SCHEMA_VERSION, alias="schemaVersion")
    build_id: str = Field(..., alias="buildId")
    spec_hash: str = Field(..., alias="specHash")
    spec_version: int = Field(..., alias="specVersion", ge=0)
    compiler_version: str = Field(..., alias="compilerVersion")
    template_version: str = Field(..., alias="templateVersion")
    rules: List[RuleResult] = Field(default_factory=list)
    endpoint_policies: List[EndpointPolicy] = Field(
        default_factory=list, alias="endpointPolicies"
    )
    structural_restrictions: List[str] = Field(
        default_factory=list, alias="structuralRestrictions"
    )
    declarations: List[Declaration] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class BuildSuccess(ResultIdentity):
    kind: Literal["build"] = "build"
    status: Literal["completed"] = "completed"
    exit_code: Literal[0] = Field(0, alias="exitCode")
    build_id: str = Field(..., alias="buildId")
    files: List[GeneratedFile] = Field(default_factory=list)
    evidence: BuildEvidence

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Attack types
# ---------------------------------------------------------------------------

class AttackCheck(BaseModel):
    name: str
    expected: str
    actual: str
    passed: bool


class AttackStep(BaseModel):
    step_id: str = Field(..., alias="stepId")
    endpoint: str
    actor: Actor
    method: str
    path: str
    expect: int
    got: Optional[int] = None
    outcome: Optional[Outcome] = None
    reason: Optional[str] = None
    declaration_ids: List[str] = Field(default_factory=list, alias="declarationIds")
    checks: List[AttackCheck] = Field(default_factory=list)

    class Config:
        populate_by_name = True

    @model_validator(mode="after")
    def validate_step_id_uuid(self) -> "AttackStep":
        try:
            uuid.UUID(self.step_id)
        except Exception:
            raise ValueError(f"stepId must be a valid canonical UUID string, got: {self.step_id}")
        return self


class AttackCoverage(BaseModel):
    tested_endpoints: List[str] = Field(default_factory=list, alias="testedEndpoints")
    excluded_endpoints: List[Dict[str, str]] = Field(
        default_factory=list, alias="excludedEndpoints"
    )

    class Config:
        populate_by_name = True


class DeclarationObservation(BaseModel):
    declaration_id: str = Field(..., alias="declarationId")
    step_ids: List[str] = Field(default_factory=list, alias="stepIds")
    state: DeclarationObservationState

    class Config:
        populate_by_name = True


class AttackCompleted(ResultIdentity):
    kind: Literal["attack"] = "attack"
    status: Literal["completed"] = "completed"
    exit_code: Literal[0, 1] = Field(0, alias="exitCode")
    build_id: str = Field(..., alias="buildId")
    artifact_hash: str = Field(..., alias="artifactHash")
    steps: List[AttackStep] = Field(default_factory=list)
    as_expected: int = Field(..., alias="asExpected", ge=0)
    review: int = Field(..., ge=0)
    unexpected: int = Field(..., ge=0)
    total: int = Field(..., ge=0)
    coverage: AttackCoverage
    declaration_observations: List[DeclarationObservation] = Field(
        default_factory=list, alias="declarationObservations"
    )

    class Config:
        populate_by_name = True

    @model_validator(mode="after")
    def validate_attack_consistency(self) -> "AttackCompleted":
        # completed attack has no null outcomes
        for step in self.steps:
            if step.got is None:
                raise ValueError(f"Completed attack step {step.step_id} has null got")
            if step.outcome is None:
                raise ValueError(f"Completed attack step {step.step_id} has null outcome")
        # total must equal sum of outcome counts
        if self.total != self.as_expected + self.review + self.unexpected:
            raise ValueError(
                f"total ({self.total}) != as_expected ({self.as_expected}) "
                f"+ review ({self.review}) + unexpected ({self.unexpected})"
            )
        if self.total != len(self.steps):
            raise ValueError(
                f"total ({self.total}) != len(steps) ({len(self.steps)})"
            )
        return self


# ---------------------------------------------------------------------------
# Run failure
# ---------------------------------------------------------------------------

class RunFailure(ResultIdentity):
    kind: Literal["build", "attack"]
    status: Literal["refused", "invalid_spec", "error", "cancelled", "timed_out"]
    exit_code: Literal[1, 2, 3, 124, 130] = Field(..., alias="exitCode")
    spec_errors: List[SpecError] = Field(default_factory=list, alias="specErrors")
    diagnostics: List[Diagnostic] = Field(default_factory=list, alias="diagnostics")
    error: Optional[Dict[str, str]] = None

    class Config:
        populate_by_name = True

    @model_validator(mode="after")
    def validate_failure_consistency(self) -> "RunFailure":
        valid_combos = {
            "refused": {1},
            "invalid_spec": {2},
            "error": {3},
            "cancelled": {130},
            "timed_out": {124},
        }
        allowed = valid_combos.get(self.status, set())
        if self.exit_code not in allowed:
            raise ValueError(
                f"status={self.status} requires exitCode in {allowed}, got {self.exit_code}"
            )
        return self


# Discriminated union
RunResult = Union[BuildSuccess, AttackCompleted, RunFailure]


# ---------------------------------------------------------------------------
# SSE / Streaming
# ---------------------------------------------------------------------------

class LogLine(BaseModel):
    t: int
    phase: str
    text: str
    ms: Optional[int] = None


class PhasePayload(BaseModel):
    type: Literal["phase"] = "phase"
    phase: PhaseType
    state: PhaseState


class LogPayload(BaseModel):
    type: Literal["log"] = "log"
    log: LogLine


class ActorPayload(BaseModel):
    type: Literal["actor"] = "actor"
    step: AttackStep


class ResultPayload(BaseModel):
    type: Literal["result"] = "result"
    result: RunResult


EventPayload = Union[PhasePayload, LogPayload, ActorPayload, ResultPayload]


class RunEvent(BaseModel):
    schema_version: Literal[2] = Field(SCHEMA_VERSION, alias="schemaVersion")
    run_id: str = Field(..., alias="runId")
    spec_version: int = Field(..., alias="specVersion", ge=0)
    spec_hash: str = Field(..., alias="specHash")
    seq: int = Field(..., ge=1)
    payload: EventPayload

    class Config:
        populate_by_name = True


class RunAccepted(BaseModel):
    run_id: str = Field(..., alias="runId")
    spec_version: int = Field(..., alias="specVersion", ge=0)
    spec_hash: str = Field(..., alias="specHash")

    class Config:
        populate_by_name = True


class RunStatusResponse(BaseModel):
    run_id: str = Field(..., alias="runId")
    state: Literal["running", "terminal"]
    result: Optional[RunResult] = None

    class Config:
        populate_by_name = True


class RunCancelResponse(BaseModel):
    run_id: str = Field(..., alias="runId")
    state: Literal["cancelling"] = "cancelling"

    class Config:
        populate_by_name = True


class ApiError(BaseModel):
    error: Dict[str, str]


# ---------------------------------------------------------------------------
# API meta
# ---------------------------------------------------------------------------

class RuleMeta(BaseModel):
    id: RuleId
    name: str


class RuleDocResponse(BaseModel):
    id: str
    name: str
    checks: str
    flaw: str
    fix_type: str = Field(..., alias="fixType")
    refused: str
    accepted: str

    class Config:
        populate_by_name = True


class ServerMeta(BaseModel):
    schema_version: Literal[2] = Field(SCHEMA_VERSION, alias="schemaVersion")
    session_id: str = Field(..., alias="sessionId")
    version: str
    port: int
    target: str
    rules: List[RuleMeta] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class ExampleSpec(BaseModel):
    id: str
    title: str
    subtitle: str
    expected_check: Literal["pass", "fail"] = Field(..., alias="expectedCheck")
    expected_review: bool = Field(..., alias="expectedReview")
    spec: str

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

RULE_NAMES: Dict[RuleId, str] = {
    RuleId.TC_001: "AUTH-REQUIRED",
    RuleId.TC_002: "OWNERSHIP-CHECK",
    RuleId.TC_003: "SENSITIVE-LEAK",
    RuleId.TC_004: "MASS-ASSIGNMENT",
    RuleId.TC_005: "SECRET-SCOPE",
}


def normalize_source(raw: str) -> str:
    """Normalize CRLF/CR to LF. Do not trim or reformat."""
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def spec_hash(normalized: str) -> str:
    """SHA-256 of normalized UTF-8 text, lowercase hex."""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def export_json_schema(output_dir: Path) -> Path:
    """Export all contract schemas to JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    schemas: Dict[str, Any] = {
        "CheckResult": CheckResult.model_json_schema(by_alias=True),
        "BuildSuccess": BuildSuccess.model_json_schema(by_alias=True),
        "AttackCompleted": AttackCompleted.model_json_schema(by_alias=True),
        "RunFailure": RunFailure.model_json_schema(by_alias=True),
        "RunEvent": RunEvent.model_json_schema(by_alias=True),
        "ServerMeta": ServerMeta.model_json_schema(by_alias=True),
    }

    for name, schema in schemas.items():
        path = output_dir / f"{name}.json"
        path.write_text(json.dumps(schema, indent=2) + "\n")

    return output_dir
