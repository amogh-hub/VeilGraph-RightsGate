"""Trusted, fail-closed orchestration for the implemented RightsGate lanes."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from typing import Any

import c2pa
from PIL import Image

from app.core.config import settings
from app.core.enums import FileType
from app.extraction.video import probe_video
from app.ingestion.validator import ValidationError as UploadValidationError
from app.ingestion.validator import sanitize_filename, validate_upload

from .audio_analysis import (
    COMPONENT_VERSION as AUDIO_ANALYZER_COMPONENT_VERSION,
    inspect_pcm_wav,
)
from .contracts import (
    AssessmentState,
    AssetExposureGraph,
    ClaimRecord,
    ComponentRecord,
    ComponentState,
    EvidenceKind,
    EvidencePointer,
    ExposureGraphEdge,
    ExposureGraphNode,
    GraphEdgeKind,
    GraphNodeKind,
    MediaKind,
    ProvenanceAssessment,
    ProvenanceVerdict,
    RightsAssessment,
    RightsGateAssessment,
    RightsGateAssessmentRequest,
    RightsVerdict,
)
from .policy import (
    COMPONENT_VERSION as POLICY_COMPONENT_VERSION,
    PublicationPolicy,
    evaluate_publication_policy,
)
from .provenance import (
    VisibleWatermarkRegistry,
    inspect_image_forensics,
    verify_c2pa,
    verify_visible_watermarks,
)
from .provenance.image_forensics import COMPONENT_VERSION as FORENSICS_COMPONENT_VERSION
from .provenance.watermark import COMPONENT_VERSION as WATERMARK_COMPONENT_VERSION
from .rights import (
    ConsentAnalysisResult,
    ConsentRegistry,
    LicenceEvaluationResult,
    LicenceRegistry,
    LocalizedReferenceMatchResult,
    ReferenceKind,
    RightsImageMatchResult,
    RightsReferenceRegistry,
    analyze_likeness_consent,
    analyze_voice_consent,
    evaluate_candidate_licences,
    localize_reference_images,
    match_reference_image,
)
from .rights.image_registry import COMPONENT_VERSION as IMAGE_REGISTRY_COMPONENT_VERSION
from .rights.licensing import COMPONENT_VERSION as LICENCE_COMPONENT_VERSION
from .rights.localization import COMPONENT_VERSION as LOCALIZER_COMPONENT_VERSION
from .rights.consent import COMPONENT_VERSION as CONSENT_COMPONENT_VERSION
from .video_analysis import (
    COMPONENT_VERSION as VIDEO_ANALYZER_COMPONENT_VERSION,
    analyze_video_visuals,
)

KNOWN_UNIMPLEMENTED_COMPONENTS: dict[str, tuple[str, str]] = {
    "provenance.watermark-forensics": (
        "provenance.governed-visible-watermark-verifier",
        "No governed visible-watermark registry was supplied; arbitrary invisible watermark detection remains unsupported.",
    ),
    "rights.likeness-consent": (
        "rights.consented-likeness-detector",
        "No governed consent registry was supplied for bounded enrolled-likeness matching.",
    ),
    "rights.voice-consent": (
        "rights.consented-voice-detector",
        "No governed consent registry was supplied for bounded enrolled-voice matching.",
    ),
}
EXECUTOR_VERSION = "1.3.0"
EXECUTOR_COMPONENT_ID = "orchestration.executor"


class ExecutionInputError(ValueError):
    """Raised when uploaded bytes do not match the contracted execution input."""


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def execution_fingerprint(
    request: RightsGateAssessmentRequest,
    *,
    rights_registry: RightsReferenceRegistry,
    licence_registry: LicenceRegistry,
    policy: PublicationPolicy,
    watermark_registry: VisibleWatermarkRegistry | None = None,
    consent_registry: ConsentRegistry | None = None,
    max_hamming_distance: int = 6,
) -> str:
    """Bind idempotency to every governed input, not only caller metadata."""

    return _canonical_hash(
        {
            "licence_registry_sha256": licence_registry.commitment_sha256(),
            "executor_version": EXECUTOR_VERSION,
            "component_versions": {
                "provenance.c2pa": c2pa.__version__,
                "provenance.independent-forensics": FORENSICS_COMPONENT_VERSION,
                "provenance.watermark-forensics": WATERMARK_COMPONENT_VERSION,
                "rights.local-image-registry": IMAGE_REGISTRY_COMPONENT_VERSION,
                "rights.licence-evaluator": LICENCE_COMPONENT_VERSION,
                "rights.trademark-localizer": LOCALIZER_COMPONENT_VERSION,
                "rights.consent-reference-matcher": CONSENT_COMPONENT_VERSION,
                "ingestion.video-timeline-analyzer": VIDEO_ANALYZER_COMPONENT_VERSION,
                "ingestion.pcm-wav-parser": AUDIO_ANALYZER_COMPONENT_VERSION,
                "deployment.policy-compiler": POLICY_COMPONENT_VERSION,
            },
            "video_analysis": {
                "max_deep_frames": settings.max_video_evidence_frames,
                "sample_fps": settings.video_evidence_sample_fps,
            },
            "max_hamming_distance": max_hamming_distance,
            "consent_registry_sha256": (
                consent_registry.commitment_sha256() if consent_registry is not None else None
            ),
            "policy_sha256": policy.commitment_sha256(),
            "request_sha256": request.request_sha256(),
            "rights_registry_sha256": rights_registry.commitment_sha256(),
            "watermark_registry_sha256": (
                watermark_registry.commitment_sha256()
                if watermark_registry is not None
                else None
            ),
        }
    )


def validate_governed_inputs(
    *,
    request: RightsGateAssessmentRequest,
    rights_registry: RightsReferenceRegistry,
    licence_registry: LicenceRegistry,
    policy: PublicationPolicy,
) -> None:
    if (
        request.context.policy_id != policy.policy_id
        or request.context.policy_version != policy.version
    ):
        raise ExecutionInputError("assessment context does not match the supplied policy identity")
    reference_ids = {item.reference_id for item in rights_registry.references}
    licence_reference_ids = {
        reference_id
        for licence in licence_registry.licences
        for reference_id in licence.reference_ids
    }
    orphaned = sorted(licence_reference_ids - reference_ids)
    if orphaned:
        raise ExecutionInputError(
            "licence registry references IDs absent from the supplied rights registry: "
            + ",".join(orphaned)
        )


def validate_execution_asset(data: bytes, request: RightsGateAssessmentRequest) -> None:
    descriptor = request.asset_ir.asset
    if descriptor.media_kind == MediaKind.AUDIO:
        if not data or len(data) > settings.max_file_size_bytes:
            raise ExecutionInputError("audio is empty or exceeds the configured upload limit")
        if not sanitize_filename(descriptor.original_filename).lower().endswith(".wav"):
            raise ExecutionInputError("standalone audio currently requires a .wav filename")
        if descriptor.media_type not in {"audio/wav", "audio/x-wav"}:
            raise ExecutionInputError("standalone audio currently requires audio/wav")
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != descriptor.sha256:
            raise ExecutionInputError("uploaded bytes do not match the AssetIR SHA-256")
        if len(data) != descriptor.size_bytes:
            raise ExecutionInputError("uploaded bytes do not match the AssetIR size")
        try:
            inspected = inspect_pcm_wav(data, asset_sha256=descriptor.sha256)
        except ValueError as error:
            raise ExecutionInputError(str(error)) from error
        assert descriptor.duration_seconds is not None
        if abs(inspected.stream.duration_seconds - descriptor.duration_seconds) > (
            1 / inspected.stream.sample_rate_hz
        ):
            raise ExecutionInputError("decoded audio duration does not match the AssetIR")
        return
    try:
        file_type, media_type, actual_sha256 = validate_upload(
            data,
            sanitize_filename(descriptor.original_filename),
        )
    except UploadValidationError as error:
        raise ExecutionInputError(str(error)) from error
    expected_file_type = {
        MediaKind.IMAGE: FileType.IMAGE,
        MediaKind.VIDEO: FileType.VIDEO,
    }.get(descriptor.media_kind)
    if expected_file_type is None:
        raise ExecutionInputError(
            "the current trusted executor accepts image, bounded video and PCM/WAV audio assets"
        )
    if file_type != expected_file_type:
        raise ExecutionInputError("detected media kind does not match the AssetIR media kind")
    if actual_sha256 != descriptor.sha256:
        raise ExecutionInputError("uploaded bytes do not match the AssetIR SHA-256")
    if len(data) != descriptor.size_bytes:
        raise ExecutionInputError("uploaded bytes do not match the AssetIR size")
    if media_type != descriptor.media_type:
        raise ExecutionInputError("detected media type does not match the AssetIR media type")
    if descriptor.media_kind == MediaKind.IMAGE:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
        if (width, height) != (descriptor.width, descriptor.height):
            raise ExecutionInputError("decoded image dimensions do not match the AssetIR")
    else:
        info = probe_video(data, descriptor.original_filename)
        if descriptor.width is None or descriptor.height is None:
            raise ExecutionInputError("video AssetIR requires decoded width and height")
        if (info.width, info.height) != (descriptor.width, descriptor.height):
            raise ExecutionInputError("decoded video dimensions do not match the AssetIR")
        assert descriptor.duration_seconds is not None
        # Container frame counts can differ by less than one frame across
        # decoders. Anything outside that tolerance is a binding failure.
        if abs(info.duration_seconds - descriptor.duration_seconds) > 1 / info.fps:
            raise ExecutionInputError("decoded video duration does not match the AssetIR")


def _combine_rights(
    image_result: RightsImageMatchResult,
    localization_result: LocalizedReferenceMatchResult,
    licence_result: LicenceEvaluationResult,
) -> RightsAssessment:
    claims: tuple[ClaimRecord, ...] = (
        image_result.assessment.claims
        + localization_result.claims
        + licence_result.claims
    )
    limitations = tuple(
        sorted(
            set(
                image_result.assessment.limitations
                + localization_result.limitations
                + licence_result.limitations
            )
        )
    )
    if (
        image_result.assessment.state == AssessmentState.UNAVAILABLE
        and localization_result.component.state != ComponentState.AVAILABLE
    ):
        return RightsAssessment(
            state=AssessmentState.UNAVAILABLE,
            verdict=RightsVerdict.UNKNOWN,
            confidence=0,
            claims=claims,
            limitations=limitations,
        )
    if licence_result.policy_conflict:
        return RightsAssessment(
            state=AssessmentState.COMPLETE,
            verdict=RightsVerdict.POLICY_CONFLICT,
            confidence=1,
            claims=claims,
            limitations=limitations,
        )
    if licence_result.candidate_reference_ids:
        localized_confidence = max(
            (item.confidence for item in localization_result.evidence),
            default=0,
        )
        return RightsAssessment(
            state=AssessmentState.PARTIAL,
            verdict=RightsVerdict.POTENTIAL_EXPOSURE,
            confidence=max(image_result.assessment.confidence, localized_confidence),
            claims=claims,
            limitations=tuple(
                sorted(
                    set(
                        limitations
                        + (
                            "Known candidates have explicit licence coverage, but "
                            "unimplemented rights lanes prevent global clearance.",
                        )
                    )
                )
            ),
        )
    return RightsAssessment(
        state=image_result.assessment.state,
        verdict=RightsVerdict.UNKNOWN,
        confidence=0,
        claims=claims,
        limitations=limitations,
    )


def _combine_provenance(*assessments: ProvenanceAssessment) -> ProvenanceAssessment:
    """Preserve both lanes while applying explicit, deterministic precedence."""

    if not assessments:
        raise ValueError("at least one provenance assessment is required")
    claims = tuple(claim for item in assessments for claim in item.claims)
    limitations = tuple(
        sorted({limitation for item in assessments for limitation in item.limitations})
    )
    states = {item.state for item in assessments}
    if states == {AssessmentState.UNAVAILABLE}:
        state = AssessmentState.UNAVAILABLE
    elif AssessmentState.UNAVAILABLE in states or AssessmentState.PARTIAL in states:
        state = AssessmentState.PARTIAL
    else:
        state = AssessmentState.COMPLETE

    candidates = assessments
    if any(item.verdict == ProvenanceVerdict.TAMPERED for item in candidates):
        verdict = ProvenanceVerdict.TAMPERED
        confidence = max(
            item.confidence
            for item in candidates
            if item.verdict == ProvenanceVerdict.TAMPERED
        )
    else:
        conclusive = tuple(
            item
            for item in candidates
            if item.verdict != ProvenanceVerdict.UNKNOWN
        )
        if conclusive:
            strongest = max(conclusive, key=lambda item: item.confidence)
            verdict = strongest.verdict
            confidence = strongest.confidence
        else:
            verdict = ProvenanceVerdict.UNKNOWN
            confidence = 0
    if verdict == ProvenanceVerdict.UNKNOWN and not limitations:
        limitations = ("Neither provenance lane produced a supported origin conclusion.",)
    return ProvenanceAssessment(
        state=state,
        verdict=verdict,
        confidence=confidence,
        claims=claims,
        limitations=limitations if verdict == ProvenanceVerdict.UNKNOWN else (),
    )


def _combine_consent_rights(
    base: RightsAssessment,
    results: tuple[ConsentAnalysisResult, ...],
) -> RightsAssessment:
    if not results:
        return base
    claims = base.claims + tuple(claim for result in results for claim in result.claims)
    limitations = tuple(
        sorted(
            set(
                base.limitations
                + tuple(
                    limitation
                    for result in results
                    for limitation in result.limitations
                )
            )
        )
    )
    conflicts = tuple(result for result in results if result.policy_conflict)
    candidates = tuple(result for result in results if result.candidate_subject_ids)
    if conflicts:
        return RightsAssessment(
            state=AssessmentState.COMPLETE,
            verdict=RightsVerdict.POLICY_CONFLICT,
            confidence=max(result.confidence for result in conflicts),
            claims=claims,
            limitations=limitations,
        )
    if candidates and base.verdict != RightsVerdict.POLICY_CONFLICT:
        return RightsAssessment(
            state=AssessmentState.PARTIAL,
            verdict=RightsVerdict.POTENTIAL_EXPOSURE,
            confidence=max(base.confidence, *(result.confidence for result in candidates)),
            claims=claims,
            limitations=limitations,
        )
    return base.model_copy(update={"claims": claims, "limitations": limitations})


def _declared_unavailable_component(component_id: str) -> ComponentRecord:
    component_type, reason = KNOWN_UNIMPLEMENTED_COMPONENTS.get(
        component_id,
        (
            "declared.required-component",
            "The policy requires a component not provided by this executor.",
        ),
    )
    return ComponentRecord(
        component_id=component_id,
        component_version="unavailable-v1",
        component_type=component_type,
        state=ComponentState.UNAVAILABLE,
        mandatory=True,
        reason=reason,
    )


def _graph_id(prefix: str, value: str) -> str:
    token = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{token}"


def _build_graph(
    *,
    request: RightsGateAssessmentRequest,
    evidence: tuple[EvidencePointer, ...],
) -> AssetExposureGraph:
    descriptor = request.asset_ir.asset
    root_id = f"node.asset-{descriptor.sha256[:16]}"
    nodes: dict[str, ExposureGraphNode] = {
        root_id: ExposureGraphNode(
            node_id=root_id,
            kind=GraphNodeKind.ASSET,
            label=descriptor.original_filename,
        )
    }
    edges: dict[str, ExposureGraphEdge] = {}
    reference_nodes: dict[str, str] = {}

    for item in evidence:
        reference_id = item.attributes.get("reference_id")
        reference_kind = item.attributes.get("reference_kind")
        if item.kind == EvidenceKind.REFERENCE_MATCH and isinstance(reference_id, str):
            node_id = _graph_id("node.reference", reference_id)
            reference_nodes[reference_id] = node_id
            kind = (
                GraphNodeKind.MARK
                if reference_kind == ReferenceKind.TRADEMARK.value
                else GraphNodeKind.WORK
            )
            nodes[node_id] = ExposureGraphNode(
                node_id=node_id,
                kind=kind,
                label=reference_id,
                evidence_ids=(item.evidence_id,),
            )
            edge_id = _graph_id("edge.candidate-match", f"{reference_id}:{descriptor.sha256}")
            edges[edge_id] = ExposureGraphEdge(
                edge_id=edge_id,
                kind=GraphEdgeKind.CANDIDATE_MATCH,
                source_node_id=root_id,
                target_node_id=node_id,
                confidence=item.confidence,
                evidence_ids=(item.evidence_id,),
            )

    for item in evidence:
        if item.kind != EvidenceKind.LICENCE_RECORD or item.attributes.get("covered") is not True:
            continue
        reference_id = item.attributes.get("reference_id")
        licence_ids = item.attributes.get("covering_licence_ids")
        if not isinstance(reference_id, str) or not isinstance(licence_ids, str):
            continue
        reference_node_id = reference_nodes.get(reference_id)
        if reference_node_id is None:
            continue
        for licence_id in filter(None, licence_ids.split(",")):
            node_id = _graph_id("node.licence", licence_id)
            nodes[node_id] = ExposureGraphNode(
                node_id=node_id,
                kind=GraphNodeKind.LICENCE,
                label=licence_id,
                evidence_ids=(item.evidence_id,),
            )
            edge_id = _graph_id("edge.covered-by", f"{reference_id}:{licence_id}")
            edges[edge_id] = ExposureGraphEdge(
                edge_id=edge_id,
                kind=GraphEdgeKind.COVERED_BY,
                source_node_id=reference_node_id,
                target_node_id=node_id,
                confidence=1,
                evidence_ids=(item.evidence_id,),
            )

    for item in evidence:
        if item.kind != EvidenceKind.CONSENT_RECORD:
            continue
        subject_id = item.attributes.get("subject_id")
        consent_id = item.attributes.get("consent_id")
        covered = item.attributes.get("covered")
        if not isinstance(subject_id, str) or not isinstance(consent_id, str):
            continue
        is_voice = item.component_id == "rights.voice-consent"
        subject_node_id = _graph_id("node.subject", f"{item.component_id}:{subject_id}")
        consent_node_id = _graph_id("node.consent", consent_id)
        nodes[subject_node_id] = ExposureGraphNode(
            node_id=subject_node_id,
            kind=GraphNodeKind.VOICE if is_voice else GraphNodeKind.PERSON,
            label=subject_id,
            evidence_ids=(item.evidence_id,),
        )
        nodes[consent_node_id] = ExposureGraphNode(
            node_id=consent_node_id,
            kind=GraphNodeKind.CONSENT,
            label=consent_id,
            evidence_ids=(item.evidence_id,),
            attributes={"covered": bool(covered)},
        )
        subject_edge_id = _graph_id(
            "edge.subject-match", f"{descriptor.sha256}:{item.component_id}:{subject_id}"
        )
        edges[subject_edge_id] = ExposureGraphEdge(
            edge_id=subject_edge_id,
            kind=GraphEdgeKind.CONTAINS_VOICE if is_voice else GraphEdgeKind.DEPICTS,
            source_node_id=root_id,
            target_node_id=subject_node_id,
            confidence=item.confidence,
            evidence_ids=(item.evidence_id,),
        )
        consent_edge_id = _graph_id(
            "edge.consented-by", f"{subject_id}:{consent_id}:{descriptor.sha256}"
        )
        edges[consent_edge_id] = ExposureGraphEdge(
            edge_id=consent_edge_id,
            kind=GraphEdgeKind.CONSENTED_BY,
            source_node_id=subject_node_id,
            target_node_id=consent_node_id,
            confidence=item.confidence,
            evidence_ids=(item.evidence_id,),
            attributes={"covered": bool(covered)},
        )

    policy_evidence = tuple(item for item in evidence if item.kind == EvidenceKind.POLICY_RULE)
    if policy_evidence:
        campaign_id = _graph_id("node.campaign", request.context.intended_use)
        policy_ids = tuple(item.evidence_id for item in policy_evidence)
        nodes[campaign_id] = ExposureGraphNode(
            node_id=campaign_id,
            kind=GraphNodeKind.CAMPAIGN,
            label=request.context.intended_use,
            evidence_ids=policy_ids,
            attributes={
                "audience": request.context.audience,
                "channel": request.context.channel,
            },
        )
        used_by_id = _graph_id("edge.used-by", f"{descriptor.sha256}:{campaign_id}")
        edges[used_by_id] = ExposureGraphEdge(
            edge_id=used_by_id,
            kind=GraphEdgeKind.USED_BY,
            source_node_id=root_id,
            target_node_id=campaign_id,
            confidence=1,
            evidence_ids=policy_ids,
        )
        for territory in request.context.territories:
            territory_id = _graph_id("node.territory", territory)
            nodes[territory_id] = ExposureGraphNode(
                node_id=territory_id,
                kind=GraphNodeKind.TERRITORY,
                label=territory,
                evidence_ids=policy_ids,
            )
            edge_id = _graph_id("edge.valid-in", f"{campaign_id}:{territory}")
            edges[edge_id] = ExposureGraphEdge(
                edge_id=edge_id,
                kind=GraphEdgeKind.VALID_IN,
                source_node_id=campaign_id,
                target_node_id=territory_id,
                confidence=1,
                evidence_ids=policy_ids,
            )

    return AssetExposureGraph(
        asset_sha256=descriptor.sha256,
        root_node_id=root_id,
        nodes=tuple(nodes.values()),
        edges=tuple(edges.values()),
    )


def execute_rightsgate_assessment(
    data: bytes,
    *,
    request: RightsGateAssessmentRequest,
    rights_registry: RightsReferenceRegistry,
    licence_registry: LicenceRegistry,
    policy: PublicationPolicy,
    watermark_registry: VisibleWatermarkRegistry | None = None,
    consent_registry: ConsentRegistry | None = None,
    created_at: datetime,
    max_hamming_distance: int = 6,
) -> RightsGateAssessment:
    """Execute every implemented lane and preserve missing mandatory capabilities."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    validate_execution_asset(data, request)
    validate_governed_inputs(
        request=request,
        rights_registry=rights_registry,
        licence_registry=licence_registry,
        policy=policy,
    )
    descriptor = request.asset_ir.asset
    fingerprint = execution_fingerprint(
        request,
        rights_registry=rights_registry,
        licence_registry=licence_registry,
        policy=policy,
        watermark_registry=watermark_registry,
        consent_registry=consent_registry,
        max_hamming_distance=max_hamming_distance,
    )

    c2pa_result = verify_c2pa(data, descriptor.media_type, descriptor.sha256)
    if descriptor.media_kind == MediaKind.IMAGE:
        forensic_result = inspect_image_forensics(
            data,
            asset_sha256=descriptor.sha256,
        )
        watermark_result = (
            verify_visible_watermarks(
                data,
                asset_sha256=descriptor.sha256,
                context=request.context,
                registry=watermark_registry,
            )
            if watermark_registry is not None
            else None
        )
        provenance = _combine_provenance(
            c2pa_result.assessment,
            forensic_result.assessment,
            *((watermark_result.assessment,) if watermark_result is not None else ()),
        )
        image_result = match_reference_image(
            data,
            asset_sha256=descriptor.sha256,
            registry=rights_registry,
            max_hamming_distance=max_hamming_distance,
        )
        localization_result = localize_reference_images(
            data,
            asset_sha256=descriptor.sha256,
            registry=rights_registry,
        )
        likeness_result = (
            analyze_likeness_consent(
                data,
                asset_sha256=descriptor.sha256,
                context=request.context,
                registry=consent_registry,
                assessed_at=created_at,
            )
            if consent_registry is not None
            else None
        )
        lane_components = (
            forensic_result.component,
            image_result.component,
            localization_result.component,
            *((watermark_result.component,) if watermark_result is not None else ()),
            *((likeness_result.component,) if likeness_result is not None else ()),
        )
        lane_evidence = (
            forensic_result.evidence
            + image_result.evidence
            + localization_result.evidence
            + (watermark_result.evidence if watermark_result is not None else ())
            + (likeness_result.evidence if likeness_result is not None else ())
        )
        consent_results = (likeness_result,) if likeness_result is not None else ()
    elif descriptor.media_kind == MediaKind.VIDEO:
        video_result = analyze_video_visuals(
            data,
            source_filename=descriptor.original_filename,
            asset_sha256=descriptor.sha256,
            registry=rights_registry,
            max_hamming_distance=max_hamming_distance,
            max_deep_frames=settings.max_video_evidence_frames,
        )
        provenance = _combine_provenance(
            c2pa_result.assessment,
            video_result.forensic_assessment,
        )
        image_result = video_result.image_match
        localization_result = video_result.localization
        lane_components = (
            video_result.sampler_component,
            *video_result.detector_components,
        )
        lane_evidence = video_result.evidence
        licence_additional_evidence = localization_result.evidence
        direct_audio_rights = None
        consent_results = ()
    else:
        audio_result = inspect_pcm_wav(data, asset_sha256=descriptor.sha256)
        provenance = _combine_provenance(c2pa_result.assessment, audio_result.provenance)
        image_result = RightsImageMatchResult(
            component=audio_result.component,
            evidence=(),
            assessment=audio_result.rights,
        )
        voice_result = (
            analyze_voice_consent(
                data,
                asset_sha256=descriptor.sha256,
                context=request.context,
                registry=consent_registry,
                assessed_at=created_at,
            )
            if consent_registry is not None
            else None
        )
        lane_components = (
            audio_result.component,
            *(
                (voice_result.component,)
                if voice_result is not None
                else (_declared_unavailable_component("rights.voice-consent"),)
            ),
        )
        lane_evidence = audio_result.evidence + (
            voice_result.evidence if voice_result is not None else ()
        )
        licence_additional_evidence = ()
        direct_audio_rights = audio_result.rights
        consent_results = (voice_result,) if voice_result is not None else ()
    if descriptor.media_kind == MediaKind.IMAGE:
        licence_additional_evidence = localization_result.evidence
        direct_audio_rights = None
    licence_result = evaluate_candidate_licences(
        image_result,
        asset_sha256=descriptor.sha256,
        context=request.context,
        registry=licence_registry,
        assessed_at=created_at,
        additional_evidence=licence_additional_evidence,
    )
    if direct_audio_rights is None:
        rights = _combine_rights(image_result, localization_result, licence_result)
    else:
        rights = direct_audio_rights.model_copy(
            update={
                "claims": direct_audio_rights.claims + licence_result.claims,
                "limitations": tuple(
                    sorted(set(direct_audio_rights.limitations + licence_result.limitations))
                ),
            }
        )
    rights = _combine_consent_rights(rights, consent_results)

    components = [
        ComponentRecord(
            component_id=EXECUTOR_COMPONENT_ID,
            component_version=EXECUTOR_VERSION,
            component_type="orchestration.trusted-media-executor",
            state=ComponentState.AVAILABLE,
            mandatory=True,
        ),
        c2pa_result.component,
        *lane_components,
        licence_result.component,
    ]
    present = {item.component_id for item in components}
    for component_id in policy.required_component_ids:
        if component_id not in present:
            components.append(_declared_unavailable_component(component_id))
            present.add(component_id)

    policy_result = evaluate_publication_policy(
        asset_sha256=descriptor.sha256,
        context=request.context,
        policy=policy,
        provenance=provenance,
        rights=rights,
        licence=licence_result,
        components=tuple(components),
    )
    components.append(policy_result.component)
    evidence = tuple(
        sorted(
            c2pa_result.evidence
            + lane_evidence
            + licence_result.evidence
            + policy_result.evidence,
            key=lambda item: item.evidence_id,
        )
    )
    graph = _build_graph(request=request, evidence=evidence)
    assessment_token = hashlib.sha256(
        f"{fingerprint}:{request.idempotency_key}".encode("utf-8")
    ).hexdigest()[:32]
    return RightsGateAssessment(
        assessment_id=f"assessment.{assessment_token}",
        created_at=created_at,
        asset=descriptor,
        context=request.context,
        components=tuple(sorted(components, key=lambda item: item.component_id)),
        evidence=evidence,
        exposure_graph=graph,
        provenance=provenance,
        rights=rights,
        deployment=policy_result.assessment,
    )
