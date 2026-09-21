"""Reproducibility tests for the frozen synthetic rights sanity benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_rightsgate_eval import run
from run_rightsgate_signal_eval import run as run_signal_evaluation
from run_rightsgate_consent_eval import run as run_consent_evaluation
from app.rightsgate.evaluation import calibration_metrics


def test_calibration_metrics_reject_invalid_inputs_and_bin_edges() -> None:
    metrics = calibration_metrics(
        [False, False, True, True],
        [0.0, 0.2, 0.8, 1.0],
        bin_count=5,
    )
    assert metrics.sample_count == 4
    assert metrics.brier_score == pytest.approx(0.02)
    assert metrics.expected_calibration_error == pytest.approx(0.1)
    assert metrics.maximum_calibration_error == 0.2


def test_frozen_rights_retrieval_sanity_metrics_are_reproducible() -> None:
    report = run()

    assert report.manifest_sha256 == "aeb0e306d9d1780066f706e9875b001fe4bbd8013dfc55ed71f326e2004c8077"
    assert report.registry_sha256 == "67f7e75cb5edfd8a15c45a622affd0b0feb934e64bf823afdae21b5cce62a112"
    assert len(report.cases) == 32
    assert report.exact_only.accuracy == 0.75
    assert report.exact_only.false_positive_rate == 0
    assert report.exact_only.recall == 0.5
    assert report.perceptual.accuracy == 1
    assert report.perceptual.false_positive_rate == 0
    assert report.perceptual.recall == 1
    assert any("not a representative" in item for item in report.limitations)

    summary_path = (
        Path(__file__).resolve().parents[2]
        / "competition"
        / "techgium10"
        / "evaluation"
        / "rights-retrieval-sanity-results-v1.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["manifest_sha256"] == report.manifest_sha256
    assert summary["registry_sha256"] == report.registry_sha256
    assert summary["exact_only"] == report.exact_only.model_dump(mode="json")
    assert summary["perceptual"] == report.perceptual.model_dump(mode="json")


def test_frozen_challenge_signal_sanity_metrics_are_reproducible() -> None:
    report = run_signal_evaluation()

    assert report.manifest_sha256 == "1c8a8fb19bbab8847f4d88c715b50f005aab6595ebdbd7c52084a37f4c7df698"
    assert report.registry_sha256 == "bc312ca043ccd31c68dd452cb5d8aca1263cd87d659febf868928bb35aeaaddc"
    assert len(report.cases) == 64
    assert all(case.correct for case in report.cases)
    assert report.visual_localization.accuracy == 1
    assert report.visual_localization.false_positive_rate == 0
    assert report.generative_metadata.accuracy == 1
    assert report.generative_metadata.false_positive_rate == 0
    assert report.partial_edit_subtype_accuracy == 1
    assert report.visual_localization_calibration.sample_count == 32
    assert report.visual_localization_calibration.brier_score < 0.001
    assert report.generative_metadata_calibration.sample_count == 32
    assert report.generative_metadata_calibration.brier_score == 0.028125000000000008
    assert report.standards_ablation.credentials_or_watermark_evidence_cases == 0
    assert report.standards_ablation.credentials_or_watermark_only.recall == 0
    assert report.standards_ablation.full_signal_pipeline.recall == 1
    assert report.standards_ablation.accuracy_lift == 0.5
    assert any("not a representative" in item for item in report.limitations)

    summary_path = (
        Path(__file__).resolve().parents[2]
        / "competition"
        / "techgium10"
        / "evaluation"
        / "challenge-signals-sanity-results-v1.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["manifest_sha256"] == report.manifest_sha256
    assert summary["registry_sha256"] == report.registry_sha256
    assert summary["visual_localization"] == report.visual_localization.model_dump(mode="json")
    assert summary["generative_metadata"] == report.generative_metadata.model_dump(mode="json")
    assert summary["visual_localization_calibration"] == (
        report.visual_localization_calibration.model_dump(mode="json")
    )
    assert summary["generative_metadata_calibration"] == (
        report.generative_metadata_calibration.model_dump(mode="json")
    )
    assert summary["standards_ablation"] == report.standards_ablation.model_dump(mode="json")


def test_frozen_watermark_and_consent_sanity_metrics_are_reproducible() -> None:
    report = run_consent_evaluation()

    assert report["manifest_sha256"] == (
        "17d944f5696aae28921256b7dd7164a397ead00a2ca640659d6fe6a4762443ae"
    )
    assert report["case_count"] == 96
    for lane in (
        "visible_watermark_tamper",
        "likeness_reference",
        "voice_reference",
        "consent_scope_conflict",
    ):
        assert report[lane]["accuracy"] == 1
        assert report[lane]["false_positive_rate"] == 0
        assert report[lane]["recall"] == 1
    assert "not a representative" in report["limitations"][0]

    summary_path = (
        Path(__file__).resolve().parents[2]
        / "competition"
        / "techgium10"
        / "evaluation"
        / "watermark-consent-sanity-results-v1.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary == report
