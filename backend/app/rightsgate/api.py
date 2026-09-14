"""Public RightsGate contract, adapter and trusted execution endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypeVar

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError as PydanticValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import db
from app.core.enums import FileType
from app.ingestion.validator import (
    ValidationError as UploadValidationError,
    sanitize_filename,
    validate_upload,
)

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
from .execution import (
    ExecutionInputError,
    execute_rightsgate_assessment,
    execution_fingerprint,
    validate_execution_asset,
    validate_governed_inputs,
)
from .policy import POLICY_SCHEMA, PublicationPolicy
from .provenance import C2PAVerificationResult, verify_c2pa
from .rights import (
    LicenceRegistry,
    ReferenceKind,
    RegistryImage,
    RightsReferenceRegistry,
    build_registry_image,
)
from .rights.image_registry import REGISTRY_SCHEMA
from .rights.licensing import LICENCE_REGISTRY_SCHEMA
from .store import (
    IdempotencyConflict,
    ReservationState,
    RightsGateAssessmentStore,
    StoredAssessmentIntegrityError,
)

router = APIRouter(prefix="/api/v1/rightsgate", tags=["RightsGate"])
assessment_store = RightsGateAssessmentStore(
    db,
    lease_seconds=settings.rightsgate_execution_lease_seconds,
)
ModelT = TypeVar("ModelT", bound=StrictFrozenModel)


class ContractBundleResponse(StrictFrozenModel):
    bundle_schema: Literal["veilgraph.rightsgate.contract-bundle.v1"] = (
        "veilgraph.rightsgate.contract-bundle.v1"
    )
    contract_status: Literal["IMPLEMENTED"] = "IMPLEMENTED"
    execution_status: Literal["IMPLEMENTED"] = "IMPLEMENTED"
    detector_status: Literal["PARTIAL"] = "PARTIAL"
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


class AssessmentExecutionResponse(StrictFrozenModel):
    receipt_schema: Literal["veilgraph.rightsgate.execution-receipt.v1"] = (
        "veilgraph.rightsgate.execution-receipt.v1"
    )
    idempotency_key: str
    request_sha256: str
    execution_sha256: str
    assessment_sha256: str
    replayed: bool
    release_authorization: Literal[False] = False
    assessment: RightsGateAssessment


class AssessmentRecordResponse(StrictFrozenModel):
    record_schema: Literal["veilgraph.rightsgate.execution-record.v1"] = (
        "veilgraph.rightsgate.execution-record.v1"
    )
    idempotency_key: str
    request_sha256: str
    execution_sha256: str
    status: Literal["PENDING", "COMPLETE", "FAILED"]
    attempt_count: int
    lease_expires_at: str
    assessment_sha256: str | None = None
    failure_code: str | None = None
    release_authorization: Literal[False] = False
    assessment: RightsGateAssessment | None = None


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
            LICENCE_REGISTRY_SCHEMA: LicenceRegistry.model_json_schema(by_alias=True),
            POLICY_SCHEMA: PublicationPolicy.model_json_schema(by_alias=True),
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
    return await run_in_threadpool(verify_c2pa, data, media_type, asset_sha256)


@router.post("/rights/references/image", response_model=RegistryImage)
async def derive_image_reference(
    file: UploadFile = File(...),
    reference_id: str = Form(...),
    kind: ReferenceKind = Form(...),
    title: str = Form(...),
    rights_holder: str = Form(...),
    source_record_id: str = Form(...),
) -> RegistryImage:
    """Derive a byte-bound governed reference record using the server adapter."""

    try:
        data = await file.read(settings.max_file_size_bytes + 1)
    finally:
        await file.close()
    filename = sanitize_filename(file.filename or "reference")
    try:
        file_type, media_type, _ = validate_upload(data, filename)
    except UploadValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if file_type != FileType.IMAGE:
        raise HTTPException(status_code=400, detail="reference must be a PNG or JPEG image")
    try:
        return await run_in_threadpool(
            build_registry_image,
            reference_id=reference_id,
            kind=kind,
            title=title,
            rights_holder=rights_holder,
            data=data,
            media_type=media_type,
            source_record_id=source_record_id,
            max_pixels=settings.max_image_pixels,
        )
    except (ValueError, PydanticValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _parse_control_json(raw: str, model: type[ModelT], field_name: str) -> ModelT:
    if len(raw.encode("utf-8")) > settings.rightsgate_max_control_json_bytes:
        raise HTTPException(status_code=413, detail=f"{field_name} exceeds the control JSON limit")
    try:
        return model.model_validate_json(raw)
    except PydanticValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "field": field_name,
                "errors": error.errors(include_url=False, include_input=False),
            },
        ) from error


def _execution_response(
    *,
    idempotency_key: str,
    request_sha256: str,
    execution_sha256: str,
    assessment_sha256: str,
    replayed: bool,
    assessment: RightsGateAssessment,
) -> AssessmentExecutionResponse:
    return AssessmentExecutionResponse(
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
        execution_sha256=execution_sha256,
        assessment_sha256=assessment_sha256,
        replayed=replayed,
        assessment=assessment,
    )


@router.post("/assessments", response_model=AssessmentExecutionResponse)
async def execute_assessment(
    file: UploadFile = File(...),
    request_json: str = Form(...),
    rights_registry_json: str = Form(...),
    licence_registry_json: str = Form(...),
    policy_json: str = Form(...),
    max_hamming_distance: int = Form(6),
) -> AssessmentExecutionResponse:
    """Run the implemented lanes under durable idempotency and fail-closed policy."""

    if not 0 <= max_hamming_distance <= 64:
        raise HTTPException(status_code=422, detail="max_hamming_distance must be between 0 and 64")
    request = _parse_control_json(request_json, RightsGateAssessmentRequest, "request_json")
    rights_registry = _parse_control_json(
        rights_registry_json,
        RightsReferenceRegistry,
        "rights_registry_json",
    )
    licence_registry = _parse_control_json(
        licence_registry_json,
        LicenceRegistry,
        "licence_registry_json",
    )
    policy = _parse_control_json(policy_json, PublicationPolicy, "policy_json")
    try:
        validate_governed_inputs(
            request=request,
            rights_registry=rights_registry,
            licence_registry=licence_registry,
            policy=policy,
        )
    except ExecutionInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        data = await file.read(settings.max_file_size_bytes + 1)
    finally:
        await file.close()
    try:
        validate_execution_asset(data, request)
    except ExecutionInputError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    execution_sha256 = execution_fingerprint(
        request,
        rights_registry=rights_registry,
        licence_registry=licence_registry,
        policy=policy,
        max_hamming_distance=max_hamming_distance,
    )
    try:
        reservation = assessment_store.reserve(
            request=request,
            execution_sha256=execution_sha256,
        )
    except IdempotencyConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except StoredAssessmentIntegrityError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    if reservation.state == ReservationState.REPLAY:
        if reservation.assessment is None or reservation.assessment_sha256 is None:
            raise HTTPException(status_code=500, detail="stored assessment record is incomplete")
        return _execution_response(
            idempotency_key=reservation.idempotency_key,
            request_sha256=reservation.request_sha256,
            execution_sha256=reservation.execution_sha256,
            assessment_sha256=reservation.assessment_sha256,
            replayed=True,
            assessment=reservation.assessment,
        )
    if reservation.state == ReservationState.IN_PROGRESS:
        raise HTTPException(
            status_code=409,
            detail="an assessment with this idempotency key is already in progress",
            headers={"Retry-After": "1"},
        )
    if reservation.state == ReservationState.FAILED:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "the idempotent assessment previously failed",
                "failure_code": reservation.failure_code,
            },
        )

    try:
        assessment = await run_in_threadpool(
            execute_rightsgate_assessment,
            data,
            request=request,
            rights_registry=rights_registry,
            licence_registry=licence_registry,
            policy=policy,
            created_at=datetime.now(timezone.utc),
            max_hamming_distance=max_hamming_distance,
        )
        assessment_sha256 = assessment_store.complete(
            idempotency_key=request.idempotency_key,
            execution_sha256=execution_sha256,
            attempt_count=reservation.attempt_count,
            assessment=assessment,
        )
    except Exception:
        assessment_store.fail(
            idempotency_key=request.idempotency_key,
            execution_sha256=execution_sha256,
            attempt_count=reservation.attempt_count,
            failure_code="EXECUTION_FAILED",
        )
        raise HTTPException(
            status_code=500,
            detail="assessment failed closed; no release authorization was produced",
        ) from None

    return _execution_response(
        idempotency_key=request.idempotency_key,
        request_sha256=request.request_sha256(),
        execution_sha256=execution_sha256,
        assessment_sha256=assessment_sha256,
        replayed=False,
        assessment=assessment,
    )


@router.get("/assessments/{idempotency_key}", response_model=AssessmentRecordResponse)
def get_assessment_record(idempotency_key: str) -> AssessmentRecordResponse:
    """Retrieve durable status and a completed result without raw asset bytes."""

    if not idempotency_key or len(idempotency_key) > 128:
        raise HTTPException(status_code=422, detail="invalid idempotency key")
    try:
        record = assessment_store.get(idempotency_key)
    except StoredAssessmentIntegrityError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if record is None:
        raise HTTPException(status_code=404, detail="assessment record not found")
    status = {
        ReservationState.IN_PROGRESS: "PENDING",
        ReservationState.REPLAY: "COMPLETE",
        ReservationState.FAILED: "FAILED",
        ReservationState.ACQUIRED: "PENDING",
    }[record.state]
    return AssessmentRecordResponse(
        idempotency_key=record.idempotency_key,
        request_sha256=record.request_sha256,
        execution_sha256=record.execution_sha256,
        status=status,
        attempt_count=record.attempt_count,
        lease_expires_at=record.lease_expires_at,
        assessment_sha256=record.assessment_sha256,
        failure_code=record.failure_code,
        assessment=record.assessment,
    )
