# Architectural Decision Record 01: Stage 1 Architecture & Contracts

**Status:** Accepted  
**Date:** 7 October 2026  
**Context:** TrustC Stage 1 Setup & Contracts  

---

## 1. Context and Problem

TrustC requires rigorous machine contracts that represent compiler diagnostics, evidence records, and execution states consistently across the Python CLI, the local daemon, and the web frontend. Earlier drafts (v1) allowed ambiguous exit codes, optional inconsistent fields, and unvalidated null values.

## 2. Decisions

1. **Select Stage Pack v2 as Implementation Baseline**:
   - The eight-stage v2 pack fixes contract ambiguities, adds failure-path verification, and enforces explicit rule naming:
     - `TC-001`: `AUTH-REQUIRED`
     - `TC-002`: `OWNERSHIP-CHECK`
     - `TC-003`: `SENSITIVE-LEAK`
     - `TC-004`: `MASS-ASSIGNMENT`
     - `TC-005`: `SECRET-SCOPE`
2. **Pydantic v2 with CamelCase Aliases**:
   - Contract models are implemented in Python using Pydantic v2.
   - Serialization to JSON uses `by_alias=True` so wire payloads conform to camelCase standards (`specHash`, `schemaVersion`, `exitCode`, `rulesRun`).
3. **Dedicated Location for Schema Version 2**:
   - Exported JSON Schemas are stored in `src/trustc/schemas/v2/`.
   - A drift test (`tests/contract/test_drift.py`) asserts that checked-in schemas match the live Pydantic models.
4. **Mirror TypeScript Wire Types**:
   - `ui/src/api/types.ts` is maintained to align with Schema Version 2. Drift tests verify that rule IDs, exit codes, and model fields match across languages.
5. **Discriminator & State Consistency Enforced in Contracts**:
   - `CheckResult` enforces that successfully parsed specifications must evaluate all 5 rules (`rulesRun=5`), while syntax errors (`specErrors`) must have `rulesRun=0` and no diagnostics.
   - `AttackCompleted` enforces that completed attacks cannot contain `null` got or outcome fields, and the sum of outcomes must equal `total` and `len(steps)`.
   - `RunFailure` enforces that `exitCode` strictly maps to `status` (`refused`=1, `invalid_spec`=2, `error`=3, `timed_out`=124, `cancelled`=130).
6. **Non-Destructive Fixture Verification**:
   - Canonical fixtures (`F1.trust` to `F7b.trust`) are immutable on disk. Tests that verify transformations (such as the F1→F2 patch) operate on temporary copies.

## 3. Consequences

- Full interoperability between CLI and frontend.
- Zero silent contract drift between Python and TypeScript.
- Strong guarantees that invalid compiler states are caught at the contract level before hitting the UI.
