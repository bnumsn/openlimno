"""PyInstaller runtime hook: tells QGIS where its bundled resources live.

Runs *before* openlimno.studio.__main__ inside the frozen executable.
Without this, QgsApplication.setPrefixPath('/usr', True) would point at
the host system instead of the bundle.
"""
import os
import sys


def _bundle_dir() -> str:
    # PyInstaller sets sys._MEIPASS to the directory holding the bundle
    return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))


# Tell QGIS where its prefix lives. We laid out <prefix>/share/qgis (for
# svg/, i18n/, resources/) and <prefix>/lib/qgis/plugins (for provider_wms.so
# etc.) inside the bundle so QGIS' default prefix-derived lookups all work.
os.environ["QGIS_PREFIX_PATH"] = os.path.join(_bundle_dir(), "qgis_root")
# GDAL / PROJ data dirs (these live alongside qgis_root, not under it)
os.environ["GDAL_DATA"] = os.path.join(_bundle_dir(), "gdal")
os.environ["PROJ_LIB"] = os.path.join(_bundle_dir(), "proj")
# Tell Qt where to find its platform plugins inside the bundle
os.environ["QT_PLUGIN_PATH"] = os.path.join(_bundle_dir(), "qt5_plugins")
# (removed: setPluginPath() override — QGIS resets it during initQgis().
# We now rely on the prefix-derived path: <prefix>/lib/qgis/plugins,
# which the spec lays out at qgis_root/lib/qgis/plugins inside the bundle.)
