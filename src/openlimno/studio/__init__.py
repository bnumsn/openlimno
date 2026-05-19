"""OpenLimno Studio — standalone desktop application.

Embeds PyQGIS map canvas + layer tree inside a branded PyQt5 window.
Launched via ``python -m openlimno.studio``.

The v2.3.0 :mod:`.headless` module ships the case-run + plotting
surface that doesn't need QGIS — used by Studio's GUI controller,
by ``openlimno wua-q --plot``, and by CI tests that need to exercise
the run path without a running event loop.

Architecture: see /home/user/.claude/projects/.../memory/project_studio.md
(strategy: PyQt5 + PyQGIS-as-library + bundled installer; QGIS plugin
deprecated after Studio 1.0).
"""

# v3.1.0 R14-2 (claude): force the matplotlib Agg backend at PACKAGE
# import time, not per-function. The v3.0.0 attempt in plot_wua_q
# only worked if NOTHING earlier in the Studio process had already
# imported matplotlib.pyplot — any plugin / re-export / qgis bootstrap
# would defeat it. Setting Agg here, before any submodule's import,
# is the only way to win the race for QThread-rendered plots.
#
# Always call use("Agg") — matplotlib only honors it if pyplot
# hasn't been imported and locked a backend yet. force=True
# overrides even a previously-set backend so a parent process that
# accidentally chose Tk/Cocoa can't sabotage Studio's QThread render.
# This is safe in our use case because Studio + headless are the
# only consumers of pyplot in this codebase (no notebook contract).
import matplotlib  # noqa: PLC0415  — package-init backend lock

matplotlib.use("Agg", force=True)

from .headless import (
    HeadlessRunResult,
    plot_wua_q,
    run_case_with_plots,
)

__all__ = [
    "HeadlessRunResult",
    "plot_wua_q",
    "run_case_with_plots",
]
