"""OpenLimno QGIS plugin — thin shim over openlimno.gui_core.

All handler logic lives in ``openlimno.gui_core.Controller``; this file
only:
- declares menu / toolbar entries for QGIS,
- adapts QGIS ``iface`` to the ``Host`` protocol gui_core expects.

The plugin is in maintenance mode: new features land in OpenLimno Studio
(``openlimno.studio``) and are picked up here automatically via the
shared Controller. See memory/project_studio.md.
"""
from __future__ import annotations

import os
import sys
from typing import Any


def _ensure_openlimno_importable() -> None:
    """Splice the OpenLimno repo onto sys.path if it isn't already.

    QGIS runs its own embedded Python; the user's pip-installed
    openlimno may not be visible. Probe the typical dev install
    locations.
    """
    try:
        import openlimno.gui_core  # noqa: F401
        return
    except ImportError:
        pass
    for cand in (
        "/mnt/data/openlimno/src",
        os.path.expanduser("~/openlimno/src"),
        os.path.expanduser("~/openlimno-env/lib/python3.12/site-packages"),
        os.path.expanduser("~/openlimno-env/lib/python3.11/site-packages"),
    ):
        if os.path.isdir(os.path.join(cand, "openlimno", "gui_core")):
            sys.path.insert(0, cand)
            return


class _PluginHost:
    """Adapter from QGIS iface to gui_core.Host protocol."""

    def __init__(self, iface):
        self._iface = iface

    def main_window(self):
        return self._iface.mainWindow()

    def map_canvas(self):
        return self._iface.mapCanvas()

    def message_bar(self):
        return self._iface.messageBar()

    def status_bar(self):
        return self._iface.statusBarIface()


class OpenLimnoPlugin:
    """Plugin object instantiated by QGIS at startup."""

    def __init__(self, iface):
        self.iface = iface
        self.actions: list[Any] = []
        self.menu = "&OpenLimno"
        _ensure_openlimno_importable()
        from openlimno.gui_core import Controller
        self.ctl = Controller(_PluginHost(iface))

    # ------------------------------------------------------------------
    def initGui(self) -> None:  # noqa: N802 (QGIS API)
        try:
            from qgis.PyQt.QtGui import QIcon
            from qgis.PyQt.QtWidgets import QAction
        except ImportError:
            return

        icon = QIcon()

        def _menu_only(text, slot):
            a = QAction(icon, text, self.iface.mainWindow())
            a.triggered.connect(slot)
            self.iface.addPluginToMenu(self.menu, a)
            self.actions.append(a)
            return a

        def _toolbar_too(text, slot):
            a = _menu_only(text, slot)
            self.iface.addToolBarIcon(a)
            return a

        _toolbar_too("Open OpenLimno hydraulic results…", self.ctl.open_hydraulic_nc)
        _menu_only("Open WUA-Q curve…", self.ctl.open_wua_q)
        _menu_only("Plot cross-section profile…", self.ctl.plot_cross_section)

        a_pick = QAction(icon, "Click cross-section to view profile",
                            self.iface.mainWindow())
        a_pick.setCheckable(True)
        a_pick.triggered.connect(self.ctl.activate_pick_tool)
        self.iface.addPluginToMenu(self.menu, a_pick)
        self.iface.addToolBarIcon(a_pick)
        self.actions.append(a_pick)
        self.ctl._pick_action = a_pick  # let controller un-check on cancel

        _toolbar_too("🆕 Build case from OSM river…", self.ctl.build_case_from_osm)
        _toolbar_too("⬇ Fetch data into case…", self.ctl.fetch_data_into_case)
        _toolbar_too("▶ Run case…", self.ctl.run_case)

    def unload(self) -> None:
        try:
            from qgis.PyQt.QtWidgets import QAction  # noqa: F401
        except ImportError:
            return
        for a in self.actions:
            self.iface.removePluginMenu(self.menu, a)
            self.iface.removeToolBarIcon(a)
        self.actions = []
