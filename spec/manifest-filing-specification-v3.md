# Crescent Harbor Manifest Filing Specification, Version 3.0

**Issued by:** Port of Crescent Harbor Customs Authority (PCHCA)
**Effective:** 1 January 2026
**Supersedes:** Specification v2.4 (1 January 2024)
**Document classification:** Public

> The Crescent Harbor Customs Authority is responsible for the inspection and clearance of all commercial vessels calling at the Port of Crescent Harbor. Beginning 1 January 2024 the Authority requires that all carriers electronically file a Cargo Arrival Manifest no later than the thresholds specified in §9 prior to the vessel's expected time of arrival. This document specifies the structure of the manifest, the rules its contents must satisfy, the protocol by which it must be transmitted to the Authority, and the acknowledgment messages the Authority will return.

---

## §1. Scope and authority

§1.1 This specification governs the electronic submission of Cargo Arrival Manifests to the Port of Crescent Harbor Customs Authority for any commercial vessel exceeding 500 gross register tons calling at any of the Authority's terminals.

§1.2 Carriers, their agents, and software vendors acting on behalf of carriers are bound by this specification when filing under the Authority's Direct Filer Program.

§1.3 The protocol described in §10 is the only authorized means of submission. Submissions by email, fax, paper form, or any third-party clearinghouse are not accepted under the Direct Filer Program.

§1.4 The Authority publishes amendments to this specification on a yearly cadence. Carriers are responsible for retesting their systems against each new version prior to the version's effective date.

---

## §2. Definitions

The following terms have the meanings assigned to them throughout this document.

**Manifest** — The complete record of all cargo, vessel particulars, and crew aboard a vessel for a single arrival event at the Port of Crescent Harbor.

**Arrival event** — A single physical arrival of a single vessel at a single Crescent Harbor terminal. A vessel that calls at two terminals on the same voyage produces two distinct arrival events and two distinct manifests.

**Carrier** — The legal entity operating the vessel and responsible for the cargo aboard.

**Filer** — The legal entity transmitting the manifest to the Authority. The filer may or may not be the carrier; carriers commonly delegate filing to a software agent.

**Container** — Any sealed unit of cargo aboard the vessel for which a separate declaration is required. The container types recognized by this specification are enumerated in §5.

**Declared value** — The customs value of a container's contents, in United States dollars, as declared by the carrier. The Authority's duty assessment is independent of and may differ from the declared value.

**Filing window** — The time interval during which a manifest may be transmitted, defined relative to the vessel's expected time of arrival. See §9.

**Acknowledgment** — A message returned by the Authority indicating either acceptance or rejection of a submitted manifest. See §11.

**ETA** — Expected Time of Arrival, expressed as an ISO 8601 timestamp in UTC.

---

## §3. The Manifest document

§3.1 A Manifest is a JSON document conforming to the JSON Schema published at `schema/manifest.schema.json`.

§3.2 The top-level object of a Manifest contains exactly the following fields:

- `manifestId` — string, the filer's unique identifier for this manifest. Format and uniqueness rules are in §3.4.
- `filer` — object, the legal identity of the filer. See §3.5.
- `vessel` — object, the vessel particulars. See §4.
- `arrival` — object, terminal and ETA information. See §4.
- `containers` — array, one entry per container declared aboard the vessel. See §5.
- `crew` — array, one entry per crew member aboard. See §8.
- `declaredValueTotal` — number, in USD, the sum of all container declared values. See §7.
- `filerSignature` — object, the filer's signature block. See §10.

§3.3 No additional fields beyond those listed in §3.2 are permitted at the top level. Manifests containing unrecognized top-level fields shall be rejected with code `M-103`.

§3.4 The `manifestId` field shall be a string of 12 to 32 characters, drawn from the alphabet `[A-Z0-9-]`. The Authority will not enforce uniqueness of `manifestId` across filers, but a single filer that submits two manifests with the same `manifestId` within any rolling 90-day period will have the second submission rejected as a duplicate. The Authority recommends that filers use a UUIDv4 with hyphens removed and uppercased.

§3.5 The `filer` object contains:

- `filerId` — string, the Authority-issued Direct Filer identifier. Format: three uppercase letters followed by six digits (e.g. `CHC123456`).
- `legalName` — string, 1 to 100 characters.
- `contactEmail` — string, a syntactically valid email address as defined by RFC 5322 §3.4.1.

---

## §4. Vessel and arrival

§4.1 The `vessel` object describes the physical vessel and contains:

