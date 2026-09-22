"""Reproduce bounded C2PA interoperability metrics on pinned official fixtures.

This is an integrity-validation evaluation, not a general AI-media detector test.
Fixture binaries stay outside the repository; --fetch is explicitly opt-in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import urllib.request
from pathlib import Path
from typing import Any

import c2pa

from app.rightsgate import ProvenanceVerdict
from app.rightsgate.evaluation import binary_metrics
from app.rightsgate.provenance.c2pa import verify_c2pa

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "competition"
    / "techgium10"
    / "evaluation"
    / "c2pa-interoperability-v1.json"
)
SCHEMA = "veilgraph.rightsgate.c2pa-interoperability-manifest.v1"
REPORT_SCHEMA = "veilgraph.rightsgate.c2pa-interoperability-report.v1"
MAX_FIXTURE_BYTES = 8 * 1024 * 1024


def _wilson_interval(successes: int, total: int) -> list[float]:
    """Two-sided 95% Wilson score interval for a binomial proportion."""

    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("invalid interval counts")
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported C2PA interoperability manifest schema")
    if manifest.get("source_repository") != "https://github.com/c2pa-org/public-testfiles":
        raise ValueError("unexpected fixture source repository")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("source_commit", "")):
        raise ValueError("fixture source must be pinned to a complete commit")
    if manifest.get("source_directory") != "legacy/1.4/image/jpeg":
        raise ValueError("unexpected fixture source directory")
    if manifest.get("source_license") != "CC-BY-SA-4.0":
        raise ValueError("unexpected fixture source license")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest must declare at least one case")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case is not an object")
        name = case.get("case_id")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]+\.jpg", name):
            raise ValueError("case filename must be a bare JPEG name")
        if name in seen:
            raise ValueError(f"duplicate case: {name}")
        seen.add(name)
        if not re.fullmatch(r"[0-9a-f]{64}", case.get("sha256", "")):
            raise ValueError(f"invalid SHA-256 for {name}")
        if case.get("expected_validation") not in {"ABSENT", "VALID", "INVALID"}:
            raise ValueError(f"invalid validation label for {name}")
        if case.get("expected_tamper") not in (True, False, None):
            raise ValueError(f"invalid tamper label for {name}")
    return manifest, hashlib.sha256(raw).hexdigest()


def _fixture_bytes(
    case: dict[str, Any], manifest: dict[str, Any], *, fixture_dir: Path | None
) -> bytes:
    if fixture_dir is None:
        url = (
            "https://raw.githubusercontent.com/c2pa-org/public-testfiles/"
            f"{manifest['source_commit']}/{manifest['source_directory']}/{case['case_id']}"
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(MAX_FIXTURE_BYTES + 1)
    else:
        path = fixture_dir / case["case_id"]
        if path.stat().st_size > MAX_FIXTURE_BYTES:
            raise ValueError(f"fixture exceeds byte limit: {case['case_id']}")
        data = path.read_bytes()
    if len(data) > MAX_FIXTURE_BYTES:
        raise ValueError(f"fixture exceeds byte limit: {case['case_id']}")
    if hashlib.sha256(data).hexdigest() != case["sha256"]:
        raise ValueError(f"fixture SHA-256 mismatch: {case['case_id']}")
    return data


def run(
    manifest_path: Path = DEFAULT_MANIFEST, *, fixture_dir: Path | None = None
) -> dict[str, Any]:
    """Evaluate fetched or locally supplied exact bytes and retain raw outcomes."""

    manifest, manifest_sha256 = _load_manifest(manifest_path)
    cases: list[dict[str, Any]] = []
    tamper_expected: list[bool] = []
    tamper_predicted: list[bool] = []
    for case in manifest["cases"]:
        data = _fixture_bytes(case, manifest, fixture_dir=fixture_dir)
        result = verify_c2pa(data, "image/jpeg", case["sha256"])
        validation_state = (
            result.evidence[0].attributes.get("validation_state", "")
            if result.evidence
            else ""
        )
        if result.component.state.value != "AVAILABLE":
            predicted_validation = "UNAVAILABLE"
        elif not result.evidence:
            predicted_validation = "ABSENT"
        elif validation_state.casefold() in {"valid", "trusted"}:
            predicted_validation = "VALID"
        elif validation_state.casefold() == "invalid":
            predicted_validation = "INVALID"
        else:
            predicted_validation = "UNKNOWN"
        predicted_tamper = result.assessment.verdict == ProvenanceVerdict.TAMPERED
        if case["expected_tamper"] is not None:
            tamper_expected.append(case["expected_tamper"])
            tamper_predicted.append(predicted_tamper)
        cases.append(
            {
                "case_id": case["case_id"],
                "asset_sha256": case["sha256"],
                "expected_validation": case["expected_validation"],
                "predicted_validation": predicted_validation,
                "sdk_validation_state": validation_state,
                "validation_correct": predicted_validation == case["expected_validation"],
                "expected_tamper": case["expected_tamper"],
                "predicted_tamper": predicted_tamper,
                "failure_codes": (
                    result.evidence[0].attributes.get("failure_codes", "").split(",")
                    if result.evidence and result.evidence[0].attributes.get("failure_codes")
                    else []
                ),
            }
        )
    tamper_metrics = binary_metrics(tamper_expected, tamper_predicted)
    negative_count = tamper_metrics.true_negative + tamper_metrics.false_positive
    return {
        "schema": REPORT_SCHEMA,
        "dataset_id": manifest["dataset_id"],
        "manifest_sha256": manifest_sha256,
        "source_commit": manifest["source_commit"],
        "source_license": manifest["source_license"],
        "c2pa_sdk_version": c2pa.__version__,
        "case_count": len(cases),
        "validation_correct": sum(item["validation_correct"] for item in cases),
        "validation_accuracy": sum(item["validation_correct"] for item in cases) / len(cases),
        "validation_accuracy_95ci": _wilson_interval(
            sum(item["validation_correct"] for item in cases), len(cases)
        ),
        "tamper_scored_count": len(tamper_expected),
        "tamper_excluded_count": len(cases) - len(tamper_expected),
        "tamper": tamper_metrics.model_dump(mode="json"),
        "tamper_false_positive_rate_95ci": _wilson_interval(
            tamper_metrics.false_positive, negative_count
        ),
        "cases": cases,
        "limitations": [
            "This is a small, selected JPEG C2PA interoperability set, not a representative media-distribution sample.",
            "VALID means structurally valid under this SDK; these test certificates are not trusted publisher identities.",
            "Tamper labels cover documented cryptographic mismatch fixtures only; the missing-claim fixture is excluded from binary tamper metrics.",
            "These metrics do not evaluate AI-generation attribution, watermark families, rights clearance or deployment policy.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    fixture_source = parser.add_mutually_exclusive_group(required=True)
    fixture_source.add_argument("--fixture-dir", type=Path)
    fixture_source.add_argument("--fetch", action="store_true")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    args = parser.parse_args()
    report = run(args.manifest, fixture_dir=args.fixture_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
