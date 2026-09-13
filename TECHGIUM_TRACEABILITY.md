# TECHgium Challenge Traceability

Target: **Safeguarding Content Rights in the Age of AI-Generated Media**

## Status vocabulary

- `INHERITED` — capability exists in the frozen VeilGraph foundation but has not yet been accepted against the RightsGate requirement.
- `PLANNED` — requirement and acceptance evidence are defined; implementation is not complete.
- `IMPLEMENTED` — code and automated tests exist.
- `VALIDATED` — frozen-set or adversarial evaluation evidence exists.
- `RELEASED` — included in a signed tagged release.
- `BLOCKED` — a recorded dependency prevents honest completion.

`INHERITED` is not the same as challenge acceptance. Rows advance only when linked tests and evidence exist.

| ID | Challenge requirement | Current status | Planned acceptance evidence |
|---|---|---|---|
| CONTRACT-01 | Versioned three-dimension assessment result | IMPLEMENTED | `backend/app/rightsgate/contracts.py`; strict schema and serialization tests |
| CONTRACT-02 | Evidence bound to exact asset, component and claim | IMPLEMENTED | Referential-integrity, version-binding and commitment tests |
| CONTRACT-03 | Explicit abstention and component-failure semantics | IMPLEMENTED | `UNKNOWN`/`NOT_ASSESSED` limitation and fail-closed tests |
| CONTRACT-04 | Asset Exposure Graph schema and topology validation | IMPLEMENTED | Node/edge identity, topology and evidence-reference tests |
| API-01 | Idempotent request contract | IMPLEMENTED | Canonical request fingerprint and deterministic HTTP validation tests |
| API-02 | Durable idempotent assessment execution | PLANNED | Persistent key/fingerprint conflict tests, replay tests and detector orchestration |
| ING-01 | Process images | INHERITED | Corpus ingestion and parser-safety tests |
| ING-02 | Process video | INHERITED | Full-timeline and audio-track tests |
| ING-03 | Process standalone audio | PLANNED | Decoder, canonicalization and malformed-file tests |
| PROV-01 | Verify content credentials/C2PA | IMPLEMENTED | Official offline SDK adapter and no-manifest/status-mapping tests; signed, mismatched, stripped and replayed fixtures remain for `VALIDATED` |
| PROV-02 | Assess wholly AI-generated media | PLANNED | Frozen multi-generator test split with calibration and FPR |
| PROV-03 | Assess partial generation or manipulation | PLANNED | Splice/inpaint/localization fixtures with region/timeline scoring |
| PROV-04 | Detect provenance metadata or watermark tampering | PLANNED | Removal, forgery, collision and transformation attack matrix |
| RIGHTS-01 | Identify copyrighted-work exposure | IMPLEMENTED | Versioned byte-bound registry and exact/perceptual image candidate tests; transformed-match frozen benchmark remains for `VALIDATED` |
| RIGHTS-02 | Identify trademark/logo exposure | PLANNED | Positive, hard-negative and obscured-mark benchmark |
| RIGHTS-03 | Evaluate licence constraints | PLANNED | Intended-use, territory, expiry and conflict test cases |
| RIGHTS-04 | Identify likeness exposure | PLANNED | Consented local gallery with threshold/FAR evidence |
| RIGHTS-05 | Identify voice exposure | PLANNED | Consented local voice set with transformation and FAR evidence |
| GRAPH-01 | Combine related evidence | INHERITED | Rights-specific graph schema, inference and conflict tests |
| POLICY-01 | Configurable brand policy | INHERITED | RightsGate rule schema and deterministic policy fixtures |
| POLICY-02 | Regulatory and regional policy | PLANNED | Territory and policy-version decision table tests |
| POLICY-03 | Clear `GO`/`REVIEW`/`BLOCK` outcome | INHERITED | Exact challenge outcome mapping and fail-closed tests |
| EVID-01 | Supporting evidence per dimension | INHERITED | Challenge evidence schema, byte binding and UI inspection |
| CONF-01 | Confidence per dimension | PLANNED | Calibration protocol, reliability plots and abstention tests |
| FLOW-01 | Integrate with an existing content workflow | PLANNED | Idempotent API, webhook and simulated CMS demonstration |
| EVAL-01 | Declare test set | PLANNED | Versioned manifest, licences, hashes and frozen family split |
| EVAL-02 | State accuracy and false-positive rate | PLANNED | Reproducible per-dimension evaluation report |
| EVAL-03 | Go beyond standards/watermarking | PLANNED | Baseline and ablation comparison against the full system |
| SEC-01 | Protect assets, references and audit evidence | INHERITED | Updated threat model, security tests and signed release proof |

## Release rule

Any mandatory row that remains `PLANNED`, lacks evidence or fails during assessment prevents an unqualified `GO`. The system returns `REVIEW` or `BLOCK` with the missing evidence named.
