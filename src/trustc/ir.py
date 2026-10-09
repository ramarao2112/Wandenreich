"""Immutable Intermediate Representation for TrustSpec programs.

Matches B-compiler-spec.md §B3/B4:
- No raw executable expression, SQL string or secret literal node
- Frozen typed IR nodes with operation enums and validated symbols
- Track absent auth separately from public/required
- Retain source spans for fields and endpoint attributes
- Wrong-but-existing authorization field and role_only remain representable for TC-002
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, FrozenSet, Mapping, Optional, Tuple

from trustc.source import Span

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FieldTypeEnum(str, Enum):
    UUID = "uuid"
    STRING = "string"
    TEXT = "text"
    INT = "int"
    BOOL = "bool"
    EMAIL = "email"


class AuthKind(str, Enum):
    """Auth declaration state."""
    ABSENT = "absent"        # auth: not declared -> TC-001
    REQUIRED = "required"    # auth: required
    PUBLIC = "public"        # auth: public


class EndpointMode(str, Enum):
    """Inferred effective policy for an endpoint per B4."""
    OWNER = "owner"
    SELF = "self"
    LOGIN_ONLY = "login_only"
    PUBLIC = "public"


class OperationKind(str, Enum):
    CREATE = "create"
    LIST = "list"
    READ = "read"
    UPDATE = "update"
    PARTIAL_UPDATE = "partial_update"
    DELETE = "delete"


# ---------------------------------------------------------------------------
# IR Nodes — all frozen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Field:
    """A resource field declaration."""
    name: str
    field_type: FieldTypeEnum
    sensitive: bool
    is_credential: bool  # reserved credential name per B1
    span: Span

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.field_type.value,
            "sensitive": self.sensitive,
            "isCredential": self.is_credential,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class OwnershipExpr:
    """An ownership edge: field -> Resource.id."""
    field_name: str
    target_resource: str
    target_field: str
    span: Span

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field_name,
            "targetResource": self.target_resource,
            "targetField": self.target_field,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class Resource:
    """A resource declaration with its fields."""
    name: str
    fields: Tuple[Field, ...]
    ownership: Optional[OwnershipExpr]
    span: Span  # span of 'resource NAME:'

    @property
    def field_map(self) -> dict[str, Field]:
        return {f.name: f for f in self.fields}

    @property
    def ownership_edge(self) -> Optional[OwnershipExpr]:
        return self.ownership

    def get_field(self, name: str) -> Optional[Field]:
        return self.field_map.get(name)

    @property
    def has_id(self) -> bool:
        return any(f.name == "id" and f.field_type == FieldTypeEnum.UUID for f in self.fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fields": [f.to_dict() for f in self.fields],
            "ownership": self.ownership.to_dict() if self.ownership else None,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class SecretRef:
    """A declared environment variable name, not a value."""
    name: str
    span: Span

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class AuthorizePublic:
    """authorize: public — ownership waiver."""
    span: Span

    def to_dict(self) -> dict[str, Any]:
        return {"type": "public", "span": self.span.to_dict()}


@dataclass(frozen=True)
class AuthorizeEquality:
    """authorize: FIELD == current_user.id — explicit ownership check."""
    field_name: str
    target_field: str  # e.g. 'id' from current_user.id
    span: Span

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "equality",
            "field": self.field_name,
            "targetField": self.target_field,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class RoleOnly:
    """role_only: NAME — unsupported policy, retained for TC-002."""
    role_name: str
    span: Span

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role_name, "span": self.span.to_dict()}


@dataclass(frozen=True)
class ReturnsClause:
    resource: str
    fields: Optional[Tuple[str, ...]]


@dataclass(frozen=True)
class Endpoint:
    """An endpoint declaration with resolved attributes."""
    method: str
    path: str
    resource_name: str
    auth: AuthKind
    authorize: Optional[AuthorizePublic | AuthorizeEquality]
    role_only: Optional[RoleOnly]
    body_fields: Optional[Tuple[str, ...]]  # None = no body declared
    returns_resource: Optional[str]
    returns_projection: Optional[Tuple[str, ...]]  # None = all fields
    expose_fields: Optional[Tuple[str, ...]]  # None = no expose
    operation: OperationKind
    inferred_mode: Optional[EndpointMode]
    owner_waived: bool
    span: Span  # span of 'endpoint METHOD /path:'
    method_span: Span
    path_span: Span
    resource_span: Span  # span of 'resource:' attribute
    auth_span: Optional[Span]  # span of 'auth:' keyword if present
    auth_value_span: Optional[Span]  # span of 'required'/'public' if present
    authorize_span: Optional[Span]  # span of 'authorize:' keyword if present
    role_only_span: Optional[Span]  # span of 'role_only:' keyword if present
    body_span: Optional[Span]  # span of 'body:' keyword if present
    body_field_spans: Optional[Mapping[str, Span]] = None
    returns_span: Optional[Span] = None  # span of 'returns:' keyword if present
    returns_field_spans: Optional[Mapping[str, Span]] = None
    expose_span: Optional[Span] = None
    expose_field_spans: Optional[Mapping[str, Span]] = None

    @property
    def resource(self) -> str:
        return self.resource_name

    @property
    def body(self) -> Tuple[str, ...]:
        return self.body_fields or ()

    @property
    def expose(self) -> Tuple[str, ...]:
        return self.expose_fields or ()

    @property
    def returns(self) -> Optional[ReturnsClause]:
        if self.returns_resource is None:
            return None
        return ReturnsClause(resource=self.returns_resource, fields=self.returns_projection)

    def __post_init__(self) -> None:
        if self.body_field_spans is not None and not isinstance(
            self.body_field_spans, MappingProxyType
        ):
            object.__setattr__(
                self, "body_field_spans", MappingProxyType(dict(self.body_field_spans))
            )
        if self.returns_field_spans is not None and not isinstance(
            self.returns_field_spans, MappingProxyType
        ):
            object.__setattr__(
                self, "returns_field_spans", MappingProxyType(dict(self.returns_field_spans))
            )
        if self.expose_field_spans is not None and not isinstance(
            self.expose_field_spans, MappingProxyType
        ):
            object.__setattr__(
                self, "expose_field_spans", MappingProxyType(dict(self.expose_field_spans))
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "method": self.method,
            "path": self.path,
            "resource": self.resource_name,
            "operation": self.operation.value,
            "auth": self.auth.value,
            "inferredMode": self.inferred_mode.value if self.inferred_mode else None,
            "ownerWaived": self.owner_waived,
            "span": self.span.to_dict(),
        }
        if self.body_fields is not None:
            result["body"] = list(self.body_fields)
        if self.returns_resource is not None:
            proj = (
                list(self.returns_projection)
                if self.returns_projection is not None
                else None
            )
            result["returns"] = {
                "resource": self.returns_resource,
                "projection": proj,
            }
        if self.expose_fields is not None:
            result["expose"] = list(self.expose_fields)
        if self.authorize is not None:
            result["authorize"] = self.authorize.to_dict()
        if self.role_only is not None:
            result["roleOnly"] = self.role_only.to_dict()
        return result


@dataclass(frozen=True)
class Program:
    """The complete parsed and validated TrustSpec program IR."""
    resources: Tuple[Resource, ...]
    secrets: Tuple[SecretRef, ...]
    endpoints: Tuple[Endpoint, ...]
    source: str  # normalized source text
    source_hash: str  # SHA-256 of normalized source
    secrets_span: Optional[Span] = None

    @property
    def resource_map(self) -> dict[str, Resource]:
        return {r.name: r for r in self.resources}

    def get_resource(self, name: str) -> Resource:
        return self.resource_map[name]

    @property
    def has_user(self) -> bool:
        return any(r.name == "User" for r in self.resources)

    @property
    def secret_names(self) -> FrozenSet[str]:
        return frozenset(s.name for s in self.secrets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "specHash": self.source_hash,
            "resources": [r.to_dict() for r in self.resources],
            "secrets": [s.to_dict() for s in self.secrets],
            "endpoints": [e.to_dict() for e in self.endpoints],
        }


# ---------------------------------------------------------------------------
# Reserved names
# ---------------------------------------------------------------------------

PYTHON_KEYWORDS = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
})

CREDENTIAL_FIELDS = frozenset({
    "password", "password_hash", "access_token", "refresh_token",
    "api_key", "private_key", "jwt_secret",
})

GENERATED_RESERVED_NAMES = frozenset({
    "metadata", "registry", "model_config",
    "app", "router", "main", "models", "schemas", "auth", "db",
    "routers", "Base", "engine", "SessionLocal", "get_db",
    "create_access_token", "get_current_user",
    "HTTPException", "Depends", "APIRouter", "FastAPI",
})

VALID_TYPES = frozenset(t.value for t in FieldTypeEnum)
SUPPORTED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def is_credential_field(name: str) -> bool:
    """Check if a field name is a reserved credential name (case-insensitive)."""
    return name.lower() in CREDENTIAL_FIELDS


def is_valid_identifier(name: str) -> bool:
    """Check if a name is a valid TrustSpec identifier."""
    import re
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', name):
        return False
    if name in PYTHON_KEYWORDS:
        return False
    if name.startswith("__") and name.endswith("__"):
        return False
    return True


def is_reserved_name(name: str) -> bool:
    """Check if a name collides with generated module/class names."""
    return name.lower() in {n.lower() for n in GENERATED_RESERVED_NAMES}