- `imoNumber` — string, the International Maritime Organization vessel number, exactly seven digits, prefixed with the literal `IMO`. The seven digits must satisfy the IMO check-digit algorithm: multiply the first six digits by the weights 7, 6, 5, 4, 3, 2 respectively, sum the products, and the last digit of the sum must equal the seventh digit.
- `name` — string, 1 to 50 characters drawn from `[A-Z0-9 .-]`. Vessel names containing lowercase letters in the input shall be uppercased by the filer prior to submission.
- `flag` — string, the ISO 3166-1 alpha-2 country code of the vessel's flag state.
- `grossRegisterTons` — integer, greater than 500 (per §1.1).
- `vesselType` — string, one of `CONTAINER`, `BULK`, `TANKER`, `RORO`, `GENERAL`.

§4.2 The `arrival` object describes the arrival event and contains:

- `terminal` — string, one of `CH-A`, `CH-B`, `CH-C`, `CH-D`. (Terminals A and B are container terminals; C is bulk; D is RORO.)
- `eta` — string, an ISO 8601 timestamp in UTC, ending in `Z`. Sub-second precision is not permitted.
- `voyageNumber` — string, 1 to 16 characters drawn from `[A-Z0-9-]`.
- `previousPort` — string, the UN/LOCODE of the vessel's last port of call, format `[A-Z]{2}[A-Z]{3}` (country code followed by location code).

§4.3 The `vesselType` declared in §4.1 must be consistent with the `terminal` declared in §4.2: `CONTAINER` vessels must arrive at terminal `CH-A` or `CH-B`; `BULK` and `TANKER` at `CH-C`; `RORO` at `CH-D`. `GENERAL` vessels may arrive at any terminal at the discretion of the harbormaster.

---

## §5. Container declarations

§5.1 The `containers` array shall contain at least one entry. A vessel arriving in ballast (with no cargo) shall declare a single placeholder container of type `BALLAST` with `quantity` of zero; this is the only situation in which the `BALLAST` type may appear.

§5.2 Each entry in the `containers` array is an object with the following common fields:

- `containerId` — string, the carrier's identifier for the container, 1 to 16 characters from `[A-Z0-9]`.
- `type` — string, one of `DRY`, `REF`, `HAZ`, `LIQ`, `VEH`, `BALLAST`. Each type adds further required fields described below.
- `quantity` — integer, ≥ 1 for all types except `BALLAST` (where it must be 0).
- `declaredValueUSD` — number, ≥ 0, declared value of the container's contents in U.S. dollars, with up to two decimal places.

§5.3 `containerId` values must be unique within a single Manifest. The same `containerId` may not appear on two containers in the same Manifest, regardless of type.

§5.4 **Type `DRY`** — A standard sealed dry-goods container. No additional fields are required beyond those in §5.2.

§5.5 **Type `REF`** — A refrigerated container. Required additional fields:

- `temperatureSetpointCelsius` — number, between -30.0 and +25.0 inclusive, with up to one decimal place.
- `commodityCode` — string, the four-digit Crescent Harbor Commodity Code for the perishable cargo within. Code 0000 is reserved and may not be used.

§5.6 **Type `HAZ`** — A container holding hazardous materials. Required additional fields:

- `unNumber` — integer, the UN-assigned identification number for the substance. Valid range: 1 to 3500 inclusive.
- `hazardClass` — string, one of `1`, `2.1`, `2.2`, `2.3`, `3`, `4.1`, `4.2`, `4.3`, `5.1`, `5.2`, `6.1`, `6.2`, `7`, `8`, `9`.
- `properShippingName` — string, 1 to 80 characters.

§5.7 **Type `LIQ`** — A liquid bulk container. Required additional fields:

- `substanceName` — string, 1 to 80 characters.
- `volumeLiters` — number, > 0.

§5.8 **Type `VEH`** — A vehicle carrier. Required additional fields:

- `vins` — array of strings, each string a 17-character VIN drawn from `[A-HJ-NPR-Z0-9]` (the letters I, O, and Q are not permitted in VINs). The array must contain exactly `quantity` entries.

§5.9 **Type `BALLAST`** — A placeholder declaration for vessels arriving without cargo. No additional fields are permitted. `quantity` must be 0 and `declaredValueUSD` must be 0.

---

## §6. Hazardous materials handling

§6.1 A Manifest declaring any container of type `HAZ` shall be flagged for the harbormaster's review prior to the vessel being granted permission to berth. The Authority will not reject a Manifest solely on the basis that it contains hazardous materials.

