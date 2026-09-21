"""Versioned deterministic deployment policy for RightsGate assessments."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .contracts import (
    AssessmentContext,
    AssessmentState,
    ClaimDimension,
    ClaimOutcome,
    ClaimRecord,
    ComponentRecord,
    ComponentState,
    DeploymentAssessment,
    DeploymentDecision,
    EvidenceKind,
    EvidenceLocator,
    EvidencePointer,
    EvidencePolarity,
    ID_PATTERN,
    LocatorKind,
    ProvenanceAssessment,
    ProvenanceVerdict,
    RightsAssessment,
    RightsVerdict,
    StrictFrozenModel,
)
from .rights.licensing import LicenceEvaluationResult

POLICY_SCHEMA = "veilgraph.rightsgate.publication-policy.v1"
COMPONENT_ID = "deployment.policy-compiler"
COMPONENT_VERSION = "1.1.0"
COMPONENT_TYPE = "deployment.deterministic-policy"


class RegulatoryRuleEffect(str, Enum):
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class RegulatoryRule(StrictFrozenModel):
    """A deterministic context/verdict rule supplied by a governed policy owner."""

    rule_id: str = Field(pattern=ID_PATTERN)
    description: str = Field(min_length=1, max_length=500)
    effect: RegulatoryRuleEffect
    territories: tuple[str, ...] = ("*",)
    channels: tuple[str, ...] = ("*",)
    audiences: tuple[str, ...] = ("*",)
    brand_profiles: tuple[str, ...] = ("*",)
    provenance_verdicts: tuple[ProvenanceVerdict, ...] = ()
    rights_verdicts: tuple[RightsVerdict, ...] = ()

    @field_validator("channels", "audiences", "brand_profiles")
    @classmethod
    def normalize_casefolded_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.strip().casefold() for value in values if value.strip()}))
        if not normalized:
            raise ValueError("regulatory rule value sets cannot be empty")
        return normalized

    @field_validator("territories")
    @classmethod
    def normalize_territories(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.strip().upper() for value in values if value.strip()}))
        if not normalized or any(
            value != "*" and (len(value) != 2 or not value.isalpha()) for value in normalized
        ):
            raise ValueError("regulatory rule territories must contain '*' or two-letter codes")
        return normalized

    @field_validator("provenance_verdicts", "rights_verdicts")
    @classmethod
    def normalize_verdicts(cls, values: tuple[Enum, ...]) -> tuple[Enum, ...]:
        if len(values) != len(set(values)):
            raise ValueError("regulatory rule verdict filters must be unique")
        return tuple(sorted(values, key=lambda value: value.value))


class PublicationPolicy(StrictFrozenModel):
    schema_id: Literal[POLICY_SCHEMA] = Field(
        default=POLICY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    policy_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=100)
    allowed_channels: tuple[str, ...] = Field(min_length=1)
    allowed_audiences: tuple[str, ...] = Field(min_length=1)
    allowed_brand_profiles: tuple[str, ...] = ("*",)
    allowed_territories: tuple[str, ...] = Field(min_length=1)
    required_component_ids: tuple[str, ...] = ()
    require_known_provenance: bool = True
    require_rights_clearance: bool = True
    block_tampered_provenance: bool = True
    block_unlicensed_reference_match: bool = True
    block_unconsented_identity_match: bool = True
    regulatory_rules: tuple[RegulatoryRule, ...] = ()

    @field_validator("allowed_channels", "allowed_audiences", "allowed_brand_profiles")
    @classmethod
    def normalize_casefolded_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.strip().casefold() for value in values if value.strip()}))
        if not normalized:
            raise ValueError("allowed value sets cannot be empty")
        return normalized

    @field_validator("allowed_territories")
    @classmethod
    def normalize_territories(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.upper() for value in values}))
        if any(value != "*" and (len(value) != 2 or not value.isalpha()) for value in normalized):
            raise ValueError("allowed_territories must contain '*' or two-letter territory codes")
        return normalized

    @field_validator("required_component_ids")
    @classmethod
    def normalize_components(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("required_component_ids must be unique")
        return tuple(sorted(values))

    @field_validator("regulatory_rules")
    @classmethod
    def normalize_regulatory_rules(
        cls,
        values: tuple[RegulatoryRule, ...],
    ) -> tuple[RegulatoryRule, ...]:
        rule_ids = [value.rule_id for value in values]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("regulatory rule_id values must be unique")
        return tuple(sorted(values, key=lambda value: value.rule_id))

    @model_validator(mode="after")
    def policy_requires_real_controls(self) -> PublicationPolicy:
        if not any(
            (
                self.require_known_provenance,
                self.require_rights_clearance,
                self.block_tampered_provenance,
                self.block_unlicensed_reference_match,
                self.block_unconsented_identity_match,
                bool(self.required_component_ids),
            )
        ):
            raise ValueError("publication policy must enable at least one release control")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)

    def commitment_sha256(self) -> str:
        return _canonical_hash(self.canonical_payload())


class PolicyEvaluationResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    assessment: DeploymentAssessment


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _allowed(value: str, configured: tuple[str, ...]) -> bool:
    return "*" in configured or value.casefold() in configured


def _regulatory_rule_matches(
    rule: RegulatoryRule,
    *,
    context: AssessmentContext,
    provenance: ProvenanceAssessment,
    rights: RightsAssessment,
) -> bool:
    if not _allowed(context.channel, rule.channels):
        return False
    if not _allowed(context.audience, rule.audiences):
        return False
    if not _allowed(context.brand_profile or "", rule.brand_profiles):
        return False
    if "*" not in rule.territories and not set(context.territories).intersection(rule.territories):
        return False
    if rule.provenance_verdicts and provenance.verdict not in rule.provenance_verdicts:
        return False
    return not rule.rights_verdicts or rights.verdict in rule.rights_verdicts


def evaluate_publication_policy(
    *,
    asset_sha256: str,
    context: AssessmentContext,
    policy: PublicationPolicy,
    provenance: ProvenanceAssessment,
    rights: RightsAssessment,
    licence: LicenceEvaluationResult,
    components: tuple[ComponentRecord, ...],
) -> PolicyEvaluationResult:
    """Compile a deterministic decision; detector output cannot change policy."""

    if context.policy_id != policy.policy_id or context.policy_version != policy.version:
        raise ValueError("assessment context does not match the supplied policy identity")

    policy_sha256 = policy.commitment_sha256()
    components_by_id = {item.component_id: item for item in components}
    block_reasons: list[tuple[str, str]] = []
    review_reasons: list[tuple[str, str]] = []

    if not _allowed(context.channel, policy.allowed_channels):
        block_reasons.append(("context.channel", "The declared channel is not permitted."))
    if not _allowed(context.audience, policy.allowed_audiences):
        block_reasons.append(("context.audience", "The declared audience is not permitted."))
    if not _allowed(context.brand_profile or "", policy.allowed_brand_profiles):
        block_reasons.append(
            ("context.brand-profile", "The declared brand profile is not permitted.")
        )
    if "*" not in policy.allowed_territories:
        unsupported = sorted(set(context.territories) - set(policy.allowed_territories))
        if unsupported:
            block_reasons.append(
                ("context.territory", f"Territories are not permitted: {','.join(unsupported)}.")
            )

    for component_id in policy.required_component_ids:
        component = components_by_id.get(component_id)
        if component is None:
            review_reasons.append(
                (f"component.{component_id}", f"Required component {component_id} is absent.")
            )
        elif component.state != ComponentState.AVAILABLE:
            review_reasons.append(
                (
                    f"component.{component_id}",
                    f"Required component {component_id} is {component.state.value}.",
                )
            )

    if policy.block_tampered_provenance and provenance.verdict == ProvenanceVerdict.TAMPERED:
        block_reasons.append(
            (
                "provenance.tampered",
                "Governed provenance or watermark evidence indicates tampering.",
            )
        )
    elif provenance.verdict == ProvenanceVerdict.TAMPERED:
        review_reasons.append(
            ("provenance.tampered", "Tampered provenance cannot satisfy the release invariant.")
        )
    elif policy.require_known_provenance and provenance.verdict == ProvenanceVerdict.UNKNOWN:
        review_reasons.append(
            ("provenance.known", "Provenance is unknown and requires human review.")
        )
    elif provenance.verdict == ProvenanceVerdict.UNKNOWN:
        review_reasons.append(
            ("provenance.release-floor", "Unknown provenance cannot satisfy the release invariant.")
        )
    if provenance.state != AssessmentState.COMPLETE:
        review_reasons.append(
            ("provenance.complete", "The provenance assessment is incomplete or unavailable.")
        )

    if licence.policy_conflict and policy.block_unlicensed_reference_match:
        block_reasons.append(
            (
                "rights.licence-coverage",
                "At least one governed reference candidate lacks licence coverage "
                "for this context.",
            )
        )
    elif (
        rights.verdict == RightsVerdict.POLICY_CONFLICT
        and policy.block_unconsented_identity_match
    ):
        block_reasons.append(
            (
                "rights.consent-coverage",
                "At least one enrolled likeness or voice candidate lacks consent coverage for this context.",
            )
        )
    elif rights.verdict == RightsVerdict.POLICY_CONFLICT:
        review_reasons.append(
            ("rights.policy-conflict", "Rights evidence conflicts with the deployment policy.")
        )

    if policy.require_rights_clearance and rights.verdict != RightsVerdict.CLEAR:
        review_reasons.append(
            ("rights.clearance", "The rights assessment does not provide scoped clearance.")
        )
    elif rights.verdict != RightsVerdict.CLEAR:
        review_reasons.append(
            ("rights.release-floor", "Non-clear rights cannot satisfy the release invariant.")
        )
    if rights.state != AssessmentState.COMPLETE:
        review_reasons.append(
            ("rights.complete", "The rights assessment is incomplete or unavailable.")
        )

    for rule in policy.regulatory_rules:
        if not _regulatory_rule_matches(
            rule,
            context=context,
            provenance=provenance,
            rights=rights,
        ):
            continue
        reason = (f"regulatory.{rule.rule_id}", rule.description)
        if rule.effect == RegulatoryRuleEffect.BLOCK:
            block_reasons.append(reason)
        else:
            review_reasons.append(reason)

    # Deduplicate while retaining deterministic citation/reason ordering.
    block_reasons = sorted(set(block_reasons))
    review_reasons = sorted(set(review_reasons))
    if block_reasons:
        decision = DeploymentDecision.BLOCK
        selected_reasons = block_reasons
    elif review_reasons:
        decision = DeploymentDecision.REVIEW
        selected_reasons = review_reasons
    else:
        decision = DeploymentDecision.GO
        selected_reasons = [("release.go", "All configured release controls passed.")]

    citations = tuple(
        f"{policy.policy_id}@{policy.version}:{rule_id}" for rule_id, _ in selected_reasons
    )
    limitations = (
        tuple(reason for _, reason in selected_reasons)
        if decision == DeploymentDecision.REVIEW
        else ()
    )
    evidence_id = f"evidence.policy-{asset_sha256[:16]}-{policy_sha256[:12]}"
    evaluation_payload = {
        "asset_sha256": asset_sha256,
        "block_reasons": block_reasons,
        "context": context.model_dump(mode="json"),
        "decision": decision.value,
        "policy_sha256": policy_sha256,
        "review_reasons": review_reasons,
    }
    evidence = EvidencePointer(
        evidence_id=evidence_id,
        asset_sha256=asset_sha256,
        kind=EvidenceKind.POLICY_RULE,
        source="RightsGate deterministic publication policy",
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        polarity=(
            EvidencePolarity.SUPPORTS
            if decision == DeploymentDecision.GO
            else EvidencePolarity.CONTRADICTS
            if decision == DeploymentDecision.BLOCK
            else EvidencePolarity.NEUTRAL
        ),
        confidence=1,
        locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
        summary=f"Versioned policy evaluation produced {decision.value}.",
        payload_sha256=_canonical_hash(evaluation_payload),
        attributes={
            "block_reason_count": len(block_reasons),
            "decision": decision.value,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "review_reason_count": len(review_reasons),
        },
    )
    claim = ClaimRecord(
        claim_id=f"claim.policy-release-{asset_sha256[:16]}-{policy_sha256[:12]}",
        dimension=ClaimDimension.DEPLOYMENT_READINESS,
        claim_type="policy.publication-ready",
        statement="The asset satisfies all mandatory rules in the supplied publication policy.",
        outcome=(
            ClaimOutcome.SUPPORTED
            if decision == DeploymentDecision.GO
            else ClaimOutcome.CONTRADICTED
            if decision == DeploymentDecision.BLOCK
            else ClaimOutcome.UNKNOWN
        ),
        confidence=1 if decision != DeploymentDecision.REVIEW else 0,
        mandatory=True,
        evidence_ids=(evidence_id,),
        limitations=limitations,
    )
    incomplete_inputs = any(
        components_by_id.get(component_id) is None
        or components_by_id[component_id].state != ComponentState.AVAILABLE
        for component_id in policy.required_component_ids
    ) or provenance.state != AssessmentState.COMPLETE or rights.state != AssessmentState.COMPLETE
    state = (
        AssessmentState.PARTIAL
        if decision == DeploymentDecision.REVIEW and incomplete_inputs
        else AssessmentState.COMPLETE
    )
    component = ComponentRecord(
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        component_type=COMPONENT_TYPE,
        state=ComponentState.AVAILABLE,
        artifact_sha256=policy_sha256,
    )
    return PolicyEvaluationResult(
        component=component,
        evidence=(evidence,),
        assessment=DeploymentAssessment(
            state=state,
            decision=decision,
            confidence=1,
            claims=(claim,),
            policy_citations=citations,
            limitations=limitations,
        ),
    )
