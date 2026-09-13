# Evaluation Protocol

This protocol is pre-registered before headline evaluation. It is designed to prevent leakage, optimistic threshold tuning and unsupported claims.

## Dataset governance

Each asset record must contain:

- immutable asset ID and SHA-256 digest;
- lawful source, licence and permitted evaluation use;
- media type, codec/container and transformation lineage;
- provenance ground truth and evidence source;
- referenced work, mark, likeness, voice and licence identifiers when applicable;
- intended use, territory, channel and policy version;
- annotation method, annotator agreement and unresolved ambiguity;
- duplicate or transformation-family identifier.

Train, validation and test manifests are versioned and frozen before final scoring. Originals and every transformation from the same family remain in one split. Final thresholds are selected on validation data only.

## Scenario strata

The declared test set must include authentic and licensed media, public-domain media, fully generated media, local edits, compositing and inpainting, benign crop/re-encode/color/audio transforms, valid/invalid/stripped C2PA, watermark removal or forgery attempts, obscured logos, ambiguous near-matches, licence expiry and territory conflicts, and forced detector or dependency failure.

Results are reported per stratum as well as in aggregate.

## Metrics

### Provenance

- precision, recall, F1 and false-positive rate;
- AUROC only when score semantics make it valid;
- expected calibration error and Brier score;
- spatial or temporal localization IoU where ground truth exists;
- abstention rate and performance conditional on non-abstention.

### Rights exposure

- retrieval recall@K and precision@K for reference works;
- logo/trademark precision, recall and false-positive rate;
- likeness and voice true-accept rate at declared false-accept rates;
- licence-rule accuracy and error categories;
- percentage of flags with a resolvable evidence pointer.

### Deployment readiness

- `GO`/`REVIEW`/`BLOCK` confusion matrix;
- **unauthorized-`GO` rate** as the primary safety metric;
- unnecessary-review and unnecessary-block rates;
- policy citation accuracy and human override rate.

### System behavior

- end-to-end and per-lane latency by media duration/size;
- peak memory and evidence-storage overhead;
- reviewer decision time and disagreement;
- API idempotency, timeout and retry behavior;
- fail-closed behavior under mandatory detector failure.

All confidence intervals and sample counts accompany percentages.

## Baselines and ablations

Compare the full system against:

1. metadata-only checks;
2. C2PA-only verification;
3. watermark-only checks;
4. the best available individual forensic detector;
5. rights retrieval without graph or policy reasoning;
6. the full system without adversarial release verification;
7. the complete RightsGate pipeline.

This comparison is the evidence for the challenge requirement to go beyond standards and invisible watermarking.

## Frozen artifacts

A reported run must retain the dataset manifest, split hashes, code commit, dependency lock state, detector/model hashes, policy bundle, threshold file, raw predictions, metric output, hardware/runtime description and signed report digest. A number without these artifacts is exploratory, not a public result.
