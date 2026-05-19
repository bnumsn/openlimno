#!/usr/bin/env bash
# run_phabsim.sh — orchestrate the IFG4 → HABTAE pipeline inside the
# PHABSIM container. Placeholder (2026-05-20); the actual binary
# invocations are commented out until the source acquisition lands.
#
# Usage:
#   run_phabsim.sh <input_deck.dat> <output_dir>
#
# When complete, this script:
#   1. Validates input deck exists
#   2. Runs IFG4 (hydraulics) to produce velocity / depth per cell
#   3. Runs HABTAE (habitat) consuming IFG4 output + HSI curves
#   4. Writes a normalised CSV (station,Q,depth,velocity,HSI,WUA)
#      that test_real_run_matches.py can load and diff against
#      OpenLimno's Case.run output.

set -euo pipefail

INPUT_DECK="${1:-/work/inputs/bovee1997_5_1.dat}"
OUTPUT_DIR="${2:-/work/outputs}"

if [[ ! -f "$INPUT_DECK" ]]; then
    echo "ERROR: input deck not found at $INPUT_DECK" >&2
    echo "       (Sub-deliverable #3 of R-PHABSIM-REAL is pending;" >&2
    echo "       see benchmarks/phabsim_real/README.md.)" >&2
    exit 2
fi

mkdir -p "$OUTPUT_DIR"

echo "ERROR: run_phabsim.sh is a placeholder." >&2
echo "       The IFG4/HABTAE binaries are not yet built into this" >&2
echo "       container — see benchmarks/phabsim_real/Dockerfile and" >&2
echo "       README.md § 'USFWS PHABSIM source — license + acquisition'." >&2
exit 3

# When binaries are built into the container:
#
# # 1. Run IFG4 (hydraulics)
# cd "$OUTPUT_DIR"
# ifg4 < "$INPUT_DECK" > ifg4.out
#
# # 2. Run HABTAE (habitat) consuming IFG4 output
# habtae < ifg4.out > habtae.out
#
# # 3. Normalise to (station, Q, depth, velocity, hsi, wua) CSV.
# #    The format conversion script is itself part of the harness;
# #    not yet written. Tracking issue: R-PHABSIM-REAL #4.
# python3 /work/normalise_phabsim_output.py habtae.out > phabsim_normalised.csv
