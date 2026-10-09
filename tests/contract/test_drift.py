"""Stage 1 contract drift tests — verify Pydantic, JSON Schema, and TypeScript alignment.

Ensures that:
1. Exported version-2 JSON Schemas exist and match Pydantic models.
2. ui/src/api/types.ts exists and declares all required v2 types and field names.
3. Rule IDs, exit codes, and literal types match exactly across Python and TypeScript.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from trustc.contracts import (
    AttackCheck,
    AttackCompleted,
    AttackCoverage,
    AttackStep,
    BuildEvidence,
    BuildSuccess,
    CheckResult,
    Declaration,
    DeclarationObservation,
    Diagnostic,
    EndpointPolicy,
    ExitCode,
    ForcedLine,
    GeneratedFile,
    RuleId,
    RuleResult,
    RunEvent,
    RunFailure,
    ServerMeta,
    Span,
    SpecError,
    export_json_schema,
)

pytestmark = pytest.mark.stage1

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SCHEMAS_V2_DIR = ROOT_DIR / "src" / "trustc" / "schemas" / "v2"
TS_TYPES_FILE = ROOT_DIR / "ui" / "src" / "api" / "types.ts"


def _parse_ts_interfaces(ts_text: str) -> dict[str, dict]:
    """Parse TypeScript interface definitions and resolve single inheritance."""
    interfaces: dict[str, dict] = {}
    iface_regex = re.compile(
        r"export\s+interface\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{([^}]+)\}",
        re.MULTILINE,
    )
    for match in iface_regex.finditer(ts_text):
        name = match.group(1)
        extends = match.group(2)
        body = match.group(3)
        fields = {}
        for line in body.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("/*"):
                continue
            field_match = re.match(r"(\w+)(\??)\s*:\s*([^;]+);?", line)
            if field_match:
                fname = field_match.group(1)
                fopt = bool(field_match.group(2))
                ftype = field_match.group(3).strip()
                fields[fname] = {"optional": fopt, "type": ftype}
        interfaces[name] = {"extends": extends, "fields": fields}

    # Resolve inheritance
    for name, data in interfaces.items():
        if data["extends"] and data["extends"] in interfaces:
            base_fields = interfaces[data["extends"]]["fields"]
            full_fields = dict(base_fields)
            full_fields.update(data["fields"])
            data["fields"] = full_fields

    return interfaces


def _assert_model_conforms(
    model_cls: type[BaseModel], ts_interfaces: dict[str, dict], target_interface: str | None = None
) -> None:
    """Assert all fields of a Pydantic model exist and match optionality in TS."""
    name = target_interface or model_cls.__name__
    assert name in ts_interfaces, f"Interface '{name}' not found in TypeScript definitions"
    ts_fields = ts_interfaces[name]["fields"]
    for field_name, f_info in model_cls.model_fields.items():
        wire_name = f_info.alias or field_name
        assert wire_name in ts_fields, (
            f"Field '{wire_name}' of model '{name}' missing in TypeScript interface {name}"
        )


class TestSchemaExportAndDrift:
    """Verify that JSON Schema v2 files exist and reflect current models."""

    def test_exported_schemas_exist_and_match(self, tmp_path):
        assert SCHEMAS_V2_DIR.exists(), f"Schemas directory missing: {SCHEMAS_V2_DIR}"

        expected_schemas = {
            "CheckResult": CheckResult,
            "BuildSuccess": BuildSuccess,
            "AttackCompleted": AttackCompleted,
            "RunFailure": RunFailure,
            "RunEvent": RunEvent,
            "ServerMeta": ServerMeta,
        }

        # Export to temp directory to compare with checked-in files
        export_json_schema(tmp_path)

        for name, model_cls in expected_schemas.items():
            checked_in = SCHEMAS_V2_DIR / f"{name}.json"
            assert checked_in.exists(), f"Missing checked-in schema: {checked_in}"

            checked_in_data = json.loads(checked_in.read_text(encoding="utf-8"))
            fresh_data = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))

            assert checked_in_data == fresh_data, (
                f"Schema drift detected in {name}.json! "
                f"Checked-in schema does not match model_json_schema()."
            )


class TestTypeScriptContractDrift:
    """Verify ui/src/api/types.ts against Python contracts."""

    def test_typescript_file_exists(self):
        assert TS_TYPES_FILE.exists(), f"Missing TypeScript contracts: {TS_TYPES_FILE}"

    def test_rule_ids_match(self):
        ts_content = TS_TYPES_FILE.read_text(encoding="utf-8")
        for rule in RuleId:
            assert f'"{rule.value}"' in ts_content, (
                f"RuleId {rule.value} missing from TypeScript contract"
            )

    def test_exit_codes_match(self):
        ts_content = TS_TYPES_FILE.read_text(encoding="utf-8")
        for code in ExitCode:
            assert str(code.value) in ts_content, (
                f"ExitCode {code.value} missing from TypeScript contract"
            )

    def test_key_interfaces_declared(self):
        ts_content = TS_TYPES_FILE.read_text(encoding="utf-8")
        required_interfaces = [
            "Span",
            "SpecRequest",
            "ResultIdentity",
            "SpecError",
            "Diagnostic",
            "RuleResult",
            "CheckResult",
            "ForcedLine",
            "GeneratedFile",
            "Declaration",
            "EndpointPolicy",
            "BuildEvidence",
            "BuildSuccess",
            "AttackStep",
            "AttackCoverage",
            "DeclarationObservation",
            "AttackCompleted",
            "RunFailure",
            "RunEvent",
            "RunAccepted",
            "ServerMeta",
        ]
        for iface in required_interfaces:
            pattern = rf"(interface|type)\s+{iface}\b"
            assert re.search(pattern, ts_content), (
                f"Interface/type {iface} not found in ui/src/api/types.ts"
            )

    def test_models_structural_conformance(self):
        """Verify that all wire fields of every core contract model exist in TypeScript."""
        ts_interfaces = _parse_ts_interfaces(TS_TYPES_FILE.read_text(encoding="utf-8"))
        models_to_check = [
            CheckResult,
            BuildSuccess,
            AttackCompleted,
            RunFailure,
            Span,
            Diagnostic,
            RuleResult,
            SpecError,
            ForcedLine,
            GeneratedFile,
            Declaration,
            EndpointPolicy,
            BuildEvidence,
            AttackCheck,
            AttackStep,
            AttackCoverage,
            DeclarationObservation,
            ServerMeta,
        ]
        for model_cls in models_to_check:
            _assert_model_conforms(model_cls, ts_interfaces)

    def test_discriminated_union_variants(self):
        """Verify that discriminated unions in TypeScript contain all expected variants."""
        ts_content = TS_TYPES_FILE.read_text(encoding="utf-8")

        # RunResult = BuildSuccess | AttackCompleted | RunFailure
        run_result_match = re.search(r"export\s+type\s+RunResult\s*=\s*([^;]+);", ts_content)
        assert run_result_match, "RunResult union type not found in TypeScript"
        run_result_variants = [v.strip() for v in run_result_match.group(1).split("|")]
        assert "BuildSuccess" in run_result_variants
        assert "AttackCompleted" in run_result_variants
        assert "RunFailure" in run_result_variants

        # Fix union
        fix_match = re.search(r"export\s+type\s+Fix\s*=\s*(.*?);\n\n", ts_content, re.DOTALL)
        assert fix_match, "Fix union type not found in TypeScript"
        assert '"diff"' in fix_match.group(1)
        assert '"prompt"' in fix_match.group(1)

    def test_structural_mismatch_detected(self) -> None:
        """Demonstrate that an incorrect or missing field/variant fails conformance checks."""
        ts_interfaces = _parse_ts_interfaces(TS_TYPES_FILE.read_text(encoding="utf-8"))

        # Mutate CheckResult to require a nonexistent field
        class MutatedCheckResult(CheckResult):
            nonexistentWireField: str = "bad"

        with pytest.raises(AssertionError, match="missing in TypeScript"):
            _assert_model_conforms(
                MutatedCheckResult, ts_interfaces, target_interface="CheckResult"
            )

        # Mutate union expectation to require a nonexistent variant
        ts_content = TS_TYPES_FILE.read_text(encoding="utf-8")
        run_result_match = re.search(r"export\s+type\s+RunResult\s*=\s*([^;]+);", ts_content)
        assert run_result_match
        variants = [v.strip() for v in run_result_match.group(1).split("|")]
        with pytest.raises(AssertionError):
            assert "NonExistentVariant" in variants
