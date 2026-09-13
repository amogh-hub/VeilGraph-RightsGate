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

There is no signed RightsGate release yet. Current work is an engineering foundation and challenge plan. A competition release may be called signed only after its own manifest binds the RightsGate code, dependency state, policy, models, benchmark artifacts and evidence package.

## Repository hygiene

The public tree excludes private signing keys, runtime databases/workspaces/uploads, `.env` and credential material, dependency environments, caches, raw machine-local logs and generated release archives. For full byte-for-byte verification of the original VeilGraph archival freeze, use the private archive referenced by the source project.
