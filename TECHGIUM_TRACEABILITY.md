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
| API-02 | Durable idempotent assessment execution | IMPLEMENTED | Atomic SQLite leases, exact replay, conflict, expiry recovery and stored-commitment integrity tests |
| API-03 | Derive governed image-reference records | IMPLEMENTED | Server-side hash/dHash derivation, upload validation and HTTP tests |
| ING-01 | Process images | IMPLEMENTED | Exact hash/size/type/dimension binding and parser-safety tests in trusted execution |
| ING-02 | Process video | IMPLEMENTED | MP4/MOV byte/dimension/duration binding, every-physical-frame change screen, bounded selected-frame deep analysis, temporal/region evidence rebinding and automated execution test; audio-track rights analysis remains unavailable |
| ING-03 | Process standalone audio | IMPLEMENTED | Bounded PCM/WAV header and complete-payload decoding, byte/duration binding, malformed/truncated rejection and governed acoustic-reference consent matching |
| PROV-01 | Verify content credentials/C2PA | VALIDATED | Official offline SDK adapter plus a pinned, hash-verified 12-JPEG C2PA interoperability slice: 12/12 absent/valid/invalid classifications and 6 TP, 5 TN, 0 FP, 0 FN on adjudicable tamper labels; selected test certificates are untrusted and a representative/replayed-credential benchmark remains |
| PROV-02 | Assess wholly AI-generated media | IMPLEMENTED | C2PA and bounded self-declared generator-metadata evidence with synthetic sanity metrics; open-world visual attribution still requires a frozen multi-generator split |
| PROV-03 | Assess partial generation or manipulation | IMPLEMENTED | Partial-edit declarations and localized non-attributive residual evidence are tested; representative splice/inpaint localization remains for `VALIDATED` |
| PROV-04 | Detect provenance metadata or watermark tampering | VALIDATED | C2PA mismatch handling plus governed visible-watermark region verification; frozen 32-case inversion sanity lane reports accuracy `1.00`/FPR `0.00`; arbitrary invisible families remain out of scope |
| RIGHTS-01 | Identify copyrighted-work exposure | IMPLEMENTED | Versioned byte-bound registry and exact/perceptual image candidate tests; transformed-match frozen benchmark remains for `VALIDATED` |
| RIGHTS-02 | Identify trademark/logo exposure | IMPLEMENTED | Governed ORB/RANSAC region localization with byte-bound evidence and a frozen synthetic sanity set; open-world and obscured-mark benchmarks remain |
| RIGHTS-03 | Evaluate licence constraints | IMPLEMENTED | Status, intended-use, channel, territory, validity-window, conflict and registry-integrity tests |
| RIGHTS-04 | Identify likeness exposure | VALIDATED | Governed enrolled-image registry, scoped consent evaluation, block-on-conflict orchestration and frozen 32-case synthetic reference lane; not face recognition |
| RIGHTS-05 | Identify voice exposure | VALIDATED | Bounded PCM/WAV acoustic fingerprint, scoped consent evaluation and frozen 32-case gain/phase/frequency sanity lane; not speaker identification |
| GRAPH-01 | Combine related evidence | IMPLEMENTED | Asset, work/mark, person/voice, licence, consent, campaign and territory nodes with evidence-bound edge tests |
| POLICY-01 | Configurable brand/channel/audience policy | IMPLEMENTED | Versioned schema and deterministic mismatch fixtures |
| POLICY-02 | Regional territory policy | IMPLEMENTED | Territory allow-list and policy-version identity tests |
| POLICY-03 | Clear `GO`/`REVIEW`/`BLOCK` outcome | IMPLEMENTED | Exact deterministic mapping, missing-component abstention and contract fail-closed tests |
| POLICY-04 | Regulatory policy packs | IMPLEMENTED | Versioned context/verdict-scoped `REVIEW`/`BLOCK` rule engine and deterministic tests; curated legal rule content remains governed external input |
| EVID-01 | Supporting evidence per dimension | IMPLEMENTED | Challenge evidence schema, byte binding, graph references and review UI inspection |
| CONF-01 | Confidence per dimension | VALIDATED | Frozen synthetic Brier score, fixed-bin ECE/MCE and score-boundary tests exist for localization and generator-metadata lanes; representative calibration remains |
| FLOW-00 | Integrated RightsGate review UI | IMPLEMENTED | Image/reference intake and three-dimension evidence/decision workflow |
| FLOW-01 | Integrate with an existing CMS workflow | IMPLEMENTED | UI-consumed CMS decision schemas, immutable-assessment binding, Ed25519 receipt verification, and a separate short-lived dual-control release boundary with pinned reviewer roles/keys; vendor webhook delivery remains |
| EVAL-00 | Reproducible component sanity evaluation | VALIDATED | Frozen 32-case retrieval, 64-case challenge-signal and 96-case watermark/consent manifests, byte hashes, ablations and checked-in bounded results |
| EVAL-01 | Declare test set | IMPLEMENTED | Three versioned frozen synthetic manifests with 192 byte-fingerprinted cases exist; representative legally sourced family splits remain |
| EVAL-02 | State accuracy and false-positive rate | VALIDATED | Bounded synthetic accuracy/FPR for retrieval, localization, metadata markers, visible-watermark integrity, enrolled likeness/voice and consent scope; no challenge-wide or real-world metric claim |
| EVAL-03 | Go beyond standards/watermarking | VALIDATED | Frozen 64-case synthetic all-abstain credentials/watermark-only baseline versus full signal pipeline; representative credential/watermark attack ablation remains |
| SEC-01 | Protect assets, references and audit evidence | RELEASED | Version `v0.6.1-rightsgate-techgium`: updated threat model, secret/runtime exclusions, signed sanitized release envelope, pinned signer verification, release-tampering tests and public release artifact |

## Release rule

Any mandatory row that remains `PLANNED`, lacks evidence or fails during assessment prevents an unqualified `GO`. The system returns `REVIEW` or `BLOCK` with the missing evidence named.
