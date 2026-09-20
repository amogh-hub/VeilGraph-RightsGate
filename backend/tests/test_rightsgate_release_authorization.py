"""Security tests for RightsGate's separate dual-control release boundary."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.security.signing import (
    canonical_json_bytes,
    public_key_b64,
    sign_payload,
    signer_fingerprint,
)
from app.rightsgate.contracts import DeploymentDecision
from app.rightsgate.integration import (
    CMSDecisionPayload,
    CMSDecisionReceipt,
    CMSWorkflowStatus,
    _payload_json as cms_payload_json,
    _receipt_commitment as cms_receipt_commitment,
)
from app.rightsgate.release_authorization import (
    ReleaseApprovalPayload,
    ReleaseAuthorizationRequest,
    ReviewerAttestation,
    ReviewerRole,
    ReviewerTrustRegistry,
    TrustedReviewer,
    build_release_authorization_receipt,
    verify_release_authorization_receipt,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _reviewer(
    reviewer_id: str,
    role: ReviewerRole,
) -> tuple[Ed25519PrivateKey, TrustedReviewer]:
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return key, TrustedReviewer(
        reviewer_id=reviewer_id,
        display_name=reviewer_id.replace(".", " ").title(),
        role=role,
        public_key_b64=base64.b64encode(public).decode("ascii"),
        public_key_sha256=hashlib.sha256(public).hexdigest(),
        valid_from=NOW - timedelta(days=30),
        valid_until=NOW + timedelta(days=30),
    )


def _registry() -> tuple[
    ReviewerTrustRegistry,
    dict[str, Ed25519PrivateKey],
]:
    rights_key, rights = _reviewer("reviewer.rights", ReviewerRole.RIGHTS_REVIEWER)
    release_key, release = _reviewer("reviewer.release", ReviewerRole.RELEASE_MANAGER)
    return (
        ReviewerTrustRegistry(
            registry_id="registry.release-reviewers",
            version="2026.09.1",
            reviewers=(rights, release),
        ),
        {rights.reviewer_id: rights_key, release.reviewer_id: release_key},
    )


def _cms_receipt(
    decision: DeploymentDecision = DeploymentDecision.GO,
) -> CMSDecisionReceipt:
    status = {
        DeploymentDecision.GO: CMSWorkflowStatus.READY_FOR_RELEASE_AUTHORIZATION,
        DeploymentDecision.REVIEW: CMSWorkflowStatus.HUMAN_REVIEW_REQUIRED,
        DeploymentDecision.BLOCK: CMSWorkflowStatus.BLOCKED,
    }[decision]
    payload = CMSDecisionPayload(
        cms_system_id="cms.demo",
        content_id="content.campaign-001",
        assessment_idempotency_key="request.release-001",
        assessment_id="assessment.release-001",
        asset_sha256="a" * 64,
        request_sha256="b" * 64,
        execution_sha256="c" * 64,
        assessment_sha256="d" * 64,
        deployment_decision=decision,
        workflow_status=status,
        assessed_at=NOW - timedelta(minutes=10),
    )
    signature = sign_payload(cms_payload_json(payload))
    public_key = public_key_b64()
    return CMSDecisionReceipt(
        payload=payload,
        signature_b64=signature,
        public_key_b64=public_key,
        signer_fingerprint=signer_fingerprint(),
        receipt_sha256=cms_receipt_commitment(
            payload=payload,
            signature_b64=signature,
            public_key_b64_value=public_key,
        ),
    )


def _request(
    registry: ReviewerTrustRegistry,
    keys: dict[str, Ed25519PrivateKey],
    *,
    decision: DeploymentDecision = DeploymentDecision.GO,
) -> ReleaseAuthorizationRequest:
    receipt = _cms_receipt(decision)
    approvals: list[ReviewerAttestation] = []
    for reviewer in registry.reviewers:
        payload = ReleaseApprovalPayload(
            approval_id=f"approval.{reviewer.reviewer_id}",
            reviewer_id=reviewer.reviewer_id,
            reviewer_role=reviewer.role,
            cms_receipt_sha256=receipt.receipt_sha256,
            assessment_sha256=receipt.payload.assessment_sha256,
            asset_sha256=receipt.payload.asset_sha256,
            cms_system_id=receipt.payload.cms_system_id,
            content_id=receipt.payload.content_id,
            reason="Reviewed the evidence package and approve this exact release.",
            reviewed_at=NOW - timedelta(minutes=2),
        )
        signature = keys[reviewer.reviewer_id].sign(
            canonical_json_bytes(payload.model_dump(mode="json", by_alias=True, exclude_none=True))
        )
        approvals.append(
            ReviewerAttestation(
                payload=payload,
                signature_b64=base64.b64encode(signature).decode("ascii"),
            )
        )
    return ReleaseAuthorizationRequest(
        decision_receipt=receipt,
        approvals=tuple(approvals),
    )


def test_dual_control_release_receipt_verifies_entire_chain() -> None:
    registry, keys = _registry()
    receipt = build_release_authorization_receipt(
        _request(registry, keys),
        registry=registry,
        now=NOW,
    )

    result = verify_release_authorization_receipt(
        receipt,
        registry=registry,
        now=NOW + timedelta(minutes=1),
    )

    assert result.valid is True
    assert result.release_authorization is True
    assert receipt.payload.release_authorization is True
    assert set(receipt.payload.reviewer_ids) == {"reviewer.rights", "reviewer.release"}
    assert receipt.payload.expires_at == NOW + timedelta(minutes=15)


def test_review_or_block_can_never_enter_release_authorization() -> None:
    registry, keys = _registry()
    with pytest.raises(ValueError, match="only a valid GO"):
        build_release_authorization_receipt(
            _request(registry, keys, decision=DeploymentDecision.REVIEW),
            registry=registry,
            now=NOW,
        )


def test_revocation_expiry_and_tampering_fail_closed() -> None:
    registry, keys = _registry()
    receipt = build_release_authorization_receipt(
        _request(registry, keys),
        registry=registry,
        now=NOW,
    )
    expired = verify_release_authorization_receipt(
        receipt,
        registry=registry,
        now=NOW + timedelta(minutes=16),
    )
    assert expired.valid is False
    assert expired.release_authorization is False
    assert "expired" in expired.reason

    revoked_reviewers = tuple(
        reviewer.model_copy(update={"active": False})
        if reviewer.role == ReviewerRole.RIGHTS_REVIEWER
        else reviewer
        for reviewer in registry.reviewers
    )
    revoked = ReviewerTrustRegistry(
        registry_id=registry.registry_id,
        version="2026.09.2",
        reviewers=revoked_reviewers,
    )
    verification = verify_release_authorization_receipt(
        receipt,
        registry=revoked,
        now=NOW + timedelta(minutes=1),
    )
    assert verification.valid is False
    assert verification.release_authorization is False
    assert "registry commitment changed" in verification.reason

    tampered_payload = receipt.payload.model_copy(update={"content_id": "content.other"})
    tampered = receipt.model_copy(update={"payload": tampered_payload})
    verification = verify_release_authorization_receipt(
        tampered,
        registry=registry,
        now=NOW + timedelta(minutes=1),
    )
    assert verification.valid is False
    assert "commitment" in verification.reason


def test_untrusted_reviewer_signature_and_role_separation_are_rejected() -> None:
    registry, keys = _registry()
    request = _request(registry, keys)
    attacker = Ed25519PrivateKey.generate()
    forged = request.approvals[0].model_copy(
        update={
            "signature_b64": base64.b64encode(
                attacker.sign(
                    canonical_json_bytes(
                        request.approvals[0].payload.model_dump(
                            mode="json", by_alias=True, exclude_none=True
                        )
                    )
                )
            ).decode("ascii")
        }
    )
    with pytest.raises(ValueError, match="signature is invalid"):
        build_release_authorization_receipt(
            request.model_copy(update={"approvals": (forged, request.approvals[1])}),
            registry=registry,
            now=NOW,
        )

    release_only_reviewers = tuple(
        reviewer.model_copy(update={"role": ReviewerRole.RELEASE_MANAGER})
        for reviewer in registry.reviewers
    )
    release_only_registry = ReviewerTrustRegistry(
        registry_id="registry.release-only",
        version="1",
        reviewers=release_only_reviewers,
    )
    release_only_request = _request(release_only_registry, keys)
    with pytest.raises(ValueError, match="RIGHTS_REVIEWER"):
        build_release_authorization_receipt(
            release_only_request,
            registry=release_only_registry,
            now=NOW,
        )
