"""Verify the bundled AppImage can actually run a case end-to-end.

This catches the class of regression that v0.1.0-alpha.2 shipped with —
PyInstaller exclude lists and missing collect_all calls broke the
solver path inside the bundle while the dev-venv tests stayed green.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APPIMAGE = REPO / "OpenLimnoStudio-x86_64.AppImage"
DIST_BIN = REPO / "dist/openlimno-studio/openlimno-studio"


@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Build a tiny Lemhi-area case via the dev path; reused for all
    bundle-execution tests below."""
    pytest.importorskip("openlimno.preprocess.osm_builder")
    from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case

    out = tmp_path_factory.mktemp("appimage-smoke")
    spec = OSMCaseSpec(
        bbox=(-113.95, 44.92, -113.85, 44.98),
        n_sections=11, reach_length_m=1000,
    )
    build_case(spec, out)
    yield out
    shutil.rmtree(out, ignore_errors=True)


def _run_smoke(executable: Path, case_yaml: Path) -> str:
    """Invoke the bundle's --smoke-run-case mode and return stdout."""
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    env["QT_QPA_PLATFORM"] = "offscreen"
    r = subprocess.run(
        [str(executable), "--smoke-run-case", str(case_yaml)],
        env=env, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise AssertionError(
            f"bundle exited {r.returncode}\n"
            f"stdout:\n{r.stdout[-1000:]}\n"
            f"stderr:\n{r.stderr[-1500:]}"
        )
    return r.stdout


@pytest.mark.skipif(not DIST_BIN.is_file(),
                     reason="onedir bundle not built (run pyinstaller first)")
def test_onedir_bundle_runs_case(built_case):
    """The PyInstaller onedir bundle must run a case successfully."""
    out = _run_smoke(DIST_BIN, built_case / "case.yaml")
    assert "SMOKE_OK" in out, out
    assert (built_case / "out/hydraulics.nc").is_file()


@pytest.mark.skipif(not APPIMAGE.is_file(),
                     reason="AppImage not built (run build_appimage.sh first)")
def test_appimage_runs_case(built_case):
    """The single-file .AppImage must run a case successfully."""
    out = _run_smoke(APPIMAGE, built_case / "case.yaml")
    assert "SMOKE_OK" in out, out
    assert (built_case / "out/hydraulics.nc").is_file()
