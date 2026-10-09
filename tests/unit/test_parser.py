"""Stage 2 tests -- Grammar, positions, reference validation and IR.

Covers all acceptance criteria from TrustC-Stage-Pack-v3/stage-2-parse.md:
- All F fixtures parsed (all valid except F4)
- F4 exact error span (23:25) and code 2
- F7 retains role_only
- F7b retains wrong-field authorization
- F2 has owner policy for Trip and self policy for User
- F3 waiver span is 37:3
- X03 / X04 fail deterministically
- Table-driven expected policies
- Unicode, CRLF, no-final-newline, tab detection, byte limits
- Name, path, and shape validation
- Immutable IR (frozen dataclasses)
- CLI parse behavior (F2 exits 0, F4 exits 2)
"""

from __future__ import annotations

import json
import unittest.mock as mock
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from trustc.cli import main as cli_main
from trustc.ir import (
    AuthKind,
    AuthorizeEquality,
    AuthorizePublic,
    EndpointMode,
    Program,
    RoleOnly,
)
from trustc.parser import (
    TrustSpecError,
    parse_file,
    parse_text,
)
from trustc.source import (
    MAX_INPUT_BYTES,
    SourceError,
    check_input_size,
    spec_hash,
)

pytestmark = pytest.mark.stage2

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# 1. Canonical F-fixtures parsing tests
# ---------------------------------------------------------------------------

class TestCanonicalFFixtures:
    """All F inputs except F4 parse; F4 fails with syntax error at 23:25."""

    @pytest.mark.parametrize("name", ["F1", "F2", "F3", "F5", "F6", "F7", "F7b"])
    def test_valid_f_fixtures_parse_successfully(self, name: str) -> None:
        path = FIXTURES_DIR / f"{name}.trust"
        prog = parse_file(path)
        assert isinstance(prog, Program)
        assert len(prog.resources) >= 1
        assert len(prog.endpoints) >= 1
        assert prog.has_user

    def test_f4_syntax_error_exact_span(self) -> None:
        path = FIXTURES_DIR / "F4.trust"
        with pytest.raises(TrustSpecError) as exc_info:
            parse_file(path)

        err = exc_info.value
        assert len(err.errors) == 1
        detail = err.errors[0]
        assert detail.kind == "syntax"
        assert detail.span.line == 23
        assert detail.span.col == 25
        assert ":" in detail.message or "COLON" in detail.message


# ---------------------------------------------------------------------------
# 2. Policy resolution and representation tests
# ---------------------------------------------------------------------------

