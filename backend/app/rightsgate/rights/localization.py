"""Local ORB/RANSAC localization for governed visual rights references."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ..contracts import (
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
    StrictFrozenModel,
)
from .image_registry import DEFAULT_MAX_PIXELS, RegistryImage, RightsReferenceRegistry

COMPONENT_ID = "rights.trademark-localizer"
COMPONENT_VERSION = "1.0.0"
COMPONENT_TYPE = "rights.local-feature-localizer"
DEFAULT_RATIO_THRESHOLD = 0.76
DEFAULT_MIN_INLIERS = 6
DEFAULT_MIN_INLIER_RATIO = 0.45


class LocalizedReferenceMatchResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    claims: tuple[ClaimRecord, ...]
    candidate_reference_ids: tuple[str, ...]
    limitations: tuple[str, ...] = ()


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _component(
    registry_sha256: str,
    state: ComponentState,
    reason: str | None = None,
) -> ComponentRecord:
    return ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        component_type=COMPONENT_TYPE,
        state=state,
        artifact_sha256=registry_sha256,
        reason=reason,
    )


def _decode_grayscale(data: bytes, *, max_pixels: int) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            width, height = opened.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise ValueError("image exceeds the configured pixel budget")
            opened.load()
            return np.asarray(ImageOps.exif_transpose(opened).convert("L"), dtype=np.uint8)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("image could not be decoded safely") from error


def _candidate_features(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    detector = cv2.ORB_create(
        nfeatures=768,
        scaleFactor=1.2,
        nlevels=8,
        edgeThreshold=15,
        patchSize=31,
        fastThreshold=10,
    )
    keypoints, descriptors = detector.detectAndCompute(image, None)
    if descriptors is None or len(keypoints) < 4:
        return None
    points = np.asarray([keypoint.pt for keypoint in keypoints], dtype=np.float32)
    return points, descriptors.astype(np.uint8, copy=False)


def _reference_features(reference: RegistryImage) -> tuple[np.ndarray, np.ndarray] | None:
    manifest = reference.feature_manifest
    if manifest is None:
        return None
    points = np.asarray(
        [
            (x * manifest.image_width, y * manifest.image_height)
            for x, y in manifest.keypoints
        ],
        dtype=np.float32,
    )
    raw = base64.b64decode(manifest.descriptors_b64, validate=True)
    descriptors = np.frombuffer(raw, dtype=np.uint8).reshape(-1, manifest.descriptor_size)
    return points, descriptors


def _localized_candidate(
    reference: RegistryImage,
    candidate_points: np.ndarray,
    candidate_descriptors: np.ndarray,
    *,
    candidate_width: int,
    candidate_height: int,
    ratio_threshold: float,
    min_inliers: int,
    min_inlier_ratio: float,
) -> dict[str, Any] | None:
    decoded = _reference_features(reference)
    if decoded is None or len(candidate_descriptors) < 2:
        return None
    reference_points, reference_descriptors = decoded
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    pairs = matcher.knnMatch(reference_descriptors, candidate_descriptors, k=2)
    good = [
        pair[0]
        for pair in pairs
        if len(pair) == 2 and pair[0].distance < ratio_threshold * pair[1].distance
    ]
    if len(good) < max(4, min_inliers):
        return None

    source = np.float32([reference_points[item.queryIdx] for item in good]).reshape(-1, 1, 2)
    target = np.float32([candidate_points[item.trainIdx] for item in good]).reshape(-1, 1, 2)
    homography, mask = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
    if homography is None or mask is None or not np.isfinite(homography).all():
        return None
    inliers = int(mask.ravel().sum())
    inlier_ratio = inliers / len(good)
    if inliers < min_inliers or inlier_ratio < min_inlier_ratio:
        return None

    manifest = reference.feature_manifest
    assert manifest is not None
    corners = np.float32(
        [
            [0, 0],
            [manifest.image_width - 1, 0],
            [manifest.image_width - 1, manifest.image_height - 1],
            [0, manifest.image_height - 1],
        ]
    ).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
    if not np.isfinite(projected).all():
        return None
    x0 = max(0.0, float(projected[:, 0].min()))
    y0 = max(0.0, float(projected[:, 1].min()))
    x1 = min(float(candidate_width), float(projected[:, 0].max()))
    y1 = min(float(candidate_height), float(projected[:, 1].max()))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    area_ratio = ((x1 - x0) * (y1 - y0)) / (candidate_width * candidate_height)
    if not 0 < area_ratio <= 1:
        return None

    confidence = min(
        0.98,
        0.45 + 0.35 * inlier_ratio + 0.20 * min(1.0, inliers / 24.0),
    )
    return {
        "bbox": tuple(round(value, 3) for value in (x0, y0, x1, y1)),
        "good_match_count": len(good),
        "inlier_count": inliers,
        "inlier_ratio": round(inlier_ratio, 6),
        "area_ratio": round(area_ratio, 6),
        "confidence": round(confidence, 6),
        "homography": [round(float(value), 8) for value in homography.ravel()],
    }


def localize_reference_images(
    data: bytes,
    *,
    asset_sha256: str,
    registry: RightsReferenceRegistry,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    ratio_threshold: float = DEFAULT_RATIO_THRESHOLD,
    min_inliers: int = DEFAULT_MIN_INLIERS,
    min_inlier_ratio: float = DEFAULT_MIN_INLIER_RATIO,
) -> LocalizedReferenceMatchResult:
    """Return regional candidates without treating visual similarity as infringement."""

    if hashlib.sha256(data).hexdigest() != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied image bytes")
    if not 0.5 <= ratio_threshold < 1:
        raise ValueError("ratio_threshold must be between 0.5 inclusive and 1 exclusive")
    if min_inliers < 4:
        raise ValueError("min_inliers must be at least four")
    if not 0 < min_inlier_ratio <= 1:
        raise ValueError("min_inlier_ratio must be in (0, 1]")

    registry_sha256 = registry.commitment_sha256()
    feature_references = tuple(
        reference for reference in registry.references if reference.feature_manifest is not None
    )
    if not feature_references:
        reason = "No governed reference contains sufficient local features for localization."
        return LocalizedReferenceMatchResult(
            component=_component(registry_sha256, ComponentState.DEGRADED, reason),
            evidence=(),
            claims=(
                ClaimRecord(
                    claim_id=f"claim.visual-localization-{asset_sha256[:16]}",
                    dimension=ClaimDimension.RIGHTS_EXPOSURE,
                    claim_type="reference.localized-candidate",
                    statement="A governed work or mark is localized within the asset.",
                    outcome=ClaimOutcome.NOT_ASSESSED,
                    confidence=0,
                    mandatory=False,
                    limitations=(reason,),
                ),
            ),
            candidate_reference_ids=(),
            limitations=(reason,),
        )

    try:
        candidate = _decode_grayscale(data, max_pixels=max_pixels)
        extracted = _candidate_features(candidate)
    except ValueError as error:
        reason = str(error)
        return LocalizedReferenceMatchResult(
            component=_component(registry_sha256, ComponentState.DEGRADED, reason),
            evidence=(),
            claims=(
                ClaimRecord(
                    claim_id=f"claim.visual-localization-{asset_sha256[:16]}",
                    dimension=ClaimDimension.RIGHTS_EXPOSURE,
                    claim_type="reference.localized-candidate",
                    statement="A governed work or mark is localized within the asset.",
                    outcome=ClaimOutcome.NOT_ASSESSED,
                    confidence=0,
                    mandatory=False,
                    limitations=(reason,),
                ),
            ),
            candidate_reference_ids=(),
            limitations=(reason,),
        )
    if extracted is None:
        reason = "The assessed asset contains too few stable local features for localization."
        return LocalizedReferenceMatchResult(
            component=_component(registry_sha256, ComponentState.DEGRADED, reason),
            evidence=(),
            claims=(
                ClaimRecord(
                    claim_id=f"claim.visual-localization-{asset_sha256[:16]}",
                    dimension=ClaimDimension.RIGHTS_EXPOSURE,
                    claim_type="reference.localized-candidate",
                    statement="A governed work or mark is localized within the asset.",
                    outcome=ClaimOutcome.NOT_ASSESSED,
                    confidence=0,
                    mandatory=False,
                    limitations=(reason,),
                ),
            ),
            candidate_reference_ids=(),
            limitations=(reason,),
        )

    candidate_points, candidate_descriptors = extracted
    height, width = candidate.shape
    matches: list[tuple[RegistryImage, dict[str, Any]]] = []
    for reference in feature_references:
        localized = _localized_candidate(
            reference,
            candidate_points,
            candidate_descriptors,
            candidate_width=width,
            candidate_height=height,
            ratio_threshold=ratio_threshold,
            min_inliers=min_inliers,
            min_inlier_ratio=min_inlier_ratio,
        )
        if localized is not None:
            matches.append((reference, localized))
    matches.sort(key=lambda item: (-item[1]["confidence"], item[0].reference_id))

    if not matches:
        limitation = (
            "No local-feature candidate passed the configured geometric threshold; "
            "this is not proof of rights clearance."
        )
        evidence_id = f"evidence.visual-localization-query-{asset_sha256[:16]}"
        payload = {
            "asset_sha256": asset_sha256,
            "feature_reference_count": len(feature_references),
            "min_inlier_ratio": min_inlier_ratio,
            "min_inliers": min_inliers,
            "ratio_threshold": ratio_threshold,
            "registry_sha256": registry_sha256,
        }
        return LocalizedReferenceMatchResult(
            component=_component(registry_sha256, ComponentState.AVAILABLE),
            evidence=(
                EvidencePointer(
                    evidence_id=evidence_id,
                    asset_sha256=asset_sha256,
                    kind=EvidenceKind.REFERENCE_MATCH,
                    source="Governed local ORB/RANSAC visual-reference localizer",
                    component_id=COMPONENT_ID,
                    component_version=COMPONENT_VERSION,
                    polarity=EvidencePolarity.CONTRADICTS,
                    confidence=1,
                    locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                    summary="No governed visual reference passed geometric localization.",
                    payload_sha256=_canonical_hash(payload),
                    attributes={
                        "candidate_count": 0,
                        "feature_reference_count": len(feature_references),
                        "registry_id": registry.registry_id,
                        "registry_version": registry.version,
                    },
                ),
            ),
            claims=(
                ClaimRecord(
                    claim_id=f"claim.visual-localization-{asset_sha256[:16]}",
                    dimension=ClaimDimension.RIGHTS_EXPOSURE,
                    claim_type="reference.localized-candidate",
                    statement="A governed work or mark is localized within the asset.",
                    outcome=ClaimOutcome.CONTRADICTED,
                    confidence=1,
                    mandatory=False,
                    evidence_ids=(evidence_id,),
                    limitations=(limitation,),
                ),
            ),
            candidate_reference_ids=(),
            limitations=(limitation,),
        )

    evidence: list[EvidencePointer] = []
    claims: list[ClaimRecord] = []
    for reference, localized in matches:
        reference_token = hashlib.sha256(reference.reference_id.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"evidence.visual-localization-{reference_token}-{asset_sha256[:16]}"
        payload = {
            **localized,
            "asset_sha256": asset_sha256,
            "reference_id": reference.reference_id,
            "registry_sha256": registry_sha256,
        }
        confidence = float(localized["confidence"])
        evidence.append(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.REFERENCE_MATCH,
                source="Governed local ORB/RANSAC visual-reference localizer",
                component_id=COMPONENT_ID,
                component_version=COMPONENT_VERSION,
                polarity=EvidencePolarity.SUPPORTS,
                confidence=confidence,
                locator=EvidenceLocator(
                    kind=LocatorKind.REGION,
                    bbox=localized["bbox"],
                ),
                summary="A governed visual reference passed feature and geometric verification.",
                payload_sha256=_canonical_hash(payload),
                attributes={
                    "area_ratio": localized["area_ratio"],
                    "good_match_count": localized["good_match_count"],
                    "inlier_count": localized["inlier_count"],
                    "inlier_ratio": localized["inlier_ratio"],
                    "reference_id": reference.reference_id,
                    "reference_kind": reference.kind.value,
                    "reference_title": reference.title,
                    "rights_holder": reference.rights_holder,
                    "registry_id": registry.registry_id,
                    "registry_version": registry.version,
                    "source_record_id": reference.source_record_id,
                },
            )
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim.visual-localization-{reference_token}-{asset_sha256[:16]}",
                dimension=ClaimDimension.RIGHTS_EXPOSURE,
                claim_type="reference.localized-candidate",
                statement=(
                    f"Governed reference {reference.reference_id} is localized within the asset."
                ),
                outcome=ClaimOutcome.SUPPORTED,
                confidence=confidence,
                mandatory=False,
                evidence_ids=(evidence_id,),
                limitations=(
                    "Local-feature similarity is candidate evidence, not a legal determination.",
                ),
            )
        )

    return LocalizedReferenceMatchResult(
        component=_component(registry_sha256, ComponentState.AVAILABLE),
        evidence=tuple(evidence),
        claims=tuple(claims),
        candidate_reference_ids=tuple(sorted(reference.reference_id for reference, _ in matches)),
        limitations=(
            "Localization is limited to governed references with stable ORB features.",
            "Candidate geometry is not proof of infringement, ownership or consumer confusion.",
        ),
    )
