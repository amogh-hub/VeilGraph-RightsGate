# Independent Image Forensic Triage

## Implemented boundary

The `provenance.independent-forensics` component runs independently of C2PA. It inspects bounded PNG/JPEG metadata for recognized generator/tool markers and computes a tiled high-pass residual consistency signal. Every result is bound to the exact asset SHA-256 and detector manifest.

Recognized self-declarations can support `AI_GENERATED` or `PARTIALLY_GENERATED`. A localized residual outlier receives a region evidence pointer, but remains non-attributive: editing, compression and scene structure can create the same signal. An absent marker never becomes evidence of human authorship, so the provenance verdict remains `UNKNOWN`.

## Security and claim rules

- Decode and pixel budgets are enforced before analysis.
- Metadata values are bounded and treated only as data.
- Ambiguous phrases such as “stable diffusion of gases” do not trigger without generator context.
- Metadata can be stripped or forged and therefore requires corroboration.
- Residual anomalies do not independently prove AI generation or tampering.
- Decode failure returns typed component degradation and cannot authorize release.

The frozen 32-case metadata-marker subset in `competition/techgium10/evaluation/challenge-signals-sanity-v1.json` is a reproducibility sanity check. Its accuracy and false-positive rate are not representative real-world AI-attribution metrics.