class TestPolicyResolution:
    """Validate policy inference and preservation in IR."""

    def test_f2_endpoint_policies(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F2.trust")
        endpoints = {f"{e.method} {e.path}": e for e in prog.endpoints}

        # POST /trips -> owner policy
        post_trip = endpoints["POST /trips"]
        assert post_trip.auth == AuthKind.REQUIRED
        assert post_trip.inferred_mode == EndpointMode.OWNER
        assert not post_trip.owner_waived

        # GET /trips/{id} -> owner policy
        get_trip = endpoints["GET /trips/{id}"]
        assert get_trip.auth == AuthKind.REQUIRED
        assert get_trip.inferred_mode == EndpointMode.OWNER
        assert not get_trip.owner_waived

        # GET /users/{id} -> self policy
        get_user = endpoints["GET /users/{id}"]
        assert get_user.auth == AuthKind.REQUIRED
        assert get_user.inferred_mode == EndpointMode.SELF
        assert not get_user.owner_waived

    def test_f3_ownership_waiver_span(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F3.trust")
        endpoints = {f"{e.method} {e.path}": e for e in prog.endpoints}

        put_vis = endpoints["PUT /trips/{id}/visibility"]
        assert put_vis.auth == AuthKind.REQUIRED
        assert put_vis.inferred_mode == EndpointMode.OWNER
        assert put_vis.owner_waived is True
        assert isinstance(put_vis.authorize, AuthorizePublic)
        assert put_vis.authorize.span.line == 37
        assert put_vis.authorize.span.col == 3

    def test_f7_retains_role_only(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F7.trust")
        endpoints = {f"{e.method} {e.path}": e for e in prog.endpoints}

        get_trip = endpoints["GET /trips/{id}"]
        assert get_trip.role_only is not None
        assert isinstance(get_trip.role_only, RoleOnly)
        assert get_trip.role_only.role_name == "admin"
        assert get_trip.role_only.span.line == 26
        assert get_trip.role_only.span.col == 3

    def test_f7b_retains_wrong_field_authorization(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F7b.trust")
        endpoints = {f"{e.method} {e.path}": e for e in prog.endpoints}

        get_trip = endpoints["GET /trips/{id}"]
        assert isinstance(get_trip.authorize, AuthorizeEquality)
        assert get_trip.authorize.field_name == "id"
        assert get_trip.authorize.target_field == "id"
        assert get_trip.authorize.span.line == 26
        assert get_trip.authorize.span.col == 3

    def test_f1_absent_auth_retained(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F1.trust")
        endpoints = {f"{e.method} {e.path}": e for e in prog.endpoints}

        get_trip = endpoints["GET /trips/{id}"]
        assert get_trip.auth == AuthKind.ABSENT
        assert get_trip.span.line == 23
        assert get_trip.span.col == 1

        get_user = endpoints["GET /users/{id}"]
        assert get_user.returns_span is not None
        assert get_user.returns_span.line == 30
        assert get_user.returns_span.col == 3

    def test_f5_body_field_span(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F5.trust")
        endpoints = {f"{e.method} {e.path}": e for e in prog.endpoints}

        post_trip = endpoints["POST /trips"]
        assert post_trip.body_field_spans is not None
        assert "owner_id" in post_trip.body_field_spans
        owner_id_span = post_trip.body_field_spans["owner_id"]
        assert owner_id_span.line == 20
        assert owner_id_span.col == 23


# ---------------------------------------------------------------------------
# 3. Spec error fixtures tests (X03, X04)
# ---------------------------------------------------------------------------

class TestSpecErrorFixtures:
    """X03 and X04 must fail deterministically with SpecErrors."""

    def test_x03_multiple_ownership_edges_rejected(self) -> None:
        path = FIXTURES_DIR / "X03.trust"
        with pytest.raises(TrustSpecError) as exc_info:
            parse_file(path)
        err = exc_info.value
        codes = [e.code for e in err.errors]
        assert "MULTIPLE_OWNERSHIP" in codes

    def test_x04_unknown_projected_field_rejected(self) -> None:
        path = FIXTURES_DIR / "X04.trust"
        with pytest.raises(TrustSpecError) as exc_info:
            parse_file(path)
        err = exc_info.value
        codes = [e.code for e in err.errors]
        assert "UNKNOWN_FIELD" in codes
        unknown_err = next(e for e in err.errors if e.code == "UNKNOWN_FIELD")
        assert "nonexistent_field" in unknown_err.message
        assert unknown_err.span.line == 13
        assert unknown_err.span.col == 22


# ---------------------------------------------------------------------------
# 4. Source normalization and span tests
# ---------------------------------------------------------------------------

class TestSourceHandling:
    """Verify normalization, byte limits, hashes, CRLF, and tabs."""

    def test_crlf_normalized_to_lf(self) -> None:
        crlf_source = (
            "resource User:\r\n  fields:\r\n    id: uuid\r\n\r\n"
            "endpoint GET /users/{id}:\r\n  resource: User\r\n"
            "  auth: required\r\n  returns: User\r\n"
        )
        prog = parse_text(crlf_source)
        assert "\r" not in prog.source
        assert prog.source == crlf_source.replace("\r\n", "\n")

    def test_no_trailing_newline_accepted(self) -> None:
        source_no_nl = (
            "resource User:\n  fields:\n    id: uuid\n\n"
            "endpoint GET /users/{id}:\n  resource: User\n"
            "  auth: required\n  returns: User"
        )
        prog = parse_text(source_no_nl)
        assert len(prog.endpoints) == 1

    def test_tab_characters_rejected(self) -> None:
        tab_source = (
            "resource User:\n\tfields:\n    id: uuid\n\n"
            "endpoint GET /users/{id}:\n  resource: User\n"
            "  auth: required\n  returns: User\n"
        )
        with pytest.raises(TrustSpecError) as exc_info:
            parse_text(tab_source)
        err = exc_info.value
        assert err.errors[0].code == "TAB_CHARACTER"
        assert err.errors[0].span.line == 2
        assert err.errors[0].span.col == 1

    def test_byte_limit_exceeded_rejected(self) -> None:
        oversized = "resource User:\n  fields:\n    id: uuid\n" + ("# comment\n" * 35000)
        assert len(oversized.encode("utf-8")) > MAX_INPUT_BYTES
        with pytest.raises(SourceError) as exc_info:
            parse_text(oversized)
        assert "byte limit" in str(exc_info.value)

    def test_non_ascii_comment_preserved(self) -> None:
        source = (
            "# Unicode comment: 你好,世界 🚀\n"
            "resource User:\n  fields:\n    id: uuid\n\n"
            "endpoint GET /users/{id}:\n  resource: User\n"
            "  auth: required\n  returns: User\n"
        )
        prog = parse_text(source)
        assert len(prog.resources) == 1
        assert prog.endpoints[0].span.line == 6

    def test_trailing_newline_presence_hashes_differently(self) -> None:
        """Preserve final-newline presence and verify hashing differs."""
        base = (
            "resource User:\n  fields:\n    id: uuid\n\n"
            "endpoint GET /users/{id}:\n  resource: User\n"
            "  auth: required\n  returns: User"
        )
        source_no_nl = base
        source_with_nl = base + "\n"

        prog_no_nl = parse_text(source_no_nl)
        prog_with_nl = parse_text(source_with_nl)

        assert prog_no_nl.source == source_no_nl
        assert prog_with_nl.source == source_with_nl
        assert not prog_no_nl.source.endswith("\n")
        assert prog_with_nl.source.endswith("\n")
        assert prog_no_nl.source_hash != prog_with_nl.source_hash
        assert prog_no_nl.source_hash == spec_hash(source_no_nl)
        assert prog_with_nl.source_hash == spec_hash(source_with_nl)

    def test_exact_byte_boundary_and_crlf_shrink(self) -> None:
        """Enforce 262144 raw bytes before normalization."""
        # 1. Exact limit (262,144 bytes) passes check_input_size
        header = b"resource User:\n  fields:\n    id: uuid\n"
        exact_bytes = header + (b"# " + b"a" * 60 + b"\n") * 4220
        exact_bytes = exact_bytes[:MAX_INPUT_BYTES]
        assert len(exact_bytes) == MAX_INPUT_BYTES
        check_input_size(exact_bytes)

        # 2. One byte over (262,145 bytes) fails
        oversized_bytes = exact_bytes + b"x"
        assert len(oversized_bytes) == MAX_INPUT_BYTES + 1
        with pytest.raises(SourceError, match="Input exceeds 262144 byte limit"):
            check_input_size(oversized_bytes)

        # 3. Multibyte characters exceeding boundary
        multibyte_prefix = "resource User:\n  fields:\n    id: uuid\n# "
        # 3-byte unicode character '日'
        multibyte_fill = "日" * (MAX_INPUT_BYTES // 3 + 10)
        multibyte_str = multibyte_prefix + multibyte_fill + "\n"
        assert len(multibyte_str.encode("utf-8")) > MAX_INPUT_BYTES
        with pytest.raises(SourceError):
            parse_text(multibyte_str)

        # 4. CRLF input that would shrink below limit after normalization
        # Create input of 262145 raw bytes containing \r\n
        crlf_header = "resource User:\r\n  fields:\r\n    id: uuid\r\n"
        filler = "# " + "a" * 50 + "\r\n"
        raw_crlf = (crlf_header + filler * 5100).encode("utf-8")
        # Trim to exactly MAX_INPUT_BYTES + 1
        raw_crlf = raw_crlf[:MAX_INPUT_BYTES + 1]
        assert len(raw_crlf) == MAX_INPUT_BYTES + 1
        # If normalized to LF, it would be smaller than MAX_INPUT_BYTES
        normalized_str = raw_crlf.decode("utf-8", errors="ignore").replace("\r\n", "\n")
        assert len(normalized_str.encode("utf-8")) <= MAX_INPUT_BYTES
        # But check_input_size must reject the raw bytes before normalization!
        with pytest.raises(SourceError):
            parse_text(raw_crlf.decode("utf-8", errors="ignore"))

    def test_exact_diagnostic_span_after_non_ascii_comment(self) -> None:
        """Verify an exact diagnostic/source span after a non-ASCII comment."""
        source = (
            "# 🚀 Non-ASCII comment: 日本語テスト\n"
            "resource User:\n"
            "  fields:\n"
            "    id: uuid\n\n"
            "endpoint GET /trips/{id}\n"
            "  resource: User\n"
            "  auth: required\n"
            "  returns: User\n"
        )
        with pytest.raises(TrustSpecError) as exc_info:
            parse_text(source)
        err = exc_info.value.errors[0]
        assert err.kind == "syntax"
        # Line 6 is 'endpoint GET /trips/{id}' (length 24), missing colon is at col 25
        assert err.span.line == 6
        assert err.span.col == 25

    def test_lone_cr_handling(self) -> None:
        """Lone CR without LF is normalized and accepted."""
        source = (
            "resource User:\r  fields:\r    id: uuid\r\r"
            "endpoint GET /users/{id}:\r  resource: User\r"
            "  auth: required\r  returns: User\r"
        )
        prog = parse_text(source)
        assert "\r" not in prog.source
        assert len(prog.resources) == 1
        assert len(prog.endpoints) == 1

    def test_inconsistent_indentation_rejected(self) -> None:
        """Reject indentation that deviates from B1 specification."""
        # Top-level indented with 2 spaces
        top_indented = (
            "  resource User:\n    fields:\n      id: uuid\n\n"
            "endpoint GET /users/{id}:\n  resource: User\n  auth: required\n  returns: User\n"
        )
        with pytest.raises(TrustSpecError) as exc1:
            parse_text(top_indented)
        assert exc1.value.errors[0].code == "INCONSISTENT_INDENTATION"

        # fields: with 3 spaces instead of 2
        bad_fields_indent = (
            "resource User:\n   fields:\n    id: uuid\n\n"
            "endpoint GET /users/{id}:\n  resource: User\n  auth: required\n  returns: User\n"
        )
        with pytest.raises(TrustSpecError) as exc2:
            parse_text(bad_fields_indent)
        assert exc2.value.errors[0].code == "INCONSISTENT_INDENTATION"

        # field decl with 2 spaces instead of 4
        bad_field_indent = (
            "resource User:\n  fields:\n  id: uuid\n\n"
            "endpoint GET /users/{id}:\n  resource: User\n  auth: required\n  returns: User\n"
        )
        with pytest.raises(TrustSpecError) as exc3:
            parse_text(bad_field_indent)
        assert exc3.value.errors[0].code == "INCONSISTENT_INDENTATION"

    def test_unrelated_malformed_declaration_error_position(self) -> None:
        """Confirm malformed declarations retain their actual error positions, not F4's 23:25."""
        # Error on line 2, missing colon after User
        source = "resource User\n  fields:\n    id: uuid\n"
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        err = exc.value.errors[0]
        assert err.span.line == 1
        assert err.span.col == 14


# ---------------------------------------------------------------------------
# 5. Validation rules: syntax, references, shape
# ---------------------------------------------------------------------------

class TestValidationRules:
    """Validate all reference, shape, and identifier rules."""

    def test_duplicate_resource_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

resource User:
  fields:
    id: uuid

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "DUPLICATE_RESOURCE" for e in exc.value.errors)

    def test_duplicate_field_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid
    email: string
    email: string

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "DUPLICATE_FIELD" for e in exc.value.errors)

    def test_duplicate_endpoint_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "DUPLICATE_ENDPOINT" for e in exc.value.errors)

    def test_duplicate_endpoint_attr_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

endpoint GET /users/{id}:
  resource: User
  auth: required
  auth: public
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "DUPLICATE_ATTR" for e in exc.value.errors)

    def test_missing_user_resource_rejected(self) -> None:
        source = """
resource Trip:
  fields:
    id: uuid

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "MISSING_USER" for e in exc.value.errors)

    def test_missing_id_uuid_rejected(self) -> None:
        source = """
resource User:
  fields:
    name: string

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "MISSING_ID" for e in exc.value.errors)

    def test_unsupported_field_type_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid
    status: enum

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "UNSUPPORTED_TYPE" for e in exc.value.errors)

    def test_user_ownership_edge_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid
    owner_id: uuid -> User.id

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "USER_OWNERSHIP" for e in exc.value.errors)

    def test_ownership_target_not_user_id_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> Trip.id

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "INVALID_OWNERSHIP_TARGET" for e in exc.value.errors)

    def test_reserved_resource_name_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

