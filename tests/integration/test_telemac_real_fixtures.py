"""Opt-in TELEMAC interoperability tests against public Selafin sample files.

These tests intentionally do not run by default. Enable them explicitly with:

    OPENLIMNO_RUN_TELEMAC_REAL=1 pytest tests/integration/test_telemac_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

import pytest

from openlimno.preprocess import inspect_telemac_selafin, read_external_model

RUN_REAL_TELEMAC = os.environ.get("OPENLIMNO_RUN_TELEMAC_REAL") == "1"

pytestmark = [
    pytest.mark.online,
]


TELEMAC_FIXTURES = {
    "r2dsteady-t15k.slf": {
        "url": (
            "https://raw.githubusercontent.com/hydro-informatics/telemac/main/"
            "unsteady2d-tutorial/r2dsteady-t15k.slf"
        ),
        "sha256": "059bcc982801a653374991f48465fac28b3a725c8f37aeab56e2c0cae8fedc4c",
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = os.environ.get("OPENLIMNO_TELEMAC_FIXTURE_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp("openlimno_telemac_fixtures")


def _download_fixture(
    spec: dict[str, str],
    name: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    if not RUN_REAL_TELEMAC:
        pytest.skip("set OPENLIMNO_RUN_TELEMAC_REAL=1 to download and run TELEMAC fixture tests")

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


def test_real_telemac_selafin_imports_hydraulic_cells(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = _download_fixture(
        TELEMAC_FIXTURES["r2dsteady-t15k.slf"],
        "r2dsteady-t15k.slf",
        tmp_path_factory,
    )

    inspection = inspect_telemac_selafin(path)
    assert inspection.n_points == 12814
    assert inspection.n_elements == 25007
    assert inspection.points_per_element == 3
    assert inspection.n_timesteps == 7
    assert {"VELOCITY U", "VELOCITY V", "WATER DEPTH", "FREE SURFACE"}.issubset(
        {var.name for var in inspection.variables}
    )

    result = read_external_model(path, source="telemac-slf", time_index=-1)

    assert result.source_key == "telemac-slf"
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert len(result.table) == 25007
    assert {"depth_m", "velocity_ms", "water_surface_m", "area_m2"}.issubset(
        result.table.columns
    )
    assert result.table["depth_m"].max() > 0.0
    assert result.table["velocity_ms"].max() > 0.0
    assert result.table["area_m2"].min() > 0.0
