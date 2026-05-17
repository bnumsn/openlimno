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
    yaml_text = """openlimno: '0.2'
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


# ---------------------------------------------------------------------
# v1.1.2: occurrence-density tiers + species_occurrences.density_class
# ---------------------------------------------------------------------
def _make_v02_case_with_species_count(tmp_path: Path, count_total: int) -> Path:
    yaml_text = f"""openlimno: '0.2'
case:
  name: density_check
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
  species_occurrences:
    uri: data/sp.csv
    scientific_name: Salmo trutta
    usage_key: 8215487
    match_type: EXACT
    confidence: 99
    occurrence_count_total: {count_total}
    occurrence_count_returned: {min(count_total, 300)}
output:
  dir: ./out
  formats: [csv]
"""
    yp = tmp_path / f"case_{count_total}.yaml"
    yp.write_text(yaml_text)
    return yp


def test_v112_density_class_dense_above_100(tmp_path):
    import yaml as _yaml
    yp = _make_v02_case_with_species_count(tmp_path, 5000)
    cfg = _yaml.safe_load(yp.read_text())
    case = Case(config=cfg, case_yaml_path=yp)
    prov = case._build_provenance(
        discharges=[3.0], sections=[],
        species=["oncorhynchus_mykiss"], stages=["spawning"],
        warnings=[],
    )
    assert prov["fetch_summary"]["species_occurrences"]["density_class"] == "dense"


def test_v112_density_class_thin_between_10_and_99(tmp_path):
    import yaml as _yaml
    yp = _make_v02_case_with_species_count(tmp_path, 50)
    cfg = _yaml.safe_load(yp.read_text())
    case = Case(config=cfg, case_yaml_path=yp)
    prov = case._build_provenance(
        discharges=[3.0], sections=[],
        species=["oncorhynchus_mykiss"], stages=["spawning"],
        warnings=[],
    )
    assert prov["fetch_summary"]["species_occurrences"]["density_class"] == "thin"
    # No sparse / absent warning at 50 records
    joined = " ".join(prov["warnings"])
    assert "ZERO GBIF" not in joined
    assert "extrapolating beyond observed range" not in joined


def test_v112_density_class_sparse_below_10_warns(tmp_path):
    import yaml as _yaml
    yp = _make_v02_case_with_species_count(tmp_path, 5)
    cfg = _yaml.safe_load(yp.read_text())
    case = Case(config=cfg, case_yaml_path=yp)
    prov = case._build_provenance(
        discharges=[3.0], sections=[],
        species=["oncorhynchus_mykiss"], stages=["spawning"],
        warnings=[],
    )
    assert prov["fetch_summary"]["species_occurrences"]["density_class"] == "sparse"
    joined = " ".join(prov["warnings"])
    assert "extrapolating beyond observed range" in joined
    assert "TENTATIVE" in joined


def test_v112_density_class_absent_at_zero_keeps_v06_warning(tmp_path):
    import yaml as _yaml
    yp = _make_v02_case_with_species_count(tmp_path, 0)
    cfg = _yaml.safe_load(yp.read_text())
    case = Case(config=cfg, case_yaml_path=yp)
    prov = case._build_provenance(
        discharges=[3.0], sections=[],
        species=["oncorhynchus_mykiss"], stages=["spawning"],
        warnings=[],
    )
    assert prov["fetch_summary"]["species_occurrences"]["density_class"] == "absent"
    # v0.6 warning still fires
    joined = " ".join(prov["warnings"])
    assert "ZERO GBIF occurrences" in joined


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


# ---------------------------------------------------------------------
# v1.5.0: Case.run wires cover SI when data.lulc + data.watershed present
# ---------------------------------------------------------------------
def _make_cover_test_inputs(tmp_path: Path):
    """Build a tiny WorldCover GeoTIFF + watershed GeoJSON inside
    tmp_path/data/, return (lulc_uri, watershed_uri) as case-relative
    strings."""
    import numpy as _np
    import rasterio
    from rasterio.transform import from_origin
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # 100% tree cover (LCCS 10) → SI=1.0 in DEFAULT_RIPARIAN_COVER_SI
    arr = _np.full((20, 20), 10, dtype=_np.uint8)
    tif = data_dir / "lulc.tif"
    with rasterio.open(
        tif, "w", driver="GTiff", height=20, width=20, count=1,
        dtype="uint8", crs="EPSG:4326",
        transform=from_origin(100.0, 38.0, 5e-5, 5e-5),
    ) as dst:
        dst.write(arr, 1)
    # Polygon covering the raster extent
    import json as _json
    ws = data_dir / "watershed.geojson"
    ws.write_text(_json.dumps({
        "type": "Feature",
        "properties": {"area_km2": 0.01},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [100.0, 38.0 - 20 * 5e-5],
                [100.0 + 20 * 5e-5, 38.0 - 20 * 5e-5],
                [100.0 + 20 * 5e-5, 38.0],
                [100.0, 38.0],
                [100.0, 38.0 - 20 * 5e-5],
            ]],
        },
    }))
    return "data/lulc.tif", "data/watershed.geojson"


def test_v150_cover_habitat_runs_when_lulc_and_watershed_present(tmp_path):
    """All-tree raster + bounding watershed → cover SI = 1.0;
    cover_si.json emitted; metrics dict returned."""
    import json

    import yaml as _yaml
    lulc_uri, ws_uri = _make_cover_test_inputs(tmp_path)
    yaml_text = f"""openlimno: '0.2'
case:
  name: cover_pipeline_check
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
  lulc:
    uri: {lulc_uri}
    year: 2021
    version: v200
  watershed:
    uri: {ws_uri}
    pour_lat: 38.0
    pour_lon: 100.0
output:
  dir: ./out
  formats: [csv]
"""
    yp = tmp_path / "case.yaml"
    yp.write_text(yaml_text)
    cfg = _yaml.safe_load(yaml_text)
    case = Case(config=cfg, case_yaml_path=yp)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    metrics = case._maybe_run_cover_habitat(
        case.config, tmp_path, out_dir, warnings=[],
    )
    assert metrics is not None
    assert metrics["mean_si"] == pytest.approx(1.0)
    assert metrics["n_classes"] == 1
    assert metrics["total_pixels"] == 400
    # Per-class JSON payload was written
    cover_json = out_dir / "cover_si.json"
    assert cover_json.exists()
    payload = json.loads(cover_json.read_text())
    assert payload["mean_si"] == 1.0
    assert len(payload["classes"]) == 1
    assert payload["classes"][0]["class_code"] == 10
    assert payload["classes"][0]["cover_si"] == 1.0
    assert payload["classes"][0]["pixel_count"] == 400


def test_v150_cover_habitat_skipped_when_watershed_missing(tmp_path):
    """Mirrors v1.1.1: cases without one of the two blocks must
    short-circuit cleanly (None return, no exception)."""
    yaml_text = """openlimno: '0.2'
case:
  name: no_cover_check
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
  lulc:
    uri: data/lulc.tif
    year: 2021
    version: v200
output:
  dir: ./out
  formats: [csv]
