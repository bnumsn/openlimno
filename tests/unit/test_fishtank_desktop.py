"""Desktop app tests — headless.

The controller layer is pure (no Qt) and fully tested. The GUI smoke test runs
under the Qt ``offscreen`` platform and is skipped where PySide6 is absent, so
the suite stays green on CI/build hosts without Qt while still catching GUI
regressions (e.g. run-buttons-not-wired, charts-not-drawn) where Qt is present.
"""

from __future__ import annotations

import os

import pytest

from openlimno.fishtank.desktop import controller as ctrl


# ---- pure controller (no Qt) ------------------------------------------------
def test_list_presets_has_sixteen_with_ids_and_payloads():
    presets = ctrl.list_presets()
    assert len(presets) == 16
    assert all({"id", "label_zh", "payload"} <= set(p) for p in presets)


def test_run_ode_and_abm_return_timeseries():
    payload = ctrl.preset_payload("mature_stocked_tank")
    ode = ctrl.run_ode(payload)
    abm = ctrl.run_abm(payload)
    assert len(ode["timeseries"]) > 0
    assert len(abm["timeseries"]) > 0


def test_series_from_timeseries_selects_present_keys_only():
    ode = ctrl.run_ode(ctrl.preset_payload("fishless_cycle"))
    days, series = ctrl.series_from_timeseries(ode, ctrl.NITROGEN_SERIES)
    assert len(series) == 3  # TAN/NO2/NO3 all present
    assert {s["key"] for s in series} == {"TAN", "NO2", "NO3"}
    assert all(len(s["values"]) == len(days) for s in series)


def test_kpis_and_status_line():
    ode = ctrl.run_ode(ctrl.preset_payload("mature_stocked_tank"))
    abm = ctrl.run_abm(ctrl.preset_payload("mature_stocked_tank"))
    assert len(ctrl.summary_kpis(ode)) == 6
    assert ctrl.summary_kpis(None) == []
    line = ctrl.status_line(ode, abm)
    assert "行 ODE" in line and "ABM 个体" in line
    assert ctrl.status_line(None, None).startswith("已就绪")


# ---- Qt offscreen GUI smoke -------------------------------------------------
def test_gui_smoke_runs_and_draws():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from openlimno.fishtank.desktop.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    # select a stocked scenario so the ABM has fish
    ids = [win.preset.itemData(i) for i in range(win.preset.count())]
    win.preset.setCurrentIndex(ids.index("mature_stocked_tank"))

    win._run_both()
    app.processEvents()

    # the three run buttons exist on the always-visible toolbar
    assert win.btn_ode.text() == "运行 方程模型(ODE)"
    assert win.btn_abm.text() == "运行 个体模型(ABM)"
    assert win.btn_both.text() == "运行 两者(ODE+ABM)"
    # charts drew: nitrogen (3) + biofilm (3) + compare overlay (ODE+ABM >= 8)
    assert len(win.chart_n.ax.lines) == 3
    assert len(win.chart_bio.ax.lines) == 3
    assert len(win.chart_cmp.ax.lines) >= 8
    assert win.table.rowCount() > 0
    assert "运行完成" in win.statusBar().currentMessage()
