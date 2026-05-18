"""CLI tests via Click's CliRunner. Covers the previously-stubbed commands."""

from __future__ import annotations

import struct
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from click.testing import CliRunner

from openlimno.cli import main

HERE = Path(__file__).resolve().parents[2]
LEMHI_CASE = HERE / "examples" / "lemhi" / "case.yaml"
LEMHI_DATA = HERE / "data" / "lemhi"


def test_init_creates_skeleton(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(tmp_path / "myproj"), "--basin", "test"])
    assert result.exit_code == 0
    assert (tmp_path / "myproj" / "case.yaml").exists()
    assert (tmp_path / "myproj" / "studyplan.yaml").exists()
    assert (tmp_path / "myproj" / "data").is_dir()
    assert (tmp_path / "myproj" / "README.md").exists()


def test_init_refuses_existing_dir(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "exists"
    target.mkdir()
    result = runner.invoke(main, ["init", str(target)])
    assert result.exit_code == 1


def test_validate_lemhi_case() -> None:
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi case missing")
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(LEMHI_CASE)])
    assert result.exit_code == 0


def test_studyplan_init_non_interactive(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "study.yaml"
    result = runner.invoke(
        main,
        [
            "studyplan",
            "init",
            str(out),
            "--problem",
            "Establish ecological flow recommendations for the Lemhi River for steelhead spawning.",
            "--species",
            "oncorhynchus_mykiss",
        ],
    )
    assert result.exit_code == 0
    assert out.exists()
    # The generated plan must validate
    result2 = runner.invoke(main, ["studyplan", "validate", str(out)])
    assert result2.exit_code == 0


def test_hsi_upgrade_bulk_grade(tmp_path: Path) -> None:
    if not (LEMHI_DATA / "hsi_curve.parquet").exists():
        pytest.skip("Lemhi data missing")
    src = tmp_path / "hsi_test.parquet"
    pd.read_parquet(LEMHI_DATA / "hsi_curve.parquet").to_parquet(src)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "hsi",
            "upgrade",
            str(src),
            "--set-grade",
            "A",
            "--out",
            str(tmp_path / "upgraded.parquet"),
        ],
    )
    assert result.exit_code == 0
    df = pd.read_parquet(tmp_path / "upgraded.parquet")
    assert (df["quality_grade"] == "A").all()


def test_reproduce_check_only_on_lemhi() -> None:
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi case missing")
    # First run to create provenance
    runner = CliRunner()
    runner.invoke(main, ["run", str(LEMHI_CASE)])
    prov = LEMHI_CASE.parent / "out" / "lemhi_2024" / "provenance.json"
    assert prov.exists()
    # Now reproduce check-only
    result = runner.invoke(main, ["reproduce", str(prov)])
    assert result.exit_code == 0
    assert "case YAML SHA matches" in result.output


def test_passage_cli_smoke(tmp_path: Path) -> None:
    if not (LEMHI_DATA / "swimming_performance.parquet").exists():
        pytest.skip("Lemhi data missing")
    cv_yaml = tmp_path / "cv.yaml"
    cv_yaml.write_text(
        "length_m: 18\n"
        "diameter_or_width_m: 1.2\n"
        "slope_percent: 1.5\n"
        "material: corrugated_metal\n"
        "shape: circular\n"
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "passage",
            "--culvert",
            str(cv_yaml),
            "--swim",
            str(LEMHI_DATA / "swimming_performance.parquet"),
            "--species",
            "oncorhynchus_mykiss",
            "--stage",
            "juvenile",
            "--discharge",
            "0.5",
            "--attraction-eta",
            "0.6",
        ],
    )
    assert result.exit_code == 0
    assert "η_P" in result.output or "eta_P" in result.output
    assert "η = η_A × η_P" in result.output


