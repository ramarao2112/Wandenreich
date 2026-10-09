"""Stage 3 unit tests — fix diff generation, exact context matching, and atomic application."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from trustc.contracts import Diagnostic, DiffFix, RuleId
from trustc.fixes import (
    apply_fix_to_file,
    apply_patch_text,
    generate_unified_diff,
)
from trustc.verifier import check_file

pytestmark = pytest.mark.stage3

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestUnifiedDiffs:
    def test_diff_format(self):
        orig = "line 1\nline 2\nline 3\n"
        mod = "line 1\nline 2 edited\nline 3\n"
        diff = generate_unified_diff(orig, mod, filename="test.trust")
        assert "--- a/test.trust" in diff
        assert "+++ b/test.trust" in diff
        assert "@@" in diff
        assert "-line 2" in diff
        assert "+line 2 edited" in diff

    def test_git_apply_compatibility(self):
        """Independent patch compatibility check with git apply --check."""
        r = check_file(FIXTURES_DIR / "F1.trust")
        tc001 = [d for d in r.diagnostics if d.rule_id == RuleId.TC_001][0]
        assert isinstance(tc001.fix, DiffFix)
        diff_text = tc001.fix.diff

        with tempfile.TemporaryDirectory() as td:
            repo_dir = Path(td)
            subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
            target = repo_dir / "spec.trust"
            target.write_bytes((FIXTURES_DIR / "F1.trust").read_bytes())
            subprocess.run(
                ["git", "add", "spec.trust"], cwd=repo_dir, check=True, capture_output=True
            )

            patch_file = repo_dir / "patch.diff"
            patch_file.write_text(diff_text, encoding="utf-8", newline="\n")

            proc = subprocess.run(
                ["git", "apply", "--check", "patch.diff"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )
            assert proc.returncode == 0, f"git apply failed: {proc.stderr}"


class TestPatchApplication:
    def test_exact_context_success(self):
        source = "alpha\nbeta\ngamma\n"
        patch = (
            "--- a/spec.trust\n"
            "+++ b/spec.trust\n"
            "@@ -1,3 +1,4 @@\n"
            " alpha\n"
            "+delta\n"
            " beta\n"
            " gamma\n"
        )
        patched = apply_patch_text(source, patch)
        assert patched == "alpha\ndelta\nbeta\ngamma\n"

    def test_context_mismatch_rejection(self):
        source = "alpha\nDIFFERENT\ngamma\n"
        patch = (
            "--- a/spec.trust\n"
            "+++ b/spec.trust\n"
            "@@ -1,3 +1,4 @@\n"
            " alpha\n"
            "+delta\n"
            " beta\n"
            " gamma\n"
        )
        with pytest.raises(ValueError, match="Patch context mismatch"):
            apply_patch_text(source, patch)


class TestApplyFixToFile:
    def test_hash_mismatch_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_file = Path(td) / "F1.trust"
            shutil.copy(FIXTURES_DIR / "F1.trust", tmp_file)

            # Create a fake diagnostic with stale baseSpecHash
            fake_diag = Diagnostic(
                rule_id=RuleId.TC_001,
                rule_name="AUTH-REQUIRED",
                severity="error",
                span=dict(line=23, col=1, endLine=23, endCol=8),
                location="endpoint",
                message="Missing auth",
                why="No auth",
                fix=DiffFix(
                    base_spec_hash="stale_deadbeef_hash",
                    diff="--- a/spec.trust\n+++ b/spec.trust\n",
                    label="Add auth",
                ),
            )
            rc, msg, _ = apply_fix_to_file(tmp_file, [fake_diag])
            assert rc == 1
            assert "Spec hash mismatch" in msg

    def test_dry_run_leaves_file_unmodified(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_file = Path(td) / "F1.trust"
            shutil.copy(FIXTURES_DIR / "F1.trust", tmp_file)
            orig_bytes = tmp_file.read_bytes()

            r = check_file(tmp_file)
            rc, patch, _ = apply_fix_to_file(
                tmp_file, r.diagnostics, rule_id="TC-001", dry_run=True
            )
            assert rc == 0
            assert "auth: required" in patch
            assert tmp_file.read_bytes() == orig_bytes

    def test_ambiguous_multiple_fixes_requires_line_or_all(self):
        spec = """
