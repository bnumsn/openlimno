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
