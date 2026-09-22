# VeilGraph RightsGate v0.6.1 — demo-path acceptance

This update keeps the original VeilGraph repository untouched and advances only the separate RightsGate product.

## What changed

- Fixed a UI/API contract mismatch: an assessment may now declare an empty governed image-reference registry, as the review screen already permits. This is **not** rights clearance. The rights dimension remains `UNKNOWN`, and the publication decision remains non-authorizing `REVIEW` when rights evidence is absent.
- Added an automated acceptance test using the self-generated synthetic judge assets. It sends the asset and governed inputs through the actual assessment API, then creates and verifies the signed CMS decision receipt. It covers a licensed candidate (`REVIEW`), no reference (`UNKNOWN`/`REVIEW`), an unlicensed governed match (`BLOCK`), and an altered enrolled visible watermark (`TAMPERED`/`BLOCK`).
- The test does not introduce new model, detector or real-world accuracy claims. The 192-case synthetic and selected 12-JPEG official C2PA results remain as stated in the v0.6.0 evaluation reports.

## Reproduce

After `./scripts/setup_once.sh`, run:

```bash
cd backend
PYTHONPATH=. python -m pytest tests/test_rightsgate_judge_acceptance.py -q
```

## Remaining boundaries

This is a local workflow acceptance test, not a browser-based portal rehearsal or a production CMS integration. Representative rights/AI-media evaluation, vendor CMS authentication, and submission on the TECHgium portal still require separate work. No judge outcome can be guaranteed.
