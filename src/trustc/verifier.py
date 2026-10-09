"""TrustC Stage 3 Verifier — five B5 security rules and CheckResult engine."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from trustc.contracts import (
    CheckResult,
    Diagnostic,
    Fix,
    PromptFix,
    RuleId,
    RuleResult,
    Severity,
    Span,
    SpecError,
    SpecErrorKind,
)
from trustc.fixes import (
    create_tc001_diff,
    create_tc004_diff,
    create_tc005_diff,
)
from trustc.ir import (
    AuthKind,
    AuthorizeEquality,
    AuthorizePublic,
    Program,
    is_credential_field,
)
from trustc.parser import TrustSpecError, parse_text
from trustc.rules_doc import RULES_INFO
from trustc.source import SourceError, check_input_size, normalize_source, spec_hash

REQUIRED_SECRETS = ("DB_URL", "JWT_SECRET")


def _make_span(line: int, col: int, end_line: int, end_col: int) -> Span:
    """Create a contracts.Span model instance."""
    return Span(line=line, col=col, endLine=end_line, endCol=end_col)


def _to_span(s: Any) -> Span:
    """Convert an IR/source Span dataclass into a contracts.Span model."""
    if isinstance(s, Span):
        return s
    return Span(
        line=s.line,
        col=s.col,
        endLine=s.end_line,
        endCol=s.end_col,
    )


def _make_diag(
    rule_id: RuleId,
    rule_name: str,
    severity: Severity,
    span: Span,
    location: str,
    message: str,
    why: str,
    fix: Fix,
    endpoint: Optional[str] = None,
) -> Diagnostic:
    """Create a Diagnostic model with typed fields matching alias contracts."""
    return Diagnostic(
        ruleId=rule_id,
        ruleName=rule_name,
        severity=severity,
        span=span,
        location=location,
        message=message,
        why=why,
        fix=fix,
        endpoint=endpoint,
    )


def _make_rule_result(
    rule_id: RuleId,
    rule_name: str,
    status: Literal["passed", "failed", "not_applicable"],
    checked: int,
    violations: int,
    summary: str,
) -> RuleResult:
    """Create a RuleResult model instance."""
    return RuleResult(
        ruleId=rule_id,
        ruleName=rule_name,
        status=status,
        checked=checked,
        violations=violations,
        summary=summary,
    )


def _make_check_result(
    *,
    ok: bool,
    exit_code: Literal[0, 1, 2],
    spec_hash: str,
    spec_version: int = 0,
    command: str = "check",
    ms: int = 0,
    spec_errors: Optional[List[SpecError]] = None,
    diagnostics: Optional[List[Diagnostic]] = None,
    rules: Optional[List[RuleResult]] = None,
    rules_run: int = 0,
    endpoints: int = 0,
) -> CheckResult:
    """Create a top-level CheckResult contract model instance."""
    return CheckResult(
        schemaVersion=2,
        specVersion=spec_version,
        specHash=spec_hash,
        command=command,
        ms=ms,
        ok=ok,
        exitCode=exit_code,
        specErrors=spec_errors or [],
        diagnostics=diagnostics or [],
        rules=rules or [],
        rulesRun=rules_run,
        endpoints=endpoints,
    )


# ---------------------------------------------------------------------------
# Individual Rule Evaluation
# ---------------------------------------------------------------------------

def _eval_tc001(
    program: Program, source: str, current_hash: str
) -> Tuple[RuleResult, List[Diagnostic]]:
    """TC-001 (AUTH-REQUIRED): Missing auth declaration."""
    diags: List[Diagnostic] = []
    checked = len(program.endpoints)

    for ep in program.endpoints:
        if ep.auth == AuthKind.ABSENT:
            # Span: endpoint keyword token
            ep_span = _make_span(
                ep.span.line,
                ep.span.col,
                ep.span.line,
                ep.span.col + len("endpoint") - 1,
            )
            diff_fix = create_tc001_diff(source, ep, current_hash)
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_001,
                    rule_name="AUTH-REQUIRED",
                    severity=Severity.ERROR,
                    span=ep_span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message=(
                        f"Endpoint '{ep.method} {ep.path}' is missing an authentication "
                        "declaration (auth: required | public)."
                    ),
                    why=(
                        "Unauthenticated endpoints expose operations without verifying "
                        "caller identity. By default, endpoints should require authentication "
                        "unless explicitly declared public."
                    ),
                    fix=diff_fix,
                )
            )

    status: Literal["passed", "failed", "not_applicable"] = (
        "passed" if not diags else "failed"
    )
    summary = (
        "All endpoints declare authentication"
        if not diags
        else f"{len(diags)} endpoint(s) missing auth"
    )
    return (
        _make_rule_result(
            rule_id=RuleId.TC_001,
            rule_name="AUTH-REQUIRED",
            status=status,
            checked=checked,
            violations=len(diags),
            summary=summary,
        ),
        diags,
    )


def _eval_tc002(
    program: Program, source: str, current_hash: str
) -> Tuple[RuleResult, List[Diagnostic]]:
    """TC-002 (OWNERSHIP-CHECK): Invalid, unsupported, or contradictory authorization policy."""
    diags: List[Diagnostic] = []
    checked = len(program.endpoints)

    for ep in program.endpoints:
        res = program.get_resource(ep.resource)
        is_owned = res.ownership_edge is not None
        is_user = (res.name == "User")

        # 1. role_only (unsupported)
        if ep.role_only is not None:
            span = _to_span(ep.role_only_span or ep.span)
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_002,
                    rule_name="OWNERSHIP-CHECK",
                    severity=Severity.ERROR,
                    span=span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message="Role-based authorization ('role_only') is unsupported in v1.",
                    why=(
                        "Role-based access control is not supported in TrustSpec v1. "
                        "Use resource ownership policies (owner-based checks) or explicit "
                        "public authorization."
                    ),
                    fix=PromptFix(
                        text=(
                            "Remove 'role_only'; creation automatically assigns caller as owner."
                            if ep.method == "POST"
                            else (
                                "Remove 'role_only' and use owner-based authorization on "
                                "read/update/delete "
                                "('authorize: <owner_field> == current_user.id') "
                                "or declare 'auth: required' for login-only access."
                            )
                        )
                    ),
                )
            )
            continue

        # 2. Public owned POST
        if is_owned and ep.method == "POST" and ep.auth == AuthKind.PUBLIC:
            span = _to_span(ep.auth_value_span or ep.auth_span or ep.span)
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_002,
                    rule_name="OWNERSHIP-CHECK",
                    severity=Severity.ERROR,
                    span=span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message=f"Owned resource creation ('POST {ep.path}') cannot be public.",
                    why=(
                        "Creating an owned resource requires an authenticated caller identity "
                        "to assign ownership to the newly created item."
                    ),
                    fix=PromptFix(
                        text=(
                            "Change 'auth: public' to 'auth: required' so the calling user's "
                            "identity is recorded as the owner."
                        )
                    ),
                )
            )
            continue

        # 3. User endpoint public or ownership waiver
        if is_user:
            if ep.auth == AuthKind.PUBLIC:
                span = _to_span(ep.auth_value_span or ep.auth_span or ep.span)
                diags.append(
                    _make_diag(
                        rule_id=RuleId.TC_002,
                        rule_name="OWNERSHIP-CHECK",
                        severity=Severity.ERROR,
                        span=span,
                        location=f"endpoint {ep.method} {ep.path}",
                        endpoint=f"{ep.method} {ep.path}",
                        message=f"User endpoint '{ep.method} {ep.path}' cannot be public.",
                        why=(
                            "The User resource is strictly self-only in v1. "
                            "No public User directory is permitted."
                        ),
                        fix=PromptFix(
                            text=(
                                "Change 'auth: public' to 'auth: required' to enforce "
                                "self-only access."
                            )
                        ),
                    )
                )
                continue
            if isinstance(ep.authorize, AuthorizePublic):
                span = _to_span(ep.authorize_span or ep.span)
                diags.append(
                    _make_diag(
                        rule_id=RuleId.TC_002,
                        rule_name="OWNERSHIP-CHECK",
                        severity=Severity.ERROR,
                        span=span,
                        location=f"endpoint {ep.method} {ep.path}",
                        endpoint=f"{ep.method} {ep.path}",
                        message=f"User endpoint '{ep.method} {ep.path}' cannot waive ownership.",
                        why=(
                            "The User resource is strictly self-only in v1. "
                            "Ownership cannot be waived for User endpoints."
                        ),
                        fix=PromptFix(
                            text=(
                                "Remove 'authorize: public'; "
                                "User endpoints are strictly self-only."
                            )
                        ),
                    )
                )
                continue

        # 4. Public plus any authorize field
        if ep.auth == AuthKind.PUBLIC and ep.authorize is not None:
            span = _to_span(ep.authorize_span or ep.span)
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_002,
                    rule_name="OWNERSHIP-CHECK",
                    severity=Severity.ERROR,
                    span=span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message=(
                        f"Endpoint '{ep.method} {ep.path}' has contradictory 'auth: public' "
                        "and 'authorize:' declarations."
                    ),
                    why=(
                        "An endpoint cannot declare public access and an authorization condition "
                        "simultaneously. Require one public declaration or require authentication."
                    ),
                    fix=PromptFix(
                        text=(
                            "Remove 'authorize:' if the endpoint is intended to be public, "
                            "or change 'auth: public' to 'auth: required'."
                        )
                    ),
                )
            )
            continue

        # 5. Authorize on ordinary unowned resource
        if not is_owned and not is_user and ep.authorize is not None:
            span = _to_span(ep.authorize_span or ep.span)
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_002,
                    rule_name="OWNERSHIP-CHECK",
                    severity=Severity.ERROR,
                    span=span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message=(
                        f"Resource '{res.name}' has no ownership edge; 'authorize:' is invalid."
                    ),
                    why=(
                        f"Unowned resource '{res.name}' has no owner field to enforce. "
                        "Use 'auth: required' for login-only access."
                    ),
                    fix=PromptFix(
                        text="Remove 'authorize:' declaration on unowned resource."
                    ),
                )
            )
            continue

        # 6. Owned POST plus authorize field
        if is_owned and ep.method == "POST" and ep.authorize is not None:
            span = _to_span(ep.authorize_span or ep.span)
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_002,
                    rule_name="OWNERSHIP-CHECK",
                    severity=Severity.ERROR,
                    span=span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message=(
                        f"Creation endpoint 'POST {ep.path}' cannot declare 'authorize:'."
                    ),
                    why=(
                        "Resource creation automatically assigns the caller as owner. "
                        "Waivers and authorization predicates only apply to list, read, "
                        "update, and delete operations per specification B4."
                    ),
                    fix=PromptFix(
                        text=(
                            "Remove 'authorize:' from POST endpoint; ownership will "
                            "automatically be assigned on creation."
                        )
                    ),
                )
            )
            continue

        # 7. Authorize equality refers to wrong field
        if isinstance(ep.authorize, AuthorizeEquality):
            if is_owned and res.ownership_edge is not None:
                if ep.authorize.field_name != res.ownership_edge.field_name:
                    span = _to_span(ep.authorize_span or ep.span)
                    diags.append(
                        _make_diag(
                            rule_id=RuleId.TC_002,
                            rule_name="OWNERSHIP-CHECK",
                            severity=Severity.ERROR,
                            span=span,
                            location=f"endpoint {ep.method} {ep.path}",
                            endpoint=f"{ep.method} {ep.path}",
                            message=(
                                f"Authorization equality refers to wrong field "
                                f"'{ep.authorize.field_name}' instead of ownership field "
                                f"'{res.ownership_edge.field_name}'."
                            ),
                            why=(
                                f"Resource '{res.name}' is owned via "
                                f"'{res.ownership_edge.field_name}', not "
                                f"'{ep.authorize.field_name}'. Authorization checks must match "
                                "the declared ownership field."
                            ),
                            fix=PromptFix(
                                text=(
                                    "Remove 'authorize:' from POST creation endpoint; "
                                    "ownership will automatically be assigned on creation."
                                    if ep.method == "POST"
                                    else (
                                        f"Change 'authorize: {ep.authorize.field_name} == "
                                        f"current_user.id' to 'authorize: "
                                        f"{res.ownership_edge.field_name} == current_user.id' "
                                        "or remove it to use the default owner policy."
                                    )
                                )
                            ),
                        )
                    )

    status: Literal["passed", "failed", "not_applicable"] = (
        "passed" if not diags else "failed"
    )
    summary = (
        "All endpoint authorization policies valid"
        if not diags
        else f"{len(diags)} policy violation(s)"
    )
    return (
        _make_rule_result(
            rule_id=RuleId.TC_002,
            rule_name="OWNERSHIP-CHECK",
            status=status,
            checked=checked,
            violations=len(diags),
            summary=summary,
        ),
        diags,
    )


def _eval_tc003(
    program: Program, source: str, current_hash: str
) -> Tuple[RuleResult, List[Diagnostic]]:
    """TC-003 (SENSITIVE-LEAK): Returns sensitive or credential fields without
    permitted exposure."""
    diags: List[Diagnostic] = []
    eligible_endpoints = [ep for ep in program.endpoints if ep.returns is not None]
    checked = len(eligible_endpoints)

    for ep in eligible_endpoints:
        assert ep.returns is not None
        res = program.get_resource(ep.resource)

        # Fields returned in response
        if ep.returns.fields is not None:
            returned_fields = list(ep.returns.fields)
        else:
            # Whole resource returned
            returned_fields = [f.name for f in res.fields]

        span = _to_span(ep.returns_span or ep.span)

        # 1. Any credential field returned is an immediate TC-003 violation
        # (credentials can never be exposed)
        cred_leaks = [f for f in returned_fields if is_credential_field(f)]
        if cred_leaks:
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_003,
                    rule_name="SENSITIVE-LEAK",
                    severity=Severity.ERROR,
                    span=span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message=(
                        f"Endpoint '{ep.method} {ep.path}' returns credential field(s) "
                        f"{', '.join(repr(c) for c in cred_leaks)} in response."
                    ),
                    why=(
                        "Credential fields (password, password_hash, tokens, keys) must never "
                        "be returned in API responses to prevent credential exposure."
                    ),
                    fix=PromptFix(
                        text=(
                            f"Narrow the response projection to exclude credentials: e.g. "
                            f"'returns: {res.name} [id, email]'. Credential fields can never "
                            "be returned, even with an expose declaration."
                        )
                    ),
                )
            )
            continue

        # 2. Ordinary sensitive fields returned without explicit expose declaration
        unexposed_sensitive = []
        for fn in returned_fields:
            field_def = res.get_field(fn)
            if field_def and field_def.sensitive and not is_credential_field(fn):
                if fn not in ep.expose:
                    unexposed_sensitive.append(fn)

        if unexposed_sensitive:
            diags.append(
                _make_diag(
                    rule_id=RuleId.TC_003,
                    rule_name="SENSITIVE-LEAK",
                    severity=Severity.ERROR,
                    span=span,
                    location=f"endpoint {ep.method} {ep.path}",
                    endpoint=f"{ep.method} {ep.path}",
                    message=(
                        f"Endpoint '{ep.method} {ep.path}' returns sensitive field(s) "
                        f"{', '.join(repr(s) for s in unexposed_sensitive)} without explicit "
                        "expose authorization."
                    ),
                    why=(
                        f"Field(s) {', '.join(unexposed_sensitive)} are marked sensitive and "
                        "must not be returned unless explicitly authorized via "
                        f"'expose: [{', '.join(unexposed_sensitive)}]'."
                    ),
                    fix=PromptFix(
                        text=(
                            f"Either exclude {', '.join(unexposed_sensitive)} from the "
                            "projection, or explicitly authorize exposure by declaring "
                            f"'expose: [{', '.join(unexposed_sensitive)}]'."
                        )
                    ),
                )
            )

    status: Literal["passed", "failed", "not_applicable"] = (
        "passed" if not diags else "failed"
    )
    summary = (
        "No sensitive or credential leaks in responses"
        if not diags
        else f"{len(diags)} sensitive leak(s)"
    )
    return (
        _make_rule_result(
            rule_id=RuleId.TC_003,
            rule_name="SENSITIVE-LEAK",
            status=status,
            checked=checked,
            violations=len(diags),
            summary=summary,
        ),
        diags,
    )


def _eval_tc004(
    program: Program, source: str, current_hash: str
) -> Tuple[RuleResult, List[Diagnostic]]:
    """TC-004 (MASS-ASSIGNMENT): id, ownership, or credential field in request body."""
    diags: List[Diagnostic] = []
    checked = sum(len(ep.body) for ep in program.endpoints if ep.body)

    for ep in program.endpoints:
        if not ep.body:
            continue

        res = program.get_resource(ep.resource)
        owner_field_name = res.ownership_edge.field_name if res.ownership_edge else None

        for field_name in ep.body:
            is_pk = (field_name == "id")
            is_owner = (owner_field_name is not None and field_name == owner_field_name)
            is_cred = is_credential_field(field_name)

            if is_pk or is_owner or is_cred:
                field_span = _to_span(
                    (ep.body_field_spans.get(field_name) if ep.body_field_spans else None)
                    or ep.body_span
                    or ep.span
                )
                diff_fix = create_tc004_diff(source, ep, field_name, current_hash)
                kind_desc = (
                    "primary key"
                    if is_pk
                    else ("ownership field" if is_owner else "credential field")
                )

                diags.append(
                    _make_diag(
                        rule_id=RuleId.TC_004,
                        rule_name="MASS-ASSIGNMENT",
                        severity=Severity.ERROR,
                        span=field_span,
                        location=f"body field '{field_name}' in endpoint {ep.method} {ep.path}",
                        endpoint=f"{ep.method} {ep.path}",
                        message=(
                            f"Server-controlled {kind_desc} '{field_name}' cannot be declared "
                            "in request body."
                        ),
                        why=(
                            f"Allowing client writes to '{field_name}' permits mass assignment / "
                            "privilege tampering attacks. Primary keys and ownership "
                            "references must be assigned by the server, not the client."
                        ),
                        fix=diff_fix,
                    )
                )

    status: Literal["passed", "failed", "not_applicable"] = (
        "passed" if not diags else "failed"
    )
    summary = (
        "No server-controlled fields in request bodies"
        if not diags
        else f"{len(diags)} mass-assignment issue(s)"
    )
    return (
        _make_rule_result(
            rule_id=RuleId.TC_004,
            rule_name="MASS-ASSIGNMENT",
            status=status,
            checked=checked,
            violations=len(diags),
            summary=summary,
        ),
        diags,
    )


def _eval_tc005(
    program: Program, source: str, current_hash: str
) -> Tuple[RuleResult, List[Diagnostic]]:
    """TC-005 (SECRET-SCOPE): Missing DB_URL or JWT_SECRET declaration."""
    diags: List[Diagnostic] = []
    checked = len(REQUIRED_SECRETS)

    declared_secrets = {s.name for s in program.secrets}
    missing_secrets = [s for s in REQUIRED_SECRETS if s not in declared_secrets]

    if missing_secrets:
        # Span: secrets keyword span if secrets block exists, else first endpoint span
        if program.secrets_span:
            span = _to_span(program.secrets_span)
        elif program.endpoints:
            span = _make_span(
                program.endpoints[0].span.line,
                program.endpoints[0].span.col,
                program.endpoints[0].span.line,
                program.endpoints[0].span.col + len("endpoint") - 1,
            )
        else:
            span = _make_span(1, 1, 1, 1)

        diff_fix = create_tc005_diff(source, program, missing_secrets, current_hash)
        diags.append(
            _make_diag(
                rule_id=RuleId.TC_005,
                rule_name="SECRET-SCOPE",
                severity=Severity.ERROR,
                span=span,
                location="secrets block",
                endpoint=None,
                message=(
                    f"Missing required environment secret reference(s): "
                    f"{', '.join(missing_secrets)}."
                ),
                why=(
                    "Generated backend services require DB_URL and JWT_SECRET environment "
                    "references for database connectivity and JWT signing. Both must be "
                    "declared in the secrets block."
                ),
                fix=diff_fix,
            )
        )

    status: Literal["passed", "failed", "not_applicable"] = (
        "passed" if not diags else "failed"
    )
    summary = (
        "All required environment secrets declared"
        if not diags
        else f"{len(missing_secrets)} secret(s) missing"
    )
    return (
        _make_rule_result(
            rule_id=RuleId.TC_005,
            rule_name="SECRET-SCOPE",
            status=status,
            checked=checked,
            violations=len(diags),
            summary=summary,
        ),
        diags,
    )


# ---------------------------------------------------------------------------
# Public Verification API
# ---------------------------------------------------------------------------

def check_text(text: str, spec_version: int = 0) -> CheckResult:
    """Evaluate TrustSpec text and return a verified CheckResult contract."""
    t0 = time.time()

    # Step 1: Input size and encoding checks
    try:
        raw_bytes = text.encode("utf-8")
        check_input_size(raw_bytes)
        norm_text = normalize_source(text)
        hash_val = spec_hash(norm_text)
    except (SourceError, UnicodeDecodeError) as e:
        duration_ms = max(0, int((time.time() - t0) * 1000))
        return _make_check_result(
            spec_version=spec_version,
            spec_hash="",
            command="check",
            ms=duration_ms,
            ok=False,
            exit_code=2,
            spec_errors=[
                SpecError(
                    kind=SpecErrorKind.SYNTAX,
                    code="SOURCE_ERROR",
                    message=str(e),
                    span=_make_span(1, 1, 1, 1),
                    snippet="",
                )
            ],
            diagnostics=[],
            rules=[],
            rules_run=0,
            endpoints=0,
        )

    # Step 2: Parse to IR
    try:
        program = parse_text(norm_text)
    except TrustSpecError as e:
        duration_ms = max(0, int((time.time() - t0) * 1000))
        spec_errs = [
            SpecError(
                kind=SpecErrorKind(err.kind),
                code=err.code,
                message=err.message,
                span=_to_span(err.span),
                snippet=err.snippet,
            )
            for err in e.errors
        ]
        return _make_check_result(
            spec_version=spec_version,
            spec_hash=e.source_hash or hash_val,
            command="check",
            ms=duration_ms,
            ok=False,
            exit_code=2,
            spec_errors=spec_errs,
            diagnostics=[],
            rules=[],
            rules_run=0,
            endpoints=0,
        )

    # Step 3: Run all five verifier rules in order
    r1, d1 = _eval_tc001(program, norm_text, hash_val)
    r2, d2 = _eval_tc002(program, norm_text, hash_val)
    r3, d3 = _eval_tc003(program, norm_text, hash_val)
    r4, d4 = _eval_tc004(program, norm_text, hash_val)
    r5, d5 = _eval_tc005(program, norm_text, hash_val)

    rules = [r1, r2, r3, r4, r5]
    all_diags = d1 + d2 + d3 + d4 + d5

    # Sort diagnostics deterministically by (line, col, rule_id)
    sorted_diags = sorted(all_diags, key=lambda d: (d.span.line, d.span.col, d.rule_id))

    duration_ms = max(0, int((time.time() - t0) * 1000))
    ok = (len(sorted_diags) == 0)
    exit_code: Literal[0, 1] = 0 if ok else 1

    return _make_check_result(
        spec_version=spec_version,
        spec_hash=hash_val,
        command="check",
        ms=duration_ms,
        ok=ok,
        exit_code=exit_code,
        spec_errors=[],
        diagnostics=sorted_diags,
        rules=rules,
        rules_run=5,
        endpoints=len(program.endpoints),
    )


def check_file(path: Path | str, spec_version: int = 0) -> CheckResult:
    """Verify a TrustSpec file on disk."""
    p = Path(path)
    if not p.exists():
        return _make_check_result(
            spec_version=spec_version,
            spec_hash="",
            command="check",
            ms=0,
            ok=False,
            exit_code=2,
            spec_errors=[
                SpecError(
                    kind=SpecErrorKind.SYNTAX,
                    code="FILE_NOT_FOUND",
                    message=f"File not found: {p}",
                    span=_make_span(1, 1, 1, 1),
                    snippet="",
                )
            ],
            diagnostics=[],
            rules=[],
            rules_run=0,
            endpoints=0,
        )
    try:
        raw_bytes = p.read_bytes()
        check_input_size(raw_bytes)
        raw_text = raw_bytes.decode("utf-8")
    except (SourceError, UnicodeDecodeError) as exc:
        return _make_check_result(
            spec_version=spec_version,
            spec_hash="",
            command="check",
            ms=0,
            ok=False,
            exit_code=2,
            spec_errors=[
                SpecError(
                    kind=SpecErrorKind.SYNTAX,
                    code="SOURCE_ERROR",
                    message=str(exc),
                    span=_make_span(1, 1, 1, 1),
                    snippet="",
                )
            ],
            diagnostics=[],
            rules=[],
            rules_run=0,
            endpoints=0,
        )
    return check_text(raw_text, spec_version=spec_version)


# ---------------------------------------------------------------------------
# Formatting Helpers (SARIF 2.1.0 & Human Terminal Output)
# ---------------------------------------------------------------------------

def export_sarif(result: CheckResult, filename: str = "spec.trust") -> Dict[str, Any]:
    """Export CheckResult as an OASIS SARIF 2.1.0 JSON document."""
    rules_list = []
    for r_id, r_meta in RULES_INFO.items():
        rules_list.append({
            "id": r_id,
            "name": r_meta["name"],
            "shortDescription": {"text": r_meta["shortDescription"]},
            "fullDescription": {"text": r_meta["fullDescription"]},
            "defaultConfiguration": {"level": "error"},
            "helpUri": r_meta["helpUri"],
        })

    sarif_results = []
    for diag in result.diagnostics:
        sarif_results.append({
            "ruleId": diag.rule_id,
            "level": "error" if diag.severity == Severity.ERROR else "warning",
            "message": {"text": diag.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": filename},
                        "region": {
                            "startLine": diag.span.line,
                            "startColumn": diag.span.col,
                            "endLine": diag.span.end_line,
                            "endColumn": diag.span.end_col,
                        },
                    }
                }
            ],
        })

    sarif_schema = (
        "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/"
        "master/Schemata/sarif-schema-2.1.0.json"
    )
    return {
        "$schema": sarif_schema,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "trustc",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/ramarao2112/TrustC",
                        "rules": rules_list,
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def format_human_report(result: CheckResult, filename: str = "spec.trust") -> str:
    """Format CheckResult for terminal human-readable display."""
    lines: List[str] = []
    lines.append(f"TrustC Security Verification: {filename}")
    lines.append(f"Spec Hash: {result.spec_hash}")
    lines.append(f"Status:    {'PASSED' if result.ok else 'FAILED'} (exit {result.exit_code})\n")

    if result.spec_errors:
        lines.append("Specification Errors:")
        for err in result.spec_errors:
            loc = f"Line {err.span.line}:{err.span.col}:"
            lines.append(f"  [{err.kind.value.upper()}/{err.code}] {loc} {err.message}")
            if err.snippet:
                lines.append(f"    {err.span.line} | {err.snippet}")
        return "\n".join(lines)

    if result.diagnostics:
        lines.append("Security Diagnostics:")
        for idx, d in enumerate(result.diagnostics, 1):
            r_id_str = d.rule_id.value if hasattr(d.rule_id, "value") else str(d.rule_id)
            loc = f"Line {d.span.line}, Column {d.span.col}"
            lines.append(f"\n  {idx}. [{r_id_str}: {d.rule_name}] at {loc}")
            lines.append(f"     Message: {d.message}")
            lines.append(f"     Why:     {d.why}")
            if d.fix.type == "diff":
                lines.append(f"     Fix:     [Automated Diff] {getattr(d.fix, 'label', '')}")
            else:
                lines.append(f"     Fix:     [Guidance] {getattr(d.fix, 'text', '')}")

    lines.append("\n" + "-" * 50)
    summary_hdr = (
        f"Rule Summary ({result.rules_run} rules evaluated across "
        f"{result.endpoints} endpoint(s)):"
    )
    lines.append(summary_hdr)
    for r in result.rules:
        mark = "PASS" if r.status == "passed" else ("FAIL" if r.status == "failed" else "SKIP")
        r_id_str = r.rule_id.value if hasattr(r.rule_id, "value") else str(r.rule_id)
        v_info = f"({r.checked} checked, {r.violations} violation(s))"
        lines.append(f"  [{mark}] {r_id_str} ({r.rule_name}): {r.status} {v_info}")

    lines.append("-" * 50)
    return "\n".join(lines)
