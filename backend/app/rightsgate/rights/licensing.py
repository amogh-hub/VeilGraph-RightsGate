"""Deterministic licence, territory and intended-use evaluation for matched works."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..contracts import (
    AssessmentContext,
    ClaimDimension,
    ClaimOutcome,
    ClaimRecord,
    ComponentRecord,
    ComponentState,
    EvidenceKind,
    EvidenceLocator,
    EvidencePointer,
    EvidencePolarity,
    ID_PATTERN,
    LocatorKind,
    StrictFrozenModel,
)
from .image_registry import RightsImageMatchResult

LICENCE_REGISTRY_SCHEMA = "veilgraph.rightsgate.licence-registry.v1"
COMPONENT_ID = "rights.licence-evaluator"
COMPONENT_VERSION = "1.0.0"
COMPONENT_TYPE = "rights.licence-policy-evaluator"


class LicenceState(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class LicenceRecord(StrictFrozenModel):
    licence_id: str = Field(pattern=ID_PATTERN)
    source_record_id: str = Field(pattern=ID_PATTERN)
    reference_ids: tuple[str, ...] = Field(min_length=1)
    licensor: str = Field(min_length=1, max_length=300)
    licensee: str = Field(min_length=1, max_length=300)
    state: LicenceState = LicenceState.ACTIVE
    valid_from: datetime
    valid_until: datetime
    territories: tuple[str, ...] = Field(min_length=1)
    channels: tuple[str, ...] = Field(min_length=1)
    intended_uses: tuple[str, ...] = Field(min_length=1)

    @field_validator("reference_ids")
    @classmethod
    def normalize_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("reference_ids must be unique")
        return tuple(sorted(values))

    @field_validator("territories")
    @classmethod
    def normalize_territories(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.upper() for value in values}))
        if any(value != "*" and (len(value) != 2 or not value.isalpha()) for value in normalized):
            raise ValueError("territories must contain '*' or ISO 3166-1 alpha-2-like codes")
        return normalized

    @field_validator("channels", "intended_uses")
    @classmethod
    def normalize_casefolded_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.strip().casefold() for value in values if value.strip()}))
        if not normalized:
            raise ValueError("licence value sets cannot be empty")
        return normalized

    @field_validator("valid_from", "valid_until")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("licence timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> LicenceRecord:
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be later than valid_from")
        return self


class LicenceRegistry(StrictFrozenModel):
    schema_id: Literal[LICENCE_REGISTRY_SCHEMA] = Field(
        default=LICENCE_REGISTRY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    registry_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=100)
    licences: tuple[LicenceRecord, ...] = ()

    @model_validator(mode="after")
    def require_unique_licences(self) -> LicenceRegistry:
        licence_ids = [item.licence_id for item in self.licences]
        if len(licence_ids) != len(set(licence_ids)):
            raise ValueError("licence_id values must be unique")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True)
        payload["licences"] = sorted(payload["licences"], key=lambda item: item["licence_id"])
        return payload

    def commitment_sha256(self) -> str:
        return _canonical_hash(self.canonical_payload())


class LicenceEvaluationResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    claims: tuple[ClaimRecord, ...]
    candidate_reference_ids: tuple[str, ...]
    covered_reference_ids: tuple[str, ...]
    uncovered_reference_ids: tuple[str, ...]
    policy_conflict: bool
    limitations: tuple[str, ...] = ()


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _component(registry_sha256: str) -> ComponentRecord:
    return ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        component_type=COMPONENT_TYPE,
        state=ComponentState.AVAILABLE,
        artifact_sha256=registry_sha256,
    )


def _candidate_reference_ids(
    match: RightsImageMatchResult,
    additional_evidence: tuple[EvidencePointer, ...],
) -> tuple[str, ...]:
    values = {
        str(item.attributes["reference_id"])
        for item in match.evidence + additional_evidence
        if item.kind == EvidenceKind.REFERENCE_MATCH
        and item.polarity == EvidencePolarity.SUPPORTS
        and item.attributes.get("reference_id")
    }
    return tuple(sorted(values))


def _coverage_failures(
    licence: LicenceRecord,
    *,
    context: AssessmentContext,
    assessed_at: datetime,
) -> tuple[str, ...]:
    failures: list[str] = []
    if licence.state != LicenceState.ACTIVE:
        failures.append(f"state:{licence.state.value}")
    if assessed_at < licence.valid_from:
        failures.append("not-yet-valid")
    if assessed_at > licence.valid_until:
        failures.append("expired")
    if "*" not in licence.territories and not set(context.territories).issubset(
        licence.territories
    ):
        failures.append("territory-not-covered")
    if "*" not in licence.channels and context.channel.casefold() not in licence.channels:
        failures.append("channel-not-covered")
    intended_use = context.intended_use.strip().casefold()
    if "*" not in licence.intended_uses and intended_use not in licence.intended_uses:
        failures.append("intended-use-not-covered")
    return tuple(failures)


def evaluate_candidate_licences(
    match: RightsImageMatchResult,
    *,
    asset_sha256: str,
    context: AssessmentContext,
    registry: LicenceRegistry,
    assessed_at: datetime,
    additional_evidence: tuple[EvidencePointer, ...] = (),
) -> LicenceEvaluationResult:
    """Evaluate explicit licences for retrieved candidates without implying legal advice."""

    if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
        raise ValueError("assessed_at must be timezone-aware")
    registry_sha256 = registry.commitment_sha256()
    candidates = _candidate_reference_ids(match, additional_evidence)
    if not candidates:
        limitation = "No governed reference candidate was available for licence evaluation."
        return LicenceEvaluationResult(
            component=_component(registry_sha256),
            evidence=(),
            claims=(
                ClaimRecord(
                    claim_id=f"claim.licence-not-assessed-{asset_sha256[:16]}",
                    dimension=ClaimDimension.RIGHTS_EXPOSURE,
                    claim_type="licence.candidate-coverage",
                    statement=(
                        "Retrieved reference candidates are covered for the declared "
                        "deployment context."
                    ),
                    outcome=ClaimOutcome.NOT_ASSESSED,
                    confidence=0,
                    mandatory=False,
                    limitations=(limitation,),
                ),
            ),
            candidate_reference_ids=(),
            covered_reference_ids=(),
            uncovered_reference_ids=(),
            policy_conflict=False,
            limitations=(limitation,),
        )

    evidence: list[EvidencePointer] = []
    claims: list[ClaimRecord] = []
    covered: list[str] = []
    uncovered: list[str] = []

    for reference_id in candidates:
        applicable = tuple(
            licence for licence in registry.licences if reference_id in licence.reference_ids
        )
        evaluations = tuple(
            (licence, _coverage_failures(licence, context=context, assessed_at=assessed_at))
            for licence in applicable
        )
        covering = tuple(licence for licence, failures in evaluations if not failures)
        is_covered = bool(covering)
        (covered if is_covered else uncovered).append(reference_id)

        reference_token = hashlib.sha256(reference_id.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"evidence.licence-{reference_token}-{asset_sha256[:16]}"
        evaluation_payload = {
            "assessed_at": assessed_at.isoformat(),
            "asset_sha256": asset_sha256,
            "context": context.model_dump(mode="json"),
            "covering_licence_ids": sorted(item.licence_id for item in covering),
            "evaluations": [
                {"licence_id": item.licence_id, "failures": list(failures)}
                for item, failures in evaluations
            ],
            "reference_id": reference_id,
            "registry_sha256": registry_sha256,
        }
        evidence.append(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.LICENCE_RECORD,
                source="Governed local licence registry",
                component_id=COMPONENT_ID,
                component_version=COMPONENT_VERSION,
                polarity=(
                    EvidencePolarity.SUPPORTS if is_covered else EvidencePolarity.CONTRADICTS
                ),
                confidence=1,
                locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                summary=(
                    "A current governed licence covers this candidate for the declared context."
                    if is_covered
                    else "No current governed licence covers this candidate for the "
                    "declared context."
                ),
                payload_sha256=_canonical_hash(evaluation_payload),
                attributes={
                    "covered": is_covered,
                    "covering_licence_ids": ",".join(
                        sorted(item.licence_id for item in covering)
                    ),
                    "covering_source_record_ids": ",".join(
                        sorted(item.source_record_id for item in covering)
                    ),
                    "covering_licence_count": len(covering),
                    "evaluated_licence_count": len(applicable),
                    "reference_id": reference_id,
                    "registry_id": registry.registry_id,
                    "registry_version": registry.version,
                },
            )
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim.licence-{reference_token}-{asset_sha256[:16]}",
                dimension=ClaimDimension.RIGHTS_EXPOSURE,
                claim_type="licence.candidate-coverage",
                statement=(
                    f"Governed reference {reference_id} is covered for the declared "
                    "deployment context."
                ),
                outcome=ClaimOutcome.SUPPORTED if is_covered else ClaimOutcome.CONTRADICTED,
                confidence=1,
                mandatory=True,
                evidence_ids=(evidence_id,),
                limitations=(
                    "This is deterministic registry evaluation, not a legal opinion "
                    "or proof of ownership.",
                ),
            )
        )

    limitations = (
        "Licence coverage is limited to explicit records in the supplied governed registry.",
        "Licence evaluation does not replace qualified legal or rights review.",
    )
    return LicenceEvaluationResult(
        component=_component(registry_sha256),
        evidence=tuple(evidence),
        claims=tuple(claims),
        candidate_reference_ids=candidates,
        covered_reference_ids=tuple(sorted(covered)),
        uncovered_reference_ids=tuple(sorted(uncovered)),
        policy_conflict=bool(uncovered),
        limitations=limitations,
    )
