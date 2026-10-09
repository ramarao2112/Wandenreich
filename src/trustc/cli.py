from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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

    # parse
    parse_parser = subparsers.add_parser("parse", help="Parse a TrustSpec file to IR")
    parse_parser.add_argument("spec", help="Path to .trust file")
    parse_parser.add_argument("--format", choices=["json", "human"], default="json")

    # check
    check_parser = subparsers.add_parser("check", help="Parse and verify a TrustSpec file")
    check_parser.add_argument("spec", help="Path to .trust file")
    check_parser.add_argument("--format", choices=["json", "sarif", "human"], default=None)
    check_parser.add_argument("--json", action="store_true", help="Output JSON format")
    check_parser.add_argument("--sarif", action="store_true", help="Output SARIF format")
    check_parser.add_argument(
        "--revision", type=int, default=0, help="Spec revision version (default: 0)"
    )

    # build
    build_parser = subparsers.add_parser("build", help="Generate a FastAPI app from a TrustSpec")
    build_parser.add_argument("spec", help="Path to .trust file")
    build_parser.add_argument(
        "--target", default="fastapi", choices=["fastapi"], help="Target backend"
    )
    build_parser.add_argument("--output", "-o", default="out/", help="Output directory")
    build_parser.add_argument(
        "--replace", action="store_true", help="Replace existing TrustC output"
    )
    build_parser.add_argument("--format", choices=["json", "human"], default="json")
    build_parser.add_argument(
        "--revision", type=int, default=0, help="Spec revision version (default: 0)"
    )

    # attack
    attack_parser = subparsers.add_parser("attack", help="Build, run and test the generated app")
    attack_parser.add_argument("spec", help="Path to .trust file")
    attack_parser.add_argument(
        "--format", choices=["json", "human"], default="human", help="Output format"
    )
    attack_parser.add_argument(
        "--revision", type=int, default=0, help="Spec revision version (default: 0)"
    )

    # fix and apply-fix
    for cmd_name in ["fix", "apply-fix"]:
        fix_parser = subparsers.add_parser(cmd_name, help="Apply proposed security fixes")
        fix_parser.add_argument("spec", help="Path to .trust file")
        fix_parser.add_argument("--rule", help="Rule ID to fix (e.g. TC-001)")
        fix_parser.add_argument("--line", type=int, help="Specific line to fix")
        fix_parser.add_argument(
            "--all", action="store_true", dest="fix_all", help="Apply all fixes for --rule"
        )
        fix_parser.add_argument(
            "--dry-run", action="store_true", help="Show patch without applying"
        )

    # explain
    explain_parser = subparsers.add_parser("explain", help="Explain a security rule")
    explain_parser.add_argument("rule_id", help="Rule ID (e.g. TC-001)")

    # serve
    serve_parser = subparsers.add_parser(
        "serve", help="Run the local API server and workbench"
    )
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8787, help="Port to bind (default: 8787)"
    )
    serve_parser.add_argument(
        "--static", default=None, help="Directory to serve static UI assets from"
    )
    serve_parser.add_argument(
        "--workspace", default=None, help="Workspace directory for server artifacts"
    )

    return parser


