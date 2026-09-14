"""Trusted, fail-closed orchestration for the implemented RightsGate lanes."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from typing import Any

import c2pa
from PIL import Image

from app.core.enums import FileType
from app.ingestion.validator import ValidationError as UploadValidationError
from app.ingestion.validator import sanitize_filename, validate_upload

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
from .provenance import verify_c2pa
from .rights import (
    LicenceEvaluationResult,
    LicenceRegistry,
    ReferenceKind,
    RightsImageMatchResult,
    RightsReferenceRegistry,
    evaluate_candidate_licences,
    match_reference_image,
)
from .rights.image_registry import COMPONENT_VERSION as IMAGE_REGISTRY_COMPONENT_VERSION
from .rights.licensing import COMPONENT_VERSION as LICENCE_COMPONENT_VERSION

KNOWN_UNIMPLEMENTED_COMPONENTS: dict[str, tuple[str, str]] = {
    "provenance.independent-forensics": (
        "provenance.forensic-detector",
        "Independent AI-media forensic detection is not implemented.",
    ),
    "provenance.watermark-forensics": (
        "provenance.watermark-detector",
        "General invisible-watermark and metadata-tampering detection is not implemented.",
    ),
    "rights.trademark-localizer": (
        "rights.trademark-detector",
        "Trademark and logo localization is not implemented.",
    ),
    "rights.likeness-consent": (
        "rights.consented-likeness-detector",
        "Consented likeness comparison is not implemented.",
    ),
    "rights.voice-consent": (
        "rights.consented-voice-detector",
        "Consented voice comparison is not implemented.",
    ),
}
EXECUTOR_VERSION = "1.0.0"
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
    max_hamming_distance: int = 6,
) -> str:
    """Bind idempotency to every governed input, not only caller metadata."""

    return _canonical_hash(
        {
            "licence_registry_sha256": licence_registry.commitment_sha256(),
            "executor_version": EXECUTOR_VERSION,
            "component_versions": {
                "provenance.c2pa": c2pa.__version__,
                "rights.local-image-registry": IMAGE_REGISTRY_COMPONENT_VERSION,
                "rights.licence-evaluator": LICENCE_COMPONENT_VERSION,
                "deployment.policy-compiler": POLICY_COMPONENT_VERSION,
            },
            "max_hamming_distance": max_hamming_distance,
            "policy_sha256": policy.commitment_sha256(),
            "request_sha256": request.request_sha256(),
            "rights_registry_sha256": rights_registry.commitment_sha256(),
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
    try:
        file_type, media_type, actual_sha256 = validate_upload(
            data,
            sanitize_filename(descriptor.original_filename),
        )
    except UploadValidationError as error:
        raise ExecutionInputError(str(error)) from error
    if file_type != FileType.IMAGE or descriptor.media_kind != MediaKind.IMAGE:
        raise ExecutionInputError(
            "the current trusted executor accepts image assets only; "
            "video and audio remain fail-closed"
        )
    if actual_sha256 != descriptor.sha256:
        raise ExecutionInputError("uploaded bytes do not match the AssetIR SHA-256")
    if len(data) != descriptor.size_bytes:
        raise ExecutionInputError("uploaded bytes do not match the AssetIR size")
    if media_type != descriptor.media_type:
        raise ExecutionInputError("detected media type does not match the AssetIR media type")
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    if (width, height) != (descriptor.width, descriptor.height):
        raise ExecutionInputError("decoded image dimensions do not match the AssetIR")


def _combine_rights(
    image_result: RightsImageMatchResult,
    licence_result: LicenceEvaluationResult,
) -> RightsAssessment:
    claims: tuple[ClaimRecord, ...] = image_result.assessment.claims + licence_result.claims
    limitations = tuple(
        sorted(set(image_result.assessment.limitations + licence_result.limitations))
    )
    if image_result.assessment.state == AssessmentState.UNAVAILABLE:
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
        return RightsAssessment(
            state=AssessmentState.PARTIAL,
            verdict=RightsVerdict.POTENTIAL_EXPOSURE,
            confidence=image_result.assessment.confidence,
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
        max_hamming_distance=max_hamming_distance,
    )

    provenance_result = verify_c2pa(data, descriptor.media_type, descriptor.sha256)
    image_result = match_reference_image(
        data,
        asset_sha256=descriptor.sha256,
        registry=rights_registry,
        max_hamming_distance=max_hamming_distance,
    )
    licence_result = evaluate_candidate_licences(
        image_result,
        asset_sha256=descriptor.sha256,
        context=request.context,
        registry=licence_registry,
        assessed_at=created_at,
    )
    rights = _combine_rights(image_result, licence_result)

    components = [
        ComponentRecord(
            component_id=EXECUTOR_COMPONENT_ID,
            component_version=EXECUTOR_VERSION,
            component_type="orchestration.trusted-image-executor",
            state=ComponentState.AVAILABLE,
            mandatory=True,
        ),
        provenance_result.component,
        image_result.component,
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
        provenance=provenance_result.assessment,
        rights=rights,
        licence=licence_result,
        components=tuple(components),
    )
    components.append(policy_result.component)
    evidence = tuple(
        sorted(
            provenance_result.evidence
            + image_result.evidence
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
        provenance=provenance_result.assessment,
        rights=rights,
        deployment=policy_result.assessment,
    )
