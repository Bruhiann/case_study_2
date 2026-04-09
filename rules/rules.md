# Crescent Harbor Manifest Business Rules

The following 25 rules must be enforced against every Cargo Arrival Manifest *before* it is transmitted to the Authority. The rules complement the JSON Schema in `schema/manifest.schema.json` — the schema catches structural and per-field violations; these rules catch the cross-field business logic that JSON Schema cannot express.

Each rule has an ID, a category, a severity, and a prose description in the same style the Authority publishes them in §11.4 of the specification.

A few of these rules are deliberately ambiguous. Working from ambiguous regulatory prose is the job. Decide what each rule means, document your interpretation in `ARCHITECTURE.md`, and move on. **Do not contact the Authority for clarification** — the Direct Filer support desk does not answer specification interpretation questions, only operational ones.

A machine-readable version of these rules is in `rules.json`. The two files describe the same 25 rules. If they disagree, the prose in this file is authoritative.

The "Severity" column distinguishes rules whose violation should reject the manifest outright (`reject`) from rules that the Authority will warn on but still accept (`warning`). Both must be detected and surfaced; only `reject` rules block transmission.

---

## Identity rules

### R-001 — manifestId format
**Severity:** reject
**Spec reference:** §3.4
The `manifestId` field must be 12 to 32 characters drawn from `[A-Z0-9-]`. Lowercase characters in the input must not be silently normalized; manifests with lowercase characters in `manifestId` must be rejected.

### R-002 — filerId format
**Severity:** reject
**Spec reference:** §3.5
The `filerId` field must match the format of three uppercase letters followed by six digits.

### R-003 — contactEmail syntactic validity
**Severity:** reject
**Spec reference:** §3.5
The `contactEmail` field must be a syntactically valid email address as defined by RFC 5322 §3.4.1. (You are not required to verify deliverability — only that the address is well-formed.)

---

## Vessel rules

### R-004 — IMO check digit
**Severity:** reject
**Spec reference:** §4.1, rejection code R-603
The seven-digit IMO number must satisfy the IMO check-digit algorithm: multiply the first six digits by the weights 7, 6, 5, 4, 3, 2 respectively, sum the products, and the last digit of the resulting sum must equal the seventh digit. Manifests whose IMO check digit fails must be rejected.

### R-005 — Vessel name normalization
**Severity:** reject
**Spec reference:** §4.1
The vessel `name` field must consist of characters drawn from `[A-Z0-9 .-]` only. *(Ambiguous: §4.1 also says "Vessel names containing lowercase letters in the input shall be uppercased by the filer prior to submission." It is unclear whether your filer software should silently uppercase lowercase input or reject it as a data-quality problem at the source. Decide and document.)*

### R-006 — Gross register tons
**Severity:** reject
**Spec reference:** §1.1, §4.1
Vessel `grossRegisterTons` must be greater than 500.

### R-007 — Vessel type and terminal consistency
**Severity:** reject
**Spec reference:** §4.3, rejection code R-601
The vessel type and arrival terminal must be consistent: `CONTAINER` vessels arrive at `CH-A` or `CH-B`; `BULK` and `TANKER` arrive at `CH-C`; `RORO` arrives at `CH-D`. `GENERAL` vessels may arrive at any terminal.

---

## Container structural rules

### R-008 — Container ID uniqueness
**Severity:** reject
**Spec reference:** §5.3, rejection code R-604
A `containerId` value may not appear on two containers within the same Manifest, regardless of container type.

### R-009 — At least one container or ballast declaration
**Severity:** reject
**Spec reference:** §5.1
The `containers` array must contain at least one entry. A vessel arriving in ballast must declare exactly one `BALLAST` placeholder container; this is the only situation in which `BALLAST` may appear.

### R-010 — Ballast container exclusivity
**Severity:** reject
**Spec reference:** §5.1, §5.9
A `BALLAST` container, if present, must be the only container in the Manifest. A Manifest declaring a `BALLAST` container alongside any other container must be rejected.

### R-011 — Reserved commodity code
**Severity:** reject
**Spec reference:** §5.5, rejection code R-606
A `REF` (refrigerated) container's `commodityCode` field may not be the reserved value `"0000"`.

### R-012 — Vehicle VIN list length
**Severity:** reject
**Spec reference:** §5.8, rejection code R-605
For each `VEH` (vehicle carrier) container, the length of the `vins` array must equal the container's `quantity` field exactly.

