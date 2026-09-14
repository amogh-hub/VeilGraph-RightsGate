"""Reproducibility tests for the frozen synthetic rights sanity benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from run_rightsgate_eval import run


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