def test_calibrate_pestpp_glm_generates_workspace(tmp_path: Path) -> None:
    """CLI PEST++ path writes files instead of pretending to run pestpp-glm."""
    xs_path = tmp_path / "cross_section.parquet"
    pd.DataFrame({
        "station_m": [0.0, 0.0, 0.0, 0.0],
        "point_index": [0, 1, 2, 3],
        "distance_m": [-5.0, -4.999, 4.999, 5.0],
        "elevation_m": [5.0, 0.0, 0.0, 5.0],
    }).to_parquet(xs_path, index=False)
    (tmp_path / "mesh.nc").write_bytes(b"placeholder")
    observed = tmp_path / "observed.csv"
    pd.DataFrame({"h_m": [0.5, 1.0], "Q_m3s": [2.5, 6.0]}).to_csv(observed, index=False)
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text(
        "openlimno: '0.1'\n"
        "case:\n"
        "  name: pestpp_cli\n"
        "  crs: EPSG:4326\n"
        "mesh:\n"
        "  uri: mesh.nc\n"
        "hydrodynamics:\n"
        "  backend: builtin-1d\n"
        "habitat:\n"
        "  species: [oncorhynchus_mykiss]\n"
        "  stages: [spawning]\n"
        "  metric: wua-q\n"
        "  composite: min\n"
        "  acknowledge_independence: false\n"
        "  acknowledge_independence_reason: not using independent composite in this test\n"
        "data:\n"
        "  cross_section: cross_section.parquet\n"
        "output:\n"
        "  dir: out\n"
        "  formats: [csv]\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "pestpp"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "calibrate",
            str(case_yaml),
            "--observed",
            str(observed),
            "--algo",
            "pestpp-glm",
            "--pestpp-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "PEST++ GLM workspace generated" in result.output
    assert (out_dir / "openlimno_calibration.pst").exists()
    assert (out_dir / "run_openlimno_calibration.py").exists()


def test_preprocess_import_model_lists_supported_paths() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["preprocess", "import-model", "--list-supported"])
    assert result.exit_code == 0
    assert "hecras-geometry" in result.output
    assert "river2d-cdg" in result.output
    assert "hecras-hdf" in result.output
    assert "delft3d-netcdf" in result.output
    assert "mike-dfs" in result.output
    assert "mike-1d" in result.output
    assert "habby-csv" in result.output
    assert "instream-netlogo" in result.output


def test_preprocess_import_model_hecras_geometry(tmp_path: Path) -> None:
    ras = tmp_path / "synthetic.g03"
    ras.write_text(
        "Geom Title=Synthetic Test Geometry\n"
        "River Reach=Lemhi      ,Main\n"
        "X1=  100.0,      2,      0.,     20.,      0.,      0.\n"
        "GR=     1.5,      0.,     1.0,      5.\n"
    )
    out = tmp_path / "imported.csv"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "auto",
            "--in",
            str(ras),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert out.exists()
    df = pd.read_csv(out)
    assert len(df) == 2
    assert "HEC-RAS" in result.output


def test_preprocess_inspect_model_river2d_cdg(tmp_path: Path) -> None:
    cdg = tmp_path / "river2d.cdg"
    cdg.write_text(
        "NODES 3\n"
        "1 0.0 0.0 100.0 0.5\n"
        "2 1.0 0.0 100.1 0.6\n"
        "3 0.0 1.0 100.2 0.7\n"
        "ELEMENTS 1\n"
        "1 1 2 3\n"
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "preprocess",
            "inspect-model",
            "--source",
            "river2d-cdg",
            "--in",
            str(cdg),
        ],
    )

    assert result.exit_code == 0
    assert "River2D CDG inspection" in result.output
    assert "n_nodes" in result.output
    assert "n_elements" in result.output
    assert "node_id" in result.output


def test_preprocess_river2d_ugrid_command(tmp_path: Path) -> None:
    cdg = tmp_path / "river2d.cdg"
    cdg.write_text(
        "NODES 3\n"
        "1 0.0 0.0 100.0 0.5\n"
        "2 1.0 0.0 100.1 0.6\n"
        "3 0.0 1.0 100.2 0.7\n"
        "ELEMENTS 1\n"
        "1 1 2 3\n"
    )
    out = tmp_path / "river2d.nc"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "preprocess",
            "river2d-ugrid",
            "--in",
            str(cdg),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    assert out.exists()
    assert "wrote River2D UGRID mesh" in result.output


