# RightsGate three-minute judge demo

This script demonstrates the exact implemented boundary. Use only synthetic or properly licensed media and never claim that the bounded evaluation results are real-world biometric, copyright or AI-detector accuracy.

## Before the session

1. Check out tag `v0.6.1-rightsgate-techgium` and run `./scripts/setup_once.sh`.
2. Run `./scripts/run_backend.sh` and `./scripts/run_frontend.sh` in separate terminals.
3. Prepare a fresh local fixture directory outside the repository:
   - `cd backend && PYTHONPATH=. python prepare_rightsgate_judge_demo.py --output-dir ../../rightsgate-judge-demo-local --fetch-c2pa`
   - If that directory already exists, choose a new name; the generator will not overwrite it. The `--fetch-c2pa` option uses pinned SHA-256-verified official CC BY-SA 4.0 fixtures; omit it for an offline synthetic-only pack.
   - Read the generated `DEMO_GUIDE.txt` and `DEMO_MANIFEST.json` before presenting.
4. Reproduce the three synthetic evaluations and selected official C2PA interoperability evaluation from `backend/`:
   - `PYTHONPATH=. python run_rightsgate_eval.py`
   - `PYTHONPATH=. python run_rightsgate_signal_eval.py`
   - `PYTHONPATH=. python run_rightsgate_consent_eval.py`
   - `PYTHONPATH=. python run_rightsgate_c2pa_interop_eval.py --fetch`
   - `PYTHONPATH=. python -m pytest tests/test_rightsgate_judge_acceptance.py -q` checks the generated demo assets against the real assessment and signed CMS-decision endpoints.
5. Keep the generated intact campaign image, altered-watermark image, governed reference and registry JSON ready. Prepare a separate consent-scope and PCM/WAV case only if those lanes will be shown.
6. Confirm that no private, unlicensed or biometric production data is present.

## 0:00–0:25 — Problem and differentiator

"Content teams need one publication gate, not disconnected detector scores. RightsGate binds the exact media bytes, provenance evidence, rights candidates, licence and consent scope, policy version and final decision into one evidence graph. Missing mandatory evidence fails closed."

Show the three output dimensions and the Asset Exposure Graph in the review screen.

## 0:25–1:05 — Provenance and tampering

Submit `synthetic-campaign-watermark-altered.png` with `synthetic-watermark-registry.json`. Show:

- exact asset SHA-256 and component version;
- C2PA result and independent forensic triage as separate evidence;
- the configured watermark region, registry commitment and mismatch distance;
- provenance `TAMPERED` and the resulting policy `BLOCK`.

Then, if time allows, submit `official-c2pa-adobe-20220124-E-uri-CA.jpg` and show the independently detected assertion-URI hash mismatch. State the boundary: "An intact enrolled visible watermark does not prove authenticity, and arbitrary invisible-watermark families are outside this release. These C2PA files are interoperability examples, not an AI-detection benchmark."

## 1:05–1:45 — Rights, licence and consent reasoning

Submit `synthetic-campaign-intact.png` with `synthetic-campaign-reference.png`. Disable the valid-licence toggle to demonstrate a governed rights conflict. Show:

- work or mark candidate and localized region evidence;
- licence validity, territory, channel and intended-use evaluation;
- person or voice node, consent record and `CONSENTED_BY` edge;
- the absent licence producing `POLICY_CONFLICT` and `BLOCK`.

For a territory-scope demo, use a separately governed licence/consent fixture; the standard review UI's licence toggle creates a same-territory licence and does not itself demonstrate a territory mismatch.

State the boundary: "Similarity is candidate evidence, not infringement, ownership, face recognition or speaker identification. Consent comes only from the governed record."

## 1:45–2:20 — Workflow and release control

Show the deterministic `GO / REVIEW / BLOCK` policy evidence and signed CMS receipt. Explain that the CMS receipt is deliberately non-authorizing. Show that publication authorization requires fresh signatures from distinct trusted `RIGHTS_REVIEWER` and `RELEASE_MANAGER` identities and is bound to the asset, assessment, CMS receipt, trust registry and expiry.

## 2:20–2:45 — Reproducible evidence

Open the checked-in evaluation summaries. State:

- 32 retrieval cases;
- 64 localization/generator-metadata cases with calibration and a standards/watermark-only ablation;
- 96 visible-watermark, enrolled-likeness, enrolled-voice and consent-scope cases;
- 192 total byte-fingerprinted synthetic cases.
- a separate 12-case selected official C2PA JPEG slice: 12/12 correct credential states; among 11 adjudicable tamper labels, 6 TP, 5 TN, 0 FP and 0 FN. Its 0/5 observed FPR has a 95% Wilson upper bound of about 43%.

Say: "The synthetic results cover only declared transformations. The official C2PA slice checks interoperability, with untrusted test certificates and a small denominator. None of these metrics estimates challenge-wide real-world accuracy."

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
