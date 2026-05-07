"""End-to-end test: PHABSIM replication example reproduces analytic WUA."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "phabsim_replication"


def test_build_data_then_case_matches_analytic(tmp_path: Path) -> None:
    """Run build_data.py + Case.run and assert analytic agreement (≤1e-2)."""
    # Build data in-place (idempotent under examples/)
    import os as _os

    proc = subprocess.run(
        [sys.executable, str(EXAMPLE / "build_data.py")],
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": str(REPO / "src"),
            "PATH": _os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONNOUSERSITE": "1",
        },
        cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr

    expected = json.loads((EXAMPLE / "data" / "expected_wua.json").read_text())
    sys.path.insert(0, str(REPO / "src"))
    from openlimno.case import Case

    case = Case.from_yaml(EXAMPLE / "case.yaml")
    res = case.run(discharges_m3s=[0.5, 1.5, 4.0, 8.0], slope=0.001, manning_n=0.030)

    df = res.wua_q
    for Q in (0.5, 1.5, 4.0, 8.0):
        analytic = float(expected[str(Q)])
        ol = float(df.loc[df["discharge_m3s"] == Q, "wua_m2_oncorhynchus_mykiss_spawning"].iloc[0])
        rel = abs(ol - analytic) / max(analytic, 1e-9)
        assert rel < 1e-2, f"Q={Q}: rel err {rel:.2e} > 1e-2 (analytic={analytic}, ol={ol})"
