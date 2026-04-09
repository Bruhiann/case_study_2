"""
Crescent Harbor Direct Filer — CLI entry point.

Current capabilities (Phases 1–2):
  build     : assemble a complete manifest from a scenario input
  validate  : run JSON Schema validation against the built manifest
  rules     : run all 25 business rules against the validated manifest

Planned (later phases):
  transmit  : HMAC-signed submission to the Authority
  all       : run the full pipeline for all scenarios and write results.json

Usage:
  python run.py --scenario PATH          # build + validate + rules check
  python run.py --scenario PATH --json   # also print the built manifest JSON
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from any working directory.
sys.path.insert(0, str(Path(__file__).parent))

from src import builder, rules, validator


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
    print(f"[builder]  manifestId    : {manifest['manifestId']}")
    print(f"[builder]  filer.filerId : {manifest['filer']['filerId']}")
    print(f"[builder]  arrival.eta   : {manifest['arrival']['eta']}")
    print(f"[builder]  signedAtUtc   : {manifest['filerSignature']['signedAtUtc']}")
    print(f"[builder]  vessel.name   : {manifest['vessel']['name']}")

    if args.print_json:
        print("\n--- built manifest ---")
        print(json.dumps(manifest, indent=2))
        print("--- end manifest ---\n")

    # ---- Schema validate ------------------------------------------------------
    schema_errors = validator.validate(manifest)
    if schema_errors:
        print(f"\n[validator] SCHEMA INVALID — {len(schema_errors)} error(s):")
        for e in schema_errors:
            print(f"  [{e['code']}] {e['path']}: {e['message']}")
        print("\nOutcome: rejected_by_schema")
        sys.exit(2)
    print("\n[validator] schema OK")

    # ---- Business rules -------------------------------------------------------
    rejections, warnings = rules.check(manifest)

    if warnings:
        print(f"\n[rules]    {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  [WARN {w.rule_id}] {w.field_path}: {w.message}")

    if rejections:
        print(f"\n[rules]    REJECTED — {len(rejections)} rule violation(s):")
        for r in rejections:
            print(f"  [FAIL {r.rule_id}] {r.field_path}: {r.message}")
        print("\nOutcome: rejected_by_rules")
        sys.exit(3)

    print(f"\n[rules]    all rules passed (0 rejections, {len(warnings)} warning(s))")
    print("\nOutcome: ready for transmission (Phase 3 not yet implemented)")


if __name__ == "__main__":
    main()
