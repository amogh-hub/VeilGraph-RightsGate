"""Offline invariants for the pinned external C2PA interoperability evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_rightsgate_c2pa_interop_eval import (
    DEFAULT_MANIFEST,
    _fixture_bytes,
    _load_manifest,
    _wilson_interval,
)

RESULTS = (
    Path(__file__).resolve().parents[2]
    / "competition"
    / "techgium10"
    / "evaluation"
    / "c2pa-interoperability-results-v1.json"
)


def test_pinned_fixture_manifest_and_checked_report_are_consistent() -> None:
    manifest, digest = _load_manifest(DEFAULT_MANIFEST)
    report = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert report["manifest_sha256"] == digest
    assert report["source_commit"] == manifest["source_commit"]
    assert report["case_count"] == len(manifest["cases"]) == 12
    assert report["tamper_scored_count"] == 11
    assert report["tamper_excluded_count"] == 1
    assert report["validation_correct"] == sum(
        case["validation_correct"] for case in report["cases"]
    )
    for case, result in zip(manifest["cases"], report["cases"], strict=True):
        assert result["case_id"] == case["case_id"]
        assert result["asset_sha256"] == case["sha256"]
        assert result["expected_validation"] == case["expected_validation"]
        assert result["expected_tamper"] == case["expected_tamper"]
        assert result["validation_correct"] == (
            result["predicted_validation"] == case["expected_validation"]
        )
    scored = [case for case in report["cases"] if case["expected_tamper"] is not None]
    assert report["tamper"]["true_positive"] == sum(
        case["expected_tamper"] and case["predicted_tamper"] for case in scored
    )
    assert report["tamper"]["true_negative"] == sum(
        not case["expected_tamper"] and not case["predicted_tamper"] for case in scored
    )
    assert report["tamper"]["false_positive"] == sum(
        not case["expected_tamper"] and case["predicted_tamper"] for case in scored
    )
    assert report["tamper"]["false_negative"] == sum(
        case["expected_tamper"] and not case["predicted_tamper"] for case in scored
    )


def test_fixture_hash_mismatch_stops_evaluation(tmp_path: Path) -> None:
    manifest, _ = _load_manifest(DEFAULT_MANIFEST)
    case = manifest["cases"][0]
    (tmp_path / case["case_id"]).write_bytes(b"not the pinned fixture")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _fixture_bytes(case, manifest, fixture_dir=tmp_path)


def test_wilson_interval_exposes_small_sample_uncertainty() -> None:
    assert _wilson_interval(0, 5) == pytest.approx([0.0, 0.43448246478317476])
    assert _wilson_interval(12, 12) == pytest.approx([0.7575059933447592, 1.0])