"""
    yp = tmp_path / "case.yaml"
    yp.write_text(yaml_text)
    case = Case.from_yaml(yp)
    metrics = case._maybe_run_cover_habitat(
        case.config, tmp_path, tmp_path / "out", warnings=[],
    )
    assert metrics is None


def test_v150_provenance_always_contains_cover_metrics_key():
    """Same regression-pin philosophy as thermal_metrics: cover_metrics
    must exist (None when no LULC × watershed), so downstream tooling
    can rely on the dict shape."""
    import json
    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0])
    prov = json.loads(result.provenance_path.read_text())
    assert "cover_metrics" in prov
    assert prov["cover_metrics"] is None


# ---------------------------------------------------------------------
# v1.6.0 — multivariate HSI composite (depth × velocity × cover × thermal)
# ---------------------------------------------------------------------
def test_v160_overlay_from_metrics_handles_both_overlays():
    """``CompositeOverlay.from_metrics`` resolves a product of two
    scalar overlays when both thermal_metrics and cover_metrics are
    present."""
    from openlimno.habitat.composite import CompositeOverlay

    overlay = CompositeOverlay.from_metrics(
        thermal_metrics={"mean_SI": 0.6},
        cover_metrics={"mean_si": 0.5},
    )
    assert overlay.cover_si == pytest.approx(0.5)
    assert overlay.thermal_si == pytest.approx(0.6)
    assert overlay.overlay_si == pytest.approx(0.3)
    assert overlay.n_overlays == 2


def test_v160_overlay_thermal_only_when_cover_absent():
    """Single-overlay cases drop the missing factor cleanly."""
    from openlimno.habitat.composite import CompositeOverlay

    overlay = CompositeOverlay.from_metrics(
        thermal_metrics={"mean_SI": 0.7},
        cover_metrics=None,
    )
    assert overlay.cover_si is None
    assert overlay.thermal_si == pytest.approx(0.7)
    assert overlay.overlay_si == pytest.approx(0.7)
    assert overlay.n_overlays == 1


def test_v160_overlay_none_when_both_absent():
    """No overlays → overlay_si is None (composite step gets skipped)."""
    from openlimno.habitat.composite import CompositeOverlay

    overlay = CompositeOverlay.from_metrics(None, None)
    assert overlay.overlay_si is None
    assert overlay.n_overlays == 0


def test_v160_overlay_rejects_out_of_range():
    """SI values outside [0, 1] are caller bugs and must raise."""
    from openlimno.habitat.composite import CompositeOverlay

    with pytest.raises(ValueError, match="outside"):
        CompositeOverlay.from_metrics(
            thermal_metrics=None,
            cover_metrics={"mean_si": 1.5},
        )


def test_v160_apply_overlay_multiplies_only_base_columns():
    """``apply_overlay`` adds paired composite columns and leaves the
    base table intact. Idempotent when re-applied (the second pass
    should NOT recurse over the composite_* columns)."""
    import pandas as pd

    from openlimno.habitat.composite import CompositeOverlay, apply_overlay

    base = pd.DataFrame({
        "discharge_m3s": [1.0, 5.0, 10.0],
        "wua_m2_salmo_trutta_adult": [100.0, 250.0, 300.0],
    })
    overlay = CompositeOverlay(cover_si=0.5, thermal_si=0.6, overlay_si=0.3)
    composite = apply_overlay(base, overlay)
    # Original column preserved
    assert composite["wua_m2_salmo_trutta_adult"].tolist() == [100.0, 250.0, 300.0]
    # Composite column added with multiplicative overlay applied
    assert composite["wua_m2_composite_salmo_trutta_adult"].tolist() == \
        pytest.approx([30.0, 75.0, 90.0])
    # Re-application does NOT cascade the composite into a double
    # composite (regression pin for the startswith-check in apply_overlay).
    twice = apply_overlay(composite, overlay)
    assert "wua_m2_composite_composite_salmo_trutta_adult" not in twice.columns


def test_v160_composite_summary_reports_ratio():
    """``composite_summary`` ships overlay factors + max-WUA shrinkage
    for review."""
    import pandas as pd

    from openlimno.habitat.composite import CompositeOverlay, composite_summary

    base = pd.DataFrame({
        "discharge_m3s": [1.0, 5.0, 10.0],
        "wua_m2_a_b": [100.0, 250.0, 200.0],
    })
    overlay = CompositeOverlay(cover_si=0.5, thermal_si=0.6, overlay_si=0.3)
    summary = composite_summary(base, overlay)
    assert summary["overlay_si"] == pytest.approx(0.3)
    assert summary["cover_si"] == pytest.approx(0.5)
    assert summary["thermal_si"] == pytest.approx(0.6)
    assert summary["n_overlays"] == 2
    assert summary["n_discharges"] == 3
    [series] = summary["by_species_stage"]
    assert series["species_stage"] == "a_b"
    assert series["wua_m2_base_max"] == pytest.approx(250.0)
    assert series["wua_m2_composite_max"] == pytest.approx(75.0)
    assert series["discharge_m3s_at_composite_max"] == pytest.approx(5.0)
    assert series["composite_to_base_ratio"] == pytest.approx(0.3)


def test_v160_maybe_run_composite_hsi_writes_outputs(tmp_path):
    """End-to-end shape: when overlays exist, ``composite_wua_q.parquet``,
    ``composite_wua_q.csv`` (when csv format requested), and
    ``composite_hsi.json`` all appear in out_dir, and the helper
    returns the summary dict."""
    import json

    import pandas as pd
    case = Case(
        config={"case": {"name": "composite_smoke"}},
        case_yaml_path=tmp_path / "composite_smoke.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_df = pd.DataFrame({
        "discharge_m3s": [1.0, 5.0, 10.0],
        "wua_m2_oncorhynchus_mykiss_spawning": [120.0, 240.0, 180.0],
    })
    summary, composite_df = case._maybe_run_composite_hsi(
        wua_df,
        thermal_metrics_dict={"mean_SI": 0.6},
        cover_metrics_dict={"mean_si": 0.5},
        out_dir=out_dir,
        formats=["csv", "parquet"],
        warnings=[],
    )
    assert summary is not None
    assert summary["overlay_si"] == pytest.approx(0.3)
    # v1.7.0: helper also returns the resolved composite DataFrame so
    # the downstream regulatory_export step can reuse it.
    assert composite_df is not None
    assert "wua_m2_composite_oncorhynchus_mykiss_spawning" in composite_df.columns

    # All three artefacts emitted
    composite_parquet = out_dir / "composite_wua_q.parquet"
    composite_csv = out_dir / "composite_wua_q.csv"
    composite_json = out_dir / "composite_hsi.json"
    assert composite_parquet.exists()
    assert composite_csv.exists()
    assert composite_json.exists()

    payload = json.loads(composite_json.read_text())
    assert payload["cover_si"] == pytest.approx(0.5)
    assert payload["thermal_si"] == pytest.approx(0.6)
    assert payload["overlay_si"] == pytest.approx(0.3)
    # Composite column carries the overlay multiplied through
    df_check = pd.read_parquet(composite_parquet)
    assert "wua_m2_composite_oncorhynchus_mykiss_spawning" in df_check.columns
    assert df_check["wua_m2_composite_oncorhynchus_mykiss_spawning"].tolist() == \
        pytest.approx([36.0, 72.0, 54.0])


def test_v160_maybe_run_composite_hsi_skipped_when_no_overlays(tmp_path):
    """Mirrors v1.1.1 / v1.5.0 silent-skip semantics: no thermal AND
    no cover → return None, no artefacts emitted."""
    import pandas as pd
    case = Case(
        config={"case": {"name": "composite_skip"}},
        case_yaml_path=tmp_path / "composite_skip.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_df = pd.DataFrame({
        "discharge_m3s": [1.0, 5.0],
        "wua_m2_a_b": [10.0, 20.0],
    })
    summary, composite_df = case._maybe_run_composite_hsi(
        wua_df,
        thermal_metrics_dict=None,
        cover_metrics_dict=None,
        out_dir=out_dir,
        formats=["csv", "parquet"],
        warnings=[],
    )
    assert summary is None
    assert composite_df is None
    assert not (out_dir / "composite_wua_q.parquet").exists()
    assert not (out_dir / "composite_wua_q.csv").exists()
    assert not (out_dir / "composite_hsi.json").exists()


def test_v160_provenance_always_contains_composite_summary_key():
    """Regression pin: ``composite_summary`` must exist in every
    provenance file (None when no overlays were present), matching the
    v1.1.1 / v1.5.0 dict-shape contract downstream tooling relies on."""
    import json
    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0])
    prov = json.loads(result.provenance_path.read_text())
    assert "composite_summary" in prov
    assert prov["composite_summary"] is None


# ---------------------------------------------------------------------
# v1.7.0 — regulatory_export composite integration
# (cover × thermal overlay folded into SL-712 / FERC 4e / WFD reports)
# ---------------------------------------------------------------------
def _make_synthetic_wua_q():
    """Triangular WUA-Q curve peaking at Q=5 m³/s, 100 m² apex."""
    import numpy as _np
    import pandas as _pd
    Qs = _np.array([0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0])
    W = _np.maximum(0, 100 * (1 - _np.abs(_np.log(Qs / 5)) / _np.log(4)))
    return _pd.DataFrame({
        "discharge_m3s": Qs,
        "wua_m2_oncorhynchus_mykiss_spawning": W,
    })


def _make_synthetic_discharge_series(tmp_path: Path) -> Path:
    """Write a 2-year daily snowmelt discharge CSV. Returns the path."""
    import numpy as _np
    import pandas as _pd
    times = _pd.date_range("2024-01-01", periods=2 * 365, freq="D")
    doys = times.dayofyear.values
    Q = 3.0 + 8.0 * _np.exp(-((doys - 150) ** 2) / (2 * 30**2))
    df = _pd.DataFrame({"time": times, "discharge_m3s": Q})
    path = tmp_path / "discharge.csv"
    df.to_csv(path, index=False)
    return path


def test_v170_composite_view_renames_columns():
    """``_composite_view`` drops base ``wua_m2_*`` columns and renames
    ``wua_m2_composite_*`` to ``wua_m2_*`` so existing compute_*
    functions look up the composite values transparently."""
    import pandas as pd
    composite_df = pd.DataFrame({
        "discharge_m3s": [1.0, 5.0],
        "wua_m2_oncorhynchus_mykiss_spawning": [100.0, 250.0],
        "wua_m2_composite_oncorhynchus_mykiss_spawning": [30.0, 75.0],
    })
    view = Case._composite_view(composite_df)
    # Base column dropped, composite column renamed
    assert "wua_m2_composite_oncorhynchus_mykiss_spawning" not in view.columns
    assert "wua_m2_oncorhynchus_mykiss_spawning" in view.columns
    assert view["wua_m2_oncorhynchus_mykiss_spawning"].tolist() == [30.0, 75.0]
    # Discharge column preserved untouched
    assert view["discharge_m3s"].tolist() == [1.0, 5.0]


def test_v170_composite_header_lines_full_overlay():
    """Both overlays present → header annotates depth × velocity × cover × thermal."""
    summary = {
        "cover_si": 0.4255,
        "thermal_si": 0.62,
        "overlay_si": 0.26381,
        "n_overlays": 2,
    }
    lines = Case._composite_header_lines(summary)
    assert any("cover_si=0.4255" in line for line in lines)
    assert any("thermal_si=0.62" in line for line in lines)
    assert any("overlay_si=0.26381" in line for line in lines)
    assert any("depth × velocity × cover × thermal" in line for line in lines)


def test_v170_composite_header_lines_partial_overlay():
    """Single overlay → header notes which factor is missing."""
    summary = {
        "cover_si": 0.4,
        "thermal_si": None,
        "overlay_si": 0.4,
        "n_overlays": 1,
    }
    lines = Case._composite_header_lines(summary)
    joined = "\n".join(lines)
    assert "cover only" in joined
    assert "no thermal overlay" in joined


def test_v170_composite_header_lines_none_summary_empty():
    """No overlay → no header lines added (and no crash)."""
    assert Case._composite_header_lines(None) == []


def test_v170_run_regulatory_exports_emits_composite_csvs(tmp_path):
    """End-to-end shape: SL-712, FERC 4e, and WFD each produce both
    base and ``_composite.csv`` artefacts when composite_df is supplied,
    and the composite files carry the overlay-annotation header."""
    case = Case(
        config={"case": {"name": "v170_smoke"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    # Composite WUA = 0.3 × base (cover 0.5 × thermal 0.6)
    composite_df = wua_q.copy()
    composite_df["wua_m2_composite_oncorhynchus_mykiss_spawning"] = \
        composite_df["wua_m2_oncorhynchus_mykiss_spawning"] * 0.3
    composite_summary = {
        "cover_si": 0.5,
        "thermal_si": 0.6,
        "overlay_si": 0.3,
        "n_overlays": 2,
    }
    ds_csv = _make_synthetic_discharge_series(tmp_path)

    case._run_regulatory_exports(
        export_list=["CN-SL712", "US-FERC-4e", "EU-WFD"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=composite_df,
        composite_summary=composite_summary,
    )

    # All 6 artefacts emitted (3 base + 3 composite)
    base = [
        out_dir / "sl712.csv",
        out_dir / "ferc_4e.csv",
        out_dir / "eu_wfd.csv",
    ]
    composite = [
        out_dir / "sl712_composite.csv",
        out_dir / "ferc_4e_composite.csv",
        out_dir / "eu_wfd_composite.csv",
    ]
    for p in base + composite:
        assert p.exists(), f"missing artefact: {p}"

    # Composite files carry the overlay-annotation header
    for p in composite:
        head = p.read_text(encoding="utf-8").splitlines()[0]
        # v1.8.1 dropped the hard-coded "v1.7.0" version stamp from the
        # composite annotation header (2nd-review N5). The generic
        # "OpenLimno composite overlay" prefix is what survives.
        assert "OpenLimno composite overlay" in head, p


def test_v170_run_regulatory_exports_base_only_without_composite(tmp_path):
    """When composite_df is None, regulatory_export still emits the
    base reports (preserving v1.6.x behavior) and skips the composite
    variants — no surprise files."""
    case = Case(
        config={"case": {"name": "v170_base_only"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    ds_csv = _make_synthetic_discharge_series(tmp_path)

    case._run_regulatory_exports(
        export_list=["CN-SL712"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=None,
        composite_summary=None,
    )
    assert (out_dir / "sl712.csv").exists()
    assert not (out_dir / "sl712_composite.csv").exists()


def test_v170_composite_sl712_preserves_recommended_flow_under_multiplicative_overlay(tmp_path):
    """Sanity check on the composite SL-712 output: when the overlay
    is applied as a uniform multiplicative factor (cover × thermal),
    the peak WUA is scaled down by that factor, but the *peak location*
    (i.e. recommended Q) is unchanged — composite_to_base_ratio = overlay.
    This pins the multiplicative-overlay invariant for regulatory
    reporting.

    v1.7.1 (review F10): renamed from
    ``..._recommends_lower_flows_than_base`` — the previous name
    contradicted the actual assertion (the flows are equal under the
    multiplicative invariant, only the WUA magnitude shrinks).
    """
    import pandas as pd

    from openlimno.habitat.regulatory_export import cn_sl712
    wua_q = _make_synthetic_wua_q()
    composite_df = wua_q.copy()
    composite_df["wua_m2_composite_oncorhynchus_mykiss_spawning"] = \
        composite_df["wua_m2_oncorhynchus_mykiss_spawning"] * 0.3
    view = Case._composite_view(composite_df)

    Q = pd.read_csv(_make_synthetic_discharge_series(tmp_path))
    base = cn_sl712.compute_sl712(Q, wua_q, "oncorhynchus_mykiss", "spawning")
    comp = cn_sl712.compute_sl712(Q, view, "oncorhynchus_mykiss", "spawning")
    # Q at peak preserved (multiplicative-overlay invariant; the peak
    # location is a function of curve SHAPE, not absolute magnitude)
    assert comp.monthly["suitable_eco_flow_m3s"].iloc[0] == \
        pytest.approx(base.monthly["suitable_eco_flow_m3s"].iloc[0])
    assert comp.monthly["min_eco_flow_m3s"].iloc[0] == \
        pytest.approx(base.monthly["min_eco_flow_m3s"].iloc[0])


# ---------------------------------------------------------------------
# v1.7.1 — review-feedback patches (codex + gemini findings)
# ---------------------------------------------------------------------
def test_v171_composite_summary_handles_empty_wua_df():
    """F1: ``composite_summary`` must not raise on an empty WUA-Q
    DataFrame (previously crashed on ``idxmax`` of an empty Series)."""
    import pandas as pd

    from openlimno.habitat.composite import CompositeOverlay, composite_summary

    empty = pd.DataFrame({
        "discharge_m3s": [],
        "wua_m2_a_b": [],
    })
    overlay = CompositeOverlay(cover_si=0.5, thermal_si=0.6, overlay_si=0.3)
    summary = composite_summary(empty, overlay)
    assert summary["n_discharges"] == 0
    assert summary["by_species_stage"] == []
    # Overlay factors still present so reviewers know what was
    # configured even when the hydraulic sweep had zero rows.
    assert summary["cover_si"] == pytest.approx(0.5)
    assert summary["overlay_si"] == pytest.approx(0.3)


def test_v171_maybe_run_composite_hsi_skips_overlay_zero(tmp_path):
    """F5: overlay_si == 0 must skip composite emission (with a
    warning) rather than ship degenerate regulatory recommendations
    (WFD would raise on reference_wua=0; SL-712 would collapse to the
    lowest Q)."""
    import pandas as pd
    case = Case(
        config={"case": {"name": "overlay_zero"}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_df = pd.DataFrame({
        "discharge_m3s": [1.0, 5.0],
        "wua_m2_a_b": [10.0, 20.0],
    })
    warnings: list[str] = []
    summary, composite_df = case._maybe_run_composite_hsi(
        wua_df,
        thermal_metrics_dict={"mean_SI": 0.0},  # full lethal-zone period
        cover_metrics_dict={"mean_si": 0.5},
        out_dir=out_dir,
        formats=["csv", "parquet"],
        warnings=warnings,
    )
    assert summary is None
    assert composite_df is None
    assert not (out_dir / "composite_wua_q.parquet").exists()
    assert not (out_dir / "composite_hsi.json").exists()
    assert any("overlay_si=0" in w for w in warnings)


def test_v171_maybe_run_composite_hsi_skips_when_no_wua_columns(tmp_path):
    """F8: when wua_df has no `wua_m2_*` columns, composite emission
    must be skipped (instead of writing an empty parquet/csv with no
    composite columns)."""
    import pandas as pd
    case = Case(
        config={"case": {"name": "no_wua_cols"}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_df = pd.DataFrame({"discharge_m3s": [1.0, 5.0]})  # no wua_m2_*
    warnings: list[str] = []
    summary, composite_df = case._maybe_run_composite_hsi(
        wua_df,
        thermal_metrics_dict={"mean_SI": 0.6},
        cover_metrics_dict={"mean_si": 0.5},
        out_dir=out_dir,
        formats=["parquet", "csv"],
        warnings=warnings,
    )
    assert summary is None
    assert composite_df is None
    assert not (out_dir / "composite_wua_q.parquet").exists()
    assert any("no `wua_m2_*` columns" in w for w in warnings)


def test_v171_from_metrics_degrades_invalid_thermal_when_warnings_supplied():
    """F6: when the pipeline supplies a warnings list,
    ``CompositeOverlay.from_metrics`` drops an invalid thermal value
    independently and KEEPS a valid cover overlay — instead of raising
    and losing both factors."""
    from openlimno.habitat.composite import CompositeOverlay

    warnings: list[str] = []
    overlay = CompositeOverlay.from_metrics(
        thermal_metrics={"mean_SI": -0.1},  # invalid: < 0
        cover_metrics={"mean_si": 0.4},
        warnings=warnings,
    )
    # Cover survives; thermal dropped
    assert overlay.cover_si == pytest.approx(0.4)
    assert overlay.thermal_si is None
    assert overlay.overlay_si == pytest.approx(0.4)
    # And the degradation is recorded
    assert any("thermal_metrics.mean_SI" in w for w in warnings)


def test_v171_from_metrics_still_raises_for_direct_api_callers():
    """F6: API-level fail-loud semantics preserved when ``warnings``
    is omitted (default None) — protects programmatic callers from
    silently consuming garbage overlays."""
    from openlimno.habitat.composite import CompositeOverlay

    with pytest.raises(ValueError, match="outside"):
        CompositeOverlay.from_metrics(
            thermal_metrics=None,
            cover_metrics={"mean_si": 1.5},
            # no warnings kwarg → strict mode
        )


def test_v171_regulatory_csvs_carry_quality_watermark(tmp_path):
    """F3: SL-712 / FERC 4e / WFD CSVs (base AND composite) must
    carry the same TENTATIVE watermark that ``wua_q.csv`` does, so a
    downstream consumer cannot cite a C-grade flow recommendation
    without seeing the quality warning."""
    case = Case(
        config={"case": {"name": "watermark_check"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    composite_df = wua_q.copy()
    composite_df["wua_m2_composite_oncorhynchus_mykiss_spawning"] = \
        composite_df["wua_m2_oncorhynchus_mykiss_spawning"] * 0.3
    composite_summary = {
        "cover_si": 0.5, "thermal_si": 0.6, "overlay_si": 0.3, "n_overlays": 2,
    }
    ds_csv = _make_synthetic_discharge_series(tmp_path)

    case._run_regulatory_exports(
        export_list=["CN-SL712", "US-FERC-4e", "EU-WFD"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=composite_df,
        composite_summary=composite_summary,
        wua_quality_grade="C",  # tentative
    )

    # All 6 files: base + composite × {SL-712, FERC, WFD}
    for fname in [
        "sl712.csv", "sl712_composite.csv",
        "ferc_4e.csv", "ferc_4e_composite.csv",
        "eu_wfd.csv", "eu_wfd_composite.csv",
    ]:
        text = (out_dir / fname).read_text(encoding="utf-8")
        first = text.splitlines()[0]
        assert "TENTATIVE" in first, (
            f"v1.7.1 F3: {fname} first line should carry the C-grade "
            f"TENTATIVE watermark, got: {first!r}"
        )


# ---------------------------------------------------------------------
# v1.8.0 — F7 (CaseRunResult.composite_wua_q) + F9 (WFD scaling header)
# ---------------------------------------------------------------------
def test_v180_caserunresult_carries_composite_fields_on_lemhi():
    """F7: ``CaseRunResult`` must expose the new ``composite_wua_q``
    and ``composite_summary`` fields. Lemhi has no overlays, so both
    are ``None`` — the regression pin is that the FIELDS exist (so
    notebook users can rely on the dataclass shape without try/except)."""
    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0])
    # Field exists on the dataclass (would AttributeError on v1.7.x)
    assert hasattr(result, "composite_wua_q")
    assert hasattr(result, "composite_summary")
    # And both are None for a case without overlays
    assert result.composite_wua_q is None
    assert result.composite_summary is None


def test_v180_composite_header_lines_includes_per_series_scaling():
    """F9: ``_composite_header_lines`` should now embed the
    base → composite scaling per species/stage so a reviewer reading
    eu_wfd_composite.csv sees the reference-WUA scaling directly."""
    summary = {
        "cover_si": 0.4255,
        "thermal_si": 0.62,
        "overlay_si": 0.26381,
        "n_overlays": 2,
        "by_species_stage": [
            {
                "species_stage": "oncorhynchus_mykiss_spawning",
                "wua_m2_base_max": 520.00,
                "wua_m2_composite_max": 137.18,
                "composite_to_base_ratio": 0.26381,
                "discharge_m3s_at_composite_max": 5.0,
            },
        ],
    }
    lines = Case._composite_header_lines(summary)
    joined = "\n".join(lines)
    # The per-series scaling line is present with both magnitudes
    assert "oncorhynchus_mykiss_spawning" in joined
    assert "520.00" in joined and "137.18" in joined
    assert "×0.26381" in joined


def test_v180_wfd_composite_csv_includes_scaling_in_header(tmp_path):
    """F9 end-to-end: emitting ``eu_wfd_composite.csv`` should now
    carry the base → composite scaling line in its header so a reviewer
    can see that ``reference_wua_m2=137.18`` was scaled from a base
    of 520 without having to cross-reference the base report."""
    case = Case(
        config={"case": {"name": "f9_smoke"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    composite_df = wua_q.copy()
    composite_df["wua_m2_composite_oncorhynchus_mykiss_spawning"] = \
        composite_df["wua_m2_oncorhynchus_mykiss_spawning"] * 0.26381
    composite_summary = {
        "cover_si": 0.4255,
        "thermal_si": 0.62,
        "overlay_si": 0.26381,
        "n_overlays": 2,
        "by_species_stage": [
            {
                "species_stage": "oncorhynchus_mykiss_spawning",
                "wua_m2_base_max": 100.0,
                "wua_m2_composite_max": 26.381,
                "composite_to_base_ratio": 0.26381,
                "discharge_m3s_at_composite_max": 5.0,
            },
        ],
    }
    ds_csv = _make_synthetic_discharge_series(tmp_path)
    case._run_regulatory_exports(
        export_list=["EU-WFD"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=composite_df,
        composite_summary=composite_summary,
        wua_quality_grade="A",  # focus on the F9 scaling header
    )
    text = (out_dir / "eu_wfd_composite.csv").read_text(encoding="utf-8")
    head = text.splitlines()[:8]
    head_joined = "\n".join(head)
    # F9 scaling line shows both magnitudes + ratio
    assert "oncorhynchus_mykiss_spawning" in head_joined
    assert "100.00" in head_joined and "26.38" in head_joined
    assert "×0.26381" in head_joined


def test_v171_regulatory_csvs_grade_a_has_no_watermark(tmp_path):
    """A-grade HSI should NOT carry a watermark line — preserves the
    v1.7.0 file shape for high-confidence curves (regression pin so we
    don't accidentally prefix all reports unconditionally)."""
    case = Case(
        config={"case": {"name": "grade_a_check"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    ds_csv = _make_synthetic_discharge_series(tmp_path)

    case._run_regulatory_exports(
        export_list=["CN-SL712"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=None,
        composite_summary=None,
        wua_quality_grade="A",
    )
    first = (out_dir / "sl712.csv").read_text(
        encoding="utf-8"
    ).splitlines()[0]
    # Original SL-712 header survives untouched
    assert first.startswith("# OpenLimno SL/Z 712-2014")


# ---------------------------------------------------------------------
# v1.8.1 — 2nd-pass codex + gemini review patches
# (N1 atomic write, N2 defensive header, N3 test integrity, N4 NaN
# guard, N5 drop v1.7.0 stamp)
# ---------------------------------------------------------------------
def test_v181_n1_emit_regulatory_csv_leaves_no_inprogress_files(tmp_path):
    """N1: the atomic-publish refactor uses sibling tempfiles named
    ``.csv.inprogress`` and ``.csv.publishtmp``. After
    ``_emit_regulatory_csv`` returns, only the target path should
    remain on disk — no orphaned tempfiles."""
    case = Case(
        config={"case": {"name": "n1_smoke"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    ds_csv = _make_synthetic_discharge_series(tmp_path)
    case._run_regulatory_exports(
        export_list=["CN-SL712"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=None,
        composite_summary=None,
        wua_quality_grade="C",
    )
    # Exactly one CSV; no leftover tempfiles
    files = sorted(p.name for p in out_dir.iterdir() if p.is_file())
    assert files == ["sl712.csv"], files
    # And the target file carries TENTATIVE on line 1 (race-free guarantee)
    first = (out_dir / "sl712.csv").read_text(
        encoding="utf-8"
    ).splitlines()[0]
    assert "TENTATIVE" in first


def test_v181_n3_full_csv_integrity_under_layered_prepend(tmp_path):
    """N3: previous test_v171 layered tests only checked that the
    TENTATIVE line appears at the top. This goes further and verifies
    that beneath the layered prefix (quality watermark → overlay
    annotation → original SL-712 header), the actual monthly DATA
    survives intact — i.e. the read-modify-write didn't corrupt the
    DataFrame payload."""
    import pandas as pd
    case = Case(
        config={"case": {"name": "n3_integrity"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    composite_df = wua_q.copy()
    composite_df["wua_m2_composite_oncorhynchus_mykiss_spawning"] = \
        composite_df["wua_m2_oncorhynchus_mykiss_spawning"] * 0.3
    composite_summary = {
        "cover_si": 0.5, "thermal_si": 0.6, "overlay_si": 0.3, "n_overlays": 2,
    }
    ds_csv = _make_synthetic_discharge_series(tmp_path)
    case._run_regulatory_exports(
        export_list=["CN-SL712"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=composite_df,
        composite_summary=composite_summary,
        wua_quality_grade="C",
    )
    text = (out_dir / "sl712_composite.csv").read_text(encoding="utf-8")
    lines = text.splitlines()

    # Layered order verification (top → bottom):
    # 1. TENTATIVE quality watermark on line 0
    assert "TENTATIVE" in lines[0]
    # 2. Composite overlay annotation block follows
    assert any("OpenLimno composite overlay" in line for line in lines[:8])
    # 3. The original "# OpenLimno SL/Z 712-2014" report header still
    #    appears below the prefix block
    assert any("SL/Z 712-2014" in line for line in lines)
    # 4. The 12 monthly data rows survive intact (month=1..12 + header).
    # v1.8.2 (3rd-review M5): use skiprows to find the column-header row
    # robustly, instead of relying on pd.read_csv(comment="#"). A future
    # report column whose value contains "#" would silently truncate
    # under the comment-prefix mode.
    n_comment_rows = sum(1 for line in lines if line.startswith("#"))
    df = pd.read_csv(
        out_dir / "sl712_composite.csv", skiprows=n_comment_rows,
    )
    assert len(df) == 12
    assert (df["month"] == list(range(1, 13))).all()


def test_v181_n2_composite_header_skips_malformed_series_lines():
    """N2: malformed entries in ``by_species_stage`` (NaN, strings,
    missing fields) must drop only that one line — not abort the
    whole header. Pin this so regulatory_export keeps emitting base
    CSVs even when a future code change produces a partly-broken
    composite summary."""
    summary = {
        "cover_si": 0.5,
        "thermal_si": 0.6,
        "overlay_si": 0.3,
        "n_overlays": 2,
        "by_species_stage": [
            # OK series — should produce a line
            {
                "species_stage": "good_one",
                "wua_m2_base_max": 100.0,
                "wua_m2_composite_max": 30.0,
                "composite_to_base_ratio": 0.3,
            },
            # NaN — must be skipped silently
            {
                "species_stage": "nan_one",
                "wua_m2_base_max": float("nan"),
                "wua_m2_composite_max": 30.0,
                "composite_to_base_ratio": 0.3,
            },
            # Non-numeric — must be skipped silently
            {
                "species_stage": "string_one",
                "wua_m2_base_max": "not a number",
                "wua_m2_composite_max": 30.0,
                "composite_to_base_ratio": 0.3,
            },
            # Missing fields — must be skipped silently
            {"species_stage": "missing_one"},
        ],
    }
    lines = Case._composite_header_lines(summary)
    joined = "\n".join(lines)
    # The good one survives
    assert "good_one" in joined
    assert "100.00" in joined and "30.00" in joined
    # The malformed ones don't appear
    assert "nan_one" not in joined
    assert "string_one" not in joined
    assert "missing_one" not in joined
    # And critically: no `(×nan)` rendered (N4 guard)
    assert "nan)" not in joined


def test_v181_n4_nan_ratio_renders_without_nan_marker():
    """N4: explicit pin for NaN ratio handling — when
    composite_to_base_ratio is NaN the line should either omit the
    ratio entirely or be skipped, but NEVER render as ``(×nan)``."""
    summary = {
        "cover_si": 0.5, "thermal_si": 0.6, "overlay_si": 0.3, "n_overlays": 2,
        "by_species_stage": [
            {
                "species_stage": "nan_ratio",
                "wua_m2_base_max": 100.0,
                "wua_m2_composite_max": 30.0,
                "composite_to_base_ratio": float("nan"),
            },
        ],
    }
    lines = Case._composite_header_lines(summary)
    joined = "\n".join(lines)
    # The base/composite line still emits (magnitudes are valid)
    assert "nan_ratio" in joined
    assert "100.00" in joined and "30.00" in joined
    # But no nan rendered
    assert "nan)" not in joined and "(×nan" not in joined


def test_v181_n3_caserunresult_composite_fields_set_when_overlays_present(
    tmp_path,
):
    """N3 + F7 strengthening: the v1.8.0 F7 test verified the FIELDS
    exist on CaseRunResult (None on Lemhi). This test exercises the
    other branch — when _maybe_run_composite_hsi DOES produce a
    composite, the returned CaseRunResult must carry the actual
    DataFrame and summary dict (not just the field with None).

    Uses a synthetic minimal case via the helper directly so we don't
    need a full hydraulic-section fixture."""
    import pandas as pd
    case = Case(
        config={"case": {"name": "f7_overlay"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_df = pd.DataFrame({
        "discharge_m3s": [1.0, 5.0, 10.0],
        "wua_m2_oncorhynchus_mykiss_spawning": [100.0, 250.0, 200.0],
    })
    summary, composite_df = case._maybe_run_composite_hsi(
        wua_df,
        thermal_metrics_dict={"mean_SI": 0.6},
        cover_metrics_dict={"mean_si": 0.5},
        out_dir=out_dir,
        formats=["parquet"],
        warnings=[],
    )
    # Both return values populated when overlays are valid
    assert summary is not None
    assert composite_df is not None
    # And the composite_df actually carries the overlay-multiplied column
    assert "wua_m2_composite_oncorhynchus_mykiss_spawning" in composite_df.columns
    assert composite_df["wua_m2_composite_oncorhynchus_mykiss_spawning"].tolist() == \
        pytest.approx([30.0, 75.0, 60.0])


def test_v182_caserunresult_population_through_case_run(monkeypatch, tmp_path):
    """M3 (3rd-review): the v1.8.0 F7 test only checks that fields exist
    on CaseRunResult; the v1.8.1 strengthening calls
    ``_maybe_run_composite_hsi`` directly. Neither test would fail if a
    future refactor accidentally dropped ``composite_wua_q=composite_df``
    from the ``return CaseRunResult(...)`` call site.

    This test patches ``_maybe_run_composite_hsi`` to return a known
    composite tuple, runs the real Lemhi case end-to-end, and verifies
    that BOTH the patched DataFrame and summary land on the returned
    CaseRunResult — pinning the integration of the helper return values
    with the dataclass population at the run() return site.
    """
    if not CASE_YAML.exists():
        pytest.skip("Lemhi example missing")
    import pandas as pd

    sentinel_summary = {
        "cover_si": 0.42,
        "thermal_si": 0.6,
        "overlay_si": 0.252,
        "n_overlays": 2,
        "by_species_stage": [],
    }
    sentinel_df = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0],
        "wua_m2_composite_sentinel_marker": [99.0, 99.0],
    })

    def _stub_maybe_run_composite_hsi(
        self, wua_df, thermal_metrics_dict, cover_metrics_dict,
        out_dir, formats, warnings, method="product",
    ):
        return sentinel_summary, sentinel_df

    monkeypatch.setattr(
        Case, "_maybe_run_composite_hsi",
        _stub_maybe_run_composite_hsi,
    )
    result = Case.from_yaml(CASE_YAML).run(discharges_m3s=[3.0])

    # The patched helper output reached the returned CaseRunResult
    assert result.composite_summary is sentinel_summary
    assert result.composite_wua_q is sentinel_df
    # And the sentinel column is observable (proves we got the right
    # DataFrame, not a fresh one from a real composite run)
    assert "wua_m2_composite_sentinel_marker" in result.composite_wua_q.columns


def test_v182_emit_regulatory_csv_concurrent_safe_tempfile_naming(tmp_path):
    """M1 (3rd-review): regression pin that ``_emit_regulatory_csv``
    no longer uses fixed ``<path>.inprogress`` / ``<path>.publishtmp``
    suffixes — two concurrent writers to the same target would have
    collided on those names. The v1.8.2 refactor uses
    ``tempfile.mkstemp`` with per-call random suffixes.

    We can't easily simulate concurrent processes here, but we CAN
    pin that the tempfile names follow the new pattern (random-suffix
    hidden files prefixed with ``.<basename>.body.`` / ``.<basename>.publish.``)
    by patching ``tempfile.mkstemp`` and recording the kwargs used.
    """
    import tempfile
    captured_calls: list[dict] = []
    real_mkstemp = tempfile.mkstemp

    def _spy_mkstemp(*args, **kwargs):
        captured_calls.append(dict(kwargs))
        return real_mkstemp(*args, **kwargs)

    case = Case(
        config={"case": {"name": "m1_smoke"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    ds_csv = _make_synthetic_discharge_series(tmp_path)

    import unittest.mock as _mock
    with _mock.patch("tempfile.mkstemp", side_effect=_spy_mkstemp):
        case._run_regulatory_exports(
            export_list=["CN-SL712"],
            wua_q=wua_q,
            species_list=["oncorhynchus_mykiss"],
            stage_list=["spawning"],
            out_dir=out_dir,
            discharge_series_path=ds_csv,
            warnings=[],
            composite_df=None,
            composite_summary=None,
            wua_quality_grade="C",
        )

    # Two mkstemp calls per regulatory CSV: one for the body, one for
    # the publish stage. CN-SL712 base only (no composite) → 2 calls.
    assert len(captured_calls) == 2
    # Both calls land in the target output directory (atomic os.replace
    # needs same-filesystem siblings)
    for call in captured_calls:
        assert call["dir"] == out_dir
    # Distinct prefixes — body vs publish — so they don't share names
    prefixes = [c["prefix"] for c in captured_calls]
    assert any(".body." in p for p in prefixes)
    assert any(".publish." in p for p in prefixes)
    # And the final published target exists with TENTATIVE on line 1
    out_files = sorted(p.name for p in out_dir.iterdir() if p.is_file())
    assert out_files == ["sl712.csv"]
    first_line = (out_dir / "sl712.csv").read_text().splitlines()[0]
    assert "TENTATIVE" in first_line


def test_v182_composite_header_lines_handles_non_mapping_entries():
    """M2 (3rd-review): codex flagged that the v1.8.1 defensive try/except
    caught (TypeError, ValueError) but missed AttributeError, which a
    non-mapping ``series`` (None / float / string in by_species_stage)
    would raise on .get(). Pin that those entries now drop silently
    too, so a malformed upstream summary can't abort regulatory_export
    before any base CSV is emitted."""
    summary = {
        "cover_si": 0.5, "thermal_si": 0.6, "overlay_si": 0.3, "n_overlays": 2,
        "by_species_stage": [
            # OK entry, should emit
            {
                "species_stage": "ok",
                "wua_m2_base_max": 100.0,
                "wua_m2_composite_max": 30.0,
                "composite_to_base_ratio": 0.3,
            },
            None,                      # ← raises AttributeError on .get
            float("nan"),              # ← also AttributeError-ish
            "bad string entry",        # ← also AttributeError-ish
            42,                        # ← also AttributeError-ish
            ["list", "not", "mapping"],  # ← also AttributeError-ish
        ],
    }
    # Must NOT raise; should silently drop the non-mapping entries
    lines = Case._composite_header_lines(summary)
    joined = "\n".join(lines)
    assert "ok" in joined
    assert "100.00" in joined and "30.00" in joined
    # And the malformed entries didn't produce garbage output
    assert "None" not in joined
    assert "bad string entry" not in joined


def test_v182_composite_header_lines_docstring_no_v170_stamp():
    """M4 (3rd-review): regression pin that the ``_composite_header_lines``
    docstring no longer mentions ``v1.7.0`` (the stamp was dropped from
    the actual emitted header in v1.8.1 but the docstring was overlooked
    until v1.8.2)."""
    doc = Case._composite_header_lines.__doc__
    assert doc is not None
    # The historical-reference note in v1.8.2 explicitly mentions
    # 'v1.7.0' to record WHEN the stamp was dropped, but the emitted-
    # header literal should be the generic form.
    assert "OpenLimno composite overlay" in doc
    # ...and the docstring should not claim the emitter still writes
    # the old form. Easiest check: the literal "v1.7.0 composite" must
    # not appear as a quoted emitter string.
    assert "v1.7.0 composite overlay" not in doc


# ---------------------------------------------------------------------
# v1.8.3 — 4th-pass review: file-permission regression from mkstemp
# ---------------------------------------------------------------------
@pytest.mark.skipif(
    __import__("platform").system() == "Windows",
    reason="POSIX umask semantics; Windows has different permission model",
)
def test_v183_regulatory_csvs_respect_umask_not_mkstemp_0600(tmp_path):
    """4th-review regression pin: v1.8.2 introduced `tempfile.mkstemp`
    for the atomic publish, which creates files with 0600 (user-only).
    Both codex and gemini independently flagged that os.replace
    preserved those restrictive perms — a regression vs the pre-v1.8.2
    to_csv behavior (umask-respecting, typically 0644). Shared-filesystem
    deployments would lose group/other read access to regulatory CSVs.

    v1.8.3 chmods the published file using ``0o666 & ~current_umask``
    so the file follows the umask convention. Pin this so a future
    refactor that strips the chmod call gets caught.
    """
    import os
    case = Case(
        config={"case": {"name": "v183"}, "data": {}},
        case_yaml_path=tmp_path / "case.yaml",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    wua_q = _make_synthetic_wua_q()
    ds_csv = _make_synthetic_discharge_series(tmp_path)
    case._run_regulatory_exports(
        export_list=["CN-SL712"],
        wua_q=wua_q,
        species_list=["oncorhynchus_mykiss"],
        stage_list=["spawning"],
        out_dir=out_dir,
        discharge_series_path=ds_csv,
        warnings=[],
        composite_df=None,
        composite_summary=None,
        wua_quality_grade="C",
    )
    perms = os.stat(out_dir / "sl712.csv").st_mode & 0o777

    # The 0600 regression: file must NOT be user-only.
    assert perms != 0o600, (
        f"v1.8.3 regression check: sl712.csv perms={oct(perms)} "
        f"— mkstemp's 0600 default leaked through os.replace"
    )
    # And it must include at least owner read+write (basic sanity).
    assert perms & 0o600 == 0o600

    # And the file should follow the process umask: 0o666 & ~umask.
    current_umask = os.umask(0)
    os.umask(current_umask)
    expected = 0o666 & ~current_umask
    assert perms == expected, (
        f"v1.8.3 perms={oct(perms)} != 0o666 & ~umask({oct(current_umask)}) "
        f"= {oct(expected)}"
    )


# ---------------------------------------------------------------------
# v1.9.0 — atomic-write helper generalized to all output writers
# ---------------------------------------------------------------------
def test_v190_atomic_write_helper_publishes_via_temp_rename(tmp_path):
    """The new shared ``Case._atomic_write(target, writer)`` helper must:
    (1) invoke ``writer(tmp_path)`` on a sibling tempfile, not the
        target path directly,
    (2) rename atomically onto the target via ``os.replace``,
    (3) leave no tempfile leftovers in the directory,
    (4) restore umask-respecting perms (closes the v1.8.3 regression
        for all writers, not just regulatory CSVs).
    """
    target = tmp_path / "data.txt"
    seen_writer_path: dict[str, Path | None] = {"p": None}

    def _writer(p: Path) -> None:
        seen_writer_path["p"] = p
        # writer must NEVER be invoked on the target itself
        assert p != target
        # but should land in the same directory (for atomic rename)
        assert p.parent == target.parent
        p.write_text("hello v1.9.0 atomic\n", encoding="utf-8")

    Case._atomic_write(target, _writer)
    assert target.read_text(encoding="utf-8") == "hello v1.9.0 atomic\n"
    # No tempfile leftovers
    leftover = [
        p.name for p in tmp_path.iterdir()
        if p.name != "data.txt" and (".publish." in p.name or ".body." in p.name)
    ]
    assert leftover == [], f"v1.9.0 leftover tempfiles: {leftover}"


@pytest.mark.skipif(
    __import__("platform").system() == "Windows",
    reason="POSIX umask semantics; Windows perm model differs",
)
def test_v190_atomic_write_helper_respects_umask(tmp_path):
    """All output writers, not just regulatory CSVs, now respect the
    process umask. Regression pin against future refactors of
    ``_atomic_write`` that might lose the chmod step."""
    import os
    target = tmp_path / "out.json"
    Case._atomic_write(
        target,
        lambda p: p.write_text('{"k": "v"}', encoding="utf-8"),
    )
    perms = os.stat(target).st_mode & 0o777
    current_umask = os.umask(0)
    os.umask(current_umask)
    expected = 0o666 & ~current_umask
    assert perms == expected, (
        f"v1.9.0: _atomic_write target perms={oct(perms)} != "
        f"expected {oct(expected)}"
    )


def test_v190_atomic_write_cleans_up_on_writer_exception(tmp_path):
    """If the writer callable raises, the helper must remove the
    publish tempfile (no orphan in the output dir) and re-raise the
    original exception."""
    target = tmp_path / "boom.txt"

    class _BoomError(RuntimeError):
        pass

    def _bad_writer(p: Path) -> None:
        p.write_text("partial", encoding="utf-8")
        raise _BoomError("intentional")

    with pytest.raises(_BoomError, match="intentional"):
        Case._atomic_write(target, _bad_writer)

    # Target should not exist (writer failed before os.replace);
    # publish tempfile should be cleaned up.
    assert not target.exists()
    leftover = list(tmp_path.iterdir())
    assert leftover == [], f"v1.9.0 cleanup leftover: {leftover}"


def test_v190_provenance_json_routes_through_atomic_write(monkeypatch):
    """End-to-end pin that Case.run's provenance.json write now goes
    through the atomic-publish path.

    v1.9.1 (5th-review R5-2): the v1.9.0 form of this test only checked
    valid JSON + absence of tempfile leftovers — codex correctly noted
    that a direct ``prov_path.write_text(...)`` would pass the same
    assertions. This version spies on ``Case._atomic_write`` to assert
    the helper is actually invoked, and that provenance.json is among
    the targets routed through it. Lemhi has no overlays, so the
    standard run() exercises the new path without needing a synthetic
    overlay fixture.
    """
    seen_targets: list[Path] = []
    real_atomic_write = Case._atomic_write

    def _spy(target, writer):
        seen_targets.append(target)
        return real_atomic_write(target, writer)

    monkeypatch.setattr(Case, "_atomic_write", staticmethod(_spy))

    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0])

    # The helper was invoked, and provenance.json was one of the targets
    assert seen_targets, (
        "R5-2: _atomic_write was never called during Case.run — the "
        "provenance integration is not actually routed through the helper"
    )
    target_names = [p.name for p in seen_targets]
    assert "provenance.json" in target_names, (
        f"R5-2: provenance.json not in {target_names}"
    )

    # Basic correctness preserved: file is valid JSON
    import json as _json
    _json.loads(result.provenance_path.read_text())

    # And no .publish.*.tmp / .body.*.inprogress leftover next to it
    leftover = [
        p.name for p in result.output_dir.iterdir()
        if ".publish." in p.name or ".body." in p.name
    ]
    assert leftover == [], (
        f"v1.9.0 provenance integration left tempfiles: {leftover}"
    )


def test_v191_atomic_write_publishes_perms_atomically_with_content(tmp_path):
    """R5-1: chmod must run BEFORE os.replace so the target appears
    with content and umask-respecting permissions in a single atomic
    step. Previous (v1.9.0) ordering chmodded AFTER replace, leaving a
    narrow window where a concurrent non-owner reader could observe
    0o600.

    The semantic guarantee we want: if the target file is observable
    on disk, its mode is already the umask-respecting one. Test by
    asserting that os.chmod is called on the PUBLISH path (the
    tempfile) BEFORE os.replace renames it onto the target.
    """
    import os as _os
    call_log: list[tuple[str, str]] = []
    target = tmp_path / "ordered.txt"

    real_chmod = _os.chmod
    real_replace = _os.replace

    def _logging_chmod(path, mode):
        call_log.append(("chmod", str(path)))
        return real_chmod(path, mode)

    def _logging_replace(src, dst):
        call_log.append(("replace", str(src)))
        return real_replace(src, dst)

    import unittest.mock as _mock
    with _mock.patch("os.chmod", side_effect=_logging_chmod), \
         _mock.patch("os.replace", side_effect=_logging_replace):
        Case._atomic_write(
            target,
            lambda p: p.write_text("ordered v1.9.1\n", encoding="utf-8"),
        )

    # The chmod must hit the publish tempfile BEFORE the replace.
    # Filter to the two semantic calls we care about.
    chmod_calls = [c for c in call_log if c[0] == "chmod"]
    replace_calls = [c for c in call_log if c[0] == "replace"]
    assert len(chmod_calls) == 1
    assert len(replace_calls) == 1

    chmod_idx = call_log.index(chmod_calls[0])
    replace_idx = call_log.index(replace_calls[0])
    assert chmod_idx < replace_idx, (
        f"R5-1: chmod must happen BEFORE replace; got call order "
        f"{call_log}"
    )

    # And the chmod was applied to the publish tempfile, not the final
    # target — that's what makes content + perms atomic together.
    assert str(target) not in chmod_calls[0][1], (
        f"R5-1: chmod was applied to the final target {target}, not "
        f"the publish tempfile. This re-opens the race window — content "
        f"became visible via os.replace before perms were set."
    )


# ---------------------------------------------------------------------
# v1.9.2 — R5-3 close-out: hydraulics.nc + wua_q_curve.png atomic
# ---------------------------------------------------------------------
@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_v192_hydraulics_nc_routes_through_atomic_write(monkeypatch):
    """R5-3: ``hydraulics.nc`` must now go through ``Case._atomic_write``
    so it inherits the atomic + umask-respecting contract that all
    other Case.run outputs got in v1.9.0. Spy on the helper to confirm
    integration."""
    import os
    seen_targets: list[Path] = []
    real_atomic_write = Case._atomic_write

    def _spy(target, writer):
        seen_targets.append(target)
        return real_atomic_write(target, writer)

    monkeypatch.setattr(Case, "_atomic_write", staticmethod(_spy))

    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0])

    target_names = [p.name for p in seen_targets]
    # The Lemhi example writes hydraulics.nc when output.formats includes
    # "netcdf"; the case YAML does include it, so this target should
    # have routed through the helper.
    assert "hydraulics.nc" in target_names, (
        f"R5-3: hydraulics.nc not in atomic-write targets {target_names}"
    )
    # And the file landed on disk with umask perms
    nc_path = result.output_dir / "hydraulics.nc"
    if nc_path.exists():
        perms = os.stat(nc_path).st_mode & 0o777
        current_umask = os.umask(0)
        os.umask(current_umask)
        expected = 0o666 & ~current_umask
        assert perms == expected, (
            f"R5-3: hydraulics.nc perms={oct(perms)} != "
            f"expected {oct(expected)}"
        )


def test_v192_atomic_write_supports_binary_writers(tmp_path):
    """R5-3 generalization: matplotlib's ``fig.savefig`` writes binary
    PNG bytes, not text. Confirm the helper's writer-callable contract
    actually works for binary writers — the publish tempfile must be
    suitable for both text and bytes writes."""
    target = tmp_path / "image.bin"

    def _binary_writer(p: Path) -> None:
        # Simulate matplotlib savefig: write binary bytes to the path
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    Case._atomic_write(target, _binary_writer)
    content = target.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n"), (
        "R5-3: binary content via _atomic_write was corrupted"
    )
    assert len(content) == 108

    # No tempfile leftovers
    leftover = [
        p.name for p in tmp_path.iterdir() if p != target
    ]
    assert leftover == [], f"R5-3 binary cleanup leftover: {leftover}"


# ---------------------------------------------------------------------------
# v1.10.0 — N6 strict-mode opt-in + 4-way geom-mean overlay method
# ---------------------------------------------------------------------------


def test_v1100_from_metrics_strict_true_raises_on_out_of_range():
    """N6: explicit ``strict=True`` raises on invalid inputs regardless
    of whether a ``warnings`` list is supplied — the legacy
    ``warnings=None → strict`` inference no longer hides the contract.
    """
    from openlimno.habitat.composite import CompositeOverlay

    msgs: list[str] = []
    with pytest.raises(ValueError, match="cover_metrics.mean_si"):
        CompositeOverlay.from_metrics(
            {"mean_SI": 0.5},
            {"mean_si": 1.5},
            warnings=msgs,
            strict=True,
        )


def test_v1100_from_metrics_strict_false_with_no_warnings_list_synthesises_one():
    """N6: ``strict=False`` without a caller-supplied ``warnings`` list
    must not crash. The implementation creates one internally so that
    invalid overlays still degrade gracefully — previously
    ``strict=False`` was only reachable by supplying ``warnings``."""
    from openlimno.habitat.composite import CompositeOverlay

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.5},
        {"mean_si": 1.5},
        strict=False,
    )
    # Cover got rejected, thermal preserved
    assert overlay.cover_si is None
    assert overlay.thermal_si == 0.5
    assert overlay.overlay_si == 0.5


def test_v1100_from_metrics_legacy_strict_inference_unchanged():
    """N6 back-compat: callers that never pass ``strict`` still get the
    v1.7.1—v1.9.x behaviour — supplying ``warnings`` → lenient,
    omitting it → strict."""
    from openlimno.habitat.composite import CompositeOverlay

    msgs: list[str] = []
    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.5},
        {"mean_si": 1.5},
        warnings=msgs,
    )
    assert overlay.cover_si is None
    assert overlay.thermal_si == 0.5
    assert len(msgs) == 1

    with pytest.raises(ValueError, match="cover_metrics.mean_si"):
        CompositeOverlay.from_metrics(
            {"mean_SI": 0.5},
            {"mean_si": 1.5},
        )


def test_v1100_apply_overlay_rejects_unknown_method():
    """v1.10.0: ``apply_overlay(method=...)`` should fail loud on
    unknown method strings (e.g. typos) rather than silently fall back
    to product."""
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
    )

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.5}, {"mean_si": 0.6},
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0, 3.0],
        "wua_m2_sp_juv": [10.0, 20.0, 30.0],
    })
    with pytest.raises(ValueError, match="unknown method"):
        apply_overlay(wua, overlay, method="armean")  # type: ignore[arg-type]


def test_v1100_apply_overlay_product_method_is_bit_for_bit_v160():
    """v1.10.0 contract: passing ``method="product"`` (or omitting it)
    must reproduce the v1.6.0 numeric output exactly — base * overlay
    factor on each ``wua_m2_*`` column."""
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
    )

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.5}, {"mean_si": 0.4255},
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0, 3.0],
        "wua_m2_sp_juv": [10.0, 20.0, 30.0],
    })
    out = apply_overlay(wua, overlay, method="product")
    expected = [v * overlay.overlay_si for v in wua["wua_m2_sp_juv"]]
    assert list(out["wua_m2_composite_sp_juv"]) == pytest.approx(expected)

    # Default arg is product — same answer.
    out_default = apply_overlay(wua, overlay)
    assert list(out_default["wua_m2_composite_sp_juv"]) == pytest.approx(
        expected
    )


