# Crescent Harbor Direct Filer

A submission for the Crescent Harbor customs filing case study. This repository contains a Python-based end-to-end filer that builds manifests from the provided scenarios, validates them against the published JSON Schema, enforces the business rules catalog, signs and transmits them to the mock Authority endpoint, polls for acknowledgments, and writes a `results.json` report for all eight scenarios.

The implementation is intentionally production-shaped rather than prototype-shaped: the repository includes the filer, the original specification artifacts it depends on, runnable instructions, architecture notes, and a short threat model.

## What This Solution Covers

This project includes all required deliverables from the case study:

- Schema-driven manifest builder
- Business rules engine covering the published rule set
- HMAC-signed transmission client for the mock Authority
- End-to-end pipeline for all 8 scenarios
- `ARCHITECTURE.md`
- `THREAT-MODEL.md`
- `RUNNING.md`

## Repository Layout

```text
case-study/
├── filer/             # implementation
├── mock-customs/      # provided mock Authority endpoint
├── spec/              # provided filing specification
├── schema/            # provided JSON Schema
├── rules/             # provided business rules catalog
├── scenarios/         # provided input fixtures
├── run.sh             # single-command batch runner
├── RUNNING.md         # exact run instructions
├── ARCHITECTURE.md    # design/tradeoff writeup
├── THREAT-MODEL.md    # security/threat model writeup
└── results.json       # sample output report
```

## Quick Start

1. Start the mock Authority:

```bash
cd mock-customs
docker compose up --build
```

2. Install filer dependencies from the repository root:

```bash
pip install -r filer/requirements.txt
```

3. Run all scenarios:

```bash
bash run.sh
```

This writes `results.json` in the repository root.

For exact setup steps, single-scenario debugging, and troubleshooting, see [RUNNING.md](./RUNNING.md).

## Expected Outcomes

The pipeline evaluates all eight scenarios without hardcoding outcomes by filename.

Expected final outcomes:

- `accepted`: 6 scenarios
- `rejected_by_rules`: 1 scenario
- `rejected_by_schema`: 1 scenario

The output report uses the allowed Format B shape:

```json
{
  "results": [
    { "scenario": "01-aurora-borealis", "outcome": "accepted" }
  ]
}
```

Additional detail fields are included for human readability.

## Design Notes

A few specification points were intentionally ambiguous. I documented the decisions and tradeoffs in [ARCHITECTURE.md](./ARCHITECTURE.md), including:

- vessel-name normalization behavior
- hazmat weight interpretation
- filing-window clock choice
- amendment-rule limitations in a stateless implementation

Security and operational considerations are summarized in [THREAT-MODEL.md](./THREAT-MODEL.md).

## Original Case Study Materials

The original case study artifacts are preserved in this repository because the implementation depends on them directly:

- [spec/](./spec/)
- [schema/](./schema/)
- [rules/](./rules/)
- [scenarios/](./scenarios/)
- [mock-customs/](./mock-customs/)
