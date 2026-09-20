# RightsGate Trusted Media Execution

## Purpose

`POST /api/v1/rightsgate/assessments` accepts one PNG/JPEG, bounded MP4/MOV or bounded PCM/WAV deployment asset plus four strict JSON control documents as multipart fields:

- `request_json` — versioned `AssetIR`, deployment context and idempotency key;
- `rights_registry_json` — content-addressed image references;
- `licence_registry_json` — governed licence records;
- `policy_json` — deterministic publication policy;
- `max_hamming_distance` — bounded perceptual retrieval threshold.

Use `POST /api/v1/rightsgate/rights/references/image` to derive a reference record from real reference bytes. The browser workflow performs this step automatically.

## Execution order

```text
validate control schemas and cross-registry references
  -> bind SHA-256, size, media type, dimensions and/or duration to uploaded bytes
  -> compute request + registry + policy + threshold execution fingerprint
  -> atomically reserve/replay the idempotency key
  -> verify embedded C2PA credentials offline
  -> image: inspect bounded generator metadata and localized residual consistency
  -> video: change-screen every physical frame and deeply analyze selected/novel frames
  -> audio: decode and length-check the complete bounded PCM/WAV stream, then abstain on unavailable origin/voice lanes
  -> retrieve exact/perceptual governed visual candidates
  -> localize governed visual references with ORB/RANSAC geometry and image/video-frame coordinates
  -> evaluate licence status/date/territory/channel/intended use
  -> compile deterministic GO / REVIEW / BLOCK policy, including scoped regulatory rules
  -> build the Asset Exposure Graph
  -> persist and verify the assessment commitment
  -> create an Ed25519-signed, non-authorizing CMS decision receipt on request
  -> optionally authorize a short release window after a signed GO and two trusted role-separated reviewer attestations
```

The executor version and component versions are included in the execution fingerprint. Changing a registry, policy, threshold or component version prevents stale replay under the same key.

## Idempotency behavior

| Situation | Result |
|---|---|
| New key and inputs | reserve, execute and persist |
| Same key and identical governed inputs | return the exact stored assessment with `replayed: true` |
| Different key with equivalent governed inputs | create a distinct assessment sharing the same execution fingerprint |
| Same key but changed request, registry, policy or threshold | HTTP `409` conflict |
| Same key while a live lease owns execution | HTTP `409` with `Retry-After` |
| Expired lease after interruption | atomically recover, increment the fencing attempt and reject stale completion |
| Stored request/result commitment mismatch | HTTP `500`, fail closed |
| Prior stored execution failure | HTTP `409` with a bounded failure code |

`GET /api/v1/rightsgate/assessments/{idempotency_key}` returns durable status without any raw media bytes.

`POST /api/v1/rightsgate/integrations/cms/decision` binds a CMS content ID to the stored request, execution, asset and assessment commitments. Its deterministic Ed25519 receipt maps `BLOCK`, `REVIEW` and `GO` to `BLOCKED`, `HUMAN_REVIEW_REQUIRED` and `READY_FOR_RELEASE_AUTHORIZATION`. `POST /api/v1/rightsgate/integrations/cms/receipts/verify` verifies the receipt commitment, signer fingerprint and signature.

## Media-specific coverage

- **Image:** full current provenance, global/localized visual retrieval and licence lanes.
- **Video:** MP4/MOV limits are enforced, every physical frame is change-screened, and evidence plus materially novel frames enter the image lanes within a configured deep-analysis budget. Budget truncation degrades the timeline component. Embedded audio-track voice/acoustic rights are not assessed.
- **Audio:** RIFF/WAVE PCM structure, parameters, declared duration and full payload length are verified. C2PA is attempted on the original bytes, while origin, voice identity/consent and acoustic-work matching remain explicit abstentions.

## Release boundary

The integrated endpoint is trusted to execute registered code and persist evidence, but the public prototype accepts caller-supplied policy and registry documents. It therefore always returns:

```json
{"release_authorization": false}
```

Even a computed `GO` or valid CMS decision receipt is decision support only. `READY_FOR_RELEASE_AUTHORIZATION` means the separate administered endpoint may consider release; it is not itself permission to publish. Missing mandatory detectors remain explicit and normally force `REVIEW`; an unlicensed governed candidate can deterministically produce `BLOCK`.

The release endpoint is disabled unless `VEILGRAPH_RIGHTSGATE_REVIEWER_REGISTRY_PATH` points to a regular, non-symlink JSON file conforming to `veilgraph.rightsgate.reviewer-trust-registry.v1`. The registry must contain distinct active Ed25519 identities for both roles. Reviewer signatures bind their approval to the exact CMS receipt, assessment, asset, CMS system and content ID.

```text
POST /api/v1/rightsgate/integrations/cms/release-authorizations
POST /api/v1/rightsgate/integrations/cms/release-authorizations/verify
```

Authorization is permitted only for a valid locally signed `GO`, fresh approvals from distinct `RIGHTS_REVIEWER` and `RELEASE_MANAGER` identities, and the current exact reviewer-registry commitment. The default receipt expires after 15 minutes. Any block/review decision, stale approval, inactive/revoked identity, role mismatch, signature failure, registry rotation, receipt mutation or expiry returns no release authorization.
