"""Controller — the single source of truth for plugin + Studio actions.

Both the QGIS plugin and OpenLimno Studio instantiate one ``Controller``
per session, passing a ``Host`` adapter that exposes the QGIS-iface-shaped
methods the handlers need. Handlers don't import ``iface`` directly.
"""
from __future__ import annotations

import csv
import math
import os
import time
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


class _NoArrowExceptionAvailable(Exception):
    """Sentinel: never matches any real exception.

    Used as a fallback in the module-level ``_ARROW_CATCH`` tuple when
    pyarrow has no recognisable Arrow* exception classes (no
    ``ArrowException`` parent, no individual subclasses). ``except
    _NoArrowExceptionAvailable`` is then a syntactically valid clause
    that simply never fires.
    """


def _build_arrow_catch_tuples() -> tuple[tuple[type, ...], tuple[type, ...]]:
    """Build TWO catch-tuples: transient and permanent Arrow* failures.

    Post-v0.1.0 round-1 review (Claude #1): the previous single
    ``_ARROW_CATCH`` lumped permanent schema/coercion failures
    (``ArrowKeyError`` = missing column, ``ArrowNotImplementedError`` =
    unsupported encoding, ``ArrowTypeError`` = type coercion fail,
    ``ArrowCapacityError`` = >2 GB column) in with truly transient I/O
    issues (``ArrowInvalid`` = torn footer, ``ArrowIOError`` = read
    underflow). Re-raising both as ``OSError`` made the cache retry
    burn ~150 ms total backoff (50 + 100 ms) across 3 attempts on
    guaranteed-permanent failures — same
    pattern that ``MissingParquetBackend`` was introduced to fix.

    Now returns ``(transient, permanent)``. Caller in
    ``_read_wua_parquet`` routes the two through different normalised
    exception types; ``_read_xs_rows_cached`` short-circuits the
    permanent class like it does for ``MissingParquetBackend``.

    Vendor-pyarrow handling: each tuple falls back to the sentinel if
    none of its classes are available on the build.
    """
    try:
        from pyarrow import lib as _pa_lib
    except ImportError:
        return (_NoArrowExceptionAvailable,), (_NoArrowExceptionAvailable,)

    def _resolve(*names: str) -> tuple[type, ...]:
        classes = []
        for name in names:
            cls = getattr(_pa_lib, name, None)
            if isinstance(cls, type) and issubclass(cls, BaseException):
                classes.append(cls)
        return tuple(classes) if classes else (_NoArrowExceptionAvailable,)

    transient = _resolve(
        "ArrowInvalid",       # corrupt footer / bad data: retry-eligible
        "ArrowIOError",       # I/O underflow: retry-eligible
        # Post-v0.1.1 round-3 review (Claude + Gemini consensus):
        # ``ArrowMemoryError`` was briefly moved here in round-2, but
        # 50/100 ms backoff is far too short for an OS to free
        # meaningful RAM. If pyarrow's allocation failed once, a
        # 50 ms retry will almost certainly fail again — exactly
        # the burn-the-budget pattern transient-vs-permanent was
        # introduced to fix. Reverted to permanent below.
    )
    # All 8 currently-known permanent Arrow* classes plus the
    # ``ArrowException`` parent as a forward-compat fallback.
    # Post-v0.1.1 round-5 review (Claude #2): the previous version of
    # this comment claimed "Order matters: the parent ArrowException
    # MUST be last" — that's FALSE. Python's ``except (A, B, C)``
    # uses isinstance against all classes in the tuple, so tuple
    # order is irrelevant here. The actual load-bearing order is
    # the order of the EXCEPT BLOCKS in ``_read_wua_parquet``
    # (TRANSIENT block before PERMANENT block), which is documented
    # there with its own DO-NOT-REORDER comment.
    #
    # Post-v0.1.0 round-2 review (Codex P2): the previous narrower
    # list dropped ``ArrowMemoryError``, ``ArrowSerializationError``,
    # ``ArrowCancelled``, ``ArrowIndexError``, and any future
    # subclass — those would escape both this function AND the cache
    # wrapper's ``except (OSError, EOFError, RuntimeError, ValueError)``
    # tuple, crashing the GUI. Including ``ArrowException`` last
    # gives forward-compatible coverage; new pyarrow exception types
    # default to "permanent" (don't waste retry budget on unknown).
    permanent = _resolve(
        "ArrowKeyError",            # missing column lookup
        "ArrowNotImplementedError", # unsupported encoding
        "ArrowTypeError",           # type coercion failure
        "ArrowCapacityError",       # >2 GB column
        "ArrowMemoryError",         # alloc failure (50 ms backoff won't help)
        "ArrowSerializationError",  # cannot serialize
        "ArrowCancelled",           # operation cancelled (user-driven)
        "ArrowIndexError",          # out-of-bounds
        "ArrowException",           # forward-compat fallback (parent)
    )
    return transient, permanent


