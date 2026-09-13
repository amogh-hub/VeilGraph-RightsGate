# Baseline and Lineage

This file makes the relationship between the original VeilGraph system and VeilGraph RightsGate explicit and auditable.

| Field | Value |
|---|---|
| Authoritative source | `https://github.com/amogh-hub/VeilGraph.git` |
| Source branch | `main` |
| Source commit | `ac1ccbdcec6a08c12599b166cb25d7aed6f17ac3` |
| Source subject | `Initial release: VeilGraph pre-Grand-Finale frozen system` |
| Source timestamp | `2026-08-14T00:59:49+05:30` |
| Derived product | `VeilGraph RightsGate` |

## Isolation guarantee

The source repository is the authoritative frozen SIH project. No RightsGate commit is to be pushed or merged into it.

In this working copy, the source remote is named `upstream` and is deliberately fetch-only. Its push URL is set to `NO_PUSH_TO_FROZEN_VEILGRAPH`. The new public repository receives a separate `origin` remote only after creation.

## Baseline acceptance

Before challenge implementation starts:

1. Reproduce the backend test suite on a clean environment.
2. Reproduce the frontend typecheck and production build.
3. Record relevant Python, Node, dependency and system-tool versions.
4. Tag the imported source commit as `veilgraph-baseline-ac1ccbd`.
5. Retain all inherited limitations and security assumptions until superseded by reviewed evidence.

The original README records a historical result of **268 passed, 0 failed**. That figure describes the frozen source at its release point. It must not be presented as a RightsGate result until independently reproduced here, and it must never be presented as accuracy evidence for the new provenance or rights dimensions.

## Change rule

Every challenge capability must be traceable to a requirement, test and evaluation artifact. Features may be described as `IMPLEMENTED` only after automated tests exist, and as `VALIDATED` only after evaluation on the declared frozen dataset.

## Reproduction record — 2026-09-13

Environment: macOS arm64, Python 3.12.14, Node.js 26.7.0, npm 11.19.0, Tesseract 5.5.3, Poppler 26.08.0 and Homebrew FFmpeg.

| Check | Result |
|---|---|
| Exact inherited Python pins | 268 passed, 0 failed, 6 dependency deprecation warnings in 235.67 seconds |
| Exact inherited frontend | Typecheck passed; production build passed |
| Inherited npm audit | 3 findings: 1 moderate, 2 high |
| Inherited Python audit | 75 advisory records across 6 packages |
| Hardened frontend | Vite 8.3.0; typecheck and production build passed; 0 audit findings |
| Hardened Python pins | 268 passed, 0 failed, 7 dependency deprecation warnings in 236.95 seconds; 0 audit findings |

Audit counts are point-in-time results and must be regenerated continuously. The hardened dependency changes belong to RightsGate; the baseline tag continues to point to the exact imported source commit.
