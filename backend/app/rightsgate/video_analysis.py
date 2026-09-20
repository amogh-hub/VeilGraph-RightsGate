"""Bounded full-timeline video triage for RightsGate.

Every physical frame is first change-screened by VeilGraph's existing video
guard. The evidence frames and every materially novel frame then enter the
image forensic, reference-retrieval and localization lanes. A hard analysis
budget is explicit and degrades the sampler instead of silently claiming full
detector coverage.
"""

from __future__ import annotations

import hashlib
import io
from typing import Iterable

from PIL import Image

from app.extraction.video import VideoInfo, physical_frame, security_scan_frame_indices

from .contracts import (
    AssessmentState,
    ClaimRecord,
    ComponentRecord,
    ComponentState,
    EvidenceLocator,
    EvidencePointer,
    LocatorKind,
    ProvenanceAssessment,
    ProvenanceVerdict,
    RightsAssessment,
    RightsVerdict,
    StrictFrozenModel,
)
from .provenance import inspect_image_forensics
from .rights import (
    LocalizedReferenceMatchResult,
    RightsImageMatchResult,
    RightsReferenceRegistry,
    localize_reference_images,
    match_reference_image,
)

COMPONENT_ID = "ingestion.video-timeline-analyzer"
COMPONENT_VERSION = "1.0.0"
COMPONENT_TYPE = "ingestion.full-timeline-change-screen"
DEFAULT_MAX_DEEP_FRAMES = 120


class VideoVisualAnalysisResult(StrictFrozenModel):
    sampler_component: ComponentRecord
    detector_components: tuple[ComponentRecord, ...]
    evidence: tuple[EvidencePointer, ...]
    forensic_assessment: ProvenanceAssessment
    image_match: RightsImageMatchResult
    localization: LocalizedReferenceMatchResult
    total_frames: int
    change_screened_frames: int
    deep_analyzed_frame_indices: tuple[int, ...]


def _frame_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def _bounded_indices(indices: tuple[int, ...], limit: int) -> tuple[int, ...]:
    if limit < 2:
        raise ValueError("video deep-analysis frame limit must be at least two")
    if len(indices) <= limit:
        return indices
    # Deterministic integer spacing retains the first and last security-selected
    # frame without importing floating-point sampling behavior.
    positions = {
        round(index * (len(indices) - 1) / (limit - 1))
        for index in range(limit)
    }
    return tuple(indices[position] for position in sorted(positions))


def _frame_locator(
    locator: EvidenceLocator,
    *,
    frame_index: int,
    info: VideoInfo,
) -> EvidenceLocator:
    if locator.kind == LocatorKind.REGION:
        return EvidenceLocator(
            kind=LocatorKind.REGION,
            frame_index=frame_index,
            bbox=locator.bbox,
        )
    start = frame_index / info.fps
    end = min(info.duration_seconds, (frame_index + 1) / info.fps)
    if end <= start:
        end = start + 1 / info.fps
    return EvidenceLocator(
        kind=LocatorKind.TIME_RANGE,
        start_seconds=round(start, 6),
        end_seconds=round(end, 6),
    )


def _map_frame_outputs(
    evidence: tuple[EvidencePointer, ...],
    claims: tuple[ClaimRecord, ...],
    *,
    root_asset_sha256: str,
    frame_sha256: str,
    frame_index: int,
    info: VideoInfo,
) -> tuple[tuple[EvidencePointer, ...], tuple[ClaimRecord, ...]]:
    evidence_ids = {
        item.evidence_id: f"{item.evidence_id}-f{frame_index}"
        for item in evidence
    }
    mapped_evidence = tuple(
        item.model_copy(
            update={
                "evidence_id": evidence_ids[item.evidence_id],
                "asset_sha256": root_asset_sha256,
                "locator": _frame_locator(item.locator, frame_index=frame_index, info=info),
                "attributes": {
                    **item.attributes,
                    "derived_frame_sha256": frame_sha256,
                    "frame_index": frame_index,
                    "timestamp_seconds": round(frame_index / info.fps, 6),
                },
            }
        )
        for item in evidence
    )
    mapped_claims = tuple(
        item.model_copy(
            update={
                "claim_id": f"{item.claim_id}-f{frame_index}",
                "evidence_ids": tuple(evidence_ids[value] for value in item.evidence_ids),
            }
        )
        for item in claims
    )
    return mapped_evidence, mapped_claims