# Module-level: built once at import. Tests assert against these
# tuples directly to detect vendor-pyarrow downgrades and the
# transient-vs-permanent partition.
_ARROW_TRANSIENT, _ARROW_PERMANENT = _build_arrow_catch_tuples()


class MissingParquetBackend(RuntimeError):
    """Neither pyarrow nor GDAL/OGR is importable.

    Inherits from ``RuntimeError`` so the GUI direct-call sites'
    existing ``except (..., RuntimeError)`` still surfaces a friendly
    QMessageBox. The cache retry loop in
    ``Controller._read_xs_rows_cached`` checks for this subtype
    *before* the broader RuntimeError clause so it short-circuits
    instead of burning the retry budget on a permanent install
    problem (round-2 review — Claude P1 #3 + Gemini).
    """


class ParquetSchemaError(RuntimeError):
    """Permanent parquet failure that should NOT be retried.

    Used by ``_read_wua_parquet`` to normalise the four Arrow* classes
    that represent permanent schema or capacity failures
    (``ArrowKeyError``, ``ArrowNotImplementedError``, ``ArrowTypeError``,
    ``ArrowCapacityError``). Like ``MissingParquetBackend``, this
    inherits from ``RuntimeError`` so GUI direct-call sites' existing
    ``except (..., RuntimeError)`` clause continues to surface a
    friendly QMessageBox; the cache retry loop must short-circuit on
    this subtype to avoid burning ~150 ms total (50+100 ms backoff
    across 3 attempts) on a guaranteed-permanent
    failure (post-v0.1.0 round-1 — Claude #1).
    """


