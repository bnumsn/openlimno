"""Synthetic-archive coverage for ``studio_instream7_default``.

Claude's 2026-05-28 triple-AI review #3 flagged that the 460-line
core of ``studio_instream7_default.py`` had zero unit coverage —
the principal-axis projection, the ExampleB cell/GeoDataFrame
row-alignment block, the cm→mm abundance-weighted conversion, and
cohort emission all relied on the real GPL-3.0 archive (which is
gitignored), so any regression would silently pass CI.

This module ships a hand-built 2-reach × 2-species inSTREAM 7-shaped
archive that exercises every code path inside
``build_studio_scenario_from_instream7_archive`` without depending
on Cal Poly Humboldt's distribution.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixture: a tiny synthetic inSTREAM 7-shaped archive
# ---------------------------------------------------------------------------


_PARAMETER_FILE_TEMPLATE = """\
; Synthetic parameter file for OpenLimno unit tests
to set-parameters
  set start-date "10/1/2001"
  set end-date "9/30/2002"
  set GIS-file-name "{shapefile_rel}"
  set reach-names {reach_list}
  set time-series-input-files {ts_list}
  set depth-file-names {depth_list}
  set velocity-file-names {vel_list}
  set species-list {species_list}
  set initial-population-file "{init_pop_rel}"
  set trout-spawn-start-day (list time:create "4/1")
  set trout-spawn-end-day (list time:create "7/1")
  set trout-spawn-fecund-mult (list 1.0)
  set trout-spawn-fecund-exp (list 2.5)
  set trout-spawn-egg-viability (list 0.02)
  set trout-spawn-min-length (list 12)
  set trout-emerge-length-mode (list 2.8)
  set trout-weight-A (list 0.0124)
  set trout-weight-B (list 2.98)
  set trout-cmax-A (list 0.628)
  set trout-cmax-B (list -0.3)
  set trout-move-radius-max (list 100)
  set trout-move-radius-L1 (list 10)
  set trout-move-radius-L9 (list 50)
  set trout-resp-A (list 0.0001)
  set trout-resp-B (list 0.069)
  set trout-resp-C (list 0.041)
  set trout-resp-D (list 0.85)
  set mort-redd-dewater-surv (list 0.9)
  set mort-redd-scour-depth (list 1.5)
  set mort-high-temp-T1 (list 25)
  set mort-high-temp-T9 (list 28)
  set cmax-temperature-optimum 18