def test_preprocess_import_model_hecras_hdf(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    ras = tmp_path / "ras_results.hdf"
    with h5py.File(ras, "w") as h5:
        geom = h5.create_group("/Geometry/2D Flow Areas/Area 1")
        geom.create_dataset("Cells Center Coordinate", data=[[0.0, 0.0], [1.0, 0.0]])
        ts = h5.create_group(
            "/Results/Unsteady/Output/Output Blocks/Base Output/"
            "Unsteady Time Series/2D Flow Areas/Area 1"
        )
        ts.create_dataset("Depth", data=[[0.1, 0.2], [1.1, 1.2]])
        ts.create_dataset("Water Surface", data=[[10.1, 10.2], [11.1, 11.2]])
        ts.create_dataset("Velocity", data=[[0.4, 0.5], [1.4, 1.5]])

    out = tmp_path / "hydraulic_cells.csv"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "hecras-hdf",
            "--in",
            str(ras),
            "--out",
            str(out),
            "--time-index",
            "1",
        ],
    )
    assert result.exit_code == 0
    df = pd.read_csv(out)
    assert list(df["depth_m"]) == [1.1, 1.2]
    assert list(df["velocity_ms"]) == [1.4, 1.5]


def test_preprocess_inspect_model_hecras_hdf(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    ras = tmp_path / "ras_results.hdf"
    with h5py.File(ras, "w") as h5:
        geom = h5.create_group("/Geometry/2D Flow Areas/Area 1")
        geom.create_dataset("Cells Center Coordinate", data=[[0.0, 0.0], [1.0, 0.0]])
        ts = h5.create_group(
            "/Results/Unsteady/Output/Output Blocks/Base Output/"
            "Unsteady Time Series/2D Flow Areas/Area 1"
        )
        ts.create_dataset("Depth", data=[[0.1, 0.2], [1.1, 1.2]])
        ts.create_dataset("Water Surface", data=[[10.1, 10.2], [11.1, 11.2]])
        ts.create_dataset("Velocity", data=[[0.4, 0.5], [1.4, 1.5]])

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "preprocess",
            "inspect-model",
            "--source",
            "hecras-hdf",
            "--in",
            str(ras),
        ],
    )

    assert result.exit_code == 0
    assert "Area 1" in result.output
    assert "Depth" in result.output
    assert "cell_aligned" in result.output


def _install_fake_mikeio(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeItem:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeArray:
        def __init__(self, values: list[list[float]]) -> None:
            self.values = np.asarray(values, dtype=float)

    class FakeGeometry:
        n_elements = 2
        n_nodes = 3
        element_coordinates = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=float)

        def get_element_area(self) -> np.ndarray:
            return np.asarray([10.0, 20.0], dtype=float)

    class FakeDataset:
        items = (FakeItem("Water Depth"), FakeItem("Current speed"))
        geometry = FakeGeometry()
        time = ("2026-01-01 00:00", "2026-01-01 01:00")

        def __getitem__(self, idx: int) -> FakeArray:
            values = [
                [[0.1, 0.2], [1.1, 1.2]],
                [[0.4, 0.5], [1.4, 1.5]],
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

    monkeypatch.setitem(sys.modules, "mikeio", types.SimpleNamespace(open=lambda _: FakeReader()))


def test_preprocess_inspect_model_mike_dfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mikeio(monkeypatch)
    mike = tmp_path / "mike21_results.dfsu"
    mike.write_text("fake")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["preprocess", "inspect-model", "--source", "mike-dfs", "--in", str(mike)],
    )

    assert result.exit_code == 0
    assert "MIKE inspection" in result.output
    assert "Water Depth" in result.output
    assert "hydraulic_cells" in result.output


