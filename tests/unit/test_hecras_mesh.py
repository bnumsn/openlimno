from __future__ import annotations

from pathlib import Path

import pandas as pd
import xarray as xr

from openlimno.hydro.schism import SCHISMAdapter, _write_hgrid_from_ugrid
from openlimno.preprocess import read_hecras_geometry, write_hecras_gis_ugrid

_HECRAS_GIS_G01 = """\
Geom Title=Mesh Test Geometry
Program Version=5.07
River Reach=Clinch River    ,Upper Reach
Type RM Length L Ch R = 1 ,200,10,10,10
XS GIS Cut Line=2
       0       0      10       0
#Sta/Elev= 3
       0   3.0       5   1.0      10   3.0
Type RM Length L Ch R = 1 ,100,10,10,10
XS GIS Cut Line=2
       0      20      10      20
#Sta/Elev= 3
       0   2.5       5   0.5      10   2.5
"""


def test_write_hecras_gis_ugrid_from_cutlines(tmp_path: Path) -> None:
    g01 = tmp_path / "test.g01"
    g01.write_text(_HECRAS_GIS_G01)
    cross_sections = read_hecras_geometry(g01)

    mesh_path = tmp_path / "mesh.nc"
    result = write_hecras_gis_ugrid(cross_sections, mesh_path, transverse_nodes=3)

    assert result.n_sections == 2
    assert result.n_nodes == 6
    assert result.n_faces == 2
    assert result.n_open_boundaries == 2
    assert result.n_land_boundaries == 2
    assert result.n_open_boundary_nodes == 6
    assert result.n_land_boundary_nodes == 4
    with xr.open_dataset(mesh_path) as ds:
        assert ds.attrs["Conventions"] == "UGRID-1.0"
        assert ds["mesh2d_face_nodes"].shape == (2, 4)
        assert ds["bottom_elevation"].shape == (6,)
        assert ds["open_boundary_node_connectivity"].shape == (2, 3)
        assert ds["land_boundary_node_connectivity"].shape == (2, 2)


def test_write_hecras_gis_ugrid_respects_requested_reach_order(tmp_path: Path) -> None:
    cross_sections = pd.DataFrame(
        [
            {
                "river": "Clinch River",
                "reach": reach,
                "station_m": station,
                "distance_m": distance,
                "elevation_m": elevation,
                "x_m": x,
                "y_m": y,
            }
            for reach, station, y in (
                ("A", 100.0, 0.0),
                ("A", 90.0, 10.0),
                ("B", 20.0, 100.0),
                ("B", 10.0, 110.0),
            )
            for distance, elevation, x in ((0.0, 3.0, 0.0), (10.0, 2.0, 10.0))
        ]
    )

    mesh_path = tmp_path / "mesh.nc"
    write_hecras_gis_ugrid(
        cross_sections,
        mesh_path,
        reaches=("B", "A"),
        transverse_nodes=2,
    )

    with xr.open_dataset(mesh_path) as ds:
        assert ds["hecras_station_m"].values[:4].tolist() == [20.0, 20.0, 10.0, 10.0]


def test_hecras_gis_ugrid_can_feed_schism_hgrid(tmp_path: Path) -> None:
    g01 = tmp_path / "test.g01"
    g01.write_text(_HECRAS_GIS_G01)
    cross_sections = read_hecras_geometry(g01)
    mesh_path = tmp_path / "mesh.nc"
    hgrid_path = tmp_path / "hgrid.gr3"

    write_hecras_gis_ugrid(cross_sections, mesh_path, transverse_nodes=3)
    _write_hgrid_from_ugrid(mesh_path, hgrid_path)

    lines = hgrid_path.read_text().splitlines()
    assert lines[1] == "4 6"
    assert lines[8].split()[1] == "3"
    assert "2 = number of open boundary segments" in lines
    assert "6 = total number of open boundary nodes" in lines
    assert "2 = number of land boundary segments" in lines
    assert "4 = total number of land boundary nodes" in lines


def test_hecras_gis_ugrid_can_write_schism_bathymetric_depth(tmp_path: Path) -> None:
    g01 = tmp_path / "test.g01"
    g01.write_text(_HECRAS_GIS_G01)
    cross_sections = read_hecras_geometry(g01)
    mesh_path = tmp_path / "mesh_depth.nc"
    hgrid_path = tmp_path / "hgrid_depth.gr3"

    write_hecras_gis_ugrid(
        cross_sections,
        mesh_path,
        transverse_nodes=3,
        depth_reference_m=5.0,
    )
    summary = _write_hgrid_from_ugrid(mesh_path, hgrid_path)

    assert summary["depth_source"] == "schism_bathymetric_depth"
    assert summary["depth_reference_m"] == 5.0
    with xr.open_dataset(mesh_path) as ds:
        assert ds.attrs["schism_depth_reference_m"] == 5.0
        assert ds["schism_bathymetric_depth"].values.max() == 4.5
    first_node = hgrid_path.read_text().splitlines()[2].split()
    assert first_node[3] == "2.000000"


def test_hecras_gis_ugrid_schism_prepare_matches_boundary_count(tmp_path: Path) -> None:
    g01 = tmp_path / "test.g01"
    g01.write_text(_HECRAS_GIS_G01)
    cross_sections = read_hecras_geometry(g01)
    mesh_path = tmp_path / "mesh.nc"
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("# case\n")

    write_hecras_gis_ugrid(cross_sections, mesh_path, transverse_nodes=3)
    SCHISMAdapter().prepare(case_yaml, tmp_path / "schism", wedm_mesh_path=mesh_path)

    bctides = (tmp_path / "schism" / "bctides.in").read_text()
    assert "2   ! nope" in bctides