def test_v1100_apply_overlay_geom_mean_is_softer_than_product():
    """v1.10.0 design property: for non-degenerate overlays (both
    factors strictly in (0, 1)), the geometric-mean composite must
    sit ABOVE the product composite at the peak discharge — that is
    the defining "soft" property of HABBY's geom-mean option."""
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
    )

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.62}, {"mean_si": 0.4255},
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0, 3.0, 4.0, 5.0],
        "wua_m2_sp_juv": [10.0, 50.0, 100.0, 80.0, 30.0],
    })
    product = apply_overlay(wua, overlay, method="product")
    geom = apply_overlay(wua, overlay, method="geom_mean")
    product_peak = float(product["wua_m2_composite_sp_juv"].max())
    geom_peak = float(geom["wua_m2_composite_sp_juv"].max())
    # The geom-mean reach-scale linearisation softens the dampening.
    assert geom_peak > product_peak, (
        f"geom_mean ({geom_peak:.2f}) was not softer than product "
        f"({product_peak:.2f})"
    )


def test_v1100_apply_overlay_geom_mean_falls_back_to_product_when_no_overlay():
    """When no overlay is present, ``geom_mean`` must collapse to the
    identity path (same as product) — there is no "n-factor" to take
    a geom-mean over without at least one scalar overlay."""
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
    )

    overlay = CompositeOverlay(
        cover_si=None, thermal_si=None, overlay_si=None,
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0],
        "wua_m2_sp_juv": [10.0, 20.0],
    })
    geom = apply_overlay(wua, overlay, method="geom_mean")
    # No overlay → composite column equals base column.
    assert list(geom["wua_m2_composite_sp_juv"]) == [10.0, 20.0]


