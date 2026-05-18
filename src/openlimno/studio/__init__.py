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