end
"""


def _quoted_list(values: list[str]) -> str:
    return "(list " + " ".join(f'"{v}"' for v in values) + ")"


def _write_hydraulic_matrix(path: Path, role: str, n_cells: int, *, first_cell_id: int) -> None:
    """Write a tiny depth/velocity matrix in the official format."""
    flows = [1.0, 5.0, 10.0]
    lines = [
        f"; Synthetic {role} file,,,,",
        ";",
        ";",
        f"{len(flows)},Number of flows in table,,,",
        "," + ",".join(str(f) for f in flows),
    ]
    rng = np.random.default_rng(seed=42 if role == "depth" else 7)
    for i in range(n_cells):
        cell_id = first_cell_id + i
        # Synthesize plausible monotone increase in depth/velocity vs flow
        base = 0.1 + 0.05 * i if role == "depth" else 0.2 + 0.05 * i
        values = [round(base + 0.1 * j + rng.uniform(0, 0.01), 4) for j in range(len(flows))]
        lines.append(f"{cell_id}," + ",".join(str(v) for v in values))
    path.write_text("\n".join(lines) + "\n")


def _write_timeseries(path: Path) -> None:
    lines = [
        "; Synthetic time series,,",
        ";,,",
        "Date,temperature,flow,turbidity",
    ]
    # Just 4 days — enough for ``ts.flow.median()`` etc. to work
    for day, t, q, tu in [
        ("10/1/2001 12:00", 12.0, 5.0, 2),
        ("10/2/2001 12:00", 12.2, 5.0, 2),
        ("10/3/2001 12:00", 12.4, 5.0, 2),
        ("10/4/2001 12:00", 12.5, 5.0, 2),
    ]:
        lines.append(f"{day},{t},{q},{tu}")
    path.write_text("\n".join(lines) + "\n")


def _write_initial_population(
    path: Path, rows: list[tuple[str, str, int, int, float, float, float]]
) -> None:
    lines = [
        "; Synthetic initial population,,,,,,",
        "; Species,Reach,Age,Number,Length min,Length mode,Length max",
    ]
    for species, reach, age, n, l_min, l_mode, l_max in rows:
        lines.append(f"{species},{reach},{age},{n},{l_min},{l_mode},{l_max}")
    path.write_text("\n".join(lines) + "\n")


def _write_shapefile(path: Path, *, reach_cells: dict[str, list[tuple[int, float, float]]]) -> None:
    """Write a tiny 2-reach shapefile via geopandas.

    ``reach_cells`` maps reach_id → list of (cell_id_int, x, y) for cell
    centroids. Each cell becomes a 2m square polygon centred at (x, y).
    """
    import geopandas as gpd
    from shapely.geometry import Polygon

    geometries: list[Polygon] = []
    attrs: list[dict[str, object]] = []
    for reach_id, cells in reach_cells.items():
        for cell_id, x, y in cells:
            geometries.append(
                Polygon([(x - 1, y - 1), (x + 1, y - 1), (x + 1, y + 1), (x - 1, y + 1)]),
            )
            attrs.append(
                {
                    "ID_TEXT": str(cell_id),
                    "REACH_NAME": reach_id,
                    "AREA": 4.0,
                    "NUM_HIDING": 2,
                    "FRACVSHL": 0.30,
                    "FRACSPWN": 0.10,
                }
            )
    gdf = gpd.GeoDataFrame(
        attrs, geometry=geometries, crs="EPSG:32610"
    )  # UTM zone 10N — projected, metres
    gdf.to_file(path)


@pytest.fixture
def synthetic_instream7_archive(tmp_path: Path) -> Path:
    """A 2-reach × 2-species synthetic archive in inSTREAM 7 layout.

    Layout::

        tmp_path/
          synthetic-case/
            parameters-synthetic.nls
            Synthetic-Shapefile/synthetic.shp + sidecars
            ReachA-Depths.csv
            ReachA-Vels.csv
            ReachA-TimeSeriesInputs.csv
            ReachB-Depths.csv
            ReachB-Vels.csv
            ReachB-TimeSeriesInputs.csv
            initial_population.csv

    Reach A has 4 cells centred along a roughly east-trending line;
    reach B has 3 cells along a north-trending line — different
    principal axes exercise the sign-convention logic.
    """
    # ``discover_instream7_cases`` only globs ``Example-Project-*/parameters-*.nls``,
    # so the directory must match that pattern.
    case_root = tmp_path / "Example-Project-Synthetic"
    case_root.mkdir()
    shp_dir = case_root / "Synthetic-Shapefile"
    shp_dir.mkdir()

    # Reach A: 4 cells along x-axis (axis points east)
    # Reach B: 3 cells along y-axis (axis points north)
    reach_cells = {
        "ReachA": [(1, 0.0, 0.0), (2, 5.0, 0.5), (3, 10.0, 0.0), (4, 15.0, 0.4)],
        "ReachB": [(101, 0.0, 0.0), (102, 0.2, 5.0), (103, 0.0, 10.0)],
    }
    _write_shapefile(shp_dir / "synthetic.shp", reach_cells=reach_cells)

    _write_hydraulic_matrix(case_root / "ReachA-Depths.csv", "depth", 4, first_cell_id=1)
    _write_hydraulic_matrix(case_root / "ReachA-Vels.csv", "velocity", 4, first_cell_id=1)
    _write_timeseries(case_root / "ReachA-TimeSeriesInputs.csv")

    _write_hydraulic_matrix(case_root / "ReachB-Depths.csv", "depth", 3, first_cell_id=101)
    _write_hydraulic_matrix(case_root / "ReachB-Vels.csv", "velocity", 3, first_cell_id=101)
    _write_timeseries(case_root / "ReachB-TimeSeriesInputs.csv")

    # 2 species × 3 ages × 2 reaches = 12 cohorts; per-reach abundance:
    #   ReachA: 50+50+10+50+50+10 = 220; ReachB: 30+30+5+30+30+5 = 130
    init_pop_rows: list[tuple[str, str, int, int, float, float, float]] = []
    for species in ["Rainbow", "Brown"]:
        init_pop_rows.append((species, "ReachA", 0, 50, 4.0, 6.0, 7.0))
        init_pop_rows.append((species, "ReachA", 1, 50, 9.0, 12.0, 15.0))
        init_pop_rows.append((species, "ReachA", 2, 10, 15.0, 18.0, 22.0))
        init_pop_rows.append((species, "ReachB", 0, 30, 4.0, 5.0, 6.0))
        init_pop_rows.append((species, "ReachB", 1, 30, 9.0, 11.0, 13.0))
        init_pop_rows.append((species, "ReachB", 2, 5, 15.0, 17.0, 20.0))
    _write_initial_population(case_root / "initial_population.csv", init_pop_rows)

    # Parameter file — paths are resolved relative to the archive ROOT
    # (tmp_path), so each rel path must include the case-directory prefix.
    rel_prefix = "Example-Project-Synthetic/"
    nls_body = _PARAMETER_FILE_TEMPLATE.format(
        shapefile_rel=f"{rel_prefix}Synthetic-Shapefile/synthetic.shp",
        reach_list=_quoted_list(["ReachA", "ReachB"]),
        ts_list=_quoted_list(
            [f"{rel_prefix}ReachA-TimeSeriesInputs.csv", f"{rel_prefix}ReachB-TimeSeriesInputs.csv"]
        ),
        depth_list=_quoted_list(
            [f"{rel_prefix}ReachA-Depths.csv", f"{rel_prefix}ReachB-Depths.csv"]
        ),
        vel_list=_quoted_list([f"{rel_prefix}ReachA-Vels.csv", f"{rel_prefix}ReachB-Vels.csv"]),
        species_list=_quoted_list(["Rainbow", "Brown"]),
        init_pop_rel=f"{rel_prefix}initial_population.csv",
    )
    (case_root / "parameters-synthetic.nls").write_text(nls_body)

    return tmp_path


# ---------------------------------------------------------------------------
# Fixture meta-test: archive discovery itself works
# ---------------------------------------------------------------------------


def test_synthetic_archive_discovers(synthetic_instream7_archive: Path) -> None:
    """The synthetic archive parses cleanly via the shared discovery path."""
    from openlimno.ibm.instream7 import discover_instream7_cases

    cases = discover_instream7_cases(synthetic_instream7_archive)
    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "synthetic"
    assert tuple(r.reach_id for r in case.reaches) == ("ReachA", "ReachB")
    assert case.species == ("Rainbow", "Brown")


# ---------------------------------------------------------------------------
# Core build path: projection + cohort emission + cm→mm conversion
# ---------------------------------------------------------------------------


def test_build_studio_scenario_from_synthetic_archive(
    synthetic_instream7_archive: Path,
) -> None:
    """End-to-end smoke through the full builder — covers _shapefile_axis_projection,
    cohort emission, cm→mm weighting, and the per-reach filter (A5 fix)."""
    from openlimno.ibm.studio_instream7_default import (
        build_studio_scenario_from_instream7_archive,
    )

    payload = build_studio_scenario_from_instream7_archive(
        synthetic_instream7_archive,
        case_id="synthetic",
    )

    # Reach selection: takes first reach only
    prov = payload["_provenance"]
    assert isinstance(prov, dict)
    assert prov["case_id"] == "synthetic"
    assert prov["reach_id"] == "ReachA"

    # Cells: 4 for ReachA (filter from total 7 in shapefile)
    cells = payload["cells"]
    assert isinstance(cells, list)
    assert len(cells) == 4

    # Per-reach cohort filter (A5 fix): 6 cohorts in ReachA, not all 12
    cohort_specs = payload["config"]["population_cohorts"]
    assert isinstance(cohort_specs, list)
    assert len(cohort_specs) == 6, (
        "expected 6 cohorts in ReachA (2 species × 3 ages); "
        f"got {len(cohort_specs)} — multi-reach filter regressed"
    )
    species_in_cohorts = {c["species"] for c in cohort_specs}
    assert species_in_cohorts == {"Rainbow", "Brown"}

    # Initial abundance equals the ReachA cohort sum: 2 × (50+50+10) = 220
    assert payload["config"]["initial_abundance"] == 220

    # cm→mm conversion sanity: weighted mean length should land between
    # smallest cohort mode (60 mm) and largest (180 mm), and reflect
    # the 50/50/10 abundance weighting → biased toward smaller modes.
    init_length_mm = float(payload["config"]["initial_length_mm"])
    # Hand-computed: (50*60 + 50*120 + 10*180 + 50*60 + 50*120 + 10*180) / 220
    expected = (50 * 60 + 50 * 120 + 10 * 180) * 2 / 220
    assert abs(init_length_mm - expected) < 0.01, (
        f"cm→mm conversion off: {init_length_mm} vs expected {expected}"
    )

    # Geometry: principal-axis projection should set ReachA station 0 at the
    # westmost cell (x=0). All cell station_m values should be in [0, ~15].
    cell_stations = sorted(float(c["station_m"]) for c in cells)
    assert cell_stations[0] == pytest.approx(0.0, abs=1e-3)
    assert 14.5 <= cell_stations[-1] <= 15.5


def test_cohort_population_dataframe_matches_synthetic_archive(
    synthetic_instream7_archive: Path,
) -> None:
    """Each cohort emits the right number of fish at the right lengths.

    This covers the cohort branch of build_initial_population that wasn't
    exercised before (Claude review #3 explicitly mentioned)."""
    from openlimno.ibm.native import SpeciesProfile, build_initial_population
    from openlimno.ibm.studio_instream7_default import (
        build_studio_scenario_from_instream7_archive,
    )

    payload = build_studio_scenario_from_instream7_archive(
        synthetic_instream7_archive,
        case_id="synthetic",
    )
    cohorts = payload["config"]["population_cohorts"]
    assert isinstance(cohorts, list)

    pop = build_initial_population(
        n=0,  # ignored when cohorts is supplied
        cohorts=cohorts,
        profile=SpeciesProfile(species="rainbow_trout"),
        rng=np.random.default_rng(seed=42),
    )

    # 220 individuals across 6 cohorts
    assert len(pop) == 220
    # Species split: ReachA has Rainbow 110 + Brown 110
    by_species = pop["species"].value_counts().to_dict()
    assert by_species == {"Rainbow": 110, "Brown": 110}
    # Triangular sampling: lengths bounded by cohort min/max envelopes
    # Smallest cohort min = 40 mm, largest max = 220 mm
    assert pop["length_mm"].min() >= 39.0
    assert pop["length_mm"].max() <= 221.0
    # Mass derives from length via the profile's weight_a/b — should be
    # positive and finite for every individual.
    assert (pop["mass_g"] > 0).all()
    assert np.isfinite(pop["mass_g"]).all()


def test_multi_reach_shapefile_row_alignment(
    synthetic_instream7_archive: Path,
) -> None:
    """A5 regression test: the shared 7-cell shapefile must align with
    the 4-cell ReachA cells_df. Previously this loop hit ``IndexError:
    iloc out-of-bounds`` because gdf had 7 rows and cells_df had 4."""
    from openlimno.ibm.studio_instream7_default import (
        build_studio_scenario_from_instream7_archive,
    )

    # Must build successfully — the IndexError would surface here.
    payload = build_studio_scenario_from_instream7_archive(
        synthetic_instream7_archive,
        case_id="synthetic",
    )
    # Cell IDs are prefixed with the case_id
    cell_ids = {c["cell_id"] for c in payload["cells"]}
    assert {f"synthetic-{i}" for i in (1, 2, 3, 4)} == cell_ids


def test_shapefile_axis_projection_axis_sign_is_deterministic(
    synthetic_instream7_archive: Path,
) -> None:
    """The eigh axis sign is fixed by the loader to point east-then-north.
    Two builds of the same archive must produce identical station_m
    values (deterministic across LAPACK builds)."""
    from openlimno.ibm.studio_instream7_default import (
        build_studio_scenario_from_instream7_archive,
    )

    p1 = build_studio_scenario_from_instream7_archive(
        synthetic_instream7_archive,
        case_id="synthetic",
    )
    p2 = build_studio_scenario_from_instream7_archive(
        synthetic_instream7_archive,
        case_id="synthetic",
    )
    s1 = [float(c["station_m"]) for c in p1["cells"]]
    s2 = [float(c["station_m"]) for c in p2["cells"]]
    assert s1 == s2


# ---------------------------------------------------------------------------
# counts_by_reach_and_species helper coverage (Claude review pinned this)
# ---------------------------------------------------------------------------


def test_counts_by_reach_and_species_mixed_columns() -> None:
    """Pin the 2026-05-28 multi-species attribution helper across the four
    column-presence combinations (both / reach only / species only / neither)."""
    from openlimno.ibm.events import counts_by_reach_and_species

    # Both columns present → real groupby
    both = pd.DataFrame(
        {
            "reach_id": ["A", "A", "B", "B"],
            "species": ["Rainbow", "Brown", "Rainbow", "Rainbow"],
        }
    )
    out = counts_by_reach_and_species(both, "default_r", "default_s")
    assert out == {("A", "Rainbow"): 1, ("A", "Brown"): 1, ("B", "Rainbow"): 2}

    # Reach only → default species
    reach_only = pd.DataFrame({"reach_id": ["A", "A", "B"]})
    out = counts_by_reach_and_species(reach_only, "default_r", "default_s")
    assert out == {("A", "default_s"): 2, ("B", "default_s"): 1}

    # Species only → default reach
    species_only = pd.DataFrame({"species": ["Rainbow", "Brown", "Brown"]})
    out = counts_by_reach_and_species(species_only, "default_r", "default_s")
    assert out == {("default_r", "Rainbow"): 1, ("default_r", "Brown"): 2}

    # Neither column → single default bucket
    neither = pd.DataFrame({"foo": [1, 2, 3]})
    out = counts_by_reach_and_species(neither, "default_r", "default_s")
    assert out == {("default_r", "default_s"): 3}

    # Empty → empty dict, not a default bucket
    assert counts_by_reach_and_species(pd.DataFrame(), "r", "s") == {}
