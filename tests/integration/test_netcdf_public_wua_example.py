"""Opt-in end-to-end test for the public Delft3D NetCDF -> WUA example."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

RUN_REAL_NETCDF = os.environ.get("OPENLIMNO_RUN_NETCDF_REAL") == "1"

pytestmark = [
    pytest.mark.online,
]


def test_public_delft3d_wua_example_runs_end_to_end(tmp_path: Path) -> None:
    if not RUN_REAL_NETCDF:
        pytest.skip("set OPENLIMNO_RUN_NETCDF_REAL=1 to run the public Delft3D WUA example")

    repo = Path(__file__).resolve().parents[2]
    script = repo / "examples" / "model_interop" / "delft3d_public_wua.py"
    cache_dir = Path(os.environ.get("OPENLIMNO_NETCDF_FIXTURE_DIR", tmp_path / "fixtures"))
    out_dir = tmp_path / "delft3d_public_wua"

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--cache-dir",
            str(cache_dir),
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        cwd=repo,
    )

    summary = pd.read_csv(out_dir / "wua_summary.csv")
    report = (out_dir / "REPORT.md").read_text(encoding="utf-8")

    assert len(summary) == 5
    assert summary["n_cells"].eq(1152).all()
    assert summary["wua_m2"].max() > 0.0
    assert summary["area_m2"].eq(72.0).all()
    assert (out_dir / "habitat_cells.parquet").exists()
    assert (out_dir / "hydraulic_cells.parquet").exists()
    assert (out_dir / "wua_hmu.csv").exists()
    assert (out_dir / "wua_timeseries.png").stat().st_size > 0
    assert "Synthetic demonstration curve" in report
