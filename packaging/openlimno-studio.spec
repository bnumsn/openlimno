# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OpenLimno Studio (Linux AppImage / onedir).

Bundles:
- openlimno + openlimno.gui_core + openlimno.studio
- PyQGIS bindings (/usr/lib/python3/dist-packages/qgis)
- QGIS C++ libraries (/usr/lib/libqgis_*.so*)
- Qt5 platform plugins (xcb, offscreen)
- PROJ / GDAL data directories

Build:    pyinstaller packaging/openlimno-studio.spec
Run:      dist/openlimno-studio/openlimno-studio

BUILD-ENVIRONMENT REQUIREMENTS
==============================
This spec assumes the build host has:
  * QGIS apt package (provides /usr/lib/python3/dist-packages/qgis,
    /usr/lib/libqgis_*.so*, /usr/lib/qgis/plugins/, /usr/share/qgis/);
  * Qt5 system packages (PyQt5, qtbase5-dev with platform plugins);
  * a Python venv with editable openlimno install + pyinstaller +
    matching versions of jsonschema 4.18+, numpy 2.x, scipy.

We deliberately keep ``/usr/lib/python3/dist-packages`` OFF ``pathex``
to prevent PyInstaller from collecting an outdated jsonschema 4.10
alongside the venv's modern 4.26 (the two have incompatible internal
APIs and the bundle ends up with a broken hybrid).

