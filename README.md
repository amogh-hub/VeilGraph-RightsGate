# VeilGraph RightsGate

**Evidence-first trust gateway for AI-generated and AI-assisted media.**

VeilGraph RightsGate is a challenge-focused product line derived from the frozen [VeilGraph](https://github.com/amogh-hub/VeilGraph) privacy-engineering system. The source repository remains unchanged. This repository targets the TECHgium challenge **“Safeguarding Content Rights in the Age of AI-Generated Media.”**

**Status:** `FOUNDATION IMPORTED` · `CHALLENGE CONTRACT DEFINED` · `RIGHTS MODULES NOT YET IMPLEMENTED`

![VeilGraph RightsGate architecture](docs/architecture/rightsgate-architecture.svg)

## What exists today

The inherited VeilGraph foundation already provides:

- local-first processing for documents, images, structured data and video;
- a relationship-aware Identity Exposure Graph;
- configurable policy compilation;
- deterministic, fail-closed release decisions;
- adversarial output verification;
- cryptographically bound audit evidence and signed proof packages.

Those capabilities are inherited engineering assets, not evidence that the new challenge is already solved. AI-generation detection, provenance verification and rights-matching modules are explicitly planned work until their implementation and benchmark evidence land in this repository.

## Product contract

Every assessment must return three distinct, evidence-backed dimensions:

| Dimension | Required output |
|---|---|
| Provenance | Calibrated confidence, localized evidence and a conclusion of `SUPPORTED`, `CONTRADICTED` or `UNKNOWN` for generation and manipulation claims. |
| Rights exposure | Candidate work, mark, likeness or voice matches; source and usage constraints; confidence; and required human review. |
| Deployment readiness | A deterministic `GO`, `REVIEW` or `BLOCK` decision under a versioned brand, regulatory and regional policy. |

The system follows three strict claims rules:

1. Missing C2PA credentials or watermarks are `UNKNOWN`, never proof of human authorship.
2. Similarity is risk evidence, not a legal determination of infringement or ownership.
3. Missing mandatory evidence, detector failure or low confidence fails closed to `REVIEW` or `BLOCK`.

## Intended architecture

```text
Media asset + intended use + policy context
                 |
          Secure local ingestion
                 |
       +---------+---------+
       |                   |
Provenance lane       Rights lane
credentials,          works, marks,
watermarks,           likeness, voice,
forensics             licences
       +---------+---------+
                 |
        Asset Exposure Graph
                 |
       Versioned policy compiler
                 |
    Adversarial release verification
                 |
       GO / REVIEW / BLOCK
       + signed evidence pack
```

The Asset Exposure Graph will connect works, people, voices, marks, licences, transformations, territories, campaigns and intended uses. This lets RightsGate reason about combinations that isolated detectors cannot resolve—for example, a strong logo match paired with an expired licence in a restricted territory.

## Evidence-led development

Repository claims use these maturity labels:

- `PLANNED` — contracted but not implemented;
- `IMPLEMENTED` — code and automated tests exist;
- `VALIDATED` — frozen-set evaluation evidence exists;
- `RELEASED` — included in a signed tagged release.

Start with the engineering evidence:

- [Baseline and lineage](BASELINE.md)
- [Engineering plan](ENGINEERING_PLAN.md)
- [Challenge traceability](TECHGIUM_TRACEABILITY.md)
- [Evaluation protocol](EVALUATION_PROTOCOL.md)
- [Threat model](RIGHTSGATE_THREAT_MODEL.md)
- [Architecture decision records](docs/adr)
- [TECHgium abstract draft](competition/techgium10/ABSTRACT_DRAFT.md)

## Run the inherited foundation

Requirements: Python 3.11+, Node.js 22+, Tesseract OCR, Poppler and FFmpeg.

```bash
./scripts/setup_once.sh
./scripts/run_backend.sh
./scripts/run_frontend.sh
```

Backend tests:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. pytest -q
```

Frontend checks:

```bash
cd frontend
npm run typecheck
npm run build
```

## Repository map

```text
backend/                    FastAPI engine, graph, policy, verification and proof
frontend/                   React/Vite review and release interface
competition/techgium10/     Competition-specific narrative and evidence
docs/adr/                   Architecture decisions
scripts/                    Setup and local run helpers
```

## Claim boundaries

RightsGate does not make legal determinations, prove human authorship from missing metadata, promise detection of every generator, or replace qualified rights reviewers. Likeness and voice matching will be limited to an explicit, consented local reference registry. The system is a defensible decision-support and release-control layer whose evidence is designed to be inspected.

## Licence

Copyright © 2026 Amogh R B. All rights reserved. See [LICENSE](LICENSE).