def test_v1100_composite_summary_records_method_key():
    """v1.10.0: the ``composite_hsi.json`` payload now carries the
    ``method`` key so audits and regulatory exports can tell which
    combination rule produced the numbers."""
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        composite_summary,
    )

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.62}, {"mean_si": 0.4255},
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0, 3.0],
        "wua_m2_sp_juv": [10.0, 20.0, 30.0],
    })
    for method in ("product", "geom_mean"):
        summary = composite_summary(wua, overlay, method=method)
        assert summary["method"] == method


def test_v1100_composite_header_lines_surfaces_method():
    """v1.10.0: every ``*_composite.csv`` header block now includes
    ``# method=<product|geom_mean>`` so a reviewer reading the file
    in isolation sees the combination rule applied."""
    summary = {
        "method": "geom_mean",
        "cover_si": 0.4255,
        "thermal_si": 0.62,
        "overlay_si": 0.26381,
        "n_overlays": 2,
        "n_discharges": 24,
        "by_species_stage": [],
    }
    lines = Case._composite_header_lines(summary)
    assert any("method=geom_mean" in line for line in lines), (
        f"v1.10.0 header missing method line: {lines}"
    )


def test_v1100_composite_header_lines_defaults_to_product_for_legacy_summaries():
    """v1.10.0 back-compat: a legacy summary (pre-v1.10.0; no
    ``method`` key) must render as ``method=product`` so old runs
    re-read in this version still look sane."""
    summary = {
        # No "method" key — legacy v1.6.0—v1.9.x summary shape.
        "cover_si": 0.4255,
        "thermal_si": 0.62,
        "overlay_si": 0.26381,
        "n_overlays": 2,
        "n_discharges": 24,
        "by_species_stage": [],
    }
    lines = Case._composite_header_lines(summary)
    assert any("method=product" in line for line in lines), (
        f"v1.10.0 fallback header missing method=product: {lines}"
    )


