"""SPEC §4.2.2.1 / ADR-0006 — HSI quality_grade watermark tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from openlimno.case import Case

CASE_YAML = Path(__file__).resolve().parents[2] / "examples" / "lemhi" / "case.yaml"


@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_wua_csv_has_grade_b_watermark_header_for_lemhi() -> None:
    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[1.0, 5.0, 12.0])
    csv_path = result.output_dir / "wua_q.csv"
    text = csv_path.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    # Lemhi HSI loaded as B grade (USFWS Blue Book transferred)
    assert first.startswith("#")
    assert "grade B" in first or "grade C" in first
    # Header must precede the column row
    second = text.splitlines()[1]
    assert second.startswith("discharge_m3s")


def test_grade_a_produces_no_watermark(tmp_path: Path) -> None:
    """Helper unit test on the static private method for A-grade."""
    from openlimno.case import Case as CaseClass

    # Use any Case object; only the helper is tested
    case = CaseClass(config={"case": {"name": "x"}}, case_yaml_path=tmp_path / "x.yaml")
    assert case._wua_csv_header("A") is None
    assert case._wua_csv_header("B").startswith("#")
    assert "TENTATIVE" in case._wua_csv_header("C")


@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_provenance_records_quality_grade() -> None:
    import json

    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0, 6.0])
    prov = json.loads(result.provenance_path.read_text())
    assert prov["wua_quality_grade"] in {"A", "B", "C"}


# ---------------------------------------------------------------------
# v0.6: fetch_summary + species-match warnings (WEDM v0.2 data blocks)
# ---------------------------------------------------------------------
@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_provenance_carries_fetch_summary_key() -> None:
    """fetch_summary must be present (possibly empty) so downstream
    tooling can rely on its existence. Lemhi has no v0.2 data.* blocks
    so the dict is empty, but the key MUST exist."""
    import json

    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0, 6.0])
    prov = json.loads(result.provenance_path.read_text())
    assert "fetch_summary" in prov, (
        "v0.6 regression: provenance.json must always carry "
        "fetch_summary, even on v0.1 cases"
    )
    assert isinstance(prov["fetch_summary"], dict)


def test_provenance_fetch_summary_picks_up_v02_data_blocks(tmp_path: Path) -> None:
    """v0.2 data.lulc + data.species_occurrences in the case.yaml must
    surface as provenance.fetch_summary keys, and a match_type=NONE +
    zero-occurrence species must emit both warnings.

    Calls _build_provenance directly to bypass the full hydraulic run
    (which would need a real mesh/cross_section). The helper is the
    actual code path that integrates v0.2 schema fields with
    provenance, so this is the unit under test.
    """
    yaml_text = """openlimno: '0.2'
case:
  name: v02_fetch_summary_check
  crs: EPSG:4326
  bbox: [100.10, 38.10, 100.30, 38.30]
mesh:
  uri: nonexistent.nc
hydrodynamics:
  backend: builtin-1d
habitat:
  species: [oncorhynchus_mykiss]
  stages: [spawning]
  metric: wua-q
  composite: min
data:
  lulc:
    uri: data/lulc_2021.tif
    year: 2021
    version: v200
    class_km2:
      "30": 288.14
  species_occurrences:
    uri: data/species_gbif_unknown.csv
    scientific_name: Frabnitzia notarealius
    usage_key: 1
    match_type: NONE
    confidence: 80
    occurrence_count_total: 0
    occurrence_count_returned: 0
output:
  dir: ./out
  formats: [csv]
