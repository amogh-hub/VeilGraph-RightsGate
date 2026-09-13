"""Public, detector-independent RightsGate contract endpoints.

These endpoints expose and validate versioned envelopes only. They do not claim
that provenance or rights detectors are available and never authorize release.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter

from .contracts import (
    ASSESSMENT_REQUEST_SCHEMA,
    ASSESSMENT_SCHEMA,
    ASSET_IR_SCHEMA,
    EXPOSURE_GRAPH_SCHEMA,
    AssetExposureGraph,
    AssetIR,
    DeploymentDecision,
    RightsGateAssessment,
    RightsGateAssessmentRequest,
    StrictFrozenModel,
)

router = APIRouter(prefix="/api/v1/rightsgate", tags=["RightsGate contracts"])


class ContractBundleResponse(StrictFrozenModel):
    bundle_schema: Literal["veilgraph.rightsgate.contract-bundle.v1"] = (
        "veilgraph.rightsgate.contract-bundle.v1"
    )
    contract_status: Literal["IMPLEMENTED"] = "IMPLEMENTED"
    detector_status: Literal["NOT_INCLUDED"] = "NOT_INCLUDED"
    schemas: dict[str, dict[str, Any]]


class RequestValidationReceipt(StrictFrozenModel):
    receipt_schema: Literal["veilgraph.rightsgate.request-validation.v1"] = (
        "veilgraph.rightsgate.request-validation.v1"
    )
    accepted_schema: Literal[ASSESSMENT_REQUEST_SCHEMA] = ASSESSMENT_REQUEST_SCHEMA
    idempotency_key: str
    request_sha256: str
    assessment_started: Literal[False] = False


class AssessmentValidationReceipt(StrictFrozenModel):
    receipt_schema: Literal["veilgraph.rightsgate.assessment-validation.v1"] = (
        "veilgraph.rightsgate.assessment-validation.v1"
    )
    accepted_schema: Literal[ASSESSMENT_SCHEMA] = ASSESSMENT_SCHEMA
    assessment_id: str
    assessment_sha256: str
    deployment_decision: DeploymentDecision
    release_authorization: Literal[False] = False


@router.get("/contracts", response_model=ContractBundleResponse)
def get_contracts() -> ContractBundleResponse:
    """Return canonical JSON Schemas for the implemented Gate 1 boundary."""

    return ContractBundleResponse(
        schemas={
            ASSET_IR_SCHEMA: AssetIR.model_json_schema(by_alias=True),
            ASSESSMENT_REQUEST_SCHEMA: RightsGateAssessmentRequest.model_json_schema(by_alias=True),
            EXPOSURE_GRAPH_SCHEMA: AssetExposureGraph.model_json_schema(by_alias=True),
            ASSESSMENT_SCHEMA: RightsGateAssessment.model_json_schema(by_alias=True),
        }
    )


@router.post("/requests/validate", response_model=RequestValidationReceipt)
def validate_request(payload: RightsGateAssessmentRequest) -> RequestValidationReceipt:
    """Validate and fingerprint an idempotent assessment request envelope."""

    return RequestValidationReceipt(
        idempotency_key=payload.idempotency_key,
        request_sha256=payload.request_sha256(),
    )


@router.post("/assessments/validate", response_model=AssessmentValidationReceipt)
def validate_assessment(payload: RightsGateAssessment) -> AssessmentValidationReceipt:
    """Validate an externally assembled result without granting release authority."""

    return AssessmentValidationReceipt(
        assessment_id=payload.assessment_id,
        assessment_sha256=payload.commitment_sha256(),
        deployment_decision=payload.deployment.decision,
    )
