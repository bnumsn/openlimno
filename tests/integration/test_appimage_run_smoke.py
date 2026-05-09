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


FIXTURE = Path(__file__).resolve().parent / "fixtures/lemhi-tiny"


@pytest.fixture(scope="module")
def built_case(tmp_path_factory):
    """Use a frozen 5-node Lemhi reach checked into the repo. Frozen
    rather than rebuilt each run because (a) Overpass downtime / rate
    limits would make CI flaky, (b) the fixture is 52 KB so caching
    doesn't matter, (c) we need the test to be hermetic when network
    is unavailable.

    The fixture is a copy because Case.run() writes to <case>/out/.
    """
    if not (FIXTURE / "case.yaml").is_file():
        pytest.skip(f"fixture missing at {FIXTURE} — run setup script")
    out = tmp_path_factory.mktemp("appimage-smoke")
    shutil.copytree(FIXTURE, out, dirs_exist_ok=True)
    yield out


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
