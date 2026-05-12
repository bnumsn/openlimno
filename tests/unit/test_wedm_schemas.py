"""Unit tests for WEDM JSON-Schemas.

These exercise schema self-validation and a few representative valid/invalid
fixtures. Real per-table tests will expand in M1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from openlimno.wedm import _schema_dir, load_schema, validate_case

SCHEMAS = sorted(_schema_dir().glob("*.schema.json"))


@pytest.mark.parametrize("schema_path", SCHEMAS, ids=lambda p: p.name)
def test_schema_self_validates_as_draft_2020_12(schema_path: Path) -> None:
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)


def test_load_schema_returns_dict() -> None:
    schema = load_schema("case")
    assert isinstance(schema, dict)
    assert schema["title"] == "OpenLimno Case Configuration"


def test_case_schema_rejects_missing_required(tmp_path: Path) -> None:
    case = tmp_path / "incomplete.yaml"
    case.write_text("openlimno: '0.1'\n", encoding="utf-8")
    errors = validate_case(case)
    assert errors, "Should report missing required fields"
    joined = " ".join(errors)
    assert "case" in joined or "required" in joined.lower()


def test_case_schema_minimal_valid(tmp_path: Path) -> None:
    case = tmp_path / "ok.yaml"
    case.write_text(
        """
openlimno: '0.1'
case:
  name: smoke
  crs: EPSG:32612
mesh:
  uri: file://nonexistent.nc
hydrodynamics:
  backend: builtin-1d
habitat:
  species: [oncorhynchus_mykiss]
  stages: [spawning]
  metric: wua-q
  composite: min
output:
  dir: ./out
  formats: [netcdf]
""".lstrip(),
        encoding="utf-8",
    )
    errors = validate_case(case)
    assert errors == [], f"Unexpected errors: {errors}"


def _v02_case_base() -> str:
    """Minimal v0.2 case body shared by the v0.2-specific tests."""
    return """
openlimno: '0.2'
case:
  name: smoke_v02
  crs: EPSG:4326
mesh:
  uri: file://nonexistent.nc
hydrodynamics:
  backend: builtin-1d
habitat:
  species: [oncorhynchus_mykiss]
  stages: [spawning]
  metric: wua-q
  composite: min
output:
  dir: ./out
  formats: [netcdf]
""".lstrip()


def test_case_schema_accepts_v02_version_string(tmp_path: Path) -> None:
    """v0.2 documents must validate against the same schema as v0.1
    (additive change — no breakage)."""
    case = tmp_path / "v02.yaml"
    case.write_text(_v02_case_base(), encoding="utf-8")
    errors = validate_case(case)
    assert errors == [], f"v0.2 minimal case must validate: {errors}"


def test_case_schema_accepts_bbox(tmp_path: Path) -> None:
    """v0.2 adds case.bbox = [lon_min, lat_min, lon_max, lat_max]."""
    case = tmp_path / "bbox.yaml"
    body = _v02_case_base().replace(
        "  crs: EPSG:4326",
        "  crs: EPSG:4326\n  bbox: [100.10, 38.10, 100.30, 38.30]",
    )
    case.write_text(body, encoding="utf-8")
    assert validate_case(case) == []


def test_case_schema_rejects_bad_bbox(tmp_path: Path) -> None:
    """Wrong number of bbox elements must fail."""
    case = tmp_path / "bbox_bad.yaml"
    body = _v02_case_base().replace(
        "  crs: EPSG:4326",
        "  crs: EPSG:4326\n  bbox: [100.10, 38.10, 100.30]",  # 3 not 4
    )
    case.write_text(body, encoding="utf-8")
    errors = validate_case(case)
    assert errors, "3-element bbox must be rejected"


def test_case_schema_accepts_full_v02_data_block(tmp_path: Path) -> None:
    """All five new data.* blocks together must validate."""
    case = tmp_path / "full_v02.yaml"
    body = _v02_case_base() + """data:
  dem: data/dem.tif
  lulc:
    uri: data/lulc_2021.tif
    year: 2021
    version: v200
    class_km2:
      "30": 288.14
      "60": 45.62
      "10": 40.80
  soil:
    uri: data/soil.csv
    lat: 38.20
    lon: 100.20
    properties: [clay, sand, silt, phh2o]
    depths: [0-5cm, 5-15cm]
    statistic: mean
  watershed:
    uri: data/watershed.geojson
    pour_lat: 38.20
    pour_lon: 100.20
    pour_hybas_id: 4120511510
    region: as
    level: 12
    n_basins: 18
    area_km2: 2503.4
  species_occurrences:
    uri: data/species_gbif_8215487.csv
    scientific_name: Salmo trutta
    canonical_name: Salmo trutta
    usage_key: 8215487
    family: Salmonidae
    order: Salmoniformes
    match_type: EXACT
    confidence: 99
    occurrence_count_returned: 300
    occurrence_count_total: 1104661
  climate:
    uri: data/climate_2020_2024.csv
    source: open-meteo
    lat: 38.20
    lon: 100.20
    start_year: 2020
    end_year: 2024
