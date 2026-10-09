"""Stage 1 contract tests — round-trip serialization and invalid-union rejection."""

import uuid

import pytest
from pydantic import ValidationError

from trustc.contracts import (
    AttackCheck,
    AttackCompleted,
    AttackCoverage,
    AttackStep,
    BuildEvidence,
    BuildSuccess,
    CheckResult,
    Diagnostic,
    DiffFix,
    ForcedLine,
    GeneratedFile,
    PromptFix,
    RuleResult,
    RunFailure,
    Span,
    normalize_source,
    spec_hash,
)

pytestmark = pytest.mark.stage1


class TestSpan:
    def test_round_trip(self):
        s = Span(line=1, col=1, endLine=1, endCol=10)
        d = s.model_dump(by_alias=True)
        assert d == {"line": 1, "col": 1, "endLine": 1, "endCol": 10}
        assert Span.model_validate(d) == s

    def test_rejects_zero_line(self):
        with pytest.raises(ValidationError):
            Span(line=0, col=1, endLine=1, endCol=1)


class TestCheckResult:
    def _make_rules(self, statuses):
        names = ["AUTH-REQUIRED", "OWNERSHIP-CHECK", "SENSITIVE-LEAK",
                 "MASS-ASSIGNMENT", "SECRET-SCOPE"]
        ids = ["TC-001", "TC-002", "TC-003", "TC-004", "TC-005"]
        return [
            RuleResult(
                ruleId=ids[i], ruleName=names[i], status=statuses[i],
                checked=1, violations=0 if statuses[i] == "passed" else 1,
                summary=f"Rule {ids[i]}"
            )
            for i in range(5)
        ]

    def test_valid_passing_check(self):
        rules = self._make_rules(["passed"] * 5)
        cr = CheckResult(
            schemaVersion=2, specVersion=0, specHash="abc123",
            command="check test.trust", ms=42,
            ok=True, exitCode=0,
            rules=rules, rulesRun=5, endpoints=3,
        )
        assert cr.ok is True
        assert cr.exit_code == 0
        d = cr.model_dump(by_alias=True)
        assert d["schemaVersion"] == 2
        assert d["kind"] == "check"

    def test_valid_failing_check(self):
        rules = self._make_rules(["failed", "passed", "passed", "passed", "passed"])
        diags = [
            Diagnostic(
                ruleId="TC-001", ruleName="AUTH-REQUIRED", severity="error",
                span=Span(line=23, col=1, endLine=23, endCol=8),
                location="endpoint GET /trips/{id}", message="Missing auth",
                why="No auth declaration", fix=DiffFix(
                    baseSpecHash="abc", diff="+ auth: required", label="Add auth"
                ),
            )
        ]
        cr = CheckResult(
            schemaVersion=2, specVersion=0, specHash="abc",
            command="check test.trust", ms=10,
            ok=False, exitCode=1,
            specErrors=[], diagnostics=diags,
            rules=rules, rulesRun=5, endpoints=3,
        )
        assert cr.ok is False
        assert cr.exit_code == 1

    def test_spec_error_no_rules(self):
        from trustc.contracts import SpecError, SpecErrorKind
        cr = CheckResult(
            schemaVersion=2, specVersion=0, specHash="abc",
            command="check test.trust", ms=5,
            ok=False, exitCode=2,
            specErrors=[SpecError(
                kind=SpecErrorKind.SYNTAX, code="E001",
                message="Missing colon",
                span=Span(line=23, col=25, endLine=23, endCol=25),
                snippet="endpoint GET /trips/{id}"
            )],
            diagnostics=[], rules=[], rulesRun=0, endpoints=0,
        )
        assert cr.exit_code == 2

    def test_rejects_ok_true_with_nonzero_exit(self):
        with pytest.raises(ValidationError, match="ok=true requires exitCode=0"):
            CheckResult(
                schemaVersion=2, specVersion=0, specHash="abc",
                command="check", ms=0,
                ok=True, exitCode=1,
                rules=[], rulesRun=5, endpoints=0,
            )

    def test_rejects_spec_errors_with_diagnostics(self):
        from trustc.contracts import SpecError, SpecErrorKind
        with pytest.raises(ValidationError, match="specErrors present"):
            CheckResult(
                schemaVersion=2, specVersion=0, specHash="abc",
                command="check", ms=0,
                ok=False, exitCode=2,
                specErrors=[SpecError(
                    kind=SpecErrorKind.SYNTAX, code="E001", message="err",
                    span=Span(line=1, col=1, endLine=1, endCol=1), snippet="x"
                )],
                diagnostics=[
                    Diagnostic(
                        ruleId="TC-001", ruleName="AUTH-REQUIRED", severity="error",
                        span=Span(line=1, col=1, endLine=1, endCol=1),
                        location="x", message="y", why="z",
                        fix=PromptFix(text="fix"),
                    )
                ],
                rules=[], rulesRun=0, endpoints=0,
            )

    def test_round_trip_json(self):
        rules = self._make_rules(["passed"] * 5)
        cr = CheckResult(
            schemaVersion=2, specVersion=0, specHash="abc",
            command="check test.trust", ms=10,
            ok=True, exitCode=0,
            rules=rules, rulesRun=5, endpoints=3,
        )
        json_str = cr.model_dump_json(by_alias=True)
        cr2 = CheckResult.model_validate_json(json_str)
        assert cr2.ok == cr.ok
        assert cr2.exit_code == cr.exit_code


