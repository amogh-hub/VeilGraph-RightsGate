# VeilGraph RightsGate

**Evidence-first trust gateway for AI-generated and AI-assisted media.**

[![CI](https://github.com/amogh-hub/VeilGraph-RightsGate/actions/workflows/ci.yml/badge.svg)](https://github.com/amogh-hub/VeilGraph-RightsGate/actions/workflows/ci.yml)

VeilGraph RightsGate is a challenge-focused product line derived from the frozen [VeilGraph](https://github.com/amogh-hub/VeilGraph) privacy-engineering system. The source repository remains unchanged. This repository targets the TECHgium challenge **“Safeguarding Content Rights in the Age of AI-Generated Media.”**

**Status:** `FOUNDATION VALIDATED` · `TRUSTED IMAGE EXECUTION IMPLEMENTED` · `C2PA ADAPTER IMPLEMENTED` · `RIGHTS + LICENCE EVALUATION IMPLEMENTED` · `POLICY + REVIEW UI IMPLEMENTED` · `SYNTHETIC SANITY EVAL IMPLEMENTED`

![VeilGraph RightsGate architecture](docs/architecture/rightsgate-architecture.svg)

## What exists today

The inherited VeilGraph foundation already provides:

- local-first processing for documents, images, structured data and video;
- a relationship-aware Identity Exposure Graph;
- configurable policy compilation;
- deterministic, fail-closed release decisions;
- adversarial output verification;
- cryptographically bound audit evidence and signed proof packages.

Those capabilities are inherited engineering assets, not evidence that the new challenge is already solved. Independent AI-forensic detection, general watermark forensics, localized trademark detection, likeness/voice comparison and benchmark evidence remain planned work.

The implemented RightsGate boundary now includes strict, versioned `AssetIR`, assessment-request, evidence/claim, Asset Exposure Graph and three-dimension result schemas. Referential integrity, explicit abstention and fail-closed release invariants have automated tests.

The first provenance adapter uses the official CAI `c2pa-python` SDK in local-only mode. It reads and validates embedded Content Credentials, recognizes the IPTC declarations for AI-generated and AI-edited media, retains validation-status evidence, and distinguishes cryptographic mismatches from an untrusted signer. It is `IMPLEMENTED`, not yet `VALIDATED`: signed, tampered and transformed frozen fixture evaluation remains required before competition metrics are claimed.

The first rights adapter provides exact-byte and perceptual-image candidate retrieval against a versioned, content-addressed local registry. It applies EXIF orientation, enforces a pixel budget, fails closed on unsafe inputs and deliberately returns `UNKNOWN`—not “clear”—when no registered candidate is found. Similarity produces `POTENTIAL_EXPOSURE`, never a legal infringement conclusion. This adapter is also `IMPLEMENTED`, not benchmark-`VALIDATED`.

The trusted image executor binds uploaded bytes to `AssetIR`, the rights registry, licence registry, policy and retrieval threshold. SQLite-backed leases provide atomic idempotency, attempt fencing, exact replay, conflict rejection, crash recovery and stored-result commitment verification. It combines C2PA evidence, reference candidates, licence coverage and policy results into one Asset Exposure Graph and three-dimension assessment. Raw uploaded media is not persisted by this workflow.

The licence evaluator checks explicit validity windows, status, territory, channel and intended use for every governed candidate. The policy compiler enforces allowed audience, brand profile, channel and territory plus mandatory component availability. The dedicated review UI displays the resulting evidence and limitations. Every execution receipt still returns `release_authorization: false`: caller-supplied registries and policies cannot grant publication authority.

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

- [Authoritative implementation status](IMPLEMENTATION_STATUS.md)
- [Baseline and lineage](BASELINE.md)
- [Engineering plan](ENGINEERING_PLAN.md)
- [Challenge traceability](TECHGIUM_TRACEABILITY.md)
- [Evaluation protocol](EVALUATION_PROTOCOL.md)
- [Threat model](RIGHTSGATE_THREAT_MODEL.md)
- [Trusted image execution](docs/RIGHTSGATE_EXECUTION.md)
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

Frozen synthetic rights-retrieval sanity evaluation:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. python run_rightsgate_eval.py
```

The declared 32-case synthetic resize set reports exact-only accuracy `0.75`, recall `0.50` and FPR `0.00`; the perceptual baseline reports accuracy `1.00`, recall `1.00` and FPR `0.00`. These are intentionally narrow deterministic sanity metrics, not representative real-world copyright/trademark accuracy. The [manifest](competition/techgium10/evaluation/rights-retrieval-sanity-v1.json) and [summary](competition/techgium10/evaluation/rights-retrieval-sanity-results-v1.json) record the claim boundary.

## RightsGate API and review workflow

The frontend opens on the RightsGate challenge workflow. Its integrated image path uses these endpoints:

```text
GET  /api/v1/rightsgate/contracts
POST /api/v1/rightsgate/requests/validate
POST /api/v1/rightsgate/assessments/validate
POST /api/v1/rightsgate/provenance/c2pa
POST /api/v1/rightsgate/rights/references/image
POST /api/v1/rightsgate/assessments
GET  /api/v1/rightsgate/assessments/{idempotency_key}
```

Request validation is content-addressed: identical assessment inputs produce the same SHA-256 fingerprint regardless of the caller's idempotency key. The execution fingerprint additionally binds all governed registries, policy and retrieval settings. The C2PA endpoint returns a provenance fragment; the trusted assessment endpoint persists and replays the combined decision. Caller-supplied validation and execution both remain non-authorizing until a separately administered, signed policy/release boundary exists.

## Repository map

```text
backend/                    FastAPI engine, graph, policy, verification and proof
backend/app/rightsgate/     Contracts, durable execution, policy and validation API
backend/app/rightsgate/provenance/  Offline provenance adapters
backend/app/rightsgate/rights/      Governed local rights-reference adapters
frontend/                   React/Vite RightsGate review and inherited privacy interfaces
competition/techgium10/     Competition-specific narrative and evidence
docs/adr/                   Architecture decisions
scripts/                    Setup and local run helpers
```

## Claim boundaries

RightsGate does not make legal determinations, prove human authorship from missing metadata, promise detection of every generator, or replace qualified rights reviewers. Likeness and voice matching will be limited to an explicit, consented local reference registry. The system is a defensible decision-support and release-control layer whose evidence is designed to be inspected.

## Licence

Copyright © 2026 Amogh R B. All rights reserved. See [LICENSE](LICENSE).
