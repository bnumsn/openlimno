"""OpenLimno Studio main window — feature-parity with the QGIS plugin.

Wires gui_core.Controller to a standalone PyQt5 window:
- File menu: Open GeoPackage, Quit
- Tools menu / toolbar: Build from OSM, Run case, Click cross-section,
  Open hydraulic results, Open WUA-Q, Plot cross-section
- Navigation toolbar: Pan, Zoom in/out, Zoom to full extent
- OSM basemap auto-loaded on first start
- QgsMessageBar above canvas + cursor-coords status indicator
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsLayerTreeModel,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import (
    QgsLayerTreeMapCanvasBridge,
    QgsLayerTreeView,
    QgsMapCanvas,
    QgsMapToolPan,
    QgsMapToolZoom,
    QgsMessageBar,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QActionGroup,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from openlimno.gui_core import Controller


class _StatusBarIfaceShim:
    """Adapts QStatusBar.showMessage / clearMessage to the iface-shaped API.

    QGIS iface.statusBarIface() returns a QgsStatusBar wrapper; we expose
    the same two methods Controller uses so it Just Works.
    """

    def __init__(self, qstatus_bar):
        self._sb = qstatus_bar

    def showMessage(self, msg, timeout=0):  # noqa: N802 (Qt API)
        self._sb.showMessage(msg, timeout)

    def clearMessage(self):  # noqa: N802 (Qt API)
        self._sb.clearMessage()


class MainWindow(QMainWindow):
    """OpenLimno Studio top-level window. Implements gui_core.Host."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenLimno Studio")
        self.resize(1280, 800)
        self._set_window_icon()

        # ---- Project CRS (default to Web Mercator so OSM basemap aligns)
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

        # ---- Central area: message bar + canvas stacked vertically
        central = QWidget(self)
        v = QVBoxLayout(central); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        self._message_bar = QgsMessageBar(central)
        v.addWidget(self._message_bar)
        self.canvas = QgsMapCanvas(central)
        self.canvas.setCanvasColor(Qt.white)
        self.canvas.enableAntiAliasing(True)
        self.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        v.addWidget(self.canvas, 1)
        self.setCentralWidget(central)

        # ---- Layer tree dock
        root = QgsProject.instance().layerTreeRoot()
        self.layer_tree_view = QgsLayerTreeView(self)
        self.layer_tree_model = QgsLayerTreeModel(root, self)
        for flag in (
            QgsLayerTreeModel.AllowNodeChangeVisibility,
            QgsLayerTreeModel.AllowNodeReorder,
            QgsLayerTreeModel.AllowNodeRename,
        ):
            self.layer_tree_model.setFlag(flag)
        self.layer_tree_view.setModel(self.layer_tree_model)
        self.layer_tree_view.defaultActions()  # lazily instantiate context-menu actions
        self.bridge = QgsLayerTreeMapCanvasBridge(root, self.canvas, self)

        dock = QDockWidget("Layers", self)
        dock.setObjectName("LayersDock")
        dock.setWidget(self.layer_tree_view)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        # ---- Status bar: cursor coords + project CRS
        self._coord_label = QLabel("—")
        self._coord_label.setMinimumWidth(220)
        self.statusBar().addPermanentWidget(self._coord_label)
        self._crs_label = QLabel(f"CRS: {QgsProject.instance().crs().authid()}")
        self.statusBar().addPermanentWidget(self._crs_label)
        self.canvas.xyCoordinates.connect(self._on_xy_coords)

        # ---- Status bar shim for Controller
        self._status_bar_iface = _StatusBarIfaceShim(self.statusBar())

        # ---- Controller (gui_core)
        self.ctl = Controller(self)

        # ---- Build menus + toolbars
        self._nav_tools = {}  # cached map tools so they're not GC'd
        self._build_menus_and_toolbars()

        # ---- Default basemap (OSM tiles) — loaded after canvas exists
        self._add_osm_basemap()

        # Default to the Pan tool for a sensible initial mode
        self.canvas.setMapTool(self._nav_tools["pan"])

    # ------------------------------------------------------------------
    # gui_core.Host protocol implementation
    # ------------------------------------------------------------------
    def main_window(self):
        return self

    def map_canvas(self):
        return self.canvas

    def message_bar(self):
        return self._message_bar

    def status_bar(self):
        return self._status_bar_iface

    # ------------------------------------------------------------------
    def _on_xy_coords(self, point) -> None:
        self._coord_label.setText(f"{point.x():.6f}, {point.y():.6f}")

    # ------------------------------------------------------------------
    # Menus + toolbars
    # ------------------------------------------------------------------
    def _build_menus_and_toolbars(self) -> None:
        mb = self.menuBar()

        # --- File ---
        m_file = mb.addMenu("&File")
        a_open_gpkg = QAction("Open GeoPackage…", self)
        a_open_gpkg.setShortcut("Ctrl+O")
        a_open_gpkg.triggered.connect(self.open_geopackage)
        m_file.addAction(a_open_gpkg)
        a_open_proj = QAction("Open QGIS project (.qgz)…", self)
        a_open_proj.setShortcut("Ctrl+Shift+O")
        a_open_proj.triggered.connect(self.open_project)
        m_file.addAction(a_open_proj)
        m_file.addSeparator()
        a_quit = QAction("Quit", self)
        a_quit.setShortcut("Ctrl+Q")
        a_quit.triggered.connect(self.close)
        m_file.addAction(a_quit)

        # --- View / Navigation toolbar (pan/zoom) ---
        nav_tb = QToolBar("Navigation", self)
        nav_tb.setObjectName("NavigationToolbar")
        self.addToolBar(Qt.TopToolBarArea, nav_tb)

        # Build navigation tools in a QActionGroup so only one's checked
        nav_group = QActionGroup(self)
        nav_group.setExclusive(True)

        a_pan = QAction("Pan", self); a_pan.setCheckable(True); a_pan.setChecked(True)
        self._nav_tools["pan"] = QgsMapToolPan(self.canvas)
        a_pan.triggered.connect(lambda: self.canvas.setMapTool(self._nav_tools["pan"]))
        nav_group.addAction(a_pan); nav_tb.addAction(a_pan)

        a_zin = QAction("Zoom in", self); a_zin.setCheckable(True)
        self._nav_tools["zin"] = QgsMapToolZoom(self.canvas, False)
        a_zin.triggered.connect(lambda: self.canvas.setMapTool(self._nav_tools["zin"]))
        nav_group.addAction(a_zin); nav_tb.addAction(a_zin)

        a_zout = QAction("Zoom out", self); a_zout.setCheckable(True)
        self._nav_tools["zout"] = QgsMapToolZoom(self.canvas, True)
        a_zout.triggered.connect(lambda: self.canvas.setMapTool(self._nav_tools["zout"]))
        nav_group.addAction(a_zout); nav_tb.addAction(a_zout)

        nav_tb.addSeparator()

        a_full = QAction("Zoom to full extent", self)
        a_full.setShortcut("Ctrl+0")
        a_full.triggered.connect(self._zoom_full_extent)
        nav_tb.addAction(a_full)

        a_zlayer = QAction("Zoom to selected layer", self)
        a_zlayer.triggered.connect(self._zoom_to_selected_layer)
        nav_tb.addAction(a_zlayer)

        # --- View menu (mirrors nav toolbar) ---
        m_view = mb.addMenu("&View")
        for a in (a_pan, a_zin, a_zout, a_full, a_zlayer):
            m_view.addAction(a)

        # --- Tools menu + OpenLimno toolbar (delegate to Controller) ---
        ol_tb = QToolBar("OpenLimno", self)
        ol_tb.setObjectName("OpenLimnoToolbar")
        self.addToolBar(Qt.TopToolBarArea, ol_tb)
        m_tools = mb.addMenu("&Tools")

        def _ol_action(text, slot, *, checkable=False, on_toolbar=True):
            a = QAction(text, self)
            if checkable:
                a.setCheckable(True)
                a.triggered.connect(slot)  # slot takes the bool checked arg
            else:
                a.triggered.connect(lambda _checked=False: slot())
            m_tools.addAction(a)
            if on_toolbar:
                ol_tb.addAction(a)
            return a

        _ol_action("🆕 Build case from OSM…", self.ctl.build_case_from_osm)
        _ol_action("▶ Run case…", self.ctl.run_case)
        a_pick = _ol_action("Click cross-section to view profile",
                              self.ctl.activate_pick_tool, checkable=True)
        self.ctl._pick_action = a_pick
        m_tools.addSeparator()
        _ol_action("Open hydraulic results (.nc)…", self.ctl.open_hydraulic_nc,
                     on_toolbar=False)
        _ol_action("Open WUA-Q curve…", self.ctl.open_wua_q, on_toolbar=False)
        _ol_action("Plot cross-section profile…", self.ctl.plot_cross_section,
                     on_toolbar=False)

        # --- Help ---
        m_help = mb.addMenu("&Help")
        a_about = QAction("About OpenLimno Studio", self)
        a_about.triggered.connect(self._show_about)
        m_help.addAction(a_about)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _show_about(self) -> None:
        QMessageBox.about(
            self, "OpenLimno Studio",
            "<b>OpenLimno Studio</b><br>"
            "Open-source aquatic ecosystem modeling — successor to "
            "PHABSIM / River2D / FishXing.<br><br>"
            "Built on PyQGIS. Source: https://github.com/openlimno/openlimno",
        )

    def _zoom_full_extent(self) -> None:
        extent = QgsRectangle()
        extent.setMinimal()
        for lyr in QgsProject.instance().mapLayers().values():
            if not lyr.extent().isEmpty():
                extent.combineExtentWith(lyr.extent())
        if not extent.isEmpty():
            self.canvas.setExtent(extent)
            self.canvas.refresh()

    def _zoom_to_selected_layer(self) -> None:
        idx = self.layer_tree_view.currentIndex()
        if not idx.isValid():
            self._message_bar.pushInfo("OpenLimno", "Select a layer in the panel first.")
            return
        node = self.layer_tree_model.index2node(idx)
        try:
            lyr = node.layer()
        except Exception:
            return
        if lyr is None or lyr.extent().isEmpty():
            return
        self.canvas.setExtent(lyr.extent())
        self.canvas.refresh()

    def open_geopackage(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GeoPackage",
            str(Path.home() / "openlimno-workspace"),
            "GeoPackage (*.gpkg)",
        )
        if not path:
            return
        self.load_geopackage(Path(path))

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open QGIS project",
            str(Path.home() / "openlimno-workspace"),
            "QGIS project (*.qgz *.qgs)",
        )
        if not path:
            return
        ok = QgsProject.instance().read(path)
        if not ok:
            QMessageBox.warning(self, "OpenLimno Studio",
                                  f"Failed to open project: {path}")
            return
        self._zoom_full_extent()

    def load_geopackage(self, gpkg: Path) -> int:
        probe = QgsVectorLayer(str(gpkg), "probe", "ogr")
        if not probe.isValid():
            QMessageBox.warning(self, "OpenLimno Studio",
                                  f"Could not open {gpkg}.")
            return 0
        added = 0
        for sl in probe.dataProvider().subLayers():
            parts = sl.split("!!::!!")
            if len(parts) < 2:
                continue
            name = parts[1]
            uri = f"{gpkg}|layername={name}"
            lyr = QgsVectorLayer(uri, name, "ogr")
            if lyr.isValid():
                QgsProject.instance().addMapLayer(lyr)
                added += 1
        if added > 0:
            self._zoom_full_extent()
        self.statusBar().showMessage(f"Loaded {added} layer(s) from {gpkg.name}", 5000)
        return added

    # ------------------------------------------------------------------
    def _set_window_icon(self) -> None:
        """Find and apply the bundled brand icon. Looks in the PyInstaller
        bundle's _internal/ first, then falls back to the dev repo path."""
        candidates = [
            Path(getattr(sys, "_MEIPASS", "")) / "icons/openlimno-studio.png",
            Path(__file__).resolve().parents[3] / "packaging/icons/openlimno-studio.png",
        ]
        for cand in candidates:
            if cand.is_file():
                self.setWindowIcon(QIcon(str(cand)))
                return

    def _add_osm_basemap(self) -> None:
        """Load OSM XYZ tiles as a default basemap if not already present."""
        from qgis.core import QgsApplication, QgsProviderRegistry

        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == "OpenStreetMap":
                return
        url = (
            "type=xyz&"
            "url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&"
            "zmax=19&zmin=0"
        )
        layer = QgsRasterLayer(url, "OpenStreetMap", "wms")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            extent = layer.extent()
            if not extent.isEmpty():
                self.canvas.setExtent(extent)
                self.canvas.refresh()
            return
        # Diagnostic: surface why the layer rejected itself
        providers = sorted(QgsProviderRegistry.instance().providerList())
        plugin_path = QgsApplication.pluginPath()
        err = layer.error().summary() if layer.error() else "(no error obj)"
        self._message_bar.pushWarning(
            "OpenLimno",
            f"OSM basemap failed: {err} | "
            f"pluginPath={plugin_path} | "
            f"providers={len(providers)}: {','.join(providers[:8])}…",
        )
