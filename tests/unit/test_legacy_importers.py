"""HEC-RAS .g0X + River2D .cdg legacy importer tests."""

from __future__ import annotations

import struct
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from openlimno.preprocess import (
    diagnose_mike_environment,
    infer_external_model,
    inspect_habitat_exchange,
    inspect_hecras_hdf,
    inspect_instream_exchange,
    inspect_telemac_selafin,
    list_external_model_support,
    read_external_model,
    read_hecras_geometry,
    read_river2d_cdg,
    read_river2d_elements,
    validate_ugrid_mesh,
    write_river2d_ugrid,
)

# Small synthetic .g03 fragment with two cross-sections on one reach.
_HECRAS_G03 = """\
Geom Title=Synthetic Test Geometry
Program Version=6.10
River Reach=Lemhi      ,Main
Type RM Length L Ch R= 1 ,    100.0,    50.0
X1=  100.0,      4,      0.,     20.,      0.,      0.
GR=     1.5,      0.,     1.0,      5.,     0.5,    10.0,     1.0,    20.0
Type RM Length L Ch R= 1 ,    200.0,    60.0
X1=  200.0,      3,      0.,     18.,      0.,      0.
GR=     1.6,      0.,     1.1,      9.,     1.6,    18.0
"""

_HECRAS_STA_ELEV_G01 = """\
Geom Title=Modern HEC-RAS Test Geometry
Program Version=5.07
River Reach=Clinch River    ,Upper Reach
Type RM Length L Ch R = 1 ,4893.771,44.6,45.31,43.51
XS GIS Cut Line=2
     320729.9764    4049882.4458     320876.6807    4049955.5874
#Sta/Elev= 4
       0  357.05    3.56  355.87    5.34  355.44    7.12  354.92
#Mann= 1 ,-1 , 0
       0     .03       0
Bank Sta=0,7.12
Type RM Length L Ch R = 1 ,4848.462,47.67,49.13,49.02
#Sta/Elev= 3
       0  358.65    1.82  357.54    3.63  355.78
"""


_CDG_BED = """\
HEADER River2D Bed File v1.0
NODES 4
1   0.0   0.0   1.5  0.5
2   1.0   0.0   1.0  0.6
3   1.0   1.0   1.1  0.55
4   0.0   1.0   1.2  0.5
ELEMENTS 2
1 1 2 3
2 1 3 4
"""

_RIVER2D_OFFICIAL_CDG = """\
Number of Variables = 3
Number of Parameters = 3
Number of Nodes = 3
Number of Elements = 1

Node Information

Node #, Coordinates, Parameters, Variables

1 s 0.0 0.0 100.0 0.03 10 1.0 0.3 0.4
2 x 1.0 0.0 100.1 0.03 10 0.5 0.1 0.2
3   0.0 1.0 100.2 0.03 10 -0.1 0.0 0.0

Element Information

Element #, vtype, gtype, nodes

1 210 210 1 2 3 0.0 0.0 0.0
"""


def test_read_hecras_geometry_finds_two_xs(tmp_path: Path) -> None:
    p = tmp_path / "synthetic.g03"
    p.write_text(_HECRAS_G03)
    df = read_hecras_geometry(p)
    assert {"river", "reach", "station_m", "distance_m", "elevation_m"}.issubset(df.columns)
    stations = sorted(set(df["station_m"]))
    assert stations == [100.0, 200.0]
    # First XS has 4 points, second has 3
    n_at_100 = (df["station_m"] == 100.0).sum()
    n_at_200 = (df["station_m"] == 200.0).sum()
    assert n_at_100 == 4
    assert n_at_200 == 3
    assert (df["river"] == "Lemhi").all()


