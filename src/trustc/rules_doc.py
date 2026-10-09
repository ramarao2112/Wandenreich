"""Rule documentation provider for CLI explain command and API documentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

DOCS_DIR = Path(__file__).resolve().parent / "rule_docs"

RULES_INFO: Dict[str, Dict[str, Any]] = {
    "TC-001": {
        "id": "TC-001",
        "name": "AUTH-REQUIRED",
        "shortDescription": "Endpoint missing authentication declaration",
        "fullDescription": (
            "Every endpoint must declare either 'auth: required' or 'auth: public'. "
            "Unauthenticated endpoints expose operations without verifying caller identity."
        ),
        "target": "endpoint",
        "helpUri": "https://github.com/ramarao2112/TrustC/blob/main/docs/rules/TC-001.md",
    },
    "TC-002": {
        "id": "TC-002",
        "name": "OWNERSHIP-CHECK",
        "shortDescription": "Invalid, unsupported, or contradictory authorization policy",
        "fullDescription": (
            "Enforces supported authorization policies per specification B4: role-based policies, "
            "wrong field equality predicates, public owned creation, authorize on owned creation, "
            "and public or waived User operations are rejected. Waivers apply to list, read, "
            "update, and delete operations on owned resources; creation always assigns caller."
        ),
        "target": "endpoint policy",
        "helpUri": "https://github.com/ramarao2112/TrustC/blob/main/docs/rules/TC-002.md",
    },
    "TC-003": {
        "id": "TC-003",
        "name": "SENSITIVE-LEAK",
        "shortDescription": "Sensitive or credential field returned without permitted exposure",
        "fullDescription": (
            "Credential fields (password_hash, tokens, keys) can never be returned in responses. "
            "Ordinary sensitive fields require explicit expose declarations in responses."
        ),
        "target": "returns projection",
        "helpUri": "https://github.com/ramarao2112/TrustC/blob/main/docs/rules/TC-003.md",
    },
    "TC-004": {
        "id": "TC-004",
        "name": "MASS-ASSIGNMENT",
        "shortDescription": "Server-controlled id, ownership, or credential field in request body",
        "fullDescription": (
            "Primary keys, ownership edges, and credential fields cannot be client-writable. "
            "Allowing these in request bodies permits mass assignment / parameter tampering."
        ),
        "target": "body fields",
        "helpUri": "https://github.com/ramarao2112/TrustC/blob/main/docs/rules/TC-004.md",
    },
    "TC-005": {
        "id": "TC-005",
        "name": "SECRET-SCOPE",
        "shortDescription": "Missing required DB_URL or JWT_SECRET environment secret reference",
        "fullDescription": (
            "Generated services require DB_URL and JWT_SECRET environment references. "
            "Declaring both ensures proper environment-variable configuration without hardcoding."
        ),
        "target": "secrets block",
        "helpUri": "https://github.com/ramarao2112/TrustC/blob/main/docs/rules/TC-005.md",
    },
}


def get_rule_doc(rule_id: str) -> str:
    """Retrieve raw markdown documentation for a rule."""
    normalized_id = rule_id.upper()
    if normalized_id not in RULES_INFO:
        supported = ", ".join(RULES_INFO.keys())
        raise KeyError(f"Unknown rule ID '{rule_id}'. Supported rules: {supported}")

    doc_file = DOCS_DIR / f"{normalized_id}.md"
    if doc_file.exists():
        return doc_file.read_text(encoding="utf-8")

    # Fallback to metadata summary
    info = RULES_INFO[normalized_id]
    return f"# {info['id']}: {info['name']}\n\n{info['fullDescription']}\n"