def test_preprocess_import_model_mike_dfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mikeio(monkeypatch)
    mike = tmp_path / "mike21_results.dfsu"
    mike.write_text("fake")
    out = tmp_path / "mike_cells.csv"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "mike-dfs",
            "--in",
            str(mike),
            "--out",
            str(out),
            "--time-index",
            "1",
        ],
    )

    assert result.exit_code == 0
    df = pd.read_csv(out)
    assert list(df["depth_m"]) == [1.1, 1.2]
    assert list(df["velocity_ms"]) == [1.4, 1.5]


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
    for t, depth in ((0.0, [0.1, 0.2, 0.3, 0.4]), (3600.0, [1.1, 1.2, 1.3, 1.4])):
        payload += _slf_float_record([t])
        payload += _slf_float_record(depth)
        payload += _slf_float_record([10.0 + d for d in depth])
        payload += _slf_float_record([0.6, 0.8, 0.0, 0.0])
        payload += _slf_float_record([0.8, 0.6, 0.0, 0.0])
    path.write_bytes(payload)


def test_preprocess_import_and_inspect_telemac_selafin(tmp_path: Path) -> None:
    slf = tmp_path / "telemac_results.slf"
    _write_synthetic_selafin(slf)

    runner = CliRunner()
    inspect_result = runner.invoke(
        main,
        ["preprocess", "inspect-model", "--source", "telemac-slf", "--in", str(slf)],
    )
    assert inspect_result.exit_code == 0
    assert "TELEMAC Selafin inspection" in inspect_result.output
    assert "WATER DEPTH" in inspect_result.output
    assert "u_ms" in inspect_result.output

    out = tmp_path / "telemac_cells.csv"
    import_result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "telemac-slf",
            "--in",
            str(slf),
            "--out",
            str(out),
            "--time-index",
            "1",
        ],
    )
    assert import_result.exit_code == 0
    df = pd.read_csv(out)
    assert list(df["depth_m"]) == pytest.approx([1.2, 1.2666666667])
    assert list(df["area_m2"]) == pytest.approx([0.5, 0.5])
    assert "velocity_ms" in df.columns


def test_preprocess_import_and_inspect_delft3d_netcdf(tmp_path: Path) -> None:
    nc = tmp_path / "dflowfm_map.nc"
    ds = xr.Dataset(
        data_vars={
            "mesh2d_face_x": ("mesh2d_nFaces", [0.0, 1.0]),
            "mesh2d_face_y": ("mesh2d_nFaces", [0.0, 0.0]),
            "mesh2d_flowelem_ba": ("mesh2d_nFaces", [10.0, 20.0]),
            "mesh2d_waterdepth": (("time", "mesh2d_nFaces"), [[0.1, 0.2], [1.1, 1.2]]),
            "mesh2d_s1": (("time", "mesh2d_nFaces"), [[10.1, 10.2], [11.1, 11.2]]),
            "mesh2d_ucmag": (("time", "mesh2d_nFaces"), [[0.4, 0.5], [1.4, 1.5]]),
        },
        coords={"time": pd.date_range("2026-01-01", periods=2, freq="h")},
    )
    ds.to_netcdf(nc)

    runner = CliRunner()
    inspect_result = runner.invoke(
        main,
        ["preprocess", "inspect-model", "--source", "delft3d-netcdf", "--in", str(nc)],
    )
    assert inspect_result.exit_code == 0
    assert "CF/UGRID NetCDF inspection" in inspect_result.output
    assert "mesh2d_waterdepth" in inspect_result.output

    out = tmp_path / "netcdf_cells.csv"
    import_result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "delft3d-netcdf",
            "--in",
            str(nc),
            "--out",
            str(out),
            "--time-index",
            "1",
        ],
    )
    assert import_result.exit_code == 0
    df = pd.read_csv(out)
    assert list(df["depth_m"]) == [1.1, 1.2]
    assert list(df["velocity_ms"]) == [1.4, 1.5]
    assert list(df["area_m2"]) == [10.0, 20.0]


