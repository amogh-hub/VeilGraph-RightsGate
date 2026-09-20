"""End-to-end tests for durable, fail-closed RightsGate execution."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.core.database import Database
from app.extraction.video import physical_frame, probe_video
from app.rightsgate import (
    AssessmentContext,
    AssessmentState,
    AssetDescriptor,
    AssetIR,
    AssetRepresentation,
    ComponentRecord,
    ComponentState,
    DeploymentDecision,
    EvidenceLocator,
    LocatorKind,
    MediaKind,
    ProvenanceAssessment,
    ProvenanceVerdict,
    RepresentationKind,
    RightsAssessment,
    RightsGateAssessmentRequest,
    RightsVerdict,
)
from app.rightsgate.execution import execute_rightsgate_assessment, execution_fingerprint
from app.rightsgate.policy import (
    PublicationPolicy,
    RegulatoryRule,
    RegulatoryRuleEffect,
    evaluate_publication_policy,
)
from app.rightsgate.rights import (
    LicenceEvaluationResult,
    LicenceRecord,
    LicenceRegistry,
    LicenceState,
    ReferenceKind,
    RightsReferenceRegistry,
    build_registry_image,
    evaluate_candidate_licences,
    match_reference_image,
)
from app.rightsgate.store import (
    IdempotencyConflict,
    ReservationState,
    RightsGateAssessmentStore,
    StoredAssessmentIntegrityError,
)

NOW = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)


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


def pcm_wav(*, sample_rate: int = 8_000, frame_count: int = 800) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def assessment_request(
    data: bytes,
    *,
    key: str = "request.execute-001",
) -> RightsGateAssessmentRequest:
    sha256 = hashlib.sha256(data).hexdigest()
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    descriptor = AssetDescriptor(
        asset_id="asset.execute-001",
        sha256=sha256,
        media_kind=MediaKind.IMAGE,
        media_type="image/png",
        size_bytes=len(data),
        original_filename="campaign.png",
        width=width,
        height=height,
    )
    return RightsGateAssessmentRequest(
        idempotency_key=key,
        asset_ir=AssetIR(
            asset=descriptor,
            representations=(
                AssetRepresentation(
                    representation_id="representation.original-001",
                    kind=RepresentationKind.ORIGINAL,
                    sha256=sha256,
                    media_type="image/png",
                    size_bytes=len(data),
                    locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                ),
            ),
        ),
        context=AssessmentContext(
            policy_id="policy.publication",
            policy_version="2026.09.1",
            intended_use="Public advertising campaign",
            channel="web",
            audience="general",
            territories=("IN",),
        ),
    )


def rights_registry(data: bytes) -> RightsReferenceRegistry:
    reference = build_registry_image(
        reference_id="reference.work-001",
        kind=ReferenceKind.COPYRIGHTED_WORK,
        title="Governed campaign work",
        rights_holder="Rights Holder Ltd",
        data=data,
        media_type="image/png",
        source_record_id="rights-record.work-001",
    )
    return RightsReferenceRegistry(
        registry_id="registry.rights",
        version="2026.09.1",
        references=(reference,),
    )


def licence_registry(*, covered: bool = True) -> LicenceRegistry:
    territories = ("IN",) if covered else ("US",)
    licence = LicenceRecord(
        licence_id="licence.work-001",
        source_record_id="licence-record.work-001",
        reference_ids=("reference.work-001",),
        licensor="Rights Holder Ltd",
        licensee="Example Content Team",
        state=LicenceState.ACTIVE,
        valid_from=NOW - timedelta(days=30),
        valid_until=NOW + timedelta(days=30),
        territories=territories,
        channels=("web",),
        intended_uses=("public advertising campaign",),
    )
    return LicenceRegistry(
        registry_id="registry.licences",
        version="2026.09.1",
        licences=(licence,),
    )


def publication_policy(*, require_unimplemented: bool = True) -> PublicationPolicy:
    required = (
        "provenance.c2pa",
        "rights.local-image-registry",
        "rights.licence-evaluator",
    )
    if require_unimplemented:
        required += (
            "provenance.independent-forensics",
            "rights.trademark-localizer",
        )
    return PublicationPolicy(
        policy_id="policy.publication",
        version="2026.09.1",
        allowed_channels=("web",),
        allowed_audiences=("general",),
        allowed_territories=("IN",),
        required_component_ids=required,
    )


def execute_fixture(
    data: bytes,
    *,
    licences: LicenceRegistry | None = None,
    policy: PublicationPolicy | None = None,
):
    return execute_rightsgate_assessment(
        data,
        request=assessment_request(data),
        rights_registry=rights_registry(data),
        licence_registry=licences or licence_registry(),
        policy=policy or publication_policy(),
        created_at=NOW,
    )


def test_licence_evaluator_covers_exact_candidate_for_declared_context() -> None:
    data = gradient_png()
    request = assessment_request(data)
    match = match_reference_image(
        data,
        asset_sha256=request.asset_ir.asset.sha256,
        registry=rights_registry(data),
    )
    result = evaluate_candidate_licences(
        match,
        asset_sha256=request.asset_ir.asset.sha256,
        context=request.context,
        registry=licence_registry(),
        assessed_at=NOW,
    )

    assert result.policy_conflict is False
    assert result.covered_reference_ids == ("reference.work-001",)
    assert result.evidence[0].attributes["covering_licence_ids"] == "licence.work-001"
    assert result.evidence[0].attributes["covering_source_record_ids"] == "licence-record.work-001"
    assert result.claims[0].outcome.value == "SUPPORTED"


def test_licence_evaluator_detects_territory_conflict() -> None:
    data = gradient_png()
    request = assessment_request(data)
    match = match_reference_image(
        data,
        asset_sha256=request.asset_ir.asset.sha256,
        registry=rights_registry(data),
    )
    result = evaluate_candidate_licences(
        match,
        asset_sha256=request.asset_ir.asset.sha256,
        context=request.context,
        registry=licence_registry(covered=False),
        assessed_at=NOW,
    )

    assert result.policy_conflict is True
    assert result.uncovered_reference_ids == ("reference.work-001",)
    assert result.evidence[0].attributes["covering_licence_count"] == 0
    assert result.claims[0].outcome.value == "CONTRADICTED"


@pytest.mark.parametrize(
    "licence_update",
    [
        {"state": LicenceState.REVOKED},
        {"valid_from": NOW - timedelta(days=60), "valid_until": NOW - timedelta(days=1)},
        {"channels": ("broadcast",)},
        {"intended_uses": ("internal archive",)},
    ],
)
def test_licence_evaluator_fails_closed_for_restriction_mismatch(licence_update) -> None:
    data = gradient_png()
    request = assessment_request(data)
    match = match_reference_image(
        data,
        asset_sha256=request.asset_ir.asset.sha256,
        registry=rights_registry(data),
    )
    base = licence_registry().licences[0]
    registry = LicenceRegistry(
        registry_id="registry.restricted",
        version="1",
        licences=(base.model_copy(update=licence_update),),
    )
    result = evaluate_candidate_licences(
        match,
        asset_sha256=request.asset_ir.asset.sha256,
        context=request.context,
        registry=registry,
        assessed_at=NOW,
    )

    assert result.policy_conflict is True
    assert result.covered_reference_ids == ()


def test_licence_window_and_identity_are_strict() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        LicenceRecord(
            licence_id="licence.invalid",
            source_record_id="record.invalid",
            reference_ids=("reference.work-001",),
            licensor="Licensor",
            licensee="Licensee",
            valid_from=datetime(2026, 1, 1),
            valid_until=datetime(2027, 1, 1),
            territories=("IN",),
            channels=("WEB",),
            intended_uses=("Campaign",),
        )

    first = licence_registry().licences[0]
    with pytest.raises(ValidationError, match="licence_id values must be unique"):
        LicenceRegistry(
            registry_id="registry.invalid",
            version="1",
            licences=(first, first),
        )


def test_end_to_end_blocks_unlicensed_candidate_with_evidence_graph() -> None:
    data = gradient_png()
    assessment = execute_fixture(data, licences=licence_registry(covered=False))

    assert assessment.deployment.decision == DeploymentDecision.BLOCK
    assert assessment.rights.verdict == RightsVerdict.POLICY_CONFLICT
    assert assessment.commitment_sha256()
    assert any(item.kind.value == "WORK" for item in assessment.exposure_graph.nodes)
    assert any(item.kind.value == "CANDIDATE_MATCH" for item in assessment.exposure_graph.edges)
    assert any("licence-coverage" in item for item in assessment.deployment.policy_citations)
    assert assessment.deployment.confidence == 1


def test_end_to_end_reviews_when_required_detector_evidence_is_incomplete() -> None:
    assessment = execute_fixture(gradient_png())

    assert assessment.deployment.decision == DeploymentDecision.REVIEW
    assert assessment.deployment.state == AssessmentState.PARTIAL
    states = {item.component_id: item.state for item in assessment.components}
    assert states["provenance.independent-forensics"] == ComponentState.AVAILABLE
    assert states["rights.trademark-localizer"] == ComponentState.DEGRADED
    assert assessment.rights.verdict == RightsVerdict.POTENTIAL_EXPOSURE
    assert assessment.deployment.claims[0].outcome.value == "UNKNOWN"


def test_video_executor_change_screens_timeline_and_binds_frame_evidence() -> None:
    video_path = Path(__file__).resolve().parents[1] / "test_video_privacy_demo.mp4"
    data = video_path.read_bytes()
    info = probe_video(data, video_path.name)
    first_frame, _, _ = physical_frame(data, 0, video_path.name)
    frame_buffer = io.BytesIO()
    first_frame.save(frame_buffer, format="PNG")
    reference_data = frame_buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    request = RightsGateAssessmentRequest(
        idempotency_key="request.video-001",
        asset_ir=AssetIR(
            asset=AssetDescriptor(
                asset_id="asset.video-001",
                sha256=digest,
                media_kind=MediaKind.VIDEO,
                media_type="video/mp4",
                size_bytes=len(data),
                original_filename=video_path.name,
                duration_seconds=info.duration_seconds,
                width=info.width,
                height=info.height,
            ),
            representations=(
                AssetRepresentation(
                    representation_id="representation.video-original-001",
                    kind=RepresentationKind.ORIGINAL,
                    sha256=digest,
                    media_type="video/mp4",
                    size_bytes=len(data),
                    locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                ),
            ),
        ),
        context=assessment_request(gradient_png()).context,
    )
    assessment = execute_rightsgate_assessment(
        data,
        request=request,
        rights_registry=rights_registry(reference_data),
        licence_registry=licence_registry(),
        policy=publication_policy(),
        created_at=NOW,
    )

    components = {item.component_id: item for item in assessment.components}
    sampler = components["ingestion.video-timeline-analyzer"]
    assert sampler.state == ComponentState.AVAILABLE
    assert assessment.asset.media_kind == MediaKind.VIDEO
    assert assessment.deployment.decision == DeploymentDecision.REVIEW
    assert assessment.evidence
    assert all(item.asset_sha256 == digest for item in assessment.evidence)
    assert any(
        item.locator.kind in {LocatorKind.TIME_RANGE, LocatorKind.REGION}
        and (
            item.locator.kind == LocatorKind.TIME_RANGE
            or item.locator.frame_index is not None
        )
        for item in assessment.evidence
    )
    assert any(
        item.attributes.get("derived_frame_sha256")
        for item in assessment.evidence
    )


def test_standalone_pcm_audio_is_processed_but_voice_rights_abstain() -> None:
    data = pcm_wav()
    digest = hashlib.sha256(data).hexdigest()
    request = RightsGateAssessmentRequest(
        idempotency_key="request.audio-001",
        asset_ir=AssetIR(
            asset=AssetDescriptor(
                asset_id="asset.audio-001",
                sha256=digest,
                media_kind=MediaKind.AUDIO,
                media_type="audio/wav",
                size_bytes=len(data),
                original_filename="voice.wav",
                duration_seconds=0.1,
            ),
            representations=(
                AssetRepresentation(
                    representation_id="representation.audio-original-001",
                    kind=RepresentationKind.ORIGINAL,
                    sha256=digest,
                    media_type="audio/wav",
                    size_bytes=len(data),
                    locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                ),
            ),
        ),
        context=assessment_request(gradient_png()).context,
    )
    reference = gradient_png()
    assessment = execute_rightsgate_assessment(
        data,
        request=request,
        rights_registry=rights_registry(reference),
        licence_registry=licence_registry(),
        policy=publication_policy(),
        created_at=NOW,
    )

    components = {item.component_id: item for item in assessment.components}
    assert components["ingestion.pcm-wav-parser"].state == ComponentState.AVAILABLE
    assert components["rights.voice-consent"].state == ComponentState.UNAVAILABLE
    assert assessment.provenance.verdict == ProvenanceVerdict.UNKNOWN
    assert assessment.rights.state == AssessmentState.UNAVAILABLE
    assert assessment.rights.verdict == RightsVerdict.UNKNOWN
    assert assessment.deployment.decision == DeploymentDecision.REVIEW
    assert any(item.source == "RightsGate bounded PCM/WAV parser" for item in assessment.evidence)


def test_audio_rejects_truncated_pcm_payload() -> None:
    data = pcm_wav()[:-2]
    digest = hashlib.sha256(data).hexdigest()
    request = RightsGateAssessmentRequest(
        idempotency_key="request.audio-truncated",
        asset_ir=AssetIR(
            asset=AssetDescriptor(
                asset_id="asset.audio-truncated",
                sha256=digest,
                media_kind=MediaKind.AUDIO,
                media_type="audio/wav",
                size_bytes=len(data),
                original_filename="truncated.wav",
                duration_seconds=0.1,
            ),
            representations=(
                AssetRepresentation(
                    representation_id="representation.audio-truncated",
                    kind=RepresentationKind.ORIGINAL,
                    sha256=digest,
                    media_type="audio/wav",
                    size_bytes=len(data),
                    locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                ),
            ),
        ),
        context=assessment_request(gradient_png()).context,
    )
    with pytest.raises(ValueError, match="truncated"):
        execute_rightsgate_assessment(
            data,
            request=request,
            rights_registry=rights_registry(gradient_png()),
            licence_registry=licence_registry(),
            policy=publication_policy(),
            created_at=NOW,
        )


def test_execution_fingerprint_binds_threshold_and_all_governed_inputs() -> None:
    data = gradient_png()
    request = assessment_request(data)
    inputs = {
        "rights_registry": rights_registry(data),
        "licence_registry": licence_registry(),
        "policy": publication_policy(),
    }
    first = execution_fingerprint(request, **inputs, max_hamming_distance=4)
    second = execution_fingerprint(request, **inputs, max_hamming_distance=5)
    assert first != second


def test_policy_can_go_only_with_complete_clear_inputs_and_available_components() -> None:
    data = gradient_png()
    request = assessment_request(data)
    policy = publication_policy(require_unimplemented=False)
    components = tuple(
        ComponentRecord(
            component_id=component_id,
            component_version="1",
            component_type="test.component",
            state=ComponentState.AVAILABLE,
        )
        for component_id in policy.required_component_ids
    )
    licence = LicenceEvaluationResult(
        component=components[-1],
        evidence=(),
        claims=(),
        candidate_reference_ids=(),
        covered_reference_ids=(),
        uncovered_reference_ids=(),
        policy_conflict=False,
    )
    result = evaluate_publication_policy(
        asset_sha256=request.asset_ir.asset.sha256,
        context=request.context,
        policy=policy,
        provenance=ProvenanceAssessment(
            state=AssessmentState.COMPLETE,
            verdict=ProvenanceVerdict.AUTHENTIC,
            confidence=1,
        ),
        rights=RightsAssessment(
            state=AssessmentState.COMPLETE,
            verdict=RightsVerdict.CLEAR,
            confidence=1,
        ),
        licence=licence,
        components=components,
    )

    assert result.assessment.decision == DeploymentDecision.GO
    assert result.assessment.state == AssessmentState.COMPLETE
    assert result.assessment.claims[0].outcome.value == "SUPPORTED"


def test_contract_release_floors_override_permissive_caller_policy() -> None:
    data = gradient_png()
    permissive = publication_policy(require_unimplemented=False).model_copy(
        update={
            "require_known_provenance": False,
            "require_rights_clearance": False,
            "block_tampered_provenance": False,
            "block_unlicensed_reference_match": False,
        }
    )
    result = execute_rightsgate_assessment(
        data,
        request=assessment_request(data),
        rights_registry=rights_registry(data),
        licence_registry=licence_registry(),
        policy=permissive,
        created_at=NOW,
    )

    assert result.deployment.decision == DeploymentDecision.REVIEW
    assert any("release-floor" in item for item in result.deployment.policy_citations)


def test_policy_blocks_disallowed_context_deterministically() -> None:
    data = gradient_png()
    request = assessment_request(data)
    result = execute_rightsgate_assessment(
        data,
        request=request,
        rights_registry=rights_registry(data),
        licence_registry=licence_registry(),
        policy=publication_policy().model_copy(update={"allowed_channels": ("broadcast",)}),
        created_at=NOW,
    )
    assert result.deployment.decision == DeploymentDecision.BLOCK
    assert any("context.channel" in item for item in result.deployment.policy_citations)


@pytest.mark.parametrize(
    ("policy_update", "citation"),
    [
        ({"allowed_territories": ("US",)}, "context.territory"),
        ({"allowed_brand_profiles": ("restricted-brand",)}, "context.brand-profile"),
        ({"allowed_audiences": ("employees",)}, "context.audience"),
    ],
)
def test_policy_blocks_regional_brand_and_audience_mismatch(policy_update, citation) -> None:
    data = gradient_png()
    result = execute_rightsgate_assessment(
        data,
        request=assessment_request(data),
        rights_registry=rights_registry(data),
        licence_registry=licence_registry(),
        policy=publication_policy().model_copy(update=policy_update),
        created_at=NOW,
    )
    assert result.deployment.decision == DeploymentDecision.BLOCK
    assert any(citation in item for item in result.deployment.policy_citations)


def test_scoped_regulatory_rule_blocks_matching_context() -> None:
    data = gradient_png()
    policy = publication_policy().model_copy(
        update={
            "regulatory_rules": (
                RegulatoryRule(
                    rule_id="india.synthetic-ad-review",
                    description="Synthetic public advertising in India requires legal review.",
                    effect=RegulatoryRuleEffect.BLOCK,
                    territories=("IN",),
                    channels=("web",),
                    provenance_verdicts=(ProvenanceVerdict.UNKNOWN,),
                ),
            ),
        }
    )
    result = execute_rightsgate_assessment(
        data,
        request=assessment_request(data),
        rights_registry=rights_registry(data),
        licence_registry=licence_registry(),
        policy=policy,
        created_at=NOW,
    )

    assert result.deployment.decision == DeploymentDecision.BLOCK
    assert any(
        "regulatory.india.synthetic-ad-review" in citation
        for citation in result.deployment.policy_citations
    )


def test_regulatory_rule_does_not_apply_outside_its_scope() -> None:
    data = gradient_png()
    policy = publication_policy().model_copy(
        update={
            "regulatory_rules": (
                RegulatoryRule(
                    rule_id="us.broadcast-only",
                    description="US broadcast assets require review.",
                    effect=RegulatoryRuleEffect.BLOCK,
                    territories=("US",),
                    channels=("broadcast",),
                ),
            ),
        }
    )
    result = execute_rightsgate_assessment(
        data,
        request=assessment_request(data),
        rights_registry=rights_registry(data),
        licence_registry=licence_registry(),
        policy=policy,
        created_at=NOW,
    )

    assert not any("us.broadcast-only" in citation for citation in result.deployment.policy_citations)


def test_regulatory_rule_ids_are_unique_and_canonicalized() -> None:
    rule = RegulatoryRule(
        rule_id="review.synthetic",
        description="Synthetic assets require review.",
        effect=RegulatoryRuleEffect.REVIEW,
        territories=("in",),
        channels=("WEB",),
    )
    assert rule.territories == ("IN",)
    assert rule.channels == ("web",)
    with pytest.raises(ValidationError, match="rule_id values must be unique"):
        publication_policy().model_copy(
            update={"regulatory_rules": (rule, rule)},
        ).model_validate(
            publication_policy().model_copy(
                update={"regulatory_rules": (rule, rule)}
            ).model_dump(mode="json", by_alias=True)
        )


def test_executor_rejects_policy_identity_and_registry_reference_mismatch() -> None:
    data = gradient_png()
    request = assessment_request(data)
    with pytest.raises(ValueError, match="policy identity"):
        execute_rightsgate_assessment(
            data,
            request=request,
            rights_registry=rights_registry(data),
            licence_registry=licence_registry(),
            policy=publication_policy().model_copy(update={"version": "other"}),
            created_at=NOW,
        )

    orphaned = licence_registry().licences[0].model_copy(
        update={"reference_ids": ("reference.absent",)}
    )
    with pytest.raises(ValueError, match="absent from the supplied rights registry"):
        execute_rightsgate_assessment(
            data,
            request=request,
            rights_registry=rights_registry(data),
            licence_registry=LicenceRegistry(
                registry_id="registry.orphaned",
                version="1",
                licences=(orphaned,),
            ),
            policy=publication_policy(),
            created_at=NOW,
        )


def _multipart_payload(data: bytes, *, key: str = "request.execute-001") -> tuple[dict, dict]:
    request = assessment_request(data, key=key)
    form = {
        "request_json": request.model_dump_json(by_alias=True),
        "rights_registry_json": rights_registry(data).model_dump_json(by_alias=True),
        "licence_registry_json": licence_registry().model_dump_json(by_alias=True),
        "policy_json": publication_policy().model_dump_json(by_alias=True),
        "max_hamming_distance": "6",
    }
    files = {"file": ("campaign.png", data, "image/png")}
    return form, files


def test_execution_endpoint_persists_and_replays_exact_result(client: TestClient) -> None:
    data = gradient_png()
    form, files = _multipart_payload(data)
    first = client.post("/api/v1/rightsgate/assessments", data=form, files=files)
    second = client.post("/api/v1/rightsgate/assessments", data=form, files=files)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_body = first.json()
    second_body = second.json()
    assert first_body["replayed"] is False
    assert second_body["replayed"] is True
    assert first_body["assessment_sha256"] == second_body["assessment_sha256"]
    assert first_body["assessment"] == second_body["assessment"]
    assert first_body["release_authorization"] is False

    stored = client.get("/api/v1/rightsgate/assessments/request.execute-001")
    assert stored.status_code == 200
    assert stored.json()["status"] == "COMPLETE"
    assert stored.json()["assessment_sha256"] == first_body["assessment_sha256"]


def test_cms_receipt_is_signed_stable_and_never_authorizes_release(client: TestClient) -> None:
    data = gradient_png()
    form, files = _multipart_payload(data, key="request.cms-001")
    executed = client.post("/api/v1/rightsgate/assessments", data=form, files=files)
    assert executed.status_code == 200, executed.text
    execution = executed.json()
    request = {
        "schema": "veilgraph.rightsgate.cms-decision-request.v1",
        "cms_system_id": "cms.demo",
        "content_id": "content.campaign-001",
        "assessment_idempotency_key": execution["idempotency_key"],
        "expected_asset_sha256": execution["assessment"]["asset"]["sha256"],
        "expected_assessment_sha256": execution["assessment_sha256"],
        "requested_action": "REQUEST_PUBLICATION",
    }

    first = client.post("/api/v1/rightsgate/integrations/cms/decision", json=request)
    second = client.post("/api/v1/rightsgate/integrations/cms/decision", json=request)
    assert first.status_code == 200, first.text
    assert first.json() == second.json()
    receipt = first.json()
    assert receipt["payload"]["workflow_status"] == "HUMAN_REVIEW_REQUIRED"
    assert receipt["payload"]["release_authorization"] is False
    assert receipt["payload"]["assessment_sha256"] == execution["assessment_sha256"]

    verified = client.post(
        "/api/v1/rightsgate/integrations/cms/receipts/verify",
        json=receipt,
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    assert verified.json()["release_authorization"] is False

    receipt["payload"]["content_id"] = "content.tampered"
    tampered = client.post(
        "/api/v1/rightsgate/integrations/cms/receipts/verify",
        json=receipt,
    )
    assert tampered.status_code == 200
    assert tampered.json()["valid"] is False

    attacker = Ed25519PrivateKey.generate()
    attacker_public = attacker.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    attacker_public_b64 = base64.b64encode(attacker_public).decode("ascii")
    canonical_payload = json.dumps(
        receipt["payload"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    attacker_signature = base64.b64encode(attacker.sign(canonical_payload)).decode("ascii")
    receipt["public_key_b64"] = attacker_public_b64
    receipt["signer_fingerprint"] = hashlib.sha256(attacker_public).hexdigest()
    receipt["signature_b64"] = attacker_signature
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            {
                "payload": receipt["payload"],
                "public_key_b64": attacker_public_b64,
                "signature_b64": attacker_signature,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    untrusted = client.post(
        "/api/v1/rightsgate/integrations/cms/receipts/verify",
        json=receipt,
    )
    assert untrusted.status_code == 200
    assert untrusted.json()["valid"] is False


def test_cms_receipt_rejects_commitment_mismatch(client: TestClient) -> None:
    data = gradient_png()
    form, files = _multipart_payload(data, key="request.cms-mismatch")
    execution = client.post(
        "/api/v1/rightsgate/assessments",
        data=form,
        files=files,
    ).json()
    response = client.post(
        "/api/v1/rightsgate/integrations/cms/decision",
        json={
            "cms_system_id": "cms.demo",
            "content_id": "content.campaign-002",
            "assessment_idempotency_key": execution["idempotency_key"],
            "expected_asset_sha256": "0" * 64,
            "expected_assessment_sha256": execution["assessment_sha256"],
        },
    )

    assert response.status_code == 409
    assert "asset commitment" in response.text


def test_execution_endpoint_rejects_idempotency_conflict(client: TestClient) -> None:
    data = gradient_png()
    form, files = _multipart_payload(data)
    assert client.post("/api/v1/rightsgate/assessments", data=form, files=files).status_code == 200
    form["max_hamming_distance"] = "5"

    conflict = client.post("/api/v1/rightsgate/assessments", data=form, files=files)
    assert conflict.status_code == 409
    assert "different assessment inputs" in conflict.text


def test_equivalent_execution_can_use_a_distinct_idempotency_key(client: TestClient) -> None:
    data = gradient_png()
    first_form, files = _multipart_payload(data, key="request.equivalent-001")
    second_form, _ = _multipart_payload(data, key="request.equivalent-002")

    first = client.post("/api/v1/rightsgate/assessments", data=first_form, files=files)
    second = client.post("/api/v1/rightsgate/assessments", data=second_form, files=files)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["execution_sha256"] == second.json()["execution_sha256"]
    assert (
        first.json()["assessment"]["assessment_id"]
        != second.json()["assessment"]["assessment_id"]
    )
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is False


def test_execution_endpoint_rejects_unbound_bytes_without_reserving_key(
    client: TestClient,
) -> None:
    declared = gradient_png()
    supplied = gradient_png(reverse=True)
    form, _ = _multipart_payload(declared, key="request.unbound-001")
    response = client.post(
        "/api/v1/rightsgate/assessments",
        data=form,
        files={"file": ("campaign.png", supplied, "image/png")},
    )

    assert response.status_code == 400
    assert "SHA-256" in response.text
    assert client.get("/api/v1/rightsgate/assessments/request.unbound-001").status_code == 404


def test_store_recovers_expired_lease_and_preserves_conflict(tmp_path) -> None:
    database = Database(tmp_path / "rightsgate.db")
    store = RightsGateAssessmentStore(database, lease_seconds=60)
    request = assessment_request(gradient_png())
    first = store.reserve(request=request, execution_sha256="a" * 64)
    assert first.state == ReservationState.ACQUIRED
    in_progress = store.reserve(request=request, execution_sha256="a" * 64)
    assert in_progress.state == ReservationState.IN_PROGRESS

    with database.connection() as connection:
        connection.execute(
            "UPDATE rightsgate_assessments SET lease_expires_at=? WHERE idempotency_key=?",
            ((NOW - timedelta(days=1)).isoformat(), request.idempotency_key),
        )
    recovered = store.reserve(request=request, execution_sha256="a" * 64)
    assert recovered.state == ReservationState.ACQUIRED
    assert recovered.attempt_count == 2

    with pytest.raises(IdempotencyConflict):
        store.reserve(request=request, execution_sha256="b" * 64)


def test_store_completion_is_immutable_and_failure_is_bounded(tmp_path) -> None:
    data = gradient_png()
    request = assessment_request(data)
    assessment = execute_fixture(data)
    database = Database(tmp_path / "rightsgate.db")
    store = RightsGateAssessmentStore(database)
    reservation = store.reserve(request=request, execution_sha256="c" * 64)
    commitment = store.complete(
        idempotency_key=request.idempotency_key,
        execution_sha256="c" * 64,
        attempt_count=reservation.attempt_count,
        assessment=assessment,
    )
    replay = store.reserve(request=request, execution_sha256="c" * 64)
    assert replay.state == ReservationState.REPLAY
    assert replay.assessment_sha256 == commitment
    assert replay.assessment == assessment

    failed_request = assessment_request(data, key="request.failed-001")
    failed_reservation = store.reserve(request=failed_request, execution_sha256="d" * 64)
    store.fail(
        idempotency_key=failed_request.idempotency_key,
        execution_sha256="d" * 64,
        attempt_count=failed_reservation.attempt_count,
        failure_code="SAFE_FAILURE",
    )
    failed = store.reserve(request=failed_request, execution_sha256="d" * 64)
    assert failed.state == ReservationState.FAILED
    assert failed.failure_code == "SAFE_FAILURE"


def test_store_detects_persisted_result_tampering(tmp_path) -> None:
    data = gradient_png()
    request = assessment_request(data)
    database = Database(tmp_path / "rightsgate.db")
    store = RightsGateAssessmentStore(database)
    reservation = store.reserve(request=request, execution_sha256="e" * 64)
    store.complete(
        idempotency_key=request.idempotency_key,
        execution_sha256="e" * 64,
        attempt_count=reservation.attempt_count,
        assessment=execute_fixture(data),
    )
    with database.connection() as connection:
        connection.execute(
            "UPDATE rightsgate_assessments SET assessment_sha256=? WHERE idempotency_key=?",
            ("f" * 64, request.idempotency_key),
        )

    with pytest.raises(StoredAssessmentIntegrityError):
        store.get(request.idempotency_key)


def test_store_fences_stale_worker_after_lease_recovery(tmp_path) -> None:
    data = gradient_png()
    request = assessment_request(data)
    database = Database(tmp_path / "rightsgate.db")
    store = RightsGateAssessmentStore(database, lease_seconds=60)
    stale = store.reserve(request=request, execution_sha256="9" * 64)
    with database.connection() as connection:
        connection.execute(
            "UPDATE rightsgate_assessments SET lease_expires_at=? WHERE idempotency_key=?",
            ((NOW - timedelta(days=1)).isoformat(), request.idempotency_key),
        )
    current = store.reserve(request=request, execution_sha256="9" * 64)

    with pytest.raises(RuntimeError, match="no longer active"):
        store.complete(
            idempotency_key=request.idempotency_key,
            execution_sha256="9" * 64,
            attempt_count=stale.attempt_count,
            assessment=execute_fixture(data),
        )
    assert not store.fail(
        idempotency_key=request.idempotency_key,
        execution_sha256="9" * 64,
        attempt_count=stale.attempt_count,
        failure_code="STALE_FAILURE",
    )
    store.complete(
        idempotency_key=request.idempotency_key,
        execution_sha256="9" * 64,
        attempt_count=current.attempt_count,
        assessment=execute_fixture(data),
    )
    assert store.get(request.idempotency_key).state == ReservationState.REPLAY


def test_store_detects_persisted_request_tampering(tmp_path) -> None:
    data = gradient_png()
    request = assessment_request(data)
    database = Database(tmp_path / "rightsgate.db")
    store = RightsGateAssessmentStore(database)
    store.reserve(request=request, execution_sha256="f" * 64)
    with database.connection() as connection:
        connection.execute(
            "UPDATE rightsgate_assessments SET request_json=? WHERE idempotency_key=?",
            ("{}", request.idempotency_key),
        )

    with pytest.raises(StoredAssessmentIntegrityError):
        store.get(request.idempotency_key)