resource FastAPI:
  fields:
    id: uuid

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "RESERVED_NAME" for e in exc.value.errors)

    def test_python_keyword_identifier_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid
    def: string

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "INVALID_IDENTIFIER" for e in exc.value.errors)

    def test_invalid_path_pattern_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

endpoint GET /users?status=active:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "INVALID_PATH" or e.kind == "syntax" for e in exc.value.errors)

    def test_body_on_get_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid
    email: string

endpoint GET /users/{id}:
  resource: User
  auth: required
  body: [email]
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "BODY_NOT_ALLOWED" for e in exc.value.errors)

    def test_missing_body_on_put_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id
    destination: string

endpoint PUT /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "MISSING_BODY" for e in exc.value.errors)

    def test_cross_resource_returns_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "CROSS_RESOURCE_RETURNS" for e in exc.value.errors)

    def test_source_after_endpoints_rejected(self) -> None:
        source = """
resource User:
  fields:
    id: uuid

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User

resource Trip:
  fields:
    id: uuid
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert exc.value.errors[0].kind == "syntax"

    def test_forbidden_user_operations_rejected(self) -> None:
        """v1 User endpoint is only 'GET /users/{id}'; other operations are rejected."""
        cases = [
            ("POST", "/users", "body: [email]\n  returns: User"),
            ("GET", "/users", "returns: User"),
            ("DELETE", "/users/{id}", ""),
            ("PUT", "/users/{id}", "body: [email]\n  returns: User"),
        ]
        for method, path, extra in cases:
            source = f"""
