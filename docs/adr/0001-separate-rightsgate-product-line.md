# ADR 0001: Create a Separate RightsGate Product Line

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

VeilGraph is a frozen, public SIH system with a recorded regression baseline. TECHgium requires new provenance, rights-exposure, policy and evaluation capabilities. Adding speculative challenge work to the source repository would weaken its freeze and make lineage and claims harder to audit.

## Decision

Develop VeilGraph RightsGate in a separate public repository while preserving VeilGraph commit history. Keep the source repository as a fetch-only `upstream`; use a separate `origin` for RightsGate. Tag the imported source commit and record all challenge requirements in traceability.

## Consequences

- The original VeilGraph repository remains unchanged.
- Shared history makes inherited code and new work distinguishable.
- RightsGate can adopt its own release cadence, threat model and benchmark.
- Upstream improvements require deliberate review rather than automatic merging.
- Public language must distinguish inherited, implemented and validated capabilities.
