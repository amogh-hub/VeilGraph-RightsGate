"""Run the frozen synthetic localization and metadata-signal benchmark."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import io
import json
import struct
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from app.rightsgate import ProvenanceVerdict
from app.rightsgate.evaluation import (
    ChallengeSignalEvaluationReport,
    SignalEvaluationCaseResult,
    StandardsAblation,
    binary_metrics,
    calibration_metrics,
)
from app.rightsgate.provenance import inspect_image_forensics
from app.rightsgate.rights import (
    ReferenceKind,
    RightsReferenceRegistry,
    build_registry_image,
    localize_reference_images,
)

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "competition"
    / "techgium10"
    / "evaluation"
    / "challenge-signals-sanity-v1.json"
)


def _ppm(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PPM")
    return buffer.getvalue()


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body))


def _stored_zlib(payload: bytes) -> bytes:
    """Encode a zlib stream with stored DEFLATE blocks for byte portability."""

    stream = bytearray(b"\x78\x01")
    offset = 0
    while offset < len(payload):
        size = min(65_535, len(payload) - offset)
        final = offset + size == len(payload)
        stream.append(1 if final else 0)
        stream.extend(struct.pack("<H", size))
        stream.extend(struct.pack("<H", size ^ 0xFFFF))
        stream.extend(payload[offset : offset + size])
        offset += size
    first = 1
    second = 0
    for value in payload:
        first = (first + value) % 65_521
        second = (second + first) % 65_521
    stream.extend(struct.pack(">I", second << 16 | first))
    return bytes(stream)


def _png(image: Image.Image, metadata: dict[str, str]) -> bytes:
    """Write a minimal uncompressed PNG independent of platform zlib choices."""

    normalized = image.convert("RGB")
    width, height = normalized.size
    pixels = normalized.tobytes()
    stride = width * 3
    scanlines = b"".join(
        b"\x00" + pixels[row * stride : (row + 1) * stride]
        for row in range(height)
    )
    chunks = [
        _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
        )
    ]
    chunks.extend(
        _png_chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1"))
        for key, value in sorted(metadata.items())
    )
    chunks.extend((_png_chunk(b"IDAT", _stored_zlib(scanlines)), _png_chunk(b"IEND", b"")))
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


def deterministic_mark(seed: int, *, width: int = 220, height: int = 160) -> Image.Image:
    image = Image.new("RGB", (width, height), (245, 245, 242))
    draw = ImageDraw.Draw(image)
    for index in range(12):
        x = (seed * 31 + index * 47) % (width - 30)
        y = (seed * 19 + index * 29) % (height - 24)
        color = (
            (seed * 23 + index * 61) % 220,
            (seed * 47 + index * 37) % 220,
            (seed * 71 + index * 17) % 220,
        )
        draw.rectangle(
            (x, y, x + 14 + index % 4 * 4, y + 10 + index % 3 * 5),
            outline=(20, 20, 20),
            fill=color,
            width=2,
        )
    for index in range(8):
        draw.line(
            (
                (seed * 7 + index * 27) % width,
                0,
                (seed * 13 + index * 41) % width,
                height - 1,
            ),
            fill=((index * 45) % 255, 35, (seed * 29) % 255),
            width=3,
        )
    return image


def localized_candidate(*, seed: int, scale_percent: int, x: int, y: int) -> bytes:
    candidate = Image.new("RGB", (700, 500), (220, 226, 232))
    mark = deterministic_mark(seed)
    mark = mark.resize(
        (mark.width * scale_percent // 100, mark.height * scale_percent // 100),
        Image.Resampling.NEAREST,
    )
    candidate.paste(mark, (x, y))
    return _ppm(candidate)


def unrelated_candidate(seed: int) -> bytes:
    generator = np.random.default_rng(seed)
    pixels = generator.integers(0, 256, size=(500, 700, 3), dtype=np.uint8)
    return _ppm(Image.fromarray(pixels, mode="RGB"))


def metadata_candidate(seed: int, label: str) -> bytes:
    metadata = {
        "AI_GENERATED": {
            "parameters": f"Stable Diffusion prompt=campaign-{seed}; steps=20; seed={seed}"
        },
        "PARTIALLY_GENERATED": {"Software": "Adobe Firefly generative fill"},
        "HUMAN_OR_UNKNOWN": (
            {"Software": "GIMP", "Comment": f"retouched fixture {seed}"}
            if seed % 2
            else {"Comment": "A lesson about stable diffusion of gases"}
        ),
    }[label]
    return _png(deterministic_mark(seed), metadata)


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_fingerprint(case: dict[str, Any], data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    if digest != case["expected_sha256"]:
        raise ValueError(f"case {case['case_id']} failed byte-fingerprint verification")
    return digest


def run(manifest_path: Path = DEFAULT_MANIFEST) -> ChallengeSignalEvaluationReport:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "veilgraph.rightsgate.signal-evaluation-manifest.v1":
        raise ValueError("unsupported signal evaluation manifest schema")

    reference_seed = int(manifest["reference"]["seed"])
    reference_data = _ppm(deterministic_mark(reference_seed))
    if hashlib.sha256(reference_data).hexdigest() != manifest["reference"]["expected_sha256"]:
        raise ValueError("reference failed byte-fingerprint verification")
    registry = RightsReferenceRegistry(
        registry_id=manifest["registry_id"],
        version=manifest["version"],
        references=(
            build_registry_image(
                reference_id=manifest["reference"]["reference_id"],
                kind=ReferenceKind.TRADEMARK,
                title="Synthetic governed visual reference",
                rights_holder="Synthetic evaluation fixture",
                data=reference_data,
                media_type="image/x-portable-pixmap",
                source_record_id="eval.source-localization",
            ),
        ),
    )

    localization_expected: list[bool] = []
    localization_predicted: list[bool] = []
    localization_scores: list[float] = []
    metadata_expected: list[bool] = []
    metadata_predicted: list[bool] = []
    metadata_scores: list[float] = []
    partial_correct: list[bool] = []
    results: list[SignalEvaluationCaseResult] = []
    for case in manifest["cases"]:
        if case["lane"] == "visual_localization":
            data = (
                localized_candidate(
                    seed=reference_seed,
                    scale_percent=int(case["scale_percent"]),
                    x=int(case["x"]),
                    y=int(case["y"]),
                )
                if case["expected_label"] == "MATCH"
                else unrelated_candidate(int(case["seed"]))
            )
            digest = _verify_fingerprint(case, data)
            match = localize_reference_images(
                data,
                asset_sha256=digest,
                registry=registry,
            )
            predicted = "MATCH" if match.candidate_reference_ids else "NO_MATCH"
            localization_expected.append(case["expected_label"] == "MATCH")
            localization_predicted.append(predicted == "MATCH")
            localization_scores.append(
                max((item.confidence for item in match.evidence), default=0.0)
                if match.candidate_reference_ids
                else 0.0
            )
        else:
            data = metadata_candidate(int(case["seed"]), case["expected_label"])
            digest = _verify_fingerprint(case, data)
            inspection = inspect_image_forensics(data, asset_sha256=digest)
            predicted = inspection.assessment.verdict.value
            expected_positive = case["expected_label"] != "HUMAN_OR_UNKNOWN"
            metadata_expected.append(expected_positive)
            metadata_predicted.append(
                inspection.assessment.verdict
                in {ProvenanceVerdict.AI_GENERATED, ProvenanceVerdict.PARTIALLY_GENERATED}
            )
            metadata_scores.append(
                inspection.assessment.confidence
                if inspection.assessment.verdict
                in {ProvenanceVerdict.AI_GENERATED, ProvenanceVerdict.PARTIALLY_GENERATED}
                else 0.0
            )
            if case["expected_label"] == "PARTIALLY_GENERATED":
                partial_correct.append(predicted == "PARTIALLY_GENERATED")
        results.append(
            SignalEvaluationCaseResult(
                case_id=case["case_id"],
                lane=case["lane"],
                expected_label=case["expected_label"],
                predicted_label=predicted,
                asset_sha256=digest,
                correct=(
                    predicted == case["expected_label"]
                    or (
                        case["expected_label"] == "HUMAN_OR_UNKNOWN"
                        and predicted == "UNKNOWN"
                    )
                ),
            )
        )

    combined_expected = localization_expected + metadata_expected
    combined_predicted = localization_predicted + metadata_predicted
    baseline_predictions = [False] * len(combined_expected)
    baseline_metrics = binary_metrics(combined_expected, baseline_predictions)
    full_metrics = binary_metrics(combined_expected, combined_predicted)
    return ChallengeSignalEvaluationReport(
        dataset_id=manifest["dataset_id"],
        manifest_sha256=_canonical_hash(manifest),
        registry_sha256=registry.commitment_sha256(),
        visual_localization=binary_metrics(localization_expected, localization_predicted),
        visual_localization_calibration=calibration_metrics(
            localization_expected,
            localization_scores,
        ),
        generative_metadata=binary_metrics(metadata_expected, metadata_predicted),
        generative_metadata_calibration=calibration_metrics(
            metadata_expected,
            metadata_scores,
        ),
        standards_ablation=StandardsAblation(
            sample_count=len(combined_expected),
            # These byte-stable fixtures intentionally contain neither C2PA
            # credentials nor invisible-watermark ground truth. That makes a
            # standards/watermark-only baseline an explicit all-abstain lane.
            credentials_or_watermark_evidence_cases=0,
            credentials_or_watermark_only=baseline_metrics,
            full_signal_pipeline=full_metrics,
            accuracy_lift=full_metrics.accuracy - baseline_metrics.accuracy,
            recall_lift=full_metrics.recall - baseline_metrics.recall,
        ),
        partial_edit_subtype_accuracy=(
            sum(partial_correct) / len(partial_correct) if partial_correct else 0
        ),
        cases=tuple(results),
        limitations=tuple(manifest["limitations"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.manifest).model_dump(mode="json", by_alias=True), indent=2))


if __name__ == "__main__":
    main()
