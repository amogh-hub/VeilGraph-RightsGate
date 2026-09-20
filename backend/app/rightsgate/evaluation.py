"""Reproducible metrics for declared RightsGate evaluation manifests."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import SHA256_PATTERN, StrictFrozenModel

EVALUATION_REPORT_SCHEMA = "veilgraph.rightsgate.evaluation-report.v1"
SIGNAL_EVALUATION_REPORT_SCHEMA = "veilgraph.rightsgate.signal-evaluation-report.v1"


class BinaryClassificationMetrics(StrictFrozenModel):
    true_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=1)
    false_positive_rate: float = Field(ge=0, le=1)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)


class CalibrationMetrics(StrictFrozenModel):
    """Bounded binary-score calibration statistics.

    Scores are interpreted as probabilities only inside the declared evaluation
    set. A perfect synthetic result must not be promoted to an open-world model
    calibration claim.
    """

    sample_count: int = Field(gt=0)
    bin_count: int = Field(gt=0, le=100)
    brier_score: float = Field(ge=0, le=1)
    expected_calibration_error: float = Field(ge=0, le=1)
    maximum_calibration_error: float = Field(ge=0, le=1)
    mean_score: float = Field(ge=0, le=1)
    empirical_positive_rate: float = Field(ge=0, le=1)


class StandardsAblation(StrictFrozenModel):
    """Comparison against a credentials/watermark-only decision baseline."""

    sample_count: int = Field(gt=0)
    credentials_or_watermark_evidence_cases: int = Field(ge=0)
    credentials_or_watermark_only: BinaryClassificationMetrics
    full_signal_pipeline: BinaryClassificationMetrics
    accuracy_lift: float = Field(ge=-1, le=1)
    recall_lift: float = Field(ge=-1, le=1)


class EvaluationCaseResult(StrictFrozenModel):
    case_id: str
    expected_match: bool
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    exact_only_prediction: bool
    perceptual_prediction: bool


class RightsRetrievalEvaluationReport(StrictFrozenModel):
    schema_id: Literal[EVALUATION_REPORT_SCHEMA] = Field(
        default=EVALUATION_REPORT_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    dataset_id: str
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    registry_sha256: str = Field(pattern=SHA256_PATTERN)
    max_hamming_distance: int = Field(ge=0, le=64)
    exact_only: BinaryClassificationMetrics
    perceptual: BinaryClassificationMetrics
    cases: tuple[EvaluationCaseResult, ...]
    limitations: tuple[str, ...]


class SignalEvaluationCaseResult(StrictFrozenModel):
    case_id: str
    lane: Literal["visual_localization", "generative_metadata"]
    expected_label: str
    predicted_label: str
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    correct: bool


class ChallengeSignalEvaluationReport(StrictFrozenModel):
    schema_id: Literal[SIGNAL_EVALUATION_REPORT_SCHEMA] = Field(
        default=SIGNAL_EVALUATION_REPORT_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    dataset_id: str
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    registry_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_localization: BinaryClassificationMetrics
    visual_localization_calibration: CalibrationMetrics
    generative_metadata: BinaryClassificationMetrics
    generative_metadata_calibration: CalibrationMetrics
    standards_ablation: StandardsAblation
    partial_edit_subtype_accuracy: float = Field(ge=0, le=1)
    cases: tuple[SignalEvaluationCaseResult, ...]
    limitations: tuple[str, ...]


def binary_metrics(expected: list[bool], predicted: list[bool]) -> BinaryClassificationMetrics:
    if not expected or len(expected) != len(predicted):
        raise ValueError("expected and predicted must be non-empty and equal length")
    true_positive = sum(label and output for label, output in zip(expected, predicted, strict=True))
    true_negative = sum(not label and not output for label, output in zip(expected, predicted, strict=True))
    false_positive = sum(not label and output for label, output in zip(expected, predicted, strict=True))
    false_negative = sum(label and not output for label, output in zip(expected, predicted, strict=True))
    total = len(expected)
    negatives = true_negative + false_positive
    predicted_positive = true_positive + false_positive
    positives = true_positive + false_negative
    return BinaryClassificationMetrics(
        true_positive=true_positive,
        true_negative=true_negative,
        false_positive=false_positive,
        false_negative=false_negative,
        accuracy=(true_positive + true_negative) / total,
        false_positive_rate=false_positive / negatives if negatives else 0,
        precision=true_positive / predicted_positive if predicted_positive else 0,
        recall=true_positive / positives if positives else 0,
    )


def calibration_metrics(
    expected: list[bool],
    scores: list[float],
    *,
    bin_count: int = 10,
) -> CalibrationMetrics:
    """Calculate Brier score and fixed-width ECE without third-party state.

    Empty bins are excluded from ECE/MCE. A score of exactly 1 belongs to the
    final bin, and every other score belongs to ``floor(score * bin_count)``.
    """

    if not expected or len(expected) != len(scores):
        raise ValueError("expected and scores must be non-empty and equal length")
    if not 1 <= bin_count <= 100:
        raise ValueError("bin_count must be between 1 and 100")
    if any(score < 0 or score > 1 for score in scores):
        raise ValueError("calibration scores must be between zero and one")

    total = len(expected)
    brier = sum(
        (score - (1.0 if label else 0.0)) ** 2
        for label, score in zip(expected, scores, strict=True)
    ) / total
    weighted_gap = 0.0
    maximum_gap = 0.0
    for bin_index in range(bin_count):
        members = [
            index
            for index, score in enumerate(scores)
            if min(int(score * bin_count), bin_count - 1) == bin_index
        ]
        if not members:
            continue
        average_score = sum(scores[index] for index in members) / len(members)
        positive_rate = sum(expected[index] for index in members) / len(members)
        gap = abs(average_score - positive_rate)
        weighted_gap += len(members) / total * gap
        maximum_gap = max(maximum_gap, gap)

    return CalibrationMetrics(
        sample_count=total,
        bin_count=bin_count,
        brier_score=brier,
        expected_calibration_error=weighted_gap,
        maximum_calibration_error=maximum_gap,
        mean_score=sum(scores) / total,
        empirical_positive_rate=sum(expected) / total,
    )