def _read_wua_parquet(path: str) -> list[dict[str, Any]]:
    """Read parquet via pyarrow (preferred) with GDAL/OGR fallback.

    Round-7 review (Codex P1): the previous implementation caught
    ``Exception`` at both backends and returned ``[]`` on failure.
    That made ``Controller._read_xs_rows_cached``'s retry-on-exception
    code unreachable in production — torn reads silently produced
    empty rows that got cached. Now only ``ImportError`` falls through
    between backends; read failures propagate so the cache layer can
    act on them.
    """
    # Catch tuples built once at module import (above). Two-tuple
    # split so transient I/O is retried by the cache wrapper while
    # permanent schema/coercion failures short-circuit (post-v0.1.0
    # round-1 — Claude #1).
    try:
        import pyarrow.parquet as pq
    except ImportError:
        pq = None
    if pq is not None:
        # ===== DO NOT REORDER THESE except CLAUSES =====
        # _ARROW_PERMANENT below contains the ``ArrowException`` parent
        # as a forward-compat fallback; ArrowInvalid (in
        # _ARROW_TRANSIENT) IS a subclass of ArrowException via the
        # MRO. Python tries except clauses in source order, so swapping
        # would silently classify all transient errors as permanent
        # and disable retry. Pinned by
        # ``test_except_clause_order_real_arrow_invalid_routes_to_oserror``
        # (post-v0.1.0 round-3 — Claude #1).
        # Phase 1: READ. Only Arrow exceptions get re-classified here.
        # Plain ValueError from pq.read_table (older/vendor pyarrow
        # paths reporting torn footer as ValueError, bad-arg errors)
        # propagates to the cache wrapper's ``except ValueError``
        # clause where it gets transient retry semantics — same as
        # v0.1.1. Post-v0.1.2 round-1 (Codex P2 + Claude #1): a
        # too-broad ValueError catch in the convert phase was
        # reclassifying these as permanent, dropping retry.
        try:
            t = pq.read_table(path)
        except _ARROW_TRANSIENT as e:
            raise OSError(f"parquet read failed: {e}") from e
        except _ARROW_PERMANENT as e:
            raise ParquetSchemaError(
                f"parquet read failed permanently ({type(e).__name__}): {e}"
            ) from e

        # Phase 2: CONVERT. Arrow exceptions during materialization
        # still get classified (Gemini round-3); plus the
        # zip(strict=True) ValueError and plain MemoryError get
        # mapped to permanent ParquetSchemaError because column-shape
        # mismatch and OOM aren't going to fix themselves with a
        # 50/100 ms retry. The ``ValueError`` catch here is SAFE
        # because pq.read_table already succeeded — any ValueError
        # reaching this point is from zip-strict or the dict-comp.
        try:
            return [
                dict(zip(t.column_names, row, strict=True))
                for row in zip(*[c.to_pylist() for c in t.columns], strict=True)
            ]
        except _ARROW_TRANSIENT as e:
            raise OSError(f"parquet conversion failed: {e}") from e
        except _ARROW_PERMANENT as e:
            raise ParquetSchemaError(
                f"parquet conversion failed permanently ({type(e).__name__}): {e}"
            ) from e
        except ValueError as e:
            raise ParquetSchemaError(
                f"parquet column-length mismatch: {e}"
            ) from e
        except MemoryError as e:
            raise ParquetSchemaError(
                f"parquet materialization OOM (MemoryError): {e}"
            ) from e
    # No pyarrow: try GDAL OGR.
    try:
        from osgeo import ogr
    except ImportError as e:
        raise MissingParquetBackend(
            "neither pyarrow nor GDAL available to read parquet"
        ) from e
    ds = ogr.Open(path)
    if ds is None:
        raise OSError(f"GDAL/OGR failed to open {path}")
    try:
        # Round-2 review (Claude P1 #1): malformed datasets can return
        # ``None`` from ``GetLayer(0)``; without this guard the next
        # ``GetLayerDefn()`` raises ``AttributeError`` which the cache
        # retry loop classifies as a programmer bug and propagates uncaught.
        layer = ds.GetLayer(0)
        if layer is None:
            raise OSError(f"GDAL/OGR returned no layer in {path}")
        defn = layer.GetLayerDefn()
        field_names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
        return [{fn: feat.GetField(fn) for fn in field_names} for feat in layer]
    finally:
        # OGR's idiomatic close: assigning ``None`` releases the C++
        # reference and frees the file handle. Long PyQt sessions
        # otherwise accumulate open fds across repeated WUA-Q opens.
        ds = None  # noqa: F841




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
            QDialog, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
            QVBoxLayout,
        )

        path, _ = QFileDialog.getOpenFileName(
            self.host.main_window(),
            "Open WUA-Q file",
            "",
            "WUA-Q (*.csv *.parquet);;All files (*)",
        )
        if not path:
            return
        # Round-1 review (Codex P2 + Claude): _read_wua_parquet now raises
        # on torn parquet (alpha.10 round-7 change); without this guard,
        # selecting a corrupt file in the dialog crashes the GUI thread
        # via the unhandled exception path.
        try:
            rows = _read_wua_csv(path) if path.endswith(".csv") else _read_wua_parquet(path)
        except (OSError, EOFError, ValueError, RuntimeError) as e:
            QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                f"Could not read {path}:\n{e}")
            return
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
        # Round-1 review: _read_wua_parquet raises on torn parquet
        # (alpha.10 round-7); collapse exception + empty-rows into one
        # error UX path so corrupt files don't escape into Qt's default
        # exception handler.
        try:
            rows = _read_wua_parquet(xs_path)
        except (OSError, EOFError, ValueError, RuntimeError) as e:
            QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                f"Could not read {xs_path}:\n{e}")
            return
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

        # Compute slug — sanitise to drop ../ and shell-special chars so
        # the user can't direct the case dir to /etc, ~/.ssh, etc. by
        # putting path traversal in the river-name field.
        import re as _re
        def _safe_slug(s: str) -> str:
            return _re.sub(r"[^a-z0-9_\-]", "_", s.lower())[:64] or "case"

        if rb_name.isChecked() and e_river.text().strip():
            slug = _safe_slug(e_river.text().strip().replace(" ", "_"))
        elif rb_polyline.isChecked() and e_polyline.text().strip():
            slug = _safe_slug(Path(e_polyline.text()).stem.replace(" ", "_"))
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

        # Re-entry guard. Without this, a second click while the first
        # solver is still running spawns a competing QThread that races
        # for the same hydraulics.nc file lock.
        existing = getattr(self, "_run_case_worker", None)
        if existing is not None and existing.isRunning():
            self.host.message_bar().pushMessage(
                "OpenLimno",
                "A run is already in progress — wait for it to finish.",
                level=1, duration=4,
            )
            return

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

        # Stash these so the click-to-profile tool can find them without
        # the GeoPackage-source heuristic — memory layers added below
        # have no on-disk source for the heuristic to grep.
        if xs_pq.is_file():
            self._xs_parquet = str(xs_pq)
        out_nc = case_dir / "out" / "hydraulics.nc"
        if out_nc.is_file():
            self._hyd_nc = str(out_nc)

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
            QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry,
            QgsPointXY, QgsProject, QgsRectangle, QgsVectorLayer,
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
                canvas_crs = controller.host.map_canvas().mapSettings().destinationCrs()
                station = None
                hit_layer = None
                for layer in cands:
                    # Click pt is in canvas CRS; layer.getFeatures expects
                    # layer CRS. Mesh / cross-section memory layers are
                    # EPSG:4326 while canvas is EPSG:3857 → without this
                    # transform the rect filters out everything.
                    layer_crs = layer.crs()
                    if layer_crs.isValid() and canvas_crs.isValid() and layer_crs != canvas_crs:
                        xform = QgsCoordinateTransform(canvas_crs, layer_crs,
                                                          QgsProject.instance())
                        try:
                            pt_l = xform.transform(pt)
                        except Exception:
                            continue
                        # Approximate tolerance in layer units by transforming
                        # a small offset point and taking the resulting delta.
                        try:
                            offset = xform.transform(QgsPointXY(pt.x() + tol, pt.y()))
                            tol_l = abs(offset.x() - pt_l.x()) or tol
                        except Exception:
                            tol_l = tol
                    else:
                        pt_l = pt
                        tol_l = tol
                    bb = QgsRectangle(pt_l.x() - tol_l, pt_l.y() - tol_l,
                                        pt_l.x() + tol_l, pt_l.y() + tol_l)
                    req = QgsFeatureRequest().setFilterRect(bb)
                    feats = list(layer.getFeatures(req))
                    if not feats:
                        continue
                    pt_geom = QgsGeometry.fromPointXY(pt_l)
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

    def _read_xs_rows_cached(self, path: str, max_retries: int = 3) -> list:
        """Read cross_section.parquet rows with a stat→read→stat guard.

        Round-3 review (codex+gemini+claude unanimous) found the previous
        cache implementation cemented torn rows when the file was rewritten
        during the read: post-read stat agreed with new on-disk metadata,
        so subsequent clicks served the corrupt cache forever. The correct
        pattern is:
            pre = stat()
            rows = read()
            post = stat()
            if pre == post: cache (rows, pre); return rows
            else: retry (file was rewritten mid-read)

        On stat failure (file deleted/unmounted), prefer serving the
        previously-cached rows over crashing — better UX, and the user
        will see the next legitimate read fail with a real error.
        """
        # Normalize so cache keys are stable across cwd changes (Qt file
        # dialogs sometimes ``chdir``).
        path = os.path.realpath(path)
        cache = getattr(self, "_xs_rows_cache", {})

        def _stat(p):
            try:
                return (os.path.getmtime(p), os.path.getsize(p))
            except OSError:
                return None

        cur = _stat(path)
        # Cache hit — fast path
        if (cur is not None
                and cache.get("path") == path
                and cache.get("stat") == cur):
            return cache["rows"]
        # Stat failed — keep stale cache rather than crash
        if cur is None and cache.get("path") == path and cache.get("rows"):
            return cache["rows"]
        # Cache miss: read with TOCTOU guard. Each transient failure
        # mode (stat-fails, parquet-read-raises, post-stat-None, pre/post
        # disagree) records last_error and continues into the next
        # attempt — only when retries are exhausted do we fall back to
        # the prior cache or raise. Round-6 fixes:
        #   - Codex P2 / Claude P1: ``post is None`` was raising on
        #     attempt 0, defeating the retry budget for `mv -f`-style
        #     transient unlinks. Now it `continue`s.
        #   - Gemini P0: parquet readers raise on torn input
        #     (ArrowInvalid, EOFError, OSError). The previous code
        #     let those propagate out, bypassing retry. Wrap.
        #   - Claude P1: ``cache.get("rows")`` was falsy on empty
        #     rows; an empty parquet would be treated as no-cache.
        #     Use ``"rows" in cache`` instead.
        last_error = None
        for attempt in range(max_retries):
            if attempt > 0:
                time.sleep(0.05 * attempt)
            pre = _stat(path)
            if pre is None:
                last_error = OSError(f"cannot stat {path}")
                continue
            # ===== DO NOT REORDER THESE except CLAUSES =====
            # Both MissingParquetBackend and ParquetSchemaError inherit
            # from RuntimeError (so GUI direct-call sites' existing
            # except-tuple catches them with a friendly QMessageBox).
            # The cache short-circuit MUST come before the broader
            # RuntimeError clause below — otherwise both permanent
            # classes get caught as transient and retried 3× with
            # backoff, undoing the whole point of the dedicated
            # subclasses. Pinned by
            # ``test_cache_loop_except_clause_order_pins_short_circuit``
            # (post-v0.1.1 round-1 — Claude).
            try:
                rows = _read_wua_parquet(path)
            except (MissingParquetBackend, ParquetSchemaError):
                # Permanent failures: install missing or schema/capacity
                # error. No amount of retry will fix these.
                raise
            except (OSError, EOFError, RuntimeError) as e:
                # Round-7 review (all 3): narrow from `except Exception`
                # to the transient I/O / read-failure family. Don't
                # swallow programmer bugs (TypeError, AttributeError,
                # KeyError) under the retry banner. ArrowInvalid is a
                # subclass of OSError in newer pyarrow, ValueError in
                # older — we add ValueError as a safety net below.
                last_error = e
                continue
            except ValueError as e:
                # pyarrow.lib.ArrowInvalid on torn footers used to be
                # ValueError. Treat as transient.
                last_error = e
                continue
            post = _stat(path)
            if post is None:
                last_error = FileNotFoundError(
                    f"{path} vanished during read")
                continue
            if pre == post:
                self._xs_rows_cache = {"path": path, "stat": pre, "rows": rows}
                return rows
            last_error = RuntimeError(f"{path} changed during read")
        # Retries exhausted. Prefer prior cache (from a clean read)
        # over raising — caller's downstream logic handles "rows looks
        # familiar" better than "file disappeared". Use ``"rows" in
        # cache`` so an empty list (legitimate) still hits.
        if cache.get("path") == path and "rows" in cache:
            return cache["rows"]
        raise last_error or RuntimeError(f"unable to read {path} stably")

    def _plot_at_station(self, station: float) -> None:
        from qgis.PyQt.QtWidgets import (
            QComboBox, QDialog, QDialogButtonBox, QFormLayout, QMessageBox,
        )

        if not self._xs_parquet:
            QMessageBox.warning(self.host.main_window(), "OpenLimno",
                                  "No cross_section.parquet selected.")
            return
        cache_key = self._xs_parquet
        rows = self._read_xs_rows_cached(cache_key)
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
