#!/usr/bin/env python3
"""Build and self-verify the signed, sanitized RightsGate competition archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.security.release_package import build_release_package, verify_release_package_bytes

EXPECTED_SIGNER_FINGERPRINT = "c0cf1c7413d387b59afb0a3ac091c3b4a43b8c33a227f7c1697254d16f8192c6"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "competition/releases/veilgraph-rightsgate-techgium-v0.6.0.zip",
    )
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()

    package, manifest = build_release_package(
        ROOT,
        phase="techgium10-rightsgate",
        sign_manifest=True,
    )
    verification = verify_release_package_bytes(
        package, expected_signer_fingerprint=EXPECTED_SIGNER_FINGERPRINT
    )
    if not verification.get("valid") or not verification.get("signed"):
        raise SystemExit(f"Signed release self-verification failed: {verification}")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(package)
    report = {
        "schema": "veilgraph.rightsgate.competition-release-result.v1",
        "output": str(arguments.output),
        "sha256": hashlib.sha256(package).hexdigest(),
        "size_bytes": len(package),
        "entry_count": manifest["entry_count"],
        "signer_fingerprint": verification["signer_fingerprint"],
        "verification": verification,
    }
    if arguments.report is not None:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
