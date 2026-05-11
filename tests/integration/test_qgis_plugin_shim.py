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


def test_read_parquet_async_does_not_leak_qobjects(plugin, tmp_path):
    """Successive async reads must not accumulate QObjects.

    Without explicit ``worker.deleteLater() / thread.deleteLater() /
    progress.deleteLater()`` plus signal disconnect, the Python↔Qt
    signal connections form ref cycles Python's GC can't break. Pre-
    fix this leaked ~2 QObjects per read; over a long PyQt session
    (hundreds of file opens) that adds up to thousands of dead Qt
    objects holding C++ memory.

    Pins the bounded-leak contract: after N reads, the net new QObject
    count must NOT scale linearly with N.
    """
    import gc
    from qgis.PyQt.QtCore import QEventLoop, QObject, QTimer

    p, _ = plugin
    ctl = p.ctl

    def trivial(path: str):
        return [{"x": 1}]

    def _qobject_count() -> int:
        gc.collect()
        return sum(1 for obj in gc.get_objects() if isinstance(obj, QObject))

    def _spin_event_loop(ms: int = 200) -> None:
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

    # Warm up so any one-shot setup objects materialise before baseline.
    state = {"done": False}
    ctl._read_parquet_async("/warm", trivial,
                             lambda r: state.update(done=True),
                             lambda m: None, "warm")
    while not state["done"]:
        _spin_event_loop(50)
    _spin_event_loop(200)  # drain deferred-delete queue
    baseline = _qobject_count()

    # Do N reads and measure.
    N = 25
    for i in range(N):
        st = {"done": False}
        ctl._read_parquet_async(f"/p{i}", trivial,
                                 lambda r, st=st: st.update(done=True),
                                 lambda m: None, "n")
        while not st["done"]:
            _spin_event_loop(50)

    _spin_event_loop(500)  # let all deleteLater() drain
    after = _qobject_count()

    leak_per_read = (after - baseline) / N
    assert leak_per_read < 0.5, (
        f"REGRESSION: {leak_per_read:.2f} QObjects leaked per async read "
        f"(baseline {baseline}, after {N} reads {after}). Without "
        f"worker/thread/progress .deleteLater() + signal disconnect, "
        f"each async read leaks ~2 QObjects from the Python↔Qt signal "
        f"ref cycle. Over a long session this is hundreds of dead Qt "
        f"objects holding C++ memory."
    )


def test_read_parquet_async_uncaught_exception_dispatches_error(plugin, tmp_path):
    """If ``read_fn`` raises an exception outside the cache wrapper's
    narrow tuple (e.g., a programmer-bug TypeError or AttributeError),
    the worker must still emit ``error`` so:

    1. ``_read_in_flight`` resets to False (else ALL subsequent reads
       are silently dropped — clicking buttons does nothing forever).
    2. The progress dialog closes (else GUI is modal-locked).
    3. The thread cleans up (else "QThread: Destroyed while still
       running" warning).

    The error message must include the exception type + traceback
    so the bug is visible to the user instead of silently breaking
    every subsequent click.
    """
    from qgis.PyQt.QtCore import QEventLoop, QTimer

    p, _ = plugin
    ctl = p.ctl

    captured: dict = {"error_msg": None, "success_called": False}

    def bad_read(path: str):
        # Programmer-bug class outside the old narrow except tuple.
        raise TypeError("simulated programmer bug")

    def on_success(rows) -> None:
        captured["success_called"] = True

    def on_error(msg: str) -> None:
        captured["error_msg"] = msg

    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)
    ctl._read_parquet_async(str(tmp_path / "x.parquet"), bad_read,
                             on_success, on_error, "test")
    loop.exec()

    assert captured["error_msg"] is not None, (
        "REGRESSION: uncaught TypeError in worker did not route to "
        "on_error — the GUI would hang with the progress dialog stuck "
        "modal forever and _read_in_flight stuck True."
    )
    assert "TypeError" in captured["error_msg"], (
        "Error message should surface the exception type so the user "
        "can see the underlying bug"
    )
    assert "simulated programmer bug" in captured["error_msg"]
    assert not captured["success_called"]
    assert ctl._read_in_flight is False, (
        "REGRESSION: _read_in_flight stuck at True after an uncaught "
        "exception — every subsequent _read_parquet_async call would "
        "be silently dropped."
    )
    assert ctl._async_handles == set(), (
        "REGRESSION: thread/worker/dialog handle leaked after uncaught "
        "exception — QThread will be destroyed while still running."
    )


def test_read_parquet_async_dedupes_concurrent_reads(plugin, tmp_path):
    """While a read is in flight, additional ``_read_parquet_async``
    calls must be dropped (no competing worker) AND route the caller
    to ``on_error`` with a "busy" message so the user knows the click
    was acknowledged. Silent drop made the map-click path feel broken.
    """
    from qgis.PyQt.QtCore import QEventLoop, QTimer

    p, _ = plugin
    ctl = p.ctl

    def first_read(path: str) -> list:
        # Block briefly so the second call lands while we're in-flight.
        import time
        time.sleep(0.1)
        return [{"first": True}]

    def second_read(path: str) -> list:
        raise AssertionError("second read must not run — first is in flight")

    results: dict = {
        "first_rows": None,
        "second_called": False,
        "second_error_msg": None,
    }

    def first_success(rows) -> None:
        results["first_rows"] = rows

    def second_success(rows) -> None:
        results["second_called"] = True

    def second_error(msg: str) -> None:
        results["second_error_msg"] = msg

    def noop_error(msg: str) -> None:
        pass

    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)  # safety timeout

    # Kick off first read.
    ctl._read_parquet_async(str(tmp_path / "a.parquet"), first_read,
                             first_success, noop_error, "first")
    # Immediately attempt a second — must be dropped AND notify caller.
    ctl._read_parquet_async(str(tmp_path / "b.parquet"), second_read,
                             second_success, second_error, "second")

    # Run the loop until first signal processes (or timeout).
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
        "second async read must NOT run — would race on cache"
    )
    assert results["second_error_msg"] is not None, (
        "REGRESSION: deduped second call silently dropped without "
        "feedback — user has no indication their click was received. "
        "_read_parquet_async should route through on_error when "
        "_read_in_flight is already True."
    )
    assert "progress" in results["second_error_msg"].lower() or \
           "wait" in results["second_error_msg"].lower(), (
        f"on_error message should explain the busy state, got: "
        f"{results['second_error_msg']!r}"
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
