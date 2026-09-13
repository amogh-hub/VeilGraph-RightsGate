"""Contract tests for detector-independent RightsGate assessment results."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.rightsgate import (
    AssessmentContext,
    AssessmentState,
    AssetExposureGraph,
    AssetIR,
    AssetRepresentation,
    AssetDescriptor,
    ClaimDimension,
    ClaimOutcome,
    ClaimRecord,
    ComponentRecord,
    ComponentState,
    DeploymentAssessment,
    DeploymentDecision,
    EvidenceKind,
    EvidenceLocator,
    EvidencePolarity,
    EvidencePointer,
    ExposureGraphEdge,
    ExposureGraphNode,
    GraphEdgeKind,
    GraphNodeKind,
    LocatorKind,
    MediaKind,
    ProvenanceAssessment,
    ProvenanceVerdict,
    RepresentationKind,
    RightsAssessment,
    RightsGateAssessment,
    RightsGateAssessmentRequest,
    RightsVerdict,
)

ASSET_SHA256 = "a" * 64
ARTIFACT_SHA256 = "b" * 64


def valid_assessment_payload() -> dict:
    return {
        "schema": "veilgraph.rightsgate.assessment.v1",
        "assessment_id": "assessment.demo-001",
        "created_at": "2026-09-13T10:00:00+00:00",
        "asset": {
            "asset_id": "asset.demo-001",
            "sha256": ASSET_SHA256,
            "media_kind": "IMAGE",
            "media_type": "image/png",
            "size_bytes": 4096,
            "original_filename": "campaign.png",
            "width": 1920,
            "height": 1080,
        },
        "context": {
            "policy_id": "policy.publication",
            "policy_version": "2026.09.1",
            "intended_use": "Public advertising campaign",
            "channel": "web",
            "audience": "general",
            "territories": ["US", "IN"],
            "brand_profile": "default",
        },
        "components": [
            {
                "component_id": "provenance.core",
                "component_version": "1.0.0",
                "component_type": "provenance.adapter",
                "state": "AVAILABLE",
                "artifact_sha256": ARTIFACT_SHA256,
            },
            {
                "component_id": "rights.core",
                "component_version": "1.0.0",
                "component_type": "rights.adapter",
                "state": "AVAILABLE",
                "artifact_sha256": ARTIFACT_SHA256,
            },
            {
                "component_id": "policy.core",
                "component_version": "1.0.0",
                "component_type": "policy.compiler",
                "state": "AVAILABLE",
                "artifact_sha256": ARTIFACT_SHA256,
            },
        ],
        "evidence": [
            {
                "evidence_id": "evidence.provenance-001",
                "asset_sha256": ASSET_SHA256,
                "kind": "CONTENT_CREDENTIAL",
                "source": "C2PA verifier",
                "component_id": "provenance.core",
                "component_version": "1.0.0",
                "polarity": "SUPPORTS",
                "confidence": 0.99,
                "locator": {"kind": "WHOLE_ASSET"},
                "summary": "Credential chain and asset binding verified.",
                "payload_sha256": "c" * 64,
            },
            {
                "evidence_id": "evidence.rights-001",
                "asset_sha256": ASSET_SHA256,
                "kind": "REFERENCE_MATCH",
                "source": "Governed reference registry",
                "component_id": "rights.core",
                "component_version": "1.0.0",
                "polarity": "CONTRADICTS",
                "confidence": 0.96,
                "locator": {"kind": "WHOLE_ASSET"},
                "summary": "No registered restricted-work candidate exceeded the review threshold.",
                "payload_sha256": "d" * 64,
            },
            {
                "evidence_id": "evidence.policy-001",
                "asset_sha256": ASSET_SHA256,
                "kind": "POLICY_RULE",
                "source": "Deterministic policy compiler",
                "component_id": "policy.core",
                "component_version": "1.0.0",
                "polarity": "SUPPORTS",
                "confidence": 1.0,
                "locator": {"kind": "WHOLE_ASSET"},
                "summary": "All mandatory publication rules evaluated without a violation.",
                "payload_sha256": "e" * 64,
            },
        ],
        "exposure_graph": {
            "schema": "veilgraph.rightsgate.asset-exposure-graph.v1",
            "asset_sha256": ASSET_SHA256,
            "root_node_id": "node.asset-001",
            "nodes": [
                {
                    "node_id": "node.asset-001",
                    "kind": "ASSET",
                    "label": "campaign.png",
                    "evidence_ids": ["evidence.provenance-001"],
                },
                {
                    "node_id": "node.campaign-001",
                    "kind": "CAMPAIGN",
                    "label": "Public advertising campaign",
                    "evidence_ids": ["evidence.policy-001"],
                },
            ],
            "edges": [
                {
                    "edge_id": "edge.used-by-001",
                    "kind": "USED_BY",
                    "source_node_id": "node.asset-001",
                    "target_node_id": "node.campaign-001",
                    "confidence": 1.0,
                    "evidence_ids": ["evidence.policy-001"],
                }
            ],
        },
        "provenance": {
            "state": "COMPLETE",
            "verdict": "AUTHENTIC",
            "confidence": 0.99,
            "claims": [
                {
                    "claim_id": "claim.provenance-001",
                    "dimension": "PROVENANCE",
                    "claim_type": "credential.asset-binding",
                    "statement": "The signed credential is bound to the assessed asset bytes.",
                    "outcome": "SUPPORTED",
                    "confidence": 0.99,
                    "evidence_ids": ["evidence.provenance-001"],
                }
            ],
        },
        "rights": {
            "state": "COMPLETE",
            "verdict": "CLEAR",
            "confidence": 0.96,
            "claims": [
                {
                    "claim_id": "claim.rights-001",
                    "dimension": "RIGHTS_EXPOSURE",
                    "claim_type": "reference.restricted-match",
                    "statement": "A restricted reference work exceeds the review threshold.",
                    "outcome": "CONTRADICTED",
                    "confidence": 0.96,
                    "evidence_ids": ["evidence.rights-001"],
                }
            ],
        },
        "deployment": {
            "state": "COMPLETE",
            "decision": "GO",
            "confidence": 0.96,
            "claims": [
                {
                    "claim_id": "claim.deployment-001",
                    "dimension": "DEPLOYMENT_READINESS",
                    "claim_type": "policy.publication-ready",
                    "statement": "The asset satisfies all mandatory publication rules.",
                    "outcome": "SUPPORTED",
                    "confidence": 1.0,
                    "evidence_ids": ["evidence.policy-001"],
                }
            ],
            "policy_citations": ["PUBLICATION-1", "RIGHTS-3"],
        },
    }


def test_valid_assessment_is_strict_versioned_and_serializable() -> None:
    assessment = RightsGateAssessment.model_validate(valid_assessment_payload())

    serialized = assessment.model_dump(mode="json", by_alias=True)
    assert serialized["schema"] == "veilgraph.rightsgate.assessment.v1"
    assert "schema_id" not in serialized
    assert serialized["context"]["territories"] == ["IN", "US"]
    assert len(assessment.commitment_sha256()) == 64


def test_typed_construction_exposes_all_contract_primitives() -> None:
    locator = EvidenceLocator(kind=LocatorKind.WHOLE_ASSET)
    component = ComponentRecord(
        component_id="component.test",
        component_version="1",
        component_type="test.adapter",
        state=ComponentState.AVAILABLE,
        artifact_sha256=ARTIFACT_SHA256,
    )
    evidence = EvidencePointer(
        evidence_id="evidence.test",
        asset_sha256=ASSET_SHA256,
        kind=EvidenceKind.FORENSIC_SIGNAL,
        source="test",
        component_id=component.component_id,
        component_version=component.component_version,
        polarity=EvidencePolarity.NEUTRAL,
        confidence=0.5,
        locator=locator,
        summary="A bounded test signal.",
    )
    claim = ClaimRecord(
        claim_id="claim.test",
        dimension=ClaimDimension.PROVENANCE,
        claim_type="test.signal",
        statement="The signal is present.",
        outcome=ClaimOutcome.SUPPORTED,
        confidence=0.5,
        evidence_ids=(evidence.evidence_id,),
    )

    assert claim.evidence_ids == ("evidence.test",)
    assert AssetDescriptor(
        asset_id="asset.test",
        sha256=ASSET_SHA256,
        media_kind=MediaKind.IMAGE,
        media_type="image/png",
        size_bytes=1,
        original_filename="test.png",
        width=1,
        height=1,
    ).media_kind == MediaKind.IMAGE
    assert AssessmentContext(
        policy_id="policy.test",
        policy_version="1",
        intended_use="test",
        channel="test",
        audience="test",
        territories=("us", "IN"),
    ).territories == ("IN", "US")


def valid_asset_ir() -> AssetIR:
    asset = AssetDescriptor(
        asset_id="asset.request-001",
        sha256=ASSET_SHA256,
        media_kind=MediaKind.IMAGE,
        media_type="image/png",
        size_bytes=4096,
        original_filename="request.png",
        width=1920,
        height=1080,
    )
    return AssetIR(
        asset=asset,
        representations=(
            AssetRepresentation(
                representation_id="representation.original-001",
                kind=RepresentationKind.ORIGINAL,
                sha256=ASSET_SHA256,
                media_type="image/png",
                size_bytes=4096,
                locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
            ),
        ),
    )


def test_asset_ir_binds_exactly_one_original_to_asset_bytes() -> None:
    asset_ir = valid_asset_ir()
    assert asset_ir.representations[0].sha256 == asset_ir.asset.sha256
    assert len(asset_ir.commitment_sha256()) == 64

    mismatched = asset_ir.model_dump(mode="json", by_alias=True)
    mismatched["representations"][0]["sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="match the asset byte identity"):
        AssetIR.model_validate(mismatched)


def test_request_fingerprint_is_idempotent_and_excludes_idempotency_key() -> None:
    context = AssessmentContext(
        policy_id="policy.test",
        policy_version="1",
        intended_use="public campaign",
        channel="web",
        audience="general",
        territories=("IN",),
    )
    request_one = RightsGateAssessmentRequest(
        idempotency_key="request.key-001",
        asset_ir=valid_asset_ir(),
        context=context,
    )
    request_two = RightsGateAssessmentRequest(
        idempotency_key="request.key-002",
        asset_ir=valid_asset_ir(),
        context=context,
        requested_dimensions=(
            ClaimDimension.RIGHTS_EXPOSURE,
            ClaimDimension.PROVENANCE,
            ClaimDimension.DEPLOYMENT_READINESS,
        ),
    )

    assert request_one.request_sha256() == request_two.request_sha256()


def test_request_requires_all_three_challenge_dimensions() -> None:
    with pytest.raises(ValidationError, match="each challenge dimension"):
        RightsGateAssessmentRequest(
            idempotency_key="request.key-001",
            asset_ir=valid_asset_ir(),
            context=AssessmentContext(
                policy_id="policy.test",
                policy_version="1",
                intended_use="public campaign",
                channel="web",
                audience="general",
                territories=("IN",),
            ),
            requested_dimensions=(ClaimDimension.PROVENANCE,),
        )


def test_exposure_graph_validates_topology_and_evidence_references() -> None:
    root = ExposureGraphNode(
        node_id="node.asset",
        kind=GraphNodeKind.ASSET,
        label="asset",
    )
    work = ExposureGraphNode(
        node_id="node.work",
        kind=GraphNodeKind.WORK,
        label="candidate work",
        evidence_ids=("evidence.reference",),
    )
    edge = ExposureGraphEdge(
        edge_id="edge.match",
        kind=GraphEdgeKind.CANDIDATE_MATCH,
        source_node_id=root.node_id,
        target_node_id=work.node_id,
        confidence=0.8,
        evidence_ids=("evidence.reference",),
    )
    graph = AssetExposureGraph(
        asset_sha256=ASSET_SHA256,
        root_node_id=root.node_id,
        nodes=(root, work),
        edges=(edge,),
    )
    assert len(graph.commitment_sha256()) == 64

    with pytest.raises(ValidationError, match="unknown node"):
        AssetExposureGraph(
            asset_sha256=ASSET_SHA256,
            root_node_id=root.node_id,
            nodes=(root,),
            edges=(edge,),
        )


def test_assessment_rejects_unbound_graph_evidence() -> None:
    payload = valid_assessment_payload()
    payload["exposure_graph"]["nodes"][0]["evidence_ids"] = ["evidence.missing"]

    with pytest.raises(ValidationError, match="graph references missing evidence"):
        RightsGateAssessment.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("provenance", "claims", 0, "evidence_ids"), ["evidence.missing"], "missing evidence"),
        (("evidence", 0, "asset_sha256"), "f" * 64, "different asset"),
        (("evidence", 0, "component_version"), "9.9.9", "component version"),
    ],
)
def test_referential_integrity_rejects_unbound_evidence(
    path: tuple[str | int, ...], value: object, message: str
) -> None:
    payload = valid_assessment_payload()
    cursor: object = payload
    for key in path[:-1]:
        cursor = cursor[key]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ValidationError, match=message):
        RightsGateAssessment.model_validate(payload)


def test_go_is_forbidden_when_a_mandatory_component_is_unavailable() -> None:
    payload = valid_assessment_payload()
    payload["components"][0].update(
        state="UNAVAILABLE",
        reason="Verifier initialization failed.",
    )

    with pytest.raises(ValidationError, match="GO is forbidden.*mandatory components"):
        RightsGateAssessment.model_validate(payload)


def test_go_is_forbidden_for_unknown_provenance() -> None:
    payload = valid_assessment_payload()
    payload["provenance"].update(
        state="PARTIAL",
        verdict="UNKNOWN",
        confidence=0.0,
        limitations=["Required provenance verifier was unavailable."],
    )
    payload["provenance"]["claims"][0].update(
        outcome="UNKNOWN",
        confidence=0.0,
        evidence_ids=[],
        limitations=["No trustworthy provenance signal was available."],
    )

    with pytest.raises(ValidationError, match="GO requires complete provenance"):
        RightsGateAssessment.model_validate(payload)


def test_review_preserves_explicit_abstention_and_failure_evidence() -> None:
    payload = valid_assessment_payload()
    payload["components"][0].update(
        state="UNAVAILABLE",
        reason="Verifier initialization failed.",
    )
    payload["provenance"].update(
        state="UNAVAILABLE",
        verdict="UNKNOWN",
        confidence=0.0,
        limitations=["Provenance could not be assessed."],
    )
    payload["provenance"]["claims"][0].update(
        outcome="NOT_ASSESSED",
        confidence=0.0,
        evidence_ids=[],
        limitations=["Mandatory provenance component unavailable."],
    )
    payload["deployment"].update(
        decision="REVIEW",
        confidence=1.0,
        limitations=["Mandatory provenance evidence is missing."],
    )

    assessment = RightsGateAssessment.model_validate(payload)
    assert assessment.deployment.decision == DeploymentDecision.REVIEW
    assert assessment.provenance.verdict == ProvenanceVerdict.UNKNOWN
    assert assessment.provenance.claims[0].outcome == ClaimOutcome.NOT_ASSESSED


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "WHOLE_ASSET", "page_index": 0},
        {"kind": "REGION", "bbox": [1, 1, 0, 2]},
        {"kind": "TIME_RANGE", "start_seconds": 2, "end_seconds": 2},
        {"kind": "TEXT_RANGE", "page_index": 0, "text_start": 5, "text_end": 4},
        {"kind": "METADATA_PATH", "metadata_path": "x", "frame_index": 0},
    ],
)
def test_evidence_locator_rejects_ambiguous_or_invalid_ranges(payload: dict) -> None:
    with pytest.raises(ValidationError):
        EvidenceLocator.model_validate(payload)


def test_naive_assessment_timestamp_is_rejected() -> None:
    payload = valid_assessment_payload()
    payload["created_at"] = datetime(2026, 9, 13, 10, 0, 0)

    with pytest.raises(ValidationError, match="timezone-aware"):
        RightsGateAssessment.model_validate(payload)


def test_commitment_is_order_invariant_but_policy_sensitive() -> None:
    original = valid_assessment_payload()
    reordered = deepcopy(original)
    reordered["components"].reverse()
    reordered["evidence"].reverse()
    reordered["exposure_graph"]["nodes"].reverse()
    reordered["deployment"]["policy_citations"].reverse()

    original_commitment = RightsGateAssessment.model_validate(original).commitment_sha256()
    reordered_commitment = RightsGateAssessment.model_validate(reordered).commitment_sha256()
    assert original_commitment == reordered_commitment

    changed_policy = deepcopy(original)
    changed_policy["context"]["policy_version"] = "2026.09.2"
    changed_commitment = RightsGateAssessment.model_validate(changed_policy).commitment_sha256()
    assert changed_commitment != original_commitment


def test_unknown_claim_requires_a_limitation() -> None:
    with pytest.raises(ValidationError, match="explicit limitation"):
        ClaimRecord(
            claim_id="claim.unknown",
            dimension=ClaimDimension.RIGHTS_EXPOSURE,
            claim_type="reference.match",
            statement="A candidate reference match was found.",
            outcome=ClaimOutcome.UNKNOWN,
            confidence=0.0,
        )


def test_contract_rejects_undeclared_fields() -> None:
    payload = valid_assessment_payload()
    payload["legal_conclusion"] = "No infringement"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RightsGateAssessment.model_validate(payload)


def test_dimension_claim_cannot_be_misfiled() -> None:
    claim = ClaimRecord(
        claim_id="claim.rights",
        dimension=ClaimDimension.RIGHTS_EXPOSURE,
        claim_type="reference.match",
        statement="A candidate reference match was found.",
        outcome=ClaimOutcome.NOT_ASSESSED,
        confidence=0,
        limitations=("Reference registry unavailable.",),
    )

    with pytest.raises(ValidationError, match="another dimension"):
        ProvenanceAssessment(
            state=AssessmentState.PARTIAL,
            verdict=ProvenanceVerdict.UNKNOWN,
            confidence=0,
            claims=(claim,),
            limitations=("Incomplete assessment.",),
        )


def test_go_requires_complete_rights_and_deployment_assessments() -> None:
    payload = valid_assessment_payload()
    payload["rights"].update(
        state="PARTIAL",
        verdict="POTENTIAL_EXPOSURE",
        limitations=["Candidate requires human review."],
    )

    with pytest.raises(ValidationError, match="GO requires complete provenance and rights"):
        RightsGateAssessment.model_validate(payload)

    with pytest.raises(ValidationError, match="GO requires a complete deployment assessment"):
        DeploymentAssessment(
            state=AssessmentState.PARTIAL,
            decision=DeploymentDecision.GO,
            confidence=0.5,
            policy_citations=("TEST-1",),
        )


def test_rights_unknown_requires_a_limitation() -> None:
    with pytest.raises(ValidationError, match="unknown rights exposure"):
        RightsAssessment(
            state=AssessmentState.UNAVAILABLE,
            verdict=RightsVerdict.UNKNOWN,
            confidence=0,
        )


def test_created_at_utc_is_accepted() -> None:
    payload = valid_assessment_payload()
    payload["created_at"] = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
    assert RightsGateAssessment.model_validate(payload).created_at.utcoffset().total_seconds() == 0
