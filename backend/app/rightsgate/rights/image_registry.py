"""Local exact/perceptual candidate retrieval for governed image references."""

from __future__ import annotations

import hashlib
import io
import json
from enum import Enum
from typing import Any, Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import Field, model_validator

from ..contracts import (
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
    RightsAssessment,
    RightsVerdict,
    SHA256_PATTERN,
    ID_PATTERN,
    StrictFrozenModel,
)

REGISTRY_SCHEMA = "veilgraph.rightsgate.rights-reference-registry.v1"
COMPONENT_ID = "rights.local-image-registry"
COMPONENT_VERSION = "1.0.0"
COMPONENT_TYPE = "rights.reference-retriever"
DHASH_PATTERN = r"^[0-9a-f]{16}$"
DEFAULT_MAX_PIXELS = 40_000_000


class ReferenceKind(str, Enum):
    COPYRIGHTED_WORK = "COPYRIGHTED_WORK"
    TRADEMARK = "TRADEMARK"


class RegistryImage(StrictFrozenModel):
    reference_id: str = Field(pattern=ID_PATTERN)
    kind: ReferenceKind
    title: str = Field(min_length=1, max_length=300)
    rights_holder: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=SHA256_PATTERN)
    dhash: str = Field(pattern=DHASH_PATTERN)
    media_type: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(pattern=ID_PATTERN)


