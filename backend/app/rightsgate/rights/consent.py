"""Governed consent matching for enrolled likeness and acoustic references.

The matchers are deliberately bounded candidate-retrieval controls. They do
not perform open-world face recognition or speaker identification and never
infer consent from similarity alone.
"""

from __future__ import annotations

import hashlib
import io
import json
import wave
from datetime import datetime
from typing import Any, Literal

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import Field, field_validator, model_validator

from ..contracts import (
    AssessmentContext,
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
    SHA256_PATTERN,
    ID_PATTERN,
    StrictFrozenModel,
)

CONSENT_REGISTRY_SCHEMA = "veilgraph.rightsgate.consent-registry.v1"
LIKENESS_COMPONENT_ID = "rights.likeness-consent"
VOICE_COMPONENT_ID = "rights.voice-consent"
COMPONENT_VERSION = "1.0.0"
DHASH_PATTERN = r"^[0-9a-f]{16}$"
VOICE_FEATURE_COUNT = 48
MAX_AUDIO_SECONDS = 300.0


class ConsentGrant(StrictFrozenModel):
    consent_id: str = Field(pattern=ID_PATTERN)
    source_record_id: str = Field(pattern=ID_PATTERN)
    subject_id: str = Field(pattern=ID_PATTERN)
    valid_from: datetime
    valid_until: datetime
    territories: tuple[str, ...] = Field(min_length=1)
    channels: tuple[str, ...] = Field(min_length=1)
    intended_uses: tuple[str, ...] = Field(min_length=1)

    @field_validator("valid_from", "valid_until")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("consent timestamps must be timezone-aware")
        return value

    @field_validator("territories")
    @classmethod
    def normalize_territories(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.upper() for value in values}))
        if any(value != "*" and (len(value) != 2 or not value.isalpha()) for value in normalized):
            raise ValueError("territories must contain '*' or two-letter codes")
        return normalized

    @field_validator("channels", "intended_uses")
    @classmethod
    def normalize_text(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.strip().casefold() for value in values if value.strip()}))
        if not normalized:
            raise ValueError("consent scope values cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_window(self) -> ConsentGrant:
        if self.valid_until <= self.valid_from:
            raise ValueError("consent valid_until must be after valid_from")
        return self


class LikenessTemplate(StrictFrozenModel):
    template_id: str = Field(pattern=ID_PATTERN)
    reference_sha256: str = Field(pattern=SHA256_PATTERN)
    dhash: str = Field(pattern=DHASH_PATTERN)
    consent: ConsentGrant
    max_hamming_distance: int = Field(default=6, ge=0, le=64)


class VoiceTemplate(StrictFrozenModel):
    template_id: str = Field(pattern=ID_PATTERN)
    reference_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_version: Literal["log-spectrum-voice-reference.v1"] = (
        "log-spectrum-voice-reference.v1"
    )
    features: tuple[float, ...] = Field(
        min_length=VOICE_FEATURE_COUNT,
        max_length=VOICE_FEATURE_COUNT,
    )
    consent: ConsentGrant
    minimum_similarity: float = Field(default=0.94, ge=0.5, le=1)

    @field_validator("features")
    @classmethod
    def finite_features(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if not all(np.isfinite(value) for value in values):
            raise ValueError("voice features must be finite")
        norm = float(np.linalg.norm(np.asarray(values, dtype=np.float64)))
        if not 0.999 <= norm <= 1.001:
            raise ValueError("voice features must be unit-normalized")
        return values


class ConsentRegistry(StrictFrozenModel):
    schema_id: Literal[CONSENT_REGISTRY_SCHEMA] = Field(
        default=CONSENT_REGISTRY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    registry_id: str = Field(pattern=ID_PATTERN)
    version: str = Field(min_length=1, max_length=100)
    likeness_templates: tuple[LikenessTemplate, ...] = ()
    voice_templates: tuple[VoiceTemplate, ...] = ()

    @model_validator(mode="after")
    def unique_templates_and_consents(self) -> ConsentRegistry:
        templates = [item.template_id for item in self.likeness_templates + self.voice_templates]
        if len(templates) != len(set(templates)):
            raise ValueError("template_id values must be unique")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True)
        payload["likeness_templates"] = sorted(
            payload["likeness_templates"], key=lambda item: item["template_id"]
        )
        payload["voice_templates"] = sorted(
            payload["voice_templates"], key=lambda item: item["template_id"]
        )
        return payload

    def commitment_sha256(self) -> str:
        return _canonical_hash(self.canonical_payload())


class ConsentAnalysisResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    claims: tuple[ClaimRecord, ...]
    candidate_subject_ids: tuple[str, ...]
    policy_conflict: bool
    confidence: float = Field(ge=0, le=1)
    state: AssessmentState
    limitations: tuple[str, ...] = ()


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _image_dhash(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened).convert("L").resize(
                (9, 8), Image.Resampling.LANCZOS
            )
            pixels = list(image.get_flattened_data())
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("likeness reference could not be decoded safely") from error
    bits = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            bits = (bits << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return f"{bits:016x}"


def _pcm_samples(data: bytes) -> tuple[np.ndarray, int]:
    try:
        with wave.open(io.BytesIO(data), "rb") as stream:
            if stream.getcomptype() != "NONE":
                raise ValueError("voice references require uncompressed PCM/WAV")
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            frame_count = stream.getnframes()
            if not 1 <= channels <= 8 or sample_width not in {1, 2, 3, 4}:
                raise ValueError("unsupported PCM voice-reference layout")
            if not 8_000 <= sample_rate <= 192_000:
                raise ValueError("voice-reference sample rate is outside the bounded range")
            if frame_count < max(128, sample_rate // 10):
                raise ValueError("voice reference must contain at least 100 ms of audio")
            if frame_count / sample_rate > MAX_AUDIO_SECONDS:
                raise ValueError("voice reference exceeds the bounded duration")
            raw = stream.readframes(frame_count)
            expected = frame_count * channels * sample_width
            if len(raw) != expected:
                raise ValueError("voice-reference PCM payload is truncated")
    except (wave.Error, EOFError) as error:
        raise ValueError("voice reference could not be decoded as PCM/WAV") from error

    if sample_width == 1:
        values = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0
        scale = 128.0
    elif sample_width == 2:
        values = np.frombuffer(raw, dtype="<i2").astype(np.float64)
        scale = 32768.0
    elif sample_width == 4:
        values = np.frombuffer(raw, dtype="<i4").astype(np.float64)
        scale = 2147483648.0
    else:
        triplets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        packed = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
        values = np.where(packed & 0x800000, packed - 0x1000000, packed).astype(np.float64)
        scale = 8388608.0
    mono = (values.reshape(-1, channels) / scale).mean(axis=1)
    if not np.isfinite(mono).all() or float(np.max(np.abs(mono))) < 1e-6:
        raise ValueError("voice reference contains no usable acoustic signal")
    return mono, sample_rate


def voice_reference_features(data: bytes) -> tuple[float, ...]:
    """Return a bounded acoustic reference fingerprint, not a speaker embedding."""

    samples, sample_rate = _pcm_samples(data)
    samples = samples - float(np.mean(samples))
    frame_size = max(256, round(sample_rate * 0.025))
    hop = max(128, round(sample_rate * 0.010))
    if len(samples) < frame_size:
        samples = np.pad(samples, (0, frame_size - len(samples)))
    starts = range(0, len(samples) - frame_size + 1, hop)
    frames = np.stack([samples[start : start + frame_size] for start in starts])
    energies = np.sqrt(np.mean(frames * frames, axis=1))
    floor = max(1e-8, float(np.percentile(energies, 40)) * 0.5)
    frames = frames[energies >= floor]
    if not len(frames):
        raise ValueError("voice reference contains no usable non-silent frames")
    window = np.hanning(frame_size)
    spectra = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    frequencies = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
    upper = min(8_000.0, sample_rate / 2)
    edges = np.geomspace(80.0, upper, 25)
    bands: list[np.ndarray] = []
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        mask = (frequencies >= low) & (frequencies < high)
        if not np.any(mask):
            nearest = int(np.argmin(np.abs(frequencies - ((low + high) / 2))))
            mask[nearest] = True
        bands.append(np.log1p(np.mean(spectra[:, mask], axis=1)))
    matrix = np.stack(bands, axis=1)
    vector = np.concatenate((matrix.mean(axis=0), matrix.std(axis=0)))
    vector = vector - float(np.mean(vector))
    norm = float(np.linalg.norm(vector))
    if norm < 1e-12:
        raise ValueError("voice reference produced a degenerate fingerprint")
    vector /= norm
    return tuple(round(float(value), 10) for value in vector)


def build_likeness_template(
    *,
    template_id: str,
    reference_data: bytes,
    consent: ConsentGrant,
    max_hamming_distance: int = 6,
) -> LikenessTemplate:
    return LikenessTemplate(
        template_id=template_id,
        reference_sha256=hashlib.sha256(reference_data).hexdigest(),
        dhash=_image_dhash(reference_data),
        consent=consent,
        max_hamming_distance=max_hamming_distance,
    )


def build_voice_template(
    *,
    template_id: str,
    reference_data: bytes,
    consent: ConsentGrant,
    minimum_similarity: float = 0.94,
) -> VoiceTemplate:
    return VoiceTemplate(
        template_id=template_id,
        reference_sha256=hashlib.sha256(reference_data).hexdigest(),
        features=voice_reference_features(reference_data),
        consent=consent,
        minimum_similarity=minimum_similarity,
    )


def _scope_covers(grant: ConsentGrant, context: AssessmentContext, assessed_at: datetime) -> bool:
    territories = set(context.territories)
    return bool(
        grant.valid_from <= assessed_at <= grant.valid_until
        and ("*" in grant.territories or territories.issubset(set(grant.territories)))
        and ("*" in grant.channels or context.channel.casefold() in grant.channels)
        and (
            "*" in grant.intended_uses
            or context.intended_use.casefold() in grant.intended_uses
        )
    )


def _component(component_id: str, registry: ConsentRegistry) -> ComponentRecord:
    return ComponentRecord(
        component_id=component_id,
        component_version=COMPONENT_VERSION,
        component_type="rights.governed-consent-reference-matcher",
        state=ComponentState.AVAILABLE,
        artifact_sha256=registry.commitment_sha256(),
    )


def _no_candidate(
    *,
    component_id: str,
    asset_sha256: str,
    registry: ConsentRegistry,
    modality: str,
) -> ConsentAnalysisResult:
    evidence_id = f"evidence.{modality}-consent-query-{asset_sha256[:16]}"
    limitation = (
        f"No enrolled {modality} reference met the configured threshold; "
        "registry non-match is not proof that no protected person or voice is present."
    )
    return ConsentAnalysisResult(
        component=_component(component_id, registry),
        evidence=(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.REFERENCE_MATCH,
                source=f"Governed {modality} consent registry",
                component_id=component_id,
                component_version=COMPONENT_VERSION,
                polarity=EvidencePolarity.CONTRADICTS,
                confidence=1,
                locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                summary=f"No enrolled {modality} reference met the configured threshold.",
                payload_sha256=_canonical_hash(
                    {
                        "asset_sha256": asset_sha256,
                        "modality": modality,
                        "registry_sha256": registry.commitment_sha256(),
                    }
                ),
                attributes={
                    "candidate_count": 0,
                    "registry_id": registry.registry_id,
                    "registry_version": registry.version,
                },
            ),
        ),
        claims=(
            ClaimRecord(
                claim_id=f"claim.{modality}-candidate-{asset_sha256[:16]}",
                dimension=ClaimDimension.RIGHTS_EXPOSURE,
                claim_type=f"consent.{modality}-candidate",
                statement=f"The asset matches an enrolled {modality} reference.",
                outcome=ClaimOutcome.CONTRADICTED,
                confidence=1,
                mandatory=False,
                evidence_ids=(evidence_id,),
                limitations=(limitation,),
            ),
        ),
        candidate_subject_ids=(),
        policy_conflict=False,
        confidence=0,
        state=AssessmentState.COMPLETE,
        limitations=(limitation,),
    )


def analyze_likeness_consent(
    data: bytes,
    *,
    asset_sha256: str,
    context: AssessmentContext,
    registry: ConsentRegistry,
    assessed_at: datetime,
) -> ConsentAnalysisResult:
    if hashlib.sha256(data).hexdigest() != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied image bytes")
    candidate_dhash = _image_dhash(data)
    matches: list[tuple[LikenessTemplate, int, float]] = []
    for template in registry.likeness_templates:
        distance = (int(candidate_dhash, 16) ^ int(template.dhash, 16)).bit_count()
        exact = template.reference_sha256 == asset_sha256
        if exact or distance <= template.max_hamming_distance:
            similarity = 1.0 if exact else round(max(0.5, 1.0 - distance / 64.0), 6)
            matches.append((template, distance, similarity))
    if not matches:
        return _no_candidate(
            component_id=LIKENESS_COMPONENT_ID,
            asset_sha256=asset_sha256,
            registry=registry,
            modality="likeness",
        )
    return _matched_consents(
        component_id=LIKENESS_COMPONENT_ID,
        asset_sha256=asset_sha256,
        context=context,
        registry=registry,
        assessed_at=assessed_at,
        modality="likeness",
        matches=tuple((item, distance, similarity) for item, distance, similarity in matches),
    )


def analyze_voice_consent(
    data: bytes,
    *,
    asset_sha256: str,
    context: AssessmentContext,
    registry: ConsentRegistry,
    assessed_at: datetime,
) -> ConsentAnalysisResult:
    if hashlib.sha256(data).hexdigest() != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied audio bytes")
    candidate = np.asarray(voice_reference_features(data), dtype=np.float64)
    matches: list[tuple[VoiceTemplate, int, float]] = []
    for template in registry.voice_templates:
        similarity = float(
            np.clip(np.dot(candidate, np.asarray(template.features, dtype=np.float64)), -1, 1)
        )
        if template.reference_sha256 == asset_sha256:
            similarity = 1.0
        if similarity >= template.minimum_similarity:
            matches.append((template, 0, round(similarity, 6)))
    if not matches:
        return _no_candidate(
            component_id=VOICE_COMPONENT_ID,
            asset_sha256=asset_sha256,
            registry=registry,
            modality="voice",
        )
    return _matched_consents(
        component_id=VOICE_COMPONENT_ID,
        asset_sha256=asset_sha256,
        context=context,
        registry=registry,
        assessed_at=assessed_at,
        modality="voice",
        matches=tuple((item, distance, similarity) for item, distance, similarity in matches),
    )


def _matched_consents(
    *,
    component_id: str,
    asset_sha256: str,
    context: AssessmentContext,
    registry: ConsentRegistry,
    assessed_at: datetime,
    modality: str,
    matches: tuple[tuple[LikenessTemplate | VoiceTemplate, int, float], ...],
) -> ConsentAnalysisResult:
    evidence: list[EvidencePointer] = []
    claims: list[ClaimRecord] = []
    subjects: set[str] = set()
    conflicts: list[float] = []
    for template, distance, similarity in sorted(
        matches, key=lambda item: (-item[2], item[0].template_id)
    ):
        grant = template.consent
        subjects.add(grant.subject_id)
        covered = _scope_covers(grant, context, assessed_at)
        if not covered:
            conflicts.append(similarity)
        token = hashlib.sha256(template.template_id.encode("utf-8")).hexdigest()[:16]
        evidence_id = f"evidence.{modality}-consent-{token}-{asset_sha256[:16]}"
        payload = {
            "asset_sha256": asset_sha256,
            "consent_id": grant.consent_id,
            "context": context.model_dump(mode="json"),
            "covered": covered,
            "registry_sha256": registry.commitment_sha256(),
            "similarity": similarity,
            "template_id": template.template_id,
        }
        evidence.append(
            EvidencePointer(
                evidence_id=evidence_id,
                asset_sha256=asset_sha256,
                kind=EvidenceKind.CONSENT_RECORD,
                source=f"Governed {modality} consent registry",
                component_id=component_id,
                component_version=COMPONENT_VERSION,
                polarity=EvidencePolarity.SUPPORTS if covered else EvidencePolarity.CONTRADICTS,
                confidence=similarity,
                locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
                summary=(
                    f"Enrolled {modality} candidate has consent covering the deployment context."
                    if covered
                    else f"Enrolled {modality} candidate lacks consent covering the deployment context."
                ),
                payload_sha256=_canonical_hash(payload),
                attributes={
                    "consent_id": grant.consent_id,
                    "covered": covered,
                    "registry_id": registry.registry_id,
                    "registry_version": registry.version,
                    "similarity": similarity,
                    "source_record_id": grant.source_record_id,
                    "subject_id": grant.subject_id,
                    "template_id": template.template_id,
                    **({"dhash_distance": distance} if modality == "likeness" else {}),
                },
            )
        )
        claims.append(
            ClaimRecord(
                claim_id=f"claim.{modality}-consent-{token}-{asset_sha256[:16]}",
                dimension=ClaimDimension.RIGHTS_EXPOSURE,
                claim_type=f"consent.{modality}-coverage",
                statement=(
                    f"Consent for enrolled {modality} subject {grant.subject_id} covers this deployment."
                ),
                outcome=ClaimOutcome.SUPPORTED if covered else ClaimOutcome.CONTRADICTED,
                confidence=similarity,
                mandatory=True,
                evidence_ids=(evidence_id,),
                limitations=(
                    f"This is bounded enrolled-reference matching, not open-world {modality} identification.",
                ),
            )
        )
    return ConsentAnalysisResult(
        component=_component(component_id, registry),
        evidence=tuple(evidence),
        claims=tuple(claims),
        candidate_subject_ids=tuple(sorted(subjects)),
        policy_conflict=bool(conflicts),
        confidence=max((similarity for _, _, similarity in matches), default=0),
        state=AssessmentState.COMPLETE,
        limitations=(
            f"The {modality} lane only evaluates enrolled governed references and does not provide open-world clearance.",
        ),
    )
