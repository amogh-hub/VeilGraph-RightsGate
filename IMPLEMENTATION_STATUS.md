# RightsGate Implementation Status

Status snapshot: **2026-09-21**

This document is the authoritative, claim-bounded record of the current TECHgium implementation. It distinguishes code that exists from capabilities that have been benchmark-validated or released as a complete competition prototype.

## Current requirement matrix

| Requirement | Current status |
|---|---|
| Versioned three-dimension result format | ✅ Implemented |
| Evidence pointers and confidence fields | ✅ Implemented |
| Fail-closed `GO / REVIEW / BLOCK` rules | ✅ Implemented in contracts and the trusted image executor |
| C2PA credential verification | 🟡 Implemented, not benchmark-validated |
| Declared whole/partial AI generation | 🟡 Detected through valid C2PA declarations or recognized self-declared generator metadata; stripped/forged metadata remains unresolved |
| Independent AI-media forensic detection | 🟡 Deterministic metadata and localized residual triage implemented for images; not a calibrated universal generator classifier |
| Metadata/watermark tampering | 🟡 C2PA cryptographic mismatch, residual anomaly evidence and governed visible-watermark region integrity checks are implemented; arbitrary/vendor invisible-watermark families remain unsupported |
| Copyrighted-image candidate matching | 🟡 Exact/perceptual local-registry baseline implemented; results are candidates, not legal conclusions or clearance |
| Trademark/logo localization | 🟡 Governed local ORB/RANSAC reference localization implemented with region evidence; open-world semantic detection is not implemented |
| Licence validity and restrictions | 🟡 Status, validity window, territory, channel and intended-use checks implemented for governed image candidates; broader contract semantics missing |
| Likeness detection | 🟡 Governed enrolled-image candidate matching plus context-scoped consent validation is implemented; this is not open-world face recognition |
| Voice detection | 🟡 Governed PCM/WAV acoustic-reference matching plus context-scoped consent validation is implemented; this is not speaker identification or acoustic-work recognition |
| Brand/regulatory/regional policy execution | 🟡 Audience, brand-profile, channel, territory and scoped `REVIEW`/`BLOCK` regulatory rules implemented; curated jurisdiction-specific packs missing |
| End-to-end three-dimension orchestration | ✅ Implemented with durable idempotency for images, bounded video and PCM/WAV, including optional watermark and consent registries with explicit abstention |
| RightsGate review UI/CMS integration | 🟡 Dedicated review UI, signed non-authorizing CMS decision contract, and short-lived dual-control release authorization implemented; authenticated vendor webhook delivery remains missing |
| Image, video and audio coverage | 🟡 Image is the strongest lane; bounded MP4/MOV full-timeline change screening and standalone PCM/WAV voice-reference matching are implemented, while video audio-track and open-world acoustic-work detection remain incomplete |
| Declared frozen test set | 🟡 Frozen 32-case retrieval, 64-case localization/metadata and 96-case watermark/consent manifests are byte-fingerprinted; representative legally sourced real-world sets are missing |
| Accuracy and false-positive rates | 🟡 Reproducible synthetic metrics report accuracy/FPR for seven bounded lanes; challenge-wide or real-world accuracy/FPR cannot be claimed |
| Confidence calibration | 🟡 Brier score, fixed-bin ECE and MCE are reproducible on the frozen synthetic signal set; representative calibration is missing |
| Comparison against C2PA/watermark-only baselines | 🟡 A frozen credentials/watermark-only all-abstain ablation is implemented for fixtures containing no such evidence; a representative attack set is missing |
| Signed competition release and demo | 🟡 Version `v0.5.0-rightsgate-techgium` is frozen as a sanitized Ed25519-signed archive with pinned verification; final portal-specific demo rehearsal/recording remains |

## What is locked in

