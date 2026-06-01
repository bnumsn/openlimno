#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${TMPDIR:-/tmp}/openlimno-fishtank-release-check"
mkdir -p "$OUT_DIR"

ruff check src/openlimno/fishtank tests/unit/test_fishtank_tier1.py
pytest -q tests/unit/test_fishtank_tier1.py
python -m openlimno.fishtank validate examples/fishtank/fishless_cycle.yaml
python -m openlimno.fishtank run examples/fishtank/fishless_cycle.yaml --out-dir "$OUT_DIR"

test -s "$OUT_DIR/timeseries.csv"
test -s "$OUT_DIR/events_log.csv"
test -s "$OUT_DIR/warnings.json"
test -s "$OUT_DIR/provenance.json"

echo "Fishtank release check passed. Outputs: $OUT_DIR"
