"""Dual-control release authorization bound to a signed RightsGate decision.

The CMS decision receipt deliberately never authorizes publication. This module
implements the separate release boundary: a valid ``GO`` decision plus two
cryptographically authenticated, role-separated human approvals. Reviewer keys
come only from an operator-governed local trust registry; caller-supplied keys
are never trusted.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.security.signing import public_key_b64, sign_payload, signer_fingerprint, verify_payload

from .contracts import ID_PATTERN, SHA256_PATTERN, DeploymentDecision, StrictFrozenModel
from .integration import (
    CMSDecisionReceipt,
    CMSWorkflowStatus,
    verify_cms_decision_receipt,
)

REVIEWER_REGISTRY_SCHEMA = "veilgraph.rightsgate.reviewer-trust-registry.v1"
RELEASE_REQUEST_SCHEMA = "veilgraph.rightsgate.release-authorization-request.v1"
RELEASE_PAYLOAD_SCHEMA = "veilgraph.rightsgate.release-authorization-payload.v1"
RELEASE_RECEIPT_SCHEMA = "veilgraph.rightsgate.release-authorization-receipt.v1"
RELEASE_VERIFICATION_SCHEMA = "veilgraph.rightsgate.release-authorization-verification.v1"


class ReviewerRole(str, Enum):
    RIGHTS_REVIEWER = "RIGHTS_REVIEWER"
    RELEASE_MANAGER = "RELEASE_MANAGER"


class TrustedReviewer(StrictFrozenModel):
    reviewer_id: str = Field(pattern=ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    role: ReviewerRole
    public_key_b64: str = Field(min_length=1, max_length=128)
    public_key_sha256: str = Field(pattern=SHA256_PATTERN)
    active: bool = True
    valid_from: datetime
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_key_and_window(self) -> TrustedReviewer:
        if self.valid_from.tzinfo is None or self.valid_from.utcoffset() is None:
            raise ValueError("reviewer valid_from must be timezone-aware")
        if self.valid_until is not None:
            if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
                raise ValueError("reviewer valid_until must be timezone-aware")
            if self.valid_until <= self.valid_from:
                raise ValueError("reviewer valid_until must be after valid_from")
        try:
            public_key = base64.b64decode(self.public_key_b64, validate=True)
        except ValueError as error:
            raise ValueError("reviewer public key must be valid base64") from error
        if len(public_key) != 32:
            raise ValueError("reviewer public key must contain 32 Ed25519 bytes")
        if hashlib.sha256(public_key).hexdigest() != self.public_key_sha256:
            raise ValueError("reviewer public-key fingerprint does not match")
        return self


class ReviewerTrustRegistry(StrictFrozenModel):
    schema_id: Literal[REVIEWER_REGISTRY_SCHEMA] = Field(
        default=REVIEWER_REGISTRY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    registry_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=100)
    reviewers: tuple[TrustedReviewer, ...] = Field(min_length=2, max_length=1000)

    @field_validator("reviewers")
    @classmethod
    def normalize_reviewers(
        cls,
        reviewers: tuple[TrustedReviewer, ...],
    ) -> tuple[TrustedReviewer, ...]:
        reviewer_ids = [item.reviewer_id for item in reviewers]
        fingerprints = [item.public_key_sha256 for item in reviewers]
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError("reviewer IDs must be unique")
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("one reviewer key cannot represent multiple reviewers")
        return tuple(sorted(reviewers, key=lambda item: item.reviewer_id))

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def commitment_sha256(self) -> str:
        return _canonical_hash(self.canonical_payload())


class ReleaseApprovalPayload(StrictFrozenModel):
    approval_schema: Literal["veilgraph.rightsgate.release-approval.v1"] = (
        "veilgraph.rightsgate.release-approval.v1"
    )
    approval_id: str = Field(pattern=ID_PATTERN)
    reviewer_id: str = Field(pattern=ID_PATTERN)
    reviewer_role: ReviewerRole
    cms_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    assessment_sha256: str = Field(pattern=SHA256_PATTERN)
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    cms_system_id: str = Field(pattern=ID_PATTERN)
    content_id: str = Field(pattern=ID_PATTERN)
    action: Literal["APPROVE_RELEASE"] = "APPROVE_RELEASE"
    reason: str = Field(min_length=12, max_length=1000)
    reviewed_at: datetime

    @model_validator(mode="after")
    def require_aware_review_time(self) -> ReleaseApprovalPayload:
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return self


class ReviewerAttestation(StrictFrozenModel):
    payload: ReleaseApprovalPayload
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_b64: str = Field(min_length=1, max_length=512)

    def commitment_sha256(self) -> str:
        return _canonical_hash(self.model_dump(mode="json", exclude_none=True))


class ReleaseAuthorizationRequest(StrictFrozenModel):
    schema_id: Literal[RELEASE_REQUEST_SCHEMA] = Field(
        default=RELEASE_REQUEST_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    decision_receipt: CMSDecisionReceipt
    approvals: tuple[ReviewerAttestation, ...] = Field(min_length=2, max_length=10)

    @field_validator("approvals")
    @classmethod
    def normalize_approvals(
        cls,
        approvals: tuple[ReviewerAttestation, ...],
    ) -> tuple[ReviewerAttestation, ...]:
        approval_ids = [item.payload.approval_id for item in approvals]
        reviewer_ids = [item.payload.reviewer_id for item in approvals]
        if len(approval_ids) != len(set(approval_ids)):
            raise ValueError("approval IDs must be unique")
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError("each required approval must come from a distinct reviewer")
        return tuple(sorted(approvals, key=lambda item: item.payload.approval_id))


class ReleaseAuthorizationPayload(StrictFrozenModel):
    schema_id: Literal[RELEASE_PAYLOAD_SCHEMA] = Field(
        default=RELEASE_PAYLOAD_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    authorization_id: str = Field(pattern=ID_PATTERN)
    cms_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    assessment_sha256: str = Field(pattern=SHA256_PATTERN)
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    cms_system_id: str = Field(pattern=ID_PATTERN)
    content_id: str = Field(pattern=ID_PATTERN)
    reviewer_registry_sha256: str = Field(pattern=SHA256_PATTERN)
    approval_sha256s: tuple[str, ...] = Field(min_length=2, max_length=10)
    reviewer_ids: tuple[str, ...] = Field(min_length=2, max_length=10)
    issued_at: datetime
    expires_at: datetime
    release_authorization: Literal[True] = True

    @model_validator(mode="after")
    def validate_authorization_window(self) -> ReleaseAuthorizationPayload:
        for field_name, value in (("issued_at", self.issued_at), ("expires_at", self.expires_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        if len(set(self.approval_sha256s)) != len(self.approval_sha256s):
            raise ValueError("approval commitments must be unique")
        if len(set(self.reviewer_ids)) != len(self.reviewer_ids):
            raise ValueError("reviewer IDs must be unique")
        return self


class ReleaseAuthorizationReceipt(StrictFrozenModel):
    receipt_schema: Literal[RELEASE_RECEIPT_SCHEMA] = RELEASE_RECEIPT_SCHEMA
    payload: ReleaseAuthorizationPayload
    decision_receipt: CMSDecisionReceipt
    approvals: tuple[ReviewerAttestation, ...]
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_b64: str = Field(min_length=1, max_length=512)
    public_key_b64: str = Field(min_length=1, max_length=512)
    signer_fingerprint: str = Field(pattern=SHA256_PATTERN)
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)


class ReleaseAuthorizationVerification(StrictFrozenModel):
    verification_schema: Literal[RELEASE_VERIFICATION_SCHEMA] = RELEASE_VERIFICATION_SCHEMA
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    valid: bool
    release_authorization: bool
    reason: str = Field(min_length=1, max_length=500)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payload_json(payload: StrictFrozenModel) -> dict[str, Any]:
    return payload.model_dump(mode="json", by_alias=True, exclude_none=True)


def _receipt_commitment(
    *,
    payload: ReleaseAuthorizationPayload,
    decision_receipt: CMSDecisionReceipt,
    approvals: tuple[ReviewerAttestation, ...],
    signature_b64: str,
    public_key_b64_value: str,
) -> str:
    return _canonical_hash(
        {
            "approvals": [_payload_json(item) for item in approvals],
            "decision_receipt": _payload_json(decision_receipt),
            "payload": _payload_json(payload),
            "public_key_b64": public_key_b64_value,
            "signature_b64": signature_b64,
        }
    )


def _validate_approvals(
    request: ReleaseAuthorizationRequest,
    *,
    registry: ReviewerTrustRegistry,
    now: datetime,
    max_review_age_seconds: int,
) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if max_review_age_seconds < 60:
        raise ValueError("max_review_age_seconds must be at least 60")
    decision = request.decision_receipt
    if not verify_cms_decision_receipt(decision):
        raise ValueError("CMS decision receipt is invalid or signed by an untrusted signer")
    if (
        decision.payload.deployment_decision != DeploymentDecision.GO
        or decision.payload.workflow_status != CMSWorkflowStatus.READY_FOR_RELEASE_AUTHORIZATION
    ):
        raise ValueError("only a valid GO decision can enter release authorization")

    trusted_by_id = {item.reviewer_id: item for item in registry.reviewers}
    observed_roles: set[ReviewerRole] = set()
    for attestation in request.approvals:
        approval = attestation.payload
        reviewer = trusted_by_id.get(approval.reviewer_id)
        if reviewer is None or not reviewer.active:
            raise ValueError(f"reviewer {approval.reviewer_id} is not actively trusted")
        if reviewer.role != approval.reviewer_role:
            raise ValueError(f"reviewer {approval.reviewer_id} asserted an untrusted role")
        if approval.reviewed_at < reviewer.valid_from or (
            reviewer.valid_until is not None and approval.reviewed_at > reviewer.valid_until
        ):
            raise ValueError(f"reviewer {approval.reviewer_id} approval is outside key validity")
        if approval.reviewed_at < decision.payload.assessed_at:
            raise ValueError("release approval predates the bound assessment")
        if approval.reviewed_at > now + timedelta(minutes=5):
            raise ValueError("release approval timestamp is too far in the future")
        if now - approval.reviewed_at > timedelta(seconds=max_review_age_seconds):
            raise ValueError("release approval is stale")
        expected_bindings = {
            "cms_receipt_sha256": decision.receipt_sha256,
            "assessment_sha256": decision.payload.assessment_sha256,
            "asset_sha256": decision.payload.asset_sha256,
            "cms_system_id": decision.payload.cms_system_id,
            "content_id": decision.payload.content_id,
        }
        for field_name, expected in expected_bindings.items():
            if getattr(approval, field_name) != expected:
                raise ValueError(f"release approval {field_name} does not match the CMS decision")
        if not verify_payload(
            _payload_json(approval),
            attestation.signature_b64,
            reviewer.public_key_b64,
        ):
            raise ValueError(f"reviewer {approval.reviewer_id} signature is invalid")
        observed_roles.add(approval.reviewer_role)

    required_roles = {ReviewerRole.RIGHTS_REVIEWER, ReviewerRole.RELEASE_MANAGER}
    if not required_roles.issubset(observed_roles):
        raise ValueError("release requires distinct RIGHTS_REVIEWER and RELEASE_MANAGER approvals")


def build_release_authorization_receipt(
    request: ReleaseAuthorizationRequest,
    *,
    registry: ReviewerTrustRegistry,
    now: datetime,
    authorization_ttl_seconds: int = 900,
    max_review_age_seconds: int = 86_400,
) -> ReleaseAuthorizationReceipt:
    """Issue a short-lived release authorization after dual-control verification."""

    if not 60 <= authorization_ttl_seconds <= 3600:
        raise ValueError("authorization TTL must be between 60 and 3600 seconds")
    _validate_approvals(
        request,
        registry=registry,
        now=now,
        max_review_age_seconds=max_review_age_seconds,
    )
    approvals = request.approvals
    approval_sha256s = tuple(item.commitment_sha256() for item in approvals)
    decision = request.decision_receipt
    token = _canonical_hash(
        {
            "approvals": approval_sha256s,
            "decision_receipt_sha256": decision.receipt_sha256,
            "registry_sha256": registry.commitment_sha256(),
        }
    )[:32]
    payload = ReleaseAuthorizationPayload(
        authorization_id=f"release.{token}",
        cms_receipt_sha256=decision.receipt_sha256,
        assessment_sha256=decision.payload.assessment_sha256,
        asset_sha256=decision.payload.asset_sha256,
        cms_system_id=decision.payload.cms_system_id,
        content_id=decision.payload.content_id,
        reviewer_registry_sha256=registry.commitment_sha256(),
        approval_sha256s=approval_sha256s,
        reviewer_ids=tuple(sorted(item.payload.reviewer_id for item in approvals)),
        issued_at=now,
        expires_at=now + timedelta(seconds=authorization_ttl_seconds),
    )
    serialized = _payload_json(payload)
    signature = sign_payload(serialized)
    public_key = public_key_b64()
    return ReleaseAuthorizationReceipt(
        payload=payload,
        decision_receipt=decision,
        approvals=approvals,
        signature_b64=signature,
        public_key_b64=public_key,
        signer_fingerprint=signer_fingerprint(),
        receipt_sha256=_receipt_commitment(
            payload=payload,
            decision_receipt=decision,
            approvals=approvals,
            signature_b64=signature,
            public_key_b64_value=public_key,
        ),
    )


def verify_release_authorization_receipt(
    receipt: ReleaseAuthorizationReceipt,
    *,
    registry: ReviewerTrustRegistry,
    now: datetime,
    expected_signer_fingerprint: str | None = None,
) -> ReleaseAuthorizationVerification:
    """Verify the entire decision/approval/release chain and current trust state."""

    def invalid(reason: str) -> ReleaseAuthorizationVerification:
        return ReleaseAuthorizationVerification(
            receipt_sha256=receipt.receipt_sha256,
            valid=False,
            release_authorization=False,
            reason=reason,
        )

    if now.tzinfo is None or now.utcoffset() is None:
        return invalid("verification time must be timezone-aware")
    if receipt.payload.expires_at < now:
        return invalid("release authorization has expired")
    if receipt.payload.issued_at > now + timedelta(minutes=5):
        return invalid("release authorization was issued in the future")
    try:
        public_key = base64.b64decode(receipt.public_key_b64, validate=True)
    except ValueError:
        return invalid("release signer public key is malformed")
    if hashlib.sha256(public_key).hexdigest() != receipt.signer_fingerprint:
        return invalid("release signer fingerprint does not match its public key")
    trusted_signer = expected_signer_fingerprint or signer_fingerprint()
    if receipt.signer_fingerprint != trusted_signer:
        return invalid("release signer is not trusted")
    if receipt.payload.reviewer_registry_sha256 != registry.commitment_sha256():
        return invalid("reviewer trust registry commitment changed")
    expected_commitment = _receipt_commitment(
        payload=receipt.payload,
        decision_receipt=receipt.decision_receipt,
        approvals=receipt.approvals,
        signature_b64=receipt.signature_b64,
        public_key_b64_value=receipt.public_key_b64,
    )
    if expected_commitment != receipt.receipt_sha256:
        return invalid("release receipt commitment does not match")
    if not verify_payload(
        _payload_json(receipt.payload),
        receipt.signature_b64,
        receipt.public_key_b64,
    ):
        return invalid("release receipt signature is invalid")
    if receipt.payload.cms_receipt_sha256 != receipt.decision_receipt.receipt_sha256:
        return invalid("release payload is not bound to the bundled CMS receipt")
    if tuple(item.commitment_sha256() for item in receipt.approvals) != (
        receipt.payload.approval_sha256s
    ):
        return invalid("release payload is not bound to the bundled approvals")
    if tuple(sorted(item.payload.reviewer_id for item in receipt.approvals)) != (
        receipt.payload.reviewer_ids
    ):
        return invalid("release reviewer identities do not match the payload")
    try:
        _validate_approvals(
            ReleaseAuthorizationRequest(
                decision_receipt=receipt.decision_receipt,
                approvals=receipt.approvals,
            ),
            registry=registry,
            now=now,
            max_review_age_seconds=86_400,
        )
    except ValueError as error:
        return invalid(str(error))
    decision = receipt.decision_receipt.payload
    if (
        receipt.payload.assessment_sha256 != decision.assessment_sha256
        or receipt.payload.asset_sha256 != decision.asset_sha256
        or receipt.payload.cms_system_id != decision.cms_system_id
        or receipt.payload.content_id != decision.content_id
    ):
        return invalid("release payload bindings do not match the CMS decision")
    return ReleaseAuthorizationVerification(
        receipt_sha256=receipt.receipt_sha256,
        valid=True,
        release_authorization=True,
        reason="GO decision and both currently trusted role-separated approvals verified.",
    )
