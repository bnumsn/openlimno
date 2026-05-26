"""Unit test for the HABTAE → normalised-CSV parser.

Tests the parser against mock HABTAE output (since the real binary
isn't built yet per ADR-0012 R-PHABSIM-REAL track). When a real
HABTAE output becomes available, this test gets a golden file +
strict comparison.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the parent dir to sys.path so the script can be imported as a module.
sys.path.insert(0, str(Path(__file__).parent))
from normalise_phabsim_output import (  # noqa: E402
    HABTAE_ROW_PATTERN,
    normalise_habtae_output,
    write_normalised_csv,
)


def test_row_pattern_matches_canonical_layout() -> None:
    """The HABTAE_ROW_PATTERN must match a row in the canonical
    public-documented layout: STA Q SPECIES LIFE_STAGE CSI AREA WUA."""
    sample = "  100.000  1.500  oncorhynchus_mykiss  spawning  0.85  25.0  21.25"
    m = HABTAE_ROW_PATTERN.match(sample)
    assert m is not None
    assert m.group("station") == "100.000"
    assert m.group("q") == "1.500"
    assert m.group("species") == "oncorhynchus_mykiss"
    assert m.group("life_stage") == "spawning"
    assert m.group("wua") == "21.25"


def test_normaliser_skips_banner_and_blank_lines() -> None:
    """Real HABTAE output has interleaved banners; the normaliser
    must skip non-row lines silently."""
    habtae_text = """\
\x0c
HABTAE 5.0 — USFWS PHABSIM
TITLE   BOVEE 1997 COOKBOOK 5.1
CASE    BOVEE1997_5_1_OPENLIMNO_SYNTH

OUTPUT TABLE:

    0.000  0.500  oncorhynchus_mykiss  spawning  0.50  10.0  5.0
  100.000  0.500  oncorhynchus_mykiss  spawning  0.65  10.0  6.5
  200.000  1.500  oncorhynchus_mykiss  spawning  0.85  10.0  8.5

End of HABTAE output.
"""
    rows = normalise_habtae_output(habtae_text)
    assert len(rows) == 3
    assert rows[0]["station_m"] == 0.0
    assert rows[0]["discharge_m3s"] == 0.5
    assert rows[0]["wua_m2"] == 5.0
    assert rows[1]["wua_m2"] == 6.5
    assert rows[2]["wua_m2"] == 8.5


def test_normaliser_writes_5_column_csv(tmp_path: Path) -> None:
    """Output CSV schema must be station_m, discharge_m3s, species,
    life_stage, wua_m2 — matching test_real_run_matches.py expectation."""
    rows = [
        {
            "station_m": 0.0,
            "discharge_m3s": 1.5,
            "species": "oncorhynchus_mykiss",
            "life_stage": "spawning",
            "wua_m2": 21.25,
        },
    ]
    out = tmp_path / "normalised.csv"
    write_normalised_csv(rows, out)
    text = out.read_text(encoding="utf-8")
    header_line = text.splitlines()[0]
    assert header_line == "station_m,discharge_m3s,species,life_stage,wua_m2", (
        f"Schema mismatch: harness expects this exact 5-column header. "
        f"Got: {header_line!r}"
    )
    body_lines = text.splitlines()[1:]
    assert len(body_lines) == 1
    assert "oncorhynchus_mykiss" in body_lines[0]
    assert body_lines[0].endswith("21.25")


def test_empty_habtae_output_raises_at_main_level(tmp_path: Path) -> None:
    """If a malformed HABTAE output produces zero rows, the normaliser
    should produce zero rows + a higher-layer caller should error
    on the empty output. The pure parser doesn't error itself."""
    rows = normalise_habtae_output("\n\nHABTAE 5.0\nTITLE blah\n\n")
    assert rows == []