def test_preprocess_import_and_inspect_habitat_exchange(tmp_path: Path) -> None:
    habitat = tmp_path / "habby_wua_cells.csv"
    pd.DataFrame(
        {
            "unit_id": [1, 2],
            "area": [10.0, 20.0],
            "HSI": [0.5, 0.2],
            "Q": [1.5, 1.5],
            "species": ["trout", "trout"],
            "stage": ["adult", "adult"],
        }
    ).to_csv(habitat, index=False)

    runner = CliRunner()
    inspect_result = runner.invoke(
        main,
        ["preprocess", "inspect-model", "--source", "habby-csv", "--in", str(habitat)],
    )
    assert inspect_result.exit_code == 0
    assert "Habitat exchange inspection" in inspect_result.output
    assert "habitat_cells" in inspect_result.output
    assert "HSI" in inspect_result.output

    out = tmp_path / "habitat_cells.csv"
    import_result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "habby-csv",
            "--in",
            str(habitat),
            "--out",
            str(out),
        ],
    )
    assert import_result.exit_code == 0
    df = pd.read_csv(out)
    assert list(df["cell_id"]) == [1, 2]
    assert list(df["wua_m2"]) == [5.0, 4.0]


def test_preprocess_import_habby_txt_spu_summary(tmp_path: Path) -> None:
    habitat = tmp_path / "d1_to_d9_sub_spu.txt"
    habitat.write_text(
        "discharge\tSPU\twetted_area\tspecies\tstage\n"
        "74.7\t31.5\t90.0\tbarbel\tadult\n",
        encoding="utf-8",
    )
    out = tmp_path / "habby_spu.csv"

    runner = CliRunner()
    import_result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "habby-csv",
            "--in",
            str(habitat),
            "--out",
            str(out),
        ],
    )

    assert import_result.exit_code == 0
    df = pd.read_csv(out)
    assert list(df["wua_m2"]) == [31.5]
    assert list(df["mean_csi"]) == pytest.approx([0.35])


def test_preprocess_diagnose_model_mike_1d_reports_runtime_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openlimno.preprocess.mike as mike_module

    monkeypatch.setattr(mike_module.sys, "platform", "linux")
    monkeypatch.setattr(mike_module.shutil, "which", lambda _: None)
    monkeypatch.setitem(sys.modules, "mikeio1d", types.SimpleNamespace(__version__="1.1.1"))

    runner = CliRunner()
    result = runner.invoke(main, ["preprocess", "diagnose-model", "--source", "mike-1d"])

    assert result.exit_code == 0
    assert "External model dependency diagnostic" in result.output
    assert "dotnet_required" in result.output
    assert "openlimno[mike]" in result.output
    assert "dotnet-runtime-8.0" in result.output


def test_preprocess_import_and_inspect_instream_population_summary(tmp_path: Path) -> None:
    population = tmp_path / "instream_population_summary.csv"
    pd.DataFrame(
        {
            "scenario": ["baseline", "baseline"],
            "reach": ["A", "A"],
            "year": [2026, 2026],
            "day": [1, 2],
            "species": ["rainbow_trout", "rainbow_trout"],
            "stage": ["adult", "adult"],
            "abundance": [120, 118],
            "biomass_g": [24000.0, 23850.0],
        }
    ).to_csv(population, index=False)

    runner = CliRunner()
    inspect_result = runner.invoke(
        main,
        [
            "preprocess",
            "inspect-model",
            "--source",
            "instream-netlogo",
            "--in",
            str(population),
        ],
    )
    assert inspect_result.exit_code == 0
    assert "inSTREAM/NetLogo exchange inspection" in inspect_result.output
    assert "population_summary" in inspect_result.output
    assert "abundance" in inspect_result.output

    out = tmp_path / "instream_population.csv"
    import_result = runner.invoke(
        main,
        [
            "preprocess",
            "import-model",
            "--source",
            "instream-netlogo",
            "--in",
            str(population),
            "--out",
            str(out),
        ],
    )
    assert import_result.exit_code == 0
    df = pd.read_csv(out)
    assert list(df["abundance"]) == [120, 118]
    assert list(df["reach_id"]) == ["A", "A"]


