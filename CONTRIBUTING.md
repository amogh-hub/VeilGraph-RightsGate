# Contributing

VeilGraph RightsGate is developed as an evidence-led security product. A pull request is complete only when its claim, tests and operational failure behavior agree.

## Workflow

1. Select one or more IDs from `TECHGIUM_TRACEABILITY.md`.
2. State the intended maturity transition.
3. Add or update tests before advancing a capability to `IMPLEMENTED`.
4. Add frozen evaluation evidence before advancing it to `VALIDATED`.
5. Update the threat model for new inputs, tools, models, data or authority.
6. Keep model output advisory; deterministic code owns policy and release.

## Data rules

Do not commit confidential assets, scraped corpora with unclear rights, unlicensed media, secrets or biometric data. Test fixtures must have documented lawful use. Consented likeness/voice references remain outside Git and are addressed only through governed local manifests.

## Required checks

```bash
cd backend
PYTHONPATH=. pytest -q

cd ../frontend
npm run typecheck
npm run build
```

If a mandatory dependency is unavailable, the implementation and its tests must demonstrate a typed `REVIEW` or `BLOCK` outcome rather than silently bypassing the dependency.
