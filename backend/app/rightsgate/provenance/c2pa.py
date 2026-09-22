"""Offline C2PA verification mapped into RightsGate evidence contracts."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any

import c2pa

from ..contracts import (
    AssessmentState,
    ClaimDimension,
    ClaimOutcome,
    ClaimRecord,
    ComponentRecord,
    ComponentState,
    EvidenceKind,
    EvidenceLocator,
    EvidencePointer,
    EvidencePolarity,
    LocatorKind,
    ProvenanceAssessment,
    ProvenanceVerdict,
    StrictFrozenModel,
)

COMPONENT_ID = "provenance.c2pa"
COMPONENT_TYPE = "provenance.credential-verifier"
TRAINED_ALGORITHMIC_MEDIA = "trainedAlgorithmicMedia"
COMPOSITE_GENERATIVE_MEDIA = {
    "compositeWithTrainedAlgorithmicMedia",
    "compositeSynthetic",
}
TAMPER_FAILURE_TOKENS = (
    "hash.mismatch",
    "hasheduri.mismatch",
    "signature.mismatch",
    "timestamp.mismatch",
)


class C2PAVerificationResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    assessment: ProvenanceAssessment


@dataclass(frozen=True)
class _ManifestObservation:
    validation_state: str | None
    validation_results: dict[str, Any] | None
    active_manifest: dict[str, Any]
    report: dict[str, Any]


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_manifest(data: bytes, media_type: str) -> _ManifestObservation | None:
    """Read and validate embedded credentials without network retrieval."""

    settings = c2pa.Settings.from_dict({"verify": {"remote_manifest_fetch": False}})
    with c2pa.Context(settings) as context:
        reader = c2pa.Reader.try_create(media_type, io.BytesIO(data), context=context)
        if reader is None:
            return None
        with reader:
            report = json.loads(reader.json())
            active_manifest = reader.get_active_manifest()
            if not isinstance(active_manifest, dict):
                raise c2pa.C2paError.Manifest("active manifest is missing or malformed")
            validation_results = reader.get_validation_results()
            return _ManifestObservation(
                validation_state=reader.get_validation_state(),
                validation_results=(
                    validation_results if isinstance(validation_results, dict) else None
                ),
                active_manifest=active_manifest,
                report=report,
            )


def _active_actions(active_manifest: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    actions: list[dict[str, Any]] = []
    assertions = active_manifest.get("assertions")
    if not isinstance(assertions, list):
        return ()
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        data = assertion.get("data")
        if not isinstance(data, dict):
            continue
        candidates = data.get("actions")
        if not isinstance(candidates, list):
            continue
        actions.extend(item for item in candidates if isinstance(item, dict))
    return tuple(actions)


def _digital_source_types(active_manifest: dict[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()
    for action in _active_actions(active_manifest):
        value = action.get("digitalSourceType")
        if isinstance(value, str) and value:
            values.add(value.rsplit("/", 1)[-1])
    return tuple(sorted(values))


def _status_codes(results: dict[str, Any] | None, category: str) -> tuple[str, ...]:
    if results is None:
        return ()
    values: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            statuses = value.get(category)
            if isinstance(statuses, list):
                for status in statuses:
                    if isinstance(status, dict) and isinstance(status.get("code"), str):
                        values.add(status["code"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(results)
    return tuple(sorted(values))


def _component(state: ComponentState, reason: str | None = None) -> ComponentRecord:
    return ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=c2pa.__version__,
        component_type=COMPONENT_TYPE,
        state=state,
        reason=reason,
    )


def _unknown_without_manifest(asset_sha256: str) -> C2PAVerificationResult:
    limitation = (
        "No embedded C2PA manifest was found; absence is not evidence of human authorship."
    )
    claim = ClaimRecord(
        claim_id=f"claim.c2pa-presence-{asset_sha256[:16]}",
        dimension=ClaimDimension.PROVENANCE,
        claim_type="credential.present",
        statement="The asset contains an embedded C2PA manifest.",
        outcome=ClaimOutcome.UNKNOWN,
        confidence=0,
        mandatory=False,
        limitations=(limitation,),
    )
    return C2PAVerificationResult(
        component=_component(ComponentState.AVAILABLE),
        evidence=(),
        assessment=ProvenanceAssessment(
            state=AssessmentState.COMPLETE,
            verdict=ProvenanceVerdict.UNKNOWN,
            confidence=0,
            claims=(claim,),
            limitations=(limitation,),
        ),
    )


def _safe_failure(asset_sha256: str, error: c2pa.C2paError) -> C2PAVerificationResult:
    reason = "The C2PA SDK could not safely parse or verify this asset."
    error_category = str(error).split(":", 1)[0][:100]
    evidence = EvidencePointer(
        evidence_id=f"evidence.c2pa-failure-{asset_sha256[:16]}",
        asset_sha256=asset_sha256,
        kind=EvidenceKind.COMPONENT_FAILURE,
        source="Content Authenticity Initiative c2pa-python SDK",
        component_id=COMPONENT_ID,
        component_version=c2pa.__version__,
        polarity=EvidencePolarity.NEUTRAL,
        confidence=1,
        locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
        summary=reason,
        payload_sha256=hashlib.sha256(str(error).encode("utf-8")).hexdigest(),
        attributes={"error_category": error_category},
    )
    claim = ClaimRecord(
        claim_id=f"claim.c2pa-integrity-{asset_sha256[:16]}",
        dimension=ClaimDimension.PROVENANCE,
        claim_type="credential.integrity",
        statement="The embedded C2PA manifest validates for the assessed asset bytes.",
        outcome=ClaimOutcome.NOT_ASSESSED,
        confidence=0,
        mandatory=False,
        limitations=(reason,),
    )
    return C2PAVerificationResult(
        component=_component(ComponentState.DEGRADED, reason),
        evidence=(evidence,),
        assessment=ProvenanceAssessment(
            state=AssessmentState.UNAVAILABLE,
            verdict=ProvenanceVerdict.UNKNOWN,
            confidence=0,
            claims=(claim,),
            limitations=(reason,),
        ),
    )


def _map_observation(
    observation: _ManifestObservation,
    asset_sha256: str,
) -> C2PAVerificationResult:
    validation_state = observation.validation_state or "Unknown"
    normalized_state = validation_state.casefold()
    sources = _digital_source_types(observation.active_manifest)
    failures = _status_codes(observation.validation_results, "failure")
    report_sha256 = _canonical_hash(observation.report)
    evidence_id = f"evidence.c2pa-{asset_sha256[:16]}"

    if normalized_state == "invalid":
        tamper_signal = any(
            token in code.casefold()
            for code in failures
            for token in TAMPER_FAILURE_TOKENS
        )
        verdict = ProvenanceVerdict.TAMPERED if tamper_signal else ProvenanceVerdict.UNKNOWN
        outcome = ClaimOutcome.CONTRADICTED
        polarity = EvidencePolarity.CONTRADICTS
        confidence = 1.0
        summary = "The embedded Content Credential failed C2PA validation."
        limitations = (
            (
                "A cryptographic mismatch is evidence of credential or asset tampering; inspect the status codes."
                if tamper_signal
                else "The credential is invalid, but the available status codes do not establish tampering."
            ),
        )
    elif normalized_state in {"valid", "trusted"}:
        outcome = ClaimOutcome.SUPPORTED
        polarity = EvidencePolarity.SUPPORTS
        confidence = 1.0 if normalized_state == "trusted" else 0.95
        summary = f"The embedded Content Credential is {validation_state}."
        limitations = ()
        if any("signingcredential.untrusted" in code.casefold() for code in failures):
            limitations = (
                "The signing credential is untrusted; structural validation does not authenticate the publisher.",
            )
        if any(source in COMPOSITE_GENERATIVE_MEDIA for source in sources):
            verdict = ProvenanceVerdict.PARTIALLY_GENERATED
        elif TRAINED_ALGORITHMIC_MEDIA in sources:
            verdict = ProvenanceVerdict.AI_GENERATED
        else:
            verdict = ProvenanceVerdict.UNKNOWN
            limitations += (
                "The credential validates but does not declare a recognized generative-AI source type.",
            )
    else:
        verdict = ProvenanceVerdict.UNKNOWN
        outcome = ClaimOutcome.UNKNOWN
        polarity = EvidencePolarity.NEUTRAL
        confidence = 0
        summary = f"The embedded Content Credential reported validation state {validation_state}."
        limitations = ("The C2PA validation state is not sufficient for a provenance conclusion.",)

    evidence = EvidencePointer(
        evidence_id=evidence_id,
        asset_sha256=asset_sha256,
        kind=EvidenceKind.CONTENT_CREDENTIAL,
        source="Content Authenticity Initiative c2pa-python SDK",
        component_id=COMPONENT_ID,
        component_version=c2pa.__version__,
        polarity=polarity,
        confidence=confidence,
        locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
        summary=summary,
        payload_sha256=report_sha256,
        attributes={
            "validation_state": validation_state,
            "failure_codes": ",".join(failures),
            "digital_source_types": ",".join(sources),
        },
    )
    claims = [
        ClaimRecord(
            claim_id=f"claim.c2pa-integrity-{asset_sha256[:16]}",
            dimension=ClaimDimension.PROVENANCE,
            claim_type="credential.integrity",
            statement="The embedded C2PA manifest validates for the assessed asset bytes.",
            outcome=outcome,
            confidence=confidence,
            mandatory=False,
            evidence_ids=(evidence_id,) if outcome != ClaimOutcome.UNKNOWN else (),
            limitations=limitations,
        )
    ]
    if verdict in {
        ProvenanceVerdict.AI_GENERATED,
        ProvenanceVerdict.PARTIALLY_GENERATED,
    }:
        claims.append(
            ClaimRecord(
                claim_id=f"claim.c2pa-ai-source-{asset_sha256[:16]}",
                dimension=ClaimDimension.PROVENANCE,
                claim_type="credential.ai-source-declaration",
                statement="The active C2PA manifest declares a recognized generative-AI source type.",
                outcome=ClaimOutcome.SUPPORTED,
                confidence=confidence,
                mandatory=False,
                evidence_ids=(evidence_id,),
            )
        )

    return C2PAVerificationResult(
        component=_component(ComponentState.AVAILABLE),
        evidence=(evidence,),
        assessment=ProvenanceAssessment(
            state=AssessmentState.COMPLETE,
            verdict=verdict,
            confidence=confidence,
            claims=tuple(claims),
            limitations=limitations,
        ),
    )


def verify_c2pa(data: bytes, media_type: str, asset_sha256: str) -> C2PAVerificationResult:
    """Verify embedded C2PA data locally and return bounded evidence.

    The result reports what the credential declares and whether its cryptographic
    structure validates. It does not treat a missing credential as proof of
    human authorship or a valid credential as a legal rights determination.
    """

    try:
        observation = _read_manifest(data, media_type)
    except c2pa.C2paError as error:
        return _safe_failure(asset_sha256, error)
    if observation is None:
        return _unknown_without_manifest(asset_sha256)
    return _map_observation(observation, asset_sha256)
