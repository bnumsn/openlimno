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
    pd.DataFrame(
        {
            "station_m": [0.0, 0.0, 0.0, 0.0],
            "point_index": [0, 1, 2, 3],
            "distance_m": [-5.0, -4.999, 4.999, 5.0],
            "elevation_m": [5.0, 0.0, 0.0, 5.0],
        }
    ).to_parquet(xs_path, index=False)
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


def test_v251_wua_plot_cli_writes_png_via_atomic_write(tmp_path: Path) -> None:
    """v2.5.1 (R8-9): pin that the CLI ``openlimno wua --plot`` route
    actually writes a PNG to disk.

    v2.3.0 fixed a latent v1.9.2 R5-3 regression where matplotlib's
    ``fig.savefig`` raised ``Format 'tmp' is not supported`` because
    the publish tempfile from ``Case._atomic_write`` ends in
    ``.tmp``. The fix passes ``format="png"`` explicitly. v2.3.0
    covered the headless ``plot_wua_q`` path but NOT this CLI route
    end-to-end, so the regression could re-emerge if anyone
    refactored the CLI invocation without touching the helper.
    """
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi example missing")
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
            "--plot",
            "--n-q",
            "3",
        ],
    )
    assert result.exit_code == 0, f"CLI exited {result.exit_code}; output:\n{result.output}"
    # Output PNG lives under the case's output_dir (lemhi out/...).
    # The CLI prints "plot saved: <path>"; assert that path exists.
    saved_lines = [line for line in result.output.splitlines() if "plot saved:" in line]
    assert saved_lines, f"no 'plot saved' line in CLI output:\n{result.output}"
    png_path = Path(saved_lines[-1].split("plot saved:", 1)[1].strip())
    assert png_path.exists(), f"PNG not on disk: {png_path}"
    assert png_path.stat().st_size > 0, "PNG file is empty"


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
        "discharge\tSPU\twetted_area\tspecies\tstage\n74.7\t31.5\t90.0\tbarbel\tadult\n",
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


