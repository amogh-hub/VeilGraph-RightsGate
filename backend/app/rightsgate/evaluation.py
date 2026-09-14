"""Reproducible metrics for declared RightsGate evaluation manifests."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import SHA256_PATTERN, StrictFrozenModel

EVALUATION_REPORT_SCHEMA = "veilgraph.rightsgate.evaluation-report.v1"


class BinaryClassificationMetrics(StrictFrozenModel):
    true_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=1)
    false_positive_rate: float = Field(ge=0, le=1)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)


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