def test_read_hecras_geometry_finds_sta_elev_blocks(tmp_path: Path) -> None:
    p = tmp_path / "modern.g01"
    p.write_text(_HECRAS_STA_ELEV_G01)
    df = read_hecras_geometry(p)

    assert sorted(set(df["station_m"])) == [4848.462, 4893.771]
    assert len(df) == 7
    first = df[df["station_m"] == 4893.771].sort_values("point_index").iloc[0]
    assert first["distance_m"] == pytest.approx(0.0)
    assert first["elevation_m"] == pytest.approx(357.05)
    assert first["x_m"] == pytest.approx(320729.9764)
    assert first["y_m"] == pytest.approx(4049882.4458)
    georef = df[df["station_m"] == 4893.771].sort_values("point_index")
    assert georef["x_m"].notna().all()
    assert georef.iloc[-1]["x_m"] == pytest.approx(320876.6807)
    assert georef.iloc[-1]["y_m"] == pytest.approx(4049955.5874)
    assert (df["river"] == "Clinch River").all()
    assert (df["reach"] == "Upper Reach").all()


def test_read_hecras_geometry_empty_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.g03"
    p.write_text("Geom Title=Empty\n")
    with pytest.raises(ValueError, match="No cross-sections found"):
        read_hecras_geometry(p)


def test_read_river2d_cdg(tmp_path: Path) -> None:
    p = tmp_path / "bed.cdg"
    p.write_text(_CDG_BED)
    df = read_river2d_cdg(p)
    assert len(df) == 4
    assert set(df.columns) >= {"node_id", "x", "y", "z"}
    assert "depth" in df.columns
    assert df.loc[df["node_id"] == 1, "z"].iloc[0] == 1.5


def test_read_river2d_cdg_official_2002_format(tmp_path: Path) -> None:
    p = tmp_path / "official.CDG"
    p.write_text(_RIVER2D_OFFICIAL_CDG)

    nodes = read_river2d_cdg(p)
    elements = read_river2d_elements(p)

    assert len(nodes) == 3
    assert nodes.attrs["river2d_n_elements"] == 1
    assert {"bed_elevation_m", "roughness_m", "depth_m", "velocity_ms"}.issubset(nodes.columns)
    assert nodes.loc[nodes["node_id"] == 1, "velocity_ms"].iloc[0] == pytest.approx(0.5)
    assert nodes.loc[nodes["node_id"] == 3, "velocity_ms"].iloc[0] == 0.0
    assert list(elements[["node_1", "node_2", "node_3"]].iloc[0]) == [1, 2, 3]


def test_write_river2d_ugrid_from_official_cdg(tmp_path: Path) -> None:
    p = tmp_path / "official.CDG"
    p.write_text(_RIVER2D_OFFICIAL_CDG)
    out = tmp_path / "river2d_mesh.nc"

    written = write_river2d_ugrid(p, out)
    report = validate_ugrid_mesh(written)

    assert written == out
    assert report.is_valid
    assert report.topology_dim == 2
    assert report.n_nodes == 3
    assert report.n_faces == 1
    assert report.has_bottom_elevation


def test_read_river2d_cdg_no_nodes_raises(tmp_path: Path) -> None:
    p = tmp_path / "broken.cdg"
    p.write_text("HEADER junk\nELEMENTS 0\n")
    with pytest.raises(ValueError, match="No NODES"):
        read_river2d_cdg(p)


def test_external_model_registry_marks_core_and_plugin_paths() -> None:
    support = {entry.key: entry for entry in list_external_model_support()}
    assert support["hecras-geometry"].status == "implemented"
    assert support["river2d-cdg"].status == "implemented"
    assert support["hecras-hdf"].status == "implemented"
    assert support["telemac-slf"].status == "implemented"
    assert support["delft3d-netcdf"].status == "implemented"
    assert support["mike-dfs"].status == "implemented"
    assert support["mike-1d"].status == "implemented"
    assert support["habby-csv"].status == "implemented"
    assert support["instream-netlogo"].status == "implemented"


def test_external_model_auto_import_hecras_geometry(tmp_path: Path) -> None:
    p = tmp_path / "synthetic.g03"
    p.write_text(_HECRAS_G03)
    assert infer_external_model(p) == "hecras-geometry"
    result = read_external_model(p)
    assert result.source_key == "hecras-geometry"
    assert result.model == "HEC-RAS"
    assert len(result.table) == 7
    assert result.table.attrs["openlimno_output_table"] == "cross_section_points"
    assert result.warnings