§6.2 The combined gross weight of `HAZ` containers on a single vessel may not exceed 25 percent of the vessel's `grossRegisterTons` reported in §4.1. A Manifest violating this proportion shall be rejected with code `H-201`.

§6.3 A `HAZ` container of class `7` (Radioactive Material) requires the Authority's prior written authorization, the reference number of which must be carried in an additional `priorAuthorizationRef` field on that container. Class 7 containers without a `priorAuthorizationRef` shall be rejected with code `H-204`.

§6.4 [Reserved.]

---

## §7. Cargo valuation

§7.1 The `declaredValueTotal` field in §3.2 shall equal the arithmetic sum of all `declaredValueUSD` values across all entries in the `containers` array. Sums must agree to the cent. Filers shall round each container's declared value to two decimal places using standard half-away-from-zero rounding before summing.

§7.2 Manifests in which `declaredValueTotal` does not equal the sum computed in §7.1, after rounding, shall be rejected with code `V-301`.

§7.3 The `declaredValueTotal` of a single Manifest may not exceed five hundred million U.S. dollars (USD 500,000,000.00). Manifests in excess of this threshold must be split across multiple arrival events at the discretion of the carrier.

---

## §8. Crew manifest

§8.1 The `crew` array shall contain one entry per individual aboard the vessel at the time of arrival, including the master, all officers, all ratings, and any non-crew personnel (e.g. supernumeraries, repair technicians, family members lawfully aboard).

§8.2 Each crew entry contains:

- `fullName` — string, 1 to 70 characters.
- `nationality` — string, ISO 3166-1 alpha-2 country code.
- `role` — string, one of `MASTER`, `OFFICER`, `RATING`, `OTHER`.
- `passportNumber` — string, 6 to 12 characters drawn from `[A-Z0-9]`.
- `dateOfBirth` — string, ISO 8601 date `YYYY-MM-DD`.

§8.3 Exactly one crew member with `role: MASTER` shall appear in every Manifest. Manifests with zero or more than one master shall be rejected with code `C-401`.

§8.4 Crew member ages on the date of arrival must be at least 16 years and not greater than 80 years. Manifests containing crew members outside this range shall be rejected with code `C-402`.

§8.5 The Authority does not enforce uniqueness of `passportNumber` within a Manifest, on the grounds that the same individual may legitimately appear twice (e.g. a master who is also recorded as an officer for the inbound leg). Filers should be aware that the Authority's downstream systems will surface any such duplication for the harbormaster's attention.

---

## §9. Filing windows and amendments

§9.1 An original Manifest must be transmitted no earlier than 96 hours and no later than 24 hours prior to the `eta` declared in §4.2. Manifests transmitted outside this window shall be rejected with code `T-501` (too early) or `T-502` (too late).

§9.2 [Reserved for future use. Filers may not assume that the timing thresholds in §9.1 will remain constant across specification versions.]

§9.3 An amended Manifest may be transmitted at any time after the original Manifest has been accepted, up to and including 4 hours past the actual time of arrival. Amendments are submitted using the same protocol as originals; the amended Manifest must reuse the original `manifestId` and additionally carry an `amendmentSequence` integer (starting at 1 for the first amendment, incrementing for each subsequent amendment of the same Manifest).

§9.4 The Authority does not specify the maximum number of amendments that may be applied to a single Manifest, nor does it require that an amendment differ in any specific way from the prior version. The Authority reserves the right to flag carriers whose amendment patterns appear designed to circumvent the timing thresholds in §9.1.

---

## §10. Submission protocol

§10.1 Manifests are transmitted to the Authority by HTTPS POST to the endpoint `https://customs.crescentharbor.example/v3/manifests`. The request body shall be the JSON document described in §3, encoded as UTF-8, with `Content-Type: application/json`.

§10.2 Each request shall additionally carry the following headers:

- `X-Crescent-FilerId` — the filer's `filerId` from §3.5.
- `X-Crescent-Timestamp` — the request timestamp as an integer count of seconds since the Unix epoch.
- `X-Crescent-Signature` — the filer's HMAC signature, computed as described in §10.3.

§10.3 The signature is the HMAC-SHA256 of the string formed by concatenating, with single newline (`\n`, U+000A) separators and no trailing newline:

1. The literal string `CHCAv3`
2. The HTTP method (`POST`)
3. The request path (`/v3/manifests`)
4. The value of the `X-Crescent-Timestamp` header
5. The lowercase hex SHA-256 digest of the request body bytes