"""
    yp = tmp_path / "v02_case.yaml"
    yp.write_text(yaml_text, encoding="utf-8")

    # Construct Case bypassing from_yaml's full load chain — only need
    # the case_yaml_path + name for _build_provenance to do its job.
    import yaml as _yaml
    cfg = _yaml.safe_load(yaml_text)
    case = Case(config=cfg, case_yaml_path=yp)

    prov = case._build_provenance(
        discharges=[3.0],
        sections=[],
        species=["oncorhynchus_mykiss"],
        stages=["spawning"],
        warnings=[],
    )

    # fetch_summary picks up both blocks
    assert "lulc" in prov["fetch_summary"]
    assert prov["fetch_summary"]["lulc"]["year"] == 2021
    assert prov["fetch_summary"]["lulc"]["version"] == "v200"
    sp = prov["fetch_summary"]["species_occurrences"]
    assert sp["scientific_name"] == "Frabnitzia notarealius"
    assert sp["match_type"] == "NONE"

    # Both warnings fire (NONE match + zero occurrences)
    joined = " ".join(prov["warnings"])
    assert "match_type=NONE" in joined, f"warnings={prov['warnings']}"
    assert "ZERO GBIF occurrences" in joined, f"warnings={prov['warnings']}"


# ---------------------------------------------------------------------
# v1.1.1: Case.run wires thermal HSI when both data blocks are present
# ---------------------------------------------------------------------
def test_v111_thermal_habitat_runs_when_fishbase_and_climate_present(tmp_path):
    """v1.1.1: a case with both data.fishbase_traits and data.climate
    triggers _maybe_run_thermal_habitat, which emits thermal_hsi.csv
    and folds metrics into provenance.thermal_metrics."""
    import json
    import pandas as pd

    # Build a synthetic climate CSV matching the Open-Meteo schema
    case_data_dir = tmp_path / "data"
    case_data_dir.mkdir()
    clim_df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=10, freq="D"
                              ).strftime("%Y-%m-%d"),
        "tmax_C": [10.0] * 10,
        "tmin_C": [6.0] * 10,
        "T_air_C_mean": [8.0] * 10,
        "T_water_C_stefan": [12.0] * 10,  # in Rainbow trout's optimum
    })
    clim_csv = case_data_dir / "climate_2024_2024.csv"
    clim_df.to_csv(clim_csv, index=False)

    # Synthetic v0.2 case.yaml
    yaml_text = f"""openlimno: '0.2'
case:
  name: thermal_pipeline_check
  crs: EPSG:4326
mesh:
  uri: nonexistent.nc
hydrodynamics:
  backend: builtin-1d
habitat:
  species: [oncorhynchus_mykiss]
  stages: [spawning]
  metric: wua-q
  composite: min
data:
  fishbase_traits:
    scientific_name: Oncorhynchus mykiss
    temperature_min_C: 9.0
    temperature_max_C: 18.0
  climate:
    uri: data/climate_2024_2024.csv
    source: open-meteo
    lat: 38.2
    lon: 100.2
    start_year: 2024
    end_year: 2024
output:
  dir: ./out
  formats: [csv]
"""
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text(yaml_text)

    case = Case.from_yaml(case_yaml)
    # Build provenance directly with thermal_metrics_dict computed by
    # the pipeline helper. This exercises the v1.1.1 path without
    # depending on a real mesh / cross_section.
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    thermal_metrics_dict = case._maybe_run_thermal_habitat(
        case.config, tmp_path, out_dir, warnings=[],
    )
    assert thermal_metrics_dict is not None
    # 12 °C is inside Oncorhynchus mykiss's 9-18 °C preferred range
    # → all 10 days should be optimal (SI = 1.0).
    assert thermal_metrics_dict["days_optimal"] == 10
    assert thermal_metrics_dict["days_total"] == 10
    assert thermal_metrics_dict["mean_SI"] == 1.0
    # And the per-day CSV was written
    out_csv = out_dir / "thermal_hsi.csv"
    assert out_csv.exists()
    out_df = pd.read_csv(out_csv)
    assert list(out_df.columns) == ["time", "T_water_C", "thermal_SI"]
    assert (out_df["thermal_SI"] == 1.0).all()


def test_v111_thermal_habitat_skipped_without_fishbase(tmp_path):
    """A v0.2 case with data.climate but no data.fishbase_traits must
    skip the thermal step cleanly (return None) — v1.0.x cases
    without FishBase still run unchanged."""
    yaml_text = """openlimno: '0.2'
case:
  name: no_thermal_check
  crs: EPSG:4326
mesh:
  uri: nonexistent.nc
hydrodynamics:
  backend: builtin-1d
habitat:
  species: [oncorhynchus_mykiss]
  stages: [spawning]
  metric: wua-q
  composite: min
data:
  climate:
    uri: data/climate.csv
    source: open-meteo
output:
  dir: ./out
  formats: [csv]
"""
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text(yaml_text)
    case = Case.from_yaml(case_yaml)
    metrics = case._maybe_run_thermal_habitat(
        case.config, tmp_path, tmp_path / "out", warnings=[],
    )
    assert metrics is None


def test_v111_provenance_always_contains_thermal_metrics_key():
    """Same regression-pin philosophy as fetch_summary: the key must
    exist even when None, so downstream tooling can rely on it."""
    import json
    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0])
    prov = json.loads(result.provenance_path.read_text())
    assert "thermal_metrics" in prov
    # Lemhi has no FishBase + climate blocks → None
    assert prov["thermal_metrics"] is None