class RightsReferenceRegistry(StrictFrozenModel):
    schema_id: Literal[REGISTRY_SCHEMA] = Field(
        default=REGISTRY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    registry_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=100)
    references: tuple[RegistryImage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_references(self) -> RightsReferenceRegistry:
        reference_ids = [item.reference_id for item in self.references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("reference_id values must be unique")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True)
        payload["references"] = sorted(
            payload["references"], key=lambda item: item["reference_id"]
        )
        return payload

    def commitment_sha256(self) -> str:
        return _canonical_hash(self.canonical_payload())


class RightsImageMatchResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    assessment: RightsAssessment


class _ImageInspectionError(ValueError):
    pass


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def image_dhash(data: bytes, *, max_pixels: int = DEFAULT_MAX_PIXELS) -> str:
    """Return a deterministic 64-bit difference hash after EXIF orientation."""

    if max_pixels < 1:
        raise ValueError("max_pixels must be positive")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            width, height = opened.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise _ImageInspectionError("image exceeds the configured pixel budget")
            opened.load()
            normalized = ImageOps.exif_transpose(opened).convert("L")
            resized = normalized.resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(resized.get_flattened_data())
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise _ImageInspectionError("image could not be decoded safely") from error

    bits = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            bits = (bits << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return f"{bits:016x}"


def build_registry_image(
    *,
    reference_id: str,
    kind: ReferenceKind,
    title: str,
    rights_holder: str,
    data: bytes,
    media_type: str,
    source_record_id: str,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> RegistryImage:
    """Build a byte-bound registry record from a governed local image."""

    return RegistryImage(
        reference_id=reference_id,
        kind=kind,
        title=title,
        rights_holder=rights_holder,
        sha256=hashlib.sha256(data).hexdigest(),
        dhash=image_dhash(data, max_pixels=max_pixels),
        media_type=media_type,
        source_record_id=source_record_id,
    )


def _hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _component(registry_sha256: str, state: ComponentState, reason: str | None = None) -> ComponentRecord:
    return ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        component_type=COMPONENT_TYPE,
        state=state,
        artifact_sha256=registry_sha256,
        reason=reason,
    )


def _safe_failure(
    *,
    asset_sha256: str,
    registry_sha256: str,
    reason: str,
) -> RightsImageMatchResult:
    evidence_id = f"evidence.rights-registry-failure-{asset_sha256[:16]}"
    evidence = EvidencePointer(
        evidence_id=evidence_id,
        asset_sha256=asset_sha256,
        kind=EvidenceKind.COMPONENT_FAILURE,
        source="Governed local rights-reference registry",
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        polarity=EvidencePolarity.NEUTRAL,
        confidence=1,
        locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
        summary=reason,
        payload_sha256=_canonical_hash(
            {"asset_sha256": asset_sha256, "registry_sha256": registry_sha256, "reason": reason}
        ),
    )
    claim = ClaimRecord(
        claim_id=f"claim.rights-registry-{asset_sha256[:16]}",
        dimension=ClaimDimension.RIGHTS_EXPOSURE,
        claim_type="reference.candidate-match",
        statement="The asset has a candidate match in the governed local reference registry.",
        outcome=ClaimOutcome.NOT_ASSESSED,
        confidence=0,
        mandatory=False,
        limitations=(reason,),
    )
    return RightsImageMatchResult(
        component=_component(registry_sha256, ComponentState.DEGRADED, reason),
        evidence=(evidence,),
        assessment=RightsAssessment(
            state=AssessmentState.UNAVAILABLE,
            verdict=RightsVerdict.UNKNOWN,
            confidence=0,
            claims=(claim,),
            limitations=(reason,),
        ),
    )


def match_reference_image(
    data: bytes,
    *,
    asset_sha256: str,
    registry: RightsReferenceRegistry,
    max_hamming_distance: int = 6,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> RightsImageMatchResult:
    """Retrieve exact/perceptual candidates without making a legal conclusion."""

    if not 0 <= max_hamming_distance <= 64:
        raise ValueError("max_hamming_distance must be between 0 and 64")
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied image bytes")

    registry_sha256 = registry.commitment_sha256()
    try:
        candidate_dhash = image_dhash(data, max_pixels=max_pixels)
    except _ImageInspectionError:
        return _safe_failure(
            asset_sha256=asset_sha256,
            registry_sha256=registry_sha256,
            reason="The candidate image could not be decoded within the configured safety budget.",
        )

    matches: list[tuple[RegistryImage, int, bool]] = []
    for reference in registry.references:
        exact = reference.sha256 == asset_sha256
        distance = _hamming_distance(candidate_dhash, reference.dhash)
        if exact or distance <= max_hamming_distance:
            matches.append((reference, distance, exact))
    matches.sort(key=lambda item: (not item[2], item[1], item[0].reference_id))

    if not matches:
        limitation = (
            "No candidate exceeded the configured threshold in this registry; registry coverage is not proof of rights clearance."
        )
        evidence_id = f"evidence.rights-registry-query-{asset_sha256[:16]}"
        evidence = EvidencePointer(
            evidence_id=evidence_id,
            asset_sha256=asset_sha256,
            kind=EvidenceKind.REFERENCE_MATCH,
            source="Governed local rights-reference registry",
            component_id=COMPONENT_ID,
            component_version=COMPONENT_VERSION,
            polarity=EvidencePolarity.CONTRADICTS,
            confidence=1,
            locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
            summary="No exact or perceptual candidate met the configured registry threshold.",
            payload_sha256=_canonical_hash(
                {
                    "asset_sha256": asset_sha256,
                    "candidate_dhash": candidate_dhash,
                    "max_hamming_distance": max_hamming_distance,
                    "registry_sha256": registry_sha256,
                }
            ),
            attributes={
                "candidate_count": 0,
                "max_hamming_distance": max_hamming_distance,
                "registry_id": registry.registry_id,
                "registry_version": registry.version,
            },
        )
        claim = ClaimRecord(
            claim_id=f"claim.rights-registry-{asset_sha256[:16]}",
            dimension=ClaimDimension.RIGHTS_EXPOSURE,
            claim_type="reference.candidate-match",
            statement="The asset has a candidate match in the governed local reference registry.",
            outcome=ClaimOutcome.CONTRADICTED,
            confidence=1,
            mandatory=False,
            evidence_ids=(evidence_id,),
            limitations=(limitation,),
        )
        return RightsImageMatchResult(
            component=_component(registry_sha256, ComponentState.AVAILABLE),
            evidence=(evidence,),
            assessment=RightsAssessment(
                state=AssessmentState.COMPLETE,
                verdict=RightsVerdict.UNKNOWN,
                confidence=0,
                claims=(claim,),
                limitations=(limitation,),
            ),
        )

    evidence: list[EvidencePointer] = []
    claims: list[ClaimRecord] = []
    for reference, distance, exact in matches:
        similarity = 1.0 if exact else max(0.5, 0.95 * (1.0 - (distance / 64.0)))
        reference_token = hashlib.sha256(reference.reference_id.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"evidence.rights-match-{reference_token}-{asset_sha256[:16]}"
        evidence.append(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.REFERENCE_MATCH,
                source="Governed local rights-reference registry",
                component_id=COMPONENT_ID,
                component_version=COMPONENT_VERSION,
                polarity=EvidencePolarity.SUPPORTS,
                confidence=similarity,
                locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                summary=(
                    "Exact byte match with governed reference."
                    if exact
                    else "Perceptual-hash candidate match with governed reference."
                ),
                payload_sha256=_canonical_hash(
                    {
                        "asset_sha256": asset_sha256,
                        "distance": distance,
                        "exact": exact,
                        "reference_id": reference.reference_id,
                        "registry_sha256": registry_sha256,
                    }
                ),
                attributes={
                    "distance": distance,
                    "exact": exact,
                    "reference_id": reference.reference_id,
                    "reference_kind": reference.kind.value,
                    "registry_id": registry.registry_id,
                    "registry_version": registry.version,
                },
            )
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim.rights-match-{reference_token}-{asset_sha256[:16]}",
                dimension=ClaimDimension.RIGHTS_EXPOSURE,
                claim_type="reference.candidate-match",
                statement=(
                    f"The asset is a candidate match for governed reference {reference.reference_id}."
                ),
                outcome=ClaimOutcome.SUPPORTED,
                confidence=similarity,
                mandatory=False,
                evidence_ids=(evidence_id,),
                limitations=(
                    "Similarity is retrieval evidence, not a legal determination of ownership or infringement.",
                ),
            )
        )

    return RightsImageMatchResult(
        component=_component(registry_sha256, ComponentState.AVAILABLE),
        evidence=tuple(evidence),
        assessment=RightsAssessment(
            state=AssessmentState.COMPLETE,
            verdict=RightsVerdict.POTENTIAL_EXPOSURE,
            confidence=max(item.confidence for item in evidence),
            claims=tuple(claims),
            limitations=(
                "Candidate matches require licence, consent, territory and intended-use evaluation.",
                "Similarity is retrieval evidence, not a legal determination of ownership or infringement.",
            ),
        ),
    )
