# RightsGate Trusted Image Execution

## Purpose

`POST /api/v1/rightsgate/assessments` is the first integrated challenge workflow. It accepts one PNG/JPEG deployment asset plus four strict JSON control documents as multipart fields:

- `request_json` — versioned `AssetIR`, deployment context and idempotency key;
- `rights_registry_json` — content-addressed image references;
- `licence_registry_json` — governed licence records;
- `policy_json` — deterministic publication policy;
- `max_hamming_distance` — bounded perceptual retrieval threshold.

Use `POST /api/v1/rightsgate/rights/references/image` to derive a reference record from real reference bytes. The browser workflow performs this step automatically.

## Execution order

```text
validate control schemas and cross-registry references
  -> bind SHA-256, size, media type and dimensions to uploaded bytes
  -> compute request + registry + policy + threshold execution fingerprint
  -> atomically reserve/replay the idempotency key
  -> verify embedded C2PA credentials offline
  -> retrieve exact/perceptual governed image candidates
  -> evaluate licence status/date/territory/channel/intended use
  -> declare required but missing components unavailable
  -> compile deterministic GO / REVIEW / BLOCK policy
  -> build the Asset Exposure Graph
  -> persist and verify the assessment commitment
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

## Release boundary

The integrated endpoint is trusted to execute registered code and persist evidence, but the public prototype accepts caller-supplied policy and registry documents. It therefore always returns:

```json
{"release_authorization": false}
```

Even a computed `GO` is decision support only. Production publication authorization requires authenticated, administrator-approved policy/registry versions, adversarial release verification and signed proof. Missing mandatory detectors remain explicit and normally force `REVIEW`; an unlicensed governed candidate can deterministically produce `BLOCK`.
