"""
Crescent Harbor Direct Filer — CLI entry point.

Current capabilities (Phase 1):
  build     : assemble a complete manifest from a scenario input
  validate  : run JSON Schema validation against the built manifest

Planned (later phases):
  rules     : business rules engine
  transmit  : HMAC-signed submission to the Authority
  all       : run the full pipeline for all scenarios and write results.json

Usage:
  python run.py --scenario PATH          # build + validate a single scenario
  python run.py --scenario PATH --json   # print the built manifest as JSON
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from any working directory.
sys.path.insert(0, str(Path(__file__).parent))

from src import builder, validator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crescent Harbor Direct Filer",
    )
    parser.add_argument(
        "--scenario",
        metavar="PATH",
        required=True,
        help="Path to a scenario JSON file (e.g. scenarios/01-aurora-borealis.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="print_json",
        help="Print the built manifest as formatted JSON before validating",
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        print(f"ERROR: scenario file not found: {scenario_path}", file=sys.stderr)
        sys.exit(1)

    # ---- Build ----------------------------------------------------------------
    with scenario_path.open(encoding="utf-8") as f:
        scenario = json.load(f)

    manifest = builder.build(scenario)
    print(f"[builder]  manifestId       : {manifest['manifestId']}")
    print(f"[builder]  filer.filerId    : {manifest['filer']['filerId']}")
    print(f"[builder]  arrival.eta      : {manifest['arrival']['eta']}")
    print(f"[builder]  filerSignature   : signedAtUtc={manifest['filerSignature']['signedAtUtc']}")
    print(f"[builder]  vessel.name      : {manifest['vessel']['name']}")

    if args.print_json:
        print("\n--- built manifest ---")
        print(json.dumps(manifest, indent=2))
        print("--- end manifest ---\n")

    # ---- Schema validate -------------------------------------------------------
    schema_errors = validator.validate(manifest)
    if schema_errors:
        print(f"\n[validator] SCHEMA INVALID — {len(schema_errors)} error(s):")
        for e in schema_errors:
            print(f"  [{e['code']}] {e['path']}: {e['message']}")
        sys.exit(2)
    else:
        print("\n[validator] schema OK — manifest is schema-valid")

    print("\nPhase 1 complete. Rules engine and transmission not yet implemented.")


if __name__ == "__main__":
    main()
