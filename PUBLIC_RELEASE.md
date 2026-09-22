# Public Release Provenance

VeilGraph RightsGate is a derived product. Its `main` branch intentionally diverges from the signed VeilGraph pre-Grand-Finale build; the historical VeilGraph manifests do **not** authenticate new RightsGate changes.

## Exact inherited baseline

The unmodified public VeilGraph source is preserved by:

- commit `ac1ccbdcec6a08c12599b166cb25d7aed6f17ac3`;
- tag `veilgraph-baseline-ac1ccbd`;
- fetch-only source remote `upstream` at `https://github.com/amogh-hub/VeilGraph.git`.

To verify the historical public release without replacing the RightsGate working tree, create a separate worktree at the baseline tag:

```bash
git worktree add ../veilgraph-baseline veilgraph-baseline-ac1ccbd
cd ../veilgraph-baseline
./scripts/setup_once.sh
backend/.venv/bin/python scripts/verify_public_release.py
```

The expected historical ending is:

```text
PUBLIC_RELEASE_PROVENANCE_VALID
Allowed sanitized omission: competition/final/FINAL_FULL_REGRESSION.log
```

## Historical sanitized omission

The inherited public source intentionally excludes the raw machine-local regression log:

```text
competition/final/FINAL_FULL_REGRESSION.log
expected SHA-256:
25c152eaa0e73348bd6da5186e133b17231051822293e0b6604def71ea858363
```

The source verifier permits only that documented omission and rejects any other missing or mismatched signed file.

## RightsGate release state

The public competition release is tagged `v0.6.1-rightsgate-techgium`. It includes image, bounded MP4/MOV and PCM/WAV orchestration; C2PA and independent forensic triage; governed visible-watermark, work, mark, licence and enrolled likeness/voice-consent controls; versioned policy; review UI; signed CMS decisions; dual-control release authorization; three frozen synthetic evaluation manifests containing 192 declared cases; and a separate pinned 12-case official C2PA JPEG interoperability manifest with raw outcomes. Official C2PA image binaries are fetched on demand and are not included in the public archive. A self-checking fixture generator prepares a synthetic and optional official-C2PA judge demo outside the repository. An automated acceptance test sends that synthetic demo pack through the assessment and signed CMS-decision APIs, including the no-reference fail-closed path.

The downloadable competition archive is independently sanitized and contains a signed release envelope. Its manifest binds every included byte, excludes runtime databases, workspaces, dependency trees, generated archives and private-key material, and embeds the Ed25519 public key and signer fingerprint needed for offline verification. The archive is a reproducible evidence package, not a claim of real-world detector accuracy or legal clearance.

Verify an archive without trusting the surrounding checkout:

```bash
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from pathlib import Path
from app.security.release_package import verify_release_package_bytes

package = Path("competition/releases/veilgraph-rightsgate-techgium-v0.6.1.zip")
print(verify_release_package_bytes(
    package.read_bytes(),
    expected_signer_fingerprint="c0cf1c7413d387b59afb0a3ac091c3b4a43b8c33a227f7c1697254d16f8192c6",
))
PY
```

## Repository hygiene

The public tree excludes private signing keys, runtime databases/workspaces/uploads, `.env` and credential material, dependency environments, caches, raw machine-local logs and generated release archives. For full byte-for-byte verification of the original VeilGraph archival freeze, use the private archive referenced by the source project.