def _slf_record(payload: bytes) -> bytes:
    return struct.pack(">i", len(payload)) + payload + struct.pack(">i", len(payload))


def _slf_int_record(values: list[int]) -> bytes:
    return _slf_record(struct.pack(f">{len(values)}i", *values))


def _slf_float_record(values: list[float]) -> bytes:
    return _slf_record(struct.pack(f">{len(values)}f", *values))


def _slf_var(name: str, unit: str) -> bytes:
    return _slf_record(name.encode("ascii").ljust(16)[:16] + unit.encode("ascii").ljust(16)[:16])


def _write_synthetic_selafin(path: Path) -> None:
    title = "Synthetic TELEMAC".encode("ascii").ljust(72) + b"SERAFIN "
    payload = bytearray()
    payload += _slf_record(title)
    payload += _slf_int_record([4, 0])
    payload += _slf_var("WATER DEPTH", "M")
    payload += _slf_var("FREE SURFACE", "M")
    payload += _slf_var("VELOCITY U", "M/S")
    payload += _slf_var("VELOCITY V", "M/S")
    payload += _slf_int_record([0] * 10)
    payload += _slf_int_record([2, 4, 3, 1])
    payload += _slf_int_record([1, 2, 3, 1, 3, 4])
    payload += _slf_int_record([0, 0, 0, 0])
    payload += _slf_float_record([0.0, 1.0, 1.0, 0.0])
    payload += _slf_float_record([0.0, 0.0, 1.0, 1.0])
    for t, depth, wse, u, v in (
        (
            0.0,
            [0.1, 0.2, 0.3, 0.4],
            [10.1, 10.2, 10.3, 10.4],
            [0.3, 0.4, 0.0, 0.0],
            [0.4, 0.3, 0.0, 0.0],
        ),
        (
            3600.0,
            [1.1, 1.2, 1.3, 1.4],
            [11.1, 11.2, 11.3, 11.4],
            [0.6, 0.8, 0.0, 0.0],
            [0.8, 0.6, 0.0, 0.0],
        ),
    ):
        payload += _slf_float_record([t])
        payload += _slf_float_record(depth)
        payload += _slf_float_record(wse)
        payload += _slf_float_record(u)
        payload += _slf_float_record(v)
    path.write_bytes(payload)


def test_external_model_imports_telemac_selafin_cells(tmp_path: Path) -> None:
    p = tmp_path / "telemac_results.slf"
    _write_synthetic_selafin(p)

    assert infer_external_model(p) == "telemac-slf"
    inspection = inspect_telemac_selafin(p)
    assert inspection.n_points == 4
    assert inspection.n_elements == 2
    assert inspection.n_timesteps == 2
    assert [var.role for var in inspection.variables] == [
        "depth_m",
        "water_surface_m",
        "u_ms",
        "v_ms",
    ]

    result = read_external_model(p, source="telemac-slf", time_index=1)

    assert result.source_key == "telemac-slf"
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert list(result.table["cell_id"]) == [0, 1]
    assert list(result.table["area_m2"]) == pytest.approx([0.5, 0.5])
    assert list(result.table["depth_m"]) == pytest.approx([1.2, 1.2666666667])
    assert list(result.table["water_surface_m"]) == pytest.approx([11.2, 11.2666666667])
    assert list(result.table["velocity_ms"]) == pytest.approx([0.659966, 0.333333], rel=1e-5)
    assert result.table["time_s"].iloc[0] == 3600.0


