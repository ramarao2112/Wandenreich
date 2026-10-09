# TrustC Source Inventory & Assets Note

**Date:** 7 October 2026  
**Document Status:** Complete for Stage 1  

---

## 1. Source Inventory

The workspace `/Users/polasavishal1124/Desktop/TrustC` contains the following asset sets:

### 1.1 Specification Baseline (Stage Pack v2)
Located in `docs/handoff-v2/` and `TrustC-Stage-Pack-v2/`:
- `00-START-HERE.md`: Top-level roadmap and architectural overview.
- `01-REVIEW-AND-DECISIONS.md`: Strategic architectural decisions and v1 vs v2 repair log.
- `A-contracts.md`: Wire contracts, data structures, and HTTP API schemas.
- `B-compiler-spec.md`: Grammar, AST, IR, rule triggers (TC-001 through TC-005), code generation rules, and claims.
- `C-fixtures-and-tests.md`: Canonical fixture definitions, expected results, and test levels.
- `D-ui-design-addendum.md`: Workbench UI tokens, states, and accessibility standards.
- `stage-1-setup-and-fixtures.md` through `stage-8-demo-proofing.md`: Step-by-step stage execution guides.
- `optional-9-ai-front-door.md`: Optional AI assistant specifications.
- `PACK-MANIFEST.json`: Cryptographic manifest and integrity metadata.

### 1.2 Implemented Software (`src/trustc/`)
- `__init__.py`: Package root, version `0.1.0`.
- `cli.py`: Minimal CLI entry point with `--help`, `--version`, and subcommand stubs.
- `contracts.py`: Executable Pydantic v2 schemas for all Section A contracts.
- `schemas/v2/*.json`: Exported JSON Schemas for `CheckResult`, `BuildSuccess`, `AttackCompleted`, `RunFailure`, `RunEvent`, `ServerMeta`.

### 1.3 Test Suite & Fixtures (`tests/`)
- `tests/fixtures/`: Canonical fixtures `F1.trust` to `F7b.trust`, plus boundary fixtures `X01.trust` to `X15.trust`.
- `tests/expected/decisions.py`: Pre-computed ground truth expectations for all fixtures.
- `tests/contract/`: Pydantic contract validation tests (`test_contracts.py`) and schema/TypeScript drift tests (`test_drift.py`).
- `tests/unit/`: Fixture integrity and line-count tests (`test_fixtures.py`).

### 1.4 UI Wire Contracts (`ui/`)
- `ui/src/api/types.ts`: Mirror TypeScript types aligned with Schema Version 2.
- `ui/package.json`: Locked frontend dependencies.

---

## 2. Missing Historical Assets

Per the Stage Pack v2 specification:
1. **Master Build Document**: Unavailable/superseded. The Stage Pack v2 (`A-contracts.md`, `B-compiler-spec.md`, `C-fixtures-and-tests.md`) is self-contained and serves as the official specification authority.
2. **Mockup ZIP Archive**: Unavailable. UI layout and tokens are fully defined in `D-ui-design-addendum.md` and `stage-7-ui.md`.

**Note:** Missing historical assets do not block implementation or verification of the v2 system.
