"""Deterministic tests for image forensic triage and visual localization."""

from __future__ import annotations

import base64
import hashlib
import io

import numpy as np
import pytest
from PIL import Image, ImageDraw, PngImagePlugin
from pydantic import ValidationError

from app.rightsgate import ClaimOutcome, ComponentState, LocatorKind, ProvenanceVerdict
from app.rightsgate.provenance import inspect_image_forensics
from app.rightsgate.rights import (
    ImageFeatureManifest,
    ReferenceKind,
    RightsReferenceRegistry,
    build_registry_image,
    image_feature_manifest,
    localize_reference_images,
)


def _png(image: Image.Image, *, metadata: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    png_info = PngImagePlugin.PngInfo()
    for key, value in sorted((metadata or {}).items()):
        png_info.add_text(key, value)
    image.save(buffer, format="PNG", pnginfo=png_info)
    return buffer.getvalue()


def _feature_rich_mark() -> Image.Image:
    image = Image.new("RGB", (220, 160), "white")
    draw = ImageDraw.Draw(image)
    for x in range(10, 210, 20):
        draw.line((x, 5, 219 - x, 155), fill=(x % 255, 40, 180), width=3)
    for y in range(10, 150, 20):
        draw.rectangle((10 + y // 2, y, 50 + y, y + 12), outline="black", width=2)
    draw.text((55, 65), "VEILGRAPH RIGHTS", fill="black", stroke_width=1)
    return image


def _registry(reference_data: bytes) -> RightsReferenceRegistry:
    return RightsReferenceRegistry(
        registry_id="registry.visual-test",
        version="1",
        references=(
            build_registry_image(
                reference_id="reference.mark-test",
                kind=ReferenceKind.TRADEMARK,
                title="Governed test mark",
                rights_holder="Example Rights Holder",
                data=reference_data,
                media_type="image/png",
                source_record_id="rights-record.mark-test",
            ),
        ),
    )


def test_feature_manifest_is_deterministic_and_byte_bound() -> None:
    data = _png(_feature_rich_mark())
    first = image_feature_manifest(data)
    second = image_feature_manifest(data)

    assert first is not None
    assert first == second
    assert 4 <= len(first.keypoints) <= 384
    assert len(base64.b64decode(first.descriptors_b64)) == len(first.keypoints) * 32

    with pytest.raises(ValidationError, match="descriptor bytes"):
        ImageFeatureManifest(
            image_width=10,
            image_height=10,
            keypoints=((0.1, 0.1), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4)),
            descriptors_b64=base64.b64encode(b"short").decode("ascii"),
        )


def test_feature_manifest_uses_post_exif_orientation_coordinates() -> None:
    image = _feature_rich_mark()
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95, exif=exif)

    manifest = image_feature_manifest(buffer.getvalue())

    assert manifest is not None
    assert (manifest.image_width, manifest.image_height) == (160, 220)
    assert all(0 <= coordinate <= 1 for point in manifest.keypoints for coordinate in point)


def test_localizer_finds_a_governed_mark_inside_a_larger_asset() -> None:
    reference_data = _png(_feature_rich_mark())
    candidate = Image.new("RGB", (600, 420), (231, 235, 240))
    candidate.paste(_feature_rich_mark(), (170, 120))
    candidate_data = _png(candidate)
    asset_sha256 = hashlib.sha256(candidate_data).hexdigest()

    result = localize_reference_images(
        candidate_data,
        asset_sha256=asset_sha256,
        registry=_registry(reference_data),
    )

    assert result.component.state == ComponentState.AVAILABLE
    assert result.candidate_reference_ids == ("reference.mark-test",)
    assert result.claims[0].outcome == ClaimOutcome.SUPPORTED
    assert result.evidence[0].locator.kind == LocatorKind.REGION
    assert result.evidence[0].locator.bbox == pytest.approx((170, 120, 390, 280), abs=2)
    assert result.evidence[0].attributes["source_record_id"] == "rights-record.mark-test"
    assert result.evidence[0].attributes["inlier_count"] >= 6


def test_localizer_does_not_treat_no_match_as_clearance() -> None:
    reference_data = _png(_feature_rich_mark())
    unrelated = Image.new("RGB", (600, 420), "white")
    draw = ImageDraw.Draw(unrelated)
    for x in range(0, 600, 30):
        draw.ellipse((x, x % 300, x + 18, x % 300 + 18), fill="navy")
    candidate_data = _png(unrelated)

    result = localize_reference_images(
        candidate_data,
        asset_sha256=hashlib.sha256(candidate_data).hexdigest(),
        registry=_registry(reference_data),
    )

    assert result.component.state == ComponentState.AVAILABLE
    assert result.candidate_reference_ids == ()
    assert result.claims[0].outcome == ClaimOutcome.CONTRADICTED
    assert "not proof of rights clearance" in result.claims[0].limitations[0]


def test_localizer_degrades_when_reference_has_no_stable_features() -> None:
    reference_data = _png(Image.new("RGB", (128, 128), "white"))
    candidate_data = _png(_feature_rich_mark())
    result = localize_reference_images(
        candidate_data,
        asset_sha256=hashlib.sha256(candidate_data).hexdigest(),
        registry=_registry(reference_data),
    )

    assert result.component.state == ComponentState.DEGRADED
    assert result.claims[0].outcome == ClaimOutcome.NOT_ASSESSED


def test_forensics_reports_declared_generation_without_overclaiming() -> None:
    data = _png(
        _feature_rich_mark(),
        metadata={
            "parameters": "Stable Diffusion prompt=city skyline; steps=20; seed=42",
        },
    )
    result = inspect_image_forensics(data, asset_sha256=hashlib.sha256(data).hexdigest())

    assert result.component.state == ComponentState.AVAILABLE
    assert result.assessment.verdict == ProvenanceVerdict.AI_GENERATED
    assert result.assessment.confidence == pytest.approx(0.85)
    assert any(item.locator.kind == LocatorKind.METADATA_PATH for item in result.evidence)
    assert any(item.outcome == ClaimOutcome.SUPPORTED for item in result.assessment.claims)


def test_forensics_recognizes_declared_partial_edit() -> None:
    data = _png(
        _feature_rich_mark(),
        metadata={"Software": "Adobe Firefly generative fill"},
    )
    result = inspect_image_forensics(data, asset_sha256=hashlib.sha256(data).hexdigest())

    assert result.assessment.verdict == ProvenanceVerdict.PARTIALLY_GENERATED
    assert result.assessment.confidence == pytest.approx(0.70)


def test_forensics_keeps_clean_metadata_absence_unknown() -> None:
    data = _png(_feature_rich_mark())
    result = inspect_image_forensics(data, asset_sha256=hashlib.sha256(data).hexdigest())

    assert result.assessment.verdict == ProvenanceVerdict.UNKNOWN
    assert result.assessment.confidence == 0
    assert result.assessment.limitations
    assert result.assessment.claims[0].outcome == ClaimOutcome.UNKNOWN


def test_forensics_localizes_non_attributive_residual_anomaly() -> None:
    rng = np.random.default_rng(20260915)
    pixels = np.full((300, 300), 128, dtype=np.uint8)
    pixels[100:150, 150:200] = rng.integers(0, 256, size=(50, 50), dtype=np.uint8)
    data = _png(Image.fromarray(pixels, mode="L"))
    result = inspect_image_forensics(data, asset_sha256=hashlib.sha256(data).hexdigest())

    anomaly = next(item for item in result.evidence if item.kind.value == "FORENSIC_SIGNAL")
    assert anomaly.attributes["anomalous"] is True
    assert anomaly.locator.kind == LocatorKind.REGION
    assert result.assessment.verdict == ProvenanceVerdict.UNKNOWN


@pytest.mark.parametrize("adapter", [inspect_image_forensics, localize_reference_images])
def test_detectors_reject_unbound_asset_bytes(adapter) -> None:
    data = _png(_feature_rich_mark())
    kwargs = {"registry": _registry(data)} if adapter is localize_reference_images else {}
    with pytest.raises(ValueError, match="does not match"):
        adapter(data, asset_sha256="0" * 64, **kwargs)
