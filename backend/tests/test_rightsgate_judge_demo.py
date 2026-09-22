"""Judge-demo fixture package must stay deterministic and self-checking."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from prepare_rightsgate_judge_demo import build_demo


def test_judge_demo_builds_fresh_hash_bound_synthetic_assets(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    report = build_demo(output)
    assert report["synthetic_reference_match"] is True
    assert report["synthetic_watermark_altered"] == "TAMPERED"
    assert report["official_c2pa_included"] is False
    stored = json.loads((output / "DEMO_MANIFEST.json").read_text(encoding="utf-8"))
    assert stored == report
    for name, expected_hash in report["files_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected_hash
    with pytest.raises(FileExistsError):
        build_demo(output)
