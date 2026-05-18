"""Studio headless API smoke tests (v2.3.0).

These tests exercise the ``openlimno.studio.headless`` surface
without needing QGIS bindings — the same path the GUI controller
hands off to, but in-process and synchronous.

Lives under ``tests/integration/`` because it actually runs
``Case.run`` against the Lemhi example. Skipped if the example
isn't present (e.g., installed-package test runs).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

CASE_YAML = Path(__file__).resolve().parent.parent.parent / "examples" / "lemhi" / "case.yaml"


@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_v230_studio_headless_runs_lemhi_end_to_end():
    """v2.3.0: ``run_case_with_plots`` on the Lemhi case must produce
    every canonical artefact (wua_q.csv, provenance.json, wua_q_curve.png)
    with umask-respecting perms (inherits the v1.9.0+ atomic-write
    contract via ``Case._atomic_write``)."""
    from openlimno.studio import run_case_with_plots

    result = run_case_with_plots(CASE_YAML, discharges_m3s=[3.0, 6.0, 12.0])
    assert result.case_name == "lemhi_phabsim_replication"
    assert result.wua_q_csv.exists(), f"wua_q.csv missing in {result.output_dir}"
    assert result.provenance_json.exists(), "provenance.json missing"
    assert result.wua_q_plot is not None
    assert result.wua_q_plot.exists(), "wua_q_curve.png missing"

    # v1.9.0+ atomic-write contract: PNG inherits umask perms.
    current_umask = os.umask(0)
    os.umask(current_umask)
    expected = 0o666 & ~current_umask
    perms = os.stat(result.wua_q_plot).st_mode & 0o777
    assert perms == expected, (
        f"wua_q_curve.png perms={oct(perms)} != "
        f"expected {oct(expected)} (atomic-write contract broken)"
    )

    assert result.wua_quality_grade in ("A", "B", "C")
    assert result.n_discharges == 3


@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_v230_studio_headless_plot_can_be_skipped():
    """v2.3.0: ``plot=False`` must skip the PNG render entirely
    (the GUI may want to drive its own matplotlib pipeline in
    a Qt event loop)."""
    from openlimno.studio import run_case_with_plots

    result = run_case_with_plots(
        CASE_YAML, discharges_m3s=[3.0], plot=False,
    )
    assert result.wua_q_plot is None
    # The case-level artefacts are still written.
    assert result.wua_q_csv.exists()
    assert result.provenance_json.exists()


def test_v230_studio_headless_plot_wua_q_atomic_write(tmp_path):
    """v2.3.0: ``plot_wua_q`` standalone (no Case.run) renders into
    a tempdir with the same atomic-write contract. Pin perms and
    no tempfile leftovers."""
    import numpy as np
    import pandas as pd

    from openlimno.studio import plot_wua_q

    wua_q = pd.DataFrame({
        "discharge_m3s": np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        "wua_m2_sp_juv": np.array([10.0, 50.0, 100.0, 80.0, 30.0]),
    })
    png = tmp_path / "out.png"
    plot_wua_q(wua_q, png, title="v2.3.0 smoke", quality_grade="A")

    assert png.exists()
    leftover = [p.name for p in tmp_path.iterdir() if p != png]
    assert leftover == [], (
        f"v2.3.0 plot_wua_q left orphan tempfiles: {leftover}"
    )

    current_umask = os.umask(0)
    os.umask(current_umask)
    expected = 0o666 & ~current_umask
    perms = os.stat(png).st_mode & 0o777
    assert perms == expected


def test_v230_studio_headless_plot_wua_q_grade_c_overlay(tmp_path):
    """v2.3.0: a C-grade quality flag must produce the red TENTATIVE
    overlay. We can't easily verify pixel content, but we can verify
    the rendered file is BIGGER than the same plot without the
    overlay (the text overlay adds measurable bytes)."""
    import numpy as np
    import pandas as pd

    from openlimno.studio import plot_wua_q

    wua_q = pd.DataFrame({
        "discharge_m3s": np.array([1.0, 2.0, 3.0, 4.0]),
        "wua_m2_sp_juv": np.array([10.0, 20.0, 30.0, 20.0]),
    })
    png_a = tmp_path / "grade_a.png"
    png_c = tmp_path / "grade_c.png"
    plot_wua_q(wua_q, png_a, title="A", quality_grade="A")
    plot_wua_q(wua_q, png_c, title="C", quality_grade="C")
    assert png_a.exists() and png_c.exists()
    size_a = png_a.stat().st_size
    size_c = png_c.stat().st_size
    # C-grade overlay adds the TENTATIVE banner text, which makes
    # the PNG measurably larger than the A-grade baseline.
    assert size_c > size_a, (
        f"C-grade overlay should grow PNG; got A={size_a}, C={size_c}"
    )
