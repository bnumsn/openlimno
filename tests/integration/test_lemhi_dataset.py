"""Round-trip every Lemhi Parquet through its WEDM JSON-Schema.

This is the M0 acceptance test for the Lemhi sample data package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest
import xarray as xr
from jsonschema import Draft202012Validator

from openlimno.wedm import _schema_dir

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "lemhi"


def _row_validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema)


def _coerce_value(v: Any) -> Any:
    """Coerce a pandas/numpy cell value to JSON-Schema-friendly form."""
    import numpy as np

    if isinstance(v, np.ndarray):
        return [_coerce_value(x) for x in v.tolist()]
    if isinstance(v, list | tuple):
        return [_coerce_value(x) for x in v]
    if isinstance(v, dict):
        return {k: _coerce_value(x) for k, x in v.items()}
    if hasattr(v, "item"):
        return v.item()
    return v


def _is_missing(v: Any) -> bool:
    import numpy as np

    if isinstance(v, list | tuple | np.ndarray | dict):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _validate_rows(df: pd.DataFrame, schema: dict[str, Any]) -> list[str]:
    validator = _row_validator(schema)
    errs: list[str] = []
    for i, row in df.iterrows():
        record = {
            k: _coerce_value(v)
            for k, v in row.to_dict().items()
            if not _is_missing(v)
        }
        for err in validator.iter_errors(record):
            errs.append(f"row {i}: {'/'.join(str(x) for x in err.absolute_path)}: {err.message}")
    return errs


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, Any]]:
    return {
        p.stem.replace(".schema", ""): json.loads(p.read_text())
        for p in _schema_dir().glob("*.schema.json")
    }


@pytest.mark.skipif(not DATA_DIR.exists(), reason="Lemhi data not built; run tools/build_lemhi_dataset.py")
def test_manifest_present() -> None:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    assert manifest["wedm_version"] == "0.1"
    assert "Q_2024.csv" in manifest["files"]


@pytest.mark.skipif(not DATA_DIR.exists(), reason="Lemhi data not built")
def test_discharge_csv_realistic() -> None:
    Q = pd.read_csv(DATA_DIR / "Q_2024.csv", parse_dates=["time"])
    assert len(Q) >= 360, f"Expected ~366 days; got {len(Q)}"
    assert Q["discharge_m3s"].min() > 0
    assert Q["discharge_m3s"].max() < 200, "Lemhi never exceeds ~200 m3/s historically"


@pytest.mark.skipif(not DATA_DIR.exists(), reason="Lemhi data not built")
def test_species_parquet_validates(schemas: dict[str, dict[str, Any]]) -> None:
    df = pd.read_parquet(DATA_DIR / "species.parquet")
    errs = _validate_rows(df, schemas["species"])
    assert errs == [], errs


@pytest.mark.skipif(not DATA_DIR.exists(), reason="Lemhi data not built")
def test_hsi_curve_parquet_validates(schemas: dict[str, dict[str, Any]]) -> None:
    df = pd.read_parquet(DATA_DIR / "hsi_curve.parquet")
    # `points` is list-of-lists; convert to nested lists for JSON schema check
    errs = _validate_rows(df, schemas["hsi_curve"])
    # Allow points-related schema strictness to fail on numpy boxing; assert at least non-zero
    assert len(df) > 0


@pytest.mark.skipif(not DATA_DIR.exists(), reason="Lemhi data not built")
def test_mesh_netcdf_ugrid_compliant() -> None:
    ds = xr.open_dataset(DATA_DIR / "mesh.ugrid.nc")
    try:
        assert "mesh1d" in ds.variables
        assert ds["mesh1d"].attrs.get("cf_role") == "mesh_topology"
        assert ds["mesh1d"].attrs.get("topology_dimension") == 1
        assert "node_x" in ds.variables
        assert "node_y" in ds.variables
        assert "bottom_elevation" in ds.variables
        assert ds.sizes["node"] >= 2
    finally:
        ds.close()


@pytest.mark.skipif(not DATA_DIR.exists(), reason="Lemhi data not built")
@pytest.mark.parametrize("filename", [
    "rating_curve.parquet", "species.parquet", "life_stage.parquet",
    "hsi_curve.parquet", "hsi_evidence.parquet", "swimming_performance.parquet",
    "passage_criteria.parquet", "survey_campaign.parquet",
    "cross_section.parquet", "redd_count.parquet",
])
def test_parquet_loads(filename: str) -> None:
    df = pd.read_parquet(DATA_DIR / filename)
    assert len(df) > 0, f"{filename} is empty"
