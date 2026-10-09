"""TrustC Stage 4 — Backend Code Generator for FastAPI.

Generates a fully typed, secure, runnable FastAPI application backed by
SQLAlchemy 2.0 Async ORM and SQLite (aiosqlite) from a validated TrustSpec IR.
Complies with TrustSpec B-compiler-spec.md §B2, §B4, §B6, §B7 and A-contracts.md.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from jinja2 import BaseLoader, Environment, FileSystemLoader, PackageLoader, select_autoescape

from trustc import __version__ as COMPILER_VERSION
from trustc.contracts import (
    BuildEvidence,
    BuildSuccess,
    Declaration,
    DeclarationKind,
    EndpointMode,
    EndpointPolicy,
    ForcedLine,
    ForcedLineKind,
    GeneratedFile,
    RunFailure,
    Span,
)
from trustc.ir import AuthKind, FieldTypeEnum, OperationKind, Program
from trustc.manifest import generate_manifest, verify_manifest
from trustc.parser import parse_file
from trustc.source import Span as IRSpan
from trustc.verifier import CheckResult, check_file

TEMPLATE_VERSION = "1.0.0"

PROVENANCE_REGEX = re.compile(
    r"# \[trustc:provenance kind=([a-z-]+) span=(\d+):(\d+)-(\d+):(\d+)\]"
)

# Exact structural restrictions required by §B7
STRUCTURAL_RESTRICTIONS = [
    "The supported IR has no raw-query operation",
    "Generated secret references resolve through environment variables",
    "Every accepted input field has a supported type",
]

# Known limitations required by §B7
LIMITATIONS = [
    "one identity resource",
    "no signup/login UI, RBAC, migrations, pagination, rate limiting or CSRF implementation",
    "no arbitrary relationships, enum unsupported",
    "no production deployment hardening claim",
    (
        "local harness covers declared item access and selected response assertions; "
        "does not establish complete business-policy correctness"
    ),
]


class BuildError(Exception):
    """Base exception for code generation errors."""

    def __init__(self, message: str, exit_code: int = 1, failure: Optional[RunFailure] = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.failure = failure


def _get_jinja_env() -> Environment:
    """Create Jinja2 environment with package loader and filesystem fallback."""
    loader: BaseLoader
    try:
        loader = PackageLoader("trustc", "templates/fastapi")
    except Exception:
        template_dir = Path(__file__).parent / "templates" / "fastapi"
        loader = FileSystemLoader(str(template_dir))

    return Environment(
        loader=loader,
        autoescape=select_autoescape(disabled_extensions=("jinja", "py", "txt", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _render_file(tpl: Any, ctx: Dict[str, Any]) -> str:
    rendered = str(tpl.render(**ctx))
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def _py_type_for_field(field_type: FieldTypeEnum) -> str:
    if field_type == FieldTypeEnum.UUID:
        return "uuid.UUID"
    elif field_type == FieldTypeEnum.INT:
        return "int"
    elif field_type == FieldTypeEnum.BOOL:
        return "bool"
    elif field_type == FieldTypeEnum.EMAIL:
        return "EmailStr"
    else:
        return "str"


def _format_span(s: IRSpan | Span) -> str:
    return f"{s.line}:{s.col}-{s.end_line}:{s.end_col}"


def _scan_forced_lines(content: str) -> List[ForcedLine]:
    """Scan rendered Python content for provenance markers and build ForcedLine records."""
    forced: List[ForcedLine] = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        match = PROVENANCE_REGEX.search(line)
        if match:
            kind_str = match.group(1)
            start_line = int(match.group(2))
            start_col = int(match.group(3))
            end_line = int(match.group(4))
            end_col = int(match.group(5))
            try:
                kind_enum = ForcedLineKind(kind_str)
            except ValueError:
                continue
            spec_span = Span(
                line=start_line,
                col=start_col,
                endLine=end_line,
                endCol=end_col,
            )
            forced.append(ForcedLine(line=idx, specSpan=spec_span, kind=kind_enum))
    return forced


def _prepare_generation_context(program: Program) -> Dict[str, Any]:
    """Prepare lowered template variables from IR Program."""
    resources_data: List[Dict[str, Any]] = []
    user_id_span: Optional[IRSpan] = None

    for res in program.resources:
        if res.name == "User":
            id_field = res.get_field("id")
            if id_field:
                user_id_span = id_field.span

        ordinary_fields: List[Dict[str, Any]] = []
        for f in res.fields:
            if f.name == "id":
                continue
            is_own = res.ownership is not None and res.ownership.field_name == f.name
            ordinary_fields.append({
                "name": f.name,
                "type": f.field_type.value,
                "py_type": _py_type_for_field(f.field_type),
                "sensitive": f.sensitive,
                "is_credential": f.is_credential,
                "is_ownership": is_own,
                "target_table": "users" if is_own else None,
                "span": f.span,
            })

        ownership_span = res.ownership.span if res.ownership else IRSpan(1, 1, 1, 1)

        resources_data.append({
            "name": res.name,
            "table_name": f"{res.name.lower()}s",
            "is_owned": res.ownership is not None,
            "ownership_field": res.ownership.field_name if res.ownership else None,
            "ownership_span": _format_span(ownership_span),
            "ordinary_fields": ordinary_fields,
        })

    # Request schemas & Response schemas
    request_schemas: List[Dict[str, Any]] = []
    response_schemas: List[Dict[str, Any]] = []
    seen_req: Set[str] = set()
    seen_resp: Set[str] = set()

    # Route representations
    endpoints_by_resource: Dict[str, List[Dict[str, Any]]] = {}

    for ep in program.endpoints:
        res = program.get_resource(ep.resource_name)
        ep_res_list = endpoints_by_resource.setdefault(ep.resource_name, [])

        # Schema naming
        suffix = ""
        path_parts = [p for p in ep.path.split("/") if p and not p.startswith("{")]
        if len(path_parts) > 1:
            suffix = path_parts[-1].capitalize()

        req_schema_name: Optional[str] = None
        if ep.body_fields:
            if ep.operation == OperationKind.CREATE:
                req_schema_name = f"{ep.resource_name}Create"
            elif ep.operation == OperationKind.PARTIAL_UPDATE:
                req_schema_name = f"{ep.resource_name}{suffix}Patch"
            else:
                req_schema_name = f"{ep.resource_name}{suffix}Update"

            if req_schema_name not in seen_req:
                seen_req.add(req_schema_name)
                req_fields = []
                for fname in ep.body_fields:
                    f_node = res.get_field(fname)
                    if f_node:
                        req_fields.append({
                            "name": fname,
                            "py_type": _py_type_for_field(f_node.field_type),
                        })
                request_schemas.append({
                    "name": req_schema_name,
                    "is_patch": ep.operation == OperationKind.PARTIAL_UPDATE,
                    "fields": req_fields,
                })

        # Response schema
        resp_schema_name: Optional[str] = None
        if ep.returns_resource:
            ret_res = program.get_resource(ep.returns_resource)
            # Differentiate by projection
            if ep.returns_projection:
                proj_tag = "".join(p.capitalize() for p in ep.returns_projection)
                resp_schema_name = f"{ep.returns_resource}{proj_tag}Response"
            else:
                resp_schema_name = f"{ep.returns_resource}Response"

            if resp_schema_name not in seen_resp:
                seen_resp.add(resp_schema_name)
                resp_fields = []
                target_fields = (
                    ep.returns_projection
                    if ep.returns_projection is not None
                    else [f.name for f in ret_res.fields]
                )
                for fname in target_fields:
                    f_node = ret_res.get_field(fname)
                    if not f_node or f_node.is_credential:
                        continue  # Never include credentials
                    is_non_null = fname in (
                        "id",
                        ret_res.ownership.field_name if ret_res.ownership else "",
                    )
                    resp_fields.append({
                        "name": fname,
                        "py_type": _py_type_for_field(f_node.field_type),
                        "nullable": not is_non_null,
                    })
                response_schemas.append({
                    "name": resp_schema_name,
                    "fields": resp_fields,
                })

        # Route path calculation relative to prefix
        prefix = f"/{res.name.lower()}s"
        rel_path = ep.path
        if rel_path.startswith(prefix):
            rel_path = rel_path[len(prefix):]
        if not rel_path:
            rel_path = ""

        # Provenance spans
        auth_span = ep.auth_span or ep.span
        ownership_span = res.ownership.span if res.ownership else IRSpan(1, 1, 1, 1)

        ep_dict = {
            "method": ep.method,
            "path": ep.path,
            "route_path": rel_path,
            "operation": ep.operation.value,
            "op_suffix": suffix.lower() or "item",
            "auth_required": ep.auth == AuthKind.REQUIRED,
            "owner_waived": ep.owner_waived,
            "request_schema_name": req_schema_name,
            "response_schema_name": resp_schema_name,
            "span": _format_span(ep.span),
            "auth_span": _format_span(auth_span),
            "ownership_span": _format_span(ownership_span),
            "self_check_span": _format_span(user_id_span or IRSpan(1, 1, 1, 1)),
        }
        ep_res_list.append(ep_dict)

    # Collect routers
    router_modules: List[Dict[str, Any]] = []
    for r_name in sorted(endpoints_by_resource.keys()):
        router_modules.append({
            "resource_name": r_name,
            "module_name": f"{r_name.lower()}s",
        })

    all_eps = []
    for ep in program.endpoints:
        all_eps.append({
            "method": ep.method,
            "path": ep.path,
            "inferred_mode": ep.inferred_mode.value if ep.inferred_mode else "none",
            "owner_waived": ep.owner_waived,
        })

    needs_email_str = any(
        f.field_type == FieldTypeEnum.EMAIL
        for res in program.resources
        for f in res.fields
    )
    has_patch = any(
        ep.operation == OperationKind.PARTIAL_UPDATE
        for ep in program.endpoints
    )

    return {
        "compiler_version": COMPILER_VERSION,
        "spec_hash": program.source_hash,
        "resources": resources_data,
        "request_schemas": request_schemas,
        "response_schemas": response_schemas,
        "endpoints_by_resource": endpoints_by_resource,
        "router_modules": router_modules,
        "all_endpoints": all_eps,
        "needs_email_str": needs_email_str,
        "has_patch": has_patch,
    }


def generate_app_files(
    program: Program,
    check_result: CheckResult,
    spec_version: int = 0,
) -> Tuple[List[GeneratedFile], BuildEvidence]:
    """Render all FastAPI application templates into in-memory GeneratedFile instances."""
    jinja_env = _get_jinja_env()
    ctx = _prepare_generation_context(program)

    files: List[GeneratedFile] = []

    # 1. db.py
    db_tpl = jinja_env.get_template("db.py.jinja")
    db_content = _render_file(db_tpl, ctx)
    files.append(GeneratedFile(
        path="db.py",
        content=db_content,
        forced=_scan_forced_lines(db_content),
    ))

    # 2. models.py
    models_tpl = jinja_env.get_template("models.py.jinja")
    models_content = _render_file(models_tpl, ctx)
    files.append(GeneratedFile(
        path="models.py",
        content=models_content,
        forced=_scan_forced_lines(models_content),
    ))

    # 3. schemas.py
    schemas_tpl = jinja_env.get_template("schemas.py.jinja")
    schemas_content = _render_file(schemas_tpl, ctx)
    files.append(GeneratedFile(
        path="schemas.py",
        content=schemas_content,
        forced=_scan_forced_lines(schemas_content),
    ))

    # 4. auth.py
    auth_tpl = jinja_env.get_template("auth.py.jinja")
    auth_content = _render_file(auth_tpl, ctx)
    files.append(GeneratedFile(
        path="auth.py",
        content=auth_content,
        forced=_scan_forced_lines(auth_content),
    ))

    # 5. routers/__init__.py
    r_init_tpl = jinja_env.get_template("routers_init.py.jinja")
    r_init_content = _render_file(r_init_tpl, ctx)
    files.append(GeneratedFile(
        path="routers/__init__.py",
        content=r_init_content,
        forced=_scan_forced_lines(r_init_content),
    ))

    # 6. One router per resource with endpoints
    router_tpl = jinja_env.get_template("router.py.jinja")
    for res_name, ep_list in sorted(ctx["endpoints_by_resource"].items()):
        # Determine used schemas in this router
        r_schemas: Set[str] = set()
        for ep_info in ep_list:
            if ep_info["request_schema_name"]:
                r_schemas.add(ep_info["request_schema_name"])
            if ep_info["response_schema_name"]:
                r_schemas.add(ep_info["response_schema_name"])

        res_obj = next(r for r in ctx["resources"] if r["name"] == res_name)
        has_list = any(ep_info["operation"] == "list" for ep_info in ep_list)
        has_delete = any(ep_info["operation"] == "delete" for ep_info in ep_list)
        has_dict = any(
            ep_info["operation"] in ("update", "partial_update")
            and not ep_info["response_schema_name"]
            for ep_info in ep_list
        )
        has_select = any(
            ep_info["operation"] in ("list", "read", "update", "partial_update", "delete")
            for ep_info in ep_list
        )
        has_status = any(
            ep_info["operation"] in ("create", "read", "update", "partial_update", "delete")
            for ep_info in ep_list
        )
        has_auth = any(ep_info["auth_required"] for ep_info in ep_list)
        if has_auth and res_name != "User":
            models_import = f"from models import {res_name}, User"
        else:
            models_import = f"from models import {res_name}"

        router_ctx = {
            **ctx,
            "resource": res_obj,
            "router_prefix": f"/{res_name.lower()}s",
            "endpoints": ep_list,
            "router_schemas": sorted(r_schemas),
            "models_import": models_import,
            "has_list": has_list,
            "has_delete": has_delete,
            "has_dict": has_dict,
            "has_select": has_select,
            "has_status": has_status,
            "has_auth": has_auth,
        }
        r_content = _render_file(router_tpl, router_ctx)
        r_path = f"routers/{res_name.lower()}s.py"
        files.append(GeneratedFile(
            path=r_path,
            content=r_content,
            forced=_scan_forced_lines(r_content),
        ))

    # 7. main.py
    main_tpl = jinja_env.get_template("main.py.jinja")
    main_content = _render_file(main_tpl, ctx)
    files.append(GeneratedFile(
        path="main.py",
        content=main_content,
        forced=_scan_forced_lines(main_content),
    ))

    # 8. requirements.txt
    req_tpl = jinja_env.get_template("requirements.txt.jinja")
    req_content = _render_file(req_tpl, ctx)
    files.append(GeneratedFile(
        path="requirements.txt",
        content=req_content,
        forced=[],
    ))

    # 9. README.md
    readme_tpl = jinja_env.get_template("README.md.jinja")
    readme_content = _render_file(readme_tpl, ctx)
    files.append(GeneratedFile(
        path="README.md",
        content=readme_content,
        forced=[],
    ))

    # Verify Python syntax of every generated Python file
    for gf in files:
        if gf.path.endswith(".py"):
            try:
                compile(gf.content, gf.path, "exec")
            except SyntaxError as syn_err:
                raise BuildError(
                    f"Syntax error in rendered file {gf.path}: {syn_err}",
                    exit_code=3,
                )

    # Assemble declarations & endpoint policies
    endpoint_policies: List[EndpointPolicy] = []
    declarations: List[Declaration] = []

    for ep in program.endpoints:
        mode_val = EndpointMode(ep.inferred_mode.value) if ep.inferred_mode else EndpointMode.PUBLIC
        sens = list(ep.expose_fields or ())
        endpoint_policies.append(EndpointPolicy(
            endpoint=f"{ep.method} {ep.path}",
            mode=mode_val,
            ownerWaived=ep.owner_waived,
            sensitiveFields=sens,
        ))

        # Check for declarations
        if ep.auth == AuthKind.PUBLIC:
            declarations.append(Declaration(
                id=f"decl-pub-{ep.method}-{ep.path.replace('/', '_')}",
                endpoint=f"{ep.method} {ep.path}",
                span=Span(
                    line=ep.span.line,
                    col=ep.span.col,
                    endLine=ep.span.end_line,
                    endCol=ep.span.end_col,
                ),
                kind=DeclarationKind.PUBLIC_AUTH,
                reason="Explicit auth: public declared on endpoint",
            ))
        if ep.owner_waived:
            declarations.append(Declaration(
                id=f"decl-waive-{ep.method}-{ep.path.replace('/', '_')}",
                endpoint=f"{ep.method} {ep.path}",
                span=Span(
                    line=ep.span.line,
                    col=ep.span.col,
                    endLine=ep.span.end_line,
                    endCol=ep.span.end_col,
                ),
                kind=DeclarationKind.OWNERSHIP_WAIVER,
                reason="Explicit authorize: public waiver declared on owned endpoint",
            ))
        if ep.expose_fields:
            declarations.append(Declaration(
                id=f"decl-expose-{ep.method}-{ep.path.replace('/', '_')}",
                endpoint=f"{ep.method} {ep.path}",
                span=Span(
                    line=ep.span.line,
                    col=ep.span.col,
                    endLine=ep.span.end_line,
                    endCol=ep.span.end_col,
                ),
                kind=DeclarationKind.SENSITIVE_EXPOSURE,
                reason=f"Explicit expose: {list(ep.expose_fields)} declared",
            ))

    build_id = str(uuid.uuid4())
    evidence = BuildEvidence(
        schemaVersion=2,
        buildId=build_id,
        specHash=program.source_hash,
        specVersion=spec_version,
        compilerVersion=COMPILER_VERSION,
        templateVersion=TEMPLATE_VERSION,
        rules=check_result.rules,
        endpointPolicies=endpoint_policies,
        structuralRestrictions=STRUCTURAL_RESTRICTIONS,
        declarations=declarations,
        limitations=LIMITATIONS,
    )

    return files, evidence


def build_app(
    spec_path: str | Path,
    output_dir: str | Path,
    replace: bool = False,
    spec_version: int = 0,
) -> BuildSuccess:
    """Validate specification and build a FastAPI backend.

    Guarantees:
    - Pre-verifies with all 5 security rules. F1/F4 refusal leaves destination unchanged.
    - Refuses to overwrite non-TrustC nonempty folder without explicit TrustC report.
    - Requires replace=True to overwrite an existing verified TrustC build.
    - Atomic staging and rollback: write failures leave destination byte-identical.
    - Exports trustc-manifest.json and trustc-report.json with matching specVersion.
    """
    spec_p = Path(spec_path).resolve()
    dest_p = Path(output_dir).resolve()

    # Step 1: Verification
    check_res = check_file(spec_p, spec_version=spec_version)
    if check_res.exit_code == 2:
        failure = RunFailure(
            schemaVersion=2,
            specVersion=check_res.spec_version,
            specHash=check_res.spec_hash,
            command="build",
            ms=check_res.ms,
            kind="build",
            status="invalid_spec",
            exitCode=2,
            specErrors=check_res.spec_errors,
            diagnostics=[],
        )
        raise BuildError(
            "Specification has syntax or reference errors",
            exit_code=2,
            failure=failure,
        )
    elif check_res.exit_code == 1:
        failure = RunFailure(
            schemaVersion=2,
            specVersion=check_res.spec_version,
            specHash=check_res.spec_hash,
            command="build",
            ms=check_res.ms,
            kind="build",
            status="refused",
            exitCode=1,
            specErrors=[],
            diagnostics=check_res.diagnostics,
        )
        raise BuildError(
            "Specification failed security verification",
            exit_code=1,
            failure=failure,
        )

    program = parse_file(spec_p)

    # Step 2: Destination directory safety check
    if dest_p.exists() and any(dest_p.iterdir()):
        report_file = dest_p / "trustc-report.json"
        manifest_file = dest_p / "trustc-manifest.json"
        if not report_file.exists() and not manifest_file.exists():
            raise BuildError(
                f"Refusing to overwrite nonempty non-TrustC directory: {dest_p}",
                exit_code=1,
            )
        if not replace:
            raise BuildError(
                f"Destination directory already exists: {dest_p}. Use --replace to overwrite.",
                exit_code=1,
            )

    # Step 3: Render files in memory
    files, evidence = generate_app_files(program, check_res, spec_version=spec_version)

    # Step 4: Staging directory render & atomic publication
    staging_dir = Path(tempfile.mkdtemp(prefix="trustc_stage_"))
    backup_dir: Optional[Path] = None
    try:
        # Build files dict for manifest computation
        files_dict: Dict[str, bytes] = {
            gf.path: gf.content.encode("utf-8") for gf in files
        }

        # Write files into staging
        for gf in files:
            target = staging_dir / gf.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files_dict[gf.path])

        # Generate trustc-manifest.json
        manifest_json, _ = generate_manifest(
            files_dict=files_dict,
            build_id=evidence.build_id,
            spec_hash=program.source_hash,
            spec_version=spec_version,
            compiler_version=COMPILER_VERSION,
            template_version=TEMPLATE_VERSION,
        )
        (staging_dir / "trustc-manifest.json").write_bytes(manifest_json.encode("utf-8"))
        manifest_gf = GeneratedFile(
            path="trustc-manifest.json",
            content=manifest_json,
            forced=[],
        )
        files.append(manifest_gf)

        # Create BuildSuccess model
        build_success = BuildSuccess(
            schemaVersion=2,
            specVersion=check_res.spec_version,
            specHash=check_res.spec_hash,
            command="build",
            ms=check_res.ms,
            kind="build",
            status="completed",
            exitCode=0,
            buildId=evidence.build_id,
            files=files,
            evidence=evidence,
        )

        # Write trustc-report.json in staging
        report_data = build_success.model_dump(by_alias=True)
        report_json = json.dumps(report_data, indent=2) + "\n"
        (staging_dir / "trustc-report.json").write_bytes(report_json.encode("utf-8"))

        # Also add trustc-report.json to files in BuildSuccess
        report_gf = GeneratedFile(
            path="trustc-report.json",
            content=report_json,
            forced=[],
        )
        build_success.files.append(report_gf)

        # Pre-publication verification of manifest in staging
        staged_ok, staged_reason = verify_manifest(staging_dir)
        if not staged_ok:
            raise BuildError(
                f"Staged artifact manifest verification failed: {staged_reason}",
                exit_code=3,
            )

        # Safe atomic publish with rollback:
        if dest_p.exists() and any(dest_p.iterdir()):
            backup_dir = Path(tempfile.mkdtemp(prefix="trustc_bak_"))
            for item in dest_p.iterdir():
                if item.is_dir():
                    shutil.copytree(item, backup_dir / item.name)
                else:
                    shutil.copy2(item, backup_dir / item.name)

        try:
            dest_p.mkdir(parents=True, exist_ok=True)
            # Clear destination safely
            for item in dest_p.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            # Copy staging files to destination
            for item in staging_dir.iterdir():
                if item.is_dir():
                    shutil.copytree(item, dest_p / item.name)
                else:
                    shutil.copy2(item, dest_p / item.name)

            # Post-publication verification of manifest
            dest_ok, dest_reason = verify_manifest(dest_p)
            if not dest_ok:
                raise BuildError(
                    f"Published artifact manifest verification failed: {dest_reason}",
                    exit_code=3,
                )

        except Exception as pub_exc:
            # Rollback from backup if available
            if backup_dir and backup_dir.exists():
                for item in dest_p.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                for item in backup_dir.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, dest_p / item.name)
                    else:
                        shutil.copy2(item, dest_p / item.name)
            raise pub_exc

        return build_success

    finally:
        # Clean up staging directory
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if backup_dir and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