def test_v1101_geom_mean_all_zero_base_does_not_propagate_nan():
    """R6-1 (6th-review HIGH/MED): the v1.10.0 geom_mean
    implementation used ``area_proxy = nanmean(base[base>0]) or 1.0``
    as a scalar reweighting factor. When every base WUA value was
    zero, ``nanmean`` returned NaN and ``float(nan) or 1.0`` stayed
    NaN (nan is truthy in Python), so the whole composite column
    became NaN and ``composite_summary`` raised on idxmax.

    v1.10.1 redesigned geom_mean to a column-level overlay-softening
    rule that never touches an ``area_proxy``. Pin: an all-zero base
    column now produces an all-zero composite (no NaN), and
    ``composite_summary`` succeeds."""
    import math as _math

    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
        composite_summary,
    )

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.62}, {"mean_si": 0.4255},
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0, 3.0],
        "wua_m2_sp_juv": [0.0, 0.0, 0.0],
    })
    out = apply_overlay(wua, overlay, method="geom_mean")
    composite = out["wua_m2_composite_sp_juv"].tolist()
    assert all(not _math.isnan(v) for v in composite), (
        f"R6-1 regression: NaN propagated through geom_mean: {composite}"
    )
    assert composite == [0.0, 0.0, 0.0]

    # And composite_summary no longer raises on idxmax.
    summary = composite_summary(wua, overlay, method="geom_mean")
    assert summary["method"] == "geom_mean"
    assert summary["n_discharges"] == 3


