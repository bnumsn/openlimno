"""Headless integration tests for the QGIS plugin shim.

Exercises the same code path that QGIS' plugin manager uses
(``__init__`` → ``initGui`` → trigger an action → ``unload``) against
a mock ``iface``. This catches regressions in the gui_core →
plugin.py wiring without spinning up a full QGIS desktop session.

Skipped automatically if the bundled QGIS Python is not importable —
i.e. CI runs missing the ``qgis`` apt package.
"""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("qgis", reason="qgis bindings not on path")
pytest.importorskip("qgis.core", reason="qgis.core not importable")

from qgis.core import QgsApplication  # noqa: E402


@pytest.fixture(scope="module")
def qgs_app():
    """One QgsApplication per test module — initQgis is expensive."""
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)  # gui_enabled=False → offscreen
    app.initQgis()
    yield app
    app.exitQgis()


class _MockIface:
    """Minimal iface stub matching the methods the plugin shim uses."""

    def __init__(self):
        from qgis.gui import QgsMapCanvas, QgsMessageBar
        from qgis.PyQt.QtWidgets import QMainWindow

        self._mw = QMainWindow()
        self._canvas = QgsMapCanvas(self._mw)
        self._bar = QgsMessageBar(self._mw)
        self._menu_actions: list = []
        self._toolbar_actions: list = []

    def mainWindow(self): return self._mw
    def mapCanvas(self): return self._canvas
    def messageBar(self): return self._bar

    def statusBarIface(self):
        sb = self._mw.statusBar()
        class _S:
            def showMessage(self, m, t=0): sb.showMessage(m, t)
            def clearMessage(self): sb.clearMessage()
        return _S()

    def addPluginToMenu(self, _menu, action):
        self._menu_actions.append(action)

    def addToolBarIcon(self, action):
        self._toolbar_actions.append(action)

    def removePluginMenu(self, _menu, action):
        if action in self._menu_actions:
            self._menu_actions.remove(action)

    def removeToolBarIcon(self, action):
        if action in self._toolbar_actions:
            self._toolbar_actions.remove(action)


@pytest.fixture
def plugin(qgs_app):
    """Fresh plugin + mock iface per test."""
    # Make sure /usr/lib/python3/dist-packages comes AFTER user site —
    # see openlimno.studio.__main__._ensure_qgis_importable for the why.
    if "/usr/lib/python3/dist-packages" in sys.path:
        sys.path.remove("/usr/lib/python3/dist-packages")
        sys.path.append("/usr/lib/python3/dist-packages")
    from openlimno.qgis.openlimno_qgis_plugin.plugin import OpenLimnoPlugin

    iface = _MockIface()
    p = OpenLimnoPlugin(iface)
    p.initGui()
    yield p, iface
    p.unload()


def test_plugin_wires_six_actions(plugin):
    """initGui() should add six menu entries: Open hydraulic, Open WUA-Q,
    Plot xs, Click xs, Build OSM, Run case.
    """
    p, iface = plugin
    assert len(p.actions) == 6
    titles = [a.text() for a in p.actions]
    assert any("hydraulic" in t.lower() for t in titles), titles
    assert any("wua-q" in t.lower() for t in titles), titles
    assert any("plot" in t.lower() and "cross" in t.lower() for t in titles)
    assert any("click" in t.lower() for t in titles)
    assert any("build" in t.lower() and "osm" in t.lower() for t in titles)
    assert any("run case" in t.lower() for t in titles)
    # Toolbar gets a subset (the most-used ones)
    assert len(iface._toolbar_actions) >= 4


def test_pick_action_is_checkable(plugin):
    """The click-cross-section tool toggles, so its action must be
    checkable AND wired into Controller._pick_action so the controller
    can un-check it on cancellation."""
    p, _ = plugin
    pick = next(a for a in p.actions if "click" in a.text().lower())
    assert pick.isCheckable()
    assert p.ctl._pick_action is pick


def test_controller_methods_callable(plugin):
    """Each action's slot must exist on Controller — protects against
    typos in the wiring after the gui_core refactor."""
    p, _ = plugin
    for method in ("open_hydraulic_nc", "open_wua_q", "plot_cross_section",
                     "activate_pick_tool", "build_case_from_osm", "run_case"):
        assert callable(getattr(p.ctl, method)), method


