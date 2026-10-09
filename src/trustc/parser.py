"""TrustSpec parser: Lark grammar + AST transformer + reference validator.

Stage 2 entry point: parse_text(source) -> Program | TrustSpecError

Implements B-compiler-spec.md §B1-B4 validation order:
1. Decode/limit/normalize source and calculate hash
2. Lark parser builds nodes with start/end spans
3. Resolve symbols, types, paths, duplicates and unsupported operation shapes
4. Build immutable typed IR with explicit auth absence and inferred policies
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lark import (
    Lark,
    Token,
    Transformer,
    UnexpectedCharacters,
    UnexpectedInput,
    UnexpectedToken,
)

from trustc.ir import (
    VALID_TYPES,
    AuthKind,
    AuthorizeEquality,
    AuthorizePublic,
    Endpoint,
    EndpointMode,
    Field,
    FieldTypeEnum,
    OperationKind,
    OwnershipExpr,
    Program,
    Resource,
    RoleOnly,
    SecretRef,
    is_credential_field,
    is_reserved_name,
    is_valid_identifier,
)
from trustc.source import (
    SourceError,
    Span,
    check_input_size,
    check_tabs,
    normalize_source,
    spec_hash,
)

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecErrorDetail:
    """A specification error (exit 2, no rules run)."""
    kind: str  # 'syntax' | 'reference' | 'unsupported'
    code: str
    message: str
    span: Span
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "code": self.code,
            "message": self.message,
            "span": self.span.to_dict(),
            "snippet": self.snippet,
        }


@dataclass
class TrustSpecError(Exception):
    """Raised when a TrustSpec file has errors that prevent rule checking."""
    errors: List[SpecErrorDetail]
    source_hash: str
    source: str

    def __init__(
        self,
        errors: List[SpecErrorDetail],
        source_hash: str,
        source: str,
    ) -> None:
        self.errors = errors
        self.source_hash = source_hash
        self.source = source
        super().__init__(f"{len(errors)} spec error(s)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "specHash": self.source_hash,
            "exitCode": 2,
            "specErrors": [e.to_dict() for e in self.errors],
        }


# ---------------------------------------------------------------------------
# Grammar loading
# ---------------------------------------------------------------------------

_GRAMMAR_PATH = Path(__file__).parent / "grammars" / "trustspec.lark"

_parser_cache: Optional[Lark] = None


def _get_parser() -> Lark:
    """Load and cache the Lark parser."""
    global _parser_cache
    if _parser_cache is None:
        grammar_text = _GRAMMAR_PATH.read_text(encoding="utf-8")
        _parser_cache = Lark(
            grammar_text,
            parser="lalr",
            propagate_positions=True,
        )
    return _parser_cache


# ---------------------------------------------------------------------------
# AST Transformer — extracts raw parsed data
# ---------------------------------------------------------------------------

@dataclass
class _RawField:
    name: str
    type_name: str
    ownership_target: Optional[Tuple[str, str]]  # (Resource, field)
    ownership_span: Optional[Span]
    sensitive: bool
    span: Span


@dataclass
class _RawResource:
    name: str
    fields: List[_RawField]
    span: Span


@dataclass
class _RawSecret:
    name: str
    span: Span


@dataclass
class _RawEndpointAttr:
    kind: str  # 'resource', 'auth', 'authorize', 'role_only', 'body', 'returns', 'expose'
    value: Any
    span: Span
    extra_spans: Optional[Dict[str, Span]] = None
    value_span: Optional[Span] = None


@dataclass
class _RawEndpoint:
    method: str
    path: str
    attrs: List[_RawEndpointAttr]
    span: Span  # span of 'endpoint' keyword
    method_span: Span
    path_span: Span


def _token_span(token: Token) -> Span:
    """Extract a Span from a Lark Token."""
    line = token.line or 1
    col = token.column or 1
    end_line = token.end_line or line
    end_col = token.end_column or (col + len(str(token)))
    return Span(line=line, col=col, end_line=end_line, end_col=end_col)


class _ASTTransformer(Transformer):  # type: ignore[type-arg]
    """Transform Lark parse tree into raw intermediate structures."""

    def IDENT(self, token: Token) -> Token:
        return token

    def METHOD(self, token: Token) -> Token:
        return token

    def AUTH_VALUE(self, token: Token) -> Token:
        return token

    def PATH(self, token: Token) -> Token:
        return token

    def field_type(self, items: list) -> Token:
        return items[0]  # type: ignore[no-any-return]

    def ownership_target(self, items: list) -> Tuple[str, str, Span]:
        arrow_tok = items[0]
        res_tok = items[1]
        field_tok = items[2]
        span = Span(
            line=arrow_tok.line or 1,
            col=arrow_tok.column or 1,
            end_line=field_tok.end_line or field_tok.line or 1,
            end_col=field_tok.end_column or ((field_tok.column or 1) + len(str(field_tok))),
        )
        return (str(res_tok), str(field_tok), span)

    def sensitive_marker(self, items: list) -> bool:
        return True

    def field_decl(self, items: list) -> _RawField:
        name_tok = items[0]
        type_tok = items[1]
        ownership = None
        ownership_span = None
        sensitive = False

        for item in items[2:]:
            if isinstance(item, tuple) and len(item) == 3:
                ownership = (item[0], item[1])
                ownership_span = item[2]
            elif item is True:
                sensitive = True

        return _RawField(
            name=str(name_tok),
            type_name=str(type_tok),
            ownership_target=ownership,
            ownership_span=ownership_span,
            sensitive=sensitive,
            span=_token_span(name_tok),
        )

    def resource_block(self, items: list) -> _RawResource:
        resource_keyword = items[0]
        name_tok = items[1]
        fields = [i for i in items if isinstance(i, _RawField)]
        return _RawResource(
            name=str(name_tok),
            fields=fields,
            span=_token_span(resource_keyword),
        )

    def secret_decl(self, items: list) -> _RawSecret:
        name_tok = items[0]
        return _RawSecret(name=str(name_tok), span=_token_span(name_tok))

    def secrets_block(self, items: list) -> Tuple[Span, List[_RawSecret]]:
        secrets_keyword = items[0]
        secrets = [i for i in items if isinstance(i, _RawSecret)]
        return (_token_span(secrets_keyword), secrets)

    def resource_attr(self, items: list) -> _RawEndpointAttr:
        kw = items[0]
        val = items[1]
        return _RawEndpointAttr(
            kind="resource",
            value=str(val),
            span=_token_span(kw),
            value_span=_token_span(val),
        )

    def auth_attr(self, items: list) -> _RawEndpointAttr:
        kw = items[0]
        val = items[1]
        return _RawEndpointAttr(
            kind="auth",
            value=str(val),
            span=_token_span(kw),
            value_span=_token_span(val),
        )

    def authorize_public(self, items: list) -> dict:
        return {"type": "public"}

    def authorize_equality(self, items: list) -> dict:
        field_tok = items[0]
        # items[1] is CURRENT_USER ('current_user')
        target_tok = items[2]
        return {
            "type": "equality",
            "field": str(field_tok),
            "target_field": str(target_tok),
            "field_span": _token_span(field_tok),
        }

    def authorize_attr(self, items: list) -> _RawEndpointAttr:
        kw = items[0]
        val = items[1]
        return _RawEndpointAttr(
            kind="authorize",
            value=val,
            span=_token_span(kw),
        )

    def role_only_attr(self, items: list) -> _RawEndpointAttr:
        kw = items[0]
        val = items[1]
        return _RawEndpointAttr(
            kind="role_only",
            value=str(val),
            span=_token_span(kw),
            value_span=_token_span(val),
        )

    def field_list_inner(self, items: list) -> List[Tuple[str, Span]]:
        result = []
        for t in items:
            if isinstance(t, Token) and t.type == "IDENT":
                result.append((str(t), _token_span(t)))
        return result

    def body_attr(self, items: list) -> _RawEndpointAttr:
        kw = items[0]
        field_entries: List[Tuple[str, Span]] = []
        for item in items[1:]:
            if isinstance(item, list):
                field_entries = item
        field_names = [f[0] for f in field_entries]
        field_spans = {f[0]: f[1] for f in field_entries}
        return _RawEndpointAttr(
            kind="body",
            value=field_names,
            span=_token_span(kw),
            extra_spans=field_spans,
        )

    def returns_attr(self, items: list) -> _RawEndpointAttr:
        kw = items[0]
        res_tok = items[1]
        projection_entries: Optional[List[Tuple[str, Span]]] = None
        for item in items[2:]:
            if isinstance(item, list):
                projection_entries = item

        proj_names = (
            [p[0] for p in projection_entries]
            if projection_entries is not None
            else None
        )
        proj_spans = (
            {p[0]: p[1] for p in projection_entries}
            if projection_entries is not None
            else None
        )

        return _RawEndpointAttr(
            kind="returns",
            value={
                "resource": str(res_tok),
                "resource_span": _token_span(res_tok),
                "projection": proj_names,
            },
            span=_token_span(kw),
            extra_spans=proj_spans,
        )

    def expose_attr(self, items: list) -> _RawEndpointAttr:
        kw = items[0]
        field_entries: List[Tuple[str, Span]] = []
        for item in items[1:]:
            if isinstance(item, list):
                field_entries = item
        field_names = [f[0] for f in field_entries]
        field_spans = {f[0]: f[1] for f in field_entries}
        return _RawEndpointAttr(
            kind="expose",
            value=field_names,
            span=_token_span(kw),
            extra_spans=field_spans,
        )

    def endpoint_block(self, items: list) -> _RawEndpoint:
        endpoint_kw = items[0]
        method_tok = items[1]
        path_tok = items[2]
        attrs = [i for i in items if isinstance(i, _RawEndpointAttr)]
        return _RawEndpoint(
            method=str(method_tok),
            path=str(path_tok),
            attrs=attrs,
            span=_token_span(endpoint_kw),
            method_span=_token_span(method_tok),
            path_span=_token_span(path_tok),
        )

    def start(self, items: list) -> dict:
        resources: List[_RawResource] = []
        secrets: List[_RawSecret] = []
        secrets_span: Optional[Span] = None
        endpoints: List[_RawEndpoint] = []

        for item in items:
            if isinstance(item, _RawResource):
                resources.append(item)
            elif isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], list):
                secrets_span = item[0]
                secrets.extend(item[1])
            elif isinstance(item, _RawEndpoint):
                endpoints.append(item)

        return {
            "resources": resources,
            "secrets": secrets,
            "secrets_span": secrets_span,
            "endpoints": endpoints,
        }


# ---------------------------------------------------------------------------
# Path and shape validation
# ---------------------------------------------------------------------------

_VALID_PATH_RE = re.compile(r"^/[A-Za-z0-9_\-\/{}]+$")
_RESERVED_ROUTES = frozenset({
    "/api", "/docs", "/redoc", "/openapi.json",
    "/health", "/metrics", "/admin", "/login", "/logout",
})


def _validate_path_shape(method: str, path: str, resource_name: str) -> Optional[str]:
    """Validate path syntax per B2.

    Returns error message or None if valid.
    """
    if not _VALID_PATH_RE.match(path):
        return f"Path contains invalid characters: '{path}'"

    # No query strings, percent escapes, dot segments, repeated slashes
    if "?" in path or "%" in path or "/." in path or "//" in path:
        return f"Path contains forbidden patterns: '{path}'"

    # Only single supported {id} placeholder allowed
    braces = re.findall(r"\{([^}]+)\}", path)
    for b in braces:
        if b != "id":
            return f"Unsupported path parameter: '{{{b}}}'. Only '{{id}}' is supported"

    # Check for unclosed or nested braces
    clean = re.sub(r"\{id\}", "", path)
    if "{" in clean or "}" in clean:
        return f"Malformed braces in path: '{path}'"

    # Check method/path compatibility per B2 table
    segments = [s for s in path.split("/") if s]
    if not segments:
        return "Path cannot be root '/'"

    return None


def _infer_operation(method: str, path: str) -> Optional[OperationKind]:
    """Infer OperationKind from method and path per B2."""
    has_id = "{id}" in path
    segments = [s for s in path.split("/") if s]

    if method == "POST" and not has_id:
        return OperationKind.CREATE
    elif method == "GET" and not has_id:
        return OperationKind.LIST
    elif method == "GET" and has_id and segments[-1] == "{id}":
        return OperationKind.READ
    elif method == "PUT" and has_id:
        return OperationKind.UPDATE
    elif method == "PATCH" and has_id:
        return OperationKind.PARTIAL_UPDATE
    elif method == "DELETE" and has_id and segments[-1] == "{id}":
        return OperationKind.DELETE

    return None


def _get_snippet(source: str, line: int, col: int) -> str:
    """Extract a source line snippet for error display."""
    lines = source.split("\n")
    if 1 <= line <= len(lines):
        return lines[line - 1]
    return ""


# ---------------------------------------------------------------------------
# Reference validation and IR construction
# ---------------------------------------------------------------------------

def _infer_endpoint_mode(
    method: str,
    auth: AuthKind,
    resource_name: str,
    has_ownership: bool,
    is_identity: bool,
    authorize: Optional[AuthorizePublic | AuthorizeEquality],
    role_only: Optional[RoleOnly],
) -> Tuple[Optional[EndpointMode], bool]:
    """Infer effective endpoint mode and owner_waived per B4.

    Returns:
        (mode, owner_waived)
    """
    owner_waived = False

    if auth == AuthKind.PUBLIC:
        return (EndpointMode.PUBLIC, False)

    if auth == AuthKind.REQUIRED:
        if is_identity:
            return (EndpointMode.SELF, False)
        if has_ownership:
            if isinstance(authorize, AuthorizePublic):
                owner_waived = True
            return (EndpointMode.OWNER, owner_waived)
        return (EndpointMode.LOGIN_ONLY, False)

    # auth is ABSENT — structural mode for IR
    if is_identity:
        return (EndpointMode.SELF, False)
    if has_ownership:
        return (EndpointMode.OWNER, False)
    return (EndpointMode.LOGIN_ONLY, False)


def _validate_and_build(
    raw: dict,
    source: str,
    source_hash_val: str,
) -> Program:
    """Validate references, types, paths, duplicates and build IR.

    Raises TrustSpecError on validation failures.
    """
    errors: List[SpecErrorDetail] = []
    raw_resources: List[_RawResource] = raw["resources"]
    raw_secrets: List[_RawSecret] = raw["secrets"]
    raw_endpoints: List[_RawEndpoint] = raw["endpoints"]

    # --- Resource validation ---
    resource_names: Dict[str, _RawResource] = {}
    resources: List[Resource] = []

    for rr in raw_resources:
        # Check valid identifier
        if not is_valid_identifier(rr.name):
            errors.append(SpecErrorDetail(
                kind="syntax",
                code="INVALID_IDENTIFIER",
                message=f"Invalid resource name: '{rr.name}'",
                span=rr.span,
                snippet=_get_snippet(source, rr.span.line, rr.span.col),
            ))
            continue

        # Check reserved name
        if is_reserved_name(rr.name):
            errors.append(SpecErrorDetail(
                kind="reference",
                code="RESERVED_NAME",
                message=(
                    f"Resource name '{rr.name}' collides with "
                    "a generated module/class name"
                ),
                span=rr.span,
                snippet=_get_snippet(source, rr.span.line, rr.span.col),
            ))
            continue

        # Check duplicate resource
        if rr.name in resource_names:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="DUPLICATE_RESOURCE",
                message=f"Duplicate resource: '{rr.name}'",
                span=rr.span,
                snippet=_get_snippet(source, rr.span.line, rr.span.col),
            ))
            continue

        resource_names[rr.name] = rr

        # Validate fields
        ir_fields: List[Field] = []
        field_names: Dict[str, _RawField] = {}
        ownership: Optional[OwnershipExpr] = None
        ownership_count = 0

        for rf in rr.fields:
            # Check valid field identifier
            if not is_valid_identifier(rf.name):
                errors.append(SpecErrorDetail(
                    kind="syntax",
                    code="INVALID_IDENTIFIER",
                    message=f"Invalid field name: '{rf.name}'",
                    span=rf.span,
                    snippet=_get_snippet(source, rf.span.line, rf.span.col),
                ))
                continue

            # Check duplicate field
            if rf.name in field_names:
                errors.append(SpecErrorDetail(
                    kind="reference",
                    code="DUPLICATE_FIELD",
                    message=(
                        f"Duplicate field '{rf.name}' in resource '{rr.name}'"
                    ),
                    span=rf.span,
                    snippet=_get_snippet(source, rf.span.line, rf.span.col),
                ))
                continue

            # Check valid type
            if rf.type_name not in VALID_TYPES:
                errors.append(SpecErrorDetail(
                    kind="unsupported",
                    code="UNSUPPORTED_TYPE",
                    message=(
                        f"Unsupported field type: '{rf.type_name}'. "
                        f"Supported types: {', '.join(sorted(VALID_TYPES))}"
                    ),
                    span=rf.span,
                    snippet=_get_snippet(source, rf.span.line, rf.span.col),
                ))
                continue

            field_names[rf.name] = rf
            is_cred = is_credential_field(rf.name)

            ir_fields.append(Field(
                name=rf.name,
                field_type=FieldTypeEnum(rf.type_name),
                sensitive=rf.sensitive,
                is_credential=is_cred,
                span=rf.span,
            ))

            # Check ownership edge
            if rf.ownership_target:
                ownership_count += 1
                target_res, target_field = rf.ownership_target

                if ownership_count > 1:
                    errors.append(SpecErrorDetail(
                        kind="unsupported",
                        code="MULTIPLE_OWNERSHIP",
                        message=(
                            f"Resource '{rr.name}' has multiple ownership edges. "
                            "At most one ownership edge is supported per resource"
                        ),
                        span=rf.span,
                        snippet=_get_snippet(source, rf.span.line, rf.span.col),
                    ))
                    continue

                # Check ownership target is User.id
                if target_res != "User":
                    errors.append(SpecErrorDetail(
                        kind="unsupported",
                        code="INVALID_OWNERSHIP_TARGET",
                        message=(
                            f"Ownership edge must target User.id, "
                            f"not {target_res}.{target_field}"
                        ),
                        span=rf.span,
                        snippet=_get_snippet(source, rf.span.line, rf.span.col),
                    ))
                    continue

                if target_field != "id":
                    errors.append(SpecErrorDetail(
                        kind="unsupported",
                        code="INVALID_OWNERSHIP_TARGET",
                        message=(
                            f"Ownership edge must target User.id, "
                            f"not User.{target_field}"
                        ),
                        span=rf.span,
                        snippet=_get_snippet(source, rf.span.line, rf.span.col),
                    ))
                    continue

                if rf.type_name != FieldTypeEnum.UUID.value:
                    errors.append(SpecErrorDetail(
                        kind="unsupported",
                        code="INVALID_OWNERSHIP_TYPE",
                        message=(
                            f"Ownership field must be uuid type, "
                            f"not {rf.type_name}"
                        ),
                        span=rf.span,
                        snippet=_get_snippet(source, rf.span.line, rf.span.col),
                    ))
                    continue

                # User must not declare an ownership edge
                if rr.name == "User":
                    errors.append(SpecErrorDetail(
                        kind="unsupported",
                        code="USER_OWNERSHIP",
                        message="User resource must not declare an ownership edge",
                        span=rf.span,
                        snippet=_get_snippet(source, rf.span.line, rf.span.col),
                    ))
                    continue

                ownership = OwnershipExpr(
                    field_name=rf.name,
                    target_resource=target_res,
                    target_field=target_field,
                    span=rf.span,
                )

        # Every resource must have id: uuid
        has_id = any(
            f.name == "id" and f.type_name == "uuid"
            for f in rr.fields
        )
        if not has_id:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="MISSING_ID",
                message=f"Resource '{rr.name}' must have 'id: uuid' field",
                span=rr.span,
                snippet=_get_snippet(source, rr.span.line, rr.span.col),
            ))

        resources.append(Resource(
            name=rr.name,
            fields=tuple(ir_fields),
            ownership=ownership,
            span=rr.span,
        ))

    # Must have User resource
    if "User" not in resource_names:
        first_span = raw_resources[0].span if raw_resources else Span(1, 1, 1, 1)
        errors.append(SpecErrorDetail(
            kind="reference",
            code="MISSING_USER",
            message="One resource must be named 'User'",
            span=first_span,
            snippet=_get_snippet(source, first_span.line, first_span.col),
        ))

    # --- Secret validation ---
    ir_secrets: List[SecretRef] = []
    secret_names: Dict[str, _RawSecret] = {}

    for rs in raw_secrets:
        if rs.name in secret_names:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="DUPLICATE_SECRET",
                message=f"Duplicate secret: '{rs.name}'",
                span=rs.span,
                snippet=_get_snippet(source, rs.span.line, rs.span.col),
            ))
            continue
        secret_names[rs.name] = rs
        ir_secrets.append(SecretRef(name=rs.name, span=rs.span))

    # --- Endpoint validation ---
    ir_endpoints: List[Endpoint] = []
    endpoint_keys: Dict[str, _RawEndpoint] = {}

    for re_ in raw_endpoints:
        method = re_.method
        path = re_.path

        # Check duplicate METHOD+path
        key = f"{method} {path}"
        if key in endpoint_keys:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="DUPLICATE_ENDPOINT",
                message=f"Duplicate endpoint: {key}",
                span=re_.span,
                snippet=_get_snippet(source, re_.span.line, re_.span.col),
            ))
            continue
        endpoint_keys[key] = re_

        # Validate path
        path_err = _validate_path_shape(method, path, "")
        if path_err:
            errors.append(SpecErrorDetail(
                kind="unsupported",
                code="INVALID_PATH",
                message=path_err,
                span=re_.path_span,
                snippet=_get_snippet(source, re_.path_span.line, re_.path_span.col),
            ))
            continue

        # Check reserved routes
        if path.rstrip("/") in _RESERVED_ROUTES:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="RESERVED_ROUTE",
                message=f"Path collides with reserved route: {path}",
                span=re_.path_span,
                snippet=_get_snippet(source, re_.path_span.line, re_.path_span.col),
            ))
            continue

        # Parse attributes
        resource_name: Optional[str] = None
        resource_span: Optional[Span] = None
        auth_kind = AuthKind.ABSENT
        auth_span_val: Optional[Span] = None
        auth_value_span: Optional[Span] = None
        authorize: Optional[AuthorizePublic | AuthorizeEquality] = None
        authorize_span_val: Optional[Span] = None
        role_only: Optional[RoleOnly] = None
        role_only_span_val: Optional[Span] = None
        body_fields: Optional[Tuple[str, ...]] = None
        body_span: Optional[Span] = None
        body_field_spans: Optional[Dict[str, Span]] = None
        returns_resource: Optional[str] = None
        returns_projection: Optional[Tuple[str, ...]] = None
        returns_span: Optional[Span] = None
        returns_field_spans: Optional[Dict[str, Span]] = None
        expose_fields: Optional[Tuple[str, ...]] = None
        expose_span: Optional[Span] = None
        expose_field_spans: Optional[Dict[str, Span]] = None
        seen_attrs: Dict[str, Span] = {}

        for attr in re_.attrs:
            # Check duplicate attribute
            if attr.kind in seen_attrs:
                errors.append(SpecErrorDetail(
                    kind="reference",
                    code="DUPLICATE_ATTR",
                    message=(
                        f"Duplicate endpoint attribute: '{attr.kind}' "
                        f"in {key}"
                    ),
                    span=attr.span,
                    snippet=_get_snippet(source, attr.span.line, attr.span.col),
                ))
                continue
            seen_attrs[attr.kind] = attr.span

            if attr.kind == "resource":
                resource_name = attr.value
                resource_span = attr.span
            elif attr.kind == "auth":
                auth_kind = (
                    AuthKind.REQUIRED
                    if attr.value == "required"
                    else AuthKind.PUBLIC
                )
                auth_span_val = attr.span
                auth_value_span = attr.value_span
            elif attr.kind == "authorize":
                authorize_span_val = attr.span
                val = attr.value
                if isinstance(val, dict):
                    if val["type"] == "public":
                        authorize = AuthorizePublic(span=attr.span)
                    else:
                        authorize = AuthorizeEquality(
                            field_name=val["field"],
                            target_field=val["target_field"],
                            span=attr.span,
                        )
            elif attr.kind == "role_only":
                role_only = RoleOnly(role_name=attr.value, span=attr.span)
                role_only_span_val = attr.span
            elif attr.kind == "body":
                body_fields = tuple(attr.value)
                body_span = attr.span
                body_field_spans = attr.extra_spans
            elif attr.kind == "returns":
                returns_resource = attr.value["resource"]
                proj = attr.value.get("projection")
                if proj is not None:
                    returns_projection = tuple(proj)
                returns_span = attr.span
                returns_field_spans = attr.extra_spans
            elif attr.kind == "expose":
                expose_fields = tuple(attr.value)
                expose_span = attr.span
                expose_field_spans = attr.extra_spans

        # resource: is required
        if resource_name is None:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="MISSING_RESOURCE_ATTR",
                message=f"Endpoint {key} must declare 'resource:' attribute",
                span=re_.span,
                snippet=_get_snippet(source, re_.span.line, re_.span.col),
            ))
            continue

        if resource_span is None:
            resource_span = re_.span

        # Check resource exists
        if resource_name not in resource_names:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="UNKNOWN_RESOURCE",
                message=(
                    f"Endpoint {key} references unknown resource: "
                    f"'{resource_name}'"
                ),
                span=resource_span,
                snippet=_get_snippet(
                    source, resource_span.line, resource_span.col
                ),
            ))
            continue

        res = next(
            (r for r in resources if r.name == resource_name), None
        )

        # Infer operation
        operation = _infer_operation(method, path)
        if operation is None:
            errors.append(SpecErrorDetail(
                kind="unsupported",
                code="UNSUPPORTED_OPERATION",
                message=(
                    f"Unsupported operation shape: {method} {path}"
                ),
                span=re_.span,
                snippet=_get_snippet(source, re_.span.line, re_.span.col),
            ))
            continue

        # Check forbidden User operations per B1 (only GET /users/{id} in v1)
        if resource_name == "User" and not (method == "GET" and path == "/users/{id}"):
            errors.append(SpecErrorDetail(
                kind="unsupported",
                code="FORBIDDEN_USER_OPERATION",
                message=(
                    f"Only 'GET /users/{{id}}' is supported for User resource in v1, "
                    f"not '{method} {path}'"
                ),
                span=re_.span,
                snippet=_get_snippet(source, re_.span.line, re_.span.col),
            ))
            continue

        # Validate body rules per B2
        if body_fields is not None and method in ("GET", "DELETE"):
            errors.append(SpecErrorDetail(
                kind="unsupported",
                code="BODY_NOT_ALLOWED",
                message=(
                    f"{method} endpoints do not accept body declarations"
                ),
                span=body_span or re_.span,
                snippet=_get_snippet(
                    source,
                    (body_span or re_.span).line,
                    (body_span or re_.span).col,
                ),
            ))
            continue

        if method in ("PUT", "PATCH") and (
            body_fields is None or len(body_fields) == 0
        ):
            errors.append(SpecErrorDetail(
                kind="reference",
                code="MISSING_BODY",
                message=(
                    f"{method} endpoints must declare a nonempty body"
                ),
                span=re_.span,
                snippet=_get_snippet(source, re_.span.line, re_.span.col),
            ))
            continue

        # Validate returns rules per B2
        if method == "DELETE" and returns_resource is not None:
            errors.append(SpecErrorDetail(
                kind="unsupported",
                code="RETURNS_NOT_ALLOWED",
                message="DELETE endpoints do not return a resource",
                span=returns_span or re_.span,
                snippet=_get_snippet(
                    source,
                    (returns_span or re_.span).line,
                    (returns_span or re_.span).col,
                ),
            ))
            continue

        if method in ("POST", "GET") and returns_resource is None:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="MISSING_RETURNS",
                message=(
                    f"{method} endpoints must declare 'returns:'"
                ),
                span=re_.span,
                snippet=_get_snippet(source, re_.span.line, re_.span.col),
            ))
            continue

        # Validate returns resource matches endpoint resource
        if returns_resource is not None and returns_resource != resource_name:
            errors.append(SpecErrorDetail(
                kind="reference",
                code="CROSS_RESOURCE_RETURNS",
                message=(
                    f"returns: {returns_resource} must match endpoint "
                    f"resource: {resource_name}"
                ),
                span=returns_span or re_.span,
                snippet=_get_snippet(
                    source,
                    (returns_span or re_.span).line,
                    (returns_span or re_.span).col,
                ),
            ))
            continue

        # Validate projected fields exist and have no duplicates
        if returns_projection is not None and res is not None:
            if len(returns_projection) == 0:
                errors.append(SpecErrorDetail(
                    kind="syntax",
                    code="EMPTY_PROJECTION",
                    message="Empty response projection is invalid",
                    span=returns_span or re_.span,
                    snippet=_get_snippet(
                        source,
                        (returns_span or re_.span).line,
                        (returns_span or re_.span).col,
                    ),
                ))
            seen_returns: set[str] = set()
            for fname in returns_projection:
                err_span = (returns_field_spans or {}).get(fname, returns_span or re_.span)
                if fname in seen_returns:
                    errors.append(SpecErrorDetail(
                        kind="reference",
                        code="DUPLICATE_PROJECTED_FIELD",
                        message=(
                            f"Duplicate field '{fname}' in returns projection "
                            f"for resource '{resource_name}'"
                        ),
                        span=err_span,
                        snippet=_get_snippet(source, err_span.line, err_span.col),
                    ))
                seen_returns.add(fname)
                if fname not in res.field_map:
                    errors.append(SpecErrorDetail(
                        kind="reference",
                        code="UNKNOWN_FIELD",
                        message=(
                            f"Unknown field '{fname}' in returns projection "
                            f"for resource '{resource_name}'"
                        ),
                        span=err_span,
                        snippet=_get_snippet(source, err_span.line, err_span.col),
                    ))

        # Validate body fields exist and have no duplicates
        if body_fields is not None and res is not None:
            seen_body: set[str] = set()
            for fname in body_fields:
                err_span = (body_field_spans or {}).get(fname, body_span or re_.span)
                if fname in seen_body:
                    errors.append(SpecErrorDetail(
                        kind="reference",
                        code="DUPLICATE_FIELD",
                        message=(
                            f"Duplicate field '{fname}' in body declaration "
                            f"for resource '{resource_name}'"
                        ),
                        span=err_span,
                        snippet=_get_snippet(source, err_span.line, err_span.col),
                    ))
                seen_body.add(fname)
                if fname not in res.field_map:
                    errors.append(SpecErrorDetail(
                        kind="reference",
                        code="UNKNOWN_FIELD",
                        message=(
                            f"Unknown field '{fname}' in body declaration "
                            f"for resource '{resource_name}'"
                        ),
                        span=err_span,
                        snippet=_get_snippet(source, err_span.line, err_span.col),
                    ))

        # Validate expose fields exist and have no duplicates
        if expose_fields is not None:
            if returns_resource is None:
                errors.append(SpecErrorDetail(
                    kind="reference",
                    code="EXPOSE_WITHOUT_RETURNS",
                    message="expose: requires returns: to be declared",
                    span=expose_span or re_.span,
                    snippet=_get_snippet(
                        source, (expose_span or re_.span).line, (expose_span or re_.span).col
                    ),
                ))
            elif len(expose_fields) == 0:
                errors.append(SpecErrorDetail(
                    kind="syntax",
                    code="EMPTY_EXPOSE",
                    message="Empty expose projection is invalid",
                    span=expose_span or re_.span,
                    snippet=_get_snippet(
                        source, (expose_span or re_.span).line, (expose_span or re_.span).col
                    ),
                ))
            elif res is not None:
                seen_expose: set[str] = set()
                for fname in expose_fields:
                    err_span = (expose_field_spans or {}).get(fname, expose_span or re_.span)
                    if fname in seen_expose:
                        errors.append(SpecErrorDetail(
                            kind="reference",
                            code="DUPLICATE_PROJECTED_FIELD",
                            message=(
                                f"Duplicate field '{fname}' in expose "
                                f"for resource '{resource_name}'"
                            ),
                            span=err_span,
                            snippet=_get_snippet(source, err_span.line, err_span.col),
                        ))
                    seen_expose.add(fname)
                    if fname not in res.field_map:
                        errors.append(SpecErrorDetail(
                            kind="reference",
                            code="UNKNOWN_FIELD",
                            message=(
                                f"Unknown field '{fname}' in expose "
                                f"for resource '{resource_name}'"
                            ),
                            span=err_span,
                            snippet=_get_snippet(source, err_span.line, err_span.col),
                        ))
                    elif not res.field_map[fname].sensitive:
                        errors.append(SpecErrorDetail(
                            kind="reference",
                            code="EXPOSE_NOT_SENSITIVE",
                            message=(
                                f"expose field '{fname}' must be marked [sensitive]"
                            ),
                            span=err_span,
                            snippet=_get_snippet(source, err_span.line, err_span.col),
                        ))

        # Validate authorize equality field exists
        if isinstance(authorize, AuthorizeEquality) and res is not None:
            if authorize.field_name not in res.field_map:
                errors.append(SpecErrorDetail(
                    kind="reference",
                    code="UNKNOWN_FIELD",
                    message=(
                        f"Unknown field '{authorize.field_name}' in authorize expression"
                    ),
                    span=authorize.span,
                    snippet=_get_snippet(source, authorize.span.line, authorize.span.col),
                ))

        # Infer mode
        is_identity = (
            resource_name == "User"
            and method == "GET"
            and "{id}" in path
        )
        has_ownership = (
            res is not None and res.ownership is not None
        )

        mode, owner_waived = _infer_endpoint_mode(
            method, auth_kind, resource_name,
            has_ownership, is_identity, authorize, role_only,
        )

        ir_endpoints.append(Endpoint(
            method=method,
            path=path,
            resource_name=resource_name,
            auth=auth_kind,
            authorize=authorize,
            role_only=role_only,
            body_fields=body_fields,
            returns_resource=returns_resource,
            returns_projection=returns_projection,
            expose_fields=expose_fields,
            operation=operation,
            inferred_mode=mode,
            owner_waived=owner_waived,
            span=re_.span,
            method_span=re_.method_span,
            path_span=re_.path_span,
            resource_span=resource_span,
            auth_span=auth_span_val,
            auth_value_span=auth_value_span,
            authorize_span=authorize_span_val,
            role_only_span=role_only_span_val,
            body_span=body_span,
            body_field_spans=body_field_spans,
            returns_span=returns_span,
            returns_field_spans=returns_field_spans,
            expose_span=expose_span,
            expose_field_spans=expose_field_spans,
        ))

    # If any errors, raise
    if errors:
        raise TrustSpecError(
            errors=errors,
            source_hash=source_hash_val,
            source=source,
        )

    return Program(
        resources=tuple(resources),
        secrets=tuple(ir_secrets),
        endpoints=tuple(ir_endpoints),
        source=source,
        source_hash=source_hash_val,
        secrets_span=raw.get("secrets_span"),
    )


# ---------------------------------------------------------------------------
# Syntax error handling
# ---------------------------------------------------------------------------

def _handle_parse_error(
    exc: Exception,
    source: str,
    source_hash_val: str,
) -> TrustSpecError:
    """Convert a Lark parse error into a TrustSpecError."""
    line = 1
    col = 1
    message = str(exc)

    if isinstance(exc, UnexpectedToken):
        token = exc.token
        line = token.line or 1
        col = token.column or 1
        expected = exc.expected or set()

        # B-compiler-spec.md: Missing-colon errors point at the insertion
        # point on the previous declaration line when justified by the
        # parser's expected token set. F4 is 23:25.
        clean_expected: List[str] = []
        for e in expected:
            s = str(e).strip('"').strip("'")
            if s == "COLON" or s == ":":
                clean_expected.append("':'")
            elif s == "_NL" or s == "NEWLINE":
                clean_expected.append("newline")
            else:
                clean_expected.append(s)

        clean_expected = sorted(clean_expected)

        message = (
            f"Syntax error at line {line}, column {col}: "
            f"unexpected '{token}'"
        )
        if clean_expected:
            message += f". Expected: {', '.join(clean_expected)}"

    elif isinstance(exc, UnexpectedCharacters):
        line = getattr(exc, "line", 1)
        col = getattr(exc, "column", 1)
        message = (
            f"Syntax error at line {line}, column {col}: "
            f"unexpected character"
        )

    snippet = _get_snippet(source, line, col)

    return TrustSpecError(
        errors=[
            SpecErrorDetail(
                kind="syntax",
                code="PARSE_ERROR",
                message=message,
                span=Span(line=line, col=col, end_line=line, end_col=col + 1),
                snippet=snippet,
            )
        ],
        source_hash=source_hash_val,
        source=source,
    )


def check_indentation(source: str) -> Optional[SpecErrorDetail]:
    """Enforce indentation rules per B-compiler-spec.md §B1.

    Top-level declarations start at column 1 (0 spaces).
    Resource 'fields:' uses two spaces.
    Field declarations use four spaces.
    Secret declarations use two spaces.
    Endpoint attributes use two spaces.
    Reject inconsistent indentation.
    """
    state = "TOP"
    for line_no, raw_line in enumerate(source.split("\n"), 1):
        stripped = raw_line.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(stripped)
        if stripped.startswith("resource "):
            if indent != 0:
                return SpecErrorDetail(
                    kind="syntax",
                    code="INCONSISTENT_INDENTATION",
                    message="Top-level resource declaration must start at column 1",
                    span=Span(line=line_no, col=1, end_line=line_no, end_col=indent + 1),
                    snippet=raw_line,
                )
            state = "IN_RESOURCE"
        elif stripped == "secrets:":
            if indent != 0:
                return SpecErrorDetail(
                    kind="syntax",
                    code="INCONSISTENT_INDENTATION",
                    message="Top-level secrets declaration must start at column 1",
                    span=Span(line=line_no, col=1, end_line=line_no, end_col=indent + 1),
                    snippet=raw_line,
                )
            state = "IN_SECRETS"
        elif stripped.startswith("endpoint "):
            if indent != 0:
                return SpecErrorDetail(
                    kind="syntax",
                    code="INCONSISTENT_INDENTATION",
                    message="Top-level endpoint declaration must start at column 1",
                    span=Span(line=line_no, col=1, end_line=line_no, end_col=indent + 1),
                    snippet=raw_line,
                )
            state = "IN_ENDPOINT"
        elif state == "IN_RESOURCE":
            if stripped == "fields:":
                if indent != 2:
                    return SpecErrorDetail(
                        kind="syntax",
                        code="INCONSISTENT_INDENTATION",
                        message="Expected 2 spaces indentation for 'fields:'",
                        span=Span(line=line_no, col=1, end_line=line_no, end_col=indent + 1),
                        snippet=raw_line,
                    )
                state = "IN_RESOURCE_FIELDS"
        elif state == "IN_RESOURCE_FIELDS":
            if indent != 4:
                return SpecErrorDetail(
                    kind="syntax",
                    code="INCONSISTENT_INDENTATION",
                    message="Expected 4 spaces indentation for resource fields",
                    span=Span(line=line_no, col=1, end_line=line_no, end_col=indent + 1),
                    snippet=raw_line,
                )
        elif state == "IN_SECRETS":
            if indent != 2:
                return SpecErrorDetail(
                    kind="syntax",
                    code="INCONSISTENT_INDENTATION",
                    message="Expected 2 spaces indentation for secret declarations",
                    span=Span(line=line_no, col=1, end_line=line_no, end_col=indent + 1),
                    snippet=raw_line,
                )
        elif state == "IN_ENDPOINT":
            if indent != 2:
                return SpecErrorDetail(
                    kind="syntax",
                    code="INCONSISTENT_INDENTATION",
                    message="Expected 2 spaces indentation for endpoint attributes",
                    span=Span(line=line_no, col=1, end_line=line_no, end_col=indent + 1),
                    snippet=raw_line,
                )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_text(source_text: str) -> Program:
    """Parse a TrustSpec source string into an IR Program.

    Args:
        source_text: Raw (potentially unnormalized) source text.

    Returns:
        A validated, immutable Program IR.

    Raises:
        SourceError: If source exceeds byte limit or has encoding issues.
        TrustSpecError: If source has syntax, reference, or unsupported errors.
    """
    # 1. Check raw byte size BEFORE normalization
    raw_bytes = source_text.encode("utf-8")
    check_input_size(raw_bytes)

    # 2. Normalize CRLF/CR -> LF
    normalized = normalize_source(source_text)

    # 3. Calculate hash
    hash_val = spec_hash(normalized)

    # 4. Check for tabs
    tab_span = check_tabs(normalized)
    if tab_span is not None:
        raise TrustSpecError(
            errors=[
                SpecErrorDetail(
                    kind="syntax",
                    code="TAB_CHARACTER",
                    message=(
                        "Tab characters are not allowed. "
                        "Use spaces for indentation"
                    ),
                    span=tab_span,
                    snippet=_get_snippet(
                        normalized, tab_span.line, tab_span.col
                    ),
                )
            ],
            source_hash=hash_val,
            source=normalized,
        )

    # 4b. Check for inconsistent indentation
    indent_err = check_indentation(normalized)
    if indent_err is not None:
        raise TrustSpecError(
            errors=[indent_err],
            source_hash=hash_val,
            source=normalized,
        )

    # 5. Parse with Lark (append trailing newline if missing for grammar)
    parser = _get_parser()
    source_to_parse = normalized if normalized.endswith("\n") else normalized + "\n"
    try:
        tree = parser.parse(source_to_parse)
    except (UnexpectedToken, UnexpectedCharacters, UnexpectedInput) as exc:
        raise _handle_parse_error(exc, normalized, hash_val) from exc

    # 6. Transform to raw intermediate structures
    transformer = _ASTTransformer()
    raw = transformer.transform(tree)

    # 7. Validate references and build IR
    return _validate_and_build(raw, normalized, hash_val)


def parse_file(path: str | Path) -> Program:
    """Parse a TrustSpec file into an IR Program.

    Args:
        path: Path to a .trust file.

    Returns:
        A validated, immutable Program IR.

    Raises:
        SourceError: If source exceeds byte limit or has encoding issues.
        TrustSpecError: If source has syntax, reference, or unsupported errors.
        FileNotFoundError: If the file doesn't exist.
    """
    file_path = Path(path)
    raw_bytes = file_path.read_bytes()
    check_input_size(raw_bytes)

    try:
        source_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceError(f"File is not valid UTF-8: {exc}") from exc

    return parse_text(source_text)