resource User:
  fields:
    id: uuid
    email: string

endpoint {method} {path}:
  resource: User
  auth: required
  {extra}
"""
            with pytest.raises(TrustSpecError) as exc:
                parse_text(source)
            codes = [e.code for e in exc.value.errors]
            assert "FORBIDDEN_USER_OPERATION" in codes, f"Failed for {method} {path}"

    def test_case_insensitive_reserved_names_and_collisions(self) -> None:
        """Reject reserved generated names regardless of case."""
        for name in ["app", "METADATA", "Schemas", "ROUTER", "Model_Config"]:
            source = f"""
resource User:
  fields:
    id: uuid

resource {name}:
  fields:
    id: uuid

endpoint GET /users/{{id}}:
  resource: User
  auth: required
  returns: User
"""
            with pytest.raises(TrustSpecError) as exc:
                parse_text(source)
            assert any(e.code == "RESERVED_NAME" for e in exc.value.errors), f"Failed for {name}"

    def test_duplicate_projected_fields_rejected(self) -> None:
        """Reject duplicate fields in returns projection, expose, and body."""
        # 1. Duplicate in returns projection
        source_returns = """
resource User:
  fields:
    id: uuid
    email: string

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User [id, email, id]
"""
        with pytest.raises(TrustSpecError) as exc1:
            parse_text(source_returns)
        assert any(e.code == "DUPLICATE_PROJECTED_FIELD" for e in exc1.value.errors)

        # 2. Duplicate in expose
        source_expose = """
