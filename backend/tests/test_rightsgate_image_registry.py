"""Tests for governed exact/perceptual rights-reference retrieval."""

from __future__ import annotations

import hashlib
import io

import pytest
from PIL import Image
from pydantic import ValidationError

from app.rightsgate import ClaimOutcome, ComponentState, RightsVerdict
from app.rightsgate.rights import (
    ReferenceKind,
    RightsReferenceRegistry,
    build_registry_image,
    image_dhash,
    match_reference_image,
)


def gradient_png(*, reverse: bool = False, width: int = 32, height: int = 24) -> bytes:
    image = Image.new("L", (width, height))
    for x in range(width):
        value = round(255 * x / max(1, width - 1))
        if reverse:
            value = 255 - value
        for y in range(height):
            image.putpixel((x, y), value)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def registry(reference_data: bytes | None = None) -> RightsReferenceRegistry:
    data = reference_data or gradient_png()
    reference = build_registry_image(
        reference_id="reference.work-001",
        kind=ReferenceKind.COPYRIGHTED_WORK,
        title="Governed test work",
        rights_holder="Test rights holder",
        data=data,
        media_type="image/png",
        source_record_id="rights-record.work-001",
    )
    return RightsReferenceRegistry(
        registry_id="registry.test",
        version="1",
        references=(reference,),
    )


def test_dhash_is_stable_across_lossless_resize() -> None:
    assert image_dhash(gradient_png()) == image_dhash(gradient_png(width=64, height=48))
    assert image_dhash(gradient_png()) != image_dhash(gradient_png(reverse=True))


def test_exact_reference_match_returns_potential_exposure() -> None:
    data = gradient_png()
    result = match_reference_image(
        data,
        asset_sha256=hashlib.sha256(data).hexdigest(),
        registry=registry(data),
    )

    assert result.component.state == ComponentState.AVAILABLE
    assert result.assessment.verdict == RightsVerdict.POTENTIAL_EXPOSURE
    assert result.assessment.confidence == 1
    assert result.evidence[0].attributes["exact"] is True
    assert result.evidence[0].attributes["max_hamming_distance"] == 6
    assert result.evidence[0].attributes["source_record_id"] == "rights-record.work-001"
    assert result.assessment.claims[0].outcome == ClaimOutcome.SUPPORTED
    assert "not a legal determination" in result.assessment.limitations[1]


def test_perceptual_match_survives_resize_but_remains_candidate_only() -> None:
    reference_data = gradient_png()
    candidate_data = gradient_png(width=64, height=48)
    result = match_reference_image(
        candidate_data,
        asset_sha256=hashlib.sha256(candidate_data).hexdigest(),
        registry=registry(reference_data),
        max_hamming_distance=0,
    )

    assert result.assessment.verdict == RightsVerdict.POTENTIAL_EXPOSURE
    assert result.evidence[0].attributes["exact"] is False
    assert result.evidence[0].attributes["distance"] == 0


def test_no_candidate_is_unknown_not_rights_clearance() -> None:
    candidate_data = gradient_png(reverse=True)
    result = match_reference_image(
        candidate_data,
        asset_sha256=hashlib.sha256(candidate_data).hexdigest(),
        registry=registry(),
        max_hamming_distance=4,
    )

    assert result.assessment.verdict == RightsVerdict.UNKNOWN
    assert result.assessment.claims[0].outcome == ClaimOutcome.CONTRADICTED
    assert result.evidence[0].attributes["candidate_count"] == 0
    assert "not proof of rights clearance" in result.assessment.limitations[0]


def test_asset_hash_must_bind_to_exact_candidate_bytes() -> None:
    with pytest.raises(ValueError, match="does not match"):
        match_reference_image(
            gradient_png(),
            asset_sha256="f" * 64,
            registry=registry(),
        )


def test_decode_budget_failure_degrades_and_fails_closed() -> None:
    data = gradient_png()
    result = match_reference_image(
        data,
        asset_sha256=hashlib.sha256(data).hexdigest(),
        registry=registry(data),
        max_pixels=1,
    )

    assert result.component.state == ComponentState.DEGRADED
    assert result.assessment.verdict == RightsVerdict.UNKNOWN
    assert result.assessment.claims[0].outcome == ClaimOutcome.NOT_ASSESSED


def test_registry_requires_unique_ids_and_has_order_invariant_commitment() -> None:
    first = registry().references[0]
    second = first.model_copy(
        update={
            "reference_id": "reference.work-002",
            "source_record_id": "rights-record.work-002",
        }
    )
    left = RightsReferenceRegistry(
        registry_id="registry.test",
        version="1",
        references=(first, second),
    )
    right = RightsReferenceRegistry(
        registry_id="registry.test",
        version="1",
        references=(second, first),
    )
    assert left.commitment_sha256() == right.commitment_sha256()

    with pytest.raises(ValidationError, match="reference_id values must be unique"):
        RightsReferenceRegistry(
            registry_id="registry.test",
            version="1",
            references=(first, first),
        )


def test_threshold_is_bounded() -> None:
    data = gradient_png()
    with pytest.raises(ValueError, match="between 0 and 64"):
        match_reference_image(
            data,
            asset_sha256=hashlib.sha256(data).hexdigest(),
            registry=registry(data),
            max_hamming_distance=65,
        )
