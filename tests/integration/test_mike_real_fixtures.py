"""Opt-in MIKE interoperability tests against DHI public sample files.

These tests intentionally do not run by default. They need network access and
optional DHI Python readers, so enable them explicitly with:

    OPENLIMNO_RUN_MIKE_REAL=1 pytest tests/integration/test_mike_real_fixtures.py

or use the project-managed MIKE environment, which provides conda-forge
dotnet-runtime for Linux:

    OPENLIMNO_RUN_MIKE_REAL=1 pixi run -e mike pytest tests/integration/test_mike_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import importlib
import os
import urllib.request
from pathlib import Path

import pytest

from openlimno.preprocess import inspect_mike_file, read_external_model
from openlimno.preprocess.mike import MIKE_1D_LINUX_DOTNET_HINT

RUN_REAL_MIKE = os.environ.get("OPENLIMNO_RUN_MIKE_REAL") == "1"

pytestmark = [
    pytest.mark.mike,
    pytest.mark.online,
]


MIKEIO_FIXTURES = {
    "HD2D.dfsu": {
        "url": "https://raw.githubusercontent.com/DHI/mikeio/main/tests/testdata/HD2D.dfsu",
        "sha256": "be3726a349884781a11450f934be1c188fbd971157e051ff7f85383c56122638",
    },
}

MIKEIO1D_FIXTURES = {
    "mikep_cs_demo.xns11": {
        "url": (
            "https://raw.githubusercontent.com/DHI/mikeio1d/main/"
            "tests/testdata/mikep_cs_demo.xns11"
        ),
        "sha256": "e7b9d31f370922684cbb50a84188826e63a49ee4e5137b22096acd061f000c21",
    },
    "network_river.res1d": {
        "url": (
            "https://raw.githubusercontent.com/DHI/mikeio1d/main/"
            "tests/testdata/network_river.res1d"
        ),
        "sha256": "3f9526cebc2618bf74ad4ed31814d01e98ecd1b3bddd7af738dda5c9a97f17e5",
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = os.environ.get("OPENLIMNO_MIKE_FIXTURE_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp("openlimno_mike_fixtures")


def _download_fixture(
    spec: dict[str, str],
    name: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    if not RUN_REAL_MIKE:
        pytest.skip("set OPENLIMNO_RUN_MIKE_REAL=1 to download and run MIKE fixture tests")

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


def test_real_mikeio_dfsu_imports_hydraulic_cells(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    if not RUN_REAL_MIKE:
        pytest.skip("set OPENLIMNO_RUN_MIKE_REAL=1 to download and run MIKE fixture tests")
    _import_optional_or_skip("mikeio")
    path = _download_fixture(MIKEIO_FIXTURES["HD2D.dfsu"], "HD2D.dfsu", tmp_path_factory)

    inspection = inspect_mike_file(path)
    assert inspection.source_key == "mike-dfs"
    assert inspection.file_kind == "dfsu"
    assert inspection.n_elements == 884
    assert inspection.n_timesteps == 9
    assert {"Surface elevation", "Current speed"}.issubset(inspection.item_names)

    result = read_external_model(path, source="mike-dfs", time_index=0)

    assert result.source_key == "mike-dfs"
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert len(result.table) == 884
    assert {"source_file", "cell_id", "x", "y", "water_surface_m", "velocity_ms"}.issubset(
        result.table.columns
    )
    assert result.table["velocity_ms"].notna().any()
    assert result.table["water_surface_m"].notna().any()


def test_real_mikeio1d_xns11_imports_cross_sections(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    if not RUN_REAL_MIKE:
        pytest.skip("set OPENLIMNO_RUN_MIKE_REAL=1 to download and run MIKE fixture tests")
    _import_optional_or_skip("mikeio1d")
    path = _download_fixture(
        MIKEIO1D_FIXTURES["mikep_cs_demo.xns11"],
        "mikep_cs_demo.xns11",
        tmp_path_factory,
    )

    try:
        result = read_external_model(path, source="mike-1d")
    except Exception as exc:
        # mikeio1d can import successfully while the local .NET runtime needed
        # to open real files is missing, especially on Linux CI/dev machines.
        pytest.skip(
            "mikeio1d runtime unavailable for real XNS11 fixture: "
            f"{exc} {MIKE_1D_LINUX_DOTNET_HINT}"
        )

    assert result.source_key == "mike-1d"
    assert result.table.attrs["openlimno_output_table"] == "cross_section_points"
    assert len(result.table) > 100
    assert {"reach", "station_id", "station_m", "elevation_m"}.issubset(result.table.columns)


def test_real_mikeio1d_res1d_imports_timeseries(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    if not RUN_REAL_MIKE:
        pytest.skip("set OPENLIMNO_RUN_MIKE_REAL=1 to download and run MIKE fixture tests")
    _import_optional_or_skip("mikeio1d")
    path = _download_fixture(
        MIKEIO1D_FIXTURES["network_river.res1d"],
        "network_river.res1d",
        tmp_path_factory,
    )

    try:
        inspection = inspect_mike_file(path)
        result = read_external_model(path, source="mike-1d")
    except Exception as exc:
        # mikeio1d can import successfully while the local .NET runtime needed
        # to open real files is missing, especially on Linux CI/dev machines.
        pytest.skip(
            "mikeio1d runtime unavailable for real RES1D fixture: "
            f"{exc} {MIKE_1D_LINUX_DOTNET_HINT}"
        )

    assert inspection.source_key == "mike-1d"
    assert inspection.file_kind == "res1d"
    assert inspection.n_timesteps == 73
    assert inspection.output_table == "mike_timeseries"
    assert {"WaterLevel", "Discharge", "FlowVelocity"}.issubset(inspection.item_names)

    columns = [str(column) for column in result.table.columns]
    assert result.source_key == "mike-1d"
    assert result.table.attrs["openlimno_output_table"] == "mike_timeseries"
    assert len(result.table) == 73
    assert len(set(columns)) == len(columns)
    assert any("WaterLevel" in column for column in columns)
    assert any("Discharge" in column for column in columns)
    assert result.warnings == (
        "Duplicate MIKE 1D result column names were suffixed for tabular export.",
    )


def _import_optional_or_skip(module_name: str) -> None:
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError:
        pytest.skip(f"optional dependency {module_name!r} is not installed")
    except RuntimeError as exc:
        hint = f" {MIKE_1D_LINUX_DOTNET_HINT}" if module_name == "mikeio1d" else ""
        pytest.skip(f"optional dependency {module_name!r} runtime is unavailable: {exc}{hint}")