The HMAC key is the filer's shared secret, issued by the Authority at the time of Direct Filer enrollment. The signature shall be encoded as lowercase hex (64 characters) and placed in the `X-Crescent-Signature` header.

§10.4 The Authority shall reject any request whose signature does not verify, whose timestamp differs from the Authority's clock by more than 300 seconds, or whose `filerId` is unknown. Rejected requests at the transport layer return HTTP 401 with a JSON body of the form `{"error": "<reason>"}` and do not produce an acknowledgment as defined in §11.

§10.5 The `filerSignature` object inside the Manifest body (§3.2) is *additional* to the HMAC signature on the HTTP request and is not the same thing. The `filerSignature` object is a record of who at the filer organization authorized the submission, intended to support audit; it has no cryptographic role. It contains:

- `signerName` — string, 1 to 70 characters.
- `signerTitle` — string, 1 to 70 characters.
- `signedAtUtc` — ISO 8601 timestamp in UTC, ending in `Z`.

---

## §11. Acknowledgments and rejection codes

§11.1 The Authority processes submitted Manifests asynchronously. A successful HTTPS POST as described in §10 receives an immediate HTTP 202 response containing a JSON body of the form:

```json
{ "receiptId": "<opaque>", "manifestId": "<as submitted>", "status": "RECEIVED" }
```

The `RECEIVED` status indicates only that the submission has been queued for processing; it does not indicate that the Manifest has been accepted.

§11.2 To retrieve the final disposition of a queued Manifest, the filer shall poll `GET https://customs.crescentharbor.example/v3/acks/{receiptId}` carrying the same `X-Crescent-FilerId`, `X-Crescent-Timestamp`, and `X-Crescent-Signature` headers (computed over the GET request — see §10.3). The response is one of:

- HTTP 200 with body `{"status": "PENDING"}` — processing not yet complete; poll again no sooner than 2 seconds later.
- HTTP 200 with body `{"status": "ACCEPTED", "manifestId": "...", "receiptId": "..."}` — the Manifest has been accepted.
- HTTP 200 with body `{"status": "REJECTED", "manifestId": "...", "receiptId": "...", "errors": [{"code": "...", "message": "..."}]}` — the Manifest has been rejected; the `errors` array enumerates the reasons.

§11.3 The Authority guarantees that a `PENDING` ack will reach a terminal state (`ACCEPTED` or `REJECTED`) within 30 seconds of `RECEIVED`. Filers should treat any `PENDING` state lasting longer than 60 seconds as an internal Authority error and contact the Direct Filer support desk.

§11.4 The complete catalog of rejection codes used in this specification is:

| Code | Meaning |
|---|---|
| `M-101` | Manifest body is not valid JSON |
| `M-102` | Manifest does not conform to the schema in §3 |
| `M-103` | Manifest contains unrecognized top-level fields |
| `M-104` | Duplicate manifestId within 90-day window for filer |
| `V-301` | Declared value total does not match sum of containers |
| `V-302` | Declared value total exceeds USD 500,000,000 |
| `H-201` | Hazmat gross weight exceeds 25% of vessel GRT |
| `H-204` | Class 7 hazmat without prior authorization reference |
| `C-401` | Manifest does not contain exactly one master |
| `C-402` | Crew member age outside permitted range |
| `T-501` | Manifest filed earlier than 96 hours before ETA |
| `T-502` | Manifest filed later than 24 hours before ETA |
| `R-601` | Vessel type / terminal mismatch |
| `R-602` | Container type-specific required field missing |
| `R-603` | IMO check digit invalid |
| `R-604` | Container ID duplicated within Manifest |
| `R-605` | VIN list length does not match container quantity |
| `R-606` | Reserved commodity code 0000 used on REF container |

§11.5 A single Manifest may be rejected with multiple codes simultaneously, and the `errors` array shall enumerate all violations the Authority detected, not merely the first.

---

## §12. Audit and retention

§12.1 Filers shall retain a copy of every Manifest they transmit, together with the receipt and final acknowledgment, for a period of not less than seven (7) years from the date of arrival. The Authority may at any time request the production of any retained record from the prior seven years.

§12.2 The Authority retains all received Manifests indefinitely. Filers wishing to retrieve a previously submitted Manifest must do so through the Direct Filer support desk; this is not an automated capability of the protocol described in §10.

§12.3 [End of specification.]
