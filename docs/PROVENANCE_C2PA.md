# C2PA Provenance Adapter

## Implemented boundary

RightsGate uses the Content Authenticity Initiative's official [`c2pa-python`](https://github.com/contentauth/c2pa-python) SDK, pinned to an exact version. The adapter disables remote-manifest retrieval and performs verification on an in-memory stream. It stores a hash commitment to the SDK report plus bounded status fields; the full manifest is not copied into generic evidence attributes.

The adapter recognizes the IPTC Digital Source Type terms [`trainedAlgorithmicMedia`](https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia) and [`compositeWithTrainedAlgorithmicMedia`](https://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia) when they occur in an active-manifest action. These declarations map to `AI_GENERATED` and `PARTIALLY_GENERATED` respectively only when the credential is `Valid` or `Trusted`.

## Conservative decision rules

| Observation | RightsGate result |
|---|---|
| No embedded manifest | `UNKNOWN`; absence is not evidence of human authorship |
| `Valid`/`Trusted` plus recognized AI declaration | `AI_GENERATED` or `PARTIALLY_GENERATED` with credential evidence |
| `Valid`/`Trusted` without recognized AI declaration | `UNKNOWN`; credential integrity does not prove non-AI origin |
| `Invalid` plus hash/signature mismatch | `TAMPERED` with failure status codes |
| `Invalid` without a cryptographic mismatch | `UNKNOWN`; the system does not overstate untrusted/malformed credentials as tampering |
| SDK parse/verification failure | component `DEGRADED`, dimension `UNAVAILABLE`, fail closed |

The C2PA specification distinguishes well-formed, valid and trusted manifests and requires validation of content bindings, assertions and signatures. RightsGate therefore preserves the SDK validation state rather than treating mere manifest presence as proof. See the official [C2PA security considerations](https://spec.c2pa.org/specifications/specifications/2.2/security/Security_Considerations.html) and [validation status codes](https://spec.c2pa.org/specifications/specifications/2.2/specs/ContentCredentials.html#_standard_status_codes).

## Evidence still required for `VALIDATED`

- trusted and valid signed fixtures from more than one claim generator;
- byte tampering, manifest corruption, replay and remote-manifest cases;
- stripping, recompression, crop and format-conversion cases;
- declared full-generation and partial-generation fixtures;
- explicit trust-anchor policy and offline refresh process;
- false-positive, abstention and latency measurements on the frozen evaluation split.

Until that evidence is frozen and reproducible, this capability remains `IMPLEMENTED`, never `VALIDATED` or `RELEASED`.
