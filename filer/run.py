"""
Crescent Harbor Direct Filer — CLI entry point.

Usage
-----
Single scenario (full pipeline, with transmission):
  python filer/run.py --scenario scenarios/01-aurora-borealis.json

Single scenario (print built manifest JSON for inspection):
  python filer/run.py --scenario scenarios/01-aurora-borealis.json --json

All scenarios (writes results.json):
  python filer/run.py --all

All scenarios with a custom output path:
  python filer/run.py --all --output /tmp/my-results.json
"""

import argparse
import json
import sys
from pathlib import Path

# Make the filer package importable regardless of working directory.
sys.path.insert(0, str(Path(__file__).parent))

from src import builder, rules, validator
from src.client import PollTimeoutError, TransmissionError
from src.pipeline import run_all, run_scenario

# Default locations relative to the case-study root.
_REPO_ROOT      = Path(__file__).parent.parent
_SCENARIOS_DIR  = _REPO_ROOT / "scenarios"
_DEFAULT_OUTPUT = _REPO_ROOT / "results.json"


def _print_single(scenario_path: Path, print_json: bool) -> None:
    """
    Run the full pipeline for one scenario, printing step-by-step output.
    Useful for debugging.
    """
    # ---- Build ------------------------------------------------------------
    with scenario_path.open(encoding="utf-8") as f:
        scenario = json.load(f)
    manifest = builder.build(scenario)

    print(f"[builder]  manifestId    : {manifest['manifestId']}")
    print(f"[builder]  filer.filerId : {manifest['filer']['filerId']}")
    print(f"[builder]  arrival.eta   : {manifest['arrival']['eta']}")
    print(f"[builder]  signedAtUtc   : {manifest['filerSignature']['signedAtUtc']}")
    print(f"[builder]  vessel.name   : {manifest['vessel']['name']}")

    if print_json:
        print("\n--- built manifest ---")
        print(json.dumps(manifest, indent=2))
        print("--- end manifest ---\n")

    # ---- Schema -----------------------------------------------------------
    schema_errors = validator.validate(manifest)
    if schema_errors:
        print(f"\n[validator] SCHEMA INVALID — {len(schema_errors)} error(s):")
        for e in schema_errors:
            print(f"  [{e['code']}] {e['path']}: {e['message']}")
        print("\nOutcome: rejected_by_schema")
        sys.exit(2)
    print("\n[validator] schema OK")

    # ---- Rules ------------------------------------------------------------
    rejections, warnings = rules.check(manifest)
    if warnings:
        print(f"\n[rules]    {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  [WARN {w.rule_id}] {w.field_path}: {w.message}")
    if rejections:
        print(f"\n[rules]    REJECTED — {len(rejections)} violation(s):")
        for r in rejections:
            print(f"  [FAIL {r.rule_id}] {r.field_path}: {r.message}")
        print("\nOutcome: rejected_by_rules")
        sys.exit(3)
    print(f"\n[rules]    all rules passed ({len(warnings)} warning(s))")

    # ---- Transmit ---------------------------------------------------------
    print("\n[client]   submitting to Authority...")
    try:
        from src.client import poll_ack, submit
        receipt = submit(manifest)
        receipt_id = receipt["receiptId"]
        print(f"[client]   receiptId: {receipt_id} — polling for ack...")
        ack = poll_ack(receipt_id)
        status = ack["status"]
        print(f"[client]   ack status: {status}")
        if status == "ACCEPTED":
            print("\nOutcome: accepted")
        else:
            print(f"\n[client]   Authority errors: {ack.get('errors', [])}")
            print("\nOutcome: rejected_by_authority")
            sys.exit(4)
    except (TransmissionError, PollTimeoutError) as exc:
        print(f"\n[client]   ERROR: {exc}")
        print("\nOutcome: error")
        sys.exit(5)
    except Exception as exc:
        print(f"\n[client]   UNEXPECTED ERROR: {type(exc).__name__}: {exc}")
        print("\nOutcome: error")
        sys.exit(5)


def _print_all(output_path: Path) -> None:
    """
    Run all scenarios, print a summary table, and write results.json.
    """
    print(f"Running all scenarios in {_SCENARIOS_DIR}\n")
    results = run_all(_SCENARIOS_DIR)

    # Summary table
    col_w = max(len(r["scenario"]) for r in results) + 2
    print(f"{'Scenario':<{col_w}}  Outcome")
    print("-" * (col_w + 22))
    for r in results:
        print(f"{r['scenario']:<{col_w}}  {r['outcome']}")

    # Write results.json in Format B (list of result objects).
    # The grader reads "scenario" and "outcome" from each entry in "results".
    # Extra detail fields are included for human review and are ignored by
    # the grader per the case study brief.
    output = {"results": results}
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crescent Harbor Direct Filer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--scenario",
        metavar="PATH",
        help="Run the full pipeline for a single scenario file",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run all scenarios in scenarios/ and write results.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="print_json",
        help="(--scenario only) also print the built manifest as JSON",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=str(_DEFAULT_OUTPUT),
        help=f"(--all only) output path for results.json (default: {_DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if args.scenario:
        path = Path(args.scenario)
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        _print_single(path, args.print_json)
    else:
        _print_all(Path(args.output))


if __name__ == "__main__":
    main()
