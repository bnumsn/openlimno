"""Fishtank desktop main window (PySide6) — a thin view over ``controller``.

Reads widgets → patches the active payload → calls the headless controller →
renders the returned series/KPIs. No model maths here. The three run actions
live in an always-visible toolbar (a native toolbar can't be scrolled off
screen — the failure mode the browser sidebar had).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import controller as ctrl
from .charts import LineChart


def _dig(d: dict[str, Any], path: tuple[str, ...], default: float) -> float:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def _put(d: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cur = d
    for k in path[:-1]:
        cur = cur.setdefault(k, {})
    cur[path[-1]] = value


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenLimno 鱼缸 Studio (桌面版)")
        self.resize(1180, 760)
        self.payload: dict[str, Any] = ctrl.default_payload()
        self.ode: dict[str, Any] | None = None
        self.abm: dict[str, Any] | None = None

        self._build_toolbar()
        self._build_body()
        self._load_preset_into_fields(self.payload)
        self.statusBar().showMessage(ctrl.status_line(None, None))

    # ---- layout ---------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = self.addToolBar("运行")
        tb.setMovable(False)
        tb.addWidget(QLabel("  预设案例: "))
        self.preset = QComboBox()
        for p in ctrl.list_presets():
            self.preset.addItem(p["label_zh"], p["id"])
        self.preset.currentIndexChanged.connect(self._on_preset)
        tb.addWidget(self.preset)
        tb.addSeparator()
        self.btn_ode = QPushButton("运行 方程模型(ODE)")
        self.btn_abm = QPushButton("运行 个体模型(ABM)")
        self.btn_both = QPushButton("运行 两者(ODE+ABM)")
        self.btn_ode.setDefault(True)
        for b, fn in (
            (self.btn_ode, self._run_ode),
            (self.btn_abm, self._run_abm),
            (self.btn_both, self._run_both),
        ):
            b.clicked.connect(fn)
            tb.addWidget(b)

    def _build_body(self) -> None:
        split = QSplitter(Qt.Orientation.Horizontal)

        # left: editable key parameters
        panel = QWidget()
        form = QFormLayout(panel)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color:#475569;")
        form.addRow(self.desc)
        self.f_days = QDoubleSpinBox()
        self.f_days.setRange(0, 3650)
        self.f_days.setDecimals(0)
        self.f_temp = QDoubleSpinBox()
        self.f_temp.setRange(0, 40)
        self.f_temp.setDecimals(1)
        self.f_dose = QDoubleSpinBox()
        self.f_dose.setRange(0, 50)
        self.f_dose.setDecimals(2)
        self.f_fish = QSpinBox()
        self.f_fish.setRange(0, 80)
        self.f_feed = QDoubleSpinBox()
        self.f_feed.setRange(0, 50)
        self.f_feed.setDecimals(2)
        self.f_seed = QSpinBox()
        self.f_seed.setRange(0, 999999)
        form.addRow("天数", self.f_days)
        form.addRow("温度 °C", self.f_temp)
        form.addRow("投氨速率 mg-N/L/天", self.f_dose)
        form.addRow("鱼数量 (ABM)", self.f_fish)
        form.addRow("投喂 g/天 (ABM)", self.f_feed)
        form.addRow("随机种子 (ABM)", self.f_seed)
        kpibox = QWidget()
        self.kpi_layout = QVBoxLayout(kpibox)
        self.kpi_layout.addWidget(QLabel("<b>结果指标</b>"))
        form.addRow(kpibox)
        self.warn = QPlainTextEdit()
        self.warn.setReadOnly(True)
        self.warn.setMaximumHeight(120)
        form.addRow(QLabel("预警"))
        form.addRow(self.warn)

        # right: result tabs
        self.tabs = QTabWidget()
        nwrap = QWidget()
        nlay = QVBoxLayout(nwrap)
        self.chart_n = LineChart("mg-N/L")
        self.chart_bio = LineChart("mg/L")
        nlay.addWidget(self.chart_n)
        nlay.addWidget(self.chart_bio)
        self.chart_cmp = LineChart("mg/L")
        self.table = QTableWidget()
        self.tabs.addTab(nwrap, "氮循环 / 生物膜")
        self.tabs.addTab(self.chart_cmp, "对比 ODE vs ABM")
        self.tabs.addTab(self.table, "时间序列数据")

        split.addWidget(panel)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([320, 860])
        self.setCentralWidget(split)

    # ---- payload <-> fields --------------------------------------------
    def _load_preset_into_fields(self, payload: dict[str, Any]) -> None:
        self.f_days.setValue(_dig(payload, ("run", "days"), 42))
        self.f_temp.setValue(_dig(payload, ("tank", "temperature_c"), 25))
        self.f_dose.setValue(_dig(payload, ("parameters", "ammonia_dose_mg_n_l_day"), 2))
        self.f_fish.setValue(int(_dig(payload, ("agents", "fish_count"), 6)))
        self.f_feed.setValue(_dig(payload, ("agents", "feed_g_day"), 0.3))
        self.f_seed.setValue(int(_dig(payload, ("agents", "seed"), 42)))

    def _payload_with_fields(self) -> dict[str, Any]:
        import copy

        p = copy.deepcopy(self.payload)
        _put(p, ("run", "days"), self.f_days.value())
        _put(p, ("tank", "temperature_c"), self.f_temp.value())
        _put(p, ("parameters", "ammonia_dose_mg_n_l_day"), self.f_dose.value())
        _put(p, ("agents", "fish_count"), self.f_fish.value())
        _put(p, ("agents", "feed_g_day"), self.f_feed.value())
        _put(p, ("agents", "seed"), self.f_seed.value())
        return p

    # ---- actions --------------------------------------------------------
    def _on_preset(self) -> None:
        name = self.preset.currentData()
        self.payload = ctrl.preset_payload(name)
        info = next((p for p in ctrl.list_presets() if p["id"] == name), None)
        self.desc.setText(info["description_zh"] if info else "")
        self._load_preset_into_fields(self.payload)

    def _run_ode(self) -> None:
        self.statusBar().showMessage("运行中…")
        try:
            self.ode = ctrl.run_ode(self._payload_with_fields())
        except Exception as exc:  # noqa: BLE001 - surface model errors in the status bar
            self.statusBar().showMessage(f"错误: {exc}")
            return
        self._render()

    def _run_abm(self) -> None:
        self.statusBar().showMessage("运行 ABM 中…")
        try:
            self.abm = ctrl.run_abm(self._payload_with_fields())
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"错误: {exc}")
            return
        self._render()

    def _run_both(self) -> None:
        self.statusBar().showMessage("运行中…")
        try:
            pf = self._payload_with_fields()
            self.ode = ctrl.run_ode(pf)
            self.abm = ctrl.run_abm(pf)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"错误: {exc}")
            return
        self._render()

    # ---- render ---------------------------------------------------------
    def _render(self) -> None:
        if self.ode:
            d, n = ctrl.series_from_timeseries(self.ode, ctrl.NITROGEN_SERIES)
            self.chart_n.plot(d, n, "mg-N/L")
            d2, b = ctrl.series_from_timeseries(self.ode, ctrl.OXYGEN_SERIES)
            self.chart_bio.plot(d2, b, "mg/L")
            self._render_kpis(ctrl.summary_kpis(self.ode))
            self.warn.setPlainText("\n".join(ctrl.warnings_of(self.ode)) or "（无阈值预警）")
            self._render_table(self.ode)
        if self.ode and self.abm:
            do, so = ctrl.series_from_timeseries(self.ode, ctrl.COMPARE_SERIES)
            da, sa = ctrl.series_from_timeseries(self.abm, ctrl.COMPARE_SERIES)
            self.chart_cmp.plot_compare(do, so, da, sa, "mg/L")
        self.statusBar().showMessage(ctrl.status_line(self.ode, self.abm))

    def _render_kpis(self, kpis: list[tuple[str, str]]) -> None:
        while self.kpi_layout.count() > 1:
            item = self.kpi_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        for label, value in kpis:
            self.kpi_layout.addWidget(QLabel(f"{label}: <b>{value}</b>"))

    def _render_table(self, ode: dict[str, Any]) -> None:
        cols = ["day", "TAN", "NO2", "NO3", "DO", "NH3_free", "pH"]
        rows = ode.get("timeseries", []) or []
        # show first 40 and last 40 to keep it light
        show = rows if len(rows) <= 80 else rows[:40] + rows[-40:]
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(show))
        for r, row in enumerate(show):
            for cidx, col in enumerate(cols):
                self.table.setItem(r, cidx, QTableWidgetItem(f"{row.get(col, '')}"))