def test_v1101_geom_mean_never_inflates_above_base():
    """R6-2 (6th-review HIGH from gemini): the v1.10.0 geom_mean
    reach-scale linearisation
    ``base^(1/n) · overlay_geom · area_proxy^((n-1)/n)`` could
    produce ``composite > base`` at low-flow discharges where
    ``base_Q`` was below the sweep-mean. A suitability overlay must
    never inflate the hydraulic base WUA — only dampen it.

    v1.10.1 redesigned geom_mean to ``base · (SI_T·SI_C)^(1/n)``
    which is monotone in base and bounded by ``base · 1 = base``.
    Pin across a wide WUA-Q sweep including very low and very high
    discharges."""
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
    )

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.62}, {"mean_si": 0.4255},
    )
    # Heavily skewed sweep — high WUA in the middle, near-zero at
    # the tails — the exact shape that triggered v1.10.0 inflation.
    wua = pd.DataFrame({
        "discharge_m3s": [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0],
        "wua_m2_sp_juv": [
            0.5, 5.0, 80.0, 300.0, 250.0, 30.0, 0.1,
        ],
    })
    geom = apply_overlay(wua, overlay, method="geom_mean")
    base_vals = wua["wua_m2_sp_juv"].tolist()
    composite_vals = geom["wua_m2_composite_sp_juv"].tolist()
    for q, base_v, comp_v in zip(
        wua["discharge_m3s"], base_vals, composite_vals, strict=True,
    ):
        assert comp_v <= base_v + 1e-9, (
            f"R6-2 regression: geom_mean inflated WUA at Q={q}: "
            f"base={base_v}, composite={comp_v}"
        )


