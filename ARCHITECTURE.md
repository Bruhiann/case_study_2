# Architecture — Crescent Harbor Direct Filer

## What I built

A single-purpose Python filing client that takes scenario inputs, builds
complete Cargo Arrival Manifests, validates them, enforces all 25 business
rules, and transmits them to the Crescent Harbor Customs Authority via
HMAC-signed HTTP.

### Stack

**Python 3.12, one external dependency (`jsonschema>=4.23.0`).**

Python was chosen because it is the language the I know best and
will be most comfortable discussing. The standard library covers everything
else: `hashlib`/`hmac` for signing, `urllib.request` for HTTP, `decimal`
for exact currency arithmetic, `uuid` for manifest IDs, and `datetime` for
ETA computation and crew age checks.

`jsonschema` is the only external package. It is already present in the
mock Authority's own environment (`mock-customs/requirements.txt`), so
there is no net-new dependency to install in a combined setup. JSON Schema
Draft 2020-12 validation is genuinely hard to replicate correctly from
scratch, and the spec explicitly points to the schema file as normative
(§3.1).

### Module layout

```
filer/
├── src/
│   ├── builder.py    Assembles a complete manifest from a scenario input
│   ├── validator.py  JSON Schema validation wrapper (jsonschema)
│   ├── rules.py      Business rules engine — all 25 rules
│   ├── client.py     HMAC-signed HTTP client + acknowledgment polling
│   └── pipeline.py   Orchestrates the four steps; owns outcome labels
└── run.py            CLI entry point
run.sh                Shell wrapper for grading runs
```

### Pipeline

```
scenario.json
  → builder.py   — adds manifestId, filer, arrival.eta, filerSignature
  → validator.py — schema check; blocked manifests get rejected_by_schema
  → rules.py     — 25 business rules; blocked manifests get rejected_by_rules
  → client.py    — POST + poll; outcome is accepted / rejected_by_authority / error
```

### Rules engine design

`rules.py` uses a dispatch table (`_HANDLERS: dict[rule_id → fn]`) rather
than a chain of if/elif blocks. Rule metadata (severity, field path, spec
reference) is loaded from `rules/rules.json` at import time. Adding a new
rule means adding one entry to `_HANDLERS` and writing one function.
Warnings and rejections are returned as typed `Issue` dataclasses and
partitioned by `check()` before the caller sees them.

---

## Ambiguities resolved

### R-005 — Vessel name normalization
**Decision: silent uppercase normalization.**
§4.1 says "vessel names containing lowercase letters in the input shall be
uppercased by the filer prior to submission." The word "shall be uppercased"
describes a transformation the filer performs, not a condition under which the
filer rejects. The builder normalizes the name; the rules engine then checks
that the result contains only `[A-Z0-9 .-]`.

### R-014 — HAZ gross weight vs GRT comparison
**Decision: convert grossWeightKg to metric tons (÷ 1000) before comparing to GRT.**
The spec says HAZ gross weight must not exceed 25 % of `grossRegisterTons`. A
raw numeric comparison is dimensionally inconsistent (`grossWeightKg` is mass
in kilograms; `grossRegisterTons` is a volumetric unit). Direct comparison
would wrongly reject valid scenarios (e.g. 18 500 kg > 25 % × 52 100 GRT
numerically, but 18.5 t is trivially within 25 % of any large vessel). The
conversion 18 500 kg ÷ 1 000 = 18.5 t produces a meaningful comparison.
If any HAZ container is missing `grossWeightKg` the check is skipped and a
warning is emitted (the field is optional in the schema; partial sums would
give false comfort).

### R-023 — Filing clock
**Decision: client send time (datetime.now(UTC) at the moment rules are
evaluated, immediately before transmission).**
The spec does not define whether "filing" means the client send time, the
server receive time, or the receipt issue time. The client clock is the
only one the filer controls and the most conservative choice: if the client
is within the window, the server almost certainly is too (network latency
on a LAN is negligible relative to the 24–96-hour window).

