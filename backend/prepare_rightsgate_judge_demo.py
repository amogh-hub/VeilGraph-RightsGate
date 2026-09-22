"""Prepare a self-checked RightsGate UI demo from synthetic and optional official media.

No demo assets are checked into the repository. The caller chooses a new output
directory; official C2PA fixtures are fetched only with --fetch-c2pa.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from app.rightsgate import AssessmentContext, ProvenanceVerdict
from app.rightsgate.provenance import (
    VisibleWatermarkRegistry,
    build_visible_watermark_profile,
    verify_c2pa,
    verify_visible_watermarks,
)
from app.rightsgate.rights import (
    ReferenceKind,
    RightsReferenceRegistry,
    build_registry_image,
    match_reference_image,
)
from run_rightsgate_c2pa_interop_eval import DEFAULT_MANIFEST, _fixture_bytes, _load_manifest

OFFICIAL_DEMO_CASES = (
    "adobe-20220124-C.jpg",
    "adobe-20220124-E-uri-CA.jpg",
    "adobe-20220124-A.jpg",
)
WATERMARK_BBOX = (0.75, 0.75, 1.0, 1.0)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _synthetic_assets() -> tuple[bytes, bytes, bytes]:
    image = Image.new("RGB", (512, 320), (239, 239, 239))
    draw = ImageDraw.Draw(image)
    for index in range(24):
        x = (index * 73 + 17) % 380
        y = (index * 41 + 13) % 225
        draw.rectangle(
            (x, y, x + 20 + index % 5 * 5, y + 14 + index % 4 * 4),
            fill=((index * 29) % 220, (index * 53) % 220, (index * 71) % 220),
            outline=(20, 30, 50),
            width=2,
        )
    draw.text((22, 270), "SYNTHETIC CAMPAIGN - GOVERNED DEMO", fill=(10, 20, 40))
    for index in range(16):
        x = 384 + index * 8
        draw.rectangle(
            (x, 240, x + 7, 319),
            fill=(10, 40, 110) if index % 2 else (240, 200, 35),
        )
    draw.text((422, 271), "VG", fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    template = image.crop((384, 240, 512, 320))
    altered = image.copy()
    ImageDraw.Draw(altered).rectangle((384, 240, 511, 319), fill=(239, 239, 239))
    return _png(image), _png(altered), _png(template)


def build_demo(output_dir: Path, *, fetch_c2pa: bool = False) -> dict[str, object]:
    """Create a fresh demo package and assert its expected bounded signals."""

    if output_dir.exists():
        raise FileExistsError(f"demo output directory already exists: {output_dir}")
    intact, altered, template = _synthetic_assets()
    profile = build_visible_watermark_profile(
        profile_id="watermark.synthetic-campaign-v1",
        source_record_id="brand-record.synthetic-v1",
        brand_profiles=("default",),
        normalized_bbox=WATERMARK_BBOX,
        template_data=template,
        max_hamming_distance=6,
    )
    watermark_registry = VisibleWatermarkRegistry(
        registry_id="registry.synthetic-demo-watermarks",
        version="1",
        profiles=(profile,),
    )
    context = AssessmentContext(
        policy_id="policy.techgium-demo",
        policy_version="2026.09.1",
        intended_use="Public advertising campaign",
        channel="web",
        audience="general",
        territories=("IN",),
        brand_profile="default",
    )
    intact_result = verify_visible_watermarks(
        intact,
        asset_sha256=hashlib.sha256(intact).hexdigest(),
        context=context,
        registry=watermark_registry,
    )
    altered_result = verify_visible_watermarks(
        altered,
        asset_sha256=hashlib.sha256(altered).hexdigest(),
        context=context,
        registry=watermark_registry,
    )
    if intact_result.assessment.verdict == ProvenanceVerdict.TAMPERED:
        raise RuntimeError("intact synthetic fixture failed watermark verification")
    if altered_result.assessment.verdict != ProvenanceVerdict.TAMPERED:
        raise RuntimeError("altered synthetic fixture did not trigger watermark verification")
    rights_registry = RightsReferenceRegistry(
        registry_id="registry.synthetic-demo-rights",
        version="1",
        references=(
            build_registry_image(
                reference_id="reference.synthetic-campaign-v1",
                kind=ReferenceKind.COPYRIGHTED_WORK,
                title="Synthetic campaign reference",
                rights_holder="Synthetic demo rights holder",
                data=intact,
                media_type="image/png",
                source_record_id="rights-record.synthetic-campaign-v1",
            ),
        ),
    )
    match = match_reference_image(
        intact,
        asset_sha256=hashlib.sha256(intact).hexdigest(),
        registry=rights_registry,
    )
    if not any(
        item.attributes.get("reference_id") == "reference.synthetic-campaign-v1"
        for item in match.evidence
    ):
        raise RuntimeError("synthetic governed reference did not match")

    files: dict[str, bytes] = {
        "synthetic-campaign-reference.png": intact,
        "synthetic-campaign-intact.png": intact,
        "synthetic-campaign-watermark-altered.png": altered,
        "synthetic-watermark-template.png": template,
        "synthetic-watermark-registry.json": (
            json.dumps(watermark_registry.model_dump(mode="json", by_alias=True), indent=2)
            + "\n"
        ).encode("utf-8"),
    }
    if fetch_c2pa:
        manifest, _ = _load_manifest(DEFAULT_MANIFEST)
        cases = {case["case_id"]: case for case in manifest["cases"]}
        for name in OFFICIAL_DEMO_CASES:
            data = _fixture_bytes(cases[name], manifest, fixture_dir=None)
            result = verify_c2pa(data, "image/jpeg", cases[name]["sha256"])
            if name.endswith("-C.jpg") and (
                not result.evidence
                or result.evidence[0].attributes.get("validation_state") != "Valid"
            ):
                raise RuntimeError("official C2PA valid fixture did not validate")
            if name.endswith("-E-uri-CA.jpg") and (
                result.assessment.verdict != ProvenanceVerdict.TAMPERED
            ):
                raise RuntimeError("official C2PA URI-tamper fixture did not flag")
            if name.endswith("-A.jpg") and result.evidence:
                raise RuntimeError("official no-credential fixture unexpectedly has a manifest")
            files[f"official-c2pa-{name}"] = data

    guide = (
        "RightsGate judge demo — generated outside the repository\n\n"
        "1. Start the backend and frontend. Open the RightsGate review UI.\n"
        "2. Upload synthetic-campaign-intact.png as asset and "
        "synthetic-campaign-reference.png as governed reference. With the valid licence "
        "toggle on, expect REVIEW because C2PA/AI attribution remains unknown.\n"
        "3. Turn the valid licence toggle off and reassess the same governed reference. "
        "Expect BLOCK with a licence-coverage policy citation.\n"
        "4. Upload synthetic-campaign-watermark-altered.png, then select "
        "synthetic-watermark-registry.json. Expect provenance TAMPERED and BLOCK. "
        "The watermark template is an enrolled visible region, not an invisible-watermark detector.\n"
        "5. If official C2PA files were fetched, inspect the C (structurally valid but "
        "untrusted test signer), E-uri (assertion-URI hash mismatch), and A (no credential) "
        "files. They are external C2PA interoperability fixtures under CC BY-SA 4.0; "
        "see https://github.com/c2pa-org/public-testfiles.\n\n"
        "All generated campaign media is synthetic. No case proves general rights clearance, "
        "AI authorship, signer trust, or real-world detector accuracy.\n"
    )
    files["DEMO_GUIDE.txt"] = guide.encode("utf-8")
    report = {
        "schema": "veilgraph.rightsgate.judge-demo-manifest.v1",
        "synthetic_watermark_intact": intact_result.assessment.verdict.value,
        "synthetic_watermark_altered": altered_result.assessment.verdict.value,
        "synthetic_reference_match": True,
        "official_c2pa_included": fetch_c2pa,
        "files_sha256": {
            name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())
        },
    }
    output_dir.mkdir(parents=True)
    for name, data in files.items():
        (output_dir / name).write_bytes(data)
    (output_dir / "DEMO_MANIFEST.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fetch-c2pa", action="store_true")
    args = parser.parse_args()
    report = build_demo(args.output_dir, fetch_c2pa=args.fetch_c2pa)
    print(json.dumps({"output_dir": str(args.output_dir), **report}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
