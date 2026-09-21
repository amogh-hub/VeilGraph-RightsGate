"""Bounded watermark, likeness-consent and voice-consent controls."""

from __future__ import annotations

import hashlib
import io
import math
import struct
import wave
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageOps

from app.rightsgate.contracts import AssessmentContext, EvidencePolarity, ProvenanceVerdict
from app.rightsgate.provenance.watermark import (
    VisibleWatermarkRegistry,
    build_visible_watermark_profile,
    verify_visible_watermarks,
)
from app.rightsgate.rights.consent import (
    ConsentGrant,
    ConsentRegistry,
    analyze_likeness_consent,
    analyze_voice_consent,
    build_likeness_template,
    build_voice_template,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def context(*, territory: str = "IN") -> AssessmentContext:
    return AssessmentContext(
        policy_id="policy.publication",
        policy_version="1",
        intended_use="public campaign",
        channel="web",
        audience="general",
        territories=(territory,),
        brand_profile="acme",
    )


def consent(*, territories: tuple[str, ...] = ("IN",)) -> ConsentGrant:
    return ConsentGrant(
        consent_id="consent.subject-001",
        source_record_id="consent-record.subject-001",
        subject_id="person.subject-001",
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
        territories=territories,
        channels=("web",),
        intended_uses=("public campaign",),
    )


def patterned_image(size: tuple[int, int] = (128, 128)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for value in range(0, min(size), 8):
        draw.line((0, value, value, 0), fill=(value % 255, 40, 180), width=3)
    draw.rectangle((30, 30, 98, 98), outline="black", width=4)
    draw.ellipse((48, 42, 78, 82), fill=(30, 90, 160))
    return image


def pcm_tone(frequency: float, *, amplitude: float = 0.5) -> bytes:
    sample_rate = 16_000
    samples = [
        int(32767 * amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
        for index in range(sample_rate)
    ]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"".join(struct.pack("<h", value) for value in samples))
    return buffer.getvalue()


def test_visible_watermark_profile_accepts_intact_region_and_detects_mismatch() -> None:
    template = patterned_image((32, 32))
    asset = Image.new("RGB", (128, 128), "gray")
    asset.paste(template, (96, 96))
    template_data = png(template)
    profile = build_visible_watermark_profile(
        profile_id="watermark.acme-001",
        source_record_id="brand-record.acme-001",
        brand_profiles=("acme",),
        normalized_bbox=(0.75, 0.75, 1.0, 1.0),
        template_data=template_data,
        max_hamming_distance=4,
    )
    registry = VisibleWatermarkRegistry(
        registry_id="registry.watermarks",
        version="1",
        profiles=(profile,),
    )
    asset_data = png(asset)
    intact = verify_visible_watermarks(
        asset_data,
        asset_sha256=hashlib.sha256(asset_data).hexdigest(),
        context=context(),
        registry=registry,
    )
    assert intact.assessment.verdict == ProvenanceVerdict.UNKNOWN
    assert intact.assessment.claims[0].outcome.value == "SUPPORTED"
    assert intact.evidence[0].polarity == EvidencePolarity.SUPPORTS
    assert intact.evidence[0].attributes["intact"] is True

    tampered_asset = asset.copy()
    tampered_asset.paste(ImageOps.invert(template), (96, 96))
    tampered_data = png(tampered_asset)
    tampered = verify_visible_watermarks(
        tampered_data,
        asset_sha256=hashlib.sha256(tampered_data).hexdigest(),
        context=context(),
        registry=registry,
    )
    assert tampered.assessment.verdict == ProvenanceVerdict.TAMPERED
    assert tampered.assessment.claims[0].outcome.value == "CONTRADICTED"
    assert tampered.evidence[0].polarity == EvidencePolarity.CONTRADICTS
    assert tampered.evidence[0].attributes["intact"] is False


def test_likeness_reference_requires_context_valid_consent() -> None:
    data = png(patterned_image())
    template = build_likeness_template(
        template_id="likeness.subject-001",
        reference_data=data,
        consent=consent(),
    )
    registry = ConsentRegistry(
        registry_id="registry.consents",
        version="1",
        likeness_templates=(template,),
    )
    result = analyze_likeness_consent(
        data,
        asset_sha256=hashlib.sha256(data).hexdigest(),
        context=context(),
        registry=registry,
        assessed_at=NOW,
    )
    assert result.policy_conflict is False
    assert result.candidate_subject_ids == ("person.subject-001",)
    assert result.evidence[0].attributes["covered"] is True

    conflict = analyze_likeness_consent(
        data,
        asset_sha256=hashlib.sha256(data).hexdigest(),
        context=context(territory="US"),
        registry=registry,
        assessed_at=NOW,
    )
    assert conflict.policy_conflict is True
    assert conflict.claims[0].outcome.value == "CONTRADICTED"


def test_voice_reference_matching_is_bounded_and_consent_scoped() -> None:
    reference = pcm_tone(440)
    template = build_voice_template(
        template_id="voice.subject-001",
        reference_data=reference,
        consent=consent(),
        minimum_similarity=0.99,
    )
    registry = ConsentRegistry(
        registry_id="registry.consents",
        version="1",
        voice_templates=(template,),
    )
    gain_changed = pcm_tone(440, amplitude=0.25)
    matched = analyze_voice_consent(
        gain_changed,
        asset_sha256=hashlib.sha256(gain_changed).hexdigest(),
        context=context(),
        registry=registry,
        assessed_at=NOW,
    )
    assert matched.policy_conflict is False
    assert matched.candidate_subject_ids == ("person.subject-001",)
    assert matched.evidence[0].attributes["covered"] is True

    different = pcm_tone(880)
    no_match = analyze_voice_consent(
        different,
        asset_sha256=hashlib.sha256(different).hexdigest(),
        context=context(),
        registry=registry,
        assessed_at=NOW,
    )
    assert no_match.candidate_subject_ids == ()
    assert no_match.policy_conflict is False
    assert no_match.claims[0].outcome.value == "CONTRADICTED"
