"""Stage 3 unit tests -- OASIS SARIF 2.1.0 output conformance and full schema validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, cast

import jsonschema
import pytest

from trustc.verifier import check_file, export_sarif

pytestmark = pytest.mark.stage3

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "trustc"
    / "schemas"
    / "sarif-schema-2.1.0.json"
)
OASIS_SARIF_SCHEMA_URI = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/"
    "master/Schemata/sarif-schema-2.1.0.json"
)


@pytest.fixture(scope="module")
def sarif_schema() -> Dict[str, Any]:
    """Load the published OASIS SARIF 2.1.0 JSON schema."""
    assert SCHEMA_PATH.exists(), f"Published SARIF schema missing at {SCHEMA_PATH}"
    return cast(Dict[str, Any], json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


class TestSarifOutput:
    def test_sarif_published_schema_metadata(self, sarif_schema: dict):
        """Confirm schema file corresponds to official published SARIF 2.1.0 standard."""
        assert sarif_schema.get("$id") == OASIS_SARIF_SCHEMA_URI
        assert "definitions" in sarif_schema
        assert "run" in sarif_schema["definitions"]
        assert "result" in sarif_schema["definitions"]

    def test_sarif_structure_and_schema_version(self):
        result = check_file(FIXTURES_DIR / "F1.trust")
        sarif = export_sarif(result, filename="F1.trust")

        assert sarif["$schema"] == OASIS_SARIF_SCHEMA_URI
        assert sarif["version"] == "2.1.0"
        assert "runs" in sarif
        assert len(sarif["runs"]) == 1

        run = sarif["runs"][0]
        driver = run["tool"]["driver"]
        assert driver["name"] == "trustc"
        assert driver["version"] == "0.1.0"
        assert len(driver["rules"]) == 5

        # Verify all five B5 rules are defined in the tool driver
        rule_ids = {r["id"] for r in driver["rules"]}
        assert rule_ids == {"TC-001", "TC-002", "TC-003", "TC-004", "TC-005"}

        for r_meta in driver["rules"]:
            assert "name" in r_meta
            assert "text" in r_meta["shortDescription"]
            assert "text" in r_meta["fullDescription"]
            assert r_meta["helpUri"].startswith("https://")

    def test_sarif_diagnostics_regions(self):
        result = check_file(FIXTURES_DIR / "F1.trust")
        sarif = export_sarif(result, filename="tests/fixtures/F1.trust")
        results = sarif["runs"][0]["results"]

        assert len(results) == 2
        r1, r2 = results

        assert r1["ruleId"] == "TC-001"
        assert r1["level"] == "error"
        loc1 = r1["locations"][0]["physicalLocation"]
        assert loc1["artifactLocation"]["uri"] == "tests/fixtures/F1.trust"
        region1 = loc1["region"]
        assert region1["startLine"] == 23
        assert region1["startColumn"] == 1

        assert r2["ruleId"] == "TC-003"
        assert r2["level"] == "error"
        loc2 = r2["locations"][0]["physicalLocation"]
        assert loc2["artifactLocation"]["uri"] == "tests/fixtures/F1.trust"
        region2 = loc2["region"]
        assert region2["startLine"] == 30
        assert region2["startColumn"] == 3

    def test_sarif_clean_results_empty(self):
        result = check_file(FIXTURES_DIR / "F2.trust")
        sarif = export_sarif(result, filename="tests/fixtures/F2.trust")
        results = sarif["runs"][0]["results"]
        assert len(results) == 0

    def test_full_sarif_schema_validation_f1(self, sarif_schema: dict):
        """Full validation of F1 SARIF output against published OASIS SARIF 2.1.0 schema."""
        result = check_file(FIXTURES_DIR / "F1.trust")
        sarif = export_sarif(result, filename="F1.trust")
        # jsonschema.validate raises ValidationError if non-conforming
        jsonschema.validate(instance=sarif, schema=sarif_schema)

    def test_full_sarif_schema_validation_all_canonical_fixtures(self, sarif_schema: dict):
        """Full validation of all canonical fixtures against published SARIF 2.1.0 schema."""
        test_fixtures = ["F1.trust", "F2.trust", "F3.trust", "F5.trust", "F6.trust", "F7.trust"]
        for fixture_name in test_fixtures:
            path = FIXTURES_DIR / fixture_name
            if not path.exists():
                continue
            result = check_file(path)
            sarif = export_sarif(result, filename=fixture_name)
            jsonschema.validate(instance=sarif, schema=sarif_schema)
