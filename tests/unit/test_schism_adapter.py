"""SCHISMAdapter tests. M3 alpha — dry-run only; no live SCHISM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openlimno.hydro.schism import LTS_VERSION, SCHISMAdapter


def test_lts_version_constant() -> None:
    assert LTS_VERSION == "5.11.0"


def test_prepare_creates_input_files(tmp_path: Path) -> None:
    adapter = SCHISMAdapter()
    work = tmp_path / "run1"
    case_yaml = tmp_path / "fake_case.yaml"
    case_yaml.write_text("# fake\n")
    out = adapter.prepare(case_yaml, work)
    assert out == work
    for fname in ["hgrid.gr3", "vgrid.in", "param.nml", "bctides.in"]:
        assert (work / fname).exists()
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
    assert cmd == ["/usr/bin/echo"]
    adapter2 = SCHISMAdapter(executable="/usr/bin/echo", n_procs=4)
    cmd2 = adapter2._build_command(tmp_path)
    assert cmd2 == ["mpirun", "-n", "4", "/usr/bin/echo"]


def test_build_command_container_docker(tmp_path: Path) -> None:
    adapter = SCHISMAdapter(
        container_image="ghcr.io/openlimno/schism:5.11.0",
        container_runtime="docker",
    )
    cmd = adapter._build_command(tmp_path)
    assert cmd[0] == "docker"
    assert "ghcr.io/openlimno/schism:5.11.0" in cmd
    assert "/work" in cmd  # working dir mount target


def test_build_command_container_apptainer(tmp_path: Path) -> None:
    adapter = SCHISMAdapter(
        container_image="oras://ghcr.io/openlimno/schism:5.11.0",
        container_runtime="apptainer",
    )
    cmd = adapter._build_command(tmp_path)
    assert cmd[0] == "apptainer"
    assert "--bind" in cmd


def test_build_command_no_executable_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
