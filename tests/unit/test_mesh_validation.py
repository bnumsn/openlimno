"""UGRID-2D mesh validator tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from openlimno.preprocess import validate_ugrid_mesh

LEMHI_MESH = Path(__file__).resolve().parents[2] / "data" / "lemhi" / "mesh.ugrid.nc"


def _write_minimal_ugrid(path: Path, *, with_depth: bool = True,
                          with_conventions: bool = True) -> None:
    x = np.array([0.0, 1.0, 1.0, 0.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    z = np.array([0.5, 0.4, 0.3, 0.4])
    face_nodes = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    data_vars = {
        "mesh2d_node_x": (("node",), x),
        "mesh2d_node_y": (("node",), y),
        "mesh2d_face_nodes": (("face", "vertex"), face_nodes,
                               {"_FillValue": -1}),
    }
    if with_depth:
        data_vars["bottom_elevation"] = (("node",), z)
    attrs = {"Conventions": "UGRID-1.0"} if with_conventions else {}
    xr.Dataset(data_vars=data_vars, attrs=attrs).to_netcdf(path)


def test_valid_minimal_mesh(tmp_path: Path) -> None:
    p = tmp_path / "m.nc"
    _write_minimal_ugrid(p)
    rep = validate_ugrid_mesh(p)
    assert rep.is_valid
    assert rep.n_nodes == 4
    assert rep.n_faces == 2
    assert rep.has_bottom_elevation
    assert rep.errors == []


def test_missing_connectivity_invalid(tmp_path: Path) -> None:
    p = tmp_path / "bad.nc"
    x = np.array([0.0, 1.0])
    y = np.array([0.0, 1.0])
    xr.Dataset({"mesh2d_node_x": (("node",), x),
                 "mesh2d_node_y": (("node",), y)}).to_netcdf(p)
    rep = validate_ugrid_mesh(p)
    assert not rep.is_valid
    assert any("connectivity" in e.lower() for e in rep.errors)


def test_ugrid_1d_mesh_is_valid(tmp_path: Path) -> None:
    p = tmp_path / "1d.nc"
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.0, 0.0, 0.0])
    edge_nodes = np.array([[0, 1], [1, 2]], dtype=np.int32)
    xr.Dataset(
        data_vars={
            "node_x": (("node",), x),
            "node_y": (("node",), y),
            "edge_nodes": (("edge", "two"), edge_nodes),
        },
        attrs={"Conventions": "CF-1.8 UGRID-1.0"},
    ).to_netcdf(p)
    rep = validate_ugrid_mesh(p)
    assert rep.is_valid
    assert rep.topology_dim == 1
    assert rep.n_edges == 2
    assert rep.n_faces == 0


def test_missing_depth_warns_only(tmp_path: Path) -> None:
    p = tmp_path / "no_depth.nc"
    _write_minimal_ugrid(p, with_depth=False)
    rep = validate_ugrid_mesh(p)
    assert rep.is_valid
    assert not rep.has_bottom_elevation
    assert any("bottom_elevation" in w for w in rep.warnings)


def test_missing_conventions_warns_only(tmp_path: Path) -> None:
    p = tmp_path / "no_conv.nc"
    _write_minimal_ugrid(p, with_conventions=False)
    rep = validate_ugrid_mesh(p)
    assert rep.is_valid
    assert any("UGRID" in w for w in rep.warnings)


def test_nonexistent_path_invalid(tmp_path: Path) -> None:
    rep = validate_ugrid_mesh(tmp_path / "nope.nc")
    assert not rep.is_valid
    assert any("does not exist" in e for e in rep.errors)


def test_lemhi_mesh_validates() -> None:
    if not LEMHI_MESH.exists():
        pytest.skip("Lemhi data not built")
    rep = validate_ugrid_mesh(LEMHI_MESH)
    assert rep.is_valid, f"Lemhi mesh invalid: {rep.errors}"
    assert rep.n_nodes > 0
    # Lemhi sample mesh is UGRID-1D (network of cross-section nodes + edges)
    assert rep.topology_dim == 1
    assert rep.n_edges > 0
