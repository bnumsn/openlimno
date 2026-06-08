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
    """v2.9.0 + v2.10.1 R11-15: the GUI worker MUST funnel through
    ``run_case_with_plots`` from ``openlimno.studio.headless`` rather
    than re-implement the chain.

    Pre-v2.10.1 this was an ``inspect.getsource`` substring check.
    Three problems with that pin (per 11th-round review):
    R11-15  — a hoisted-to-module-scope worker class would pass the
              substring check but still bypass the delegate.
    R11-17  — a legitimate ``case.run(plot=...)`` with an arg would
              fail the ``"case.run()" not in src`` substring even
              though it's perfectly correct.
    R11-22  — substring inspection fails on ``.pyc``-only deployments.

    v2.10.1 replaces it with a behavioral mock of the module-level
    helper ``_run_case_for_worker``. We pin the actual call shape
    (positional case_yaml + keyword ``plot=False``) and the summary
    text format — not textual coincidence in the source.
    """
    from types import SimpleNamespace
    from unittest.mock import patch

    from openlimno.gui_core import controller as ctl_mod

    fake_result = SimpleNamespace(
        case_name="mock_case",
        wua_quality_grade="A",
        n_discharges=7,
        output_dir=Path("/tmp/mock_out"),
    )
    case_yaml = Path("/tmp/mock_case.yaml")

    # v2.13.0: HeadlessRunResult now also carries wua_q_plot.
    fake_result.wua_q_plot = Path("/tmp/mock_out/wua_q_curve.png")

    with patch.object(
        ctl_mod,
        "run_case_with_plots",
        return_value=fake_result,
    ) as mock_fn:
        # v3.5.0 R16-2: tuple widened to 3 (summary, png_path,
        # trust_roots) so the GUI plot autoload can skip the
        # redundant Case.from_yaml call.
        result = ctl_mod._run_case_for_worker(case_yaml)
        assert len(result) == 3, (
            f"v3.5.0 R16-2: _run_case_for_worker must return a "
            f"3-tuple (summary, png_path, trust_roots); got "
            f"{len(result)}-tuple."
        )
        summary, png_path, trust_roots = result
        assert isinstance(trust_roots, list), (
            f"v3.5.0 R16-2: trust_roots must be a list of Paths; got {type(trust_roots).__name__}"
        )

    mock_fn.assert_called_once()
    args, kwargs = mock_fn.call_args
    assert args[0] == case_yaml, (
        f"v2.10.1 R11-15: _run_case_for_worker did not pass case_yaml "
        f"as the first positional arg; got {args!r}"
    )
    # v2.13.0: the worker now asks for the canonical WUA-Q PNG
    # (was plot=False in v2.10.1; the v2.9.0 'controller renders its
    # own plot' deferral never landed, so v2.13.0 flips to plot=True
    # and the controller auto-loads the headless-produced PNG as a
    # QgsRasterLayer).
    assert kwargs.get("plot") is True, (
        f"v2.13.0: _run_case_for_worker must call "
        f"run_case_with_plots(..., plot=True); got kwargs={kwargs!r}"
    )

    # Summary text must surface case_name, quality grade,
    # n_discharges, and output_dir — all four are part of the GUI
    # status-line contract the user sees post-run.
    assert "mock_case" in summary
    assert "HSI A" in summary
    assert "7 flows" in summary
    # normalise separators: the summary renders output_dir with the OS path
    # separator (`\tmp\mock_out` on Windows).
    assert "/tmp/mock_out" in summary.replace("\\", "/")

    # v2.13.0: the PNG path must also be threaded through so the
    # controller's auto-load step can pick it up.
    assert png_path == Path("/tmp/mock_out/wua_q_curve.png"), (
        f"v2.13.0: _run_case_for_worker did not return the wua_q_plot path. Got: {png_path!r}"
    )


def test_v310_r1311_pyqtsignal_uses_object_payload() -> None:
    """v3.1.0 R13-11: the worker's finished_ok signal must carry
    (str, object), not (str, str). The empty-string sentinel
    pattern is gone — Path | None now crosses the signal/slot
    boundary natively. Pin via source inspection."""
    import inspect

    from openlimno.gui_core.controller import Controller

    src = inspect.getsource(Controller.run_case)
    # Either the new form (preferred) OR the old form (regression).
    assert "pyqtSignal(str, object)" in src, (
        "v3.1.0 R13-11 regression: finished_ok no longer uses "
        "pyqtSignal(str, object); empty-string sentinel form is "
        "back. See SPEC_v3 §4 for the migration rationale."
    )
    assert "pyqtSignal(str, str)" not in src, (
        "v3.1.0 R13-11 regression: the v2.13.0 empty-string sentinel "
        "form (pyqtSignal(str, str)) reappeared. Use "
        "pyqtSignal(str, object) so None can cross the boundary "
        "natively."
    )