def _aggregate_component(records: Iterable[ComponentRecord]) -> ComponentRecord:
    values = tuple(records)
    if not values:
        raise ValueError("at least one component record is required")
    first = values[0]
    states = {item.state for item in values}
    if ComponentState.UNAVAILABLE in states:
        state = ComponentState.UNAVAILABLE
    elif ComponentState.DEGRADED in states:
        state = ComponentState.DEGRADED
    else:
        state = ComponentState.AVAILABLE
    reasons = sorted({item.reason for item in values if item.reason})
    return first.model_copy(
        update={
            "state": state,
            "reason": "; ".join(reasons)[:500] if reasons else None,
        }
    )


def _aggregate_forensics(
    assessments: tuple[ProvenanceAssessment, ...],
) -> ProvenanceAssessment:
    claims = tuple(claim for item in assessments for claim in item.claims)
    limitations = tuple(sorted({value for item in assessments for value in item.limitations}))
    states = {item.state for item in assessments}
    state = (
        AssessmentState.UNAVAILABLE
        if states == {AssessmentState.UNAVAILABLE}
        else AssessmentState.PARTIAL
        if AssessmentState.UNAVAILABLE in states or AssessmentState.PARTIAL in states
        else AssessmentState.COMPLETE
    )
    conclusive = tuple(item for item in assessments if item.verdict != ProvenanceVerdict.UNKNOWN)
    if conclusive:
        strongest = max(conclusive, key=lambda item: item.confidence)
        verdict = strongest.verdict
        confidence = strongest.confidence
    else:
        verdict = ProvenanceVerdict.UNKNOWN
        confidence = 0.0
        limitations = tuple(
            sorted(
                set(
                    limitations
                    + (
                        "Frame forensic triage found no attributable origin signal; "
                        "absence is not evidence of human authorship.",
                    )
                )
            )
        )
    return ProvenanceAssessment(
        state=state,
        verdict=verdict,
        confidence=confidence,
        claims=claims,
        limitations=limitations if verdict == ProvenanceVerdict.UNKNOWN else (),
    )


def _aggregate_image_matches(
    components: tuple[ComponentRecord, ...],
    evidence: tuple[EvidencePointer, ...],
    claims: tuple[ClaimRecord, ...],
    assessments: tuple[RightsAssessment, ...],
) -> RightsImageMatchResult:
    candidates = tuple(item for item in assessments if item.verdict == RightsVerdict.POTENTIAL_EXPOSURE)
    limitations = tuple(sorted({value for item in assessments for value in item.limitations}))
    state = (
        AssessmentState.UNAVAILABLE
        if all(item.state == AssessmentState.UNAVAILABLE for item in assessments)
        else AssessmentState.PARTIAL
        if any(item.state != AssessmentState.COMPLETE for item in assessments)
        else AssessmentState.COMPLETE
    )
    return RightsImageMatchResult(
        component=_aggregate_component(components),
        evidence=evidence,
        assessment=RightsAssessment(
            state=state,
            verdict=(RightsVerdict.POTENTIAL_EXPOSURE if candidates else RightsVerdict.UNKNOWN),
            confidence=max((item.confidence for item in candidates), default=0.0),
            claims=claims,
            limitations=tuple(
                sorted(
                    set(
                        limitations
                        + (
                            "Video rights retrieval covers deep-analyzed visual frames and "
                            "does not establish open-world clearance.",
                        )
                    )
                )
            ),
        ),
    )


