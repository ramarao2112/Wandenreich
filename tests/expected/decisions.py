"""Independently specified expected decisions for all fixtures.

These expectations are derived from A-contracts.md, B-compiler-spec.md and
C-fixtures-and-tests.md — NOT from running the implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Tuple


@dataclass(frozen=True)
class ExpectedDiagnostic:
    rule_id: str
    line: int
    col: int
    severity: Literal["error", "warn"] = "error"


@dataclass(frozen=True)
class ExpectedCheck:
    exit_code: Literal[0, 1, 2]
    ok: bool
    rules_run: int  # 0 for specErrors, 5 for parsed specs
    spec_errors_count: int = 0
    diagnostics: List[ExpectedDiagnostic] = field(default_factory=list)
    line_count: int = 0  # expected file line count (with trailing newline)
    endpoints: int = 0


# ---------------------------------------------------------------------------
# Fixture expectations — from C and B, not from running the compiler
# ---------------------------------------------------------------------------

# F1: Missing auth on GET /trips/{id} + sensitive leak on GET /users/{id}
F1 = ExpectedCheck(
    exit_code=1,
    ok=False,
    rules_run=5,
    line_count=30,
    endpoints=3,
    diagnostics=[
        ExpectedDiagnostic(rule_id="TC-001", line=23, col=1),
        ExpectedDiagnostic(rule_id="TC-003", line=30, col=3),
    ],
)

# F2: Clean — all checks pass
F2 = ExpectedCheck(
    exit_code=0,
    ok=True,
    rules_run=5,
    line_count=31,
    endpoints=3,
)

# F3: Clean with ownership waiver — passes with review
F3 = ExpectedCheck(
    exit_code=0,
    ok=True,
    rules_run=5,
    line_count=38,
    endpoints=4,
)

# F4: Syntax error — missing colon at 23:25
F4 = ExpectedCheck(
    exit_code=2,
    ok=False,
    rules_run=0,
    spec_errors_count=1,
    line_count=30,
    endpoints=0,
)
F4_ERROR_POSITION: Tuple[int, int] = (23, 25)

# F5: Mass-assignment — owner_id in body at 20:23
F5 = ExpectedCheck(
    exit_code=1,
    ok=False,
    rules_run=5,
    endpoints=3,
    diagnostics=[
        ExpectedDiagnostic(rule_id="TC-004", line=20, col=23),
    ],
)

# F6: Missing JWT_SECRET — secrets at 13:1
F6 = ExpectedCheck(
    exit_code=1,
    ok=False,
    rules_run=5,
    endpoints=3,
    diagnostics=[
        ExpectedDiagnostic(rule_id="TC-005", line=13, col=1),
    ],
)

# F7: role_only (unsupported) at 26:3
F7 = ExpectedCheck(
    exit_code=1,
    ok=False,
    rules_run=5,
    endpoints=3,
    diagnostics=[
        ExpectedDiagnostic(rule_id="TC-002", line=26, col=3),
    ],
)

# F7b: Wrong authorization field at 26:3
F7B = ExpectedCheck(
    exit_code=1,
    ok=False,
    rules_run=5,
    endpoints=3,
    diagnostics=[
        ExpectedDiagnostic(rule_id="TC-002", line=26, col=3),
    ],
)


# X fixtures expectations (from C-fixtures-and-tests.md)
X01 = ExpectedCheck(
    exit_code=1, ok=False, rules_run=5, endpoints=1,
    diagnostics=[ExpectedDiagnostic(rule_id="TC-002", line=18, col=9)],
)
X02 = ExpectedCheck(
    exit_code=1, ok=False, rules_run=5, endpoints=1,
    diagnostics=[ExpectedDiagnostic(rule_id="TC-002", line=11, col=9)],
)
X03 = ExpectedCheck(
    exit_code=2, ok=False, rules_run=0, spec_errors_count=1, endpoints=0,
)
X04 = ExpectedCheck(
    exit_code=2, ok=False, rules_run=0, spec_errors_count=1, endpoints=0,
)
X05 = ExpectedCheck(
    exit_code=0, ok=True, rules_run=5, endpoints=1,
)
X06 = ExpectedCheck(
    exit_code=1, ok=False, rules_run=5, endpoints=1,
    diagnostics=[ExpectedDiagnostic(rule_id="TC-003", line=13, col=11)],
)
X07 = ExpectedCheck(
    exit_code=1, ok=False, rules_run=5, endpoints=1,
    diagnostics=[ExpectedDiagnostic(rule_id="TC-004", line=20, col=22)],
)
X14 = ExpectedCheck(
    exit_code=1, ok=False, rules_run=5, endpoints=1,
    diagnostics=[ExpectedDiagnostic(rule_id="TC-005", line=6, col=1)],
)
X15 = ExpectedCheck(
    exit_code=1, ok=False, rules_run=5, endpoints=1,
    diagnostics=[ExpectedDiagnostic(rule_id="TC-001", line=11, col=1)],
)

# Lookup by fixture ID
EXPECTED: Dict[str, ExpectedCheck] = {
    "F1": F1,
    "F2": F2,
    "F3": F3,
    "F4": F4,
    "F5": F5,
    "F6": F6,
    "F7": F7,
    "F7b": F7B,
    "X01": X01,
    "X02": X02,
    "X03": X03,
    "X04": X04,
    "X05": X05,
    "X06": X06,
    "X07": X07,
    "X14": X14,
    "X15": X15,
}

# Expected attack results (from C-fixtures-and-tests.md)
# F2: 6 as_expected, 0 review, 0 unexpected
# F3: 8 as_expected, 1 review, 0 unexpected (total 9)


@dataclass(frozen=True)
class ExpectedAttack:
    as_expected: int
    review: int
    unexpected: int
    total: int


EXPECTED_ATTACKS: Dict[str, ExpectedAttack] = {
    "F2": ExpectedAttack(as_expected=6, review=0, unexpected=0, total=6),
    "F3": ExpectedAttack(as_expected=8, review=1, unexpected=0, total=9),
}


# ---------------------------------------------------------------------------
# Additional fixture scenario definitions (X01–X16 from C-fixtures-and-tests.md)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioDescriptor:
    id: str
    case: str
    stage: int  # Primary implementation/enablement stage
    expected_behavior: str
    is_standalone_spec: bool  # True if standalone .trust file, False if descriptor/harness scenario


SCENARIO_DESCRIPTORS: Dict[str, ScenarioDescriptor] = {
    "X01": ScenarioDescriptor(
        id="X01",
        case="Owned POST with auth: public",
        stage=3,
        expected_behavior="TC-002; no generated files",
        is_standalone_spec=True,
    ),
    "X02": ScenarioDescriptor(
        id="X02",
        case="User GET with auth: public or authorize public",
        stage=3,
        expected_behavior="TC-002; never a public profile response",
        is_standalone_spec=True,
    ),
    "X03": ScenarioDescriptor(
        id="X03",
        case="Multiple ownership edges / non-UUID edge / target other than User.id",
        stage=2,
        expected_behavior="reference/unsupported error, no rules",
        is_standalone_spec=True,
    ),
    "X04": ScenarioDescriptor(
        id="X04",
        case="Unknown projected field; duplicate attributes; reserved identifiers",
        stage=2,
        expected_behavior="spec error with exact offending span",
        is_standalone_spec=True,
    ),
    "X05": ScenarioDescriptor(
        id="X05",
        case="Ordinary non-credential sensitive field explicitly exposed",
        stage=4,
        expected_behavior=(
            "Check/build succeed, declaration names field; "
            "corresponding response assertion observes it"
        ),
        is_standalone_spec=True,
    ),
    "X06": ScenarioDescriptor(
        id="X06",
        case="password_hash exposed",
        stage=3,
        expected_behavior="TC-003 despite expose declaration",
        is_standalone_spec=True,
    ),
    "X07": ScenarioDescriptor(
        id="X07",
        case="id or owner in input; PATCH with extra JSON field",
        stage=3,
        expected_behavior="Compiler TC-004 for declared field; runtime 422 for undeclared field",
        is_standalone_spec=True,
    ),
    "X08": ScenarioDescriptor(
        id="X08",
        case="Public owned GET/DELETE",
        stage=5,
        expected_behavior=(
            "Anonymous and second user allowed but review; "
            "owner allowed; isolated row per actor"
        ),
        is_standalone_spec=False,
    ),
    "X09": ScenarioDescriptor(
        id="X09",
        case="Owner-filtered list containing rows from both actors",
        stage=5,
        expected_behavior="Returns caller's rows only",
        is_standalone_spec=False,
    ),
    "X10": ScenarioDescriptor(
        id="X10",
        case="Same content, different specVersion; different content, same specVersion",
        stage=5,
        expected_behavior="Hash-driven identity works; mismatched evidence never joins",
        is_standalone_spec=False,
    ),
    "X11": ScenarioDescriptor(
        id="X11",
        case="No eligible item endpoint",
        stage=5,
        expected_behavior="Empty coverage shown explicitly; no 'all secure' message",
        is_standalone_spec=False,
    ),
    "X12": ScenarioDescriptor(
        id="X12",
        case="Optional returns omitted on PUT",
        stage=4,
        expected_behavior="200 with {}, still verifies persistent mutation",
        is_standalone_spec=False,
    ),
    "X13": ScenarioDescriptor(
        id="X13",
        case="Valid narrow projection plus another route returning more fields",
        stage=4,
        expected_behavior="No schema collision or projection leak",
        is_standalone_spec=False,
    ),
    "X14": ScenarioDescriptor(
        id="X14",
        case="Missing secrets block and multiple missing secrets",
        stage=3,
        expected_behavior="One coherent patch; no duplicated blocks",
        is_standalone_spec=True,
    ),
    "X15": ScenarioDescriptor(
        id="X15",
        case="CRLF and non-ASCII comment before diagnostic token",
        stage=2,
        expected_behavior="Normalized hash and correct editor span",
        is_standalone_spec=True,
    ),
    "X16": ScenarioDescriptor(
        id="X16",
        case="Invalid/expired/wrong-signature/wrong-audience JWT and nonexistent sub",
        stage=6,
        expected_behavior="401; no traceback or token echo",
        is_standalone_spec=False,
    ),
}
