# RightsGate three-minute judge demo

This script demonstrates the exact implemented boundary. Use only synthetic or properly licensed media and never claim that the bounded evaluation results are real-world biometric, copyright or AI-detector accuracy.

## Before the session

1. Check out tag `v0.5.0-rightsgate-techgium` and run `./scripts/setup_once.sh`.
2. Run `./scripts/run_backend.sh` and `./scripts/run_frontend.sh` in separate terminals.
3. Reproduce all three frozen evaluations from `backend/`:
   - `PYTHONPATH=. python run_rightsgate_eval.py`
   - `PYTHONPATH=. python run_rightsgate_signal_eval.py`
   - `PYTHONPATH=. python run_rightsgate_consent_eval.py`
4. Keep one clean image, one configured-watermark mismatch, one governed reference candidate, one consent-scope conflict and one PCM/WAV voice-reference case ready.
5. Confirm that no private, unlicensed or biometric production data is present.

## 0:00–0:25 — Problem and differentiator

"Content teams need one publication gate, not disconnected detector scores. RightsGate binds the exact media bytes, provenance evidence, rights candidates, licence and consent scope, policy version and final decision into one evidence graph. Missing mandatory evidence fails closed."

Show the three output dimensions and the Asset Exposure Graph in the review screen.

## 0:25–1:05 — Provenance and tampering

Submit the configured-watermark mismatch. Show:

- exact asset SHA-256 and component version;
- C2PA result and independent forensic triage as separate evidence;
- the configured watermark region, registry commitment and mismatch distance;
- provenance `TAMPERED` and the resulting policy `BLOCK`.

State the boundary: "An intact enrolled visible watermark does not prove authenticity, and arbitrary invisible-watermark families are outside this release."

## 1:05–1:45 — Rights, licence and consent reasoning

Submit the governed reference/identity case. Show:

- work or mark candidate and localized region evidence;
- licence validity, territory, channel and intended-use evaluation;
- person or voice node, consent record and `CONSENTED_BY` edge;
- a territory mismatch producing `POLICY_CONFLICT` and `BLOCK`.

State the boundary: "Similarity is candidate evidence, not infringement, ownership, face recognition or speaker identification. Consent comes only from the governed record."

## 1:45–2:20 — Workflow and release control

Show the deterministic `GO / REVIEW / BLOCK` policy evidence and signed CMS receipt. Explain that the CMS receipt is deliberately non-authorizing. Show that publication authorization requires fresh signatures from distinct trusted `RIGHTS_REVIEWER` and `RELEASE_MANAGER` identities and is bound to the asset, assessment, CMS receipt, trust registry and expiry.

## 2:20–2:45 — Reproducible evidence

Open the checked-in evaluation summaries. State:

- 32 retrieval cases;
- 64 localization/generator-metadata cases with calibration and a standards/watermark-only ablation;
- 96 visible-watermark, enrolled-likeness, enrolled-voice and consent-scope cases;
- 192 total byte-fingerprinted synthetic cases.

Say: "The reported accuracy and false-positive rates are valid only for these declared transformations. We do not generalize them to real-world media."

## 2:45–3:00 — Close

"RightsGate goes beyond credentials or watermarking alone by combining independently versioned evidence with rights, consent and deployment policy, while making uncertainty visible and blocking unsafe automation."

End on the evidence graph and signed decision, not a detector-only screen.

## Expected judge questions

- **Can this prove copyright infringement?** No. It retrieves governed candidates and evaluates supplied licences; legal determination remains human.
- **Does no match mean clear?** No. Registry non-match explicitly remains open-world uncertainty.
- **Does it recognize anyone?** No. It compares only enrolled governed image/acoustic references and then evaluates an independent consent grant.
- **What if C2PA is absent?** Absence is `UNKNOWN`; independent signals may add bounded evidence but never invent credentials.
- **What prevents a tool from changing policy?** The executor hashes all governed inputs and component versions; the policy compiler is separate, deterministic and fail-closed.
- **Why can the CMS not publish directly?** The CMS receipt has `release_authorization: false`; a separate short-lived dual-control boundary is required.
- **What remains before production?** Representative legally sourced evaluation, arbitrary watermark/provider integrations, video audio-track analysis, authenticated vendor webhooks and operational key provisioning.
