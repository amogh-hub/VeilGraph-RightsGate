"""Signed, non-authorizing CMS decision receipts for publication workflows."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.security.signing import public_key_b64, sign_payload, signer_fingerprint, verify_payload

from .contracts import (
    ID_PATTERN,
    SHA256_PATTERN,
    DeploymentDecision,
    RightsGateAssessment,
    StrictFrozenModel,
)

CMS_REQUEST_SCHEMA = "veilgraph.rightsgate.cms-decision-request.v1"
CMS_RECEIPT_SCHEMA = "veilgraph.rightsgate.cms-decision-receipt.v1"
CMS_PAYLOAD_SCHEMA = "veilgraph.rightsgate.cms-decision-payload.v1"


class CMSWorkflowStatus(str, Enum):
    BLOCKED = "BLOCKED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    READY_FOR_RELEASE_AUTHORIZATION = "READY_FOR_RELEASE_AUTHORIZATION"


class CMSDecisionRequest(StrictFrozenModel):
    schema_id: Literal[CMS_REQUEST_SCHEMA] = Field(
        default=CMS_REQUEST_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    cms_system_id: str = Field(pattern=ID_PATTERN)
    content_id: str = Field(pattern=ID_PATTERN)
    assessment_idempotency_key: str = Field(pattern=ID_PATTERN)
    expected_asset_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_assessment_sha256: str = Field(pattern=SHA256_PATTERN)
    requested_action: Literal["REQUEST_PUBLICATION"] = "REQUEST_PUBLICATION"


class CMSDecisionPayload(StrictFrozenModel):
    schema_id: Literal[CMS_PAYLOAD_SCHEMA] = Field(
        default=CMS_PAYLOAD_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    cms_system_id: str = Field(pattern=ID_PATTERN)
    content_id: str = Field(pattern=ID_PATTERN)
    assessment_idempotency_key: str = Field(pattern=ID_PATTERN)
    assessment_id: str = Field(pattern=ID_PATTERN)
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_sha256: str = Field(pattern=SHA256_PATTERN)
    assessment_sha256: str = Field(pattern=SHA256_PATTERN)
    deployment_decision: DeploymentDecision
    workflow_status: CMSWorkflowStatus
    assessed_at: datetime
    requested_action: Literal["REQUEST_PUBLICATION"] = "REQUEST_PUBLICATION"
    release_authorization: Literal[False] = False

    @model_validator(mode="after")
    def bind_status_to_decision(self) -> CMSDecisionPayload:
        expected = {
            DeploymentDecision.BLOCK: CMSWorkflowStatus.BLOCKED,
            DeploymentDecision.REVIEW: CMSWorkflowStatus.HUMAN_REVIEW_REQUIRED,
            DeploymentDecision.GO: CMSWorkflowStatus.READY_FOR_RELEASE_AUTHORIZATION,
        }[self.deployment_decision]
        if self.workflow_status != expected:
            raise ValueError("CMS workflow status does not match the deployment decision")
        if self.assessed_at.tzinfo is None or self.assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be timezone-aware")
        return self


class CMSDecisionReceipt(StrictFrozenModel):
    receipt_schema: Literal[CMS_RECEIPT_SCHEMA] = CMS_RECEIPT_SCHEMA
    payload: CMSDecisionPayload
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_b64: str = Field(min_length=1, max_length=512)
    public_key_b64: str = Field(min_length=1, max_length=512)
    signer_fingerprint: str = Field(pattern=SHA256_PATTERN)
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)


class CMSReceiptVerification(StrictFrozenModel):
    verification_schema: Literal["veilgraph.rightsgate.cms-receipt-verification.v1"] = (
        "veilgraph.rightsgate.cms-receipt-verification.v1"
    )
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    valid: bool
    release_authorization: Literal[False] = False


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payload_json(payload: CMSDecisionPayload) -> dict[str, Any]:
    return payload.model_dump(mode="json", by_alias=True, exclude_none=True)


def _receipt_commitment(
    *,
    payload: CMSDecisionPayload,
    signature_b64: str,
    public_key_b64_value: str,
) -> str:
    return _canonical_hash(
        {
            "payload": _payload_json(payload),
            "public_key_b64": public_key_b64_value,
            "signature_b64": signature_b64,
        }
    )


def build_cms_decision_receipt(
    request: CMSDecisionRequest,
    *,
    assessment: RightsGateAssessment,
    request_sha256: str,
    execution_sha256: str,
    assessment_sha256: str,
) -> CMSDecisionReceipt:
    """Build a deterministic decision receipt; never grant publication authority."""

    if assessment.asset.sha256 != request.expected_asset_sha256:
        raise ValueError("CMS request asset commitment does not match the assessment")
    if assessment.commitment_sha256() != assessment_sha256:
        raise ValueError("stored assessment commitment does not match the assessment payload")
    if assessment_sha256 != request.expected_assessment_sha256:
        raise ValueError("CMS request assessment commitment does not match the stored result")
    status = {
        DeploymentDecision.BLOCK: CMSWorkflowStatus.BLOCKED,
        DeploymentDecision.REVIEW: CMSWorkflowStatus.HUMAN_REVIEW_REQUIRED,
        DeploymentDecision.GO: CMSWorkflowStatus.READY_FOR_RELEASE_AUTHORIZATION,
    }[assessment.deployment.decision]
    payload = CMSDecisionPayload(
        cms_system_id=request.cms_system_id,
        content_id=request.content_id,
        assessment_idempotency_key=request.assessment_idempotency_key,
        assessment_id=assessment.assessment_id,
        asset_sha256=assessment.asset.sha256,
        request_sha256=request_sha256,
        execution_sha256=execution_sha256,
        assessment_sha256=assessment_sha256,
        deployment_decision=assessment.deployment.decision,
        workflow_status=status,
        assessed_at=assessment.created_at,
    )
    serialized = _payload_json(payload)
    signature = sign_payload(serialized)
    public_key = public_key_b64()
    return CMSDecisionReceipt(
        payload=payload,
        signature_b64=signature,
        public_key_b64=public_key,
        signer_fingerprint=signer_fingerprint(),
        receipt_sha256=_receipt_commitment(
            payload=payload,
            signature_b64=signature,
            public_key_b64_value=public_key,
        ),
    )


def verify_cms_decision_receipt(
    receipt: CMSDecisionReceipt,
    *,
    expected_signer_fingerprint: str | None = None,
) -> bool:
    """Verify commitment, pinned signer identity and Ed25519 signature."""

    try:
        public_key = base64.b64decode(receipt.public_key_b64, validate=True)
    except ValueError:
        return False
    if hashlib.sha256(public_key).hexdigest() != receipt.signer_fingerprint:
        return False
    trusted_fingerprint = expected_signer_fingerprint or signer_fingerprint()
    if receipt.signer_fingerprint != trusted_fingerprint:
        return False
    expected = _receipt_commitment(
        payload=receipt.payload,
        signature_b64=receipt.signature_b64,
        public_key_b64_value=receipt.public_key_b64,
    )
    return expected == receipt.receipt_sha256 and verify_payload(
        _payload_json(receipt.payload),
        receipt.signature_b64,
        receipt.public_key_b64,
    )