---

## Hazardous materials rules

### R-013 — Class 7 prior authorization
**Severity:** reject
**Spec reference:** §6.3, rejection code H-204
A hazmat container of `hazardClass` `"7"` (Radioactive Material) must carry a `priorAuthorizationRef` field. Class 7 containers without this field must be rejected.

### R-014 — Hazmat gross weight proportion
**Severity:** reject
**Spec reference:** §6.2, rejection code H-201
The combined gross weight of all `HAZ` containers on a single vessel may not exceed 25 percent of the vessel's `grossRegisterTons`. *(Ambiguous: the schema does not require a `grossWeightKg` field on `HAZ` containers, and the specification does not state how this rule should behave when gross weight data is unavailable. Decide whether your enforcement is best-effort, strict, or skipped, and document why.)*

### R-015 — Hazmat warning surface
**Severity:** warning
**Spec reference:** §6.1
A Manifest declaring any `HAZ` container should be flagged for the harbormaster's review. The Authority does not reject on the basis of hazmat presence alone; your filer should produce a warning for operational visibility but must not block the submission.

---

## Cargo valuation rules

### R-016 — Declared value sum
**Severity:** reject
**Spec reference:** §7.1, rejection code V-301
The `declaredValueTotal` field must equal the arithmetic sum of all `declaredValueUSD` values across all containers in the Manifest, after rounding each container's value to two decimal places using standard half-away-from-zero rounding. The check must be exact to the cent.

### R-017 — Declared value cap
**Severity:** reject
**Spec reference:** §7.3, rejection code V-302
The `declaredValueTotal` may not exceed USD 500,000,000.00. (The JSON Schema also enforces this as an upper bound; your rules engine should still surface a clear, actionable rejection rather than relying on the schema validator to catch it.)

### R-018 — Container value precision
**Severity:** warning
**Spec reference:** §7.1
Each container's `declaredValueUSD` should have no more than two decimal places. The Authority will accept higher-precision values but will round them downstream; your filer should produce a warning so that the source data can be cleaned up.

---

## Crew rules

### R-019 — Exactly one master
**Severity:** reject
**Spec reference:** §8.3, rejection code C-401
The `crew` array must contain exactly one entry whose `role` is `MASTER`. Manifests with zero or more than one master must be rejected.

### R-020 — Crew member age range
**Severity:** reject
**Spec reference:** §8.4, rejection code C-402
Every crew member's age, computed as the difference between the date portion of the manifest's `arrival.eta` and the crew member's `dateOfBirth`, must be at least 16 years and at most 80 years.

### R-021 — Master nationality presence
**Severity:** reject
**Spec reference:** §8.2, §8.3
The crew member with `role: MASTER` must have a non-empty `nationality` field. (The JSON Schema requires `nationality` on every crew member; this rule exists to surface a more specific message if the master's nationality is missing.)

---

## Filing window rules

### R-022 — Earliest filing
**Severity:** reject
**Spec reference:** §9.1, rejection code T-501
A Manifest may not be transmitted earlier than 96 hours prior to the vessel's `arrival.eta`. The 96-hour window is computed at the moment of transmission, not at the moment the Manifest object was constructed in the filer's system.

### R-023 — Latest filing
**Severity:** reject
**Spec reference:** §9.1, rejection code T-502
A Manifest may not be transmitted later than 24 hours prior to the vessel's `arrival.eta`. *(Ambiguous: the specification does not define whether "filing" means the moment your client begins the HTTPS POST, the moment the Authority's HTTP server begins reading the request, or the moment the Authority returns the receipt. Decide which clock you treat as authoritative and document why.)*

---

## Amendment rules

### R-024 — Amendment sequence presence
**Severity:** reject
**Spec reference:** §9.3
A Manifest carrying an `amendmentSequence` field is treated as an amendment of a previously accepted original. Amendments must reuse the original Manifest's `manifestId` and may not change the `vessel.imoNumber` or `arrival.eta` from the original. (Your filer is not expected to enforce uniqueness of `manifestId` against a database for the case study; document the assumption.)

### R-025 — First-amendment sequence
**Severity:** reject
**Spec reference:** §9.3
The first amendment to a Manifest must carry `amendmentSequence: 1`. Each subsequent amendment must increment the sequence by exactly 1. Skipping or reusing sequence numbers must be rejected.
