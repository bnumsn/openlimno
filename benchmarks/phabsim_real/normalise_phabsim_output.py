"""Normalise HABTAE columnar output → phabsim_normalised.csv.

Per ADR-0012 R-PHABSIM-REAL track: the comparison harness
``test_real_run_matches.py`` consumes a 5-column CSV with schema:

    station_m, discharge_m3s, species, life_stage, wua_m2

This script reads HABTAE's raw columnar output (the format produced
by the USFWS PHABSIM Fortran binary) and converts it to that schema
so the harness can join cell-by-cell vs OpenLimno's ``Case.run``
output and assert Δ ≤ 1e-3.

PLACEHOLDER STATUS (2026-05-26): the actual HABTAE columnar layout is
documented in the USFWS PHABSIM user manual but the byte-for-byte
parse implementation requires access to a real HABTAE output to
confirm column positions, header lines, sentinel values, etc. This
script implements the EXPECTED structure based on the public manual
+ Bovee 1997 cookbook §5.1 reference traces, with `# TODO` markers
where the binary's actual output would resolve ambiguity.

The script is callable on its own (e.g. for a unit test that
provides a mock habtae.out string), AND invoked by ``run_phabsim.sh``
during the container pipeline.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


# HABTAE columnar layout per USFWS PHABSIM user manual (best-known
# public documentation). The actual binary output's exact column
# positions and any header-banner stripping requires verification
# against a real PHABSIM run on the Bovee §5.1 deck.
#
# Expected per-row structure:
#   STA   Q   SPECIES   LIFE_STAGE   CSI   AREA   WUA
# where CSI = composite suitability index in [0, 1]
#       AREA = cell area in m²
#       WUA = CSI × AREA in m²  (the column the harness compares on)
HABTAE_ROW_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<station>[+-]?\d+(?:\.\d+)?)\s+        # station_m
    (?P<q>[+-]?\d+(?:\.\d+)?)\s+              # discharge_m3s
    (?P<species>\S+)\s+                       # species token
    (?P<life_stage>\S+)\s+                    # life-stage token
    (?P<csi>[+-]?\d+(?:\.\d+)?)\s+            # composite suitability
    (?P<area>[+-]?\d+(?:\.\d+)?)\s+           # cell area m²
    (?P<wua>[+-]?\d+(?:\.\d+)?)               # weighted usable area m²
    \s*$
    """,
    re.VERBOSE,
)


def normalise_habtae_output(habtae_text: str) -> list[dict[str, str | float]]:
    """Parse HABTAE columnar text → list of normalised row dicts.

    Skips lines that:
      - Are empty
      - Start with non-data sentinels (page-break form-feed,
        HABTAE banner text like "HABTAE 5.0 ...", "TITLE...",
        "CASE...", etc.)
      - Don't match HABTAE_ROW_PATTERN

    The skipped-line policy is permissive on purpose: real HABTAE
    output is interleaved with banners and section headers. The row
    pattern is the only authoritative match.
    """
    rows: list[dict[str, str | float]] = []
    for raw_line in habtae_text.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith(("\x0c", "HABTAE", "TITLE", "CASE", "INPUT", "OUTPUT", " " * 40)):
            continue
        m = HABTAE_ROW_PATTERN.match(raw_line)
        if m is None:
            # Real HABTAE output has many non-row lines; ignore
            # silently to keep the normaliser robust against
            # banner / spacing drift.
            continue
        gd = m.groupdict()
        rows.append({
            "station_m": float(gd["station"]),
            "discharge_m3s": float(gd["q"]),
            "species": gd["species"],
            "life_stage": gd["life_stage"],
            "wua_m2": float(gd["wua"]),
        })
    return rows


def write_normalised_csv(rows: list[dict[str, str | float]], out_path: Path) -> None:
    """Write the 5-column normalised CSV that ``test_real_run_matches.py``
    expects."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["station_m", "discharge_m3s", "species", "life_stage", "wua_m2"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--habtae-out",
        type=Path,
        required=True,
        help="Path to HABTAE raw columnar output (the file run_phabsim.sh writes).",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        required=True,
        help="Path to the normalised CSV the comparison harness consumes.",
    )
    args = parser.parse_args()

    habtae_text = args.habtae_out.read_text(encoding="utf-8")
    rows = normalise_habtae_output(habtae_text)

    if not rows:
        raise SystemExit(
            f"ERROR: no HABTAE rows parsed from {args.habtae_out}. "
            f"Check the column layout against the actual binary's "
            f"output (USFWS PHABSIM user manual + a real ifg4/habtae "
            f"run on the Bovee §5.1 deck would resolve any ambiguity). "
            f"Update HABTAE_ROW_PATTERN in this file when the real "
            f"layout is confirmed."
        )

    write_normalised_csv(rows, args.csv_out)
    print(f"Wrote {len(rows)} normalised rows to {args.csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