def test_v1101_geom_mean_softens_overlay_by_nth_root():
    """v1.10.1 design property pin: the v1.10.0—v1.10.1 contract
    promises that geom_mean applies the overlay as the n-th root
    rather than the raw product. With two overlays present (n=3)
    and ``SI_T·SI_C = 0.26381``, the geom_mean factor must be
    exactly ``0.26381^(1/3) ≈ 0.6411`` — proving the redesign
    actually does column-level n-th-root softening (not a hidden
    return-to-product).
    """
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
    )

    overlay = CompositeOverlay.from_metrics(
        {"mean_SI": 0.62}, {"mean_si": 0.4255},
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0, 2.0],
        "wua_m2_sp_juv": [100.0, 200.0],
    })
    geom = apply_overlay(wua, overlay, method="geom_mean")
    expected_factor = (0.62 * 0.4255) ** (1.0 / 3.0)
    assert geom["wua_m2_composite_sp_juv"].iloc[0] == pytest.approx(
        100.0 * expected_factor
    )
    assert geom["wua_m2_composite_sp_juv"].iloc[1] == pytest.approx(
        200.0 * expected_factor
    )


def test_v1101_geom_mean_single_overlay_softens_less_than_double():
    """v1.10.1 design property: with only ONE overlay present
    (n=2), the n-th root softens less than with TWO overlays (n=3)
    because the exponent is larger (1/2 vs 1/3) and the overlay is
    multiplied into a smaller product. Pin the monotonicity in n.
    """
    import pandas as pd

    from openlimno.habitat.composite import (
        CompositeOverlay,
        apply_overlay,
    )

    overlay_one = CompositeOverlay.from_metrics(
        {"mean_SI": 0.5}, None,
    )
    overlay_two = CompositeOverlay.from_metrics(
        {"mean_SI": 0.5}, {"mean_si": 0.5},
    )
    wua = pd.DataFrame({
        "discharge_m3s": [1.0],
        "wua_m2_sp_juv": [100.0],
    })
    geom_one = apply_overlay(wua, overlay_one, method="geom_mean")
    geom_two = apply_overlay(wua, overlay_two, method="geom_mean")
    # 1-overlay: 100 * 0.5^(1/2)  = 70.71
    # 2-overlay: 100 * 0.25^(1/3) = 62.99
    assert geom_one["wua_m2_composite_sp_juv"].iloc[0] == pytest.approx(
        100.0 * (0.5 ** 0.5)
    )
    assert geom_two["wua_m2_composite_sp_juv"].iloc[0] == pytest.approx(
        100.0 * (0.25 ** (1.0 / 3.0))
    )