resource User:
  fields:
    id: uuid
    password_hash: string [sensitive]

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User [id, password_hash]
  expose: [password_hash, password_hash]
"""
        with pytest.raises(TrustSpecError) as exc2:
            parse_text(source_expose)
        assert any(e.code == "DUPLICATE_PROJECTED_FIELD" for e in exc2.value.errors)

        # 3. Duplicate in body
        source_body = """
resource User:
  fields:
    id: uuid

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id
    destination: string

endpoint POST /trips:
  resource: Trip
  auth: required
  body: [destination, destination]
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc3:
            parse_text(source_body)
        assert any(e.code == "DUPLICATE_FIELD" for e in exc3.value.errors)

    def test_duplicate_secrets_rejected(self) -> None:
        """Reject duplicate secret declarations."""
        source = """
resource User:
  fields:
    id: uuid

secrets:
  DB_URL: env
  DB_URL: env

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "DUPLICATE_SECRET" for e in exc.value.errors)

    def test_non_uuid_ownership_edge_rejected(self) -> None:
        """Ownership fields must be uuid type."""
        source = """
resource User:
  fields:
    id: uuid

resource Trip:
  fields:
    id: uuid
    owner_id: string -> User.id

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source)
        assert any(e.code == "INVALID_OWNERSHIP_TYPE" for e in exc.value.errors)

    def test_invalid_ownership_target_rejected(self) -> None:
        """Ownership edge must target User.id, not other fields or resources."""
        # Target wrong field on User
        source1 = """
resource User:
  fields:
    id: uuid
    email: string

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.email

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc1:
            parse_text(source1)
        assert any(e.code == "INVALID_OWNERSHIP_TARGET" for e in exc1.value.errors)

        # Target non-User resource
        source2 = """
