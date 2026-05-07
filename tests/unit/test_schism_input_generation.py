"""SCHISM hgrid.gr3 + param.nml generation tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from openlimno.hydro.schism import (
    SCHISMAdapter,
    _render_param_nml,
    _write_hgrid_from_ugrid,
)


def make_synthetic_ugrid_2d(path: Path) -> None:
    """Tiny 2D triangular mesh: 4 nodes, 2 triangles."""
    x = np.array([0.0, 1.0, 1.0, 0.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    z = np.array([0.5, 0.4, 0.3, 0.4])
    face_nodes = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)

    ds = xr.Dataset(
        data_vars={
            "mesh2d": (
                (),
                0,
                {
                    "cf_role": "mesh_topology",
                    "topology_dimension": 2,
                    "node_coordinates": "mesh2d_node_x mesh2d_node_y",
                    "face_node_connectivity": "mesh2d_face_nodes",
                },
            ),
            "mesh2d_node_x": (("node",), x, {"standard_name": "longitude"}),
            "mesh2d_node_y": (("node",), y, {"standard_name": "latitude"}),
            "mesh2d_face_nodes": (
                ("face", "vertex"),
                face_nodes,
                {"_FillValue": -1, "start_index": 0},
            ),
            "bottom_elevation": (("node",), z, {"units": "m"}),
        },
        attrs={"Conventions": "UGRID-1.0"},
    )
    ds.to_netcdf(path)


def test_render_param_nml_defaults_runnable() -> None:
    txt = _render_param_nml()
    assert txt.startswith("&CORE")
    assert "rnday" in txt
    assert txt.rstrip().endswith("/")


def test_render_param_nml_overrides() -> None:
    txt = _render_param_nml({"rnday": 10.0, "ibc": 1})
    assert "rnday = 10" in txt
    assert "ibc = 1" in txt


def test_hgrid_from_ugrid_round_trip(tmp_path: Path) -> None:
    ug = tmp_path / "mesh.nc"
    hg = tmp_path / "hgrid.gr3"
    make_synthetic_ugrid_2d(ug)
    _write_hgrid_from_ugrid(ug, hg)

    text = hg.read_text()
    lines = text.splitlines()
    assert lines[0] == "OpenLimno UGRID-derived mesh"
    ne, np_count = lines[1].split()
    assert int(ne) == 2
    assert int(np_count) == 4

    # Node line format: i x y z
    node_line = lines[2].split()
    assert node_line[0] == "1"
    # Element line format: i type n1 n2 n3
    elem_line = lines[6].split()
    assert elem_line[1] == "3"  # triangle


def test_adapter_prepare_with_real_mesh(tmp_path: Path) -> None:
    ug = tmp_path / "mesh.nc"
    make_synthetic_ugrid_2d(ug)

    adapter = SCHISMAdapter()
    work = tmp_path / "run"
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("# stub\n")
    adapter.prepare(case_yaml, work, wedm_mesh_path=ug)

    hgrid = (work / "hgrid.gr3").read_text()
    assert "placeholder" not in hgrid
    assert "OpenLimno UGRID-derived mesh" in hgrid

    param = (work / "param.nml").read_text()
    assert "&CORE" in param

    import json

    marker = json.loads((work / ".openlimno_prepared").read_text())
    assert marker["real_mesh"] is True


def test_adapter_prepare_falls_back_without_mesh(tmp_path: Path) -> None:
    adapter = SCHISMAdapter()
    work = tmp_path / "run"
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("# stub\n")
    adapter.prepare(case_yaml, work)

    hgrid = (work / "hgrid.gr3").read_text()
    assert "placeholder" in hgrid

    import json

    marker = json.loads((work / ".openlimno_prepared").read_text())
    assert marker["real_mesh"] is False