def _cmd_parse(args: argparse.Namespace) -> int:
    """Execute 'trustc parse' command."""
    from trustc.parser import TrustSpecError, parse_file
    from trustc.source import SourceError

    fmt = getattr(args, "format", "json")

    try:
        program = parse_file(args.spec)
        if fmt == "json":
            print(json.dumps(program.to_dict(), indent=2))
        else:
            print(f"Program parsed successfully: {args.spec}")
            res_names = ', '.join(r.name for r in program.resources)
            sec_names = ', '.join(s.name for s in program.secrets)
            print(f"  Resources ({len(program.resources)}): {res_names}")
            print(f"  Secrets ({len(program.secrets)}): {sec_names}")
            print(f"  Endpoints ({len(program.endpoints)}):")
            for ep in program.endpoints:
                mode_str = ep.inferred_mode.value if ep.inferred_mode else "none"
                print(f"    {ep.method} {ep.path} -> mode: {mode_str}, auth: {ep.auth.value}")
        return 0

    except TrustSpecError as exc:
        if fmt == "json":
            print(json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        else:
            for err in exc.errors:
                loc = f"line {err.span.line}, col {err.span.col}"
                print(
                    f"Error [{err.kind}/{err.code}] at {loc}: {err.message}",
                    file=sys.stderr,
                )
                if err.snippet:
                    print(f"  {err.span.line} | {err.snippet}", file=sys.stderr)
        return 2

    except (SourceError, FileNotFoundError) as exc:
        if fmt == "json":
            err_dict = {
                "schemaVersion": 2,
                "exitCode": 2,
                "specErrors": [
                    {
                        "kind": "syntax",
                        "code": "SOURCE_ERROR",
                        "message": str(exc),
                        "span": {"line": 1, "col": 1, "endLine": 1, "endCol": 1},
                        "snippet": "",
                    }
                ],
            }
            print(json.dumps(err_dict, indent=2), file=sys.stderr)
        else:
            print(f"Error reading {args.spec}: {exc}", file=sys.stderr)
        return 2

    except Exception as exc:
        print(f"Internal error: {exc}", file=sys.stderr)
        return 3


def _cmd_check(args: argparse.Namespace) -> int:
    """Execute 'trustc check' command."""
    from trustc.verifier import check_file, export_sarif, format_human_report

    fmt = getattr(args, "format", None)
    if getattr(args, "sarif", False):
        fmt = "sarif"
    elif getattr(args, "json", False):
        fmt = "json"
    elif not fmt:
        fmt = "json"

    try:
        result = check_file(args.spec, spec_version=getattr(args, "revision", 0))
        if fmt == "sarif":
            sarif_data = export_sarif(result, filename=args.spec)
            print(json.dumps(sarif_data, indent=2))
        elif fmt == "human":
            print(format_human_report(result, filename=args.spec))
        else:
            print(json.dumps(result.to_dict(), indent=2))
        return result.exit_code
    except Exception as exc:
        print(f"Internal error: {exc}", file=sys.stderr)
        return 3


def _cmd_fix(args: argparse.Namespace) -> int:
    """Execute 'trustc fix' or 'trustc apply-fix' command."""
    from trustc.fixes import apply_fix_to_file
    from trustc.verifier import check_file

    p = Path(args.spec)
    if not p.exists():
        print(f"Error: File not found: {args.spec}", file=sys.stderr)
        return 2

    check_res = check_file(p, spec_version=getattr(args, "revision", 0))
    if check_res.exit_code == 2:
        print(
            "Cannot apply fixes: spec has syntax or reference errors (exit 2).",
            file=sys.stderr,
        )
        return 2

    rc, msg, _ = apply_fix_to_file(
        path=p,
        diagnostics=check_res.diagnostics,
        rule_id=getattr(args, "rule", None),
        line=getattr(args, "line", None),
        apply_all=getattr(args, "fix_all", False),
        dry_run=getattr(args, "dry_run", False),
    )

    if getattr(args, "dry_run", False):
        if rc == 0:
            print(msg, end="" if msg.endswith("\n") else "\n")
        else:
            print(msg, file=sys.stderr)
        return rc
    else:
        if rc == 0:
            print(msg)
        else:
            print(msg, file=sys.stderr)
        return rc


def _cmd_explain(args: argparse.Namespace) -> int:
    """Execute 'trustc explain' command."""
    from trustc.rules_doc import get_rule_doc

    try:
        doc = get_rule_doc(args.rule_id)
        print(doc, end="" if doc.endswith("\n") else "\n")
        return 0
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def _cmd_build(args: argparse.Namespace) -> int:
    """Execute 'trustc build' command."""
    from trustc.generator import BuildError, build_app

    out_dir = getattr(args, "output", "out/")
    replace = getattr(args, "replace", False)
    fmt = getattr(args, "format", "json")
    revision = getattr(args, "revision", 0)

    try:
        success = build_app(
            args.spec,
            out_dir,
            replace=replace,
            spec_version=revision,
        )
        if fmt == "human":
            print(f"Build succeeded for {args.spec}")
            print(f"  Build ID: {success.build_id}")
            print(f"  Output directory: {out_dir}")
            print(f"  Files generated: {len(success.files)}")
        else:
            print(json.dumps(success.model_dump(by_alias=True), indent=2))
        return 0

    except BuildError as exc:
        if exc.failure is not None:
            if fmt == "human":
                print(f"Build failed ({exc.failure.status}): {exc}", file=sys.stderr)
                for err in exc.failure.spec_errors:
                    print(
                        f"  {err.kind}: {err.message} at line {err.span.line}",
                        file=sys.stderr,
                    )
                for diag in exc.failure.diagnostics:
                    print(
                        f"  {diag.rule_id}: {diag.message} at {diag.location}",
                        file=sys.stderr,
                    )
            else:
                print(
                    json.dumps(exc.failure.model_dump(by_alias=True), indent=2),
                )
        else:
            print(f"Build error: {exc}", file=sys.stderr)
        return exc.exit_code

    except Exception as exc:
        print(f"Internal error: {exc}", file=sys.stderr)
        return 3


def _cmd_attack(args: argparse.Namespace) -> int:
    """Execute 'trustc attack' command."""
    from trustc.harness import attack_spec

    fmt = getattr(args, "format", "human")
    revision = getattr(args, "revision", 0)

    try:
        result = attack_spec(
            args.spec,
            spec_version=revision,
            fmt=fmt,
        )
        return result.exit_code
    except Exception as exc:
        print(f"Internal error: {exc}", file=sys.stderr)
        return 3


def _cmd_serve(args: argparse.Namespace) -> int:
    """Execute 'trustc serve' command."""
    from trustc.server import run_server

    try:
        run_server(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8787),
            static_dir=getattr(args, "static", None),
            workspace_dir=getattr(args, "workspace", None),
        )
        return 0
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Server error: {exc}", file=sys.stderr)
        return 3


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "parse":
        return _cmd_parse(args)
    elif args.command == "check":
        return _cmd_check(args)
    elif args.command in ("fix", "apply-fix"):
        return _cmd_fix(args)
    elif args.command == "explain":
        return _cmd_explain(args)
    elif args.command == "build":
        return _cmd_build(args)
    elif args.command == "attack":
        return _cmd_attack(args)
    elif args.command == "serve":
        return _cmd_serve(args)

    # Future stages
    print(
        f"trustc {args.command}: not yet implemented (Stage 7+).",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
