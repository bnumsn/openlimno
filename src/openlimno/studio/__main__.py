"""Entry point: ``python -m openlimno.studio``.

Bootstraps PyQGIS as a library (no QGIS app process), then hands off to
the main window. Works whether launched from the system Python (which
has qgis bindings on the path) or from a virtualenv (we splice the
system dist-packages so qgis can be imported regardless).
"""
from __future__ import annotations

import os
import sys


def _ensure_qgis_importable() -> None:
    """If launched from a venv that lacks QGIS, splice the system path.

    QGIS Python bindings live in /usr/lib/python3/dist-packages/qgis on
    Debian/Ubuntu; user venvs typically don't see them. Detection is
    cheap: if `import qgis` already works, do nothing.
    """
    try:
        import qgis  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    # Probe common system paths. APPEND (not insert(0)) so any newer
    # versions of shared deps (jsonschema, etc.) in the active venv keep
    # priority over the apt-installed system copies that live alongside
    # qgis in dist-packages.
    for cand in (
        "/usr/lib/python3/dist-packages",
        "/usr/lib/python3.12/dist-packages",
        "/usr/lib/python3.11/dist-packages",
    ):
        if os.path.isdir(os.path.join(cand, "qgis")):
            sys.path.append(cand)
            return


def main() -> int:
    _ensure_qgis_importable()

    from qgis.core import QgsApplication
    from qgis.PyQt.QtWidgets import QApplication

    # Prefix path tells QGIS where its resources (svg/, i18n/, ...) live.
    # `/usr` on Debian; bundled installers will override this.
    prefix = os.environ.get("QGIS_PREFIX_PATH", "/usr")
    QgsApplication.setPrefixPath(prefix, True)

    qgs = QgsApplication([], True)  # gui_enabled=True
    qgs.setApplicationName("OpenLimno Studio")
    qgs.setOrganizationName("OpenLimno")
    qgs.initQgis()
    try:
        from openlimno.studio.main_window import MainWindow
        win = MainWindow()
        win.show()
        rc = qgs.exec_()
    finally:
        qgs.exitQgis()
    return rc


if __name__ == "__main__":
    sys.exit(main())