class TestRunFailure:
    def test_valid_refused(self):
        rf = RunFailure(
            schemaVersion=2, specVersion=0, specHash="abc",
            command="build test.trust", ms=5,
            kind="build", status="refused", exitCode=1,
        )
        assert rf.exit_code == 1

    def test_rejects_invalid_status_code(self):
        with pytest.raises(ValidationError, match="status=refused requires exitCode"):
            RunFailure(
                schemaVersion=2, specVersion=0, specHash="abc",
                command="build", ms=0,
                kind="build", status="refused", exitCode=2,
            )

    def test_valid_cancelled(self):
        rf = RunFailure(
            schemaVersion=2, specVersion=0, specHash="abc",
            command="attack test.trust", ms=100,
            kind="attack", status="cancelled", exitCode=130,
        )
        assert rf.status == "cancelled"


class TestBuildSuccess:
    def test_valid_build_success(self):
        evidence = BuildEvidence(
            schemaVersion=2,
            buildId="b123",
            specHash="abc456",
            specVersion=0,
            compilerVersion="0.1.0",
            templateVersion="0.1.0",
            rules=[],
            endpointPolicies=[],
            structuralRestrictions=[],
            declarations=[],
            limitations=[],
        )
        file = GeneratedFile(
            path="src/main.py",
            content="# generated",
            forced=[
                ForcedLine(
                    line=1,
                    specSpan=Span(line=1, col=1, endLine=1, endCol=10),
                    kind="route",
                )
            ],
        )
        bs = BuildSuccess(
            schemaVersion=2,
            specVersion=0,
            specHash="abc456",
            command="build test.trust",
            ms=50,
            buildId="b123",
            files=[file],
            evidence=evidence,
        )
        assert bs.kind == "build"
        assert bs.status == "completed"
        assert bs.exit_code == 0
        dumped = bs.model_dump(by_alias=True)
        assert dumped["schemaVersion"] == 2
        assert dumped["buildId"] == "b123"
        assert dumped["files"][0]["path"] == "src/main.py"
        # Round trip JSON
        json_str = bs.model_dump_json(by_alias=True)
        bs2 = BuildSuccess.model_validate_json(json_str)
        assert bs2.build_id == bs.build_id

    def test_rejects_nonzero_exit_code(self):
        evidence = BuildEvidence(
            schemaVersion=2,
            buildId="b123",
            specHash="abc456",
            specVersion=0,
            compilerVersion="0.1.0",
            templateVersion="0.1.0",
        )
        with pytest.raises(ValidationError):
            BuildSuccess(
                schemaVersion=2,
                specVersion=0,
                specHash="abc456",
                command="build",
                ms=0,
                buildId="b123",
                exitCode=1,  # type: ignore[arg-type]
                evidence=evidence,
            )


class TestAttackCompleted:
    def test_valid_attack_completed(self):
        step_id = str(uuid.uuid4())
        step = AttackStep(
            stepId=step_id,
            endpoint="GET /trips/{id}",
            actor="anonymous",
            method="GET",
            path="/trips/123",
            expect=401,
            got=401,
            outcome="as_expected",
            checks=[
                AttackCheck(
                    name="status_code",
                    expected="401",
                    actual="401",
                    passed=True,
                )
            ],
        )
        ac = AttackCompleted(
            schemaVersion=2,
            specVersion=0,
            specHash="abc",
            command="attack test.trust",
            ms=100,
            buildId="b1",
            artifactHash="ah1",
            steps=[step],
            asExpected=1,
            review=0,
            unexpected=0,
            total=1,
            coverage=AttackCoverage(testedEndpoints=["GET /trips/{id}"]),
        )
        assert ac.kind == "attack"
        assert ac.status == "completed"
        assert ac.exit_code == 0
        dumped = ac.model_dump(by_alias=True)
        assert dumped["asExpected"] == 1
        assert dumped["total"] == 1
        # Round trip JSON
        json_str = ac.model_dump_json(by_alias=True)
        ac2 = AttackCompleted.model_validate_json(json_str)
        assert ac2.as_expected == 1
        assert len(ac2.steps) == 1

    def test_rejects_mismatched_totals(self):
        with pytest.raises(ValidationError, match="total"):
            AttackCompleted(
                schemaVersion=2, specVersion=0, specHash="abc",
                command="attack test.trust", ms=100,
                buildId="b1", artifactHash="ah1",
                steps=[], asExpected=1, review=0, unexpected=0, total=2,
                coverage=AttackCoverage(),
            )

    def test_rejects_null_outcome_in_completed(self):
        step = AttackStep(
            stepId=str(uuid.uuid4()), endpoint="GET /trips/{id}", actor="anonymous",
            method="GET", path="/trips/abc", expect=401,
            got=None, outcome=None,
        )
        with pytest.raises(ValidationError, match="null got"):
            AttackCompleted(
                schemaVersion=2, specVersion=0, specHash="abc",
                command="attack test.trust", ms=100,
                buildId="b1", artifactHash="ah1",
                steps=[step], asExpected=0, review=0, unexpected=0, total=1,
                coverage=AttackCoverage(),
            )

    def test_rejects_non_uuid_step_id(self):
        with pytest.raises(ValidationError, match="valid canonical UUID string"):
            AttackStep(
                stepId="step-12345",
                endpoint="GET /trips/{id}",
                actor="anonymous",
                method="GET",
                path="/trips/123",
                expect=401,
                got=401,
                outcome="as_expected",
            )


class TestNormalization:
    def test_crlf(self):
        assert normalize_source("a\r\nb\rc\n") == "a\nb\nc\n"

    def test_hash_deterministic(self):
        h1 = spec_hash("hello\n")
        h2 = spec_hash("hello\n")
        assert h1 == h2
        assert len(h1) == 64

    def test_crlf_normalizes_same_hash(self):
        h1 = spec_hash(normalize_source("a\r\nb\n"))
        h2 = spec_hash(normalize_source("a\nb\n"))
        assert h1 == h2