"""
    case.write_text(body, encoding="utf-8")
    errors = validate_case(case)
    assert errors == [], f"Full v0.2 data block must validate: {errors}"


def test_case_schema_rejects_unknown_worldcover_class_code(tmp_path: Path) -> None:
    """data.lulc.class_km2 only accepts WorldCover's 11 codes
    (10/20/30/40/50/60/70/80/90/95/100). A typo like '35' must fail
    so downstream code never iterates a non-existent class."""
    case = tmp_path / "bad_lulc.yaml"
    body = _v02_case_base() + """data:
  lulc:
    uri: data/lulc_2021.tif
    class_km2:
      "35": 1.0
"""
    case.write_text(body, encoding="utf-8")
    errors = validate_case(case)
    assert errors, "class_km2 key '35' (not a WorldCover code) must fail"


def test_case_schema_rejects_unknown_climate_source(tmp_path: Path) -> None:
    case = tmp_path / "bad_climate.yaml"
    body = _v02_case_base() + """data:
  climate:
    uri: data/climate.csv
    source: openweathermap
"""
    case.write_text(body, encoding="utf-8")
    errors = validate_case(case)
    assert errors, "climate.source='openweathermap' must fail (not in enum)"


def test_case_schema_rejects_unknown_hydrosheds_region(tmp_path: Path) -> None:
    case = tmp_path / "bad_watershed.yaml"
    body = _v02_case_base() + """data:
  watershed:
    uri: data/watershed.geojson
    pour_lat: 0
    pour_lon: 0
    region: xx
"""
    case.write_text(body, encoding="utf-8")
    errors = validate_case(case)
    assert errors, "watershed.region='xx' must fail (not a continent code)"


def test_case_schema_rejects_unknown_soil_depth(tmp_path: Path) -> None:
    case = tmp_path / "bad_soil.yaml"
    body = _v02_case_base() + """data:
  soil:
    uri: data/soil.csv
    lat: 38.20
    lon: 100.20
    depths: [0-3cm]
"""
    case.write_text(body, encoding="utf-8")
    errors = validate_case(case)
    assert errors, "soil.depths=['0-3cm'] must fail (not a SoilGrids depth)"


def test_case_schema_rejects_unknown_match_type(tmp_path: Path) -> None:
    case = tmp_path / "bad_species.yaml"
    body = _v02_case_base() + """data:
  species_occurrences:
    uri: data/sp.csv
    scientific_name: Salmo trutta
    usage_key: 8215487
    match_type: PARTIAL
"""
    case.write_text(body, encoding="utf-8")
    errors = validate_case(case)
    assert errors, "match_type='PARTIAL' must fail (not in GBIF enum)"


def test_geometric_mean_requires_acknowledge_independence(tmp_path: Path) -> None:
    case = tmp_path / "no_ack.yaml"
    case.write_text(
        """
openlimno: '0.1'
case:
  name: smoke
  crs: EPSG:32612
mesh:
  uri: file://nonexistent.nc
hydrodynamics:
  backend: builtin-1d
habitat:
  species: [oncorhynchus_mykiss]
  stages: [spawning]
  metric: wua-q
  composite: geometric_mean
output:
  dir: ./out
  formats: [netcdf]
""".lstrip(),
        encoding="utf-8",
    )
    errors = validate_case(case)
    assert errors, "geometric_mean without acknowledge_independence must fail"
