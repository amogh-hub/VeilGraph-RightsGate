"""Public, detector-independent RightsGate contract endpoints.

These endpoints expose and validate versioned envelopes only. They do not claim
that provenance or rights detectors are available and never authorize release.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.ingestion.validator import (
    ValidationError as UploadValidationError,
    sanitize_filename,
    validate_upload,
)

from .provenance import C2PAVerificationResult, verify_c2pa
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
from .rights import RightsReferenceRegistry
from .rights.image_registry import REGISTRY_SCHEMA

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
            REGISTRY_SCHEMA: RightsReferenceRegistry.model_json_schema(by_alias=True),
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


@router.post("/provenance/c2pa", response_model=C2PAVerificationResult)
async def inspect_c2pa(file: UploadFile = File(...)) -> C2PAVerificationResult:
    """Run the bounded offline C2PA adapter without making a release decision."""

    try:
        data = await file.read(settings.max_file_size_bytes + 1)
    finally:
        await file.close()
    filename = sanitize_filename(file.filename or "asset")
    try:
        _, media_type, asset_sha256 = validate_upload(data, filename)
    except UploadValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return verify_c2pa(data, media_type, asset_sha256)
