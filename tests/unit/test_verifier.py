"""Stage 3 unit tests — five B5 security rules and verifier engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from trustc.contracts import CheckResult, RuleId, SpecErrorKind
from trustc.verifier import (
    check_file,
    check_text,
    format_human_report,
)

pytestmark = pytest.mark.stage3

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Canonical Fixture Tests
# ---------------------------------------------------------------------------

class TestCanonicalFixtures:
    def test_f1_auth_and_sensitive_leak(self):
        result = check_file(FIXTURES_DIR / "F1.trust")
        assert result.exit_code == 1
        assert not result.ok
        assert result.rules_run == 5
        assert result.endpoints == 3

        rule_map = {r.rule_id: r for r in result.rules}
        assert rule_map[RuleId.TC_001].status == "failed"
        assert rule_map[RuleId.TC_002].status == "passed"
        assert rule_map[RuleId.TC_003].status == "failed"
        assert rule_map[RuleId.TC_004].status == "passed"
        assert rule_map[RuleId.TC_005].status == "passed"

        assert len(result.diagnostics) == 2
        d1, d2 = result.diagnostics
        assert d1.rule_id == RuleId.TC_001
        assert d1.span.line == 23
        assert d1.span.col == 1

        assert d2.rule_id == RuleId.TC_003
        assert d2.span.line == 30
        assert d2.span.col == 3

    def test_f2_clean(self):
        result = check_file(FIXTURES_DIR / "F2.trust")
        assert result.exit_code == 0
        assert result.ok
        assert result.rules_run == 5
        assert result.endpoints == 3
        assert len(result.diagnostics) == 0
        assert all(r.status == "passed" for r in result.rules)

    def test_f3_clean_with_ownership_waiver(self):
        result = check_file(FIXTURES_DIR / "F3.trust")
        assert result.exit_code == 0
        assert result.ok
        assert result.rules_run == 5
        assert result.endpoints == 4
        assert len(result.diagnostics) == 0
        assert all(r.status == "passed" for r in result.rules)

    def test_f4_syntax_error_no_rules_run(self):
        result = check_file(FIXTURES_DIR / "F4.trust")
        assert result.exit_code == 2
        assert not result.ok
        assert result.rules_run == 0
        assert len(result.rules) == 0
        assert len(result.diagnostics) == 0
        assert len(result.spec_errors) == 1
        err = result.spec_errors[0]
        assert err.kind == SpecErrorKind.SYNTAX
        assert err.span.line == 23
        assert err.span.col == 25

    def test_f5_mass_assignment(self):
        result = check_file(FIXTURES_DIR / "F5.trust")
        assert result.exit_code == 1
        assert not result.ok
        assert len(result.diagnostics) == 1
        d = result.diagnostics[0]
        assert d.rule_id == RuleId.TC_004
        assert d.span.line == 20
        assert d.span.col == 23
        assert "owner_id" in d.message

    def test_f6_missing_jwt_secret(self):
        result = check_file(FIXTURES_DIR / "F6.trust")
        assert result.exit_code == 1
        assert not result.ok
        assert len(result.diagnostics) == 1
        d = result.diagnostics[0]
        assert d.rule_id == RuleId.TC_005
        assert d.span.line == 13
        assert d.span.col == 1
        assert "JWT_SECRET" in d.message

    def test_f7_role_only_unsupported(self):
        result = check_file(FIXTURES_DIR / "F7.trust")
        assert result.exit_code == 1
        assert not result.ok
        assert len(result.diagnostics) == 1
        d = result.diagnostics[0]
        assert d.rule_id == RuleId.TC_002
        assert d.span.line == 26
        assert d.span.col == 3
        assert "role_only" in d.message

    def test_f7b_wrong_authorization_field(self):
        result = check_file(FIXTURES_DIR / "F7b.trust")
        assert result.exit_code == 1
        assert not result.ok
        assert len(result.diagnostics) == 1
        d = result.diagnostics[0]
        assert d.rule_id == RuleId.TC_002
        assert d.span.line == 26
        assert d.span.col == 3
        assert "wrong field" in d.message.lower()


# ---------------------------------------------------------------------------
# Additional Scenario Fixtures (X01, X02, X05, X06, X07, X14, X15)
# ---------------------------------------------------------------------------

class TestScenarioFixtures:
    def test_x01_public_owned_post_rejected(self):
        result = check_file(FIXTURES_DIR / "X01.trust")
        assert result.exit_code == 1
        assert any(d.rule_id == RuleId.TC_002 for d in result.diagnostics)

    def test_x02_public_user_get_rejected(self):
        result = check_file(FIXTURES_DIR / "X02.trust")
        assert result.exit_code == 1
        assert any(d.rule_id == RuleId.TC_002 for d in result.diagnostics)

    def test_x05_ordinary_sensitive_with_expose_passes(self):
        result = check_file(FIXTURES_DIR / "X05.trust")
        assert result.exit_code == 0
        assert result.ok
        assert len(result.diagnostics) == 0

    def test_x06_credential_with_expose_rejected(self):
        result = check_file(FIXTURES_DIR / "X06.trust")
        assert result.exit_code == 1
        assert any(d.rule_id == RuleId.TC_003 for d in result.diagnostics)

    def test_x07_id_in_body_rejected(self):
        result = check_file(FIXTURES_DIR / "X07.trust")
        assert result.exit_code == 1
        assert any(d.rule_id == RuleId.TC_004 for d in result.diagnostics)

    def test_x14_missing_secrets_block(self):
        result = check_file(FIXTURES_DIR / "X14.trust")
        assert result.exit_code == 1
        tc005_diags = [d for d in result.diagnostics if d.rule_id == RuleId.TC_005]
        assert len(tc005_diags) == 1
        # Span points to first endpoint when secrets block is absent
        assert tc005_diags[0].span.line == 6
        assert tc005_diags[0].span.col == 1

    def test_x15_non_ascii_comment_tc001(self):
        result = check_file(FIXTURES_DIR / "X15.trust")
        assert result.exit_code == 1
        tc001_diags = [d for d in result.diagnostics if d.rule_id == RuleId.TC_001]
        assert len(tc001_diags) == 1
        assert tc001_diags[0].span.line == 11
        assert tc001_diags[0].span.col == 1


# ---------------------------------------------------------------------------
# Individual Rule Deep Dive
# ---------------------------------------------------------------------------

class TestIndividualRules:
    def test_tc001_missing_auth(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /users/{id}:
  resource: User
  returns: User [id, email]
"""
        res = check_text(spec)
        assert res.exit_code == 1
        assert len(res.diagnostics) == 1
        d = res.diagnostics[0]
        assert d.rule_id == RuleId.TC_001
        assert d.fix.type == "diff"
        assert "Suggested restrictive default" in d.fix.label

    def test_tc002_user_ownership_waiver_rejected(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /users/{id}:
  resource: User
  auth: required
  authorize: public
  returns: User [id, email]
"""
        res = check_text(spec)
        assert res.exit_code == 1
        assert any(d.rule_id == RuleId.TC_002 for d in res.diagnostics)

    def test_tc002_unowned_authorize_rejected(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string

resource Item:
  fields:
    id: uuid
    title: string

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /items/{id}:
  resource: Item
  auth: required
  authorize: public
  returns: Item [id, title]
"""
        res = check_text(spec)
        assert res.exit_code == 1
        tc002 = [d for d in res.diagnostics if d.rule_id == RuleId.TC_002]
        assert len(tc002) == 1
        assert "unowned" in tc002[0].why.lower()

    def test_tc002_contradictory_public_and_authorize_rejected(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /trips/{id}:
  resource: Trip
  auth: public
  authorize: public
  returns: Trip [id]
"""
        res = check_text(spec)
        assert res.exit_code == 1
        tc002 = [d for d in res.diagnostics if d.rule_id == RuleId.TC_002]
        assert len(tc002) == 1
        assert "contradictory" in tc002[0].message.lower()

    def test_tc002_owned_post_with_authorize_rejected(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string

resource Trip:
  fields:
    id: uuid
    owner_id: uuid -> User.id

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint POST /trips:
  resource: Trip
  auth: required
  authorize: public
  body: []
  returns: Trip [id]
"""
        res = check_text(spec)
        assert res.exit_code == 1
        tc002 = [d for d in res.diagnostics if d.rule_id == RuleId.TC_002]
        assert len(tc002) == 1
        assert "creation" in tc002[0].message.lower()

    def test_tc003_credential_in_returns_always_rejected(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string
    password_hash: string [sensitive]

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User [id, password_hash]
"""
        res = check_text(spec)
        assert res.exit_code == 1
        tc003 = [d for d in res.diagnostics if d.rule_id == RuleId.TC_003]
        assert len(tc003) == 1
        assert "credential" in tc003[0].message.lower()

    def test_tc004_credential_in_body_rejected(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string
    password_hash: string [sensitive]

resource Note:
  fields:
    id: uuid
    api_key: string [sensitive]
    owner_id: uuid -> User.id

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint POST /notes:
  resource: Note
  auth: required
  body: [api_key]
  returns: Note [id]
"""
        res = check_text(spec)
        assert res.exit_code == 1
        tc004 = [d for d in res.diagnostics if d.rule_id == RuleId.TC_004]
        assert len(tc004) == 1
        assert "api_key" in tc004[0].message

    def test_tc005_extra_secrets_allowed(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string

secrets:
  DB_URL: env
  JWT_SECRET: env
  STRIPE_KEY: env

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User [id, email]
"""
        res = check_text(spec)
        assert res.exit_code == 0
        assert res.ok


# ---------------------------------------------------------------------------
# API Contract & Human Formatting Tests
# ---------------------------------------------------------------------------

class TestContractAndFormatting:
    def test_check_text_identity_and_timing(self):
        spec = (FIXTURES_DIR / "F2.trust").read_text(encoding="utf-8")
        result = check_text(spec, spec_version=42)
        assert isinstance(result, CheckResult)
        assert result.schema_version == 2
        assert result.spec_version == 42
        assert len(result.spec_hash) == 64
        assert result.command == "check"
        assert result.ms >= 0

    def test_check_file_not_found(self):
        result = check_file("nonexistent.trust")
        assert result.exit_code == 2
        assert not result.ok
        assert result.rules_run == 0
        assert any(e.code == "FILE_NOT_FOUND" for e in result.spec_errors)

    def test_format_human_report(self):
        passing_result = check_file(FIXTURES_DIR / "F2.trust")
        rep_pass = format_human_report(passing_result, filename="F2.trust")
        assert "PASSED" in rep_pass
        assert "Rule Summary" in rep_pass

        failing_result = check_file(FIXTURES_DIR / "F1.trust")
        rep_fail = format_human_report(failing_result, filename="F1.trust")
        assert "FAILED" in rep_fail
        assert "TC-001" in rep_fail
        assert "TC-003" in rep_fail
