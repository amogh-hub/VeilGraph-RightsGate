# RightsGate Threat Model

## Protected assets

- confidential pre-publication media and extracted features;
- provenance, licence, consent and policy records;
- biometric reference galleries;
- benchmark and reference-corpus integrity;
- detector, model, policy and threshold versions;
- evidence, audit history, reviewer identity and release proof.

## Trust boundaries

Uploaded media, filenames, metadata, C2PA assertions, embedded text/OCR, external reference records, webhooks and all model or tool outputs are untrusted inputs. They may supply evidence but may never change the assessment goal, select privileged tools, alter policy, authorize release or sign proof.

Release authority belongs only to administered deterministic policy and verification code operating on validated schemas. The current public executor accepts caller-supplied policy and registry documents, so its receipts are deliberately non-authorizing even when the computed decision is `GO`.

## Adversaries

- a publisher attempting to bypass rights controls;
- an external party forging or stripping provenance;
- a malicious asset designed to exploit parsers or models;
- a poisoned reference or benchmark contributor;
- an insider substituting policy, thresholds or evidence;
- an unauthorized user attempting biometric search or data extraction.

## Required attack coverage

| Attack | Required control or test |
|---|---|
| Strip, forge or replay credentials/watermarks | Cryptographic byte binding, trust-chain validation, contradiction reporting and replay fixtures |
| Crop, resize, re-encode, recolor or alter audio | Transformation-resilient retrieval with hard-negative testing |
| Splice, inpaint or partially generate content | Region/timeline evidence and explicit localization uncertainty |
| Obscure or distort marks | Multi-scale detection and false-positive controls |
| Parser bombs and malformed media | Size/time/resource limits, sandbox boundaries and fail-closed parsing |
| Prompt injection in metadata or OCR | Treat content as data; no media text can change tools, policy or permissions |
| Detector crash, timeout or missing model | Typed unavailability evidence and `REVIEW`/`BLOCK`, never silent success |
| Replay, duplicate callback or race | Idempotency keys, immutable assessment IDs and state-transition tests |
| Policy or threshold substitution | Version pinning, signatures/hashes and authorization checks |
| Biometric misuse | Consented local registry, scoped access, audit and deletion controls |
| Evidence tampering | Asset/result binding, append-only audit commitments and signed proof |

## Security invariants

1. Every result is cryptographically bound to the exact input, policy and component versions.
2. Missing or unavailable mandatory evidence cannot produce `GO`.
3. Untrusted content and model output cannot alter permissions, tools, policy or release authority.
4. Assessment and release are separate, idempotent state transitions.
5. Likeness and voice comparison uses only an explicitly consented, locally governed registry.
6. Cache entries are invalidated when the asset, policy, threshold, detector or reference corpus changes.
7. Overrides record reviewer identity, reason, prior result and timestamp.
8. Retention and deletion apply to source media, features, references, logs and derived evidence.

## Implemented execution controls

- exact asset SHA-256, byte length, detected media type and decoded dimensions are checked before work is reserved;
- rights, licence and policy registries have canonical commitments included in the execution fingerprint;
- SQLite `BEGIN IMMEDIATE` reservations provide cross-process serialization with bounded recovery leases;
- changed thresholds, policy or registry inputs conflict under a reused idempotency key;
- completed assessment JSON is revalidated and recomputed against its stored commitment on replay;
- raw assessment and reference media is processed in memory and is not stored in the RightsGate assessment table;
- caller-supplied governance documents can produce decision support but always return `release_authorization: false`.
- CMS decision receipts bind content, asset, request, execution and assessment commitments; Ed25519 verification detects payload, key or signature substitution, while the receipt remains explicitly non-authorizing.

## Non-goals

RightsGate does not guarantee detection of every generator or transformation, establish copyright ownership, make infringement findings, search arbitrary people, or turn absent provenance metadata into evidence of human authorship.
