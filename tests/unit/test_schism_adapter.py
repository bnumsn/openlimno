"""SCHISMAdapter tests. M3 alpha — dry-run only; no live SCHISM."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from openlimno.hydro.schism import (
    LTS_VERSION,
    SCHISMAdapter,
    write_schism_hydraulic_cells_csv,
)


def test_lts_version_constant() -> None:
    assert LTS_VERSION == "5.11.0"


def test_prepare_creates_input_files(tmp_path: Path) -> None:
    adapter = SCHISMAdapter()
    work = tmp_path / "run1"
    case_yaml = tmp_path / "fake_case.yaml"
    case_yaml.write_text("# fake\n")
    out = adapter.prepare(case_yaml, work)
    assert out == work
    for fname in ["hgrid.gr3", "vgrid.in", "param.nml", "bctides.in", "drag.gr3"]:
        assert (work / fname).exists()
    assert (work / "outputs").is_dir()
    marker = json.loads((work / ".openlimno_prepared").read_text())
    assert marker["lts_version"] == "5.11.0"


def test_run_dry_run_returns_synthesised_report(tmp_path: Path) -> None:
    adapter = SCHISMAdapter()
    work = tmp_path / "dry"
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("ok\n")
    adapter.prepare(case_yaml, work)
    report = adapter.run(work, dry_run=True)
    assert report.dry_run
    assert report.return_code == 0
    assert report.log_path.exists()


def test_run_without_prepare_raises(tmp_path: Path) -> None:
    adapter = SCHISMAdapter()
    with pytest.raises(RuntimeError, match="not prepared"):
        adapter.run(tmp_path / "missing", dry_run=True)


def test_build_command_native(tmp_path: Path) -> None:
    """Builds an mpi/exe argv when an executable is configured."""
    adapter = SCHISMAdapter(executable="/usr/bin/echo", n_procs=1)
    cmd = adapter._build_command(tmp_path)
    assert cmd == ["/usr/bin/echo", "0"]
    adapter2 = SCHISMAdapter(executable="/usr/bin/echo", n_procs=4, n_scribes=1)
    cmd2 = adapter2._build_command(tmp_path)
    assert cmd2 == ["mpirun", "-n", "4", "/usr/bin/echo", "1"]


def test_build_command_container_docker(tmp_path: Path) -> None:
    adapter = SCHISMAdapter(
        container_image="ghcr.io/openlimno/schism:5.11.0",
        container_runtime="docker",
    )
    cmd = adapter._build_command(tmp_path)
    assert cmd[0] == "docker"
    # --user host-uid:gid is POSIX-only (os.getuid absent on Windows).
    assert ("--user" in cmd) == hasattr(os, "getuid")
    assert "ghcr.io/openlimno/schism:5.11.0" in cmd
    assert "/work" in cmd  # working dir mount target
    assert cmd[-1] == "0"

    mpi_adapter = SCHISMAdapter(
        container_image="ghcr.io/openlimno/schism:5.11.0",
        container_runtime="docker",
        n_procs=5,
        n_scribes=4,
    )
    mpi_cmd = mpi_adapter._build_command(tmp_path)
    assert "--entrypoint" in mpi_cmd
    assert "mpirun" in mpi_cmd
    assert mpi_cmd[-4:] == ["-n", "5", "/usr/local/bin/schism", "4"]


def test_build_command_container_apptainer(tmp_path: Path) -> None:
    adapter = SCHISMAdapter(
        container_image="oras://ghcr.io/openlimno/schism:5.11.0",
        container_runtime="apptainer",
    )
    cmd = adapter._build_command(tmp_path)
    assert cmd[0] == "apptainer"
    assert "--bind" in cmd
    assert cmd[-1] == "0"


def test_build_command_no_executable_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENLIMNO_SCHISM", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    adapter = SCHISMAdapter()
    with pytest.raises(RuntimeError, match="No SCHISM executable"):
        adapter._build_command(tmp_path)


def test_run_with_missing_executable_returns_127(tmp_path: Path) -> None:
    adapter = SCHISMAdapter(executable="/definitely/not/there/schism_xyz")
    work = tmp_path / "no_exe"
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("\n")
    adapter.prepare(case_yaml, work)
    report = adapter.run(work, dry_run=False)
    assert report.return_code == 127
    assert report.log_path.exists()


def test_read_results_no_files_raises(tmp_path: Path) -> None:
    adapter = SCHISMAdapter()
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("\n")
    adapter.prepare(case_yaml, tmp_path / "empty")
    with pytest.raises(FileNotFoundError, match="No schout"):
        adapter.read_results(tmp_path / "empty")


def test_read_results_normalizes_out2d_depth_velocity_and_area(tmp_path: Path) -> None:
    work = tmp_path / "schism"
    outputs = work / "outputs"
    outputs.mkdir(parents=True)
    ds = xr.Dataset(
        data_vars={
            "SCHISM_hgrid_node_x": (("node",), np.array([0.0, 1.0, 1.0, 0.0])),
            "SCHISM_hgrid_node_y": (("node",), np.array([0.0, 0.0, 1.0, 1.0])),
            "SCHISM_hgrid_node_depth": (("node",), np.array([2.0, 3.0, 1.0, 4.0])),
            "SCHISM_hgrid_face_nodes": (
                ("face", "vertex"),
                np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32),
                {"_FillValue": -1, "start_index": 0},
            ),
            "elevation": (
                ("time", "node"),
                np.array([[0.5, -0.2, -2.0, 0.0], [1.0, 0.0, 0.2, -0.5]]),
            ),
            "depthAverageVelX": (
                ("time", "node"),
                np.array([[0.3, 0.4, 0.5, 0.6], [0.1, 0.2, 0.3, 0.4]]),
            ),
            "depthAverageVelY": (
                ("time", "node"),
                np.array([[0.4, 0.3, 0.0, 0.8], [0.0, 0.1, 0.2, 0.3]]),
            ),
        },
        coords={"time": np.array([0.0, 60.0])},
    )
    ds.to_netcdf(outputs / "out2d_1.nc")

    result = SCHISMAdapter().read_results(work)

    assert result.n_nodes == 4
    assert result.n_times == 2
    assert len(result.table) == 8
    first = result.table[result.table["node_id"].eq(1) & result.table["source_time_index"].eq(0)]
    assert first["depth_m"].iloc[0] == pytest.approx(2.5)
    assert first["velocity_ms"].iloc[0] == pytest.approx(0.5)
    dry = result.table[result.table["node_id"].eq(3) & result.table["source_time_index"].eq(0)]
    assert pd.isna(dry["depth_m"].iloc[0])
    assert result.table.drop_duplicates("node_id")["area_m2"].sum() == pytest.approx(1.0)
    assert set(
        [
            "cell_id",
            "center_x_m",
            "center_y_m",
            "depth_m",
            "velocity_ms",
            "area_m2",
        ]
    ).issubset(result.table.columns)

    out_csv = write_schism_hydraulic_cells_csv(result, tmp_path / "hydraulic_cells.csv")
    assert pd.read_csv(out_csv)["cell_id"].nunique() == 4


def test_read_results_handles_v511_static_mesh_across_output_stacks(tmp_path: Path) -> None:
    work = tmp_path / "schism"
    outputs = work / "outputs"
    outputs.mkdir(parents=True)
    for index, (time_seconds, stage_offset) in enumerate(((0.0, 0.5), (60.0, 0.7)), start=1):
        xr.Dataset(
            data_vars={
                "SCHISM_hgrid_node_x": (
                    ("nSCHISM_hgrid_node",),
                    np.array([0.0, 1.0, 0.0]),
                ),
                "SCHISM_hgrid_node_y": (
                    ("nSCHISM_hgrid_node",),
                    np.array([0.0, 0.0, 1.0]),
                ),
                "depth": (("nSCHISM_hgrid_node",), np.array([2.0, 3.0, 4.0])),
                "SCHISM_hgrid_face_nodes": (
                    ("nSCHISM_hgrid_face", "nMaxSCHISM_hgrid_face_nodes"),
                    np.array([[1, 2, 3, -1]], dtype=np.int32),
                    {"_FillValue": -1, "start_index": 1},
                ),
                "elevation": (
                    ("time", "nSCHISM_hgrid_node"),
                    np.array([[stage_offset, stage_offset, stage_offset]]),
                ),
                "horizontalVelX": (
                    ("time", "nSCHISM_hgrid_node", "nSCHISM_vgrid_layers"),
                    np.array([[[0.3], [0.4], [0.5]]]),
                ),
                "horizontalVelY": (
                    ("time", "nSCHISM_hgrid_node", "nSCHISM_vgrid_layers"),
                    np.array([[[0.4], [0.3], [0.0]]]),
                ),
            },
            coords={"time": np.array([time_seconds])},
        ).to_netcdf(outputs / f"out2d_{index}.nc")

    result = SCHISMAdapter().read_results(work)

    assert result.n_nodes == 3
    assert result.n_times == 2
    assert len(result.table) == 6
    assert result.dataset["bathymetric_depth_m"].values.tolist() == pytest.approx([2.0, 3.0, 4.0])
    assert result.table.drop_duplicates("node_id")["area_m2"].sum() == pytest.approx(0.5)
    assert result.table["velocity_ms"].notna().all()


def test_read_results_can_select_one_time_index(tmp_path: Path) -> None:
    work = tmp_path / "schism"
    outputs = work / "outputs"
    outputs.mkdir(parents=True)
    xr.Dataset(
        data_vars={
            "SCHISM_hgrid_node_x": (("node",), np.array([0.0, 1.0])),
            "SCHISM_hgrid_node_y": (("node",), np.array([0.0, 0.0])),
            "SCHISM_hgrid_node_depth": (("node",), np.array([2.0, 2.0])),
            "elevation": (("time", "node"), np.array([[0.0, 0.1], [0.2, 0.3]])),
            "hvel": (
                ("time", "node", "component"),
                np.array([[[0.1, 0.2], [0.3, 0.4]], [[0.5, 0.0], [0.0, 0.6]]]),
            ),
        },
        coords={"time": np.array([0.0, 10.0])},
    ).to_netcdf(outputs / "schout_1.nc")

    result = SCHISMAdapter().read_results(work, time_index=-1)

    assert result.n_times == 1
    assert result.selected_time_index == 1
    assert result.table["source_time_index"].unique().tolist() == [1]
    assert result.table["velocity_ms"].tolist() == pytest.approx([0.5, 0.6])