def test_v1100_composite_method_threaded_through_case_run(monkeypatch, tmp_path):
    """v1.10.0 integration: ``habitat.composite_overlay_method`` in
    case.yaml must reach :meth:`Case._maybe_run_composite_hsi` so a
    user can opt into geom-mean without monkey-patching."""
    if not CASE_YAML.exists():
        pytest.skip("Lemhi example missing")

    captured: dict[str, str] = {}
    real_helper = Case._maybe_run_composite_hsi

    def _spy(self, *args, **kwargs):
        captured["method"] = kwargs.get("method", "product")
        return real_helper(self, *args, **kwargs)

    monkeypatch.setattr(Case, "_maybe_run_composite_hsi", _spy)

    # Write the case.yaml beside the original so relative data paths
    # ``../../data/lemhi/…`` still resolve, but with the new opt-in
    # key inserted.
    import yaml
    cfg = yaml.safe_load(CASE_YAML.read_text())
    cfg["habitat"]["composite_overlay_method"] = "geom_mean"
    yaml_with_opt_in = CASE_YAML.parent / "case.geom_mean_opt_in.yaml"
    yaml_with_opt_in.write_text(yaml.safe_dump(cfg))
    try:
        Case.from_yaml(yaml_with_opt_in).run(discharges_m3s=[3.0])
    finally:
        yaml_with_opt_in.unlink(missing_ok=True)

    assert captured.get("method") == "geom_mean", (
        f"composite_overlay_method did not thread through case.run: "
        f"captured={captured}"
    )