def test_read_parquet_async_runs_off_main_thread(plugin, tmp_path):
    """``Controller._read_parquet_async`` must run the read on a
    background QThread, then dispatch ``on_success`` back on the main
    thread once the worker emits. Pins the contract that the GUI
    doesn't freeze on parquet I/O.

    Captures the thread id where ``read_fn`` ran and asserts it
    differs from the main thread.
    """
    import threading

    from qgis.PyQt.QtCore import QEventLoop, QTimer

    p, _ = plugin
    ctl = p.ctl
    main_thread_id = threading.get_ident()

    captured: dict = {"rows": None, "read_thread_id": None, "error": None}

    def slow_read(path: str) -> list:
        # If this ran on the main thread, thread.get_ident() would
        # match main_thread_id.
        captured["read_thread_id"] = threading.get_ident()
        return [{"row": "ok", "path": path}]

    def on_success(rows) -> None:
        captured["rows"] = rows
        loop.quit()

    def on_error(msg: str) -> None:
        captured["error"] = msg
        loop.quit()

    # Spin a local event loop so the worker's signal can reach us.
    loop = QEventLoop()
    QTimer.singleShot(3000, loop.quit)  # safety timeout

    ctl._read_parquet_async(str(tmp_path / "fake.parquet"), slow_read,
                             on_success, on_error, "test read")
    loop.exec()

    assert captured["error"] is None, captured["error"]
    assert captured["rows"] == [{"row": "ok", "path": str(tmp_path / "fake.parquet")}]
    assert captured["read_thread_id"] is not None
    assert captured["read_thread_id"] != main_thread_id, (
        "read_fn ran on the main thread — the QThread offload regressed"
    )
    assert ctl._read_in_flight is False, (
        "_read_in_flight should reset to False once the worker dispatches"
    )
    assert ctl._async_handles == set(), (
        "async handle should be removed once cleanup runs"
    )


def test_read_parquet_async_dedupes_concurrent_reads(plugin, tmp_path):
    """While a read is in flight, additional ``_read_parquet_async``
    calls must be dropped rather than spawning competing workers
    that race on the cache.
    """
    from qgis.PyQt.QtCore import QEventLoop, QTimer

    p, _ = plugin
    ctl = p.ctl

    state = {"first_started": False}

    def first_read(path: str) -> list:
        state["first_started"] = True
        # Block briefly so the second call lands while we're in-flight.
        import time
        time.sleep(0.1)
        return [{"first": True}]

    def second_read(path: str) -> list:
        raise AssertionError("second read must not run — first is in flight")

    results: dict = {"first_rows": None, "second_called": False}

    def first_success(rows) -> None:
        results["first_rows"] = rows

    def second_success(rows) -> None:
        results["second_called"] = True

    def noop_error(msg: str) -> None:
        pass

    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)  # safety timeout

    # Kick off first read.
    ctl._read_parquet_async(str(tmp_path / "a.parquet"), first_read,
                             first_success, noop_error, "first")
    # Immediately attempt a second — must be dropped.
    ctl._read_parquet_async(str(tmp_path / "b.parquet"), second_read,
                             second_success, noop_error, "second")

    # Run the loop until both signals have processed (or timeout).
    def _check() -> None:
        if results["first_rows"] is not None:
            loop.quit()

    timer = QTimer()
    timer.timeout.connect(_check)
    timer.start(50)
    loop.exec()
    timer.stop()

    assert results["first_rows"] == [{"first": True}]
    assert results["second_called"] is False, (
        "second async read should have been dropped while the first was "
        "in flight — cache-race protection regressed"
    )


def test_unload_removes_everything(qgs_app):
    """unload() must drop every menu + toolbar entry it added —
    otherwise reloading the plugin in QGIS leaves duplicates."""
    if "/usr/lib/python3/dist-packages" in sys.path:
        sys.path.remove("/usr/lib/python3/dist-packages")
        sys.path.append("/usr/lib/python3/dist-packages")
    from openlimno.qgis.openlimno_qgis_plugin.plugin import OpenLimnoPlugin

    iface = _MockIface()
    p = OpenLimnoPlugin(iface)
    p.initGui()
    assert len(iface._menu_actions) == 6
    p.unload()
    assert len(iface._menu_actions) == 0
    assert len(iface._toolbar_actions) == 0
    assert p.actions == []
