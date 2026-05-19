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

# v3.1.0 R14-2 (claude): set the matplotlib Agg backend at PACKAGE
# import time so QThread-rendered Studio plots use a thread-safe
# backend.
#
# v3.3.0 R15-6 (claude): use force=False. The v3.1.0 force=True was
# a process-wide side effect — any third-party importer (notebook,
# downstream library) of openlimno.studio would silently lose their
# interactive backend. force=False respects an explicit choice
# upstream; if matplotlib hasn't picked a backend yet (the common
# Studio bootstrap path), Agg wins. If a notebook user has chosen
# Tk/Qt and then imports openlimno.studio, their choice is kept and
# the QThread render path is THEIR risk — which is the right
# trade-off vs. silently clobbering their environment.
import matplotlib  # noqa: PLC0415  — package-init backend lock

matplotlib.use("Agg", force=False)

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
