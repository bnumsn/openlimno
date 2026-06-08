"""Calibration workflow tests."""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from openlimno.hydro.builtin_1d import CrossSection
from openlimno.workflows import (
    build_pestpp_glm_workspace,
    calibrate_manning_n,
    run_pestpp_glm_workspace,
)


def make_rect(width: float = 10.0, n: float = 0.035) -> CrossSection:
    half = width / 2
    return CrossSection(
        station_m=0.0,
        distance_m=np.array([-half - 1e-6, -half, half, half + 1e-6]),
        elevation_m=np.array([10.0, 0.0, 0.0, 10.0]),
        manning_n=n,
    )


def test_calibrate_recovers_known_n() -> None:
    """Synthesize observed rating with n=0.030, calibrate from initial 0.045."""
    xs = make_rect(n=0.030)
    obs_h = np.array([0.3, 0.5, 0.8, 1.2, 1.6])
    obs_Q = np.array([xs.manning_discharge(h, slope=0.001) for h in obs_h])
    obs = pd.DataFrame({"h_m": obs_h, "Q_m3s": obs_Q})

    res = calibrate_manning_n(
        cross_section=xs,
        observed_rating=obs,
        slope=0.001,
        initial_n=0.045,
    )
    assert res.calibrated_value == pytest.approx(0.030, rel=1e-3)
    assert res.rmse_final < res.rmse_initial
    assert res.rmse_final < 0.01
    assert res.converged


def test_calibrate_does_not_modify_section_n() -> None:
    """Calibration must restore the original n on the input section."""
    xs = make_rect(n=0.040)
    obs = pd.DataFrame({"h_m": [0.5, 1.0], "Q_m3s": [3.0, 8.0]})
    calibrate_manning_n(xs, obs, slope=0.001)
    assert xs.manning_n == 0.040


def test_calibrate_missing_columns_raises() -> None:
    xs = make_rect()
    obs = pd.DataFrame({"depth": [0.5], "discharge": [3.0]})
    with pytest.raises(ValueError, match="h_m.*Q_m3s"):
        calibrate_manning_n(xs, obs)


def test_calibrate_respects_bounds() -> None:
    """Out-of-bounds optimum should clamp to bounds."""
    xs = make_rect(n=0.005)
    obs_h = np.array([0.5, 1.0])
    obs_Q = np.array([xs.manning_discharge(h, slope=0.001) for h in obs_h])
    obs = pd.DataFrame({"h_m": obs_h, "Q_m3s": obs_Q})

    res = calibrate_manning_n(
        xs,
        obs,
        slope=0.001,
        initial_n=0.030,
        bounds=(0.012, 0.080),  # excludes the true 0.005
    )
    # Calibrated value should be at lower bound
    assert res.calibrated_value == pytest.approx(0.012, rel=0.05)


def _write_minimal_calibration_case(tmp_path):
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
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text(
        "openlimno: '0.1'\n"
        "case:\n"
        "  name: pestpp_unit\n"
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
    return case_yaml


def test_build_pestpp_workspace_writes_control_files_and_runner(tmp_path) -> None:
    """PEST++ route should generate a runnable local model workspace."""
    case_yaml = _write_minimal_calibration_case(tmp_path)
    obs = pd.DataFrame({"h_m": [0.5, 1.0], "Q_m3s": [2.5, 6.0]})

    workspace = build_pestpp_glm_workspace(
        case_yaml,
        obs,
        tmp_path / "pestpp",
        initial_n=0.04,
        slope=0.001,
    )

    for path in (
        workspace.control_file,
        workspace.template_file,
        workspace.parameter_file,
        workspace.instruction_file,
        workspace.observed_file,
        workspace.runner_script,
        workspace.readme_file,
    ):
        assert path.exists(), path

    control = workspace.control_file.read_text()
    assert "manning_n log factor 0.04" in control
    assert "slope log factor 0.001" in control
    assert "q_0001 2.5 1.0 rating" in control
    assert "params.tpl params.in" in control

    proc = subprocess.run(
        [sys.executable, str(workspace.runner_script)],
        cwd=workspace.directory,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    model_out = workspace.model_output_file.read_text()
    assert "obs_name predicted_Q_m3s" in model_out
    assert "q_0001" in model_out
    assert "q_0002" in model_out


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="mock binary is a POSIX shebang script and the runner uses subprocess "
    "pass_fds; PEST++ is a research-route (non-Windows) path.",
)
def test_run_pestpp_workspace_invokes_external_binary(tmp_path) -> None:
    """PEST++ runner wrapper executes an installed/explicit pestpp-glm binary."""
    case_yaml = _write_minimal_calibration_case(tmp_path)
    obs = pd.DataFrame({"h_m": [0.5], "Q_m3s": [2.5]})
    workspace = build_pestpp_glm_workspace(case_yaml, obs, tmp_path / "pestpp")
    fake = tmp_path / "fake_pestpp_glm"
    fake.write_text(
        "#!/usr/bin/env python\n"
        "from pathlib import Path\n"
        "import sys\n"
        "Path('openlimno_calibration.rec').write_text('ok\\n')\n"
        "print('fake pestpp', sys.argv[1])\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    result = run_pestpp_glm_workspace(
        workspace,
        executable=str(fake),
        timeout=30,
        check=True,
    )
    assert result.returncode == 0
    assert "fake pestpp openlimno_calibration.pst" in result.stdout
    assert result.record_file == workspace.directory / "openlimno_calibration.rec"
