# ADR 0002: Define Claims and Evidence Before Selecting Models

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

Provenance and rights tools produce heterogeneous scores, metadata and failure modes. Combining them directly into one opaque number would conceal contradictions, encourage overclaiming and make policy decisions impossible to audit.

## Decision

Define `ClaimRecord`, `EvidencePointer`, `DimensionAssessment`, `AssetIR` and `AssetExposureGraph` contracts before integrating detectors. Adapters translate tool output into these types. Conflicting evidence and abstention remain visible. Deterministic policy consumes the typed assessments and alone produces the deployment decision.

## Consequences

- Detector replacement does not change the external result contract.
- Evidence can be localized, versioned and tested independently.
- Missing capability remains explicit rather than becoming a false negative.
- Additional schema work precedes visually impressive model integration.
- Model outputs cannot authorize deployment.
