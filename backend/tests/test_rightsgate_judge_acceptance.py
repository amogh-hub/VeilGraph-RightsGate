"""Exercise generated judge fixtures through the public assessment and CMS APIs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.rightsgate import (
    AssessmentContext,
    AssetDescriptor,
    AssetIR,
    AssetRepresentation,
    EvidenceLocator,
    LocatorKind,
    MediaKind,
    RepresentationKind,
    RightsGateAssessmentRequest,
)
from app.rightsgate.policy import PublicationPolicy, RegulatoryRule, RegulatoryRuleEffect
from app.rightsgate.provenance import VisibleWatermarkRegistry
from app.rightsgate.rights import (
    ConsentRegistry,
    LicenceRecord,
    LicenceRegistry,
    ReferenceKind,
    RightsReferenceRegistry,
    build_registry_image,
)
from prepare_rightsgate_judge_demo import build_demo


def _assessment_request(data: bytes, filename: str, key: str) -> RightsGateAssessmentRequest:
    digest = hashlib.sha256(data).hexdigest()
    return RightsGateAssessmentRequest(
        idempotency_key=key,
        asset_ir=AssetIR(
            asset=AssetDescriptor(
                asset_id=f"asset.{digest[:24]}",
                sha256=digest,
                media_kind=MediaKind.IMAGE,
                media_type="image/png",
                size_bytes=len(data),
                original_filename=filename,
                width=512,
                height=320,
            ),
            representations=(
                AssetRepresentation(
                    representation_id=f"representation.original-{digest[:16]}",
                    kind=RepresentationKind.ORIGINAL,
                    sha256=digest,
                    media_type="image/png",
                    size_bytes=len(data),
                    locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                ),
            ),
        ),
        context=AssessmentContext(
            policy_id="policy.techgium-demo",
            policy_version="2026.09.1",
            intended_use="Public advertising campaign",
            channel="web",
            audience="general",
            territories=("IN",),
            brand_profile="default",
        ),
    )


def _publication_policy() -> PublicationPolicy:
    return PublicationPolicy(
        policy_id="policy.techgium-demo",
        version="2026.09.1",
        allowed_channels=("web",),
        allowed_audiences=("general",),
        allowed_brand_profiles=("default",),
        allowed_territories=("IN",),
        required_component_ids=(
            "provenance.c2pa",
            "provenance.independent-forensics",
            "provenance.watermark-forensics",
            "rights.local-image-registry",
            "rights.licence-evaluator",
            "rights.trademark-localizer",
            "rights.likeness-consent",
        ),
        regulatory_rules=(
            RegulatoryRule(
                rule_id="demo.synthetic-publication-review",
                description="Synthetic or unresolved public media requires documented human review.",
                effect=RegulatoryRuleEffect.REVIEW,
                territories=("IN",),
                channels=("web",),
                audiences=("general",),
                brand_profiles=("default",),
                provenance_verdicts=("AI_GENERATED", "PARTIALLY_GENERATED", "UNKNOWN"),
            ),
        ),
    )


def _execute_demo_case(
    client: TestClient,
    *,
    data: bytes,
    filename: str,
    key: str,
    reference_data: bytes | None,
    licensed: bool,
    watermark_registry: VisibleWatermarkRegistry,
) -> dict:
    request = _assessment_request(data, filename, key)
    references = (
        (
            build_registry_image(
                reference_id="reference.synthetic-campaign-v1",
                kind=ReferenceKind.COPYRIGHTED_WORK,
                title="synthetic-campaign-reference.png",
                rights_holder="Synthetic demo rights holder",
                data=reference_data,
                media_type="image/png",
                source_record_id="rights-record.synthetic-campaign-v1",
            ),
        )
        if reference_data is not None
        else ()
    )
    rights_registry = RightsReferenceRegistry(
        registry_id="registry.techgium-demo-rights",
        version="2026.09.1",
        references=references,
    )
    now = datetime.now(timezone.utc)
    licences = (
        (
            LicenceRecord(
                licence_id="licence.synthetic-campaign-v1",
                source_record_id="licence-record.synthetic-campaign-v1",
                reference_ids=("reference.synthetic-campaign-v1",),
                licensor="Synthetic demo rights holder",
                licensee="Demo content team",
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),
                territories=("IN",),
                channels=("web",),
                intended_uses=("Public advertising campaign",),
            ),
        )
        if licensed and reference_data is not None
        else ()
    )
    licence_registry = LicenceRegistry(
        registry_id="registry.techgium-demo-licences",
        version="2026.09.1",
        licences=licences,
    )
    consent_registry = ConsentRegistry(
        registry_id="registry.techgium-demo-consents",
        version="2026.09.1",
    )
    response = client.post(
        "/api/v1/rightsgate/assessments",
        data={
            "request_json": request.model_dump_json(by_alias=True),
            "rights_registry_json": rights_registry.model_dump_json(by_alias=True),
            "licence_registry_json": licence_registry.model_dump_json(by_alias=True),
            "policy_json": _publication_policy().model_dump_json(by_alias=True),
            "watermark_registry_json": watermark_registry.model_dump_json(by_alias=True),
            "consent_registry_json": consent_registry.model_dump_json(by_alias=True),
            "max_hamming_distance": "6",
        },
        files={"file": (filename, data, "image/png")},
    )
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt["release_authorization"] is False
    assert receipt["replayed"] is False
    assessment = receipt["assessment"]
    assert assessment["schema"] == "veilgraph.rightsgate.assessment.v1"
    assert assessment["asset"]["sha256"] == hashlib.sha256(data).hexdigest()
    evidence_ids = {item["evidence_id"] for item in assessment["evidence"]}
    assert evidence_ids
    for dimension in ("provenance", "rights", "deployment"):
        output = assessment[dimension]
        assert 0 <= output["confidence"] <= 1
        for claim in output["claims"]:
            assert set(claim["evidence_ids"]).issubset(evidence_ids)
    cms = client.post(
        "/api/v1/rightsgate/integrations/cms/decision",
        json={
            "schema": "veilgraph.rightsgate.cms-decision-request.v1",
            "cms_system_id": "cms.techgium-demo",
            "content_id": f"content.{hashlib.sha256(data).hexdigest()[:24]}",
            "assessment_idempotency_key": key,
            "expected_asset_sha256": hashlib.sha256(data).hexdigest(),
            "expected_assessment_sha256": receipt["assessment_sha256"],
            "requested_action": "REQUEST_PUBLICATION",
        },
    )
    assert cms.status_code == 200, cms.text
    receipt["cms"] = cms.json()
    verified = client.post(
        "/api/v1/rightsgate/integrations/cms/receipts/verify", json=receipt["cms"]
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    return receipt


def test_generated_judge_cases_reach_expected_three_dimension_decisions(
    client: TestClient, tmp_path: Path
) -> None:
    output = tmp_path / "judge-demo"
    build_demo(output)
    intact = (output / "synthetic-campaign-intact.png").read_bytes()
    altered = (output / "synthetic-campaign-watermark-altered.png").read_bytes()
    reference = (output / "synthetic-campaign-reference.png").read_bytes()
    empty_watermarks = VisibleWatermarkRegistry(
        registry_id="registry.techgium-demo-watermarks",
        version="2026.09.1",
    )
    enrolled_watermarks = VisibleWatermarkRegistry.model_validate(
        json.loads((output / "synthetic-watermark-registry.json").read_text())
    )

    licensed = _execute_demo_case(
        client,
        data=intact,
        filename="synthetic-campaign-intact.png",
        key="request.judge-licensed",
        reference_data=reference,
        licensed=True,
        watermark_registry=empty_watermarks,
    )
    assert licensed["assessment"]["deployment"]["decision"] == "REVIEW"
    assert licensed["cms"]["payload"]["workflow_status"] == "HUMAN_REVIEW_REQUIRED"

    no_reference = _execute_demo_case(
        client,
        data=intact,
        filename="synthetic-campaign-intact.png",
        key="request.judge-no-reference",
        reference_data=None,
        licensed=False,
        watermark_registry=empty_watermarks,
    )
    assert no_reference["assessment"]["rights"]["verdict"] == "UNKNOWN"
    assert no_reference["assessment"]["deployment"]["decision"] == "REVIEW"
    assert any(
        "not proof of rights clearance" in limitation
        for limitation in no_reference["assessment"]["rights"]["limitations"]
    )

    unlicensed = _execute_demo_case(
        client,
        data=intact,
        filename="synthetic-campaign-intact.png",
        key="request.judge-unlicensed",
        reference_data=reference,
        licensed=False,
        watermark_registry=empty_watermarks,
    )
    assert unlicensed["assessment"]["rights"]["verdict"] == "POLICY_CONFLICT"
    assert unlicensed["assessment"]["deployment"]["decision"] == "BLOCK"
    assert any(
        "rights.licence-coverage" in citation
        for citation in unlicensed["assessment"]["deployment"]["policy_citations"]
    )
    assert unlicensed["cms"]["payload"]["workflow_status"] == "BLOCKED"

    watermark_altered = _execute_demo_case(
        client,
        data=altered,
        filename="synthetic-campaign-watermark-altered.png",
        key="request.judge-watermark",
        reference_data=None,
        licensed=False,
        watermark_registry=enrolled_watermarks,
    )
    assert watermark_altered["assessment"]["provenance"]["verdict"] == "TAMPERED"
    assert watermark_altered["assessment"]["deployment"]["decision"] == "BLOCK"
    assert watermark_altered["cms"]["payload"]["workflow_status"] == "BLOCKED"
