# Abstract Draft — TECHgium 10

> **Submission warning:** This is a project-specific drafting aid, not text to paste unchanged. The portal warns that directly copied AI-generated text may be disqualified and asks the submitter to attest that the abstract is at least 75% unique. The team must verify every claim and rewrite the final abstract in its own voice before publication.

## Proposed title

**VeilGraph RightsGate — Evidence-First Trust Gateway for AI Media**

## Draft (284 words)

VeilGraph RightsGate is a local-first pre-publication trust gateway that converts each media asset into an inspectable Asset Exposure Graph instead of returning one opaque detector score. It extends the tested VeilGraph privacy platform through three coordinated evidence lanes.

First, the provenance lane validates C2PA credentials, signatures, metadata continuity and watermark signals, then combines them with forensic models for generation, splicing, inpainting and voice cloning. It reports whole-asset and region/timeline findings, while absence of a credential is treated as unknown rather than proof of manipulation.

Second, the rights lane compares visual and audio features against approved reference collections, detecting near-duplicate copyrighted material, logos and trademarks, and face or voice similarity against a consented likeness registry. The graph connects each detected work, person, mark, licence, territory, campaign and transformation so individually weak clues can reveal a high-risk relationship.

Third, a configurable policy compiler evaluates those findings for brand, consent, channel, audience and regional rules. Machine-learning components may nominate risks, but cannot authorize publication. Deterministic gates issue GO, REVIEW or BLOCK; low-confidence and contradictory evidence requires human review. Every decision carries source-level evidence, confidence, model and policy versions, hashes, and a signed proof package.

The prototype builds on VeilGraph’s existing multi-format pipeline, local processing, adversarial release checks, audit chain and 268-test regression. TECHgium development adds the provenance and rights detectors, reference registry, content-workflow API and per-dimension dashboard.

Evaluation will use a declared set of licensed, public-domain, synthetic and adversarially altered assets. We will report accuracy and false-positive rate for provenance, rights and policy outcomes; localization quality; decision latency; and reviewer effort, compared with C2PA/watermark-only and single-detector baselines. The goal is to prevent unlicensed content and unauthorized likeness use before publication without exposing confidential media to external services.

## Suggested keywords

content provenance, media rights, C2PA, likeness protection, policy-as-code, explainable AI, fail-closed security, multimodal forensics