resource User:
  fields:
    id: uuid

resource Organization:
  fields:
    id: uuid

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> Organization.id

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc2:
            parse_text(source2)
        assert any(e.code == "INVALID_OWNERSHIP_TARGET" for e in exc2.value.errors)

    def test_permitted_and_forbidden_return_body_combinations(self) -> None:
        """Validate return/body combinations per B2."""
        # 1. DELETE with returns rejected
        del_returns = """
resource User:
  fields:
    id: uuid
resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id

endpoint DELETE /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc1:
            parse_text(del_returns)
        assert any(e.code == "RETURNS_NOT_ALLOWED" for e in exc1.value.errors)

        # 2. DELETE with body rejected
        del_body = """
resource User:
  fields:
    id: uuid
resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id

endpoint DELETE /trips/{id}:
  resource: Trip
  auth: required
  body: [id]
"""
        with pytest.raises(TrustSpecError) as exc2:
            parse_text(del_body)
        assert any(e.code == "BODY_NOT_ALLOWED" for e in exc2.value.errors)

        # 3. GET with body rejected
        get_body = """
resource User:
  fields:
    id: uuid
endpoint GET /users/{id}:
  resource: User
  auth: required
  body: [id]
  returns: User
"""
        with pytest.raises(TrustSpecError) as exc3:
            parse_text(get_body)
        assert any(e.code == "BODY_NOT_ALLOWED" for e in exc3.value.errors)

        # 4. GET without returns rejected
        get_no_ret = """
resource User:
  fields:
    id: uuid
endpoint GET /users/{id}:
  resource: User
  auth: required
"""
        with pytest.raises(TrustSpecError) as exc4:
            parse_text(get_no_ret)
        assert any(e.code == "MISSING_RETURNS" for e in exc4.value.errors)

        # 5. POST on resource without writable inputs parses cleanly without body
        post_no_writable = """
resource User:
  fields:
    id: uuid
resource Tag:
  fields:
    id: uuid
    owner_id: uuid -> User.id

endpoint POST /tags:
  resource: Tag
  auth: required
  returns: Tag
"""
        prog = parse_text(post_no_writable)
        assert len(prog.endpoints) == 1
        assert prog.endpoints[0].body_fields is None

    def test_wrong_but_existing_auth_field_preserved(self) -> None:
        """Existing wrong auth field is preserved in IR for TC-002, unknown is rejected."""
        # 1. Existing field 'destination' (wrong auth field on Trip, but exists) -> preserved
        source_existing = """
resource User:
  fields:
    id: uuid
resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id
    destination: string

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  authorize: destination == current_user.id
  returns: Trip
"""
        prog = parse_text(source_existing)
        ep = prog.endpoints[0]
        assert isinstance(ep.authorize, AuthorizeEquality)
        assert ep.authorize.field_name == "destination"

        # 2. Truly unknown field in authorize -> rejected as reference error
        source_unknown = """
resource User:
  fields:
    id: uuid
resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  authorize: totally_unknown == current_user.id
  returns: Trip
