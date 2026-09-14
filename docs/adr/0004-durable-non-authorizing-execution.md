# ADR 0004: Durable, Non-Authorizing RightsGate Execution

- **Status:** Accepted
- **Date:** 2026-09-14

## Context

The challenge requires a working workflow, not only detector fragments. Execution must bind the exact asset, every governed registry, policy and detector setting; preserve missing mandatory capabilities; reject idempotency-key conflicts; and remain recoverable after process failure. At the same time, a public prototype must not let a caller grant itself release authority by submitting a permissive policy or fabricated registry.

## Decision

Provide a synchronous image assessment endpoint backed by an atomic SQLite reservation lease. The execution fingerprint binds the request, rights-registry commitment, licence-registry commitment, publication-policy commitment, retrieval threshold and executor version. A key can be replayed only for identical inputs. Conflicts are rejected, active leases report in-progress state, and expired leases may be recovered. Every completion or failure is fenced by its monotonically increasing attempt number, so an expired worker cannot mutate a newer retry. Completed assessment JSON is verified against its stored canonical SHA-256 commitment on every replay and read.

The executor validates asset SHA-256, byte length, detected media type and decoded dimensions before reserving work. It then runs the offline C2PA adapter, governed image retrieval, licence evaluation and deterministic policy compiler; records declared-but-unavailable required components; constructs an evidence-bound Asset Exposure Graph; and persists the result without raw media bytes.

The endpoint always returns `release_authorization: false`. Its policy decision is decision support, not permission to publish. A later administered release boundary must authenticate approved policy/registry versions and bind a signed proof before publication authorization can exist.

## Consequences

- Identical retry requests receive the identical stored assessment and creation timestamp.
- Reusing a key with a changed policy, registry or threshold fails with a conflict.
- Crashes cannot permanently strand a key because reservations have bounded leases.
- Attempt fencing prevents stale workers from completing or failing a recovered reservation.
- Tampering with a stored assessment or commitment fails closed on read.
- Missing forensics, logo, likeness or voice components remain explicit and force review when required.
- The workflow is demonstrable today without claiming that the competition solution or release-authority boundary is complete.
