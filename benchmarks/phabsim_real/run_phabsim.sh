#!/usr/bin/env bash
# benchmarks/phabsim_real/run_phabsim.sh — orchestrate IFG4 → HABTAE
# pipeline inside the PHABSIM container and emit a normalised CSV
# the comparison harness can diff against OpenLimno.
#
# Per ADR-0012 + ADR-0016 cleanup: until the USFWS PHABSIM source
# is acquired and the Dockerfile produces real ifg4/habtae binaries,
# this script runs in TWO MODES:
#
#   1. ``--check-only``  — exit 0 if all prerequisites are in place
#                           (binaries on PATH, input deck readable,
#                           output dir writable). For CI smoke
#                           without an actual run.
#   2. (default)         — run the full IFG4 → HABTAE → normalise
#                           pipeline. Exits 3 if binaries are
#                           missing (source acquisition gate).
#
# Usage:
#   run_phabsim.sh [--check-only] <input_deck.dat> [output_dir]
#
# Output:
#   <output_dir>/ifg4.out             — IFG4 raw output
#   <output_dir>/habtae.out           — HABTAE raw output
#   <output_dir>/phabsim_normalised.csv  — schema:
#       station_m, discharge_m3s, species, life_stage, wua_m2
#     (the schema test_real_run_matches.py joins on for the
#      cell-by-cell Δ ≤ 1e-3 comparison).

set -euo pipefail

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then
    CHECK_ONLY=1
    shift
fi

INPUT_DECK="${1:-/work/inputs/bovee1997_5_1.dat}"
OUTPUT_DIR="${2:-/work/outputs}"

# Resolve input deck (allow paths relative to script dir for host-side use)
if [[ ! -f "$INPUT_DECK" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "$SCRIPT_DIR/inputs/$(basename "$INPUT_DECK")" ]]; then
        INPUT_DECK="$SCRIPT_DIR/inputs/$(basename "$INPUT_DECK")"
    else
        echo "ERROR: input deck not found at $INPUT_DECK" >&2
        echo "       Expected at /work/inputs/<deck>.dat (container)" >&2
        echo "       OR at <repo>/benchmarks/phabsim_real/inputs/<deck>.dat (host)" >&2
        exit 2
    fi
fi

mkdir -p "$OUTPUT_DIR"

echo "==> Input deck: $INPUT_DECK"
echo "==> Output dir: $OUTPUT_DIR"
echo "==> Mode: $([ $CHECK_ONLY -eq 1 ] && echo 'check-only' || echo 'full-run')"

# --- Prerequisite check ---
MISSING=()
for binary in ifg4 habtae habef; do
    if ! command -v "$binary" >/dev/null 2>&1; then
        MISSING+=("$binary")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "" >&2
    echo "ERROR: required PHABSIM binaries missing from PATH: ${MISSING[*]}" >&2
    echo "       These are produced by benchmarks/phabsim_real/Dockerfile" >&2
    echo "       which requires PHABSIM_SRC_URL + PHABSIM_SRC_SHA256 build args." >&2
    echo "       See benchmarks/phabsim_real/README.md § 'USFWS PHABSIM source'." >&2
    if [[ $CHECK_ONLY -eq 1 ]]; then
        exit 3
    else
        echo "       Aborting; run with --check-only to test the harness without binaries." >&2
        exit 3
    fi
fi

if [[ $CHECK_ONLY -eq 1 ]]; then
    echo "==> ✓ All prerequisites OK (input deck readable, output dir writable, IFG4/HABTAE/HABEF binaries on PATH)"
    exit 0
fi

# --- Full run: IFG4 → HABTAE → normalise ---

# Step 1: Run IFG4 (hydraulics)
echo "==> [1/3] Running IFG4 (hydraulics)..."
cd "$OUTPUT_DIR"
ifg4 < "$INPUT_DECK" > ifg4.out
echo "    IFG4 wrote $(wc -l < ifg4.out) lines to ifg4.out"

# Step 2: Run HABTAE (habitat)
echo "==> [2/3] Running HABTAE (habitat)..."
habtae < ifg4.out > habtae.out
echo "    HABTAE wrote $(wc -l < habtae.out) lines to habtae.out"

# Step 3: Normalise HABTAE columnar output into the harness CSV schema.
echo "==> [3/3] Normalising HABTAE output to phabsim_normalised.csv..."
python3 "$(dirname "$INPUT_DECK")/../normalise_phabsim_output.py" \
    --habtae-out "$OUTPUT_DIR/habtae.out" \
    --csv-out "$OUTPUT_DIR/phabsim_normalised.csv"

ROWS=$(($(wc -l < "$OUTPUT_DIR/phabsim_normalised.csv") - 1))
echo "    Normalised $ROWS rows to $OUTPUT_DIR/phabsim_normalised.csv"

# Manifest line for the comparison harness
echo "==> Output schema: station_m, discharge_m3s, species, life_stage, wua_m2"
echo "==> Done."
