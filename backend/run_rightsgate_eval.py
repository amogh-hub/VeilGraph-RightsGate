"""Run the frozen synthetic rights-retrieval sanity benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from app.rightsgate import RightsVerdict
from app.rightsgate.evaluation import (
    EvaluationCaseResult,
    RightsRetrievalEvaluationReport,
    binary_metrics,
)
from app.rightsgate.rights import (
    ReferenceKind,
    RightsReferenceRegistry,
    build_registry_image,
    match_reference_image,
)

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "competition"
    / "techgium10"
    / "evaluation"
    / "rights-retrieval-sanity-v1.json"
)


def deterministic_ppm(seed: int, *, width: int = 64, height: int = 48, scale: int = 1) -> bytes:
    """Generate cross-platform byte-stable synthetic PPM media."""

    if seed < 1 or width < 1 or height < 1 or scale < 1:
        raise ValueError("generator inputs must be positive")
    header = f"P6\n{width * scale} {height * scale}\n255\n".encode("ascii")
    pixels = bytearray()
    for output_y in range(height * scale):
        y = output_y // scale
        for output_x in range(width * scale):
            x = output_x // scale
            value = (
                x * (seed * 2 + 3)
                + y * (seed * 3 + 5)
                + (x * y * (seed % 5 + 1)) // 23
                + seed * 17
            ) % 256
            pixels.extend(
                (
                    value,
                    (value * (seed % 7 + 1)) % 256,
                    (255 - value + seed * 11) % 256,
                )
            )
    return header + bytes(pixels)


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run(manifest_path: Path = DEFAULT_MANIFEST) -> RightsRetrievalEvaluationReport:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "veilgraph.rightsgate.evaluation-manifest.v1":
        raise ValueError("unsupported evaluation manifest schema")
    generator = manifest["generator"]
    width = int(generator["width"])
    height = int(generator["height"])
    references = []
    reference_hashes: set[str] = set()
    for item in manifest["references"]:
        data = deterministic_ppm(int(item["seed"]), width=width, height=height)
        asset_sha256 = hashlib.sha256(data).hexdigest()
        if asset_sha256 != item["expected_sha256"]:
            raise ValueError(
                f"reference {item['reference_id']} failed byte-fingerprint verification"
            )
        reference_hashes.add(asset_sha256)
        references.append(
            build_registry_image(
                reference_id=item["reference_id"],
                kind=ReferenceKind.COPYRIGHTED_WORK,
                title=f"Synthetic evaluation reference {item['seed']}",
                rights_holder="Synthetic evaluation fixture",
                data=data,
                media_type="image/x-portable-pixmap",
                source_record_id=f"eval.source-{int(item['seed']):02d}",
            )
        )
    registry = RightsReferenceRegistry(
        registry_id=manifest["registry_id"],
        version=manifest["version"],
        references=tuple(references),
    )

    expected: list[bool] = []
    exact_outputs: list[bool] = []
    perceptual_outputs: list[bool] = []
    case_results: list[EvaluationCaseResult] = []
    threshold = int(manifest["max_hamming_distance"])
    for item in manifest["cases"]:
        data = deterministic_ppm(
            int(item["seed"]),
            width=width,
            height=height,
            scale=int(item["scale"]),
        )
        asset_sha256 = hashlib.sha256(data).hexdigest()
        if asset_sha256 != item["expected_sha256"]:
            raise ValueError(f"case {item['case_id']} failed byte-fingerprint verification")
        exact_prediction = asset_sha256 in reference_hashes
        match = match_reference_image(
            data,
            asset_sha256=asset_sha256,
            registry=registry,
            max_hamming_distance=threshold,
        )
        perceptual_prediction = match.assessment.verdict == RightsVerdict.POTENTIAL_EXPOSURE
        label = bool(item["expected_match"])
        expected.append(label)
        exact_outputs.append(exact_prediction)
        perceptual_outputs.append(perceptual_prediction)
        case_results.append(
            EvaluationCaseResult(
                case_id=item["case_id"],
                expected_match=label,
                asset_sha256=asset_sha256,
                exact_only_prediction=exact_prediction,
                perceptual_prediction=perceptual_prediction,
            )
        )

    return RightsRetrievalEvaluationReport(
        dataset_id=manifest["dataset_id"],
        manifest_sha256=_canonical_hash(manifest),
        registry_sha256=registry.commitment_sha256(),
        max_hamming_distance=threshold,
        exact_only=binary_metrics(expected, exact_outputs),
        perceptual=binary_metrics(expected, perceptual_outputs),
        cases=tuple(case_results),
        limitations=tuple(manifest["limitations"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    arguments = parser.parse_args()
    report = run(arguments.manifest)
    print(json.dumps(report.model_dump(mode="json", by_alias=True), indent=2))


if __name__ == "__main__":
    main()
