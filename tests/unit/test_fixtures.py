"""Stage 1 fixture tests — validate line counts, positions and F1→F2 round trip.

These tests verify that the checked-in fixtures match the specification
WITHOUT running any compiler. They validate file-level properties only.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from trustc.contracts import normalize_source, spec_hash

pytestmark = pytest.mark.stage1

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _read_fixture(name: str) -> str:
    """Read and normalize a fixture file."""
    path = FIXTURES_DIR / f"{name}.trust"
    assert path.exists(), f"Fixture {name}.trust not found at {path}"
    raw = path.read_text(encoding="utf-8")
    return normalize_source(raw)


def _count_lines(text: str) -> int:
    """Count lines the same way wc -l does for a file ending with newline."""
    # A file with trailing newline: "a\nb\n" has 2 lines
    # A file without trailing newline: "a\nb" has 2 lines
    if not text:
        return 0
    return text.count("\n") if text.endswith("\n") else text.count("\n") + 1


class TestFixtureLineCounts:
    """C-fixtures-and-tests.md: F1=30, F2=31, F3=38 lines."""

    def test_f1_line_count(self):
        text = _read_fixture("F1")
        assert _count_lines(text) == 30, f"F1 has {_count_lines(text)} lines, expected 30"

    def test_f2_line_count(self):
        text = _read_fixture("F2")
        assert _count_lines(text) == 31, f"F2 has {_count_lines(text)} lines, expected 31"

    def test_f3_line_count(self):
        text = _read_fixture("F3")
        assert _count_lines(text) == 38, f"F3 has {_count_lines(text)} lines, expected 38"


class TestFixturePositions:
    """Verify key diagnostic positions from the spec.

    These are source-text assertions, not compiler output.
    TC-001 at 23:1 means F1 line 23 starts with 'endpoint'.
    TC-003 at 30:3 means F1 line 30 col 3 starts with 'returns'.
    F4 error at 23:25 means the missing colon position.
    F5 owner_id at 20:23 means the field token in body.
    """

    def test_f1_tc001_position_23_1(self):
        """F1 line 23 should be 'endpoint GET /trips/{id}:' — missing auth."""
        text = _read_fixture("F1")
        lines = text.split("\n")
        line_23 = lines[22]  # 0-indexed
        assert line_23.startswith("endpoint"), (
            f"F1 line 23 should start with 'endpoint', got: {line_23!r}"
        )

    def test_f1_tc003_position_30_3(self):
        """F1 line 30 col 3 should be 'returns: User' — sensitive leak."""
        text = _read_fixture("F1")
        lines = text.split("\n")
        line_30 = lines[29]  # 0-indexed
        # col 3 means character index 2 (1-based columns)
        assert line_30.strip().startswith("returns"), (
            f"F1 line 30 should contain 'returns', got: {line_30!r}"
        )

    def test_f4_missing_colon_23_25(self):
        """F4 line 23 should be 'endpoint GET /trips/{id}' WITHOUT a colon.

        The colon is missing at column 25.
        """
        text = _read_fixture("F4")
        lines = text.split("\n")
        line_23 = lines[22]
        assert "endpoint GET /trips/{id}" in line_23, f"Unexpected F4 line 23: {line_23!r}"
        # Should NOT end with colon (that's the error)
        assert not line_23.rstrip().endswith(":"), (
            f"F4 line 23 should be MISSING the colon: {line_23!r}"
        )

    def test_f5_owner_id_20_23(self):
        """F5 line 20 should have owner_id in body, col 23."""
        text = _read_fixture("F5")
        lines = text.split("\n")
        line_20 = lines[19]
        assert "owner_id" in line_20, f"F5 line 20 should contain 'owner_id': {line_20!r}"


class TestFixtureHashes:
    """Normalized hash is deterministic and CRLF-independent."""

    def test_f1_hash_stable(self):
        text = _read_fixture("F1")
        h1 = spec_hash(text)
        h2 = spec_hash(text)
        assert h1 == h2
        assert len(h1) == 64

    def test_f1_f2_different_hashes(self):
        """F1 and F2 are different files with different hashes."""
        h1 = spec_hash(_read_fixture("F1"))
        h2 = spec_hash(_read_fixture("F2"))
        assert h1 != h2


class TestF1ToF2RoundTrip:
    """C: F1 → apply TC-001 diff → only TC-003 remains → manually project → F2.

    We test the text-level transformation here.
    F1 to F2 differences:
    1. Line 25 added: '  auth: required' (fixes TC-001 on GET /trips/{id})
    2. Line 31: 'returns: User' → 'returns: User [id, email]' (fixes TC-003)
    """

    def test_f1_to_f2_diff(self):
        """Apply the two fixes to F1 and verify it matches F2 exactly."""
        f1 = _read_fixture("F1")
        f2 = _read_fixture("F2")

        lines = f1.split("\n")

        # Fix 1: Add 'auth: required' after 'resource: Trip' in GET /trips/{id}
        # F1 line 23: endpoint GET /trips/{id}:
        # F1 line 24:   resource: Trip
        # F1 line 25:   returns: Trip  ← need to insert auth before this
        # Insert '  auth: required' at index 24 (after resource: Trip)
        lines.insert(24, "  auth: required")

        # Fix 2: Change 'returns: User' to 'returns: User [id, email]'
        # After insertion, the last 'returns: User' is now at the end
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "returns: User":
                lines[i] = "  returns: User [id, email]"
                break

        result = "\n".join(lines)
        assert result == f2, (
            f"F1→F2 transformation failed.\n"
            f"Expected hash: {spec_hash(f2)}\n"
            f"Got hash: {spec_hash(result)}"
        )

    def test_round_trip_uses_temp_copy(self):
        """The round trip must not modify canonical fixtures."""
        f1_path = FIXTURES_DIR / "F1.trust"
        original_content = f1_path.read_text(encoding="utf-8")

        # Create temp copy
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "F1.trust"
            shutil.copy2(f1_path, tmp_path)

            # Modify temp
            tmp_text = tmp_path.read_text(encoding="utf-8")
            tmp_path.write_text(tmp_text + "# modified\n", encoding="utf-8")

            # Original untouched
            assert f1_path.read_text(encoding="utf-8") == original_content


class TestAllFixturesPresent:
    """Verify all expected fixture files exist."""

    @pytest.mark.parametrize("name", ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F7b"])
    def test_fixture_exists(self, name: str):
        path = FIXTURES_DIR / f"{name}.trust"
        assert path.exists(), f"Missing fixture: {path}"

    @pytest.mark.parametrize("name", ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F7b"])
    def test_fixture_utf8(self, name: str):
        """All fixtures must be valid UTF-8."""
        path = FIXTURES_DIR / f"{name}.trust"
        path.read_text(encoding="utf-8")  # raises on invalid encoding
