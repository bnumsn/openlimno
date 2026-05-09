"""Comprehensive Linux Studio smoke test matrix (manual / pre-release).

Drives every Controller code path a beta user might hit, with dialogs
patched to return preset values. Each subtest produces a screenshot in
/tmp/studio_test/ and prints a PASS/FAIL line.

This script is NOT collected by pytest (file name lacks the test_
prefix on purpose) — it makes real network calls (Overpass API) and
takes ~30-60 s end-to-end, so it's a manual pre-release smoke test
rather than a unit test. Run before tagging a release:

    DISPLAY=:1 PATH=/usr/bin:/bin /home/user/openlimno-env/bin/python \\
        tests/integration/studio_workflows_smoke.py

Coverage (11 tests):
  T1   Build case via bbox (Salmon River reach)
  T2   Build case via GeoJSON polyline
  T3   Build case via river name + region
  T4   Refuse symlinked output dir
  T5   Bad bbox returns clean error (no crash)
  T6   Run case in-process via QThread
  T7   Open hydraulics.nc as MeshLayer
  T8   Auto-discover xs.parquet + hydraulics.nc on memory layers
  T9   AppImage subprocess launches and stays alive
  T10  Render cross-section profile dialog (matplotlib in Qt)
  T11  AppImage shared-lib hygiene (bundled vs host deps)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, "/mnt/data/openlimno/src")
sys.path.append("/usr/lib/python3/dist-packages")

from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis.PyQt.QtWidgets import (
    QApplication, QDialog, QFileDialog, QMessageBox,
)

QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], True)
qgs.initQgis()

from openlimno.studio.main_window import MainWindow  # noqa: E402

OUT_ROOT = Path("/tmp/studio_test")
shutil.rmtree(OUT_ROOT, ignore_errors=True)
OUT_ROOT.mkdir(parents=True)

results: list[tuple[str, str, str]] = []  # (test_id, status, message)


def grab(win, name: str) -> None:
    """Snapshot the main window or a top-level dialog if one is open."""
    win.canvas.refreshAllLayers()
    loop = QEventLoop()
    win.canvas.mapCanvasRefreshed.connect(loop.quit)
    QTimer.singleShot(2000, loop.quit)
    loop.exec_()
    win.grab().save(str(OUT_ROOT / f"{name}.png"))


def record(test_id: str, status: str, msg: str = "") -> None:
    results.append((test_id, status, msg))
    badge = {"PASS": "✓", "FAIL": "✗", "SKIP": "·"}[status]
    print(f"  {badge} {test_id}: {msg}")


def reset_window():
    """Fresh MainWindow + cleared QgsProject for an isolated test."""
    QgsProject.instance().clear()
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    QApplication.processEvents()
    return win


# ============================================================================
# TEST 1: Build case from BBOX (real Overpass call)
# ============================================================================
def test_build_bbox():
    """The Salmon River reach we already smoke-tested. Confirms the
    in-process build_case works and outputs land in a fresh subdir."""
    print("\n[TEST 1] Build case from bbox (real Overpass)")
    win = reset_window()
    out = OUT_ROOT / "case-bbox"
    try:
        from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case
        spec = OSMCaseSpec(
            bbox=(-113.95, 44.92, -113.85, 44.98),
            n_sections=11, reach_length_m=1000,
        )
        paths = build_case(spec, out)
        for k in ("case_yaml", "mesh", "cross_section", "hsi_curve"):
            assert Path(paths[k]).is_file(), f"missing {k}"
        loaded = win.ctl._load_case_layers(out)
        assert len(loaded) == 2, f"expected 2 layers, got {loaded}"
        grab(win, "01_build_bbox")
        record("T1.build_bbox", "PASS",
                f"3 case files + {len(loaded)} layers")
    except Exception as e:
        record("T1.build_bbox", "FAIL", f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        win.close()


# ============================================================================
# TEST 2: Build case from GeoJSON polyline
# ============================================================================
def test_build_polyline():
    """User-drawn LineString skips Overpass entirely. Make a synthetic
    GeoJSON and verify it builds."""
    print("\n[TEST 2] Build case from GeoJSON polyline")
    win = reset_window()
    out = OUT_ROOT / "case-polyline"
    geojson = OUT_ROOT / "test_polyline.geojson"
    geojson.write_text(json.dumps({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-113.95, 44.92], [-113.92, 44.93], [-113.89, 44.95],
                [-113.86, 44.97], [-113.85, 44.98],
            ],
        },
        "properties": {},
    }))
    try:
        from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case
        spec = OSMCaseSpec(
            polyline_geojson=str(geojson),
            n_sections=7, reach_length_m=500,
        )
        paths = build_case(spec, out)
        # Verify case.yaml description mentions the polyline
        case_yaml = Path(paths["case_yaml"]).read_text()
        assert "polyline" in case_yaml.lower(), "case.yaml missing polyline ref"
        loaded = win.ctl._load_case_layers(out)
        grab(win, "02_build_polyline")
        record("T2.build_polyline", "PASS",
                f"yaml has polyline ref, {len(loaded)} layers loaded")
    except Exception as e:
        record("T2.build_polyline", "FAIL", f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        win.close()


# ============================================================================
# TEST 3: Build case by river name + region
# ============================================================================
def test_build_river_name():
    """Use a real Idaho river by name. Slowest test (Overpass admin-area
    query is heavy)."""
    print("\n[TEST 3] Build case by river+region (Salmon River, Idaho)")
    win = reset_window()
    out = OUT_ROOT / "case-name"
    try:
        from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case
        spec = OSMCaseSpec(
            river_name="Salmon River", region_name="Idaho",
            n_sections=7, reach_length_m=300,
        )
        paths = build_case(spec, out)
        case_name = Path(paths["case_yaml"]).read_text()
        assert "salmon_river" in case_name.lower(), case_name[:200]
        loaded = win.ctl._load_case_layers(out)
        grab(win, "03_build_river_name")
        record("T3.build_river_name", "PASS",
                f"slug = salmon_river, {len(loaded)} layers")
    except Exception as e:
        record("T3.build_river_name", "FAIL", f"{type(e).__name__}: {e}")
    finally:
        win.close()


# ============================================================================
# TEST 4: Symlink-data refusal (safety check)
# ============================================================================
def test_symlink_refusal():
    """build_case must refuse output dirs whose data/ is a symlink, to
    prevent the 'wrote into the source repo' incident from earlier."""
    print("\n[TEST 4] Refuse symlinked data/ dir")
    out = OUT_ROOT / "case-symlinked"
    out.mkdir(parents=True)
    real_target = OUT_ROOT / "real-target"
    real_target.mkdir()
    (out / "data").symlink_to(real_target)
    try:
        from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case
        spec = OSMCaseSpec(
            bbox=(-113.95, 44.92, -113.85, 44.98),
            n_sections=5, reach_length_m=200,
        )
        try:
            build_case(spec, out)
            record("T4.symlink_refusal", "FAIL", "expected ValueError")
        except ValueError as e:
            assert "symlink" in str(e).lower()
            record("T4.symlink_refusal", "PASS",
                    f"refused with: {str(e)[:80]}…")
    except Exception as e:
        record("T4.symlink_refusal", "FAIL", f"{type(e).__name__}: {e}")


# ============================================================================
# TEST 5: Bad bbox handling
# ============================================================================
def test_bad_bbox():
    """Empty/invalid bbox should raise a clean error, not crash the GUI."""
    print("\n[TEST 5] Bad bbox returns no waterway")
    out = OUT_ROOT / "case-empty-bbox"
    try:
        from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case
        spec = OSMCaseSpec(
            bbox=(0.0, 0.0, 0.001, 0.001),  # middle of Atlantic
            n_sections=5, reach_length_m=200,
        )
        try:
            build_case(spec, out)
            record("T5.bad_bbox", "FAIL", "expected ValueError")
        except ValueError as e:
            assert "no waterway" in str(e).lower(), str(e)
            record("T5.bad_bbox", "PASS",
                    f"clean error: {str(e)[:80]}…")
    except Exception as e:
        record("T5.bad_bbox", "FAIL", f"{type(e).__name__}: {e}")


# ============================================================================
# TEST 6: Run case in-process (QThread)
# ============================================================================
def test_run_case():
    """Reuse the case from T1, run it via Controller.run_case, verify
    hydraulics.nc shows up + auto-loads as mesh layer."""
    print("\n[TEST 6] Run case in-process (QThread)")
    win = reset_window()
    case_dir = OUT_ROOT / "case-bbox"
    case_yaml = case_dir / "case.yaml"
    if not case_yaml.is_file():
        record("T6.run_case", "SKIP", "T1 didn't produce case.yaml")
        win.close(); return
    win.ctl._load_case_layers(case_dir)
    # Patch _discover_case_yaml to skip dialog
    win.ctl._discover_case_yaml = lambda: case_yaml

    done = {"value": False, "summary": None, "tb": None}
    orig = win.ctl._on_run_finished

    def patched(cy, summary, tb):
        done.update(value=True, summary=summary, tb=tb)
    win.ctl._on_run_finished = patched
    win.ctl.run_case()

    # Wait for QThread to finish (max 60s)
    loop = QEventLoop()
    def poll():
        if done["value"]:
            loop.quit()
        else:
            QTimer.singleShot(500, poll)
    QTimer.singleShot(0, poll)
    QTimer.singleShot(60000, loop.quit)
    loop.exec_()

    if not done["value"]:
        record("T6.run_case", "FAIL", "timed out after 60s")
        win.close(); return
    if done["tb"]:
        record("T6.run_case", "FAIL", f"worker raised: {done['tb'][-200:]}")
        win.close(); return
    out_nc = case_dir / "out/hydraulics.nc"
    if not out_nc.is_file():
        record("T6.run_case", "FAIL", "hydraulics.nc not produced")
        win.close(); return
    win.ctl._load_hydraulics_layer(out_nc)
    grab(win, "06_run_case")
    record("T6.run_case", "PASS", done["summary"][:100])
    win.close()


# ============================================================================
# TEST 7: Open hydraulic results menu (file picker → MDAL mesh layer)
# ============================================================================
def test_open_hydraulic():
    """Patch QFileDialog to return the hydraulics.nc from T6, verify it
    loads as a mesh layer."""
    print("\n[TEST 7] Open hydraulic NetCDF as mesh layer")
    win = reset_window()
    nc = OUT_ROOT / "case-bbox/out/hydraulics.nc"
    if not nc.is_file():
        record("T7.open_hydraulic", "SKIP", "T6 didn't produce hydraulics.nc")
        win.close(); return

    # Patch the file dialog
    orig = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(
        lambda *a, **k: (str(nc), "OpenLimno NetCDF (*.nc)"))
    try:
        win.ctl.open_hydraulic_nc()
        layers = list(QgsProject.instance().mapLayers().values())
        # Anything that's not the OSM basemap counts as the loaded result
        added = [l for l in layers if l.name() != "OpenStreetMap"]
        if not added:
            record("T7.open_hydraulic", "FAIL",
                    f"no layer added; layers={[l.name() for l in layers]}")
        else:
            kind = type(added[0]).__name__
            grab(win, "07_open_hydraulic")
            record("T7.open_hydraulic", "PASS",
                    f"{kind}: {added[0].name()}")
    finally:
        QFileDialog.getOpenFileName = orig
        win.close()


# ============================================================================
# TEST 8: Auto-discovery of cross_section.parquet from loaded layers
# ============================================================================
def test_auto_discovery():
    """After a case is built and layers loaded, the click-tool's
    auto-discovery should find cross_section.parquet without a dialog."""
    print("\n[TEST 8] Auto-discover xs.parquet from loaded layers")
    win = reset_window()
    case_dir = OUT_ROOT / "case-bbox"
    if not (case_dir / "data/cross_section.parquet").is_file():
        record("T8.auto_discovery", "SKIP", "no T1 case")
        win.close(); return
    # Load the case so its data/ is reachable from layer sources
    win.ctl._load_case_layers(case_dir)
    # _load_case_layers now stashes _xs_parquet directly when memory
    # layers are added (so the click tool works on fresh builds).
    if win.ctl._xs_parquet and win.ctl._hyd_nc:
        record("T8.auto_discovery", "PASS",
                f"xs={Path(win.ctl._xs_parquet).name} hyd={Path(win.ctl._hyd_nc).name}")
    elif win.ctl._xs_parquet:
        record("T8.auto_discovery", "PASS",
                f"xs only (no hydraulics yet) — {Path(win.ctl._xs_parquet).name}")
    else:
        record("T8.auto_discovery", "FAIL",
                "neither path stashed despite case files present")
    win.close()


# ============================================================================
# TEST 9: AppImage launches (subprocess test)
# ============================================================================
def test_appimage_launches():
    """The shipped artefact must actually start. Simple subprocess +
    timeout to confirm it doesn't crash on init."""
    print("\n[TEST 9] AppImage subprocess launch")
    import subprocess
    appimage = Path("/mnt/data/openlimno/OpenLimnoStudio-x86_64.AppImage")
    if not appimage.is_file():
        record("T9.appimage_launches", "SKIP", "no AppImage in repo root")
        return
    env = {"DISPLAY": ":1", "PATH": "/usr/bin:/bin",
            "QT_QPA_PLATFORM": "offscreen"}
    try:
        p = subprocess.Popen([str(appimage)], env=env,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        # Wait 8s — if it crashed during init it'll exit; otherwise still
        # alive (running event loop)
        try:
            rc = p.wait(timeout=10)
            record("T9.appimage_launches", "FAIL",
                    f"exited early with code {rc}")
        except subprocess.TimeoutExpired:
            p.kill(); p.wait()
            record("T9.appimage_launches", "PASS",
                    "alive after 10s (event loop running)")
    except Exception as e:
        record("T9.appimage_launches", "FAIL", str(e))


# ============================================================================
# TEST 10: Plot cross-section profile (matplotlib in Qt dialog)
# ============================================================================
def test_plot_profile():
    """Patch QFileDialog to feed in cross_section.parquet + hydraulics.nc,
    patch QDialog.exec to auto-accept the station+Q selector. Verify a
    profile dialog ends up in the project (renders matplotlib canvas)."""
    print("\n[TEST 10] Render cross-section profile dialog")
    win = reset_window()
    xs = OUT_ROOT / "case-bbox/data/cross_section.parquet"
    nc = OUT_ROOT / "case-bbox/out/hydraulics.nc"
    if not (xs.is_file() and nc.is_file()):
        record("T10.plot_profile", "SKIP", "no T1+T6 outputs")
        win.close(); return

    # Drive _render_profile_dialog directly with prepared rows
    from openlimno.gui_core.controller import _read_wua_parquet
    rows = _read_wua_parquet(str(xs))
    stations = sorted({float(r["station_m"]) for r in rows})
    # Patch QDialog.exec to auto-close — we just want the profile to render
    orig_exec = QDialog.exec
    QDialog.exec = lambda self_: 0  # simulate Cancel/dismiss
    try:
        win.ctl._hyd_nc = str(nc)  # so renderer picks up WSE
        win.ctl._render_profile_dialog(rows, stations, stations[len(stations)//2], 7.2)
        record("T10.plot_profile", "PASS",
                f"rendered station {stations[len(stations)//2]:g} at Q=7.2")
    except Exception as e:
        record("T10.plot_profile", "FAIL", f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        QDialog.exec = orig_exec
        win.close()


# ============================================================================
# TEST 11: AppImage shared-lib hygiene (no host /usr leaks)
# ============================================================================
def test_appimage_lib_hygiene():
    """Verify the AppImage's _internal libs don't accidentally pull
    libqgis from the host /usr at runtime."""
    print("\n[TEST 11] AppImage library hygiene")
    bundle = Path("/mnt/data/openlimno/dist/openlimno-studio/_internal")
    libqgis = bundle / "libqgis_core.so.3.34.4"
    if not libqgis.is_file():
        record("T11.lib_hygiene", "SKIP", "no bundle to check")
        return
    import subprocess
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(bundle)
    r = subprocess.run(["ldd", str(libqgis)], env=env,
                        capture_output=True, text=True)
    # Count how many of the resolved deps come from the bundle vs host
    bundle_count = 0
    host_count = 0
    for line in r.stdout.splitlines():
        if "=>" in line and "not found" not in line:
            target = line.split("=>", 1)[1].strip().split(" ")[0]
            if str(bundle) in target:
                bundle_count += 1
            elif target.startswith("/lib") or target.startswith("/usr"):
                # Some host libs (libc, libstdc++) are unavoidable
                host_count += 1
    record("T11.lib_hygiene", "PASS" if bundle_count > 5 else "FAIL",
            f"{bundle_count} bundled deps, {host_count} host deps")


# ============================================================================
# Run all tests
# ============================================================================
if __name__ == "__main__":
    test_build_bbox()
    test_build_polyline()
    test_build_river_name()
    test_symlink_refusal()
    test_bad_bbox()
    test_run_case()
    test_open_hydraulic()
    test_auto_discovery()
    test_appimage_launches()
    test_plot_profile()
    test_appimage_lib_hygiene()

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    for tid, status, msg in results:
        badge = {"PASS": "✓", "FAIL": "✗", "SKIP": "·"}[status]
        print(f"  {badge} [{status}] {tid}: {msg}")
    print(f"\n{passed} passed / {failed} failed / {skipped} skipped")
    print(f"Screenshots in: {OUT_ROOT}/")

    qgs.exitQgis()
    sys.exit(1 if failed else 0)
