"""QGIS plugin smoke tests.

The plugin module imports lazily; these tests only verify the file loads
without QGIS APIs (importing `qgis.PyQt` is gated). True functional testing
requires QGIS and is documented in the plugin README's manual test plan.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_plugin_module_importable_without_qgis() -> None:
    """Plugin module must import even when running outside QGIS Python.

    Inside-QGIS imports are gated within method bodies so the module-level
    import succeeds in any environment.
    """
    from openlimno.qgis.openlimno_qgis_plugin import plugin

    assert hasattr(plugin, "OpenLimnoPlugin")


def test_plugin_class_factory_signature() -> None:
    from openlimno.qgis.openlimno_qgis_plugin import classFactory

    # iface arg is required; we don't actually instantiate without QGIS
    assert callable(classFactory)


def test_plugin_metadata_present() -> None:
    here = Path(__file__).resolve().parents[2]
    meta = here / "src" / "openlimno" / "qgis" / "openlimno_qgis_plugin" / "metadata.txt"
    assert meta.exists()
    text = meta.read_text(encoding="utf-8")
    assert "name=OpenLimno" in text
    assert "qgisMinimumVersion=3.34" in text
    assert "Apache-2.0" in text


def test_plugin_csv_helper_handles_openlimno_header(tmp_path: Path) -> None:
    """Helper should skip OpenLimno '#'-prefixed comment lines."""
    # The CSV/parquet readers moved from OpenLimnoPlugin (a thin shim
    # over the controller) to module-level helpers in
    # ``openlimno.gui_core.controller`` once the QGIS-plugin and
    # standalone-Studio paths shared a Controller class.
    from openlimno.gui_core.controller import _read_wua_csv

    csv_path = tmp_path / "wua_q.csv"
    csv_path.write_text(
        "# OpenLimno output header\n"
        "# annual_avg=5.11\n"
        "discharge_m3s,wua_m2_oncorhynchus_mykiss_spawning\n"
        "1.0,18.0\n"
        "5.0,62.0\n"
    )
    rows = _read_wua_csv(str(csv_path))
    # Comment-prefix rows skipped, data rows parsed
    assert len(rows) == 2
    assert "discharge_m3s" in rows[0]


def test_plugin_parquet_helper_returns_list(tmp_path: Path) -> None:
    """Helper should read parquet via pyarrow if available, list of dicts."""
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    import pandas as pd

    df = pd.DataFrame({"discharge_m3s": [1.0, 2.0], "wua": [10.0, 20.0]})
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(tmp_path / "wua.parquet"))

    from openlimno.gui_core.controller import _read_wua_parquet

    rows = _read_wua_parquet(str(tmp_path / "wua.parquet"))
    assert len(rows) == 2
    assert rows[0]["discharge_m3s"] == 1.0


# ---------------------------------------------------------------------
# v0.7 — Fetcher integration smoke (no Qt needed; just API surface)
# ---------------------------------------------------------------------
def test_v07_fetch_data_into_case_method_exists():
    """Pin that Controller exposes ``fetch_data_into_case`` so the QGIS
    plugin's '⬇ Fetch data into case…' toolbar entry has a binding
    target. Any rename / removal would silently break the plugin
    (toolbar entry would point at AttributeError on click).
    """
    from openlimno.gui_core.controller import Controller
    ctl = Controller(host=None)  # type: ignore[arg-type]
    assert hasattr(ctl, "fetch_data_into_case")
    assert callable(ctl.fetch_data_into_case)
    assert hasattr(ctl, "_on_fetch_finished")
    assert callable(ctl._on_fetch_finished)


def test_v07_qgis_plugin_wires_fetch_toolbar_entry():
    """And pin that the plugin file references the method — without
    this the controller method exists but no GUI surface exposes it."""
    import inspect

    from openlimno.qgis.openlimno_qgis_plugin import plugin as _plugin_mod
    src = inspect.getsource(_plugin_mod)
    assert "fetch_data_into_case" in src, (
        "REGRESSION: QGIS plugin no longer wires "
        "ctl.fetch_data_into_case — the toolbar lost its entry point."
    )


def test_v08_fetch_data_into_case_uses_qprocess_not_qthread():
    """v0.8 regression pin: ``fetch_data_into_case`` must use
    ``QProcess`` (subprocess isolation), not ``QThread`` (in-process).
    The whole point of the v0.8 refactor is that a fetcher crash
    can't take the QGIS process with it. If a future refactor
    swaps back to QThread that crash-isolation goes away."""
    import inspect

    from openlimno.gui_core.controller import Controller
    src = inspect.getsource(Controller.fetch_data_into_case)
    assert "QProcess" in src, (
        "REGRESSION: fetch_data_into_case no longer uses QProcess; "
        "subprocess crash isolation is gone."
    )
    # And: the openlimno fetch CLI subcommand it relies on must exist.
    from openlimno.cli import main as _main
    fetch_cmd = _main.commands.get("fetch")
    assert fetch_cmd is not None, (
        "REGRESSION: `openlimno fetch` CLI subcommand removed — "
        "fetch_data_into_case's QProcess will fail with "
        "'No such command' on the next user click."
    )


# ---------------------------------------------------------------------
# v2.9.0 — Studio GUI's run-case worker must delegate to the headless API
# ---------------------------------------------------------------------
def test_v290_run_case_worker_delegates_to_headless_api() -> None:
    """v2.9.0 regression pin: ``Controller.run_case`` must call into
    ``run_case_with_plots`` from ``openlimno.studio.headless`` rather
    than inline ``Case.from_yaml`` + ``case.run()``.

    Why this matters: v2.3.0 shipped ``run_case_with_plots`` as the
    single supported entry-point that the CLI and Studio share. The
    QGIS-plugin worker was the last caller still inlining the chain
    — that divergence meant Studio runs skipped the canonical WUA-Q
    plot and the HSI quality-grade in the status line. v2.9.0
    consolidates them; reverting would silently re-fork the path.
    """
    import inspect

    from openlimno.gui_core.controller import Controller
    src = inspect.getsource(Controller.run_case)
    assert "run_case_with_plots" in src, (
        "REGRESSION: GUI run-case worker no longer delegates to "
        "openlimno.studio.headless.run_case_with_plots — the v2.3.0 "
        "unified Studio entry-point has been re-forked."
    )
    # And: the inlined ``case.run()`` call from pre-v2.9.0 must be gone
    # — its presence indicates the duplication is back.
    assert "case.run()" not in src, (
        "REGRESSION: GUI run-case worker is calling ``case.run()`` "
        "inline again; v2.9.0 explicitly removed this in favor of "
        "``run_case_with_plots``."
    )
