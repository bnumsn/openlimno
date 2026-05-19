"""v2.8.0: pin that ``examples/composite_hsi/`` runs end-to-end.

The composite_hsi example was upgraded in v2.8.0 from a synthetic-
DataFrame walkthrough of ``apply_overlay`` to a real ``Case.run``
workflow driven entirely by ``case.yaml`` + checked-in raster
fixtures. This test exercises that chain so a future regression in
``_maybe_compute_per_section_thermal_si_from_raster`` /
``_maybe_compute_per_section_cover_si_from_raster`` /
``_maybe_run_per_cell_composite`` doesn't break the example.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

EXAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "composite_hsi"
CASE_YAML = EXAMPLE_DIR / "case.yaml"


@pytest.mark.skipif(not CASE_YAML.exists(), reason="composite_hsi example missing")
def test_v280_composite_hsi_example_runs_end_to_end():
    """The dual-raster example must run with neither a thrown
    exception nor a silent overlay-skip. Pin: composite_summary is
    populated, the v2.7.0 cover raster contributed, the v2.6.0
    thermal raster contributed, and the per-cell composite arrays
    landed."""
    from openlimno.case import Case

    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=list(np.logspace(0, np.log10(30), 6)))

    # The composite step must have fired (R9-7 + v2.7.0 synth path).
    assert result.composite_summary is not None, (
        "v2.8.0 regression: composite step was silently skipped."
    )
    assert result.composite_wua_q is not None
    summary = result.composite_summary
    assert summary["method"] == "geom_mean_per_cell"

    # BOTH overlays must be present — that's the whole point of the
    # v2.8.0 example. A single missing overlay would shrink n_overlays
    # below 2 and indicate a thermal-or-cover wiring regression.
    assert summary["n_overlays"] == 2, (
        f"v2.8.0 expected n_overlays=2 (thermal + cover); got "
        f"{summary['n_overlays']}"
    )
    assert summary["cover_si"] is not None, (
        "v2.7.0 cover-raster path did not contribute to composite."
    )
    assert summary["thermal_si"] is not None, (
        "v2.6.0 thermal-raster path did not contribute to composite."
    )

    # Per-series composite must be populated for both species/stage
    # pairs the example declares.
    by_series = {
        row["species_stage"]: row for row in summary["by_species_stage"]
    }
    assert "oncorhynchus_mykiss_spawning" in by_series
    assert "oncorhynchus_mykiss_fry" in by_series
    for suffix, row in by_series.items():
        assert row["wua_m2_base_max"] > 0, f"empty base WUA for {suffix}"
        assert row["wua_m2_composite_max"] > 0, (
            f"empty composite WUA for {suffix} — per-cell path likely "
            f"failed silently."
        )


@pytest.mark.skipif(not CASE_YAML.exists(), reason="composite_hsi example missing")
def test_v280_composite_hsi_case_yaml_schema_valid():
    """The example case.yaml must validate against the WEDM schema —
    catches v2.6/v2.7 schema-key typos in the example."""
    from openlimno.wedm import validate_case

    errors = validate_case(CASE_YAML)
    assert errors == [], f"v2.8.0 case.yaml schema errors: {errors}"


@pytest.mark.skipif(not CASE_YAML.exists(), reason="composite_hsi example missing")
def test_v280_section_locations_matches_cross_section_count():
    """v2.6.0/v2.7.0 require ``section_locations`` row count to match
    the cross-section count. Pin that the example's fixtures stay in
    sync — a Lemhi cross_section.parquet refactor that adds/removes
    sections would otherwise silently break the example."""
    import pandas as pd

    from openlimno.case import Case
    from openlimno.hydro.builtin_1d import load_sections_from_parquet

    case = Case.from_yaml(CASE_YAML)
    xs_path = case._resolve(case.config["data"]["cross_section"])
    sections = load_sections_from_parquet(xs_path, manning_n=0.035)

    locs_uri = case.config["data"]["section_locations"]["uri"]
    locs_df = pd.read_csv(case._resolve(locs_uri))
    assert len(locs_df) == len(sections), (
        f"section_locations rows {len(locs_df)} != cross_section count "
        f"{len(sections)} — example fixtures are out of sync."
    )
