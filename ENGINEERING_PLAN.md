# Engineering Plan

## Objective

Build a local-first pre-publication gateway that assesses media provenance, rights exposure and deployment readiness; returns per-dimension confidence with inspectable evidence; integrates through an API and review UI; and reports accuracy and false-positive rate on a declared test set. The final demonstration must show measurable value beyond credentials and invisible watermarking alone.

## Non-negotiable engineering principles

- Report only claims supported by versioned code and evidence.
- Keep provenance, rights exposure and deployment readiness as separate assessments.
- Treat credentials as positive or contradictory evidence, never as universal truth.
- Treat similarity as a review signal, never as a legal conclusion.
- Fail closed when required evidence or a mandatory detector is unavailable.
- Freeze datasets and evaluation logic before reporting headline metrics.
- Keep confidential assets and biometric references local by default.
- Prevent models and untrusted tool output from authorizing release or altering policy.

## Delivery gates

### Gate 0 — Isolate and reproduce the foundation

**Status:** COMPLETE — source push guard, baseline tags and local/GitHub CI evidence recorded.

- Preserve source history and prevent writes to the frozen VeilGraph repository.
- Reproduce backend tests, frontend typecheck and production build.
- Record toolchain versions and create the baseline tag.

**Exit:** clean reproducible baseline and zero changes to the source repository.

### Gate 1 — Contract the domain before adding models

**Status:** COMPLETE — versioned schemas, deterministic fingerprints, durable SQLite idempotency leases, replay/conflict/crash-recovery semantics, trusted image execution and contract/API tests are implemented.

- Define `AssetIR`, `ClaimRecord`, `EvidencePointer`, `DimensionAssessment` and `AssetExposureGraph` schemas.
- Define an idempotent assessment API and versioned result format.
- Preserve conflicting evidence and explicit abstentions.
- Add schema, serialization and compatibility tests.

**Exit:** detector-independent contracts accepted and tested.

### Gate 2 — Build the provenance lane

**Status:** IN PROGRESS — offline C2PA verification, conservative IPTC mapping, bounded generator-metadata inspection, localized non-attributive residual triage, video-frame adaptation and structural PCM/WAV processing are implemented. Signed fixtures, representative calibration, watermark attacks and audio-origin/voice models remain before exit.

- Verify C2PA credentials and bind them to the exact asset bytes.
- Inspect declared provenance metadata and supported invisible-watermark signals.
- Add pluggable image, video and audio forensic adapters.
- Localize partial-generation and manipulation evidence when supported.
- Keep `UNKNOWN` as a first-class outcome when evidence is insufficient.
- Test stripping, forgery, replay, recompression, crop, splice and detector-unavailable cases.

**Exit:** provenance results are calibrated, conflict-aware and attack-tested.

### Gate 3 — Build the rights lane

**Status:** IN PROGRESS — a versioned local image-reference registry, exact/perceptual retrieval, ORB/RANSAC region localization and deterministic licence status/date/territory/channel/intended-use evaluation are implemented. Consent, likeness, voice, open-world semantics and representative benchmark work remain before exit.

- Create a governed reference registry with works, logos, licences, consent and territory.
- Add perceptual and embedding-based candidate retrieval for image, video and audio.
- Add trademark/logo detection and policy-aware licence evaluation.
- Add likeness and voice comparison only against consented local references.
- Represent transformations and rights relationships in the Asset Exposure Graph.
- Test benign transformations, misleading near-matches, restricted licences and detector failure.

**Exit:** every rights flag has a candidate source, evidence pointer and review path.

### Gate 4 — Compile policy and control release

**Status:** IN PROGRESS — deterministic audience, brand-profile, channel, territory, scoped regulatory, provenance, rights and mandatory-component rules produce evidence-cited `GO`/`REVIEW`/`BLOCK`. Signed CMS decisions and a separate short-lived release authorization requiring distinct cryptographically trusted rights/release reviewers are implemented. Authenticated vendor delivery and operational reviewer provisioning remain.

- Extend the versioned policy compiler for brand, regulatory, territory and intended-use rules.
- Produce deterministic `GO`, `REVIEW` or `BLOCK` outcomes with cited rules.
- Add human-review overrides with identity, reason and timestamp.
- Red-team the exact proposed release artifact and evidence package.
- Bind asset hash, policy, model versions, results and override state into signed proof.
- Provide idempotent assessment and webhook integration endpoints.

**Exit:** no media can receive `GO` without complete mandatory evidence and successful release checks.

### Gate 5 — Evaluate and demonstrate

**Status:** IN PROGRESS — the RightsGate screen runs image, bounded MP4/MOV and PCM/WAV workflows, exposes all three dimensions and produces a signed CMS workflow receipt. Frozen 32-case retrieval and 64-case localization/metadata-signal sets provide bounded accuracy/FPR, calibration and standards-only ablation evidence, but representative multi-dimension evaluation and rehearsed demo cases remain.

- Build a legally sourced, versioned dataset and freeze train, validation and test families.
- Compare metadata-only, C2PA-only, watermark-only and individual-detector baselines.
- Report accuracy, false-positive rate, calibration, abstention and unauthorized-`GO` rate.
- Measure latency, reviewer effort and failure behavior.
- Extend the implemented review workflow and signed CMS contract with authenticated vendor delivery.
- Prepare a three-minute demo covering clean, ambiguous, infringing and tampered cases.

**Exit:** every public metric is reproducible from a signed evaluation manifest.

### Gate 6 — Competition freeze

**Status:** IN PROGRESS — sanitized package exclusions, an Ed25519-signed manifest envelope, pinned verification and adversarial package tests are implemented. The final public tag/release is not yet frozen.

- Close challenge traceability and threat-model gaps.
- Run dependency, secret and software-bill-of-materials checks.
- Freeze the demo dataset and failure-safe offline path.
- Produce a signed release manifest, claims sheet and rollback package.
- Rehearse judge questions against evidence, not unsupported statements.

**Exit:** tagged demo release with reproducible evidence and no critical open risk.

## Critical path

```text
schemas
  -> provenance evidence
  -> rights evidence
  -> graph reasoning
  -> policy decision
  -> adversarial release checks
  -> frozen benchmark
  -> integrated demo
```

Visual polish and additional detectors are valuable only after this path is defensible.