def test_external_model_imports_hecras_hdf_cells(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    p = tmp_path / "ras_results.hdf"
    with h5py.File(p, "w") as h5:
        geom = h5.create_group("/Geometry/2D Flow Areas/Area 1")
        geom.create_dataset(
            "Cells Center Coordinate",
            data=[[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        )
        geom.create_dataset("Cells Surface Area", data=[10.0, 11.0, 12.0])
        geom.create_dataset("Cells Minimum Elevation", data=[100.0, 99.5, 99.8])
        ts = h5.create_group(
            "/Results/Unsteady/Output/Output Blocks/Base Output/"
            "Unsteady Time Series/2D Flow Areas/Area 1"
        )
        ts.create_dataset("Depth", data=[[0.1, 0.2, 0.3], [1.1, 1.2, 1.3]])
        ts.create_dataset("Water Surface", data=[[100.1, 99.7, 100.1], [101.1, 100.7, 101.1]])
        ts.create_dataset("Velocity", data=[[0.4, 0.5, 0.6], [1.4, 1.5, 1.6]])
        h5.create_dataset(
            "/Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/"
            "Time Date Stamp",
            data=[b"01JAN2026 00:00:00", b"01JAN2026 01:00:00"],
        )

    result = read_external_model(p, time_index=0)
    assert result.source_key == "hecras-hdf"
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert list(result.table["cell_id"]) == [0, 1, 2]
    assert list(result.table["depth_m"]) == [0.1, 0.2, 0.3]
    assert list(result.table["velocity_ms"]) == [0.4, 0.5, 0.6]
    assert result.table["time"].iloc[0] == "01JAN2026 00:00:00"


def test_external_model_derives_hecras_depth_from_wse_and_bed(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    p = tmp_path / "ras_results.hdf"
    with h5py.File(p, "w") as h5:
        geom = h5.create_group("/Geometry/2D Flow Areas/Area 1")
        geom.create_dataset("Cells Center Coordinate", data=[[0.0, 0.0], [1.0, 0.0]])
        geom.create_dataset("Cells Surface Area", data=[10.0, 11.0])
        geom.create_dataset("Cells Minimum Elevation", data=[100.0, 99.5])
        ts = h5.create_group(
            "/Results/Unsteady/Output/Output Blocks/Base Output/"
            "Unsteady Time Series/2D Flow Areas/Area 1"
        )
        ts.create_dataset("Water Surface", data=[[101.0, 99.0], [102.0, 101.5]])

    result = read_external_model(p, source="hecras-hdf", time_index=1)

    assert result.source_key == "hecras-hdf"
    assert list(result.table["depth_m"]) == [2.0, 2.0]
    assert result.table["depth_m"].min() >= 0.0
    assert any("derived depth_m" in warning for warning in result.warnings)


def test_external_model_aggregates_hecras_face_velocity(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    p = tmp_path / "ras_results.hdf"
    with h5py.File(p, "w") as h5:
        geom = h5.create_group("/Geometry/2D Flow Areas/Area 1")
        geom.create_dataset("Cells Center Coordinate", data=[[0.0, 0.0], [1.0, 0.0]])
        geom.create_dataset("Cells Surface Area", data=[10.0, 11.0])
        geom.create_dataset("Cells Face and Orientation Info", data=[[0, 2], [2, 2]])
        geom.create_dataset(
            "Cells Face and Orientation Values", data=[[0, 0], [1, 0], [1, 0], [2, 0]]
        )
        geom.create_dataset("Faces FacePoint Indexes", data=[[0, 1], [1, 2], [2, 3]])
        geom.create_dataset(
            "FacePoints Coordinate", data=[[0.0, 0.0], [0.5, 0.0], [1.0, 0.0], [1.5, 0.0]]
        )
        ts = h5.create_group(
            "/Results/Unsteady/Output/Output Blocks/Base Output/"
            "Unsteady Time Series/2D Flow Areas/Area 1"
        )
        ts.create_dataset("Depth", data=[[1.0, 1.0], [1.0, 1.0]])
        ts.create_dataset("Water Surface", data=[[101.0, 101.0], [102.0, 102.0]])
        ts.create_dataset("Face Velocity", data=[[0.5, -1.5, 2.5], [1.0, -3.0, 5.0]])

    result = read_external_model(p, source="hecras-hdf", time_index=1)

    assert list(result.table["velocity_ms"]) == [2.0, 4.0]
    assert any("face velocity" in warning.lower() for warning in result.warnings)


def test_inspect_hecras_hdf_reports_cell_aligned_candidates(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    p = tmp_path / "ras_results.hdf"
    with h5py.File(p, "w") as h5:
        geom = h5.create_group("/Geometry/2D Flow Areas/Area 1")
        geom.create_dataset("Cells Center Coordinate", data=[[0.0, 0.0], [1.0, 0.0]])
        geom.create_dataset("Cells Surface Area", data=[10.0, 11.0])
        ts = h5.create_group(
            "/Results/Unsteady/Output/Output Blocks/Base Output/"
            "Unsteady Time Series/2D Flow Areas/Area 1"
        )
        ts.create_dataset("Depth", data=[[0.1, 0.2], [1.1, 1.2]])
        ts.create_dataset("Face Velocity", data=[[0.4, 0.5, 0.6]])

    inspection = inspect_hecras_hdf(p)

    assert inspection.selected_flow_area == "Area 1"
    assert inspection.n_cells == 2
    assert inspection.cell_center_path is not None
    assert any(
        info.path.endswith("/Depth") and info.cell_aligned for info in inspection.depth_candidates
    )
    assert not inspection.velocity_candidates
    assert any(
        info.path.endswith("/Cells Surface Area") and info.cell_aligned
        for info in inspection.geometry_candidates
    )


def _install_fake_mikeio(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeItem:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeArray:
        def __init__(self, values: list[list[float]]) -> None:
            self.values = np.asarray(values, dtype=float)

    class FakeGeometry:
        n_elements = 3
        n_nodes = 4
        element_coordinates = np.asarray(
            [[0.0, 0.0, -1.0], [1.0, 0.0, -1.2], [0.0, 1.0, -0.9]],
            dtype=float,
        )

        def get_element_area(self) -> np.ndarray:
            return np.asarray([10.0, 11.0, 12.0], dtype=float)

    class FakeDataset:
        items = (
            FakeItem("Water Depth"),
            FakeItem("Water Level"),
            FakeItem("U velocity"),
            FakeItem("V velocity"),
        )
        geometry = FakeGeometry()
        time = ("2026-01-01 00:00", "2026-01-01 01:00")

        def __getitem__(self, idx: int) -> FakeArray:
            values = [
                [[0.1, 0.2, 0.3], [1.1, 1.2, 1.3]],
                [[10.1, 10.2, 10.3], [11.1, 11.2, 11.3]],
                [[0.3, 0.4, 0.0], [0.6, 0.8, 0.0]],
                [[0.4, 0.3, 0.0], [0.8, 0.6, 0.0]],
            ]
            return FakeArray(values[idx])

    class FakeReader:
        items = FakeDataset.items
        geometry = FakeDataset.geometry
        n_timesteps = 2
        start_time = "2026-01-01 00:00"
        end_time = "2026-01-01 01:00"

        def read(self, **_: object) -> FakeDataset:
            return FakeDataset()

    fake_mikeio = types.SimpleNamespace(open=lambda _: FakeReader())
    monkeypatch.setitem(sys.modules, "mikeio", fake_mikeio)


def test_external_model_imports_mike_dfsu_with_optional_mikeio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_mikeio(monkeypatch)
    p = tmp_path / "mike21_results.dfsu"
    p.write_text("fake")

    assert infer_external_model(p) == "mike-dfs"
    result = read_external_model(p, source="mike-dfs", time_index=1)

    assert result.source_key == "mike-dfs"
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert list(result.table["depth_m"]) == [1.1, 1.2, 1.3]
    assert list(result.table["area_m2"]) == [10.0, 11.0, 12.0]
    assert list(result.table["velocity_ms"]) == pytest.approx([1.0, 1.0, 0.0])
    assert result.table["time"].iloc[0] == "2026-01-01 01:00"


def test_external_model_imports_mike_xns11_with_optional_mikeio1d(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCrossSection:
        raw = pd.DataFrame({"x": [0.0, 5.0], "z": [101.0, 100.5], "resistance": [30, 30]})

    class FakeXns11:
        def to_dataframe(self) -> pd.DataFrame:
            index = pd.MultiIndex.from_tuples(
                [("River A", 100.0, "Topo 1")],
                names=["reach", "chainage", "topo_id"],
            )
            return pd.DataFrame({"cross_section": [FakeCrossSection()]}, index=index)

    fake_mikeio1d = types.SimpleNamespace(open=lambda _: FakeXns11())
    monkeypatch.setitem(sys.modules, "mikeio1d", fake_mikeio1d)
    p = tmp_path / "river_network.xns11"
    p.write_text("fake")

    assert infer_external_model(p) == "mike-1d"
    result = read_external_model(p, source="mike-1d")

    assert result.source_key == "mike-1d"
    assert result.table.attrs["openlimno_output_table"] == "cross_section_points"
    assert list(result.table["station_m"]) == [0.0, 5.0]
    assert list(result.table["elevation_m"]) == [101.0, 100.5]


def test_external_model_imports_mike_res1d_deduplicates_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRes1D:
        quantities = ("WaterLevel", "Discharge")
        n_timesteps = 1

        def read(self) -> pd.DataFrame:
            table = pd.DataFrame(
                [[101.2, 101.3, 2.5]],
                columns=[
                    "WaterLevel:river_a:10.0",
                    "WaterLevel:river_a:10.0",
                    "Discharge:river_a:10.0",
                ],
            )
            table.index.name = "time"
            return table

    fake_mikeio1d = types.SimpleNamespace(open=lambda _: FakeRes1D())
    monkeypatch.setitem(sys.modules, "mikeio1d", fake_mikeio1d)
    p = tmp_path / "river_network.res1d"
    p.write_text("fake")

    assert infer_external_model(p) == "mike-1d"
    result = read_external_model(p, source="mike-1d")

    assert result.source_key == "mike-1d"
    assert result.table.attrs["openlimno_output_table"] == "mike_timeseries"
    assert len(set(result.table.columns)) == len(result.table.columns)
    assert "WaterLevel:river_a:10.0__2" in result.table.columns
    assert result.warnings == (
        "Duplicate MIKE 1D result column names were suffixed for tabular export.",
    )


def test_external_model_imports_cf_ugrid_netcdf_cells(tmp_path: Path) -> None:
    p = tmp_path / "dflowfm_map.nc"
    ds = xr.Dataset(
        data_vars={
            "mesh2d_face_x": ("mesh2d_nFaces", [0.0, 1.0, 0.0]),
            "mesh2d_face_y": ("mesh2d_nFaces", [0.0, 0.0, 1.0]),
            "mesh2d_flowelem_ba": ("mesh2d_nFaces", [10.0, 11.0, 12.0]),
            "mesh2d_waterdepth": (
                ("time", "mesh2d_nFaces"),
                [[0.1, 0.2, 0.3], [1.1, 1.2, 1.3]],
                {"standard_name": "sea_floor_depth_below_sea_surface"},
            ),
            "mesh2d_s1": (
                ("time", "mesh2d_nFaces"),
                [[100.1, 100.2, 100.3], [101.1, 101.2, 101.3]],
                {"standard_name": "water_surface_height_above_reference_datum"},
            ),
            "mesh2d_ucx": (("time", "mesh2d_nFaces"), [[0.3, 0.4, 0.0], [0.6, 0.8, 0.0]]),
            "mesh2d_ucy": (("time", "mesh2d_nFaces"), [[0.4, 0.3, 0.0], [0.8, 0.6, 0.0]]),
        },
        coords={"time": pd.date_range("2026-01-01", periods=2, freq="h")},
    )
    ds.to_netcdf(p)

    assert infer_external_model(p) == "delft3d-netcdf"
    result = read_external_model(p, source="delft3d-netcdf", time_index=1)

    assert result.source_key == "delft3d-netcdf"
    assert result.table.attrs["openlimno_output_table"] == "hydraulic_cells"
    assert list(result.table["depth_m"]) == [1.1, 1.2, 1.3]
    assert list(result.table["area_m2"]) == [10.0, 11.0, 12.0]
    assert list(result.table["velocity_ms"]) == pytest.approx([1.0, 1.0, 0.0])
    assert result.table["time_index"].iloc[0] == 1


def test_external_model_imports_cf_ugrid_velocity_magnitude_without_false_warning(
    tmp_path: Path,
) -> None:
    p = tmp_path / "dflowfm_map.nc"
    ds = xr.Dataset(
        data_vars={
            "mesh2d_face_x": ("mesh2d_nFaces", [0.0, 1.0, 0.0]),
            "mesh2d_face_y": ("mesh2d_nFaces", [0.0, 0.0, 1.0]),
            "mesh2d_flowelem_ba": ("mesh2d_nFaces", [10.0, 11.0, 12.0]),
            "mesh2d_waterdepth": (
                ("time", "mesh2d_nFaces"),
                [[0.1, 0.2, 0.3], [1.1, 1.2, 1.3]],
                {"standard_name": "sea_floor_depth_below_sea_surface"},
            ),
            "mesh2d_s1": (
                ("time", "mesh2d_nFaces"),
                [[100.1, 100.2, 100.3], [101.1, 101.2, 101.3]],
                {"standard_name": "water_surface_height_above_reference_datum"},
            ),
            "mesh2d_ucmaga": (
                ("time", "mesh2d_nFaces"),
                [[0.3, 0.4, 0.5], [0.6, 0.8, 1.0]],
                {"standard_name": "sea_water_speed"},
            ),
        },
        coords={"time": pd.date_range("2026-01-01", periods=2, freq="h")},
    )
    ds.to_netcdf(p)

    result = read_external_model(p, source="delft3d-netcdf", time_index=1)

    assert list(result.table["velocity_ms"]) == [0.6, 0.8, 1.0]
    assert result.warnings == ()


def test_external_model_imports_habitat_exchange_cells(tmp_path: Path) -> None:
    p = tmp_path / "habby_wua_cells.csv"
    pd.DataFrame(
        {
            "unit_id": [101, 102],
            "x": [10.0, 11.0],
            "y": [20.0, 21.0],
            "area": [10.0, 20.0],
            "HSI": [0.5, 0.2],
            "depth": [0.4, 0.8],
            "velocity": [0.3, 0.6],
            "Q": [1.5, 1.5],
            "species": ["trout", "trout"],
            "stage": ["adult", "adult"],
        }
    ).to_csv(p, index=False)

    assert infer_external_model(p) == "habby-csv"
    inspection = inspect_habitat_exchange(p)
    assert inspection.table_type == "habitat_cells"
    assert inspection.detected_roles["csi"] == "HSI"

    result = read_external_model(p, source="habby-csv")

    assert result.source_key == "habby-csv"
    assert result.table.attrs["openlimno_output_table"] == "habitat_cells"
    assert list(result.table["cell_id"]) == [101, 102]
    assert list(result.table["area_m2"]) == [10.0, 20.0]
    assert list(result.table["csi"]) == [0.5, 0.2]
    assert list(result.table["wua_m2"]) == [5.0, 4.0]
    assert list(result.table["discharge_m3s"]) == [1.5, 1.5]


def test_external_model_imports_habitat_exchange_wua_summary(tmp_path: Path) -> None:
    p = tmp_path / "casimir_wua_summary.csv"
    pd.DataFrame(
        {
            "discharge": [1.0, 2.0],
            "WUA": [12.0, 15.0],
            "wetted_area": [30.0, 50.0],
            "species": ["barbel", "barbel"],
            "life_stage": ["adult", "adult"],
        }
    ).to_csv(p, index=False)

    assert infer_external_model(p) == "habby-csv"
    result = read_external_model(p, source="habby-csv")

    assert result.table.attrs["openlimno_output_table"] == "wua_summary"
    assert list(result.table["wua_m2"]) == [12.0, 15.0]
    assert list(result.table["area_m2"]) == [30.0, 50.0]
    assert list(result.table["mean_csi"]) == pytest.approx([0.4, 0.3])


def test_external_model_imports_habby_txt_spu_summary(tmp_path: Path) -> None:
    p = tmp_path / "d1_to_d9_sub_PolygonSandreCoarser-dom_spu.txt"
    p.write_text(
        "discharge\tSPU\twetted_area\tspecies\tstage\n74.7\t31.5\t90.0\tbarbel\tadult\n",
        encoding="utf-8",
    )

    assert infer_external_model(p) == "habby-csv"
    inspection = inspect_habitat_exchange(p)
    assert inspection.table_type == "wua_summary"
    assert inspection.detected_roles["wua_m2"] == "SPU"

    result = read_external_model(p, source="habby-csv")

    assert result.table.attrs["openlimno_output_table"] == "wua_summary"
    assert list(result.table["wua_m2"]) == [31.5]
    assert list(result.table["area_m2"]) == [90.0]
    assert list(result.table["mean_csi"]) == pytest.approx([0.35])


def test_diagnose_mike_1d_reports_missing_linux_dotnet(monkeypatch: pytest.MonkeyPatch) -> None:
    import openlimno.preprocess.mike as mike_module

    monkeypatch.setattr(mike_module.sys, "platform", "linux")
    monkeypatch.setattr(mike_module.shutil, "which", lambda _: None)
    monkeypatch.setitem(sys.modules, "mikeio1d", types.SimpleNamespace(__version__="1.1.1"))

    diagnostic = diagnose_mike_environment("mike-1d")

    assert diagnostic.module_installed
    assert diagnostic.module_version == "1.1.1"
    assert diagnostic.dotnet_required
    assert diagnostic.dotnet_ok is False
    assert diagnostic.ready is False
    assert "dotnet-runtime-8.0" in diagnostic.install_hint


def test_external_model_imports_instream_population_summary(tmp_path: Path) -> None:
    p = tmp_path / "instream_population_summary.csv"
    pd.DataFrame(
        {
            "scenario": ["baseline", "baseline"],
            "reach": ["A", "A"],
            "year": [2026, 2026],
            "day": [1, 2],
            "species": ["rainbow_trout", "rainbow_trout"],
            "age_class": ["adult", "adult"],
            "abundance": [120, 118],
            "biomass_g": [24000.0, 23850.0],
            "survival": [1.0, 0.98],
        }
    ).to_csv(p, index=False)

    assert infer_external_model(p) == "instream-netlogo"
    inspection = inspect_instream_exchange(p)
    assert inspection.table_type == "population_summary"
    assert inspection.detected_roles["abundance"] == "abundance"

    result = read_external_model(p, source="instream-netlogo")

    assert result.source_key == "instream-netlogo"
    assert result.table.attrs["openlimno_output_table"] == "population_summary"
    assert list(result.table["scenario_id"]) == ["baseline", "baseline"]
    assert list(result.table["reach_id"]) == ["A", "A"]
    assert list(result.table["abundance"]) == [120, 118]
    assert list(result.table["survival_rate"]) == [1.0, 0.98]


def test_external_model_imports_instream_depth_matrix(tmp_path: Path) -> None:
    p = tmp_path / "instream_depths.csv"
    p.write_text(
        "; Depth input file for inSTREAM 7\n"
        "; Example\n"
        ",CELL DEPTHS IN METERS\n"
        "2,Number of flows in table\n"
        ",1.0,2.0\n"
        "1,0.1,0.2\n"
        "2,0.3,0.4\n"
    )

    assert infer_external_model(p) == "instream-netlogo"
    inspection = inspect_instream_exchange(p)
    assert inspection.table_type == "ibm_hydraulic_lookup"
    assert inspection.detected_roles["depth_m"] == "depth_m"

    result = read_external_model(p, source="instream-netlogo")

    assert result.table.attrs["openlimno_output_table"] == "ibm_hydraulic_lookup"
    assert list(result.table["cell_id"]) == ["1", "1", "2", "2"]
    assert list(result.table["discharge_m3s"]) == [1.0, 2.0, 1.0, 2.0]
    assert list(result.table["depth_m"]) == [0.1, 0.2, 0.3, 0.4]