resource User:
  fields:
    id: uuid
    email: string

resource Trip:
  fields:
    id: uuid
    destination: string
    owner_id: uuid -> User.id

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint GET /trips:
  resource: Trip
  returns: Trip [id, destination]

endpoint GET /trips/{id}:
  resource: Trip
  returns: Trip [id, destination]
"""
        with tempfile.TemporaryDirectory() as td:
            tmp_file = Path(td) / "multi.trust"
            tmp_file.write_text(spec.strip() + "\n", encoding="utf-8")

            r = check_file(tmp_file)
            tc001_diags = [d for d in r.diagnostics if d.rule_id == RuleId.TC_001]
            assert len(tc001_diags) == 2

            # Without line or all -> exit 2
            rc, msg, _ = apply_fix_to_file(tmp_file, r.diagnostics, rule_id="TC-001")
            assert rc == 2
            assert "Specify --line" in msg

            # With line -> succeeds
            rc, msg, _ = apply_fix_to_file(
                tmp_file, r.diagnostics, rule_id="TC-001", line=tc001_diags[0].span.line
            )
            assert rc == 0


class TestRequiredFixedFlow:
    def test_f1_to_f2_round_trip(self):
        """F1 -> apply TC-001 fix -> only TC-003 at line 31 ->
        project User [id, email] -> exactly F2."""
        with tempfile.TemporaryDirectory() as td:
            tmp_f1 = Path(td) / "F1.trust"
            shutil.copy(FIXTURES_DIR / "F1.trust", tmp_f1)

            # Step 1: Initial check
            r1 = check_file(tmp_f1)
            assert r1.exit_code == 1
            assert len(r1.diagnostics) == 2

            # Step 2: Apply TC-001 fix
            rc, msg, _ = apply_fix_to_file(tmp_f1, r1.diagnostics, rule_id="TC-001")
            assert rc == 0

            # Step 3: Re-check; only TC-003 remains at line 31
            r2 = check_file(tmp_f1)
            assert r2.exit_code == 1
            assert len(r2.diagnostics) == 1
            rem_diag = r2.diagnostics[0]
            assert rem_diag.rule_id == RuleId.TC_003
            assert rem_diag.span.line == 31
            assert rem_diag.span.col == 3

            # Step 4: Manually project User [id, email]
            content = tmp_f1.read_text(encoding="utf-8")
            assert "returns: User\n" in content
            content = content.replace("returns: User\n", "returns: User [id, email]\n")
            tmp_f1.write_text(content, encoding="utf-8", newline="\n")

            # Step 5: Byte-for-byte identical to F2
            f2_content = (FIXTURES_DIR / "F2.trust").read_text(encoding="utf-8")
            assert tmp_f1.read_text(encoding="utf-8") == f2_content

            # Step 6: Check now passes with exit 0
            r3 = check_file(tmp_f1)
            assert r3.exit_code == 0
            assert r3.ok

    def test_x14_multiple_secrets_patch(self):
        """X14 has no secrets block; TC-005 patch adds declarations without duplicate blocks."""
        with tempfile.TemporaryDirectory() as td:
            tmp_x14 = Path(td) / "X14.trust"
            shutil.copy(FIXTURES_DIR / "X14.trust", tmp_x14)

            r1 = check_file(tmp_x14)
            assert r1.exit_code == 1
            tc005 = [d for d in r1.diagnostics if d.rule_id == RuleId.TC_005][0]
            assert "DB_URL" in tc005.message and "JWT_SECRET" in tc005.message

            # Apply TC-005 fix
            rc, _, _ = apply_fix_to_file(tmp_x14, r1.diagnostics, rule_id="TC-005")
            assert rc == 0

            # Post-check: TC-005 is resolved and secrets block is valid
            r2 = check_file(tmp_x14)
            assert not any(d.rule_id == RuleId.TC_005 for d in r2.diagnostics)
            content = tmp_x14.read_text(encoding="utf-8")
            assert content.count("secrets:") == 1
            assert "DB_URL: env" in content
            assert "JWT_SECRET: env" in content