PyQt5 is still resolved transitively through openlimno.studio's
``from qgis.PyQt.QtWidgets import ...`` imports, which PyInstaller
analyses normally because openlimno is on pathex.
"""
import glob
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# --- repo root + python sys-paths -----------------------------------------
# Resolve relative to this .spec file so the build runs from any checkout
# (developer machines, CI runners, etc.) — not hardcoded to one path.
REPO_ROOT = Path(SPEC).resolve().parent.parent  # type: ignore[name-defined]
SYS_DIST = "/usr/lib/python3/dist-packages"

# --- discover binaries ----------------------------------------------------
binaries = []

# numpy 2.x bug: PyInstaller's hook misses numpy._core entirely. Without
# collect_all we ship a numpy/ that ImportError's on `numpy.core` access.
# Same for scipy — its 2026 layout has nontrivial submodules the default
# hook can't enumerate from import statements alone.
for pkg in ("numpy", "scipy", "jsonschema", "matplotlib", "shapely",
              "pyproj", "netCDF4", "pyarrow", "rfc3987_syntax",
              "referencing", "jsonschema_specifications"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    binaries += pkg_binaries
# QGIS C++ shared libraries
for so in glob.glob("/usr/lib/libqgis*.so*"):
    binaries.append((so, "."))
# Qt5 platform plugins (xcb is the one a user sees; offscreen is for tests)
for sub in ("platforms", "imageformats", "iconengines",
              "sqldrivers", "styles", "printsupport"):
    for so in glob.glob(f"/usr/lib/x86_64-linux-gnu/qt5/plugins/{sub}/*.so"):
        binaries.append((so, f"qt5_plugins/{sub}"))
# QGIS provider / auth-method / processing plugins. We bundle them at the
# path that QgsApplication's prefix-derived lookup uses post-initQgis():
#   <prefix>/lib/qgis/plugins
# so we don't need to override pluginPath() at runtime (which initQgis()
# silently reverts anyway).
for so in glob.glob("/usr/lib/qgis/plugins/*.so"):
    binaries.append((so, "qgis_root/lib/qgis/plugins"))

# --- discover data --------------------------------------------------------
datas = [
    # Resources sit at <prefix>/share/qgis (svg/, i18n/, resources/) — matches
    # the path QGIS computes from QgsApplication.prefixPath() after init.
    ("/usr/share/qgis", "qgis_root/share/qgis"),
    ("/usr/share/proj", "proj"),
    ("/usr/share/gdal", "gdal"),
    # WEDM JSON-Schemas — Case.from_yaml validates against these via
    # importlib.resources, so they MUST land inside the bundle. Without
    # this, every Run case action fails at validation.
    (str(REPO_ROOT / "src/openlimno/wedm/schemas"),
        "openlimno/wedm/schemas"),
    # Brand icon (loaded by MainWindow._set_window_icon at runtime)
    (str(REPO_ROOT / "packaging/icons/openlimno-studio.png"), "icons"),
    (str(REPO_ROOT / "packaging/icons/openlimno-studio.svg"), "icons"),
]
# Bundle the data files for numpy / scipy / jsonschema / etc. that
# collect_all finds — typestubs, JSON schemas, .pxd / .pyx files.
for pkg in ("numpy", "scipy", "jsonschema", "matplotlib", "shapely",
              "pyproj", "netCDF4", "pyarrow", "rfc3987_syntax",
              "referencing", "jsonschema_specifications"):
    pkg_datas, _, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
# QGIS Python bindings (.py + .pyi); .so files come via binaries below
for f in glob.glob(f"{SYS_DIST}/qgis/**/*.py", recursive=True):
    rel = Path(f).relative_to(SYS_DIST)
    datas.append((f, str(rel.parent)))
# QGIS Python C-extension .so's
for f in glob.glob(f"{SYS_DIST}/qgis/_*.so"):
    rel = Path(f).relative_to(SYS_DIST)
    binaries.append((f, str(rel.parent)))
for f in glob.glob(f"{SYS_DIST}/qgis/PyQt/*.so"):
    rel = Path(f).relative_to(SYS_DIST)
    binaries.append((f, str(rel.parent)))

# --- hidden imports -------------------------------------------------------
hiddenimports = [
    "qgis",
    "qgis.core",
    "qgis.gui",
    "qgis.analysis",
    "qgis.PyQt",
    "qgis.PyQt.QtCore",
    "qgis.PyQt.QtGui",
    "qgis.PyQt.QtWidgets",
    "qgis.PyQt.uic",
    "qgis.utils",
    # OpenLimno modules used by Controller
    "openlimno",
    "openlimno.case",                       # Case.from_yaml + run()
    "numpy._core",                          # numpy 2.x — hook drops this
    "numpy._core._multiarray_tests",
    "numpy._core._multiarray_umath",
    "openlimno.hydro",
    "openlimno.hydro.builtin_1d",           # Manning solver (brentq)
    "openlimno.habitat",
    "openlimno.wedm",                       # JSON-schema validation
    "openlimno.gui_core",
    "openlimno.gui_core.controller",
    "openlimno.studio",
    "openlimno.studio.main_window",
    "openlimno.preprocess",
    "openlimno.preprocess.osm_builder",
    # Solver dependency: Case.run() → builtin_1d → scipy.optimize.brentq
    "scipy.optimize",
    # Heavy science deps
    "matplotlib",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qtagg",
    "netCDF4",
    "pandas",
    "pyarrow",
    "pyarrow.parquet",
    "shapely",
    "shapely.geometry",
    "shapely.ops",
    "yaml",
    "requests",
    "xarray",
]
# Append the long submodule list collect_all discovered for the heavy
# science deps. Done lazily at the end so the hand-curated list above
# stays readable and we still get full submodule coverage.
for _pkg in ("numpy", "scipy", "jsonschema", "matplotlib", "shapely",
              "pyproj", "netCDF4", "pyarrow", "rfc3987_syntax",
              "referencing", "jsonschema_specifications"):
    _, _, _h = collect_all(_pkg)
    hiddenimports += _h

a = Analysis(
    [str(REPO_ROOT / "src/openlimno/studio/__main__.py")],
    # Do NOT include /usr/lib/python3/dist-packages here. It contains the
    # apt-installed jsonschema 4.10 alongside the venv's 4.26, and
    # PyInstaller mixes them, producing a bundle whose .py and _utils
    # don't agree. We get qgis bindings via the runtime hook instead.
    pathex=[str(REPO_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(REPO_ROOT / "packaging/runtime_hook.py")],
    excludes=[
        # Standard-library noise — keep unittest (numpy.testing imports it)
        "tkinter", "pydoc_data",
        # Big unused packages found in system Python by accident
        "wx", "PyQt6", "PySide2", "PySide6",
        "boto3", "botocore", "s3fs", "fsspec", "aiohttp", "aiohttp_retry",
        "zstandard", "uvloop", "fastavro", "numcodecs",
        # NOTE: do NOT exclude any scipy submodule — scipy uses lazy
        # __getattr__ that pulls in unexpected siblings (e.g. scipy.spatial
        # via _ckdtree gets imported through scipy.optimize internals on
        # some builds). One bad exclude → AppImage can't even reach the
        # solver. The full scipy is ~30 MB; not worth the fragility.
        "rasterio",
        "black", "blib2to3", "mypy", "isort", "ruff",
        "jupyter", "jupyterlab", "ipython", "IPython", "notebook",
        "sphinx", "docutils", "alabaster",
        "pytest", "_pytest", "hypothesis",
        "torch", "tensorflow", "jax",
        "sklearn", "skimage",
        # GTK / GObject — pulled in via matplotlib backends but unused here
        "gi", "gi.repository", "cairo", "Pango", "HarfBuzz",
        "matplotlib.backends.backend_gtk3agg",
        "matplotlib.backends.backend_gtk4agg",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="openlimno-studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,        # keep stdout/stderr visible during early days
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="openlimno-studio",
)