"""
        with pytest.raises(TrustSpecError) as exc:
            parse_text(source_unknown)
        assert any(e.code == "UNKNOWN_FIELD" for e in exc.value.errors)


# ---------------------------------------------------------------------------
# 6. Immutable IR tests
# ---------------------------------------------------------------------------

class TestImmutableIR:
    """IR nodes are frozen dataclasses and cannot be modified."""

    def test_program_and_nodes_are_frozen(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F2.trust")

        with pytest.raises(FrozenInstanceError):
            prog.resources = ()  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            prog.resources[0].name = "Changed"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            prog.resources[0].fields[0].name = "changed"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            prog.endpoints[0].method = "DELETE"  # type: ignore[misc]

    def test_deep_immutability_of_endpoint_spans(self) -> None:
        """Nested containers such as field spans are wrapped in MappingProxyType."""
        prog = parse_file(FIXTURES_DIR / "F2.trust")
        endpoints = {f"{e.method} {e.path}": e for e in prog.endpoints}

        # Attempt to mutate body_field_spans
        post_trip = endpoints["POST /trips"]
        assert post_trip.body_field_spans is not None
        with pytest.raises(TypeError):
            post_trip.body_field_spans["destination"] = post_trip.span  # type: ignore[index]

        # Attempt to mutate returns_field_spans
        get_user = endpoints["GET /users/{id}"]
        assert get_user.returns_field_spans is not None
        with pytest.raises(TypeError):
            get_user.returns_field_spans["email"] = get_user.span  # type: ignore[index]

    def test_to_dict_matches_v2_schema(self) -> None:
        prog = parse_file(FIXTURES_DIR / "F2.trust")
        d = prog.to_dict()

        assert d["schemaVersion"] == 2
        assert d["specHash"] == prog.source_hash
        assert isinstance(d["resources"], list)
        assert isinstance(d["secrets"], list)
        assert isinstance(d["endpoints"], list)

        # Serializes cleanly to JSON
        json_str = json.dumps(d)
        assert isinstance(json_str, str)


# ---------------------------------------------------------------------------
# 7. Grammar, LALR construction, and conflict checks
# ---------------------------------------------------------------------------

class TestGrammarAndLALR:
    """Record Lark LALR grammar construction and conflict check status."""

    def test_lark_lalr_grammar_builds_without_conflicts(self) -> None:
        from pathlib import Path

        import lark
        repo_root = Path(__file__).resolve().parent.parent.parent
        grammar_path = repo_root / "src" / "trustc" / "grammars" / "trustspec.lark"
        grammar_text = grammar_path.read_text(encoding="utf-8")

        # Lark LALR parser creation performs standard shift/reduce & reduce/reduce conflict checks
        parser = lark.Lark(
            grammar_text,
            parser="lalr",
            propagate_positions=True,
        )
        assert parser is not None
        # Record Lark version and strict check availability
        assert lark.__version__ >= "1.1"


# ---------------------------------------------------------------------------
# 8. Internal exception handling
# ---------------------------------------------------------------------------

class TestInternalExceptions:
    """Internal exceptions remain execution failures rather than mislabeled syntax errors."""

    def test_internal_exception_not_mislabeled_as_syntax_error(self) -> None:
        with mock.patch("trustc.parser._get_parser") as mock_get_parser:
            mock_parser = mock.MagicMock()
            mock_parser.parse.side_effect = RuntimeError("Internal compiler error")
            mock_get_parser.return_value = mock_parser

            valid_src = (
                "resource User:\n  fields:\n    id: uuid\n\n"
                "endpoint GET /users/{id}:\n  resource: User\n  auth: required\n  returns: User\n"
            )
            with pytest.raises(RuntimeError, match="Internal compiler error"):
                parse_text(valid_src)


# ---------------------------------------------------------------------------
# 9. CLI command tests
# ---------------------------------------------------------------------------

class TestCLIParse:
    """trustc parse CLI behavior."""

    def test_cli_parse_f2_exits_0(self) -> None:
        code = cli_main(["parse", str(FIXTURES_DIR / "F2.trust")])
        assert code == 0

    def test_cli_parse_f4_exits_2(self) -> None:
        code = cli_main(["parse", str(FIXTURES_DIR / "F4.trust")])
        assert code == 2

    def test_cli_parse_nonexistent_exits_2(self) -> None:
        code = cli_main(["parse", "nonexistent_file.trust"])
        assert code == 2
