"""Opt-in River2D interoperability tests against official public tutorial files.

These tests intentionally do not run by default. Enable them explicitly with:

    OPENLIMNO_RUN_RIVER2D_REAL=1 pytest tests/integration/test_river2d_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
import zipfile
from pathlib import Path

import pytest

from openlimno.preprocess import (
    inspect_habitat_exchange,
    read_external_model,
    read_habitat_exchange,
    read_river2d_elements,
    validate_ugrid_mesh,
    write_river2d_ugrid,
)

RUN_REAL_RIVER2D = os.environ.get("OPENLIMNO_RUN_RIVER2D_REAL") == "1"

pytestmark = [
    pytest.mark.online,
]


RIVER2D_FIXTURES = {
    "R2D_Habitat.zip": {
        "url": (
            "https://firebasestorage.googleapis.com/v0/b/"
            "rivericeresearchgroup.appspot.com/o/River2DDoc%2FR2D_Habitat.zip"
            "?alt=media&token=cf7cac7a-abf7-462c-aaaa-47a2549a006f"
        ),
        "sha256": "71390ccf73553ccc7b283badedcf394c6141a184c717a2c2cfce5d98e41878fa",
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    env_dir = os.environ.get("OPENLIMNO_RIVER2D_FIXTURE_DIR")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return tmp_path_factory.mktemp("openlimno_river2d_fixtures")


def _download_fixture(
    spec: dict[str, str],
    name: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    if not RUN_REAL_RIVER2D:
        pytest.skip("set OPENLIMNO_RUN_RIVER2D_REAL=1 to download River2D fixture tests")

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


def _extract_habitat_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    zip_path = _download_fixture(
        RIVER2D_FIXTURES["R2D_Habitat.zip"],
        "R2D_Habitat.zip",
        tmp_path_factory,
    )
    extract_dir = _fixture_dir(tmp_path_factory) / "R2D_Habitat"
    marker = extract_dir / "R2D_Habitat" / "fortnewfinal.CDG"
    if marker.exists():
        return extract_dir / "R2D_Habitat"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    return extract_dir / "R2D_Habitat"


def test_official_river2d_habitat_cdg_imports_nodes_and_elements(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    fixture_dir = _extract_habitat_fixture(tmp_path_factory)
    cdg = fixture_dir / "fortnewfinal.CDG"

    result = read_external_model(cdg, source="river2d-cdg")
    nodes = result.table
    elements = read_river2d_elements(cdg)
    ugrid_path = write_river2d_ugrid(cdg, _fixture_dir(tmp_path_factory) / "river2d_mesh.nc")
    ugrid = validate_ugrid_mesh(ugrid_path)

    assert result.source_key == "river2d-cdg"
    assert nodes.attrs["openlimno_output_table"] == "mesh_nodes"
    assert nodes.attrs["river2d_n_elements"] == 6214
    assert len(nodes) == 3240
    assert len(elements) == 6214
    assert ugrid.is_valid
    assert ugrid.n_nodes == 3240
    assert ugrid.n_faces == 6214
    assert {"node_id", "x", "y", "z", "depth_m", "velocity_ms"}.issubset(nodes.columns)
    assert {"element_id", "node_1", "node_2", "node_3"}.issubset(elements.columns)
    assert nodes["depth_m"].notna().all()
    assert nodes["velocity_ms"].max() > 0.1


def test_official_river2d_habitat_wua_csv_imports_cells(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    fixture_dir = _extract_habitat_fixture(tmp_path_factory)
    habitat_csv = fixture_dir / "Nodal_Attributes.csv"

    inspection = inspect_habitat_exchange(habitat_csv)
    result = read_habitat_exchange(habitat_csv, source_key="river2d-habitat")

    assert inspection.table_type == "habitat_cells"
    assert inspection.detected_roles["cell_id"] == "n"
    assert inspection.detected_roles["wua_m2"] == "WUA"
    assert result.table.attrs["openlimno_output_table"] == "habitat_cells"
    assert len(result.table) == 3240
    assert result.table["wua_m2"].sum() == pytest.approx(170.3601)
    assert result.summary.warnings == (
        "No area column detected; per-cell WUA is preserved only if present.",
    )
