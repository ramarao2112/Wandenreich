"""Artifact manifest generation and cryptographic verification.

Follows TrustSpec v3 Clarification 3:
- Binds buildId, specHash, specVersion, compilerVersion, and templateVersion.
- Hashes sorted relative executable paths and bytes using an unambiguous
  length-prefixed encoding.
- Excludes the manifest and report from the digest to avoid self-reference.
- Stored as `trustc-manifest.json` alongside `trustc-report.json`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

MANIFEST_SCHEMA_VERSION = 2
MANIFEST_ALGORITHM = "sha256-length-prefixed-v1"
EXCLUDED_FROM_DIGEST = frozenset({"trustc-report.json", "trustc-manifest.json"})


def compute_length_prefixed_digest(files_dict: Dict[str, bytes]) -> str:
    """Compute deterministic SHA-256 digest over sorted length-prefixed chunks.

    For each file path `p` and raw byte content `b`:
        chunk = f"{len(p)}:{p}:{len(b)}:".encode("utf-8") + b
    Concatenated in ascending lexicographical order of POSIX relative paths.
    """
    hasher = hashlib.sha256()
    for rel_path in sorted(files_dict.keys()):
        if rel_path in EXCLUDED_FROM_DIGEST:
            continue
        content_bytes = files_dict[rel_path]
        header = f"{len(rel_path)}:{rel_path}:{len(content_bytes)}:".encode("utf-8")
        hasher.update(header)
        hasher.update(content_bytes)
    return hasher.hexdigest()


def generate_manifest(
    files_dict: Dict[str, bytes],
    build_id: str,
    spec_hash: str,
    spec_version: int,
    compiler_version: str,
    template_version: str,
) -> Tuple[str, Dict[str, Any]]:
    """Generate canonical `trustc-manifest.json` content and data dict."""
    digest = compute_length_prefixed_digest(files_dict)

    file_entries: List[Dict[str, Any]] = []
    for rel_path in sorted(files_dict.keys()):
        if rel_path in EXCLUDED_FROM_DIGEST:
            continue
        content_bytes = files_dict[rel_path]
        file_sha256 = hashlib.sha256(content_bytes).hexdigest()
        file_entries.append({
            "path": rel_path.replace("\\", "/"),
            "bytes": len(content_bytes),
            "sha256": file_sha256,
        })

    manifest_data: Dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "buildId": build_id,
        "specHash": spec_hash,
        "specVersion": spec_version,
        "compilerVersion": compiler_version,
        "templateVersion": template_version,
        "algorithm": MANIFEST_ALGORITHM,
        "artifactDigest": digest,
        "files": file_entries,
    }

    manifest_json = json.dumps(manifest_data, indent=2) + "\n"
    return manifest_json, manifest_data


def verify_manifest(target_dir: Path | str) -> Tuple[bool, str]:
    """Cryptographically verify the artifact manifest of a generated build directory.

    Returns:
        (True, "Manifest verified") if all files match exactly.
        (False, "<reason>") on any discrepancy, missing file, or tampering.
    """
    p = Path(target_dir).resolve()
    manifest_path = p / "trustc-manifest.json"
    if not manifest_path.is_file():
        return False, "Missing trustc-manifest.json"

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"Invalid JSON in trustc-manifest.json: {exc}"

    expected_digest = manifest_data.get("artifactDigest")
    if not expected_digest:
        return False, "Missing artifactDigest in manifest"

    manifest_paths: set[str] = set()
    for entry in manifest_data.get("files", []):
        rel_path = entry.get("path")
        if not rel_path:
            return False, "Invalid file entry without path in manifest"
        manifest_paths.add(rel_path)
        file_path = p / rel_path
        if not file_path.is_file():
            return False, f"Manifest file missing from disk: {rel_path}"

        content_bytes = file_path.read_bytes()
        actual_sha256 = hashlib.sha256(content_bytes).hexdigest()
        if actual_sha256 != entry.get("sha256"):
            return False, (
                f"File SHA-256 mismatch for {rel_path}: "
                f"expected {entry.get('sha256')}, got {actual_sha256}"
            )
        if len(content_bytes) != entry.get("bytes"):
            return False, (
                f"File byte count mismatch for {rel_path}: "
                f"expected {entry.get('bytes')}, got {len(content_bytes)}"
            )

    # Check for unexpected/tampered files on disk
    files_on_disk: Dict[str, bytes] = {}
    for item in p.rglob("*"):
        if item.is_file():
            if "__pycache__" in item.parts or item.suffix in (".pyc", ".pyo"):
                continue
            rel_posix = item.relative_to(p).as_posix()
            if rel_posix in EXCLUDED_FROM_DIGEST:
                continue
            if rel_posix not in manifest_paths:
                return False, f"Unexpected unmanifested file on disk: {rel_posix}"
            files_on_disk[rel_posix] = item.read_bytes()

    # Recompute length-prefixed digest
    recomputed_digest = compute_length_prefixed_digest(files_on_disk)
    if recomputed_digest != expected_digest:
        return False, (
            f"Artifact digest mismatch: "
            f"expected {expected_digest}, recomputed {recomputed_digest}"
        )

    return True, "Manifest verified"
