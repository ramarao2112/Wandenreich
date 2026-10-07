#!/usr/bin/env python3
"""Stage gate checker — runs registered tests for a given stage.

Usage: python scripts/check-stage.py <stage_number>

Stages 1-8 are valid. Unimplemented stages fail clearly.
"""

import subprocess
import sys


STAGE_MARKERS = {
    1: {
        "description": "Contracts, fixtures and packaging",
        "pytest_args": [
            "-m", "stage1",
            "tests/contract/",
            "tests/unit/test_fixtures.py",
        ],
    },
    # Stages 2-8 will be populated as implemented
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/check-stage.py <stage_number>", file=sys.stderr)
        return 2

    try:
        stage = int(sys.argv[1])
    except ValueError:
        print(f"Invalid stage number: {sys.argv[1]!r}", file=sys.stderr)
        return 2

    if stage < 1 or stage > 8:
        print(f"Stage must be 1-8, got {stage}", file=sys.stderr)
        return 2

    if stage not in STAGE_MARKERS:
        print(f"Stage {stage} is not yet implemented.", file=sys.stderr)
        print("Do not claim unimplemented stages pass.", file=sys.stderr)
        return 1

    config = STAGE_MARKERS[stage]
    print(f"=== Stage {stage}: {config['description']} ===")
    print()

    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short"] + config["pytest_args"]
    print(f"Running: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print()
        print(f"✅ Stage {stage} gates passed.")
    else:
        print()
        print(f"❌ Stage {stage} gates FAILED (exit {result.returncode}).")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
