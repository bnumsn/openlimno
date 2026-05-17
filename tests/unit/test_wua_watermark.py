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
        assert "OpenLimno v1.7.0 composite overlay" in head, p


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