- The original [`amogh-hub/VeilGraph`](https://github.com/amogh-hub/VeilGraph) repository is an unchanged upstream baseline and has no push URL in this checkout.
- RightsGate has strict versioned assessment, evidence, claim, graph and decision contracts with automated invariant tests.
- The C2PA adapter uses the official CAI SDK in local-only mode and fails closed when verification is unavailable or inconclusive.
- The image rights-reference adapter provides governed, content-addressed exact and perceptual candidate retrieval and never converts absence of a match into rights clearance.
- The independent image triage lane recognizes bounded generator metadata and produces localized high-pass residual anomalies without treating them as universal AI attribution. Missing markers remain `UNKNOWN`.
- Governed reference records include bounded ORB features. RANSAC geometric verification can localize a reference inside a larger image and emits a region evidence pointer; no-match still is not clearance.
- Governed visible-watermark profiles bind an expected template, brand context, normalized region and threshold. A mismatch becomes tampering evidence; an intact configured region never proves general authenticity or covers invisible watermark families.
- Governed consent registries bind enrolled likeness/acoustic references to source records, subjects, validity windows, territories, channels and intended uses. Matching is local and bounded; similarity cannot create consent, and an uncovered enrolled match blocks under policy.
- The image executor binds exact asset bytes, both governed registry commitments, policy, retrieval threshold and executor version; it persists idempotent results under recoverable leases and verifies stored commitments on read.
- Licence evaluation covers explicit status, date, territory, channel and intended use. The policy compiler makes evidence-cited decisions while preserving unavailable mandatory detectors.
- The RightsGate review screen runs this integrated workflow and displays all three dimensions, evidence, component health and policy citations.
- The policy supports deterministic, context-scoped regulatory `REVIEW` and `BLOCK` rules. The UI converts immutable results into deterministic Ed25519-signed CMS workflow receipts; every receipt retains `release_authorization: false`.
- A separate release boundary accepts only a signed CMS `GO`, then requires fresh Ed25519 approvals from distinct trusted `RIGHTS_REVIEWER` and `RELEASE_MANAGER` identities. It binds the asset, assessment, CMS content, trust-registry commitment and approval commitments into a short-lived signed authorization; expiry, revocation, role substitution and tampering fail closed.
- MP4/MOV execution reuses VeilGraph's every-physical-frame change screen, then runs image forensics, retrieval and localization over security-selected frames within an explicit budget. PCM/WAV execution verifies the complete payload and can compare a bounded acoustic fingerprint with enrolled consent references while abstaining on speaker identity and acoustic-work clearance.
- Frozen 32-case retrieval and 64-case signal manifests record every generated byte hash. Synthetic localization and metadata-signal lanes each reproduce 16 TP, 16 TN, 0 FP and 0 FN under an explicit non-generalization boundary.
- The 64-case report now includes confidence calibration (Brier/ECE/MCE) and a standards/watermark-only ablation. The full bounded signal pipeline has accuracy `1.00` versus `0.50` for the all-abstain baseline, but this is synthetic evidence only.
- A separate 96-case synthetic manifest reproduces 16 TP, 16 TN, 0 FP and 0 FN independently for governed visible-watermark tampering, enrolled-likeness retrieval and enrolled-voice retrieval, plus consent-scope conflict evaluation. These deliberately narrow results cannot be generalized to real people, voices or watermark families.
- The release candidate passed the 375-test backend suite, Python and npm dependency audits, frontend type checking and frontend production build locally; the tagged commit is released only after the same GitHub CI gates pass.

## Claim boundary

This snapshot is a **validated engineering foundation with multimodal orchestration, C2PA, conservative forensic triage, governed visible-watermark verification, global/localized rights retrieval, bounded enrolled likeness/voice consent controls, scoped licence evaluation, deterministic policy, review UI, signed CMS decisions and cryptographic dual-control release authorization**. It must not be represented as having real-world benchmark accuracy, open-world biometric/AI attribution, arbitrary invisible-watermark coverage or legal rights clearance.

The detailed evidence-to-requirement map remains in [`TECHGIUM_TRACEABILITY.md`](TECHGIUM_TRACEABILITY.md), and remaining implementation gates remain in [`ENGINEERING_PLAN.md`](ENGINEERING_PLAN.md).
