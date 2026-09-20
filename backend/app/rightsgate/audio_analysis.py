"""Bounded standalone PCM/WAV ingestion with explicit abstention semantics."""

from __future__ import annotations

import hashlib
import io
import json
import wave

from .contracts import (
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
    RightsAssessment,
    RightsVerdict,
    StrictFrozenModel,
)

COMPONENT_ID = "ingestion.pcm-wav-parser"
COMPONENT_VERSION = "1.0.0"
COMPONENT_TYPE = "ingestion.bounded-audio-decoder"
MAX_DURATION_SECONDS = 300.0
MAX_SAMPLE_RATE = 192_000
MAX_CHANNELS = 8


class AudioStreamInfo(StrictFrozenModel):
    channels: int
    sample_width_bytes: int
    sample_rate_hz: int
    frame_count: int
    duration_seconds: float


class AudioAnalysisResult(StrictFrozenModel):
    component: ComponentRecord
    evidence: tuple[EvidencePointer, ...]
    provenance: ProvenanceAssessment
    rights: RightsAssessment
    stream: AudioStreamInfo


def _canonical_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def inspect_pcm_wav(
    data: bytes,
    *,
    asset_sha256: str,
) -> AudioAnalysisResult:
    """Validate bounded uncompressed WAV structure without claiming voice identity."""

    if hashlib.sha256(data).hexdigest() != asset_sha256:
        raise ValueError("asset_sha256 does not match the supplied audio bytes")
    if len(data) < 44 or not data.startswith(b"RIFF") or data[8:12] != b"WAVE":
        raise ValueError("standalone audio must be a RIFF/WAVE PCM asset")
    try:
        with wave.open(io.BytesIO(data), "rb") as stream:
            if stream.getcomptype() != "NONE":
                raise ValueError("compressed WAV codecs are not accepted")
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            frame_count = stream.getnframes()
            if not 1 <= channels <= MAX_CHANNELS:
                raise ValueError("audio channel count exceeds the bounded parser policy")
            if sample_width not in {1, 2, 3, 4}:
                raise ValueError("unsupported PCM sample width")
            if not 1 <= sample_rate <= MAX_SAMPLE_RATE:
                raise ValueError("audio sample rate exceeds the bounded parser policy")
            if frame_count < 1:
                raise ValueError("audio contains no PCM frames")
            duration = frame_count / sample_rate
            if duration > MAX_DURATION_SECONDS:
                raise ValueError(
                    f"audio duration exceeds the {MAX_DURATION_SECONDS:.0f}-second limit"
                )
            # Force chunk traversal so truncated data cannot pass on header
            # metadata alone. The input size is already globally bounded.
            decoded = stream.readframes(frame_count)
            expected_bytes = frame_count * channels * sample_width
            if len(decoded) != expected_bytes:
                raise ValueError("audio PCM payload is truncated")
    except (wave.Error, EOFError) as error:
        raise ValueError("audio could not be decoded as bounded PCM/WAV") from error

    info = AudioStreamInfo(
        channels=channels,
        sample_width_bytes=sample_width,
        sample_rate_hz=sample_rate,
        frame_count=frame_count,
        duration_seconds=duration,
    )
    payload = {
        "asset_sha256": asset_sha256,
        **info.model_dump(mode="json"),
    }
    evidence_id = f"evidence.audio-structure-{asset_sha256[:16]}"
    evidence = EvidencePointer(
        evidence_id=evidence_id,
        asset_sha256=asset_sha256,
        kind=EvidenceKind.METADATA,
        source="RightsGate bounded PCM/WAV parser",
        component_id=COMPONENT_ID,
        component_version=COMPONENT_VERSION,
        polarity=EvidencePolarity.NEUTRAL,
        confidence=1,
        locator=EvidenceLocator(kind=LocatorKind.WHOLE_ASSET),
        summary="Decoded the complete bounded PCM/WAV stream and recorded its structure.",
        payload_sha256=_canonical_hash(payload),
        attributes={
            "channels": channels,
            "duration_seconds": round(duration, 6),
            "frame_count": frame_count,
            "sample_rate_hz": sample_rate,
            "sample_width_bytes": sample_width,
        },
    )
    provenance_limitation = (
        "PCM structure does not establish whether audio was human-recorded, generated or edited."
    )
    rights_limitation = (
        "Voice, music and acoustic-work identification are not implemented for standalone audio."
    )
    return AudioAnalysisResult(
        component=ComponentRecord(
            component_id=COMPONENT_ID,
            component_version=COMPONENT_VERSION,
            component_type=COMPONENT_TYPE,
            state=ComponentState.AVAILABLE,
            mandatory=True,
        ),
        evidence=(evidence,),
        provenance=ProvenanceAssessment(
            state=AssessmentState.COMPLETE,
            verdict=ProvenanceVerdict.UNKNOWN,
            confidence=0,
            claims=(
                ClaimRecord(
                    claim_id=f"claim.audio-origin-{asset_sha256[:16]}",
                    dimension=ClaimDimension.PROVENANCE,
                    claim_type="audio.origin",
                    statement="The origin and edit history of the audio are known.",
                    outcome=ClaimOutcome.UNKNOWN,
                    confidence=0,
                    mandatory=True,
                    limitations=(provenance_limitation,),
                ),
            ),
            limitations=(provenance_limitation,),
        ),
        rights=RightsAssessment(
            state=AssessmentState.UNAVAILABLE,
            verdict=RightsVerdict.UNKNOWN,
            confidence=0,
            claims=(
                ClaimRecord(
                    claim_id=f"claim.audio-rights-{asset_sha256[:16]}",
                    dimension=ClaimDimension.RIGHTS_EXPOSURE,
                    claim_type="audio.voice-and-work-exposure",
                    statement="Voices and acoustic works have governed rights coverage.",
                    outcome=ClaimOutcome.NOT_ASSESSED,
                    confidence=0,
                    mandatory=True,
                    limitations=(rights_limitation,),
                ),
            ),
            limitations=(rights_limitation,),
        ),
        stream=info,
    )
