from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from trustc import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trustc",
        description="TrustC — security-focused compiler and workbench for TrustSpec",
    )
    parser.add_argument(
        "--version", action="version", version=f"trustc {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # check
    check_parser = subparsers.add_parser("check", help="Parse and verify a TrustSpec file")
    check_parser.add_argument("spec", help="Path to .trust file")
    check_parser.add_argument("--format", choices=["json", "sarif"], default="json")

    # build
    build_parser = subparsers.add_parser("build", help="Generate a FastAPI app from a TrustSpec")
    build_parser.add_argument("spec", help="Path to .trust file")
    build_parser.add_argument("--output", "-o", default="out/", help="Output directory")
    build_parser.add_argument("--replace", action="store_true", help="Replace existing TrustC output")

    # attack
    attack_parser = subparsers.add_parser("attack", help="Build, run and test the generated app")
    attack_parser.add_argument("spec", help="Path to .trust file")

    # fix
    fix_parser = subparsers.add_parser("fix", help="Apply proposed security fixes")
    fix_parser.add_argument("spec", help="Path to .trust file")
    fix_parser.add_argument("--rule", help="Rule ID to fix (e.g. TC-001)")
    fix_parser.add_argument("--line", type=int, help="Specific line to fix")
    fix_parser.add_argument("--all", action="store_true", dest="fix_all", help="Apply all fixes for --rule")
    fix_parser.add_argument("--dry-run", action="store_true", help="Show patch without applying")

    # explain
    explain_parser = subparsers.add_parser("explain", help="Explain a security rule")
    explain_parser.add_argument("rule_id", help="Rule ID (e.g. TC-001)")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Stage 1: only --help/--version are functional
    print(
        f"trustc {args.command}: not yet implemented (Stage 2+).",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
