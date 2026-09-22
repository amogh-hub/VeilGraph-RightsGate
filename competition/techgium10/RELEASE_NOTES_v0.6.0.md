# VeilGraph RightsGate v0.6.0 — TECHgium competition update

This update preserves the original VeilGraph repository and advances the separate public RightsGate project.

## What changed

- Corrected C2PA assertion-URI hash-mismatch handling so the official tampered-assertion fixture produces a `TAMPERED` signal.
- Added a pinned, SHA-256-verified 12-JPEG interoperability evaluation sourced from the official C2PA public testfiles at commit `22beccc075707475b038d8789d0136c009e43143`. The selected slice gives 12/12 correct absent/valid/invalid credential classifications. Across 11 adjudicable tamper cases it gives 6 true positives, 5 true negatives, 0 false positives and 0 false negatives. The observed 0/5 false-positive rate has a 95% Wilson upper bound of 0.4345.
- Added raw predictions, fixture hashes, source attribution and a reproducible evaluation command. The upstream CC BY-SA 4.0 JPEG binaries are fetched on demand, not bundled in this release.
- Added a self-checking judge-demo generator that creates synthetic reference and enrolled-visible-watermark examples, plus a documented licence-conflict path using the review UI's toggle. It can optionally fetch three official C2PA examples into a caller-selected directory outside the repository.
- Kept the previous 192 byte-fingerprinted synthetic cases and their deliberately bounded metrics unchanged.

## Reproduce

After `./scripts/setup_once.sh`, from `backend/`:

```bash
PYTHONPATH=. python run_rightsgate_c2pa_interop_eval.py --fetch
PYTHONPATH=. python prepare_rightsgate_judge_demo.py --output-dir ../../rightsgate-judge-demo-local --fetch-c2pa
```

The generator refuses to overwrite an existing directory. The signed ZIP asset is independently verifiable with the pinned signer fingerprint documented in `PUBLIC_RELEASE.md`.

## Claim boundary

This is a small, selected C2PA *interoperability* slice, not representative AI-generation, rights, or deployment-policy accuracy. Structurally valid credentials in this test set use untrusted test certificates. The synthetic benchmarks remain engineering sanity checks. Open-world AI attribution, general watermark tampering, representative rights/biometric evaluation, vendor CMS integration, and portal-specific rehearsal remain unfinished.
