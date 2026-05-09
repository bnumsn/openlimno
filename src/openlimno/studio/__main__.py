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


def _smoke_run_case_in_bundle(case_yaml: str) -> int:
    """Headless: load + run a case using whatever solver path the BUNDLE
    actually has access to. Catches module-exclusion regressions
    (scipy.optimize, schemas) that don't show up in dev-venv tests."""
    _ensure_qgis_importable()
    try:
        from openlimno.case import Case
        case = Case.from_yaml(case_yaml)
        result = case.run()
        print(f"SMOKE_OK: {result.summary()}", flush=True)
        return 0
    except Exception:
        import traceback
        print("SMOKE_FAIL:", flush=True)
        traceback.print_exc()
        return 1


def main() -> int:
    # Bundle smoke-test mode: run a case headless and exit. Used by the
    # release-time test that proves the AppImage can actually solve a
    # case (the way scipy.optimize + WEDM schema bundling regressions
    # got past v0.1.0-alpha.2).
    if len(sys.argv) >= 3 and sys.argv[1] == "--smoke-run-case":
        return _smoke_run_case_in_bundle(sys.argv[2])

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
