# Stage 1 Progress Report

**Date:** 7 October 2026  
**Stage:** 1 — Setup, Contracts, and Independent Fixtures  
**Status:** Completed & Gates Passed  

---

## 1. Environment & Installed Versions

- **OS:** macOS Darwin (arm64)
- **Python:** 3.9.6
- **Pip:** 26.0.1
- **Key Dependencies Installed:**
  - `pydantic`: 2.13.5
  - `pytest`: 8.4.2
  - `ruff`: 0.16.10
  - `mypy`: 1.19.1
  - `email-validator`: 2.3.0
  - `httpx`: 0.28.1
- **Lockfile:** `requirements.lock` generated and verified.

---

## 2. Actual Commands and Results

| Command | Exit Code | Outcome |
|---|---|---|
| `python scripts/check-stage.py 1` | `0` | Ruff, Mypy, and Pytest all passed (67 tests, 0 failures). |
| `pytest -v` | `0` | All 67 unit, contract, and drift tests passed. |
| `ruff check src/ tests/` | `0` | 0 lint errors. |
| `mypy src/ tests/` | `0` | Success: no issues found in 10 source files. |
| `trustc --help` | `0` | Help message displayed correctly. |
| `trustc --version` | `0` | Prints `trustc 0.1.0`. |
| `trustc check test.trust` | `3` | Graceful refusal: `trustc check: not yet implemented (Stage 2+)`. |
| `python scripts/check-stage.py 2` | `1` | Refused: `Stage 2 is not yet implemented.` |

---

## 3. Decisions Selected & Contract Guarantees

- **Stage Pack v2 Selected**: Repaired wire schemas, unambiguous exit codes, and failure-path tests.
- **Why v1 contracts cannot be mixed in**:
  - v1 allowed contradictory outcomes (e.g. `ok=true` with non-zero exit codes, undefined diagnostic structures).
  - v1 omitted required security metadata in evidence records.
  - v1 lacked strict discriminator unions for CLI and daemon outputs.
- **Independent Golden Decisions**:
  - Expected results in `tests/expected/decisions.py` were derived directly from the written specifications (`A-contracts.md`, `B-compiler-spec.md`, `C-fixtures-and-tests.md`), never by running compiler code.

---

## 4. Source & Fixture Inventory

- **Canonical Fixtures:** `F1.trust` to `F7b.trust` (8 files), verified on disk for line counts, coordinate positions, and hash stability.
- **Boundary Fixtures:** `X01.trust` to `X15.trust` (9 files authored), covering unallowed public auth, multiple ownership edges, and missing secrets.
- **Wire Contracts:**
  - Pydantic models: `src/trustc/contracts.py`
  - JSON Schema (v2): `src/trustc/schemas/v2/*.json`
  - TypeScript types: `ui/src/api/types.ts`
  - Drift test: `tests/contract/test_drift.py`

---

## 5. Remaining Work & Stage 2 Prompt

Stage 1 is complete and all gates pass.

**Next Stage Prompt:**
```text
Implement Stage 2 only from docs/handoff-v2/stage-2-parse.md; verify Stage 1 first and preserve its contracts.
```
