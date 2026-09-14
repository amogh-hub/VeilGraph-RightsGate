"""Durable, lease-based idempotency storage for RightsGate execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from app.core.database import Database

from .contracts import RightsGateAssessment, RightsGateAssessmentRequest


class ReservationState(str, Enum):
    ACQUIRED = "ACQUIRED"
    REPLAY = "REPLAY"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"


class IdempotencyConflict(ValueError):
    """Raised when one key is reused for different execution inputs."""


class StoredAssessmentIntegrityError(RuntimeError):
    """Raised when persisted result bytes no longer match their commitment."""


@dataclass(frozen=True)
class AssessmentReservation:
    state: ReservationState
    idempotency_key: str
    request_sha256: str
    execution_sha256: str
    attempt_count: int
    lease_expires_at: str
    assessment: RightsGateAssessment | None = None
    assessment_sha256: str | None = None
    failure_code: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _canonical_request_json(request: RightsGateAssessmentRequest) -> str:
    return json.dumps(
        request.model_dump(mode="json", by_alias=True, exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )


def _validated_assessment(stored: dict[str, object]) -> RightsGateAssessment:
    try:
        raw = stored["assessment_json"]
        if not isinstance(raw, str):
            raise ValueError("assessment JSON is absent")
        assessment = RightsGateAssessment.model_validate_json(raw)
        if (
            assessment.assessment_id != stored["assessment_id"]
            or assessment.commitment_sha256() != stored["assessment_sha256"]
        ):
            raise ValueError("assessment identity or commitment differs")
    except Exception as error:
        raise StoredAssessmentIntegrityError(
            "stored assessment does not match its persisted commitment"
        ) from error
    return assessment


def _validate_stored_request(stored: dict[str, object]) -> None:
    try:
        raw = stored["request_json"]
        if not isinstance(raw, str):
            raise ValueError("request JSON is absent")
        request = RightsGateAssessmentRequest.model_validate_json(raw)
        if (
            request.idempotency_key != stored["idempotency_key"]
            or request.request_sha256() != stored["request_sha256"]
        ):
            raise ValueError("request identity or commitment differs")
    except Exception as error:
        raise StoredAssessmentIntegrityError(
            "stored request does not match its persisted commitment"
        ) from error


class RightsGateAssessmentStore:
    """Atomically reserve, complete and replay synchronous assessments.

    A bounded lease permits recovery after a process crash. Completed results are
    immutable: a reused key with different execution inputs is always rejected.
    """

    def __init__(self, database: Database, *, lease_seconds: int = 600):
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self.database = database
        self.lease_seconds = lease_seconds

    def reserve(
        self,
        *,
        request: RightsGateAssessmentRequest,
        execution_sha256: str,
    ) -> AssessmentReservation:
        request_sha256 = request.request_sha256()
        now = _utc_now()
        now_iso = _iso(now)
        lease_expires_at = _iso(now + timedelta(seconds=self.lease_seconds))
        request_json = _canonical_request_json(request)

        with self.database.connection() as connection:
            # Serialize reservations across processes, not only threads in this
            # Python interpreter. The transaction is intentionally short.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM rightsgate_assessments WHERE idempotency_key=?",
                (request.idempotency_key,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO rightsgate_assessments
                    (idempotency_key,request_sha256,execution_sha256,status,attempt_count,
                     lease_expires_at,request_json,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        request.idempotency_key,
                        request_sha256,
                        execution_sha256,
                        "PENDING",
                        1,
                        lease_expires_at,
                        request_json,
                        now_iso,
                        now_iso,
                    ),
                )
                return AssessmentReservation(
                    state=ReservationState.ACQUIRED,
                    idempotency_key=request.idempotency_key,
                    request_sha256=request_sha256,
                    execution_sha256=execution_sha256,
                    attempt_count=1,
                    lease_expires_at=lease_expires_at,
                )

            stored = dict(row)
            _validate_stored_request(stored)
            if (
                stored["request_sha256"] != request_sha256
                or stored["execution_sha256"] != execution_sha256
            ):
                raise IdempotencyConflict(
                    "idempotency key is already bound to different assessment inputs"
                )

            if stored["status"] == "COMPLETE":
                assessment = _validated_assessment(stored)
                return AssessmentReservation(
                    state=ReservationState.REPLAY,
                    idempotency_key=request.idempotency_key,
                    request_sha256=request_sha256,
                    execution_sha256=execution_sha256,
                    attempt_count=int(stored["attempt_count"]),
                    lease_expires_at=stored["lease_expires_at"],
                    assessment=assessment,
                    assessment_sha256=stored["assessment_sha256"],
                )

            if stored["status"] == "FAILED":
                return AssessmentReservation(
                    state=ReservationState.FAILED,
                    idempotency_key=request.idempotency_key,
                    request_sha256=request_sha256,
                    execution_sha256=execution_sha256,
                    attempt_count=int(stored["attempt_count"]),
                    lease_expires_at=stored["lease_expires_at"],
                    failure_code=stored["failure_code"],
                )

            lease_deadline = datetime.fromisoformat(stored["lease_expires_at"])
            if lease_deadline > now:
                return AssessmentReservation(
                    state=ReservationState.IN_PROGRESS,
                    idempotency_key=request.idempotency_key,
                    request_sha256=request_sha256,
                    execution_sha256=execution_sha256,
                    attempt_count=int(stored["attempt_count"]),
                    lease_expires_at=stored["lease_expires_at"],
                )

            attempt_count = int(stored["attempt_count"]) + 1
            connection.execute(
                """UPDATE rightsgate_assessments
                SET attempt_count=?,lease_expires_at=?,updated_at=?
                WHERE idempotency_key=? AND status='PENDING'""",
                (attempt_count, lease_expires_at, now_iso, request.idempotency_key),
            )
            return AssessmentReservation(
                state=ReservationState.ACQUIRED,
                idempotency_key=request.idempotency_key,
                request_sha256=request_sha256,
                execution_sha256=execution_sha256,
                attempt_count=attempt_count,
                lease_expires_at=lease_expires_at,
            )

    def complete(
        self,
        *,
        idempotency_key: str,
        execution_sha256: str,
        attempt_count: int,
        assessment: RightsGateAssessment,
    ) -> str:
        assessment_sha256 = assessment.commitment_sha256()
        assessment_json = assessment.model_dump_json(by_alias=True, exclude_none=True)
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE rightsgate_assessments
                SET status='COMPLETE',assessment_id=?,assessment_json=?,assessment_sha256=?,
                    failure_code=NULL,updated_at=?
                WHERE idempotency_key=? AND execution_sha256=? AND attempt_count=?
                    AND status='PENDING'""",
                (
                    assessment.assessment_id,
                    assessment_json,
                    assessment_sha256,
                    _iso(_utc_now()),
                    idempotency_key,
                    execution_sha256,
                    attempt_count,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("assessment reservation is no longer active")
        return assessment_sha256

    def fail(
        self,
        *,
        idempotency_key: str,
        execution_sha256: str,
        attempt_count: int,
        failure_code: str,
    ) -> bool:
        if not failure_code or len(failure_code) > 100:
            raise ValueError("failure_code must be a bounded non-empty value")
        with self.database.connection() as connection:
            cursor = connection.execute(
                """UPDATE rightsgate_assessments
                SET status='FAILED',failure_code=?,updated_at=?
                WHERE idempotency_key=? AND execution_sha256=? AND attempt_count=?
                    AND status='PENDING'""",
                (
                    failure_code,
                    _iso(_utc_now()),
                    idempotency_key,
                    execution_sha256,
                    attempt_count,
                ),
            )
        return cursor.rowcount == 1

    def get(self, idempotency_key: str) -> AssessmentReservation | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM rightsgate_assessments WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        stored = dict(row)
        _validate_stored_request(stored)
        assessment = _validated_assessment(stored) if stored["status"] == "COMPLETE" else None
        state = {
            "PENDING": ReservationState.IN_PROGRESS,
            "COMPLETE": ReservationState.REPLAY,
            "FAILED": ReservationState.FAILED,
        }[stored["status"]]
        return AssessmentReservation(
            state=state,
            idempotency_key=stored["idempotency_key"],
            request_sha256=stored["request_sha256"],
            execution_sha256=stored["execution_sha256"],
            attempt_count=int(stored["attempt_count"]),
            lease_expires_at=stored["lease_expires_at"],
            assessment=assessment,
            assessment_sha256=stored["assessment_sha256"],
            failure_code=stored["failure_code"],
        )
