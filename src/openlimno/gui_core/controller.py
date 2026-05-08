"""Controller — the single source of truth for plugin + Studio actions.

Both the QGIS plugin and OpenLimno Studio instantiate one ``Controller``
per session, passing a ``Host`` adapter that exposes the QGIS-iface-shaped
methods the handlers need. Handlers don't import ``iface`` directly.
"""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from typing import Any, Protocol


class Host(Protocol):
    """Adapter interface implemented by both PluginHost and Studio MainWindow.

    The four methods mirror QGIS iface, so the handler bodies (which were
    originally written against ``self.iface``) port over almost verbatim.
    """

    def main_window(self) -> Any: ...
    def map_canvas(self) -> Any: ...
    def message_bar(self) -> Any: ...
    def status_bar(self) -> Any: ...


# ---------------------------------------------------------------------------
# Helpers (no Qt / iface dependency)
# ---------------------------------------------------------------------------
def _read_wua_csv(path: str) -> list[dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        data_lines = [line for line in f if not line.lstrip().startswith("#")]
    if not data_lines:
        return []
    return list(csv.DictReader(data_lines))


def _read_wua_parquet(path: str) -> list[dict[str, Any]]:
    """Best-effort Parquet read using whatever's bundled (pyarrow / GDAL)."""
    try:
        import pyarrow.parquet as pq

        t = pq.read_table(path)
        return [
            dict(zip(t.column_names, row, strict=False))
            for row in zip(*[c.to_pylist() for c in t.columns], strict=False)
        ]
    except Exception:
        pass
    try:
        from osgeo import ogr

        ds = ogr.Open(path)
        if ds is None:
            return []
        layer = ds.GetLayer(0)
        defn = layer.GetLayerDefn()
        field_names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
        return [{fn: feat.GetField(fn) for fn in field_names} for feat in layer]
    except Exception:
        return []




# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
class Controller:
    """Holds session state and exposes handler methods.

    State lifecycle:
    - ``_xs_parquet`` / ``_hyd_nc``: auto-discovery cache, reset by
      build_case_from_osm and refreshed by activate_pick_tool
    - ``_pick_tool``: active QgsMapTool (None when click-tool is off)
    - ``_run_case_proc``: keeps QProcess alive while CLI runs
    """

    def __init__(self, host: Host) -> None:
        self.host = host
        self._xs_parquet: str | None = None
        self._hyd_nc: str | None = None
        self._pick_tool: Any = None
        self._pick_action: Any = None  # set by UI when an action is checkable
        self._run_case_proc: Any = None
        self._run_case_log: bytearray = bytearray()

    # ------------------------------------------------------------------
    # Open existing results
    # ------------------------------------------------------------------
    def open_hydraulic_nc(self) -> None:
        from qgis.core import QgsMeshLayer, QgsProject, QgsRasterLayer
        from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self.host.main_window(),
            "Open OpenLimno hydraulics NetCDF",
            "",
            "OpenLimno NetCDF (*.nc);;All files (*)",
        )
        if not path:
            return
        layer_name = os.path.basename(path)
        mesh = QgsMeshLayer(path, layer_name, "mdal")
        if mesh.isValid():
            QgsProject.instance().addMapLayer(mesh)
            return
        rast = QgsRasterLayer(f'NETCDF:"{path}":water_depth', f"{layer_name}:water_depth")
        if rast.isValid():
            QgsProject.instance().addMapLayer(rast)
        else:
            QMessageBox.warning(
                self.host.main_window(), "OpenLimno",
                f"Could not load {path} as mesh or raster.",
            )

    def open_wua_q(self) -> None:
        from qgis.PyQt.QtWidgets import (
            QDialog, QFileDialog, QTableWidget, QTableWidgetItem, QVBoxLayout,
        )

        path, _ = QFileDialog.getOpenFileName(
            self.host.main_window(),
            "Open WUA-Q file",
            "",
            "WUA-Q (*.csv *.parquet);;All files (*)",
        )
        if not path:
            return
        rows = _read_wua_csv(path) if path.endswith(".csv") else _read_wua_parquet(path)
        if not rows:
            return
        dlg = QDialog(self.host.main_window())
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

    def plot_cross_section(self) -> None:
        from qgis.PyQt.QtWidgets import (
            QComboBox, QDialog, QDialogButtonBox, QFileDialog,
            QFormLayout, QMessageBox, QVBoxLayout,
        )

        xs_path, _ = QFileDialog.getOpenFileName(
            self.host.main_window(),
            "Open cross_section.parquet",
            "",
            "OpenLimno cross-sections (*.parquet);;All files (*)",
        )
        if not xs_path:
            return
        rows = _read_wua_parquet(xs_path)
        if not rows:
            QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                  f"Could not read {xs_path}")
            return
        stations = sorted({float(r["station_m"]) for r in rows})

        hyd_path, _ = QFileDialog.getOpenFileName(
            self.host.main_window(),
            "Open hydraulics.nc (cancel for bed-only plot)",
            "",
            "OpenLimno hydraulics (*.nc);;All files (*)",
        )

        dlg = QDialog(self.host.main_window())
        dlg.setWindowTitle("Plot cross-section")
        form = QFormLayout(dlg)
        cb_station = QComboBox(); cb_station.addItems([f"{s:g}" for s in stations])
        form.addRow("station_m:", cb_station)
        cb_q = QComboBox()
        discharges: list[float] = []
        if hyd_path:
            try:
                from netCDF4 import Dataset
                ds = Dataset(hyd_path)
                if "discharge" in ds.variables:
                    discharges = [float(v) for v in ds.variables["discharge"][:]]
                ds.close()
                cb_q.addItems([f"{q:g}" for q in discharges])
                form.addRow("Q (m³/s):", cb_q)
            except Exception as e:
                QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                      f"Failed to read discharges: {e}")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        target_station = float(cb_station.currentText())
        target_Q = float(cb_q.currentText()) if discharges else None
        # Stash the hydraulics path so the renderer can reach it
        self._hyd_nc = hyd_path or None
        self._render_profile_dialog(rows, stations, target_station, target_Q)

    # ------------------------------------------------------------------
    # Build a brand-new case from OSM
    # ------------------------------------------------------------------
    def build_case_from_osm(self) -> None:
        from qgis.PyQt.QtWidgets import (
            QButtonGroup, QDialog, QDialogButtonBox, QDoubleSpinBox,
            QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
            QMessageBox, QPushButton, QRadioButton, QSpinBox, QWidget,
        )

        dlg = QDialog(self.host.main_window())
        dlg.setWindowTitle("Build OpenLimno case from OSM")
        form = QFormLayout(dlg)

        canvas_extent = self.host.map_canvas().extent()
        bbox_str = (
            f"{canvas_extent.xMinimum():.6f},{canvas_extent.yMinimum():.6f},"
            f"{canvas_extent.xMaximum():.6f},{canvas_extent.yMaximum():.6f}"
        )

        rb_bbox = QRadioButton("Use current map view (bbox) — recommended")
        rb_bbox.setChecked(True)
        rb_polyline = QRadioButton("Use a GeoJSON LineString file…")
        rb_name = QRadioButton("Search by river name + region (least precise)")
        bg = QButtonGroup(dlg)
        for b in (rb_bbox, rb_polyline, rb_name):
            bg.addButton(b)

        e_bbox = QLineEdit(bbox_str)
        e_polyline = QLineEdit("")
        e_polyline.setPlaceholderText("(none)")
        e_river = QLineEdit("")
        e_river.setPlaceholderText("Lemhi River (only used in name+region mode)")
        e_region = QLineEdit("Idaho")

        form.addRow(QLabel("<b>Reach location</b>"))
        form.addRow(rb_bbox, e_bbox)
        polyline_row = QWidget(); pl = QHBoxLayout(polyline_row); pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(e_polyline)
        btn_browse = QPushButton("Browse…")

        def _browse():
            p, _ = QFileDialog.getOpenFileName(dlg, "Select LineString GeoJSON",
                                                  "", "GeoJSON (*.geojson *.json)")
            if p:
                e_polyline.setText(p); rb_polyline.setChecked(True)
        btn_browse.clicked.connect(_browse)
        pl.addWidget(btn_browse)
        form.addRow(rb_polyline, polyline_row)
        form.addRow(rb_name, QWidget())
        form.addRow("    river name:", e_river)
        form.addRow("    region:", e_region)

        e_n = QSpinBox(); e_n.setRange(3, 200); e_n.setValue(11)
        e_reach = QDoubleSpinBox(); e_reach.setRange(0.1, 100); e_reach.setValue(1.0); e_reach.setSuffix(" km")
        e_w = QDoubleSpinBox(); e_w.setRange(1, 500); e_w.setValue(10); e_w.setSuffix(" m")
        e_d = QDoubleSpinBox(); e_d.setRange(0.1, 50); e_d.setValue(1.0); e_d.setSuffix(" m")
        e_elev = QDoubleSpinBox(); e_elev.setRange(0, 9000); e_elev.setValue(1500); e_elev.setSuffix(" m")
        e_slope = QDoubleSpinBox(); e_slope.setRange(0.0001, 0.5); e_slope.setValue(0.002); e_slope.setDecimals(4)
        e_species = QLineEdit("oncorhynchus_mykiss")

        form.addRow(QLabel("<b>Geometry & habitat</b>"))
        form.addRow("Mesh nodes:", e_n)
        form.addRow("Reach length:", e_reach)
        form.addRow("Valley width:", e_w)
        form.addRow("Thalweg depth:", e_d)
        form.addRow("Bank elevation:", e_elev)
        form.addRow("Bed slope:", e_slope)
        form.addRow("Target species id:", e_species)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Compute slug
        if rb_name.isChecked() and e_river.text().strip():
            slug = e_river.text().strip().lower().replace(" ", "_")
        elif rb_polyline.isChecked() and e_polyline.text().strip():
            slug = Path(e_polyline.text()).stem.lower().replace(" ", "_")
        elif rb_bbox.isChecked():
            try:
                lon0, lat0, lon1, lat1 = (float(x) for x in e_bbox.text().split(","))
                lon_c, lat_c = (lon0 + lon1) / 2, (lat0 + lat1) / 2
                slug = (f"reach_{lat_c:.4f}_{lon_c:.4f}"
                          .replace("-", "n").replace(".", "p"))
            except ValueError:
                slug = "case"
        else:
            slug = "case"

        default_parent = Path(os.path.expanduser("~/openlimno-workspace/"))
        suggested = str(default_parent / slug)
        out_dir = QFileDialog.getExistingDirectory(
            self.host.main_window(),
            f"Choose output directory (suggested: {slug}/ — must NOT be the workspace root)",
            suggested,
        )
        if not out_dir:
            return
        out_data = Path(out_dir) / "data"
        if out_data.is_symlink() or (out_data.exists() and out_data.resolve() != out_data):
            QMessageBox.warning(
                self.host.main_window(), "OpenLimno",
                f"{out_data} is a symlink to {out_data.resolve()}.\n\n"
                f"Pick a real subdirectory (e.g. {default_parent / slug}/) so the "
                f"case files don't pollute the linked target.",
            )
            return

        # Build the OSMCaseSpec from the dialog inputs
        from openlimno.preprocess.osm_builder import OSMCaseSpec, build_case

        spec_kwargs = dict(
            n_sections=e_n.value(),
            reach_length_m=e_reach.value() * 1000.0,  # km → m
            valley_width_m=e_w.value(),
            thalweg_depth_m=e_d.value(),
            bank_elevation_m=e_elev.value(),
            slope=e_slope.value(),
            species_id=e_species.text(),
        )
        if rb_bbox.isChecked():
            try:
                lon0, lat0, lon1, lat1 = (float(x) for x in e_bbox.text().split(","))
            except ValueError:
                QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                      f"Invalid bbox: {e_bbox.text()!r}")
                return
            spec_kwargs["bbox"] = (lon0, lat0, lon1, lat1)
            if e_river.text().strip():
                spec_kwargs["river_name"] = e_river.text().strip()
        elif rb_polyline.isChecked():
            if not e_polyline.text():
                QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                      "Pick a GeoJSON file first.")
                return
            spec_kwargs["polyline_geojson"] = e_polyline.text()
        else:
            if not e_river.text().strip():
                QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                      "Provide a river name.")
                return
            spec_kwargs["river_name"] = e_river.text().strip()
            spec_kwargs["region_name"] = e_region.text() or "Idaho"

        spec = OSMCaseSpec(**spec_kwargs)

        # Show "in progress" + flush event loop so the message bar appears
        from qgis.PyQt.QtWidgets import QApplication
        from qgis.PyQt.QtGui import QGuiApplication
        from qgis.PyQt.QtCore import Qt

        self.host.message_bar().pushMessage(
            "OpenLimno", "Fetching OSM polyline + building case…",
            level=0, duration=10,
        )
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            paths = build_case(spec, out_dir)
        except Exception as e:
            QGuiApplication.restoreOverrideCursor()
            import traceback
            QMessageBox.warning(
                self.host.main_window(), "OpenLimno",
                f"Case build failed:\n\n{e}\n\n{traceback.format_exc()[-1000:]}",
            )
            return
        QGuiApplication.restoreOverrideCursor()

        case_yaml_path = Path(paths["case_yaml"])
        loaded = self._load_case_layers(Path(out_dir))
        QMessageBox.information(
            self.host.main_window(), "OpenLimno",
            f"✓ Case built at {out_dir}\n\n"
            f"case.yaml:  {case_yaml_path}\n\n"
            f"Loaded into project: {', '.join(loaded) if loaded else '(no layers)'}",
        )
        self._xs_parquet = None
        self._hyd_nc = None

    # ------------------------------------------------------------------
    # Run a case in-process via QThread (no subprocess / CLI dependency)
    # ------------------------------------------------------------------
    def run_case(self) -> None:
        from qgis.PyQt.QtCore import QThread, pyqtSignal
        from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

        case_yaml = self._discover_case_yaml()
        if not case_yaml:
            picked, _ = QFileDialog.getOpenFileName(
                self.host.main_window(),
                "Pick a case.yaml to run",
                str(Path.home() / "openlimno-workspace"),
                "OpenLimno case (*.yaml *.yml)",
            )
            if not picked:
                return
            case_yaml = Path(picked)

        # QThread subclass — defined locally to keep qgis.PyQt imports
        # inside the method body (controller.py must remain importable in
        # non-Qt environments for tests).
        class _RunCaseWorker(QThread):
            status = pyqtSignal(str)
            finished_ok = pyqtSignal(str)
            failed = pyqtSignal(str)

            def __init__(self, case_yaml_, parent=None):
                super().__init__(parent)
                self._case_yaml = case_yaml_

            def run(self_):  # noqa: N805 (Qt API; outer self is closure)
                try:
                    self_.status.emit(f"Loading {self_._case_yaml.name}…")
                    from openlimno.case import Case
                    case = Case.from_yaml(str(self_._case_yaml))
                    self_.status.emit("Solving 1D hydraulics + WUA-Q…")
                    result = case.run()
                    self_.finished_ok.emit(result.summary())
                except Exception:
                    import traceback
                    self_.failed.emit(traceback.format_exc())

        self.host.message_bar().pushMessage(
            "OpenLimno", f"Running {case_yaml.name}… (canvas stays responsive)",
            level=0, duration=3,
        )
        worker = _RunCaseWorker(case_yaml, self.host.main_window())
        worker.status.connect(lambda s: self.host.status_bar().showMessage(s))
        worker.finished_ok.connect(
            lambda summary: self._on_run_finished(case_yaml, summary, None))
        worker.failed.connect(
            lambda tb: self._on_run_finished(case_yaml, None, tb))
        self._run_case_worker = worker
        worker.start()

    def _on_run_finished(self, case_yaml: Path, summary, traceback_text):
        from qgis.PyQt.QtWidgets import QMessageBox

        self.host.status_bar().clearMessage()
        if traceback_text is not None:
            QMessageBox.warning(
                self.host.main_window(), "OpenLimno",
                f"Run failed:\n\n{traceback_text[-1500:]}",
            )
            return
        out_nc = case_yaml.parent / "out" / "hydraulics.nc"
        loaded_msg = ""
        if out_nc.is_file():
            self._load_hydraulics_layer(out_nc)
            loaded_msg = f"\n\nLoaded {out_nc.name} as a mesh layer."
            self._hyd_nc = str(out_nc)
        QMessageBox.information(
            self.host.main_window(), "OpenLimno",
            f"✓ Run finished.\n\n{summary or ''}{loaded_msg}",
        )

    def _discover_case_yaml(self) -> Path | None:
        from qgis.core import QgsProject

        for lyr in QgsProject.instance().mapLayers().values():
            try:
                src = lyr.source()
            except Exception:
                continue
            if not src:
                continue
            p = Path(src.split("|", 1)[0])
            for parent in [p.parent, p.parent.parent]:
                cand = parent / "case.yaml"
                if cand.is_file():
                    return cand
        return None

    def _load_hydraulics_layer(self, nc_path: Path) -> None:
        from qgis.core import QgsMeshLayer, QgsProject, QgsRasterLayer

        layer = QgsMeshLayer(str(nc_path), nc_path.stem, "mdal")
        if not layer.isValid():
            layer = QgsRasterLayer(f'NETCDF:"{nc_path}":water_depth',
                                     nc_path.stem, "gdal")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)

    def _load_case_layers(self, case_dir: Path) -> list[str]:
        try:
            from netCDF4 import Dataset
            import pandas as pd
            from qgis.core import (
                QgsFeature, QgsField, QgsGeometry, QgsPointXY,
                QgsProject, QgsVectorLayer,
            )
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            return []

        added: list[str] = []
        mesh_nc = case_dir / "data" / "mesh.ugrid.nc"
        xs_pq = case_dir / "data" / "cross_section.parquet"

        if mesh_nc.is_file():
            try:
                ds = Dataset(str(mesh_nc))
                xs = ds.variables["node_x"][:]
                ys = ds.variables["node_y"][:]
                stations = (ds.variables["station_m"][:]
                            if "station_m" in ds.variables else range(len(xs)))
                ds.close()
                lyr = QgsVectorLayer("Point?crs=EPSG:4326",
                                       f"{case_dir.name} mesh nodes", "memory")
                pr = lyr.dataProvider()
                pr.addAttributes([QgsField("node_id", QVariant.Int),
                                    QgsField("station_m", QVariant.Double)])
                lyr.updateFields()
                feats = []
                for i, (x, y, s) in enumerate(zip(xs, ys, stations)):
                    f = QgsFeature()
                    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(x), float(y))))
                    f.setAttributes([i, float(s)])
                    feats.append(f)
                pr.addFeatures(feats); lyr.updateExtents()
                QgsProject.instance().addMapLayer(lyr)
                added.append(lyr.name())
            except Exception as e:
                self.host.message_bar().pushMessage(
                    "OpenLimno", f"mesh.ugrid.nc load failed: {e}", level=1, duration=8)

        if xs_pq.is_file() and mesh_nc.is_file():
            try:
                df = pd.read_parquet(xs_pq)
                ds = Dataset(str(mesh_nc))
                node_x = ds.variables["node_x"][:]
                node_y = ds.variables["node_y"][:]
                stations = list(ds.variables["station_m"][:])
                ds.close()
                lyr = QgsVectorLayer("LineString?crs=EPSG:4326",
                                       f"{case_dir.name} cross-sections", "memory")
                pr = lyr.dataProvider()
                pr.addAttributes([QgsField("station_m", QVariant.Double)])
                lyr.updateFields()
                feats = []
                for i, st in enumerate(stations):
                    sec = df[df.station_m == float(st)]
                    if sec.empty:
                        continue
                    half = max(abs(sec.distance_m.min()), abs(sec.distance_m.max()))
                    j = min(i + 1, len(node_x) - 1) if i == 0 else i - 1
                    dx = float(node_x[i] - node_x[j])
                    dy = float(node_y[i] - node_y[j])
                    norm = math.hypot(dx, dy) or 1.0
                    lat = float(node_y[i])
                    m_per_deg_lat = 111000.0
                    m_per_deg_lon = 111000.0 * math.cos(math.radians(lat)) or 1.0
                    px = -dy / norm
                    py = dx / norm
                    end1 = QgsPointXY(float(node_x[i]) + px * half / m_per_deg_lon,
                                        float(node_y[i]) + py * half / m_per_deg_lat)
                    end2 = QgsPointXY(float(node_x[i]) - px * half / m_per_deg_lon,
                                        float(node_y[i]) - py * half / m_per_deg_lat)
                    f = QgsFeature()
                    f.setGeometry(QgsGeometry.fromPolylineXY([end1, end2]))
                    f.setAttributes([float(st)])
                    feats.append(f)
                pr.addFeatures(feats); lyr.updateExtents()
                QgsProject.instance().addMapLayer(lyr)
                added.append(lyr.name())
            except Exception as e:
                self.host.message_bar().pushMessage(
                    "OpenLimno", f"cross_section.parquet load failed: {e}", level=1, duration=8)

        if added:
            self._zoom_canvas_to_layer(
                QgsProject.instance().mapLayersByName(added[0])[0]
            )
        return added

    def _zoom_canvas_to_layer(self, layer) -> None:
        """Zoom canvas to a layer's extent, transforming CRS if needed.

        Canvas is typically EPSG:3857 (so OSM tiles align); mesh / xs
        layers are EPSG:4326. Without the transform, layer.extent() is
        misinterpreted as Web Mercator metres and the canvas pans to
        the middle of an ocean.
        """
        from qgis.core import QgsCoordinateTransform, QgsProject

        canvas = self.host.map_canvas()
        try:
            src_crs = layer.crs()
            dst_crs = canvas.mapSettings().destinationCrs()
            extent = layer.extent()
            if src_crs != dst_crs and src_crs.isValid() and dst_crs.isValid():
                xform = QgsCoordinateTransform(src_crs, dst_crs,
                                                  QgsProject.instance())
                extent = xform.transformBoundingBox(extent)
            canvas.setExtent(extent)
            canvas.refresh()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Click-on-map cross-section tool
    # ------------------------------------------------------------------
    def _auto_discover_paths(self) -> None:
        from qgis.core import QgsProject, QgsVectorLayer

        if self._xs_parquet and self._hyd_nc:
            return

        gpkg_paths = set()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                src = layer.dataProvider().dataSourceUri() if layer.dataProvider() else ""
                if ".gpkg" in src.lower():
                    gpkg_paths.add(src.split("|")[0])

        for gpkg in gpkg_paths:
            workspace = Path(gpkg).parent
            xs_candidates = [
                workspace / "data/lemhi/cross_section.parquet",
                workspace.parent / "data/lemhi/cross_section.parquet",
                Path.home() / "openlimno-workspace/data/lemhi/cross_section.parquet",
            ]
            hyd_candidates = []
            out_dir = workspace / "out"
            if out_dir.is_dir():
                for case_dir in out_dir.iterdir():
                    if case_dir.is_dir():
                        hyd_candidates.append(case_dir / "hydraulics.nc")
            hyd_candidates.append(Path.home() / "openlimno-workspace/out/lemhi/hydraulics.nc")

            if not self._xs_parquet:
                for p in xs_candidates:
                    if p.is_file():
                        self._xs_parquet = str(p); break
            if not self._hyd_nc:
                for p in hyd_candidates:
                    if p.is_file():
                        self._hyd_nc = str(p); break

        msg = []
        msg.append(f"xs ✓ {Path(self._xs_parquet).name}" if self._xs_parquet else "xs ✗")
        msg.append(f"hyd ✓ {Path(self._hyd_nc).name}" if self._hyd_nc else "hyd ✗ (bed-only plots)")
        self.host.message_bar().pushMessage(
            "OpenLimno auto-discovery", " | ".join(msg), level=0, duration=5,
        )

    def activate_pick_tool(self, checked: bool) -> None:
        from qgis.core import (
            QgsFeatureRequest, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer,
        )
        from qgis.gui import QgsMapTool
        from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

        canvas = self.host.map_canvas()

        if not checked:
            if self._pick_tool:
                canvas.unsetMapTool(self._pick_tool)
            self._pick_tool = None
            return

        self._auto_discover_paths()
        if not self._xs_parquet:
            p, _ = QFileDialog.getOpenFileName(
                self.host.main_window(),
                "Pick cross_section.parquet (auto-discovery failed)",
                "",
                "OpenLimno cross-sections (*.parquet);;All files (*)",
            )
            if not p:
                if self._pick_action is not None:
                    self._pick_action.setChecked(False)
                return
            self._xs_parquet = p

        controller = self

        class _ClickTool(QgsMapTool):
            def __init__(self, canvas):
                super().__init__(canvas)

            def canvasReleaseEvent(self, e):  # noqa: N802 (Qt API)
                pt = self.toMapCoordinates(e.pos())
                all_layers = list(QgsProject.instance().mapLayers().values())
                cands = [layer for layer in all_layers if isinstance(layer, QgsVectorLayer)]
                controller.host.message_bar().pushMessage(
                    "OpenLimno",
                    f"clicked @ {pt.x():.5f}, {pt.y():.5f} — "
                    f"{len(all_layers)} layer(s), {len(cands)} vector",
                    level=0, duration=4,
                )
                if not cands:
                    QMessageBox.information(
                        controller.host.main_window(), "OpenLimno",
                        f"No vector layer in this project.",
                    )
                    return
                tol = controller.host.map_canvas().mapUnitsPerPixel() * 18
                bb = QgsRectangle(pt.x() - tol, pt.y() - tol,
                                    pt.x() + tol, pt.y() + tol)
                station = None
                hit_layer = None
                for layer in cands:
                    req = QgsFeatureRequest().setFilterRect(bb)
                    feats = list(layer.getFeatures(req))
                    if not feats:
                        continue
                    pt_geom = QgsGeometry.fromPointXY(pt)
                    f = min(feats, key=lambda ff: ff.geometry().distance(pt_geom))
                    fields = [fd.name() for fd in layer.fields()]
                    if "station_m" in fields:
                        try:
                            station = float(f["station_m"]); hit_layer = layer.name(); break
                        except (TypeError, ValueError):
                            pass
                    if "node_id" in fields:
                        try:
                            station = float(f["node_id"]) * 100.0
                            hit_layer = layer.name(); break
                        except (TypeError, ValueError):
                            pass
                if station is None:
                    controller.host.message_bar().pushMessage(
                        "OpenLimno",
                        f"No mesh-node / cross-section feature within {tol:.6f}° of click",
                        level=1, duration=5,
                    )
                    return
                controller.host.message_bar().pushMessage(
                    "OpenLimno", f"hit {hit_layer} → station {station:g} m",
                    level=0, duration=3,
                )
                controller._plot_at_station(station)

        self._pick_tool = _ClickTool(canvas)
        canvas.setMapTool(self._pick_tool)
        self.host.message_bar().pushMessage(
            "OpenLimno",
            "Click any mesh node or cross-section to view its profile. "
            "Click the toolbar button again to deactivate.",
            level=0, duration=10,
        )

    def _plot_at_station(self, station: float) -> None:
        from qgis.PyQt.QtWidgets import (
            QComboBox, QDialog, QDialogButtonBox, QFormLayout, QMessageBox,
        )

        if not self._xs_parquet:
            QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                  "No cross_section.parquet selected.")
            return
        rows = _read_wua_parquet(self._xs_parquet)
        stations = sorted({float(r["station_m"]) for r in rows})
        station = min(stations, key=lambda s: abs(s - station))

        target_Q = None
        if self._hyd_nc:
            try:
                from netCDF4 import Dataset
                ds = Dataset(self._hyd_nc)
                discharges = [float(v) for v in ds.variables["discharge"][:]]
                ds.close()
            except Exception:
                discharges = []
            if discharges:
                dlg = QDialog(self.host.main_window())
                dlg.setWindowTitle(f"Q for station {station:g} m")
                form = QFormLayout(dlg)
                cb = QComboBox(); cb.addItems([f"{q:g}" for q in discharges])
                idx = min(range(len(discharges)),
                            key=lambda i: abs(discharges[i] - 7.0))
                cb.setCurrentIndex(idx)
                form.addRow("Q (m³/s):", cb)
                bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
                bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
                form.addRow(bb)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    target_Q = float(cb.currentText())

        self._render_profile_dialog(rows, stations, station, target_Q)

    def _render_profile_dialog(self, rows, stations, target_station, target_Q) -> None:
        from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QVBoxLayout

        sec = sorted(
            (r for r in rows if float(r["station_m"]) == target_station),
            key=lambda r: int(r["point_index"]),
        )
        d = [float(r["distance_m"]) for r in sec]
        z = [float(r["elevation_m"]) for r in sec]

        wse = None
        if target_Q is not None and self._hyd_nc:
            try:
                from netCDF4 import Dataset
                ds = Dataset(self._hyd_nc)
                qs = list(ds.variables["discharge"][:])
                iq = min(range(len(qs)), key=lambda i: abs(float(qs[i]) - target_Q))
                node_idx = stations.index(target_station)
                wse = float(ds.variables["water_surface"][iq, node_idx])
                ds.close()
            except Exception as e:
                QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                      f"WSE extract failed: {e}")

        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except ImportError:
            try:
                from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
                from matplotlib.figure import Figure
            except ImportError:
                QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                      "matplotlib not available")
                return

        plot_dlg = QDialog(self.host.main_window())
        plot_dlg.setWindowTitle(f"Cross-section @ station {target_station:g} m")
        v = QVBoxLayout(plot_dlg)
        fig = Figure(figsize=(9, 5))
        ax = fig.add_subplot(111)
        ax.plot(d, z, "k-", lw=2.5, zorder=10)
        z_min = min(z)
        ax.fill_between(d, z, z_min - 0.4, color="#c8a07a", alpha=0.55, zorder=1)
        title = f"Cross-section @ station {target_station:g} m"
        if wse is not None and wse > z_min:
            ax.axhline(wse, color="#1565c0", lw=2, zorder=4,
                        label=f"WSE @ Q={target_Q:g} m³/s = {wse:.2f} m")
            water_z = [max(zi, wse) if zi < wse else zi for zi in z]
            ax.fill_between(d, z, water_z, color="#90caf9", alpha=0.6,
                              interpolate=True, zorder=2)
            depth = wse - z_min
            ax.set_title(f"{title} — Q={target_Q:g} m³/s, max depth {depth:.2f} m")
            ax.legend(loc="lower right")
        else:
            ax.set_title(title + " (bed only)")
        ax.set_xlabel("transverse distance (m)")
        ax.set_ylabel("elevation (m)")
        ax.grid(True, alpha=0.3)
        fc = FigureCanvasQTAgg(fig)
        v.addWidget(fc)
        plot_dlg.resize(900, 560)
        plot_dlg.exec()
