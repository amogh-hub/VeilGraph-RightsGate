"""Versioned, detector-independent RightsGate assessment contracts.

These types deliberately separate evidence, claims, dimension verdicts and the
deployment decision. Detector adapters may contribute evidence and claims, but
only deterministic policy code should construct the deployment assessment.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ASSESSMENT_SCHEMA = "veilgraph.rightsgate.assessment.v1"
ASSET_IR_SCHEMA = "veilgraph.rightsgate.asset-ir.v1"
ASSESSMENT_REQUEST_SCHEMA = "veilgraph.rightsgate.assessment-request.v1"
EXPOSURE_GRAPH_SCHEMA = "veilgraph.rightsgate.asset-exposure-graph.v1"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^[a-z0-9][a-z0-9._:-]{0,127}$"


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        validate_default=True,
    )


class MediaKind(str, Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"


class ClaimDimension(str, Enum):
    PROVENANCE = "PROVENANCE"
    RIGHTS_EXPOSURE = "RIGHTS_EXPOSURE"
    DEPLOYMENT_READINESS = "DEPLOYMENT_READINESS"


class ClaimOutcome(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"
    NOT_ASSESSED = "NOT_ASSESSED"


class AssessmentState(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ComponentState(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceKind(str, Enum):
    CONTENT_CREDENTIAL = "CONTENT_CREDENTIAL"
    METADATA = "METADATA"
    WATERMARK = "WATERMARK"
    FORENSIC_SIGNAL = "FORENSIC_SIGNAL"
    REFERENCE_MATCH = "REFERENCE_MATCH"
    LICENCE_RECORD = "LICENCE_RECORD"
    CONSENT_RECORD = "CONSENT_RECORD"
    POLICY_RULE = "POLICY_RULE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    COMPONENT_FAILURE = "COMPONENT_FAILURE"


class EvidencePolarity(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class LocatorKind(str, Enum):
    WHOLE_ASSET = "WHOLE_ASSET"
    REGION = "REGION"
    TIME_RANGE = "TIME_RANGE"
    TEXT_RANGE = "TEXT_RANGE"
    METADATA_PATH = "METADATA_PATH"


class ProvenanceVerdict(str, Enum):
    AUTHENTIC = "AUTHENTIC"
    AI_GENERATED = "AI_GENERATED"
    PARTIALLY_GENERATED = "PARTIALLY_GENERATED"
    TAMPERED = "TAMPERED"
    UNKNOWN = "UNKNOWN"


class RightsVerdict(str, Enum):
    CLEAR = "CLEAR"
    POTENTIAL_EXPOSURE = "POTENTIAL_EXPOSURE"
    POLICY_CONFLICT = "POLICY_CONFLICT"
    UNKNOWN = "UNKNOWN"


class DeploymentDecision(str, Enum):
    GO = "GO"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class RepresentationKind(str, Enum):
    ORIGINAL = "ORIGINAL"
    VISUAL_FRAME = "VISUAL_FRAME"
    AUDIO_TRACK = "AUDIO_TRACK"
    TEXT_TRACK = "TEXT_TRACK"
    THUMBNAIL = "THUMBNAIL"


class GraphNodeKind(str, Enum):
    ASSET = "ASSET"
    WORK = "WORK"
    MARK = "MARK"
    PERSON = "PERSON"
    VOICE = "VOICE"
    LICENCE = "LICENCE"
    CONSENT = "CONSENT"
    TRANSFORMATION = "TRANSFORMATION"
    TERRITORY = "TERRITORY"
    CAMPAIGN = "CAMPAIGN"


class GraphEdgeKind(str, Enum):
    DERIVED_FROM = "DERIVED_FROM"
    CANDIDATE_MATCH = "CANDIDATE_MATCH"
    DEPICTS = "DEPICTS"
    CONTAINS_VOICE = "CONTAINS_VOICE"
    CONTAINS_MARK = "CONTAINS_MARK"
    COVERED_BY = "COVERED_BY"
    CONSENTED_BY = "CONSENTED_BY"
    VALID_IN = "VALID_IN"
    USED_BY = "USED_BY"


class EvidenceLocator(StrictFrozenModel):
    kind: LocatorKind
    page_index: int | None = Field(default=None, ge=0)
    frame_index: int | None = Field(default=None, ge=0)
    bbox: tuple[float, float, float, float] | None = None
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    metadata_path: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_shape(self) -> EvidenceLocator:
        supplied = {
            "page_index": self.page_index,
            "frame_index": self.frame_index,
            "bbox": self.bbox,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text_start": self.text_start,
            "text_end": self.text_end,
            "metadata_path": self.metadata_path,
        }
        allowed_by_kind = {
            LocatorKind.WHOLE_ASSET: set(),
            LocatorKind.REGION: {"page_index", "frame_index", "bbox"},
            LocatorKind.TIME_RANGE: {"start_seconds", "end_seconds"},
            LocatorKind.TEXT_RANGE: {"page_index", "text_start", "text_end"},
            LocatorKind.METADATA_PATH: {"metadata_path"},
        }
        unexpected = {
            field
            for field, value in supplied.items()
            if value is not None and field not in allowed_by_kind[self.kind]
        }
        if unexpected:
            raise ValueError(f"{self.kind.value} cannot carry fields: {sorted(unexpected)}")

        if self.kind == LocatorKind.WHOLE_ASSET:
            return self
        elif self.kind == LocatorKind.REGION:
            if self.bbox is None:
                raise ValueError("REGION requires bbox")
            x0, y0, x1, y1 = self.bbox
            if min(self.bbox) < 0 or x1 <= x0 or y1 <= y0:
                raise ValueError("REGION bbox must be non-negative with positive area")
        elif self.kind == LocatorKind.TIME_RANGE:
            if self.start_seconds is None or self.end_seconds is None:
                raise ValueError("TIME_RANGE requires start_seconds and end_seconds")
            if self.end_seconds <= self.start_seconds:
                raise ValueError("TIME_RANGE end_seconds must be greater than start_seconds")
        elif self.kind == LocatorKind.TEXT_RANGE:
            if self.page_index is None or self.text_start is None or self.text_end is None:
                raise ValueError("TEXT_RANGE requires page_index, text_start and text_end")
            if self.text_end <= self.text_start:
                raise ValueError("TEXT_RANGE text_end must be greater than text_start")
        elif self.kind == LocatorKind.METADATA_PATH and self.metadata_path is None:
            raise ValueError("METADATA_PATH requires metadata_path")
        return self


class EvidencePointer(StrictFrozenModel):
    evidence_id: str = Field(pattern=ID_PATTERN)
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    kind: EvidenceKind
    source: str = Field(min_length=1, max_length=200)
    component_id: str = Field(pattern=ID_PATTERN)
    component_version: str = Field(min_length=1, max_length=100)
    polarity: EvidencePolarity = EvidencePolarity.NEUTRAL
    confidence: float = Field(ge=0, le=1)
    locator: EvidenceLocator
    summary: str = Field(min_length=1, max_length=1000)
    payload_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class AssetRepresentation(StrictFrozenModel):
    representation_id: str = Field(pattern=ID_PATTERN)
    kind: RepresentationKind
    sha256: str = Field(pattern=SHA256_PATTERN)
    media_type: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(gt=0)
    locator: EvidenceLocator
    component_id: str | None = Field(default=None, pattern=ID_PATTERN)
    component_version: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_derivation_identity(self) -> AssetRepresentation:
        if (self.component_id is None) != (self.component_version is None):
            raise ValueError("component_id and component_version must be provided together")
        if self.kind == RepresentationKind.ORIGINAL:
            if self.locator.kind != LocatorKind.WHOLE_ASSET:
                raise ValueError("ORIGINAL representation must locate the whole asset")
            if self.component_id is not None:
                raise ValueError("ORIGINAL representation cannot be attributed to a derived component")
        elif self.component_id is None:
            raise ValueError("derived representations require component identity")
        return self


class ClaimRecord(StrictFrozenModel):
    claim_id: str = Field(pattern=ID_PATTERN)
    dimension: ClaimDimension
    claim_type: str = Field(pattern=ID_PATTERN)
    statement: str = Field(min_length=1, max_length=1000)
    outcome: ClaimOutcome
    confidence: float = Field(ge=0, le=1)
    mandatory: bool = True
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("evidence_ids must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def enforce_evidence_semantics(self) -> ClaimRecord:
        if self.outcome in {ClaimOutcome.SUPPORTED, ClaimOutcome.CONTRADICTED} and not self.evidence_ids:
            raise ValueError("supported or contradicted claims require evidence")
        if self.outcome == ClaimOutcome.UNKNOWN and not self.limitations:
            raise ValueError("unknown claims require an explicit limitation")
        if self.outcome == ClaimOutcome.NOT_ASSESSED:
            if self.confidence != 0 or self.evidence_ids:
                raise ValueError("not-assessed claims require zero confidence and no evidence")
            if not self.limitations:
                raise ValueError("not-assessed claims require an explicit limitation")
        return self


class ComponentRecord(StrictFrozenModel):
    component_id: str = Field(pattern=ID_PATTERN)
    component_version: str = Field(min_length=1, max_length=100)
    component_type: str = Field(pattern=ID_PATTERN)
    state: ComponentState
    mandatory: bool = True
    artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def unavailable_components_explain_why(self) -> ComponentRecord:
        if self.state != ComponentState.AVAILABLE and not self.reason:
            raise ValueError("degraded or unavailable components require a reason")
        return self


class AssetDescriptor(StrictFrozenModel):
    asset_id: str = Field(pattern=ID_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    media_kind: MediaKind
    media_type: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(gt=0)
    original_filename: str = Field(min_length=1, max_length=255)
    duration_seconds: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_media_dimensions(self) -> AssetDescriptor:
        if self.media_kind in {MediaKind.AUDIO, MediaKind.VIDEO} and self.duration_seconds is None:
            raise ValueError("audio and video assets require duration_seconds")
        if self.media_kind == MediaKind.IMAGE and (self.width is None or self.height is None):
            raise ValueError("image assets require width and height")
        return self


class AssessmentContext(StrictFrozenModel):
    policy_id: str = Field(pattern=ID_PATTERN)
    policy_version: str = Field(min_length=1, max_length=100)
    intended_use: str = Field(min_length=1, max_length=300)
    channel: str = Field(min_length=1, max_length=100)
    audience: str = Field(min_length=1, max_length=200)
    territories: tuple[str, ...] = Field(min_length=1)
    brand_profile: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("territories")
    @classmethod
    def normalize_territories(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.upper() for value in values}))
        if any(len(value) != 2 or not value.isalpha() for value in normalized):
            raise ValueError("territories must contain ISO 3166-1 alpha-2-like codes")
        return normalized


class AssetIR(StrictFrozenModel):
    schema_id: Literal[ASSET_IR_SCHEMA] = Field(
        default=ASSET_IR_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    asset: AssetDescriptor
    representations: tuple[AssetRepresentation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def bind_original_representation(self) -> AssetIR:
        representation_ids = [item.representation_id for item in self.representations]
        if len(representation_ids) != len(set(representation_ids)):
            raise ValueError("representation_id values must be unique")
        originals = [item for item in self.representations if item.kind == RepresentationKind.ORIGINAL]
        if len(originals) != 1:
            raise ValueError("AssetIR requires exactly one ORIGINAL representation")
        original = originals[0]
        if original.sha256 != self.asset.sha256 or original.size_bytes != self.asset.size_bytes:
            raise ValueError("ORIGINAL representation must match the asset byte identity")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        payload["representations"] = sorted(
            payload["representations"], key=lambda item: item["representation_id"]
        )
        return payload

    def commitment_sha256(self) -> str:
        return _sha256_json(self.canonical_payload())


class RightsGateAssessmentRequest(StrictFrozenModel):
    schema_id: Literal[ASSESSMENT_REQUEST_SCHEMA] = Field(
        default=ASSESSMENT_REQUEST_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    idempotency_key: str = Field(pattern=ID_PATTERN)
    asset_ir: AssetIR
    context: AssessmentContext
    requested_dimensions: tuple[ClaimDimension, ...] = (
        ClaimDimension.PROVENANCE,
        ClaimDimension.RIGHTS_EXPOSURE,
        ClaimDimension.DEPLOYMENT_READINESS,
    )

    @field_validator("requested_dimensions")
    @classmethod
    def require_challenge_dimensions(
        cls, values: tuple[ClaimDimension, ...]
    ) -> tuple[ClaimDimension, ...]:
        required = set(ClaimDimension)
        if len(values) != len(set(values)) or set(values) != required:
            raise ValueError("requested_dimensions must contain each challenge dimension exactly once")
        return tuple(sorted(values, key=lambda item: item.value))

    def request_sha256(self) -> str:
        """Fingerprint inputs so a reused idempotency key can be conflict-checked."""

        payload = self.model_dump(
            mode="json",
            by_alias=True,
            exclude={"idempotency_key"},
            exclude_none=True,
        )
        payload["asset_ir"] = self.asset_ir.canonical_payload()
        return _sha256_json(payload)


class ExposureGraphNode(StrictFrozenModel):
    node_id: str = Field(pattern=ID_PATTERN)
    kind: GraphNodeKind
    label: str = Field(min_length=1, max_length=300)
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("evidence_ids must be unique")
        return tuple(sorted(values))


class ExposureGraphEdge(StrictFrozenModel):
    edge_id: str = Field(pattern=ID_PATTERN)
    kind: GraphEdgeKind
    source_node_id: str = Field(pattern=ID_PATTERN)
    target_node_id: str = Field(pattern=ID_PATTERN)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("evidence_ids must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def reject_self_edges(self) -> ExposureGraphEdge:
        if self.source_node_id == self.target_node_id:
            raise ValueError("exposure graph edges cannot be self-referential")
        return self


class AssetExposureGraph(StrictFrozenModel):
    schema_id: Literal[EXPOSURE_GRAPH_SCHEMA] = Field(
        default=EXPOSURE_GRAPH_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    root_node_id: str = Field(pattern=ID_PATTERN)
    nodes: tuple[ExposureGraphNode, ...] = Field(min_length=1)
    edges: tuple[ExposureGraphEdge, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_topology(self) -> AssetExposureGraph:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node_id values must be unique")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("edge_id values must be unique")
        nodes_by_id = {node.node_id: node for node in self.nodes}
        root = nodes_by_id.get(self.root_node_id)
        if root is None or root.kind != GraphNodeKind.ASSET:
            raise ValueError("root_node_id must reference an ASSET node")
        for edge in self.edges:
            if edge.source_node_id not in nodes_by_id or edge.target_node_id not in nodes_by_id:
                raise ValueError(f"edge {edge.edge_id} references an unknown node")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        payload["nodes"] = sorted(payload["nodes"], key=lambda item: item["node_id"])
        payload["edges"] = sorted(payload["edges"], key=lambda item: item["edge_id"])
        return payload

    def commitment_sha256(self) -> str:
        return _sha256_json(self.canonical_payload())


class ProvenanceAssessment(StrictFrozenModel):
    dimension: Literal[ClaimDimension.PROVENANCE] = ClaimDimension.PROVENANCE
    state: AssessmentState
    verdict: ProvenanceVerdict
    confidence: float = Field(ge=0, le=1)
    claims: tuple[ClaimRecord, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_dimension(self) -> ProvenanceAssessment:
        if any(claim.dimension != self.dimension for claim in self.claims):
            raise ValueError("provenance assessment contains a claim from another dimension")
        if self.verdict == ProvenanceVerdict.UNKNOWN and not self.limitations:
            raise ValueError("unknown provenance requires an explicit limitation")
        if self.state == AssessmentState.UNAVAILABLE and self.verdict != ProvenanceVerdict.UNKNOWN:
            raise ValueError("unavailable provenance must have UNKNOWN verdict")
        return self


class RightsAssessment(StrictFrozenModel):
    dimension: Literal[ClaimDimension.RIGHTS_EXPOSURE] = ClaimDimension.RIGHTS_EXPOSURE
    state: AssessmentState
    verdict: RightsVerdict
    confidence: float = Field(ge=0, le=1)
    claims: tuple[ClaimRecord, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_dimension(self) -> RightsAssessment:
        if any(claim.dimension != self.dimension for claim in self.claims):
            raise ValueError("rights assessment contains a claim from another dimension")
        if self.verdict == RightsVerdict.UNKNOWN and not self.limitations:
            raise ValueError("unknown rights exposure requires an explicit limitation")
        if self.state == AssessmentState.UNAVAILABLE and self.verdict != RightsVerdict.UNKNOWN:
            raise ValueError("unavailable rights assessment must have UNKNOWN verdict")
        return self


class DeploymentAssessment(StrictFrozenModel):
    dimension: Literal[ClaimDimension.DEPLOYMENT_READINESS] = ClaimDimension.DEPLOYMENT_READINESS
    state: AssessmentState
    decision: DeploymentDecision
    confidence: float = Field(ge=0, le=1)
    claims: tuple[ClaimRecord, ...] = Field(default_factory=tuple)
    policy_citations: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_dimension(self) -> DeploymentAssessment:
        if any(claim.dimension != self.dimension for claim in self.claims):
            raise ValueError("deployment assessment contains a claim from another dimension")
        if self.decision == DeploymentDecision.GO and self.state != AssessmentState.COMPLETE:
            raise ValueError("GO requires a complete deployment assessment")
        return self


class RightsGateAssessment(StrictFrozenModel):
    schema_id: Literal[ASSESSMENT_SCHEMA] = Field(
        default=ASSESSMENT_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    assessment_id: str = Field(pattern=ID_PATTERN)
    created_at: datetime
    asset: AssetDescriptor
    context: AssessmentContext
    components: tuple[ComponentRecord, ...] = Field(min_length=1)
    evidence: tuple[EvidencePointer, ...] = Field(default_factory=tuple)
    exposure_graph: AssetExposureGraph
    provenance: ProvenanceAssessment
    rights: RightsAssessment
    deployment: DeploymentAssessment

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def enforce_referential_and_release_integrity(self) -> RightsGateAssessment:
        component_ids = [component.component_id for component in self.components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("component_id values must be unique")

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")
        evidence_id_set = set(evidence_ids)
        component_id_set = set(component_ids)

        if self.exposure_graph.asset_sha256 != self.asset.sha256:
            raise ValueError("exposure graph is bound to a different asset")
        graph_evidence_ids = {
            evidence_id
            for node in self.exposure_graph.nodes
            for evidence_id in node.evidence_ids
        } | {
            evidence_id
            for edge in self.exposure_graph.edges
            for evidence_id in edge.evidence_ids
        }
        missing_graph_evidence = graph_evidence_ids - evidence_id_set
        if missing_graph_evidence:
            raise ValueError(
                f"exposure graph references missing evidence: {sorted(missing_graph_evidence)}"
            )

        for item in self.evidence:
            if item.asset_sha256 != self.asset.sha256:
                raise ValueError(f"evidence {item.evidence_id} is bound to a different asset")
            if item.component_id not in component_id_set:
                raise ValueError(f"evidence {item.evidence_id} references an unknown component")
            component = next(
                candidate
                for candidate in self.components
                if candidate.component_id == item.component_id
            )
            if item.component_version != component.component_version:
                raise ValueError(
                    f"evidence {item.evidence_id} component version does not match its component record"
                )

        claims = self.provenance.claims + self.rights.claims + self.deployment.claims
        claim_ids = [claim.claim_id for claim in claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique across the assessment")
        for claim in claims:
            missing = set(claim.evidence_ids) - evidence_id_set
            if missing:
                raise ValueError(f"claim {claim.claim_id} references missing evidence: {sorted(missing)}")

        if self.deployment.decision == DeploymentDecision.GO:
            unavailable = [
                component.component_id
                for component in self.components
                if component.mandatory and component.state != ComponentState.AVAILABLE
            ]
            if unavailable:
                raise ValueError(f"GO is forbidden while mandatory components are unavailable: {unavailable}")
            if self.provenance.state != AssessmentState.COMPLETE or self.rights.state != AssessmentState.COMPLETE:
                raise ValueError("GO requires complete provenance and rights assessments")
            if self.provenance.verdict in {ProvenanceVerdict.UNKNOWN, ProvenanceVerdict.TAMPERED}:
                raise ValueError("GO is forbidden for unknown or tampered provenance")
            if self.rights.verdict != RightsVerdict.CLEAR:
                raise ValueError("GO requires a CLEAR rights verdict")
            unresolved = [
                claim.claim_id
                for claim in claims
                if claim.mandatory and claim.outcome in {ClaimOutcome.UNKNOWN, ClaimOutcome.NOT_ASSESSED}
            ]
            if unresolved:
                raise ValueError(f"GO is forbidden while mandatory claims are unresolved: {unresolved}")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        """Return a stable, secret-free payload suitable for hashing/signing."""

        payload = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        payload["components"] = sorted(payload["components"], key=lambda item: item["component_id"])
        payload["evidence"] = sorted(payload["evidence"], key=lambda item: item["evidence_id"])
        payload["exposure_graph"] = self.exposure_graph.canonical_payload()
        for dimension in ("provenance", "rights", "deployment"):
            payload[dimension]["claims"] = sorted(
                payload[dimension]["claims"],
                key=lambda item: item["claim_id"],
            )
            payload[dimension]["limitations"] = sorted(payload[dimension]["limitations"])
            for claim in payload[dimension]["claims"]:
                claim["evidence_ids"] = sorted(claim["evidence_ids"])
                claim["limitations"] = sorted(claim["limitations"])
        payload["deployment"]["policy_citations"] = sorted(
            payload["deployment"]["policy_citations"]
        )
        return payload

    def commitment_sha256(self) -> str:
        return _sha256_json(self.canonical_payload())


def _sha256_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
