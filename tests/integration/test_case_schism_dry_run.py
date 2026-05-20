"""End-to-end test: case.run() with backend=schism + dry_run produces a
fully-populated SCHISM work_dir (real hgrid.gr3 from a UGRID-2D mesh) and
falls back to Builtin1D for habitat post-processing so that wua_q.csv is
still written. Confirms ADR-0002 dry-run path is wired end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from openlimno.case import Case

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "lemhi"


def _write_synthetic_ugrid_2d(path: Path) -> None:
    """Tiny 4-node 2-triangle UGRID-2D mesh."""
    x = np.array([0.0, 1.0, 1.0, 0.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    z = np.array([0.5, 0.4, 0.3, 0.4])
    face_nodes = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    xr.Dataset(
        data_vars={
            "mesh2d_node_x": (("node",), x),
            "mesh2d_node_y": (("node",), y),
            "mesh2d_face_nodes": (
                ("face", "vertex"),
                face_nodes,
                {"_FillValue": -1, "start_index": 0},
            ),
            "bottom_elevation": (("node",), z),
        },
        attrs={"Conventions": "UGRID-1.0"},
    ).to_netcdf(path)


def _write_case_yaml(tmp_path: Path, mesh_path: Path, dry_run: bool) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir(parents=True, exist_ok=True)
    out_dir = case_dir / "out"
    # v3.0.0: declare allowed_data_roots so the strict-by-default
    # sandbox lets us reach DATA_DIR (outside the test's tmp_path).
    yaml_text = (
        "openlimno: '0.1'\n"
        "case:\n"
        "  name: schism_dry_run\n"
        "  crs: EPSG:32612\n"
        f"  allowed_data_roots: ['{DATA_DIR}', '{mesh_path.parent}']\n"
        "mesh:\n"
        f"  uri: {mesh_path}\n"
        "data:\n"
        f"  cross_section: {DATA_DIR / 'cross_section.parquet'}\n"
        f"  hsi_curve: {DATA_DIR / 'hsi_curve.parquet'}\n"
        "hydrodynamics:\n"
        "  backend: schism\n"
        "  schism:\n"
        f"    dry_run: {str(dry_run).lower()}\n"
        "habitat:\n"
        "  species: [oncorhynchus_mykiss]\n"
        "  stages: [spawning]\n"
        "  metric: wua-q\n"
        "  composite: min\n"
        "output:\n"
        f"  dir: {out_dir}\n"
        "  formats: [csv]\n"
    )
    p = case_dir / "case.yaml"
    p.write_text(yaml_text)
    return p


@pytest.fixture
def lemhi_present() -> bool:
    return (DATA_DIR / "cross_section.parquet").exists()


def test_schism_dry_run_end_to_end(tmp_path: Path, lemhi_present: bool) -> None:
    if not lemhi_present:
        pytest.skip("Lemhi data not built")
    mesh = tmp_path / "mesh.nc"
    _write_synthetic_ugrid_2d(mesh)
    case_yaml = _write_case_yaml(tmp_path, mesh_path=mesh, dry_run=True)

    case = Case.from_yaml(case_yaml)
    res = case.run(discharges_m3s=[5.0, 12.0])

    # SCHISM work_dir is populated
    work = res.output_dir / "hydro_work_schism"
    hgrid = (work / "hgrid.gr3").read_text()
    assert "OpenLimno UGRID-derived mesh" in hgrid
    assert "placeholder" not in hgrid
    assert (work / "param.nml").exists()
    assert (work / "vgrid.in").exists()
    assert (work / "bctides.in").exists()
    assert (work / "schism.log").read_text().startswith("DRY RUN")

    # Builtin1D fallback supplied habitat results (so the run is useful in CI)
    df = pd.read_csv(res.output_dir / "wua_q.csv", comment="#")
    assert "wua_m2_oncorhynchus_mykiss_spawning" in df.columns
    assert (df["wua_m2_oncorhynchus_mykiss_spawning"] >= 0).all()

    # Warnings explicitly mention the SCHISM dry_run + fallback path.
    # 2026-05-20 round-20 codex A10 + gemini A7: the warning wording
    # was updated when the silent-fallback behavior was split into
    # dry_run-keeps-fallback vs return_code-raises. The dry-run path
    # still emits a Builtin1D-approximation warning; the precise text
    # is "dry_run=True — used Builtin1D approximation".
    joined = " ".join(res.warnings)
    assert "dry_run=True" in joined
    assert "Builtin1D approximation" in joined


def test_schism_without_executable_raises_no_silent_fallback(
    tmp_path: Path, lemhi_present: bool,
) -> None:
    """2026-05-20 round-20 codex A10 + gemini A7 (HIGH convergent): if
    SCHISM is missing AND ``dry_run`` is not set, ``Case.run`` must
    NOT silently fall back to Builtin1D — that would be a regulatory-
    defense hazard (a user requesting 2D would get 1D math + a soft
    warning). Pre-round-20 this test asserted the silent fallback; it
    is now inverted to pin the safer post-round-20 contract.
    """
    if not lemhi_present:
        pytest.skip("Lemhi data not built")
    mesh = tmp_path / "mesh.nc"
    _write_synthetic_ugrid_2d(mesh)
    case_yaml = _write_case_yaml(tmp_path, mesh_path=mesh, dry_run=False)

    case = Case.from_yaml(case_yaml)
    # If a real SCHISM binary happens to be installed, this test is moot;
    # in that case skip rather than spend minutes running a real solve.
    import shutil

    if shutil.which("pschism_TVD-VL") or shutil.which("schism"):
        pytest.skip("Real SCHISM binary present; cannot exercise the no-binary raise path")

    with pytest.raises(RuntimeError, match="SCHISM hydrodynamic run failed"):
        case.run(discharges_m3s=[5.0])
