"""OpenLimno QGIS plugin: read-only viewer.

ADR-0005 Layer 1 (read-only viewer): uses only QGIS-bundled GDAL / Qt; no
runtime dependency on the OpenLimno Python package. M2 alpha deliverable.

Functionality:
1. Open OpenLimno hydraulic NetCDF (CF / UGRID) → load each variable as a
   QGIS mesh layer or raster overlay
2. Open WUA-Q CSV / Parquet → display as table + line chart in a docked panel
3. Open HSI evidence Parquet → display as table

What this plugin does NOT do (deliberately):
- Run hydraulics or habitat (call the external `openlimno` CLI)
- Edit data (read-only)
- Depend on `openlimno` Python package inside QGIS Python

This file is intentionally minimal so the plugin works against QGIS LTS 3.34+
without external Python deps.
"""

from __future__ import annotations

import csv
import os
from typing import Any


class OpenLimnoPlugin:
    """Plugin object instantiated by QGIS at startup."""

    def __init__(self, iface):  # noqa: ANN001
        self.iface = iface
        self.actions: list[Any] = []
        self.menu = "&OpenLimno"

    # ------------------------------------------------------------------
    # Lifecycle hooks called by QGIS
    # ------------------------------------------------------------------
    def initGui(self) -> None:  # noqa: N802 (QGIS API)
        try:
            from qgis.PyQt.QtGui import QIcon
            from qgis.PyQt.QtWidgets import QAction
        except ImportError:
            return  # outside QGIS env (e.g. unit-test import)

        icon = QIcon()  # placeholder; real icon at resources/openlimno_icon.svg
        a_open_results = QAction(icon, "Open OpenLimno hydraulic results…",
                                  self.iface.mainWindow())
        a_open_results.triggered.connect(self.open_hydraulic_nc)
        self.iface.addPluginToMenu(self.menu, a_open_results)
        self.iface.addToolBarIcon(a_open_results)
        self.actions.append(a_open_results)

        a_open_wua = QAction(icon, "Open WUA-Q curve…",
                             self.iface.mainWindow())
        a_open_wua.triggered.connect(self.open_wua_q)
        self.iface.addPluginToMenu(self.menu, a_open_wua)
        self.actions.append(a_open_wua)

    def unload(self) -> None:
        try:
            from qgis.PyQt.QtWidgets import QAction  # noqa: F401
        except ImportError:
            return
        for a in self.actions:
            self.iface.removePluginMenu(self.menu, a)
            self.iface.removeToolBarIcon(a)
        self.actions = []

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------
    def open_hydraulic_nc(self) -> None:
        """File picker → load NetCDF as QGIS mesh / raster layer."""
        try:
            from qgis.core import QgsMeshLayer, QgsProject, QgsRasterLayer
            from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
        except ImportError:
            return

        path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Open OpenLimno hydraulics NetCDF",
            "",
            "OpenLimno NetCDF (*.nc);;All files (*)",
        )
        if not path:
            return

        # Try mesh layer first (UGRID); fall back to raster
        layer_name = os.path.basename(path)
        mesh = QgsMeshLayer(path, layer_name, "mdal")
        if mesh.isValid():
            QgsProject.instance().addMapLayer(mesh)
            return

        # Raster fallback (e.g. for water_depth / velocity_magnitude variables)
        # Each NetCDF var becomes a sub-dataset
        rast = QgsRasterLayer(f'NETCDF:"{path}":water_depth',
                              f"{layer_name}:water_depth")
        if rast.isValid():
            QgsProject.instance().addMapLayer(rast)
        else:
            QMessageBox.warning(
                self.iface.mainWindow(), "OpenLimno",
                f"Could not load {path} as mesh or raster. "
                "If this is a non-UGRID NetCDF, try the 'Add Mesh Layer' tool."
            )

    def open_wua_q(self) -> None:
        """File picker for WUA-Q CSV/Parquet → show table + chart."""
        try:
            from qgis.PyQt.QtWidgets import (
                QDialog, QFileDialog, QTableWidget, QTableWidgetItem, QVBoxLayout,
            )
        except ImportError:
            return

        path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Open WUA-Q file",
            "",
            "WUA-Q (*.csv *.parquet);;All files (*)",
        )
        if not path:
            return

        rows = self._read_wua_csv(path) if path.endswith(".csv") else \
            self._read_wua_parquet(path)
        if not rows:
            return

        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle(f"WUA-Q: {os.path.basename(path)}")
        layout = QVBoxLayout(dlg)
        headers = list(rows[0].keys())
        table = QTableWidget(len(rows), len(headers), dlg)
        table.setHorizontalHeaderLabels(headers)
        for i, row in enumerate(rows):
            for j, h in enumerate(headers):
                table.setItem(i, j, QTableWidgetItem(str(row.get(h, ""))))
        layout.addWidget(table)
        dlg.resize(640, 480)
        dlg.exec()

    # ------------------------------------------------------------------
    # Internal helpers — must work without OpenLimno Python deps
    # ------------------------------------------------------------------
    @staticmethod
    def _read_wua_csv(path: str) -> list[dict[str, str]]:
        # OpenLimno regulatory exports prefix metadata with '#'; strip them
        # before passing to csv.DictReader so the actual header is the first
        # non-comment row.
        with open(path, encoding="utf-8") as f:
            data_lines = [line for line in f if not line.lstrip().startswith("#")]
        if not data_lines:
            return []
        reader = csv.DictReader(data_lines)
        return list(reader)

    @staticmethod
    def _read_wua_parquet(path: str) -> list[dict[str, Any]]:
        """Best-effort Parquet read using QGIS-bundled tools."""
        # Try pyarrow (often available in QGIS Python on Linux/macOS)
        try:
            import pyarrow.parquet as pq
            t = pq.read_table(path)
            return [dict(zip(t.column_names, row, strict=False))
                    for row in zip(*[c.to_pylist() for c in t.columns], strict=False)]
        except Exception:
            pass
        # If not available, gdal/ogr can read Parquet via the Apache Arrow driver
        try:
            from osgeo import ogr
            ds = ogr.Open(path)
            if ds is None:
                return []
            layer = ds.GetLayer(0)
            field_names = [layer.GetLayerDefn().GetFieldDefn(i).GetName()
                            for i in range(layer.GetLayerDefn().GetFieldCount())]
            rows = []
            for feat in layer:
                rows.append({fn: feat.GetField(fn) for fn in field_names})
            return rows
        except Exception:
            return []
