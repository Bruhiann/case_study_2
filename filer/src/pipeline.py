"""
End-to-end filing pipeline.

Orchestrates the four steps for each scenario:
  1. Build   — assemble a complete manifest from scenario input (builder.py)
  2. Schema  — validate against the Authority's JSON Schema (validator.py)
  3. Rules   — enforce all 25 business rules (rules.py)
  4. Transmit — HMAC-sign, POST, poll for acknowledgment (client.py)

Outcome labels (exactly as required by the case study grader):
  "accepted"               — Authority returned ACCEPTED
  "rejected_by_schema"     — JSON Schema validation blocked transmission
  "rejected_by_rules"      — business rules engine blocked transmission
  "rejected_by_authority"  — transmitted; Authority returned REJECTED
  "error"                  — unexpected failure (network, crash, etc.)

Neither run_scenario() nor run_all() references scenario filenames or
expected outcomes. Outcomes are determined entirely by the pipeline logic.
"""

import json
import urllib.error
from pathlib import Path

from src import builder, rules, validator
from src.client import PollTimeoutError, TransmissionError, poll_ack, submit

# The five permitted outcome strings (case study §4, results.json spec)
ACCEPTED              = "accepted"
REJECTED_BY_SCHEMA    = "rejected_by_schema"
REJECTED_BY_RULES     = "rejected_by_rules"
REJECTED_BY_AUTHORITY = "rejected_by_authority"
ERROR                 = "error"


def run_scenario(scenario_path: Path) -> dict:
    """
    Run the full pipeline for a single scenario file.

    :param scenario_path: Path to a scenario JSON file.
    :returns: A result dict containing at minimum "scenario" and "outcome".
              Additional fields (manifestId, receiptId, errors, warnings) are
              included for human readability; the grader ignores them.
    """
    scenario_name = scenario_path.stem   # filename without .json

    try:
        # ---- 1. Build ---------------------------------------------------
        with scenario_path.open(encoding="utf-8") as f:
            scenario = json.load(f)
        manifest = builder.build(scenario)

        # ---- 2. Schema validation ----------------------------------------
        schema_errors = validator.validate(manifest)
        if schema_errors:
            return {
                "scenario": scenario_name,
                "outcome": REJECTED_BY_SCHEMA,
                "schemaErrors": schema_errors,
            }

        # ---- 3. Business rules -------------------------------------------
        rejections, warnings = rules.check(manifest)
        if rejections:
            return {
                "scenario": scenario_name,
                "outcome": REJECTED_BY_RULES,
                "ruleViolations": [r.to_dict() for r in rejections],
                "warnings":       [w.to_dict() for w in warnings],
            }

        # ---- 4. Transmit -------------------------------------------------
        receipt = submit(manifest)
        receipt_id = receipt["receiptId"]
        ack = poll_ack(receipt_id)

        if ack["status"] == "ACCEPTED":
            return {
                "scenario":   scenario_name,
                "outcome":    ACCEPTED,
                "manifestId": manifest["manifestId"],
                "receiptId":  receipt_id,
                "warnings":   [w.to_dict() for w in warnings],
            }
        else:
            return {
                "scenario":  scenario_name,
                "outcome":   REJECTED_BY_AUTHORITY,
                "receiptId": receipt_id,
                "errors":    ack.get("errors", []),
            }

    except (TransmissionError, PollTimeoutError, urllib.error.URLError) as exc:
        return {
            "scenario": scenario_name,
            "outcome":  ERROR,
            "error":    str(exc),
        }
    except Exception as exc:
        return {
            "scenario": scenario_name,
            "outcome":  ERROR,
            "error":    f"{type(exc).__name__}: {exc}",
        }


def run_all(scenarios_dir: Path) -> list[dict]:
    """
    Run the pipeline for every scenario JSON file in scenarios_dir.

    Files are processed in lexicographic order. Files whose names start with
    '_' or '.' are skipped (they are not scenario inputs).

    :param scenarios_dir: Directory containing scenario JSON files.
    :returns: List of result dicts, one per scenario.
    """
    scenario_files = sorted(
        p for p in scenarios_dir.glob("*.json")
        if not p.name.startswith(("_", "."))
    )

    results = []
    for path in scenario_files:
        result = run_scenario(path)
        results.append(result)

    return results
