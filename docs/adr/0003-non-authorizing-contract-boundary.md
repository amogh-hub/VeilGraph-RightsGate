# ADR 0003: Keep Contract Validation Separate from Release Authorization

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

Gate 1 must make integration and schema work testable before challenge-specific detectors exist. A validation endpoint could otherwise be mistaken for evidence that an assessment ran or for permission to publish an asset. Accepting caller-assembled evidence as trusted release authority would create a critical privilege-boundary flaw.

## Decision

Expose versioned JSON Schemas plus stateless request and result validation endpoints. Canonical SHA-256 fingerprints make replay/conflict semantics explicit for the later durable job API. Validation verifies structure, asset and component binding, graph references, abstention requirements and fail-closed `GO` invariants. It never starts an assessment and always returns `release_authorization: false` for caller-supplied results.

Only a future trusted orchestration boundary may execute registered detector adapters, compile policy, persist idempotency records and authorize release.

## Consequences

- Frontend and CMS integration can begin against stable contracts.
- Repeated equivalent inputs have a deterministic identity.
- Unfinished detectors cannot be presented as working capabilities.
- A structurally valid caller-supplied result cannot become a release capability.
- Gate 1 remains open until durable idempotency and trusted execution are implemented.
