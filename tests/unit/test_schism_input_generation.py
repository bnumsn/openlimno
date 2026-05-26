"""SCHISM hgrid.gr3 + param.nml generation tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from openlimno.hydro.schism import (
    SCHISMAdapter,
    _render_bctides_template,
    _render_param_nml,
    _write_hgrid_from_ugrid,
    write_schism_type1_boundary_forcing,
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


def test_render_bctides_template_matches_open_boundary_count() -> None:
    txt = _render_bctides_template(2)
    assert "2   ! nope" in txt
    assert "open boundary 1" in txt
    assert "open boundary 2" in txt


def test_write_schism_type1_boundary_forcing_package(tmp_path: Path) -> None:
    forcing = pd.DataFrame(
        [
            {
                "boundary_id": 1,
                "role": "upstream_inflow",
                "boundary_condition_hint": "flow",
                "time_seconds": 0.0,
                "stage_m": 10.0,
                "discharge_m3s": 5.0,
            },
            {
                "boundary_id": 2,
                "role": "downstream_stage",
                "boundary_condition_hint": "stage",
                "time_seconds": 0.0,
                "stage_m": 7.0,
                "discharge_m3s": 5.0,
            },
            {
                "boundary_id": 1,
                "role": "upstream_inflow",
                "boundary_condition_hint": "flow",
                "time_seconds": 3600.0,
                "stage_m": 10.2,
                "discharge_m3s": 6.0,
            },
            {
                "boundary_id": 2,
                "role": "downstream_stage",
                "boundary_condition_hint": "stage",
                "time_seconds": 3600.0,
                "stage_m": 7.1,
                "discharge_m3s": 6.0,
            },
        ]
    )

    package = write_schism_type1_boundary_forcing(
        forcing,
        tmp_path,
        boundary_node_counts=[3, 4],
        stage_reference_m=5.0,
    )

    assert package.n_boundaries == 2
    assert package.n_flux_boundaries == 1
    assert package.n_elevation_boundaries == 1
    assert package.n_times == 2
    assert package.elev_th_path is not None
    assert package.flux_th_path is not None
    bctides = package.bctides_path.read_text()
    assert "3 0 1 0 0" in bctides
    assert "4 1 0 0 0" in bctides
    assert package.flux_th_path.read_text().splitlines() == ["0.000000 -5", "3600.000000 -6"]
    assert package.elev_th_path.read_text().splitlines() == ["0.000000 2", "3600.000000 2.1"]
    flags = pd.read_csv(package.flags_path)
    assert flags["flux_th_column"].dropna().tolist() == [1.0]
    assert flags["elev_th_column"].dropna().tolist() == [1.0]


def test_write_schism_type1_boundary_forcing_extends_terminal_time(tmp_path: Path) -> None:
    forcing = pd.DataFrame(
        [
            {
                "boundary_id": 1,
                "role": "upstream_inflow",
                "boundary_condition_hint": "flow",
                "time_seconds": 0.0,
                "stage_m": 10.0,
                "discharge_m3s": 5.0,
            },
            {
                "boundary_id": 1,
                "role": "upstream_inflow",
                "boundary_condition_hint": "flow",
                "time_seconds": 3600.0,
                "stage_m": 10.2,
                "discharge_m3s": 6.0,
            },
        ]
    )

    package = write_schism_type1_boundary_forcing(
        forcing,
        tmp_path,
        boundary_node_counts=[3],
        end_time_seconds=7200.0,
    )

    assert package.n_times == 3
    assert package.flux_th_path is not None
    assert package.flux_th_path.read_text().splitlines() == [
        "0.000000 -5",
        "3600.000000 -6",
        "7200.000000 -6",
    ]


def test_write_schism_type1_boundary_forcing_reads_hgrid_counts(tmp_path: Path) -> None:
    forcing = pd.DataFrame(
        [
            {
                "boundary_id": boundary_id,
                "role": "upstream_inflow" if boundary_id == 1 else "downstream_stage",
                "boundary_condition_hint": "flow" if boundary_id == 1 else "stage",
                "time_seconds": 0.0,
                "stage_m": 3.0 + boundary_id,
                "discharge_m3s": 2.0,
            }
            for boundary_id in (1, 2)
        ]
    )
    hgrid = tmp_path / "hgrid.gr3"
    hgrid.write_text(
        "test\n"
        "0 4\n"
        "1 0.0 0.0 0.0\n"
        "2 1.0 0.0 0.0\n"
        "3 1.0 1.0 0.0\n"
        "4 0.0 1.0 0.0\n"
        "2 = number of open boundary segments\n"
        "7 = total number of open boundary nodes\n"
        "3 = number of nodes for open boundary 1\n"
        "1\n"
        "2\n"
        "3\n"
        "4 = number of nodes for open boundary 2\n"
        "1\n"
        "2\n"
        "3\n"
        "4\n"
        "0 = number of land boundary segments\n"
        "0 = total number of land boundary nodes\n"
    )

    package = write_schism_type1_boundary_forcing(forcing, tmp_path, hgrid_path=hgrid)

    flags = pd.read_csv(package.flags_path)
    assert flags["n_nodes"].tolist() == [3, 4]
    assert "3 0 1 0 0" in package.bctides_path.read_text()
    assert "4 1 0 0 0" in package.bctides_path.read_text()


def test_hgrid_from_ugrid_round_trip(tmp_path: Path) -> None:
    ug = tmp_path / "mesh.nc"
    hg = tmp_path / "hgrid.gr3"
    make_synthetic_ugrid_2d(ug)
    summary = _write_hgrid_from_ugrid(ug, hg)

    assert summary["n_open_boundaries"] == 0
    assert summary["n_land_boundaries"] == 0

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
    assert "0 = number of open boundary segments" in lines
    assert "0 = total number of open boundary nodes" in lines
    assert "0 = number of land boundary segments" in lines
    assert "0 = total number of land boundary nodes" in lines


def test_hgrid_from_ugrid_writes_boundary_connectivity_with_fill_values(tmp_path: Path) -> None:
    ug = tmp_path / "mesh_boundary.nc"
    hg = tmp_path / "hgrid_boundary.gr3"
    make_synthetic_ugrid_2d(ug)
    with xr.open_dataset(ug) as base:
        ds = base.load()
    ds["open_boundary_node_connectivity"] = (
        ("open_boundary", "open_boundary_node"),
        np.array([[0, 1, -1], [2, 3, -1]], dtype=np.int32),
        {"_FillValue": -1, "start_index": 0},
    )
    ds["land_boundary_node_connectivity"] = (
        ("land_boundary", "land_boundary_node"),
        np.array([[0, 3, -1]], dtype=np.int32),
        {"_FillValue": -1, "start_index": 0},
    )
    ds.to_netcdf(ug)

    summary = _write_hgrid_from_ugrid(ug, hg)

    assert summary["n_open_boundaries"] == 2
    assert summary["n_open_boundary_nodes"] == 4
    assert summary["n_land_boundaries"] == 1

    lines = hg.read_text().splitlines()
    assert "2 = number of open boundary segments" in lines
    assert "4 = total number of open boundary nodes" in lines
    assert "1 = number of land boundary segments" in lines
    assert "2 = total number of land boundary nodes" in lines


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
    bctides = (work / "bctides.in").read_text()
    assert "0   ! nope" in bctides

    import json

    marker = json.loads((work / ".openlimno_prepared").read_text())
    assert marker["real_mesh"] is True
    assert marker["hgrid"]["n_open_boundaries"] == 0


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
