# Fixture Provenance Note

**Date:** 7 October 2026  
**Status:** Verified Stage 1 Artifact  
**Repository:** TrustC  

---

## 1. Overview and Source

The reference fixtures for TrustC are divided into two categories:
1. **Canonical Fixtures (`F1.trust` through `F7b.trust`)**:
   - Reconstructed directly from the Stage Pack v2 specification (`A-contracts.md`, `B-compiler-spec.md`, `C-fixtures-and-tests.md`).
   - Placed under `tests/fixtures/` and preserved unmodified.
2. **Extended Boundary Fixtures (`X01.trust` through `X15.trust`)**:
   - Authored independently in Stage 1 directly from the requirements in `C-fixtures-and-tests.md` (lines 31–50) to test negative edge cases, multiple ownership edges, unallowed exposures, and input malformations.

---

## 2. Canonical Fixture Integrity & Invariants

| Fixture | Line Count | SHA-256 (Normalized LF) | Purpose & Essential Locations |
|---|---|---|---|
| `F1.trust` | 30 | `231ad889504c86720d588523b145a9ca223402fb6f3b01a1c97a29ec60a927a7` | Baseline failing spec. TC-001 (missing auth) at 23:1; TC-003 (sensitive leak) at 30:3. |
| `F2.trust` | 31 | `a65a94747eb48e583c267cbf7e23118cfeb5c3e44501a5e12ec68ef33ce105d1` | Clean hardened spec. Three endpoints; User GET projected as `[id, email]` (self-only). |
| `F3.trust` | 38 | `e5bc624ee437ee9bf9186676da3dc7381ff2ba384666cfb71ecb1574a78cb420` | Ownership waiver spec. Four endpoints; `authorize: public` at line 37, col 3. |
| `F4.trust` | 30 | `38b4c2b9f9361a8ef1f2a4ae49fe1c7f90f368f30737a0980c6cbf1dfdcaeb6e` | Syntax failure. Missing colon at line 23, col 25 (`endpoint GET /trips/{id}`). Exits 2. |
| `F5.trust` | 31 | `3dc3a032ba8e55e090dfc7fb081395f1fa023e10fa658e8b65da94082269d7b4` | Mass-assignment flaw (TC-004). Server-controlled `owner_id` in body at line 20, col 23. |
| `F6.trust` | 30 | `f04d7aa42d4a5b481f215033fcb749d0124f5dfcf442a3ebaf1cc85347209700` | Secret scoping flaw (TC-005). Undeclared `JWT_SECRET`; secrets block at line 13, col 1. |
| `F7.trust` | 32 | `9d5da251ee2bc3a44d039ef796bf423da053e164ae1fcb9e38f9b90c1dd69f0e` | Unsupported role policy (TC-002). `role_only` declaration at line 26, col 3. |
| `F7b.trust` | 32 | `b5358055653db3bb06019567c3319047913364c7bf915b802613b5a195b0c95d` | Wrong field authorization (TC-002). Relational mismatch at line 26, col 3. |

---

## 3. Transformation and Round-Trip Guarantees

As specified in `C-fixtures-and-tests.md`:
1. `F1.trust` represents an initial, unhardened spec.
2. Applying the proposed `TC-001` fix diff inserts `auth: required` after line 24.
3. Manually projecting safe fields on User (`returns: User [id, email]`) resolves `TC-003`.
4. The resulting text is byte-identical to `F2.trust`.
5. Automated tests (`tests/unit/test_fixtures.py::TestF1ToF2RoundTrip`) verify this non-destructively in an isolated temporary directory, ensuring canonical fixtures are never modified on disk.

---

## 4. Extended (X) Fixtures Provenance

The X fixtures implement targeted edge cases from Section C:
- `X01.trust`: Owned POST with `auth: public` (violates owner assignment).
- `X02.trust`: Identity User route with `auth: public` (violates self-only protection).
- `X03.trust`: Multiple ownership relations (unsupported relational topology).
- `X04.trust`: Unknown projected field in return statement.
- `X05.trust`: Explicit sensitive exposure using `expose: [ssn]`.
- `X06.trust`: Attempted credential exposure (`password_hash`), which must be refused despite `expose`.
- `X07.trust`: Input mass-assignment attempt (`owner_id` in POST body).
- `X14.trust`: Completely missing `secrets:` declaration block.
- `X15.trust`: Unicode comments and CRLF line endings preceding diagnostic tokens to ensure column offsets are Unicode code-point accurate.
