# Governed Rights Reference Registry

## Implemented boundary

The first rights-retrieval adapter compares an input image with a versioned local registry. Every registry record binds a reference ID and source-record ID to the exact reference SHA-256 and a deterministic 64-bit difference hash. The registry itself has a canonical SHA-256 commitment and becomes the recorded component artifact for every query.

Matching uses two signals:

- exact asset SHA-256 equality;
- perceptual difference-hash Hamming distance under an explicit threshold.

Images are normalized for EXIF orientation and decoded under a configurable pixel budget. Evidence binds the candidate bytes, registry version, registry commitment, reference ID, threshold and distance. Raw reference media is not copied into result evidence.

## Claim boundary

This is candidate retrieval, not copyright or trademark adjudication.

| Observation | RightsGate result |
|---|---|
| Exact or thresholded perceptual match | `POTENTIAL_EXPOSURE`; licence and human review still required |
| No match in the configured registry | `UNKNOWN`; registry coverage is not rights clearance |
| Hash does not match supplied asset bytes | request rejected before matching |
| Decode or safety-budget failure | component `DEGRADED`, dimension `UNAVAILABLE`, fail closed |

A perceptual hash is intentionally a transparent baseline, not the final retrieval system. It creates reproducible evidence and a benchmark target for later embedding, crop-resistant and localized detectors.

## Licence evaluation

Retrieved candidates feed a separate, versioned licence registry. Each licence binds governed reference IDs to an explicit status, validity window, territory set, channel set and intended-use set. Evaluation is deterministic at an assessment timestamp. A candidate without complete coverage becomes `POLICY_CONFLICT`; a covered candidate retains its retrieval evidence but does not create global rights clearance because other works, marks, likenesses and voices may remain outside registry coverage.

The integrated workflow derives reference SHA-256 and dHash values server-side through `POST /api/v1/rightsgate/rights/references/image`, preventing the browser from approximating the registered evidence. Raw reference bytes are processed in memory and are not included in the assessment record.

## Evidence still required for `VALIDATED`

- legally sourced positive references and unrelated hard negatives;
- crop, resize, recompression, color, overlay and partial-copy transformations;
- precision/recall, false-positive rate and threshold calibration on a frozen split;
- logo/mark localization instead of whole-image matching;
- broader licence terms, consent and contractual conflict interpretation beyond the implemented date, state, intended-use, channel and territory checks;
- consented likeness and voice reference protocols;
- reviewer-effort and latency measurements.

Until these results are reproducible from a frozen manifest, the capability remains `IMPLEMENTED`, never `VALIDATED` or `RELEASED`.
