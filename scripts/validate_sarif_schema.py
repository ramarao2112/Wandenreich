#!/usr/bin/env python3
"""Validates TrustC SARIF 2.1.0 output for canonical fixtures against the published OASIS schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from trustc.verifier import check_file, export_sarif

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SCHEMA_PATH = REPO_ROOT / "src" / "trustc" / "schemas" / "sarif-schema-2.1.0.json"
LOG_PATH = REPO_ROOT / "review-logs" / "stage-3" / "sarif-schema-validation.txt"


def main() -> int:
    print(f"Loading published OASIS SARIF 2.1.0 schema from: {SCHEMA_PATH}")
    if not SCHEMA_PATH.exists():
        print(f"ERROR: Schema not found at {SCHEMA_PATH}")
        return 1

    schema_data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_id = schema_data.get("$id", "N/A")
    schema_title = schema_data.get("title", "N/A")
    print(f"Schema ID:    {schema_id}")
    print(f"Schema Title: {schema_title}")

    fixtures = sorted(FIXTURES_DIR.glob("*.trust"))
    print(f"\nValidating {len(fixtures)} canonical fixtures against SARIF 2.1.0 schema...")

    results_log = []
    results_log.append("=" * 70)
    results_log.append("TrustC SARIF 2.1.0 Full Schema Validation Report")
    results_log.append(f"Published Schema Path: {SCHEMA_PATH}")
    results_log.append(f"Published Schema $id:  {schema_id}")
    results_log.append(f"Published Schema Title: {schema_title}")
    results_log.append("=" * 70)

    all_passed = True

    for fixture_path in fixtures:
        rel_name = fixture_path.name
        try:
            check_res = check_file(fixture_path)
            sarif = export_sarif(check_res, filename=rel_name)

            # Strict validation against schema
            jsonschema.validate(instance=sarif, schema=schema_data)

            num_diags = len(sarif["runs"][0]["results"])
            log_line = (
                f"[PASS] {rel_name:12s} - Validated against SARIF 2.1.0 schema "
                f"({num_diags} diagnostic results)"
            )
            print(log_line)
            results_log.append(log_line)
        except jsonschema.ValidationError as err:
            all_passed = False
            log_line = (
                f"[FAIL] {rel_name:12s} - Schema ValidationError: {err.message} "
                f"at path: {list(err.path)}"
            )
            print(log_line)
            results_log.append(log_line)
        except Exception as exc:
            all_passed = False
            log_line = f"[ERROR] {rel_name:12s} - Exception: {exc}"
            print(log_line)
            results_log.append(log_line)

    results_log.append("=" * 70)
    results_log.append(f"Overall Result: {'ALL PASSED' if all_passed else 'FAILURES DETECTED'}")
    results_log.append("=" * 70)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(results_log) + "\n", encoding="utf-8")
    print(f"\nValidation evidence retained at: {LOG_PATH}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
