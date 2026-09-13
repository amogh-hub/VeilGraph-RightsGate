# Security Policy

## Supported versions

Until the first tagged RightsGate release, only the latest commit on `main` is supported. The imported VeilGraph baseline tag exists for provenance and is not a maintained dependency line.

## Security posture

RightsGate inherits VeilGraph's design for sensitive privacy transformation, where uncertainty blocks release rather than being silently ignored. The core security policy is **fail closed**.

## Operational boundary

In offline competition mode:

- the API binds to `127.0.0.1`;
- operational model inference is local;
- `start_local.sh` performs no package/model download;
- Python outbound network access is guarded;
- source artifacts are stored only as encrypted job blobs under application control.

The COTS benchmark tooling is an explicitly separate evaluation path and may contact commercial services only when the operator supplies credentials/flags. It is not part of operational privacy processing.

## Data-at-rest handling

`backend/app/security/workspace.py` uses:

- random 256-bit per-job master keys;
- HKDF-SHA256 to derive separate encryption and fingerprint keys;
- AES-256-GCM for encrypted job blobs with random nonces and AAD;
- `0700` workspace directory / `0600` blob permissions where the host supports them;
- HMAC-SHA256 for normalized entity fingerprints.

Plaintext identity values may exist in process memory while a job is active. RightsGate does not claim that a compromised OS can be prevented from reading process memory.

## Signing and integrity

VeilGraph creates a local Ed25519 device key on first use. Verified outputs can receive certificates/proof packages bound to exact artifact, graph, verification and audit commitments. Audit events form a SHA-256 previous-hash chain.

**Never publish or copy the private device key.** This public repository intentionally excludes `.veilgraph/device-ed25519.key`.

## Retention and destruction

Jobs use a configured retention window. Destruction removes encrypted blobs, destroys in-process keys, removes sensitive database rows and leaves only a non-sensitive signed destruction tombstone. If the process restarts and job keys are lost, orphaned encrypted job directories are deleted because they are intentionally unrecoverable.

This is application-level cryptographic erasure, not forensic SSD-cell overwriting.

## Secure-online mode

Secure-online mode requires:

- a valid bearer token;
- HTTPS;
- trusted proxy networks before forwarded HTTPS headers are honored.

The bundled acceptance uses a real local TLS socket. Production internet exposure still requires organization-managed DNS/TLS, reverse proxy/firewall and normal infrastructure security controls.

## Resource and archive hardening

The application enforces bounded file/PDF/image/video/proof-package limits. Proof and release packages reject unsafe member paths and unmanifested entries.

## Public repository hygiene

The public release excludes private signing keys, runtime databases/workspaces/uploads, environment and credential material, virtual environments, `node_modules`, caches, raw machine-local regression logs and generated competition archives. See [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md).

## Reporting a vulnerability

Do not disclose suspected vulnerabilities, private media, credentials or personal data in a public issue. Use the repository's **Security → Report a vulnerability** flow to open a private GitHub security advisory. Include the affected commit, reproduction steps, impact and the smallest safe proof of concept.

If private reporting is unavailable, open a public issue containing no exploit or sensitive details and request a private contact channel.

## Response targets

- acknowledge a complete report within 72 hours;
- triage severity and affected scope within 7 days;
- publish a fix or mitigation timeline after validation;
- credit the reporter unless anonymity is requested.

These are project targets, not a service-level guarantee.

## Data handling

Never attach real confidential media, secrets or biometric references to a report. Use synthetic fixtures and hashes wherever possible. Likeness and voice references are expected to remain in a consented local registry outside Git.

## Claims boundary

RightsGate security evidence is bounded to the implementation, threat model and tested environments. It is not a substitute for host hardening, organizational access control, independent penetration testing or formal certification.