def analyze_video_visuals(
    data: bytes,
    *,
    source_filename: str,
    asset_sha256: str,
    registry: RightsReferenceRegistry,
    max_hamming_distance: int = 6,
    max_deep_frames: int = DEFAULT_MAX_DEEP_FRAMES,
) -> VideoVisualAnalysisResult:
    """Change-screen the entire timeline and deeply inspect selected frames."""

    if hashlib.sha256(data).hexdigest() != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied video bytes")
    info, security_indices, statistics = security_scan_frame_indices(data, source_filename)
    selected = _bounded_indices(security_indices, max_deep_frames)
    truncated = len(selected) < len(security_indices)

    mapped_forensic_evidence: list[EvidencePointer] = []
    mapped_forensic_claims: list[ClaimRecord] = []
    forensic_assessments: list[ProvenanceAssessment] = []
    forensic_components: list[ComponentRecord] = []
    mapped_match_evidence: list[EvidencePointer] = []
    mapped_match_claims: list[ClaimRecord] = []
    match_assessments: list[RightsAssessment] = []
    match_components: list[ComponentRecord] = []
    mapped_localization_evidence: list[EvidencePointer] = []
    mapped_localization_claims: list[ClaimRecord] = []
    localization_components: list[ComponentRecord] = []
    localization_candidates: set[str] = set()
    localization_limitations: set[str] = set()

    for frame_index in selected:
        frame, _, _ = physical_frame(data, frame_index, source_filename)
        frame_data = _frame_png(frame)
        frame_sha256 = hashlib.sha256(frame_data).hexdigest()

        forensic = inspect_image_forensics(frame_data, asset_sha256=frame_sha256)
        forensic_evidence, forensic_claims = _map_frame_outputs(
            forensic.evidence,
            forensic.assessment.claims,
            root_asset_sha256=asset_sha256,
            frame_sha256=frame_sha256,
            frame_index=frame_index,
            info=info,
        )
        mapped_forensic_evidence.extend(forensic_evidence)
        mapped_forensic_claims.extend(forensic_claims)
        forensic_assessments.append(
            forensic.assessment.model_copy(update={"claims": forensic_claims})
        )
        forensic_components.append(forensic.component)

        match = match_reference_image(
            frame_data,
            asset_sha256=frame_sha256,
            registry=registry,
            max_hamming_distance=max_hamming_distance,
        )
        match_evidence, match_claims = _map_frame_outputs(
            match.evidence,
            match.assessment.claims,
            root_asset_sha256=asset_sha256,
            frame_sha256=frame_sha256,
            frame_index=frame_index,
            info=info,
        )
        mapped_match_evidence.extend(match_evidence)
        mapped_match_claims.extend(match_claims)
        match_assessments.append(match.assessment.model_copy(update={"claims": match_claims}))
        match_components.append(match.component)

        localized = localize_reference_images(
            frame_data,
            asset_sha256=frame_sha256,
            registry=registry,
        )
        localized_evidence, localized_claims = _map_frame_outputs(
            localized.evidence,
            localized.claims,
            root_asset_sha256=asset_sha256,
            frame_sha256=frame_sha256,
            frame_index=frame_index,
            info=info,
        )
        mapped_localization_evidence.extend(localized_evidence)
        mapped_localization_claims.extend(localized_claims)
        localization_components.append(localized.component)
        localization_candidates.update(localized.candidate_reference_ids)
        localization_limitations.update(localized.limitations)

    deep_coverage_reason = (
        f"Deep visual detectors analyzed {len(selected)}/{len(security_indices)} "
        "security-selected frames after the full physical timeline change screen."
    )
    sampler_component = ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        component_type=COMPONENT_TYPE,
        state=ComponentState.DEGRADED if truncated else ComponentState.AVAILABLE,
        mandatory=True,
        artifact_sha256=hashlib.sha256(
            repr((info.total_frames, security_indices, selected, statistics)).encode("utf-8")
        ).hexdigest(),
        reason=deep_coverage_reason if truncated else None,
    )
    image_match = _aggregate_image_matches(
        tuple(match_components),
        tuple(mapped_match_evidence),
        tuple(mapped_match_claims),
        tuple(match_assessments),
    )
    localization_component = _aggregate_component(localization_components)
    if truncated:
        localization_limitations.add(deep_coverage_reason)
    localization = LocalizedReferenceMatchResult(
        component=localization_component,
        evidence=tuple(mapped_localization_evidence),
        claims=tuple(mapped_localization_claims),
        candidate_reference_ids=tuple(sorted(localization_candidates)),
        limitations=tuple(sorted(localization_limitations)),
    )
    return VideoVisualAnalysisResult(
        sampler_component=sampler_component,
        detector_components=(
            _aggregate_component(forensic_components),
            image_match.component,
            localization_component,
        ),
        evidence=tuple(
            mapped_forensic_evidence
            + mapped_match_evidence
            + mapped_localization_evidence
        ),
        forensic_assessment=_aggregate_forensics(tuple(forensic_assessments)),
        image_match=image_match,
        localization=localization,
        total_frames=info.total_frames,
        change_screened_frames=int(statistics["physical_frames_change_screened"]),
        deep_analyzed_frame_indices=selected,
    )
