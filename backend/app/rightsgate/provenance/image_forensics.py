"""Deterministic, C2PA-independent image forensic triage.

This adapter deliberately separates observable signals from universal generator
attribution. Recognized generative-tool metadata can support an origin claim;
pixel residual anomalies are localized but remain non-attributive review signals.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from typing import Any

import cv2
import numpy as np
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

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
    ProvenanceAssessment,
    ProvenanceVerdict,
    StrictFrozenModel,
)

COMPONENT_ID = "provenance.independent-forensics"
COMPONENT_VERSION = "1.0.0"
COMPONENT_TYPE = "provenance.deterministic-image-triage"
DEFAULT_MAX_PIXELS = 40_000_000
GENERATIVE_TOOL_TOKENS = (
    "automatic1111",
    "comfyui",
    "dall-e",
    "dalle",
    "firefly",
    "generative fill",
    "invokeai",
    "midjourney",
    "novelai",
    "stable diffusion",
)
GENERATION_FIELD_TOKENS = (
    "negative prompt",
    "prompt",
    "sampler",
    "seed",
    "steps",
)
PARTIAL_EDIT_TOKENS = (
    "controlnet",
    "generative fill",
    "inpaint",
    "outpaint",
)
UNAMBIGUOUS_TOOL_TOKENS = (
    "automatic1111",
    "comfyui",
    "dall-e",
    "dalle",
    "generative fill",
    "invokeai",
    "midjourney",
    "novelai",
)
SOURCE_FIELD_TOKENS = ("generator", "model", "software")
MIN_TILE_SIDE = 24
ANOMALY_Z_THRESHOLD = 6.0
ANOMALY_RATIO_THRESHOLD = 1.8


class ImageForensicsResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    assessment: ProvenanceAssessment


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_sha256() -> str:
    return _canonical_hash(
        {
            "anomaly_ratio_threshold": ANOMALY_RATIO_THRESHOLD,
            "anomaly_z_threshold": ANOMALY_Z_THRESHOLD,
            "component_version": COMPONENT_VERSION,
            "generation_field_tokens": GENERATION_FIELD_TOKENS,
            "generative_tool_tokens": GENERATIVE_TOOL_TOKENS,
            "min_tile_side": MIN_TILE_SIDE,
            "partial_edit_tokens": PARTIAL_EDIT_TOKENS,
            "source_field_tokens": SOURCE_FIELD_TOKENS,
            "unambiguous_tool_tokens": UNAMBIGUOUS_TOOL_TOKENS,
        }
    )


def _component(state: ComponentState, reason: str | None = None) -> ComponentRecord:
    return ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        component_type=COMPONENT_TYPE,
        state=state,
        artifact_sha256=_manifest_sha256(),
        reason=reason,
    )


def _bounded_text(value: object) -> str | None:
    if isinstance(value, bytes):
        try:
            return value[:2048].decode("utf-8", errors="replace")
        except Exception:
            return None
    if isinstance(value, (str, int, float)):
        return str(value)[:2048]
    return None


def _extract_metadata(opened: Image.Image) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key, value in sorted(opened.info.items(), key=lambda item: str(item[0]).casefold()):
        text = _bounded_text(value)
        if text:
            metadata[f"info.{str(key)[:100]}"] = text
    try:
        exif = opened.getexif()
    except (AttributeError, OSError, ValueError):
        exif = {}
    for key, value in exif.items():
        label = ExifTags.TAGS.get(key, str(key))
        text = _bounded_text(value)
        if text:
            metadata[f"exif.{str(label)[:100]}"] = text
    return dict(list(metadata.items())[:128])


def _metadata_markers(metadata: dict[str, str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    tools: set[str] = set()
    fields: set[str] = set()
    for key, value in metadata.items():
        key_folded = key.casefold()
        searchable = f"{key}={value}".casefold()
        field_hits = {
            token
            for token in GENERATION_FIELD_TOKENS
            if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", searchable)
        }
        fields.update(field_hits)
        source_field = any(token in key_folded for token in SOURCE_FIELD_TOKENS)
        for token in GENERATIVE_TOOL_TOKENS:
            if token not in searchable:
                continue
            if token in UNAMBIGUOUS_TOOL_TOKENS or source_field or field_hits:
                tools.add(token)
    return tuple(sorted(tools)), tuple(sorted(fields))


def _residual_anomaly(grayscale: np.ndarray) -> dict[str, Any] | None:
    height, width = grayscale.shape
    columns = min(6, width // MIN_TILE_SIDE)
    rows = min(6, height // MIN_TILE_SIDE)
    if columns < 3 or rows < 3:
        return None

    source = grayscale.astype(np.float32)
    residual = cv2.absdiff(source, cv2.GaussianBlur(source, (0, 0), 1.2))
    tile_scores: list[tuple[float, tuple[int, int, int, int]]] = []
    for row in range(rows):
        y0 = round(row * height / rows)
        y1 = round((row + 1) * height / rows)
        for column in range(columns):
            x0 = round(column * width / columns)
            x1 = round((column + 1) * width / columns)
            tile = residual[y0:y1, x0:x1]
            tile_scores.append((float(np.mean(tile)), (x0, y0, x1, y1)))

    values = np.asarray([item[0] for item in tile_scores], dtype=np.float64)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    maximum_index = int(np.argmax(values))
    maximum, bbox = tile_scores[maximum_index]
    robust_z = (maximum - median) / max(1e-6, 1.4826 * mad)
    ratio = maximum / max(1e-6, median)
    return {
        "anomalous": bool(
            maximum >= 2.0
            and robust_z >= ANOMALY_Z_THRESHOLD
            and ratio >= ANOMALY_RATIO_THRESHOLD
        ),
        "bbox": bbox,
        "columns": columns,
        "maximum_mean_residual": round(maximum, 6),
        "median_mean_residual": round(median, 6),
        "residual_ratio": round(ratio, 6),
        "robust_z": round(robust_z, 6),
        "rows": rows,
    }


def inspect_image_forensics(
    data: bytes,
    *,
    asset_sha256: str,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> ImageForensicsResult:
    """Inspect metadata and localized residual consistency without model overclaiming."""

    if hashlib.sha256(data).hexdigest() != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied image bytes")
    if max_pixels < 1:
        raise ValueError("max_pixels must be positive")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            width, height = opened.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise ValueError("image exceeds the configured pixel budget")
            opened.load()
            metadata = _extract_metadata(opened)
            grayscale = np.asarray(ImageOps.exif_transpose(opened).convert("L"), dtype=np.uint8)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as error:
        reason = "The image forensic adapter could not decode the asset within its safety budget."
        evidence_id = f"evidence.image-forensics-failure-{asset_sha256[:16]}"
        return ImageForensicsResult(
            component=_component(ComponentState.DEGRADED, reason),
            evidence=(
                EvidencePointer(
                    evidence_id=evidence_id,
                    asset_sha256=asset_sha256,
                    kind=EvidenceKind.COMPONENT_FAILURE,
                    source="RightsGate deterministic image forensic triage",
                    component_id=COMPONENT_ID,
                    component_version=COMPONENT_VERSION,
                    polarity=EvidencePolarity.NEUTRAL,
                    confidence=1,
                    locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                    summary=reason,
                    payload_sha256=hashlib.sha256(str(error).encode("utf-8")).hexdigest(),
                ),
            ),
            assessment=ProvenanceAssessment(
                state=AssessmentState.UNAVAILABLE,
                verdict=ProvenanceVerdict.UNKNOWN,
                confidence=0,
                claims=(
                    ClaimRecord(
                        claim_id=f"claim.image-forensics-{asset_sha256[:16]}",
                        dimension=ClaimDimension.PROVENANCE,
                        claim_type="forensics.image-origin",
                        statement="Independent image signals support an origin assessment.",
                        outcome=ClaimOutcome.NOT_ASSESSED,
                        confidence=0,
                        mandatory=False,
                        limitations=(reason,),
                    ),
                ),
                limitations=(reason,),
            ),
        )

    tools, fields = _metadata_markers(metadata)
    anomaly = _residual_anomaly(grayscale)
    evidence: list[EvidencePointer] = []
    claims: list[ClaimRecord] = []
    limitations = [
        "This deterministic triage is not a universal or calibrated AI-generator classifier.",
        "Pixel-statistics anomalies can have benign editing, compression or scene-content causes.",
    ]

    if tools:
        partial = any(token in " ".join(tools + fields) for token in PARTIAL_EDIT_TOKENS)
        verdict = (
            ProvenanceVerdict.PARTIALLY_GENERATED
            if partial
            else ProvenanceVerdict.AI_GENERATED
        )
        confidence = 0.85 if fields else 0.70
        marker_payload = {
            "asset_sha256": asset_sha256,
            "field_markers": fields,
            "metadata_keys": sorted(metadata),
            "tool_markers": tools,
        }
        evidence_id = f"evidence.generative-metadata-{asset_sha256[:16]}"
        evidence.append(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.METADATA,
                source="Bounded image metadata inspection",
                component_id=COMPONENT_ID,
                component_version=COMPONENT_VERSION,
                polarity=EvidencePolarity.SUPPORTS,
                confidence=confidence,
                locator=EvidenceLocator(
                    kind=LocatorKind.METADATA_PATH,
                    metadata_path="image.metadata",
                ),
                summary="Image metadata contains recognized generative-tool markers.",
                payload_sha256=_canonical_hash(marker_payload),
                attributes={
                    "field_markers": ",".join(fields),
                    "marker_count": len(tools) + len(fields),
                    "tool_markers": ",".join(tools),
                },
            )
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim.generative-metadata-{asset_sha256[:16]}",
                dimension=ClaimDimension.PROVENANCE,
                claim_type="metadata.generative-source",
                statement="Recognized image metadata declares generative tooling.",
                outcome=ClaimOutcome.SUPPORTED,
                confidence=confidence,
                mandatory=False,
                evidence_ids=(evidence_id,),
                limitations=(
                    "Metadata is self-declared and can be stripped or forged; corroboration is required.",
                ),
            )
        )
    else:
        verdict = ProvenanceVerdict.UNKNOWN
        confidence = 0.0
        claims.append(
            ClaimRecord(
                claim_id=f"claim.generative-metadata-{asset_sha256[:16]}",
                dimension=ClaimDimension.PROVENANCE,
                claim_type="metadata.generative-source",
                statement="Recognized image metadata declares generative tooling.",
                outcome=ClaimOutcome.UNKNOWN,
                confidence=0,
                mandatory=False,
                limitations=(
                    "No recognized marker was present; absence is not evidence of human authorship.",
                ),
            )
        )

    if anomaly is not None:
        anomaly_payload = {"asset_sha256": asset_sha256, **anomaly}
        evidence_id = f"evidence.pixel-residual-{asset_sha256[:16]}"
        signal_confidence = (
            min(0.95, 0.5 + 0.05 * min(9.0, float(anomaly["robust_z"])))
            if anomaly["anomalous"]
            else 0.0
        )
        evidence.append(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.FORENSIC_SIGNAL,
                source="Deterministic high-pass residual tile analysis",
                component_id=COMPONENT_ID,
                component_version=COMPONENT_VERSION,
                polarity=(
                    EvidencePolarity.SUPPORTS
                    if anomaly["anomalous"]
                    else EvidencePolarity.NEUTRAL
                ),
                confidence=signal_confidence,
                locator=(
                    EvidenceLocator(kind=LocatorKind.REGION, bbox=anomaly["bbox"])
                    if anomaly["anomalous"]
                    else EvidenceLocator(kind=LocatorKind.WHOLE_ASSET)
                ),
                summary=(
                    "A localized pixel-residual inconsistency exceeded the review threshold."
                    if anomaly["anomalous"]
                    else "No pixel-residual tile exceeded the conservative review threshold."
                ),
                payload_sha256=_canonical_hash(anomaly_payload),
                attributes={
                    "anomalous": anomaly["anomalous"],
                    "residual_ratio": anomaly["residual_ratio"],
                    "robust_z": anomaly["robust_z"],
                    "tile_columns": anomaly["columns"],
                    "tile_rows": anomaly["rows"],
                },
            )
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim.pixel-residual-{asset_sha256[:16]}",
                dimension=ClaimDimension.PROVENANCE,
                claim_type="forensics.localized-residual-anomaly",
                statement="The image contains a localized pixel-statistics anomaly.",
                outcome=(
                    ClaimOutcome.SUPPORTED
                    if anomaly["anomalous"]
                    else ClaimOutcome.CONTRADICTED
                ),
                confidence=signal_confidence if anomaly["anomalous"] else 1,
                mandatory=False,
                evidence_ids=(evidence_id,),
                limitations=(
                    "The anomaly is non-attributive and cannot by itself prove AI editing or tampering.",
                ),
            )
        )

    return ImageForensicsResult(
        component=_component(ComponentState.AVAILABLE),
        evidence=tuple(evidence),
        assessment=ProvenanceAssessment(
            state=AssessmentState.COMPLETE,
            verdict=verdict,
            confidence=confidence,
            claims=tuple(claims),
            limitations=tuple(limitations) if verdict == ProvenanceVerdict.UNKNOWN else (),
        ),
    )
