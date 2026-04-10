# Running the Crescent Harbor Direct Filer

## Prerequisites

- Python 3.12 or later (`python --version`)
- Docker and Docker Compose (for the mock Authority)
- `jsonschema` package: `pip install -r filer/requirements.txt`

---

## 1. Start the mock Authority endpoint

The mock Authority must be running before any scenario can be transmitted.

```bash
cd case-study/mock-customs
docker compose up --build
```

The mock listens on `http://localhost:8080`. You should see:

```text
[startup] Mock Crescent Harbor Customs listening on http://0.0.0.0:8080
[startup] Authorized filers: CHC100001
```

Leave this terminal open. The mock keeps state in memory; restarting it
clears the duplicate-manifest detection table.

**Without Docker** (development only):

```bash
cd case-study/mock-customs
pip install -r requirements.txt
CUSTOMS_SCHEMA_PATH=../schema/manifest.schema.json \
CUSTOMS_SECRETS_PATH=./secrets.json \
python server.py
```

---

## 2. Install filer dependencies

From the `case-study` root (one-time):

```bash
pip install -r filer/requirements.txt
```

If `jsonschema` is already installed at a compatible version you will see
"Requirement already satisfied."

---

## 3. Run a single scenario (debugging)

**Cross-platform (recommended):**

```bash
# Full pipeline - build, validate, rules check, transmit, poll for ack
python filer/run.py --scenario scenarios/01-aurora-borealis.json

# Also print the built manifest JSON for inspection
python filer/run.py --scenario scenarios/01-aurora-borealis.json --json

# A scenario that fails schema validation (no transmission)
python filer/run.py --scenario scenarios/08-polaris.json

# A scenario that fails business rules (no transmission)
python filer/run.py --scenario scenarios/07-tempest.json
```

**Bash-compatible environments only** (`bash`, Git Bash, macOS/Linux shell, WSL):

```bash
# Equivalent wrapper around the Python CLI
bash run.sh --scenario scenarios/01-aurora-borealis.json
bash run.sh --scenario scenarios/01-aurora-borealis.json --json
```

If `bash run.sh` fails on Windows with a WSL or shell error, use the
cross-platform `python filer/run.py ...` commands above instead.

Exit codes:
- `0` - accepted by Authority
- `2` - rejected by schema
- `3` - rejected by rules
- `4` - rejected by Authority
- `5` - network or unexpected error

---

## 4. Run all 8 scenarios and produce the report

**Cross-platform (recommended):**

```bash
python filer/run.py --all
```

**Bash-compatible environments only** (`bash`, Git Bash, macOS/Linux shell, WSL):

```bash
# Using the shell wrapper
bash run.sh
```

**Custom output path:**

```bash
python filer/run.py --all --output /tmp/results.json
```

`python filer/run.py --all` and `bash run.sh` write `results.json` to the
case-study root by default. A custom path may be provided with `--output`.
The file uses Format B as defined in the case study brief:

```json
{
  "results": [
    { "scenario": "01-aurora-borealis", "outcome": "accepted", "..." : "..." }
  ]
}
```

Each entry contains `scenario` and `outcome` (read by the grader) plus
additional detail fields (`manifestId`, `receiptId`, `warnings`, errors)
for human review.

---

## Expected outcomes

Six scenarios are accepted; two are rejected before transmission:

| Scenario | Expected outcome |
|---|---|
| 01-aurora-borealis | accepted |
| 02-pacific-crest   | accepted (R-015 warning: HAZ container present) |
| 03-star-of-helios  | accepted |
| 04-iron-brigade    | accepted |
| 05-silver-mariner  | accepted |
| 06-northern-lights | accepted (R-015 warning: HAZ container present) |
| 07-tempest         | rejected_by_rules (R-016: declared value total mismatch) |
| 08-polaris         | rejected_by_schema (M-102: PASSENGER is not a valid vessel type) |

The pipeline determines outcomes from the data; it does not look at
filenames to decide what to do.

---

## Troubleshooting

**`Connection refused` on submission**
The mock Authority is not running. Follow step 1 above.

**`HTTP 401: HMAC signature does not match`**
The filer secret does not match the mock's `secrets.json`. Override with:

```bash
CUSTOMS_FILER_SECRET="<secret>" python filer/run.py --scenario ...
```

**`HTTP 409: duplicate manifestId`**
A manifest with the same ID was already submitted in this mock session.
Restart the mock container to clear its in-memory duplicate table, then
re-run. This should be rare in this implementation because each run
generates a fresh UUID manifestId.

**Scenario produces `error` instead of expected outcome**
Check the mock Authority logs in the Docker terminal. The `error` field in
`results.json` contains the exception message.
