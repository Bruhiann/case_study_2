# Threat Model — Crescent Harbor Direct Filer

## Sensitive data in this system

| Data | Where it lives | Why it is sensitive |
|---|---|---|
| HMAC shared secret | `client.py` module constant; overridable via `CUSTOMS_FILER_SECRET` env var | Possession of this secret allows anyone to forge a valid submission to the Authority under our filer identity |
| Passport numbers | Manifest `crew[*].passportNumber` — in memory during pipeline execution, in `results.json` if the manifest detail is logged | Government-issued identifier; PII under most data protection regimes |
| Dates of birth | Manifest `crew[*].dateOfBirth` — same lifecycle as passport numbers | PII; also used for age-range computation |
| Declared values | Manifest `containers[*].declaredValueUSD` and `declaredValueTotal` | Commercially sensitive cargo valuation; potential import-duty liability |
| Contact email | `filer.contactEmail` — set in `builder.py` `FILER_CONFIG` | Operational PII; target for phishing if exposed |

---

## HMAC secret handling

**Current state (case study).** The secret
`case-study-shared-secret-do-not-use-in-production-zX4qP9rL` is committed
to the repository as a default value in `client.py` and appears in plain
text in `mock-customs/secrets.json`. This is acceptable for a hiring
exercise where the secret has no real-world value and the code is never
deployed.

**What a security reviewer would flag immediately.** A secret committed to
source control is a secret that can never truly be rotated — every
historical clone of the repository retains it. The variable name
`FILER_SECRET` with a string literal default is a common anti-pattern that
static analysis tools (e.g. `detect-secrets`, `trufflehog`) will flag.

**What production must look like.**
- The secret must never appear in source code or version control.
- At runtime, `client.py` reads `CUSTOMS_FILER_SECRET` from the environment.
  That variable is injected by a secrets manager (AWS Secrets Manager,
  HashiCorp Vault, or equivalent) at deploy time.
- Secret rotation: the secrets manager issues a new secret; the Authority
  activates it on a rolling basis; the filer picks it up on the next
  deployment or via a live reload hook. No code change required.
- Audit log entries for every signing operation (timestamp, filer ID,
  manifest ID) should be written to an append-only log to support post-hoc
  detection of unauthorized use.

---

## Audit trail

**What the spec requires.** §12.1 requires filers to retain every manifest,
receipt, and final acknowledgment for at least 7 years.

**What this filer produces.**
- `results.json` records the outcome, `manifestId`, `receiptId`, and any
  errors for every scenario run. This is a run-level audit log, not a
  durable per-manifest store.
- The `filerSignature` block inside each manifest (§10.5) records the
  signer name, title, and UTC timestamp. This is an assertion of human
  accountability for the submission, not a cryptographic proof.

**What is missing for production.**
- A durable database row per manifest linking scenario → built manifest
  JSON → receiptId → final ack. Without this there is no way to produce
  a manifest on Authority request (§12.2) or to enforce amendment
  invariants (R-024/R-025).
- The `filerSignature.signerName` is currently the string
  `"Automated Filing System"`. A production filer should record the
  identity of the human or service account that authorized the submission,
  with enough context to reconstruct the chain of custody.

---

## What a security reviewer sees when reading this code

- **`client.py` line 1:** module docstring explicitly warns that the
  default secret must not be used in production and references
  `THREAT-MODEL.md`. The env-var override path is the documented
  production path.
- **No secret in `builder.py`.** Filer identity (`filerId`, `legalName`,
  `contactEmail`) is in `FILER_CONFIG` in `builder.py`. These are not
  secrets — they are the filer's public registration data.
- **No secrets in `results.json`.** Outcome labels, manifest IDs, and
  receipt IDs are written; the HMAC secret, passport numbers, and declared
  values are not written to the output file.
- **No logging of request bodies.** `client.py` does not log the raw
  manifest JSON or the HMAC key material. Error messages include HTTP
  status codes and Authority-returned error strings only.
- **`urllib.request` over `requests`.** The standard library HTTP client
  avoids a supply-chain dependency. Its behaviour is well-audited and
  does not introduce third-party code into the signing path.
- **Plain HTTP to mock Authority.** The mock uses HTTP for grader
  convenience (documented in `mock-customs/README.md`). The spec mandates
  HTTPS (§10.1). A production deployment must use TLS to protect both
  the HMAC signature header and the manifest body (which contains PII)
  in transit.
