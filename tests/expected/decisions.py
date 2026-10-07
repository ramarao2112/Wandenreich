"""Independently specified expected decisions for all fixtures.

These expectations are derived from A-contracts.md, B-compiler-spec.md and
C-fixtures-and-tests.md — NOT from running the implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple


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
