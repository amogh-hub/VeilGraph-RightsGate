"""Governed visible-watermark integrity verification for bounded images.

This lane deliberately verifies only operator-enrolled visible watermark
profiles at configured regions. It does not claim to detect arbitrary or
vendor-specific invisible watermarks.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any, Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import Field, field_validator, model_validator

from ..contracts import (
    AssessmentContext,
    AssessmentState,
    ClaimDimension,
    ClaimOutcome,
    ClaimRecord,
    ComponentRecord,
    ComponentState,
    EvidenceKind,
    EvidenceLocator,
    EvidencePointer,
    EvidencePolarity,
    LocatorKind,
    ProvenanceAssessment,
    ProvenanceVerdict,
    SHA256_PATTERN,
    ID_PATTERN,
    StrictFrozenModel,
)

WATERMARK_REGISTRY_SCHEMA = "veilgraph.rightsgate.visible-watermark-registry.v1"
COMPONENT_ID = "provenance.watermark-forensics"
COMPONENT_VERSION = "1.0.0"
COMPONENT_TYPE = "provenance.governed-visible-watermark-verifier"
DHASH_PATTERN = r"^[0-9a-f]{16}$"
DEFAULT_MAX_PIXELS = 40_000_000


class VisibleWatermarkProfile(StrictFrozenModel):
    profile_id: str = Field(pattern=ID_PATTERN)
    source_record_id: str = Field(pattern=ID_PATTERN)
    brand_profiles: tuple[str, ...] = Field(min_length=1)
    normalized_bbox: tuple[float, float, float, float]
    template_width: int = Field(gt=0, le=4096)
    template_height: int = Field(gt=0, le=4096)
    pixel_sha256: str = Field(pattern=SHA256_PATTERN)
    dhash: str = Field(pattern=DHASH_PATTERN)
    max_hamming_distance: int = Field(default=6, ge=0, le=64)

    @field_validator("brand_profiles")
    @classmethod
    def normalize_brand_profiles(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.strip().casefold() for value in values if value.strip()}))
        if not normalized:
            raise ValueError("brand_profiles cannot be empty")
        return normalized

    @field_validator("normalized_bbox")
    @classmethod
    def validate_bbox(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = value
        if min(value) < 0 or max(value) > 1 or x1 <= x0 or y1 <= y0:
            raise ValueError("normalized_bbox must have positive area inside [0,1]")
        return value


class VisibleWatermarkRegistry(StrictFrozenModel):
    schema_id: Literal[WATERMARK_REGISTRY_SCHEMA] = Field(
        default=WATERMARK_REGISTRY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    registry_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=100)
    profiles: tuple[VisibleWatermarkProfile, ...] = ()

    @model_validator(mode="after")
    def unique_profiles(self) -> VisibleWatermarkRegistry:
        identifiers = [profile.profile_id for profile in self.profiles]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("profile_id values must be unique")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True)
        payload["profiles"] = sorted(payload["profiles"], key=lambda item: item["profile_id"])
        return payload

    def commitment_sha256(self) -> str:
        return _canonical_hash(self.canonical_payload())


class WatermarkVerificationResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    assessment: ProvenanceAssessment


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalized_rgb(image: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.exif_transpose(image).convert("RGB").resize(
        (width, height), Image.Resampling.LANCZOS
    )


def _pixel_sha256(image: Image.Image) -> str:
    payload = (
        image.width.to_bytes(4, "big")
        + image.height.to_bytes(4, "big")
        + image.tobytes()
    )
    return hashlib.sha256(payload).hexdigest()


def _dhash(image: Image.Image) -> str:
    pixels = list(
        image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).get_flattened_data()
    )
    bits = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            bits = (bits << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return f"{bits:016x}"


def build_visible_watermark_profile(
    *,
    profile_id: str,
    source_record_id: str,
    brand_profiles: tuple[str, ...],
    normalized_bbox: tuple[float, float, float, float],
    template_data: bytes,
    max_hamming_distance: int = 6,
) -> VisibleWatermarkProfile:
    """Derive a content-bound watermark profile from a governed template image."""

    try:
        with Image.open(io.BytesIO(template_data)) as opened:
            opened.load()
            normalized = _normalized_rgb(opened, opened.width, opened.height)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("watermark template could not be decoded safely") from error
    return VisibleWatermarkProfile(
        profile_id=profile_id,
        source_record_id=source_record_id,
        brand_profiles=brand_profiles,
        normalized_bbox=normalized_bbox,
        template_width=normalized.width,
        template_height=normalized.height,
        pixel_sha256=_pixel_sha256(normalized),
        dhash=_dhash(normalized),
        max_hamming_distance=max_hamming_distance,
    )


def verify_visible_watermarks(
    data: bytes,
    *,
    asset_sha256: str,
    context: AssessmentContext,
    registry: VisibleWatermarkRegistry,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> WatermarkVerificationResult:
    """Verify configured visible watermark regions and fail closed on mismatch."""

    if hashlib.sha256(data).hexdigest() != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied image bytes")
    registry_sha256 = registry.commitment_sha256()
    component = ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        component_type=COMPONENT_TYPE,
        state=ComponentState.AVAILABLE,
        artifact_sha256=registry_sha256,
    )
    selected = tuple(
        profile
        for profile in registry.profiles
        if "*" in profile.brand_profiles
        or (context.brand_profile or "").casefold() in profile.brand_profiles
    )
    if not selected:
        limitation = "No governed visible-watermark profile applies to this brand context."
        return WatermarkVerificationResult(
            component=component,
            evidence=(),
            assessment=ProvenanceAssessment(
                state=AssessmentState.COMPLETE,
                verdict=ProvenanceVerdict.UNKNOWN,
                confidence=0,
                claims=(
                    ClaimRecord(
                        claim_id=f"claim.watermark-applicability-{asset_sha256[:16]}",
                        dimension=ClaimDimension.PROVENANCE,
                        claim_type="watermark.visible-integrity",
                        statement="An applicable governed visible watermark is intact.",
                        outcome=ClaimOutcome.NOT_ASSESSED,
                        confidence=0,
                        mandatory=False,
                        limitations=(limitation,),
                    ),
                ),
                limitations=(limitation,),
            ),
        )
    try:
        with Image.open(io.BytesIO(data)) as opened:
            width, height = opened.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise ValueError("image exceeds the configured pixel budget")
            opened.load()
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as error:
        reason = "The watermark verifier could not decode the asset within its safety budget."
        return WatermarkVerificationResult(
            component=component.model_copy(
                update={"state": ComponentState.DEGRADED, "reason": reason}
            ),
            evidence=(),
            assessment=ProvenanceAssessment(
                state=AssessmentState.UNAVAILABLE,
                verdict=ProvenanceVerdict.UNKNOWN,
                confidence=0,
                claims=(
                    ClaimRecord(
                        claim_id=f"claim.watermark-failure-{asset_sha256[:16]}",
                        dimension=ClaimDimension.PROVENANCE,
                        claim_type="watermark.visible-integrity",
                        statement="An applicable governed visible watermark is intact.",
                        outcome=ClaimOutcome.NOT_ASSESSED,
                        confidence=0,
                        mandatory=True,
                        limitations=(reason,),
                    ),
                ),
                limitations=(reason, str(error)[:200]),
            ),
        )

    evidence: list[EvidencePointer] = []
    claims: list[ClaimRecord] = []
    tampered_confidences: list[float] = []
    for profile in selected:
        x0, y0, x1, y1 = profile.normalized_bbox
        pixel_bbox = (
            round(x0 * image.width),
            round(y0 * image.height),
            round(x1 * image.width),
            round(y1 * image.height),
        )
        patch = _normalized_rgb(
            image.crop(pixel_bbox), profile.template_width, profile.template_height
        )
        pixel_sha256 = _pixel_sha256(patch)
        candidate_dhash = _dhash(patch)
        distance = (int(candidate_dhash, 16) ^ int(profile.dhash, 16)).bit_count()
        intact = pixel_sha256 == profile.pixel_sha256 or distance <= profile.max_hamming_distance
        confidence = 1.0 if pixel_sha256 == profile.pixel_sha256 else round(
            max(0.5, 1.0 - distance / 64.0), 6
        )
        if not intact:
            tampered_confidences.append(round(min(0.99, 0.55 + distance / 128.0), 6))
        token = hashlib.sha256(profile.profile_id.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"evidence.watermark-{token}-{asset_sha256[:16]}"
        evidence.append(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.WATERMARK,
                source="Governed visible-watermark integrity registry",
                component_id=COMPONENT_ID,
                component_version=COMPONENT_VERSION,
                polarity=(
                    EvidencePolarity.SUPPORTS if intact else EvidencePolarity.CONTRADICTS
                ),
                confidence=confidence if intact else tampered_confidences[-1],
                locator=EvidenceLocator(kind=LocatorKind.REGION, bbox=pixel_bbox),
                summary=(
                    "Configured visible watermark region matches its governed template."
                    if intact
                    else "Configured visible watermark region differs from its governed template."
                ),
                payload_sha256=_canonical_hash(
                    {
                        "asset_sha256": asset_sha256,
                        "candidate_dhash": candidate_dhash,
                        "distance": distance,
                        "pixel_sha256": pixel_sha256,
                        "profile_id": profile.profile_id,
                        "registry_sha256": registry_sha256,
                    }
                ),
                attributes={
                    "distance": distance,
                    "intact": intact,
                    "max_hamming_distance": profile.max_hamming_distance,
                    "profile_id": profile.profile_id,
                    "registry_id": registry.registry_id,
                    "registry_version": registry.version,
                    "source_record_id": profile.source_record_id,
                },
            )
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim.watermark-{token}-{asset_sha256[:16]}",
                dimension=ClaimDimension.PROVENANCE,
                claim_type="watermark.visible-integrity",
                statement=f"Visible watermark profile {profile.profile_id} is intact.",
                outcome=ClaimOutcome.SUPPORTED if intact else ClaimOutcome.CONTRADICTED,
                confidence=confidence if intact else tampered_confidences[-1],
                mandatory=True,
                evidence_ids=(evidence_id,),
                limitations=(
                    "This verifies an enrolled visible region only; it does not inspect arbitrary invisible watermarks.",
                ),
            )
        )

    tampered = bool(tampered_confidences)
    limitation = (
        "Visible watermark mismatch is policy evidence, not proof of who altered the asset."
        if tampered
        else "Configured visible watermark profiles passed; arbitrary invisible watermarks were not assessed."
    )
    return WatermarkVerificationResult(
        component=component,
        evidence=tuple(evidence),
        assessment=ProvenanceAssessment(
            state=AssessmentState.COMPLETE,
            verdict=ProvenanceVerdict.TAMPERED if tampered else ProvenanceVerdict.UNKNOWN,
            confidence=max(tampered_confidences, default=0),
            claims=tuple(claims),
            limitations=(limitation,),
        ),
    )
