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

**Status:** IN PROGRESS — offline C2PA verification and conservative IPTC generative-source mapping are implemented with bounded unit/integration tests. Signed fixture, attack-matrix, trust-store and forensic-adapter work remains before exit.

- Verify C2PA credentials and bind them to the exact asset bytes.
- Inspect declared provenance metadata and supported invisible-watermark signals.
- Add pluggable image, video and audio forensic adapters.
- Localize partial-generation and manipulation evidence when supported.
- Keep `UNKNOWN` as a first-class outcome when evidence is insufficient.
- Test stripping, forgery, replay, recompression, crop, splice and detector-unavailable cases.

**Exit:** provenance results are calibrated, conflict-aware and attack-tested.

### Gate 3 — Build the rights lane

**Status:** IN PROGRESS — a versioned local image-reference registry, server-derived records, exact/perceptual candidate retrieval and deterministic licence status/date/territory/channel/intended-use evaluation are implemented. Consent, likeness, voice, localization, broader licence semantics and benchmark work remain before exit.

- Create a governed reference registry with works, logos, licences, consent and territory.
- Add perceptual and embedding-based candidate retrieval for image, video and audio.
- Add trademark/logo detection and policy-aware licence evaluation.
- Add likeness and voice comparison only against consented local references.
- Represent transformations and rights relationships in the Asset Exposure Graph.
- Test benign transformations, misleading near-matches, restricted licences and detector failure.

**Exit:** every rights flag has a candidate source, evidence pointer and review path.

### Gate 4 — Compile policy and control release

**Status:** IN PROGRESS — deterministic audience, brand-profile, channel, territory, provenance, rights and mandatory-component rules now produce evidence-cited `GO`/`REVIEW`/`BLOCK` assessments. Administered policy trust, human overrides, webhooks, adversarial release verification and signed authorization remain.

- Extend the versioned policy compiler for brand, regulatory, territory and intended-use rules.
- Produce deterministic `GO`, `REVIEW` or `BLOCK` outcomes with cited rules.
- Add human-review overrides with identity, reason and timestamp.
- Red-team the exact proposed release artifact and evidence package.
- Bind asset hash, policy, model versions, results and override state into signed proof.
- Provide idempotent assessment and webhook integration endpoints.

**Exit:** no media can receive `GO` without complete mandatory evidence and successful release checks.

### Gate 5 — Evaluate and demonstrate

**Status:** IN PROGRESS — a dedicated RightsGate review screen now runs the integrated image workflow and exposes all three dimensions, evidence, component health and commitments. A frozen 32-case synthetic rights-retrieval sanity set provides exact-only ablation metrics, but representative multi-dimension evaluation, CMS simulation and rehearsed demo cases remain.

- Build a legally sourced, versioned dataset and freeze train, validation and test families.
- Compare metadata-only, C2PA-only, watermark-only and individual-detector baselines.
- Report accuracy, false-positive rate, calibration, abstention and unauthorized-`GO` rate.
- Measure latency, reviewer effort and failure behavior.
- Build a review workflow and simulated CMS integration.
- Prepare a three-minute demo covering clean, ambiguous, infringing and tampered cases.

**Exit:** every public metric is reproducible from a signed evaluation manifest.

### Gate 6 — Competition freeze

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
