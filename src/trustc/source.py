"""Source handling: normalization, byte limits, hashing and span utilities.

Implements A-contracts.md §Conventions for source preparation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Tuple

# A-contracts.md: UTF-8 input is limited to 262144 bytes
MAX_INPUT_BYTES = 262_144  # 256 KiB


@dataclass(frozen=True)
class Span:
    """1-based line/column source span."""

    line: int
    col: int
    end_line: int
    end_col: int

    def to_dict(self) -> dict[str, int]:
        return {
            "line": self.line,
            "col": self.col,
            "endLine": self.end_line,
            "endCol": self.end_col,
        }


class SourceError(Exception):
    """Raised when source cannot be processed (encoding/size)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def check_input_size(raw_bytes: bytes) -> None:
    """Check raw UTF-8 input size BEFORE normalization.

    Per A-contracts.md: check raw UTF-8 input size before normalization
    so normalization cannot shrink oversized input past the boundary.
    """
    if len(raw_bytes) > MAX_INPUT_BYTES:
        raise SourceError(
            f"Input exceeds {MAX_INPUT_BYTES} byte limit "
            f"({len(raw_bytes)} bytes)"
        )


def normalize_source(raw: str) -> str:
    """Normalize CRLF/CR to LF. Do not trim or reformat.

    Per A-contracts.md: Normalize CRLF/CR to LF before hashing,
    parsing and fixing; do not trim or reformat.
    Stage 0 correction: no forced trailing newline.
    """
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def spec_hash(normalized: str) -> str:
    """SHA-256 of normalized UTF-8 text, lowercase hex."""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_tabs(source: str) -> Span | None:
    """Check for tab characters, which are rejected per B1."""
    for i, line in enumerate(source.split("\n"), 1):
        col = line.find("\t")
        if col >= 0:
            return Span(line=i, col=col + 1, end_line=i, end_col=col + 2)
    return None


def build_line_index(source: str) -> List[int]:
    """Build an index mapping line numbers (0-based) to byte offsets.

    Returns a list where index i is the character offset of line i+1.
    """
    offsets = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def offset_to_position(
    line_offsets: List[int], offset: int
) -> Tuple[int, int]:
    """Convert a 0-based character offset to 1-based (line, col)."""
    # Binary search for the line
    lo, hi = 0, len(line_offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if line_offsets[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    line_0 = lo
    col_0 = offset - line_offsets[line_0]
    return (line_0 + 1, col_0 + 1)
