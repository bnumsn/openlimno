"""Opt-in HEC-RAS interoperability tests against public HDF sample files.

These tests intentionally do not run by default. Enable them explicitly with:

    OPENLIMNO_RUN_HECRAS_REAL=1 pytest tests/integration/test_hecras_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

import pytest

from openlimno.preprocess import inspect_hecras_hdf, read_external_model

RUN_REAL_HECRAS = os.environ.get("OPENLIMNO_RUN_HECRAS_REAL") == "1"

pytestmark = [
    pytest.mark.online,
]


HECRAS_FIXTURES = {
    "BaldEagleDamBrk.p18.hdf": {
        "url": (
            "https://raw.githubusercontent.com/fema-ffrd/rashdf/main/"
            "tests/data/ras/BaldEagleDamBrk.p18.hdf"
        ),
        "sha256": "2b11056cfd5ac25011d33ae87bccb94135900364ef4a6637bd847f503b01a7a8",
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = os.environ.get("OPENLIMNO_HECRAS_FIXTURE_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp("openlimno_hecras_fixtures")


def _download_fixture(
    spec: dict[str, str],
    name: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    if not RUN_REAL_HECRAS:
        pytest.skip("set OPENLIMNO_RUN_HECRAS_REAL=1 to download and run HEC-RAS tests")

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


def test_real_hecras_hdf_imports_summary_hydraulic_cells(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = _download_fixture(
        HECRAS_FIXTURES["BaldEagleDamBrk.p18.hdf"],
        "BaldEagleDamBrk.p18.hdf",
        tmp_path_factory,
    )

    inspection = inspect_hecras_hdf(path, flow_area="Upper 2D Area")
    assert inspection.flow_areas == ("BaldEagleCr", "Upper 2D Area")
    assert inspection.selected_flow_area == "Upper 2D Area"
    assert inspection.n_cells == 1251
    assert inspection.cell_center_path is not None
    assert "derived cell face topology" in inspection.cell_center_path

    result = read_external_model(path, source="hecras-hdf", flow_area="Upper 2D Area")

    assert result.source_key == "hecras-hdf"
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert len(result.table) == 1251
    assert {"x", "y", "area_m2", "water_surface_m", "velocity_ms"}.issubset(result.table.columns)
    assert result.table["flow_area"].eq("Upper 2D Area").all()
    assert result.table["area_m2"].max() > 0.0
    assert result.table["water_surface_m"].max() > 700.0
    assert result.table["velocity_ms"].max() > 0.0
    assert any("depth" in warning.lower() for warning in result.warnings)
    assert any("face velocity" in warning.lower() for warning in result.warnings)
