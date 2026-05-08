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
"""
import glob
import os
from pathlib import Path

block_cipher = None

# --- repo root + python sys-paths -----------------------------------------
REPO_ROOT = Path("/mnt/data/openlimno")
SYS_DIST = "/usr/lib/python3/dist-packages"

# --- discover binaries ----------------------------------------------------
binaries = []
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
]
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
    "openlimno.gui_core",
    "openlimno.gui_core.controller",
    "openlimno.studio",
    "openlimno.studio.main_window",
    "openlimno.preprocess",
    "openlimno.preprocess.osm_builder",
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

a = Analysis(
    [str(REPO_ROOT / "src/openlimno/studio/__main__.py")],
    pathex=[str(REPO_ROOT / "src"), SYS_DIST],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(REPO_ROOT / "packaging/runtime_hook.py")],
    excludes=[
        # Standard-library noise
        "tkinter", "test", "unittest", "pydoc_data",
        # Big unused packages found in system Python by accident
        "wx", "PyQt6", "PySide2", "PySide6",
        "boto3", "botocore", "s3fs", "fsspec", "aiohttp", "aiohttp_retry",
        "zstandard", "uvloop", "fastavro", "numcodecs",
        "rasterio", "scipy.io", "scipy.optimize", "scipy.signal",
        "scipy.sparse.linalg", "scipy.spatial",
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
