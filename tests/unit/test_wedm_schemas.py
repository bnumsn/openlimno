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
