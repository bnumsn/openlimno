"""Opt-in CF/UGRID NetCDF interoperability tests against public Delft3D data.

These tests intentionally do not run by default. Enable them explicitly with:

    OPENLIMNO_RUN_NETCDF_REAL=1 pytest tests/integration/test_netcdf_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

import pytest

from openlimno.preprocess import inspect_netcdf_hydraulic, read_external_model

RUN_REAL_NETCDF = os.environ.get("OPENLIMNO_RUN_NETCDF_REAL") == "1"

pytestmark = [
    pytest.mark.online,
]


NETCDF_FIXTURES = {
    "turbineTest_map.nc": {
        "url": (
            "https://raw.githubusercontent.com/MHKiT-Software/MHKiT-Python/main/"
            "examples/data/river/d3d/turbineTest_map.nc"
        ),
        "sha256": "1376eb803df69bfb248e2a395e23de001ed3f03f386607f3c1c02a1c6a941a9d",
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = os.environ.get("OPENLIMNO_NETCDF_FIXTURE_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp("openlimno_netcdf_fixtures")


def _download_fixture(
    spec: dict[str, str],
    name: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    if not RUN_REAL_NETCDF:
        pytest.skip("set OPENLIMNO_RUN_NETCDF_REAL=1 to download and run NetCDF fixture tests")

    target = _fixture_dir(tmp_path_factory) / name
    expected = spec["sha256"]
    if target.exists() and _sha256(target) == expected:
        return target
    urllib.request.urlretrieve(spec["url"], target)
    actual = _sha256(target)
    if actual != expected:
        target.unlink(missing_ok=True)
        raise AssertionError(f"{name} SHA256 mismatch: expected {expected}, got {actual}")
    return target


def test_real_delft3d_netcdf_imports_hydraulic_cells(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = _download_fixture(
        NETCDF_FIXTURES["turbineTest_map.nc"],
        "turbineTest_map.nc",
        tmp_path_factory,
    )

    inspection = inspect_netcdf_hydraulic(path)
    assert inspection.n_cells == 1152
    assert inspection.selected_depth == "waterdepth"
    assert inspection.selected_water_surface == "s1"
    assert inspection.selected_u == "ucxa"
    assert inspection.selected_v == "ucya"
    assert inspection.selected_x == "FlowElem_xcc"
    assert inspection.selected_y == "FlowElem_ycc"
    assert inspection.selected_area == "FlowElem_bac"

    result = read_external_model(path, source="delft3d-netcdf", time_index=-1)

    assert result.source_key == "delft3d-netcdf"
    assert not result.warnings
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert len(result.table) == 1152
    assert {"x", "y", "depth_m", "water_surface_m", "velocity_ms", "area_m2"}.issubset(
        result.table.columns
    )
    assert result.table["time_index"].iloc[0] == 4
    assert result.table["area_m2"].min() == pytest.approx(0.0625)
    assert result.table["area_m2"].max() == pytest.approx(0.0625)
    assert result.table["depth_m"].between(1.9, 2.1).all()
    assert result.table["velocity_ms"].between(0.9, 1.1).all()
    assert result.table["x"].min() == pytest.approx(0.125)
    assert result.table["x"].max() == pytest.approx(17.875)