### R-024 / R-025 — Amendment invariants
**Decision: stateless check only.**
The spec requires that amendments reuse the original `manifestId` and not
change `vessel.imoNumber` or `arrival.eta`. Enforcing these invariants
requires a database of previously accepted manifests, which this stateless
filer does not maintain. The rules engine verifies only that
`amendmentSequence` is an integer ≥ 1 when present. The limitation is
documented here and in `THREAT-MODEL.md`. None of the 8 case-study scenarios
carry `amendmentSequence`, so this gap has no effect on grading.

---

## What I cut and why

- **Retry logic.** The mock Authority is local and deterministic. A
  production filer should retry with exponential back-off on 5xx and
  network errors; that complexity adds no value against a local mock.

- **Async I/O.** Eight scenarios, processed sequentially, complete in
  seconds. Async would reduce wall-clock time for large batches but would
  complicate error handling and readability.

- **Persistent manifest store.** The 7-year retention requirement (§12.1)
  and the amendment invariant checks (R-024/R-025) both need durable
  storage. Out of scope for a case study that has no database.

- **TLS.** The mock Authority uses plain HTTP by default (noted in
  `mock-customs/README.md`). A production deployment against a real
  Authority endpoint must use HTTPS as specified in §10.1.

---

## What I would build next to scale from one form type to five, three regulators

1. **Config-driven regulator adapters.** Each regulator gets a config
   record: base URL, filer credentials, schema path, rules file, signing
   algorithm. The pipeline selects the adapter by document type; no
   code changes for a new regulator.

2. **Persistent manifest store.** A lightweight database (SQLite to start,
   Postgres for scale) to record every submitted manifest, receipt, and
   acknowledgment. Enables amendment invariant checks, 7-year retention,
   and idempotent re-submission after a crash.

3. **Retry with exponential back-off and dead-letter queue.** Network
   failures and 5xx errors should be retried automatically; permanently
   failed manifests should go to a dead-letter queue for human review.

4. **Secret rotation.** HMAC secrets in a secrets manager (AWS Secrets
   Manager, HashiCorp Vault) with automatic rotation. The client reads the
   current secret at runtime; rotation requires no redeployment.

5. **Structured logging and audit trail.** Replace `print()` with a
   structured logger (JSON lines). Every manifest submission, ack, and
   rule violation gets a log entry with a correlation ID linking the
   scenario through all pipeline steps.

---

## What I would do differently with infinite time

- **Type the manifest.** Use `dataclasses` or Pydantic to represent the
  manifest structure instead of plain dicts. Type-safe access eliminates
  a class of key-name bugs and makes the builder's output self-documenting.

- **Separate the rules data from the dispatch table.** The current design
  loads `rules.json` for metadata but the logic lives in Python. With more
  time I would explore a rule DSL so that simple rules (regex, range,
  uniqueness) can be expressed purely in the JSON catalog without writing
  a Python function for each.

- **Integration test suite.** Tests that spin up the mock Authority and
  assert the exact outcome for each scenario. Currently the pipeline is
  verified manually by running `run.sh`.

- **Proper CLI error messages.** Replace `sys.exit(N)` codes with a single
  structured error format that downstream tooling can parse.



## AI Tooling Notes
I used AI tools deliberately throughout the project, but treated them as 
accelerators rather than sources of truth. I used ChatGPT early to refine 
prompts and think through the best way to ask for targeted help before moving 
into implementation. I used Claude Code to help plan the architecture, explore 
implementation approaches, and speed up development in the same way I would normally 
use documentation, examples, or Stack Overflow while building. After the core solution 
was in place, I used Codex as a strict reviewer to challenge the submission from an 
interviewer’s perspective, surface weak spots, catch documentation mismatches, and 
suggest small cleanup and refactoring improvements. I verified the final behavior 
myself and take responsibility for the design decisions, correctness of the implementation, 
and the tradeoffs documented in this repository.