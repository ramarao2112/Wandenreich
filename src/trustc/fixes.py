"""Diff generation and patch application engine for TrustC verifier fixes."""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from trustc.contracts import Diagnostic, DiffFix
from trustc.ir import Endpoint, Program
from trustc.source import check_input_size, normalize_source, spec_hash


def generate_unified_diff(
    original_text: str,
    modified_text: str,
    filename: str = "spec.trust",
) -> str:
    """Generate a clean unified diff string compatible with git apply."""
    orig_lines = original_text.splitlines(keepends=True)
    mod_lines = modified_text.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))
    return "".join(diff_lines)


def create_tc001_diff(source: str, ep: Endpoint, current_hash: str) -> DiffFix:
    """Create a DiffFix inserting '  auth: required' for TC-001."""
    lines = source.splitlines(keepends=True)
    # 1-based line of the endpoint declaration
    ep_line_idx = ep.span.line - 1

    # Search downward from endpoint line for '  resource:'
    insert_idx = ep_line_idx + 1
    for i in range(ep_line_idx, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("resource:"):
            insert_idx = i + 1
            break
        # Don't pass into another top-level declaration
        if i > ep_line_idx and lines[i] and not lines[i].startswith(" "):
            break

    new_lines = list(lines)
    new_lines.insert(insert_idx, "  auth: required\n")
    modified_text = "".join(new_lines)
    diff = generate_unified_diff(source, modified_text)

    return DiffFix(
        baseSpecHash=current_hash,
        diff=diff,
        label="Suggested restrictive default: require authentication",
    )


def create_tc004_diff(
    source: str, ep: Endpoint, forbidden_field: str, current_hash: str
) -> DiffFix:
    """Create a DiffFix removing a server-controlled field from body for TC-004."""
    lines = source.splitlines(keepends=True)

    # Locate body: line within endpoint
    ep_line_idx = ep.span.line - 1
    body_line_idx = -1
    for i in range(ep_line_idx, len(lines)):
        if lines[i].strip().startswith("body:"):
            body_line_idx = i
            break
        if i > ep_line_idx and lines[i] and not lines[i].startswith(" "):
            break

    if body_line_idx == -1:
        # Fallback if body line span available
        if ep.body_span:
            body_line_idx = ep.body_span.line - 1

    new_lines = list(lines)
    if body_line_idx != -1:
        orig_line = lines[body_line_idx]
        # Match body: [field1, field2, ...]
        m = re.search(r"body:\s*\[(.*?)\]", orig_line)
        if m:
            raw_fields = [f.strip() for f in m.group(1).split(",") if f.strip()]
            remaining_fields = [f for f in raw_fields if f != forbidden_field]
            new_body_content = ", ".join(remaining_fields)
            indent = orig_line[: orig_line.find("body:")]
            new_lines[body_line_idx] = f"{indent}body: [{new_body_content}]\n"

    modified_text = "".join(new_lines)
    diff = generate_unified_diff(source, modified_text)

    return DiffFix(
        baseSpecHash=current_hash,
        diff=diff,
        label=f"Remove server-controlled field '{forbidden_field}' from body",
    )


def create_tc005_diff(
    source: str, program: Program, missing_secrets: List[str], current_hash: str
) -> DiffFix:
    """Create a DiffFix declaring required environment secret(s) for TC-005."""
    lines = source.splitlines(keepends=True)
    new_lines = list(lines)

    if program.secrets:
        # secrets block exists — append missing declarations after the secrets: line
        sec_idx = -1
        for i, l in enumerate(lines):
            if l.strip().startswith("secrets:"):
                sec_idx = i
                break

        insert_pos = sec_idx + 1
        # Advance past existing secret declarations
        while insert_pos < len(lines) and lines[insert_pos].startswith("  "):
            insert_pos += 1

        to_insert = [f"  {s}: env\n" for s in missing_secrets]
        for idx, item in enumerate(to_insert):
            new_lines.insert(insert_pos + idx, item)
    else:
        # No secrets block — find first endpoint line and insert block before it
        first_ep_idx = 0
        if program.endpoints:
            first_ep_idx = program.endpoints[0].span.line - 1
        else:
            first_ep_idx = len(lines)

        block_lines = ["secrets:\n"] + [f"  {s}: env\n" for s in missing_secrets] + ["\n"]
        for idx, item in enumerate(block_lines):
            new_lines.insert(first_ep_idx + idx, item)

    modified_text = "".join(new_lines)
    diff = generate_unified_diff(source, modified_text)

    return DiffFix(
        baseSpecHash=current_hash,
        diff=diff,
        label="Declare required environment secret(s)",
    )


def apply_patch_text(source: str, patch: str) -> str:
    """Apply a unified diff patch to source text using exact-context matching."""
    # Split into lines
    src_lines = source.splitlines(keepends=True)
    patch_lines = patch.splitlines(keepends=True)

    # Simple, deterministic patch applicator for single/multi-hunk unified diffs
    # Parse hunks from patch_lines
    i = 0
    hunks: List[Dict[str, Any]] = []
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            # Header: @@ -start,count +start,count @@
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                old_start = int(m.group(1))
                old_count = int(m.group(2)) if m.group(2) is not None else 1
                new_start = int(m.group(3))
                new_count = int(m.group(4)) if m.group(4) is not None else 1
                i += 1
                hunk_lines: List[str] = []
                while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                    if patch_lines[i].startswith(("+", "-", " ")):
                        hunk_lines.append(patch_lines[i])
                    i += 1
                hunks.append({
                    "old_start": old_start,
                    "old_count": old_count,
                    "new_start": new_start,
                    "new_count": new_count,
                    "lines": hunk_lines,
                })
                continue
        i += 1

    if not hunks:
        raise ValueError("Malformed or empty unified diff patch")

    # Apply hunks in reverse order (by old_start) so line indices remain stable
    result_lines = list(src_lines)
    for hunk in sorted(hunks, key=lambda h: h["old_start"], reverse=True):
        old_start_0 = hunk["old_start"] - 1
        old_count = hunk["old_count"]

        # Validate context
        expected_old_slice: List[str] = []
        replacement_slice: List[str] = []
        for hl in hunk["lines"]:
            prefix = hl[0]
            content = hl[1:]
            if prefix == " ":
                expected_old_slice.append(content)
                replacement_slice.append(content)
            elif prefix == "-":
                expected_old_slice.append(content)
            elif prefix == "+":
                replacement_slice.append(content)

        actual_slice = result_lines[old_start_0: old_start_0 + old_count]
        if actual_slice != expected_old_slice:
            raise ValueError(
                f"Patch context mismatch at line {hunk['old_start']}.\n"
                f"Expected: {''.join(expected_old_slice)!r}\n"
                f"Found:    {''.join(actual_slice)!r}"
            )

        # Replace slice
        result_lines[old_start_0: old_start_0 + old_count] = replacement_slice

    return "".join(result_lines)


def apply_fix_to_file(
    path: Path,
    diagnostics: List[Diagnostic],
    rule_id: Optional[str] = None,
    line: Optional[int] = None,
    apply_all: bool = False,
    dry_run: bool = False,
) -> Tuple[int, str, Optional[str]]:
    """Apply eligible fix(es) to a file.

    Returns:
        (exit_code, message_or_diff, new_source_or_none)
        Exit 0: Patch applied or dry-run printed
        Exit 1: Hash/context mismatch or refusal
        Exit 2: Ambiguous invocation (multiple fixes without --line or --all)
    """
    raw_bytes = path.read_bytes()
    check_input_size(raw_bytes)
    raw_text = raw_bytes.decode("utf-8")
    source = normalize_source(raw_text)
    current_hash = spec_hash(source)

    # Filter diagnostics that have a DiffFix
    diff_diags = [d for d in diagnostics if isinstance(d.fix, DiffFix)]

    if rule_id:
        normalized_rule = rule_id.upper()
        diff_diags = [d for d in diff_diags if d.rule_id == normalized_rule]

    if line is not None:
        diff_diags = [d for d in diff_diags if d.span.line == line]

    if not diff_diags:
        return 1, f"No applicable diff fixes found for file '{path.name}'.", None

    if len(diff_diags) > 1 and not apply_all and line is None:
        lines_available = ", ".join(str(d.span.line) for d in diff_diags)
        msg = (
            f"Multiple fixes available for {rule_id or 'rules'} at lines [{lines_available}]. "
            f"Specify --line <LINE> or pass --all to apply all fixes in batch."
        )
        return 2, msg, None

    # Verify baseSpecHash on all candidate fixes
    for d in diff_diags:
        assert isinstance(d.fix, DiffFix)
        if d.fix.base_spec_hash != current_hash:
            msg = (
                f"Refused: Spec hash mismatch. File hash is {current_hash}, "
                f"but patch was generated against baseSpecHash {d.fix.base_spec_hash}."
            )
            return 1, msg, None

    # Apply single fix or compute consolidated batch
    if len(diff_diags) == 1:
        target_fix = diff_diags[0].fix
        assert isinstance(target_fix, DiffFix)
        patch = target_fix.diff
        try:
            patched_source = apply_patch_text(source, patch)
        except Exception as e:
            return 1, f"Failed to apply patch: {e}", None
    else:
        # Batch: Apply sequentially on the working text to generate a unified patch
        curr_text = source
        for d in sorted(diff_diags, key=lambda x: x.span.line, reverse=True):
            assert isinstance(d.fix, DiffFix)
            # Recompute / apply sequentially
            try:
                curr_text = apply_patch_text(curr_text, d.fix.diff)
            except Exception:
                # If offset shifted in batch, recompute unified diff from source to final
                pass
        patched_source = curr_text
        patch = generate_unified_diff(source, patched_source, filename=path.name)

    if dry_run:
        return 0, patch, None

    # Atomic write to file
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(patched_source, encoding="utf-8", newline="\n")
    tmp_path.replace(path)

    return 0, f"Successfully applied fix(es) to {path.name}", patched_source
