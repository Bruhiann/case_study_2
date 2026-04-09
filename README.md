# Case Study: Crescent Harbor Direct Filer

## The brief

You are interviewing for the role of the first software engineer on a new project. The company is enrolling in the Port of Crescent Harbor Customs Authority's **Direct Filer Program**, which requires us to electronically file Cargo Arrival Manifests for every commercial vessel calling at the Port of Crescent Harbor. We have the regulatory permissions in place. None of the software exists yet — no manifest builders, no schema validation, no transmission client, no test harness against the Authority's endpoint.

You are being asked to build the foundational components of that filer end-to-end against a mock Authority endpoint we ship inside this packet. Treat the code as production-shaped, not a prototype. We will read it that way.

The Crescent Harbor Manifest Filing Specification v3.0 — the document that defines the entire program — is in [`spec/manifest-filing-specification-v3.md`](./spec/manifest-filing-specification-v3.md). Read it before you write any code. It is intentionally dense; reading documents like this is part of the job.

---

## What's in this packet

```
case-study/
├── README.md         ← you are here
├── spec/             ← the Crescent Harbor Manifest Filing Specification v3.0
├── schema/           ← JSON Schema for the Manifest document
├── rules/            ← 25 business rules in prose and machine-readable form
├── scenarios/        ← 8 input fixtures you must run end-to-end
└── mock-customs/     ← Dockerized fake Customs Authority endpoint
```

The mock Authority endpoint is a real HTTP service implementing the protocol from §10 and §11 of the spec, including HMAC-SHA256 request signing. Connection details are in [`mock-customs/README.md`](./mock-customs/README.md).

The specification, the schema, and the rules are *real artifacts* in the sense that they completely describe what your filer must do. They are *fictional* in the sense that the Port of Crescent Harbor Customs Authority does not exist and the spec is invented for the purpose of this exercise. The fictional nature does not change the engineering work required.

---

## Required deliverables

You must hand back a single repository containing all of the following:

### 1. Schema-driven Manifest builder
Consume one of the input fixtures in `scenarios/` and emit a complete Manifest JSON document that validates against [`schema/manifest.schema.json`](./schema/manifest.schema.json) with zero errors. The manifest you produce must include all fields the spec requires — including the ones the input doesn't supply (`manifestId`, `filer`, `filerSignature`, the computed `eta`).

### 2. Business rules engine
Run all 25 rules in [`rules/rules.md`](./rules/rules.md) against a Manifest *before* it is transmitted. Rejections must surface as structured, actionable errors: rule ID, field path, and a human-readable message. Rules expressed as data — not as a wall of if-statements — is a positive signal.

A few of the rules are deliberately ambiguous. Decide what they mean, document your interpretation, move on. **Do not contact the Authority for clarification.** The Direct Filer support desk does not answer interpretation questions, only operational ones. Working from ambiguous regulatory prose is the job.

### 3. HMAC-signed transmission client
Against the mock Authority endpoint:
- Compute HMAC-SHA256 signatures per §10.3 of the spec
- POST manifests to `/v3/manifests`
- Poll `/v3/acks/{receiptId}` until you receive a terminal acknowledgment
- Parse the acknowledgment and surface errors meaningfully

The mock will reject any improperly signed request. Producing valid signatures is part of the test.

### 4. End-to-end pipeline
A single command (`./run.sh`, `make scenarios`, `npm run scenarios` — your call) that:
- Iterates over all 8 files in [`scenarios/`](./scenarios/)
- Builds, validates, rules-checks, signs, and transmits each one
- Polls for acknowledgments
- Writes a `results.json` file with one outcome per scenario

Six scenarios are designed to be accepted. Two are designed to be rejected — one for a rules violation and one for a schema violation. They are not labeled. Hardcoding which scenarios fail by filename is grounds for disqualification.

**The `results.json` file must use one of these two formats** (we have a grading script that reads it):

*Format A — flat object, one entry per scenario:*
```json
{
  "01-aurora-borealis": "accepted",
  "02-pacific-crest":   "accepted",
  "07-tempest":         "rejected_by_rules",
  "08-polaris":         "rejected_by_schema"
}
```

*Format B — list of result objects:*
```json
{
  "results": [
    { "scenario": "01-aurora-borealis", "outcome": "accepted" },
    { "scenario": "02-pacific-crest",   "outcome": "accepted" },
    { "scenario": "07-tempest",         "outcome": "rejected_by_rules" },
    { "scenario": "08-polaris",         "outcome": "rejected_by_schema" }
  ]
}
```

The five permitted outcome values are exactly:
- `accepted` — the Authority returned ACCEPTED
- `rejected_by_rules` — your rules engine blocked it before transmission
- `rejected_by_schema` — your JSON Schema validator blocked it before transmission
- `rejected_by_authority` — the Authority returned REJECTED
- `error` — anything unexpected (network failure, crash, etc.)

The scenario keys must match the input filenames in `scenarios/` (with or without the `.json` suffix — the grader accepts either). You may include additional detail fields alongside `outcome` in Format B if you want; the grader will ignore them but a human reading your output will appreciate them.

### 5. ARCHITECTURE.md (≤2 pages)
What you built. What you cut and why. What you would build next to scale this from a single-form filer to one that handles five document types from three different regulators. What you would do differently with infinite time. We want opinions, not a regurgitation of this brief.

### 6. Threat model (≤1 page)
Where does sensitive data live in your system? How is the HMAC secret handled? What does an audit trail look like? What does a security reviewer see when they read your code? Be concrete.

---

## Ground rules

- **Any language, any libraries.** Document your stack choice in `ARCHITECTURE.md` and tell us why.
- **AI coding tool use is expected and encouraged.** We expect you to use Claude Code, Cursor, Copilot, or a similar tool fluently. Claude Code is the preffered tool. Effectiveness with these tools is one of the most important things we're evaluating, because it is one of the most important skills the actual job will require. You own the correctness of every line, regardless of who or what wrote it. We will ask you about how you used the tools.
- **If the spec is ambiguous, decide and document.** Do not contact us. The spec has at least three intentional ambiguities. Finding them and resolving them with judgment is exactly the muscle we are testing.
- **Time budget: ~3–6 hours of focused work** This budget assumes you are using AI coding tools fluently. Reading the spec carefully and understanding what you're building is most of the work; the actual code, with AI assistance, comes together fast. If you find yourself spending more than 6 hours total, something is wrong. Either you are not using the tools we expect you to use, or you are over-engineering, or you are debugging the same problem in circles instead of stepping back. Any of those is a signal we want to know about. Tell us in your writeup if you went over and explain what happened. We would rather hire someone who finishes in 4 hours and tells us honestly than someone who quietly spends 20 and pretends it took 6.

---

## How to submit

A single Git repository containing all the deliverables above plus a `RUNNING.md` that explains how to:

1. Start the mock Authority endpoint
2. Run a single scenario for debugging
3. Run all 8 scenarios and produce the report

We will clone your repo, follow `RUNNING.md` exactly, and grade what we see. If the instructions don't work, we don't grade the rest. That's part of the test.

---

## What happens after you submit

1. We run your pipeline against the mock Authority and check that it produces the right outcome for all 8 scenarios.
2. We read your `ARCHITECTURE.md`, your threat model, and your code.
3. We schedule a follow-up where we walk through your case study together.

Good luck. We're excited to see what you build.