def test_ibm_studio_cli_invokes_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openlimno.ibm as ibm

    calls: dict[str, object] = {}

    def fake_run_ibm_studio(
        *,
        host: str,
        port: int,
        output_dir: str | Path,
        open_browser: bool,
    ) -> None:
        calls.update(
            {
                "host": host,
                "port": port,
                "output_dir": Path(output_dir),
                "open_browser": open_browser,
            }
        )

    monkeypatch.setattr(ibm, "run_ibm_studio", fake_run_ibm_studio)

    runner = CliRunner()
    # 2026-05-26 R-IBM-STUDIO-CONSOLIDATE: ibm-studio now requires
    # --i-understand-this-is-experimental so the third disconnected
    # GUI surface can't be invoked accidentally. ADR-0016 cleanup.
    result = runner.invoke(
        main,
        [
            "ibm-studio",
            "--host",
            "127.0.0.1",
            "--port",
            "8877",
            "--out-dir",
            str(tmp_path),
            "--no-open-browser",
            "--i-understand-this-is-experimental",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "starting OpenLimno IBM Studio" in result.output
    assert calls == {
        "host": "127.0.0.1",
        "port": 8877,
        "output_dir": tmp_path,
        "open_browser": False,
    }


def test_ibm_studio_cli_refuses_without_experimental_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-IBM-STUDIO-CONSOLIDATE: ibm-studio must refuse to start
    unless the user explicitly opts in to the experimental flag.
    Without the flag, the command returns a UsageError with a
    pointer to the production PyQt6 Studio.
    """
    import openlimno.ibm as ibm

    def fake_run_ibm_studio(*args: object, **kwargs: object) -> None:
        # Should NOT be called when the gating flag is absent.
        raise AssertionError("ibm-studio launched without the experimental flag")

    monkeypatch.setattr(ibm, "run_ibm_studio", fake_run_ibm_studio)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ibm-studio",
            "--host",
            "127.0.0.1",
            "--port",
            "8877",
            "--out-dir",
            str(tmp_path),
            "--no-open-browser",
            # --i-understand-this-is-experimental DELIBERATELY ABSENT
        ],
    )
    assert result.exit_code != 0, "ibm-studio should refuse to start without the flag"
    assert "--i-understand-this-is-experimental" in result.output


def test_ibm_run_native_writes_population_outputs(tmp_path: Path) -> None:
    cells = pd.DataFrame(
        {
            "cell_id": ["pool-a", "riffle-b"],
            "area_m2": [15.0, 25.0],
            "depth_m": [0.4, 0.8],
            "velocity_ms": [0.2, 0.35],
            "csi": [0.4, 0.9],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [0.1, 0.8],
        }
    )
    cells_path = tmp_path / "habitat_cells.csv"
    cells.to_csv(cells_path, index=False)
    out_dir = tmp_path / "native_ibm"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ibm-run-native",
            "--cells",
            str(cells_path),
            "--initial-abundance",
            "12",
            "--days",
            "3",
            "--seed",
            "4",
            "--individual-history",
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    assert "native IBM run complete" in result.output
    summary = pd.read_csv(out_dir / "native_ibm_population_summary.csv")
    individuals = pd.read_csv(out_dir / "native_ibm_final_individuals.csv")
    cell_use = pd.read_csv(out_dir / "native_ibm_cell_use.csv")
    history = pd.read_csv(out_dir / "native_ibm_individual_history.csv")
    assert len(summary) == 4
    assert len(individuals) >= 12
    assert len(history) >= 48
    assert not cell_use.empty
    assert set(cell_use["cell_id"]) <= {"pool-a", "riffle-b"}


def test_ibm_profile_validate_cli(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "profile_version: '0.2'\n"
        "species:\n"
        "  id: rainbow_trout\n"
        "mortality:\n"
        "  base_daily_survival: 0.99\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["ibm", "profile", "validate", str(profile_path)])

    assert result.exit_code == 0, result.output
    assert "validates against IBM profile schema" in result.output


def test_ibm_scenario_validate_and_run_cli(tmp_path: Path) -> None:
    cells_path = tmp_path / "habitat_cells.csv"
    pd.DataFrame(
        {
            "reach_id": ["r1", "r1"],
            "cell_id": ["pool-a", "riffle-b"],
            "area_m2": [15.0, 25.0],
            "depth_m": [0.4, 0.8],
            "velocity_ms": [0.2, 0.35],
            "csi": [0.4, 0.9],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [0.1, 0.8],
            "feeding_cover": [0.1, 0.7],
        }
    ).to_csv(cells_path, index=False)
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "profile_version: '0.2'\n"
        "species:\n"
        "  id: rainbow_trout\n"
        "mortality:\n"
        "  base_daily_survival: 1.0\n"
        "  predation_base_risk: 0.0\n"
        "  predation_csi_risk: 0.0\n",
        encoding="utf-8",
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: cli-smoke\n"
        "  reach_id: r1\n"
        "  days: 2\n"
        "  seed: 7\n"
        "  stochastic: false\n"
        "profile:\n"
        "  uri: profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 3\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["ibm", "scenario", "validate", str(scenario_path)])
    assert result.exit_code == 0, result.output
    assert "validates against IBM scenario schema" in result.output

    result = runner.invoke(main, ["ibm", "run", str(scenario_path)])
    assert result.exit_code == 0, result.output
    assert "IBM scenario run complete" in result.output
    assert (tmp_path / "out" / "ibm_run_manifest.json").exists()


def test_ibm_submodels_ensemble_and_calibrate_cli(tmp_path: Path) -> None:
    cells_path = tmp_path / "habitat_cells.csv"
    pd.DataFrame(
        {
            "cell_id": ["pool-a", "riffle-b"],
            "area_m2": [15.0, 25.0],
            "depth_m": [0.4, 0.8],
            "velocity_ms": [0.2, 0.35],
            "csi": [0.4, 0.9],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [0.1, 0.8],
            "feeding_cover": [0.1, 0.7],
        }
    ).to_csv(cells_path, index=False)
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "profile_version: '0.2'\n"
        "species:\n"
        "  id: rainbow_trout\n"
        "mortality:\n"
        "  base_daily_survival: 1.0\n"
        "  predation_base_risk: 0.0\n"
        "  predation_csi_risk: 0.0\n"
        "  thermal_stress_mortality: 0.0\n"
        "  hydraulic_stress_mortality: 0.0\n",
        encoding="utf-8",
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: cli-experiments\n"
        "  days: 1\n"
        "  stochastic: false\n"
        "  light_phases: [day]\n"
        "profile:\n"
        "  uri: profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 4\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )
    observed_path = tmp_path / "observed.csv"
    pd.DataFrame({"day": [1], "abundance": [4]}).to_csv(observed_path, index=False)
    runner = CliRunner()

    result = runner.invoke(main, ["ibm", "submodels"])
    assert result.exit_code == 0, result.output
    assert "native-habitat-utility-v0" in result.output

    result = runner.invoke(
        main,
        [
            "ibm",
            "ensemble",
            str(scenario_path),
            "--seed",
            "1",
            "--seed",
            "2",
            "--out-dir",
            str(tmp_path / "ensemble"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "IBM ensemble complete" in result.output
    assert (tmp_path / "ensemble" / "ibm_ensemble_summary.csv").exists()

    result = runner.invoke(
        main,
        [
            "ibm",
            "calibrate",
            str(scenario_path),
            "--observed",
            str(observed_path),
            "--param",
            "base_daily_survival=0.5,1.0",
            "--out-dir",
            str(tmp_path / "calibration"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "IBM calibration complete" in result.output
    assert (tmp_path / "calibration" / "best_profile.yaml").exists()


def test_ibm_benchmark_instream7_cli_invokes_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openlimno.ibm as ibm

    fixture = tmp_path / "official-instream"
    fixture.mkdir()
    out_dir = tmp_path / "benchmark"
    calls: dict[str, object] = {}

    def fake_run_instream7_official_benchmark(
        root: str | Path,
        output_dir: str | Path,
        *,
        case_ids: tuple[str, ...] | None = None,
        days: int = 7,
        seed: int = 42,
        stochastic: bool = True,
    ) -> types.SimpleNamespace:
        calls.update(
            {
                "root": Path(root),
                "output_dir": Path(output_dir),
                "case_ids": case_ids,
                "days": days,
                "seed": seed,
                "stochastic": stochastic,
            }
        )
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        redd_path = Path(output_dir) / "instream7_native_redds.csv"
        redd_path.write_text("redd_id\n", encoding="utf-8")
        return types.SimpleNamespace(
            inventory=pd.DataFrame({"case_id": ["ExampleA"]}),
            population_summary=pd.DataFrame({"day": [0, 1]}),
            paths={"instream7_native_redds": str(redd_path)},
        )

    monkeypatch.setattr(
        ibm,
        "run_instream7_official_benchmark",
        fake_run_instream7_official_benchmark,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ibm-benchmark-instream7",
            "--fixture",
            str(fixture),
            "--case-id",
            "ExampleA",
            "--days",
            "2",
            "--seed",
            "5",
            "--deterministic",
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "inSTREAM 7 official benchmark complete" in result.output
    assert calls == {
        "root": fixture,
        "output_dir": out_dir,
        "case_ids": ("ExampleA",),
        "days": 2,
        "seed": 5,
        "stochastic": False,
    }
    assert "instream7_native_redds" in result.output


def test_ibm_run_instream7_netlogo_reference_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openlimno.ibm as ibm

    fixture = tmp_path / "official"
    fixture.mkdir()
    out_dir = tmp_path / "netlogo-out"
    netlogo = tmp_path / "NetLogo_Console"
    netlogo.write_text("#!/bin/sh\n", encoding="utf-8")
    brief = out_dir / "BriefPopOut-r1.csv"
    calls: dict[str, object] = {}

    def fake_run_instream7_netlogo_reference(
        root: Path,
        output_dir: Path,
        *,
        case_id: str,
        netlogo_console: str,
        days: int,
        seed: int,
    ) -> types.SimpleNamespace:
        calls.update(
            {
                "root": root,
                "output_dir": output_dir,
                "case_id": case_id,
                "netlogo_console": netlogo_console,
                "days": days,
                "seed": seed,
            }
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        brief.write_text("brief\n", encoding="utf-8")
        return types.SimpleNamespace(
            setup_file=output_dir / "openlimno-ExampleA-2d.xml",
            table_path=output_dir / "openlimno_netlogo_table.csv",
            spreadsheet_path=output_dir / "openlimno_netlogo_spreadsheet.csv",
            brief_population_files=(brief,),
        )

    monkeypatch.setattr(
        ibm, "run_instream7_netlogo_reference", fake_run_instream7_netlogo_reference
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ibm-run-instream7-netlogo-reference",
            "--fixture",
            str(fixture),
            "--case-id",
            "ExampleA",
            "--days",
            "2",
            "--seed",
            "11",
            "--netlogo-console",
            str(netlogo),
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "NetLogo reference run complete" in result.output
    assert "brief_pop" in result.output
    assert calls == {
        "root": fixture,
        "output_dir": out_dir,
        "case_id": "ExampleA",
        "netlogo_console": str(netlogo),
        "days": 2,
        "seed": 11,
    }


def test_ibm_summarize_instream7_brief_cli(tmp_path: Path) -> None:
    brief = tmp_path / "BriefPopOut-r1.csv"
    brief.write_text(
        "InSTREAM-7 brief population output file, Created 10:39:01 AM\n"
        "BehavSp-Run,End of time step,IsCensus?,Light phase,Reach,Flow,Temperature,Turbidity,Species,Age class,Count,Mean length,Mean weight,Mean condition,FractionDriftFeeding,FractionSearchFeeding,FractionHiding\n"
        "1,10/1/2001 00:00,false,At setup,ExampleA,3.65,-999,0,Rainbow,Age-0,3,5.0,2.0,1,0,0,1\n"
        "1,10/1/2001 00:00,false,At setup,ExampleA,3.65,-999,0,Rainbow,Age-1,2,10.0,20.0,1,0,0,1\n",
        encoding="utf-8",
    )
    out = tmp_path / "summary.csv"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ibm-summarize-instream7-brief",
            "--brief-pop",
            str(brief),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "BriefPop summary written" in result.output
    summary = pd.read_csv(out)
    assert int(summary["abundance"].iloc[0]) == 5
    assert summary["mean_length_mm"].iloc[0] == pytest.approx(70.0)


def test_ibm_compare_instream7_netlogo_cli(tmp_path: Path) -> None:
    brief = tmp_path / "BriefPopOut-r1.csv"
    brief.write_text(
        "InSTREAM-7 brief population output file, Created 10:39:01 AM\n"
        "BehavSp-Run,End of time step,IsCensus?,Light phase,Reach,Flow,Temperature,Turbidity,Species,Age class,Count,Mean length,Mean weight,Mean condition,FractionDriftFeeding,FractionSearchFeeding,FractionHiding\n"
        "1,10/1/2001 00:00,false,At setup,ExampleA,3.65,-999,0,Rainbow,Age-0,3,5.0,2.0,1,0,0,1\n"
        "1,10/1/2001 00:00,false,At setup,ExampleA,3.65,-999,0,Rainbow,Age-1,2,10.0,20.0,1,0,0,1\n",
        encoding="utf-8",
    )
    native = tmp_path / "native_summary.csv"
    pd.DataFrame(
        {
            "scenario_id": ["ExampleA"],
            "reach_id": ["ExampleA"],
            "species": ["Rainbow"],
            "day": [0],
            "official_date": ["2001-10-01"],
            "abundance": [5],
            "biomass_g": [46.0],
            "mean_length_mm": [70.0],
        }
    ).to_csv(native, index=False)
    out = tmp_path / "comparison.csv"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "ibm-compare-instream7-netlogo",
            "--native-summary",
            str(native),
            "--brief-pop",
            str(brief),
            "--out",
            str(out),
            "--abundance-tolerance",
            "0",
            "--biomass-rel-tolerance",
            "0.01",
            "--mean-length-tolerance-mm",
            "0.1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "native-vs-NetLogo comparison written" in result.output
    comparison = pd.read_csv(out)
    assert len(comparison) == 1
    assert bool(comparison["passed"].iloc[0])


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