def test_ibm_export_writes_instream_exchange_package(tmp_path: Path) -> None:
    cells = pd.DataFrame(
        {
            "cell_id": [1, 2],
            "x": [10.0, 11.0],
            "y": [20.0, 21.0],
            "area_m2": [10.0, 20.0],
            "depth_m": [0.4, 0.8],
            "velocity_ms": [0.3, 0.6],
            "csi": [0.5, 0.2],
            "wua_m2": [5.0, 4.0],
            "discharge_m3s": [1.5, 1.5],
            "hmu_type": ["riffle", "run"],
        }
    )
    cells_path = tmp_path / "habitat_cells.csv"
    cells.to_csv(cells_path, index=False)
    out_dir = tmp_path / "instream_exchange"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ibm-export",
            "--cells",
            str(cells_path),
            "--scenario-id",
            "baseline",
            "--reach-id",
            "reach-a",
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    habitat = pd.read_csv(out_dir / "instream_habitat_cells.csv")
    summary = pd.read_csv(out_dir / "instream_flow_summary.csv")
    manifest = pd.read_csv(out_dir / "instream_exchange_manifest.csv")
    assert list(habitat["scenario_id"]) == ["baseline", "baseline"]
    assert list(habitat["reach_id"]) == ["reach-a", "reach-a"]
    assert summary["wua_m2"].iloc[0] == pytest.approx(9.0)
    assert set(manifest["table"]) == {"instream_habitat_cells", "instream_flow_summary"}


def test_wua_cells_cli_outputs_tables(tmp_path: Path) -> None:
    cells = pd.DataFrame(
        {
            "flow_area": ["Area 1", "Area 1"],
            "time_index": [0, 0],
            "cell_id": [0, 1],
            "depth_m": [0.5, 1.5],
            "velocity_ms": [0.4, 1.5],
            "area_m2": [10.0, 20.0],
        }
    )
    cells_path = tmp_path / "cells.csv"
    cells.to_csv(cells_path, index=False)
    hsi_path = tmp_path / "hsi_curve.parquet"
    pd.DataFrame(
        [
            {
                "species": "oncorhynchus_mykiss",
                "life_stage": "spawning",
                "variable": "depth",
                "points": [[0.0, 0.0], [0.3, 1.0], [0.9, 1.0], [1.5, 0.3], [3.0, 0.0]],
                "category": "III",
                "geographic_origin": "Pacific-Northwest-USA",
                "transferability_score": 0.6,
                "quality_grade": "B",
                "independence_tested": False,
                "evidence": [],
            },
            {
                "species": "oncorhynchus_mykiss",
                "life_stage": "spawning",
                "variable": "velocity",
                "points": [[0.0, 0.0], [0.4, 1.0], [1.0, 1.0], [2.0, 0.0]],
                "category": "III",
                "geographic_origin": "Pacific-Northwest-USA",
                "transferability_score": 0.6,
                "quality_grade": "B",
                "independence_tested": False,
                "evidence": [],
            },
        ]
    ).to_parquet(hsi_path, index=False)
    out_dir = tmp_path / "habitat"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "wua-cells",
            "--cells",
            str(cells_path),
            "--hsi",
            str(hsi_path),
            "--species",
            "oncorhynchus_mykiss",
            "--stage",
            "spawning",
            "--out-dir",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0
    assert (out_dir / "habitat_cells.csv").exists()
    summary = pd.read_csv(out_dir / "wua_summary.csv")
    assert summary["wua_m2"].iloc[0] == pytest.approx(16.0)


def test_wua_cli_outputs_table(tmp_path: Path) -> None:
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi case missing")
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "wua",
            str(LEMHI_CASE),
            "--species",
            "oncorhynchus_mykiss",
            "--stage",
            "spawning",
            "--n-q",
            "5",
        ],
    )
    assert result.exit_code == 0
    assert "discharge_m3s" in result.output
    assert "wua_m2" in result.output
