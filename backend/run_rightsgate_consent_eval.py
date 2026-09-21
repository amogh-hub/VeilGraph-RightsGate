"""Reproduce the frozen synthetic watermark and consent-control sanity set."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from app.rightsgate.contracts import AssessmentContext, ProvenanceVerdict
from app.rightsgate.evaluation import binary_metrics
from app.rightsgate.provenance import (
    VisibleWatermarkRegistry,
    build_visible_watermark_profile,
    verify_visible_watermarks,
)
from app.rightsgate.rights import (
    ConsentGrant,
    ConsentRegistry,
    analyze_likeness_consent,
    analyze_voice_consent,
    build_likeness_template,
    build_voice_template,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = (
    ROOT / "competition" / "techgium10" / "evaluation" / "watermark-consent-sanity-v1.json"
)
DEFAULT_RESULTS = (
    ROOT
    / "competition"
    / "techgium10"
    / "evaluation"
    / "watermark-consent-sanity-results-v1.json"
)
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _ppm(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PPM")
    return buffer.getvalue()


def _pattern(seed: int, size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, (235, 238, 242))
    draw = ImageDraw.Draw(image)
    for index in range(18):
        x = (seed * 31 + index * 19) % max(1, width - 12)
        y = (seed * 17 + index * 23) % max(1, height - 12)
        color = (
            (seed * 11 + index * 37) % 230,
            (seed * 29 + index * 41) % 230,
            (seed * 47 + index * 13) % 230,
        )
        draw.rectangle((x, y, min(width - 1, x + 9), min(height - 1, y + 9)), fill=color)
        draw.line((0, y, width - 1, (y + seed + index * 3) % height), fill=(20, 20, 20))
    return image


def _watermark_asset(seed: int, *, tampered: bool) -> bytes:
    background = _pattern(seed, (128, 128))
    template = _pattern(77, (32, 32))
    background.paste(ImageOps.invert(template) if tampered else template, (96, 96))
    return _ppm(background)


def _likeness_asset(seed: int, *, matched: bool) -> bytes:
    reference = _pattern(101, (128, 128))
    if matched:
        size = 128 + (seed % 4) * 16
        return _ppm(reference.resize((size, size), Image.Resampling.NEAREST))
    return _ppm(_pattern(seed, (128, 128)))


def _voice_asset(seed: int, *, matched: bool) -> bytes:
    sample_rate = 16_000
    frequency = 440.0 if matched else 760.0 + seed * 13.0
    amplitude = 0.22 + (seed % 6) * 0.05
    phase = (seed % 5) * 0.37
    samples = [
        int(
            32767
            * amplitude
            * (
                0.82 * math.sin(2 * math.pi * frequency * index / sample_rate + phase)
                + 0.18 * math.sin(4 * math.pi * frequency * index / sample_rate + phase / 2)
            )
        )
        for index in range(sample_rate)
    ]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return buffer.getvalue()


def _case_data(case: dict[str, Any]) -> bytes:
    lane = case["lane"]
    positive = bool(case["expected_positive"])
    seed = int(case["seed"])
    if lane == "visible_watermark_tamper":
        return _watermark_asset(seed, tampered=positive)
    if lane == "likeness_reference":
        return _likeness_asset(seed, matched=positive)
    if lane == "voice_reference":
        return _voice_asset(seed, matched=positive)
    raise ValueError(f"unsupported lane: {lane}")


def initialize_manifest() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for lane, positive_prefix, negative_prefix in (
        ("visible_watermark_tamper", "tampered", "intact"),
        ("likeness_reference", "match", "nonmatch"),
        ("voice_reference", "match", "nonmatch"),
    ):
        for expected, prefix, offset in (
            (True, positive_prefix, 100),
            (False, negative_prefix, 200),
        ):
            for index in range(1, 17):
                case = {
                    "case_id": f"{lane}-{prefix}-{index:02d}",
                    "lane": lane,
                    "expected_positive": expected,
                    "seed": offset + index,
                }
                data = _case_data(case)
                case["expected_sha256"] = hashlib.sha256(data).hexdigest()
                if expected and lane in {"likeness_reference", "voice_reference"}:
                    case["expected_consent_conflict"] = index > 8
                cases.append(case)
    return {
        "schema": "veilgraph.rightsgate.watermark-consent-evaluation-manifest.v1",
        "dataset_id": "rightsgate.synthetic-watermark-consent-sanity.v1",
        "version": "1.0.0",
        "frozen": True,
        "generator": {
            "id": "deterministic-ppm-pcm-reference-controls-v1",
            "watermark_seed": 77,
            "likeness_seed": 101,
            "voice_frequency_hz": 440,
        },
        "references": {
            "watermark_sha256": hashlib.sha256(_ppm(_pattern(77, (32, 32)))).hexdigest(),
            "likeness_sha256": hashlib.sha256(_ppm(_pattern(101, (128, 128)))).hexdigest(),
            "voice_sha256": hashlib.sha256(_voice_asset(0, matched=True)).hexdigest(),
        },
        "cases": cases,
        "limitations": [
            "This is deterministic synthetic sanity evidence, not a representative real-world biometric or watermark benchmark.",
            "Visible-watermark positives use one enrolled region with inversion attacks; arbitrary invisible watermark families are not assessed.",
            "Likeness positives reuse one synthetic enrolled image under nearest-neighbour scale changes; this is not face recognition.",
            "Voice positives reuse one synthetic harmonic source under gain and phase changes; this is not speaker identification.",
            "Accuracy and false-positive rates from this set must not be generalized beyond these declared transformations.",
        ],
    }


def _context(*, conflict: bool = False) -> AssessmentContext:
    return AssessmentContext(
        policy_id="policy.synthetic-eval",
        policy_version="1",
        intended_use="public campaign",
        channel="web",
        audience="general",
        territories=("US" if conflict else "IN",),
        brand_profile="acme",
    )


def run(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "veilgraph.rightsgate.watermark-consent-evaluation-manifest.v1":
        raise ValueError("unsupported watermark/consent evaluation manifest schema")
    watermark_reference = _ppm(_pattern(77, (32, 32)))
    likeness_reference = _ppm(_pattern(101, (128, 128)))
    voice_reference = _voice_asset(0, matched=True)
    references = {
        "watermark_sha256": hashlib.sha256(watermark_reference).hexdigest(),
        "likeness_sha256": hashlib.sha256(likeness_reference).hexdigest(),
        "voice_sha256": hashlib.sha256(voice_reference).hexdigest(),
    }
    if references != manifest["references"]:
        raise ValueError("frozen reference fingerprints do not reproduce")

    grant = ConsentGrant(
        consent_id="consent.synthetic-subject",
        source_record_id="consent-record.synthetic-subject",
        subject_id="person.synthetic-subject",
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        territories=("IN",),
        channels=("web",),
        intended_uses=("public campaign",),
    )
    watermark_registry = VisibleWatermarkRegistry(
        registry_id="registry.synthetic-watermarks",
        version="1",
        profiles=(
            build_visible_watermark_profile(
                profile_id="watermark.synthetic-001",
                source_record_id="brand-record.synthetic-001",
                brand_profiles=("acme",),
                normalized_bbox=(0.75, 0.75, 1.0, 1.0),
                template_data=watermark_reference,
                max_hamming_distance=4,
            ),
        ),
    )
    consent_registry = ConsentRegistry(
        registry_id="registry.synthetic-consents",
        version="1",
        likeness_templates=(
            build_likeness_template(
                template_id="likeness.synthetic-001",
                reference_data=likeness_reference,
                consent=grant,
                max_hamming_distance=9,
            ),
        ),
        voice_templates=(
            build_voice_template(
                template_id="voice.synthetic-001",
                reference_data=voice_reference,
                consent=grant,
                minimum_similarity=0.99,
            ),
        ),
    )
    expected: dict[str, list[bool]] = {
        "visible_watermark_tamper": [],
        "likeness_reference": [],
        "voice_reference": [],
    }
    predicted = {key: [] for key in expected}
    consent_expected: list[bool] = []
    consent_predicted: list[bool] = []
    case_results: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        data = _case_data(case)
        digest = hashlib.sha256(data).hexdigest()
        if digest != case["expected_sha256"]:
            raise ValueError(f"case {case['case_id']} failed byte-fingerprint verification")
        lane = case["lane"]
        expected_positive = bool(case["expected_positive"])
        expected[lane].append(expected_positive)
        conflict = bool(case.get("expected_consent_conflict", False))
        if lane == "visible_watermark_tamper":
            result = verify_visible_watermarks(
                data,
                asset_sha256=digest,
                context=_context(),
                registry=watermark_registry,
            )
            prediction = result.assessment.verdict == ProvenanceVerdict.TAMPERED
        elif lane == "likeness_reference":
            result = analyze_likeness_consent(
                data,
                asset_sha256=digest,
                context=_context(conflict=conflict),
                registry=consent_registry,
                assessed_at=NOW,
            )
            prediction = bool(result.candidate_subject_ids)
            if expected_positive:
                consent_expected.append(conflict)
                consent_predicted.append(result.policy_conflict)
        else:
            result = analyze_voice_consent(
                data,
                asset_sha256=digest,
                context=_context(conflict=conflict),
                registry=consent_registry,
                assessed_at=NOW,
            )
            prediction = bool(result.candidate_subject_ids)
            if expected_positive:
                consent_expected.append(conflict)
                consent_predicted.append(result.policy_conflict)
        predicted[lane].append(prediction)
        case_results.append(
            {
                "case_id": case["case_id"],
                "lane": lane,
                "asset_sha256": digest,
                "expected_positive": expected_positive,
                "predicted_positive": prediction,
                "correct": prediction == expected_positive,
            }
        )

    return {
        "schema": "veilgraph.rightsgate.watermark-consent-evaluation-summary.v1",
        "dataset_id": manifest["dataset_id"],
        "manifest_sha256": _canonical_hash(manifest),
        "case_count": len(case_results),
        "visible_watermark_tamper": binary_metrics(
            expected["visible_watermark_tamper"], predicted["visible_watermark_tamper"]
        ).model_dump(mode="json"),
        "likeness_reference": binary_metrics(
            expected["likeness_reference"], predicted["likeness_reference"]
        ).model_dump(mode="json"),
        "voice_reference": binary_metrics(
            expected["voice_reference"], predicted["voice_reference"]
        ).model_dump(mode="json"),
        "consent_scope_conflict": binary_metrics(
            consent_expected, consent_predicted
        ).model_dump(mode="json"),
        "watermark_registry_sha256": watermark_registry.commitment_sha256(),
        "consent_registry_sha256": consent_registry.commitment_sha256(),
        "cases": case_results,
        "reproduce": "cd backend && PYTHONPATH=. python run_rightsgate_consent_eval.py",
        "claim_boundary": "Synthetic enrolled-reference and consent-scope sanity evidence only; not representative of arbitrary invisible-watermark, face-recognition, speaker-identification or legal-clearance performance.",
        "limitations": manifest["limitations"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--write-results", action="store_true")
    arguments = parser.parse_args()
    if arguments.initialize:
        manifest = initialize_manifest()
        arguments.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = run(arguments.manifest)
    if arguments.write_results:
        DEFAULT_RESULTS.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
