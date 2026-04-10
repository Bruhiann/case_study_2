#!/usr/bin/env bash
# Crescent Harbor Direct Filer — convenience wrapper.
#
# Usage:
#   bash run.sh                          # run all 8 scenarios, write results.json
#   bash run.sh --output PATH            # write results to a custom path
#   bash run.sh --scenario PATH          # run one scenario end-to-end
#   bash run.sh --scenario PATH --json   # also print the built manifest JSON
#
# With no arguments this script defaults to --all, which is the grading path.
# Any arguments are passed directly to filer/run.py, so all run.py flags work.
#
# The mock Authority must be running before executing this script.
# See RUNNING.md for startup instructions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ $# -eq 0 ]; then
    python filer/run.py --all
else
    python filer/run.py "$@"
fi
