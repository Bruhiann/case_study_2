# Mock Crescent Harbor Customs Authority Endpoint

A standalone Dockerized HTTPS service that mimics the protocol described in §10 and §11 of the Crescent Harbor Manifest Filing Specification v3.0.

## What it implements

- `POST /v3/manifests` — accepts a Cargo Arrival Manifest, returns 202 with a receipt ID
- `GET /v3/acks/{receiptId}` — polls for the final disposition of a previously submitted manifest

Both endpoints require HMAC-SHA256 authentication via the `X-Crescent-FilerId`, `X-Crescent-Timestamp`, and `X-Crescent-Signature` headers as described in §10.3.

## What it does on submission

1. Verifies the HMAC signature against the filer's shared secret
2. Verifies the timestamp is within ±5 minutes of server time
3. Detects duplicate `(filerId, manifestId)` tuples (§3.4)
4. Validates the body against `schema/manifest.schema.json`
5. Queues an acknowledgment of `ACCEPTED` (schema clean) or `REJECTED` (schema violations) for retrieval via `GET /v3/acks/{receiptId}`

The mock does **not** enforce the business rules in `rules/rules.md` — that's the candidate's job. The mock only validates the schema. A correctly built filer will catch business-rule violations *before* transmission and never send a violating manifest to the mock at all.

## Running

For grading runs:

```bash
cd case-study/mock-customs
docker compose up --build
```

The mock listens on `http://localhost:8080`. Ports, paths, and the HMAC secret are documented in [secrets.json](./secrets.json).

For development without Docker:

```bash
cd case-study/mock-customs
python3 -m pip install -r requirements.txt
CUSTOMS_SCHEMA_PATH=../schema/manifest.schema.json \
CUSTOMS_SECRETS_PATH=./secrets.json \
python3 server.py
```

## Connection details for the candidate

- Base URL: `http://localhost:8080`
- Filer ID: `CHC100001`
- HMAC shared secret: see [secrets.json](./secrets.json) (in real production this would be issued out-of-band by the Authority)
- Both endpoints expect HMAC headers per §10.3 of the spec

## Caveats

- This is a hiring case study, not a production simulator. Real customs systems have far more robust auth, retry semantics, and reject catalogs.
- The mock keeps state in memory only. Restarting the container clears the duplicate-detection table.
- The mock does **not** use TLS by default — it's plain HTTP for grader convenience. The spec describes HTTPS, and a candidate who notices and asks about the discrepancy is showing good judgment; document the assumption in `ARCHITECTURE.md`.
