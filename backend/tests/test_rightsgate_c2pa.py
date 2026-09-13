"""C2PA provenance adapter tests with real no-manifest and bounded fake reports."""

from __future__ import annotations

import io

import c2pa
from PIL import Image

from app.rightsgate import (
    AssessmentState,
    ClaimOutcome,
    ComponentState,
    EvidencePolarity,
    ProvenanceVerdict,
)
from app.rightsgate.provenance import c2pa as adapter

ASSET_SHA256 = "a" * 64


def unsigned_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=(255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def observation(
    validation_state: str,
    *,
    digital_source_type: str | None = None,
    failures: tuple[str, ...] = (),
) -> adapter._ManifestObservation:
    action = {"action": "c2pa.created"}
    if digital_source_type:
        action["digitalSourceType"] = (
            "http://cv.iptc.org/newscodes/digitalsourcetype/" + digital_source_type
        )
    results = {
        "activeManifest": {
            "success": [{"code": "claimSignature.validated"}],
            "informational": [],
            "failure": [{"code": code} for code in failures],
        }
    }
    active = {
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "data": {"actions": [action]},
            }
        ]
    }
    return adapter._ManifestObservation(
        validation_state=validation_state,
        validation_results=results,
        active_manifest=active,
        report={
            "active_manifest": "urn:c2pa:test",
            "manifests": {"urn:c2pa:test": active},
            "validation_state": validation_state,
            "validation_results": results,
        },
    )


def test_unsigned_asset_is_unknown_not_human_authored() -> None:
    result = adapter.verify_c2pa(unsigned_png(), "image/png", ASSET_SHA256)

    assert result.component.state == ComponentState.AVAILABLE
    assert result.evidence == ()
    assert result.assessment.state == AssessmentState.COMPLETE
    assert result.assessment.verdict == ProvenanceVerdict.UNKNOWN
    assert result.assessment.claims[0].outcome == ClaimOutcome.UNKNOWN
    assert "not evidence of human authorship" in result.assessment.limitations[0]


def test_trusted_ai_declaration_maps_to_ai_generated(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "_read_manifest",
        lambda *_: observation("Trusted", digital_source_type="trainedAlgorithmicMedia"),
    )

    result = adapter.verify_c2pa(b"asset", "image/jpeg", ASSET_SHA256)
    assert result.assessment.verdict == ProvenanceVerdict.AI_GENERATED
    assert result.assessment.confidence == 1
    assert result.evidence[0].polarity == EvidencePolarity.SUPPORTS
    assert result.evidence[0].attributes["digital_source_types"] == "trainedAlgorithmicMedia"
    assert result.assessment.claims[1].outcome == ClaimOutcome.SUPPORTED


def test_valid_composite_declaration_maps_to_partial_generation(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "_read_manifest",
        lambda *_: observation(
            "Valid",
            digital_source_type="compositeWithTrainedAlgorithmicMedia",
        ),
    )

    result = adapter.verify_c2pa(b"asset", "image/jpeg", ASSET_SHA256)
    assert result.assessment.verdict == ProvenanceVerdict.PARTIALLY_GENERATED
    assert result.assessment.confidence == 0.95


def test_valid_credential_without_ai_declaration_does_not_imply_human_authorship(
    monkeypatch,
) -> None:
    monkeypatch.setattr(adapter, "_read_manifest", lambda *_: observation("Valid"))

    result = adapter.verify_c2pa(b"asset", "image/jpeg", ASSET_SHA256)
    assert result.assessment.verdict == ProvenanceVerdict.UNKNOWN
    assert result.assessment.claims[0].outcome == ClaimOutcome.SUPPORTED
    assert "does not declare" in result.assessment.limitations[0]


def test_invalid_credential_is_tamper_signal_with_status_codes(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "_read_manifest",
        lambda *_: observation("Invalid", failures=("assertion.dataHash.mismatch",)),
    )

    result = adapter.verify_c2pa(b"asset", "image/jpeg", ASSET_SHA256)
    assert result.assessment.verdict == ProvenanceVerdict.TAMPERED
    assert result.assessment.claims[0].outcome == ClaimOutcome.CONTRADICTED
    assert result.evidence[0].polarity == EvidencePolarity.CONTRADICTS
    assert result.evidence[0].attributes["failure_codes"] == "assertion.dataHash.mismatch"


def test_untrusted_credential_is_invalid_but_not_called_tampered(monkeypatch) -> None:
    monkeypatch.setattr(
        adapter,
        "_read_manifest",
        lambda *_: observation("Invalid", failures=("signingCredential.untrusted",)),
    )

    result = adapter.verify_c2pa(b"asset", "image/jpeg", ASSET_SHA256)
    assert result.assessment.verdict == ProvenanceVerdict.UNKNOWN
    assert result.assessment.claims[0].outcome == ClaimOutcome.CONTRADICTED
    assert "do not establish tampering" in result.assessment.limitations[0]


def test_sdk_error_degrades_and_fails_closed(monkeypatch) -> None:
    def fail(*_):
        raise c2pa.C2paError.NotSupported("unsupported media")

    monkeypatch.setattr(adapter, "_read_manifest", fail)
    result = adapter.verify_c2pa(b"asset", "application/octet-stream", ASSET_SHA256)

    assert result.component.state == ComponentState.DEGRADED
    assert result.assessment.state == AssessmentState.UNAVAILABLE
    assert result.assessment.verdict == ProvenanceVerdict.UNKNOWN
    assert result.assessment.claims[0].outcome == ClaimOutcome.NOT_ASSESSED
    assert result.evidence[0].attributes["error_category"] == "unsupported media"
