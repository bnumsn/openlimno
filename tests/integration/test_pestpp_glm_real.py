"""Opt-in real PEST++ GLM integration test.

Run with:

    pixi run -e pestpp test-pestpp
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from openlimno.workflows import (
    build_pestpp_glm_workspace,
    run_pestpp_glm_workspace,
)

pytestmark = pytest.mark.pestpp


def _write_case(tmp_path: Path) -> Path:
    pd.DataFrame(
        {
            "station_m": [0.0, 0.0, 0.0, 0.0],
            "point_index": [0, 1, 2, 3],
            "distance_m": [-5.0, -4.999, 4.999, 5.0],
            "elevation_m": [5.0, 0.0, 0.0, 5.0],
        }
    ).to_parquet(tmp_path / "cross_section.parquet", index=False)
    (tmp_path / "mesh.nc").write_bytes(b"placeholder")
    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text(
        "openlimno: '0.1'\n"
        "case:\n"
        "  name: pestpp_real\n"
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


def test_real_pestpp_glm_runs_openlimno_workspace(tmp_path: Path) -> None:
    """Generated PEST++ files are accepted by a real pestpp-glm binary."""
    case_yaml = _write_case(tmp_path)
    obs = pd.DataFrame(
        {
            "h_m": [0.5, 1.0, 1.5],
            "Q_m3s": [2.5, 6.0, 10.0],
        }
    )
    workspace = build_pestpp_glm_workspace(
        case_yaml,
        obs,
        tmp_path / "pestpp",
        initial_n=0.04,
        slope=0.001,
    )

    result = run_pestpp_glm_workspace(
        workspace,
        executable="pestpp-glm",
        timeout=180,
        check=True,
    )

    assert result.returncode == 0
    assert result.record_file is not None and result.record_file.exists()
    assert workspace.model_output_file.exists()
