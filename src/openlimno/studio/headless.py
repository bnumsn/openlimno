"""OpenLimno Studio — headless run API (v2.3.0).

The piece of Studio that does NOT need QGIS bindings. Provides:

* :func:`run_case_with_plots(case_yaml, ...)` — loads a case, runs the
  full WUA-Q pipeline, and renders the same WUA-Q curve PNG the
  Studio GUI displays. Used directly by ``python -m openlimno.studio
  --headless``, by the CLI ``openlimno run --plot``, and by the
  GUI controller's `_RunCaseWorker` (which previously inlined this
  logic).
* :func:`plot_wua_q(wua_q_df, png, ..., quality_grade)` — pure plotting
  function. Renders the same axes + watermark conventions
  `examples/lemhi/quickstart.py` uses (red C-grade banner, grey
  B-grade footnote). Routed through ``Case._atomic_write`` so the
  PNG inherits the v1.9.0+ atomic-write + umask contract.

Designed for use in three contexts:

1. **CLI** — ``openlimno wua-q --plot`` (already in `cli.py`; calls
   :func:`plot_wua_q` directly).
2. **Studio GUI** — the controller's run-case worker hands off to
   :func:`run_case_with_plots` instead of inlining the run+plot path.
3. **CI / tests** — :func:`run_case_with_plots` is a single-call API
   that exercises the production path without needing QGIS or a
   running event loop.

Memory: ``project_studio`` — path A is PyQt6 + PyQGIS canvas; v2.3.0
ships the core headless surface that path A's GUI sits on top of.
QGIS plugin remains the v1.x distribution path; deprecated after
Studio 1.0 lands.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class HeadlessRunResult:
    """Container for a single headless Studio run.

    Attributes:
        case_name: ``Case.name`` from the loaded YAML.
        output_dir: directory the case writes outputs to.
        wua_q_csv: path to the produced ``wua_q.csv``.
        wua_q_plot: path to the rendered ``wua_q_curve.png`` (None
            if ``plot=False`` was requested).
        provenance_json: path to the produced ``provenance.json``.
        wua_quality_grade: ``"A"`` / ``"B"`` / ``"C"`` from the
            run's HSI quality grading.
        n_discharges: number of discharge points swept.
        warnings: warnings the case emitted.
    """

    case_name: str
    output_dir: Path
    wua_q_csv: Path
    wua_q_plot: Path | None
    provenance_json: Path
    wua_quality_grade: str
    n_discharges: int
    warnings: list[str]


def plot_wua_q(
    wua_q_df: Any,
    png_path: Path,
    *,
    title: str,
    quality_grade: str = "A",
    dpi: int = 120,
) -> None:
    """Render the canonical OpenLimno WUA-Q curve PNG.

    Same axes / legend / watermark conventions used by
    ``examples/lemhi/quickstart.py`` and the CLI ``wua-q --plot``.
    Routes through ``Case._atomic_write`` so the PNG inherits the
    v1.9.0+ atomic-write + umask contract (R5-3 close-out).

    Args:
        wua_q_df: DataFrame with columns ``discharge_m3s`` and one or
            more ``wua_m2_<species>_<stage>`` columns.
        png_path: where to write the rendered PNG. Parent must exist.
        title: figure title.
        quality_grade: ``"A"``, ``"B"``, or ``"C"``. ``"C"`` overlays
            a red TENTATIVE banner; ``"B"`` adds a grey footnote;
            ``"A"`` adds nothing.
        dpi: matplotlib DPI passed to ``fig.savefig``.
    """
    # v3.1.0 R14-2: matplotlib Agg backend is now forced at the
    # ``openlimno.studio`` package __init__ (before any submodule
    # import), which is the only place it reliably wins the race
    # against early pyplot imports from plugins / qgis bootstrap.
    # The previous v3.0.0 per-function attempt was kept here too as
    # a belt-and-suspenders but trips a lint warning; R14-2 moves it
    # to the package level and this function imports pyplot cleanly.
    import matplotlib.pyplot as plt

    from openlimno.case import Case

    fig, ax = plt.subplots(figsize=(8, 5))
    series_cols = [c for c in wua_q_df.columns if c.startswith("wua_m2_")]
    for col in series_cols:
        label = col.replace("wua_m2_", "").replace("_", " ").title()
        ax.plot(
            wua_q_df["discharge_m3s"],
            wua_q_df[col],
            "o-", lw=2, markersize=6, label=label,
        )
    ax.set_xlabel("Discharge (m³/s)")
    ax.set_ylabel("WUA (m²)")
    if wua_q_df["discharge_m3s"].min() > 0 and len(wua_q_df) >= 3:
        ax.set_xscale("log")
    ax.set_title(title)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    if quality_grade == "C":
        ax.text(
            0.5, 0.5, "C-GRADE HSI — TENTATIVE",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=42, color="red", alpha=0.18,
            rotation=18, weight="bold",
        )
    elif quality_grade == "B":
        ax.text(
            0.99, 0.01,
            "HSI quality: B (transferred curve — see provenance.json)",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="gray",
        )

    fig.tight_layout()
    # The publish tempfile that ``_atomic_write`` allocates has a
    # ``.tmp`` suffix; matplotlib's ``savefig`` infers the writer
    # from the extension, so we MUST pass ``format=...`` explicitly
    # (otherwise it tries to write a "tmp" format and raises). This
    # also fixes a latent v1.9.2 R5-3 regression in ``cli.py``'s
    # ``wua-q --plot`` route that the existing test suite missed.
    Case._atomic_write(
        png_path, lambda p: fig.savefig(p, dpi=dpi, format="png"),
    )
    plt.close(fig)


def run_case_with_plots(
    case_yaml: Path | str,
    *,
    discharges_m3s: list[float] | None = None,
    slope: float = 0.002,
    manning_n: float = 0.035,
    plot: bool = True,
) -> HeadlessRunResult:
    """End-to-end headless Studio run.

    Loads the case, runs the full WUA-Q + HSI pipeline, and (if
    ``plot=True``) renders the canonical WUA-Q curve PNG alongside
    the rest of the run artefacts.

    Args:
        case_yaml: path to a case YAML.
        discharges_m3s: optional explicit discharge sweep. Default
            ``np.logspace(0, log10(30), 12)`` for the canonical
            1—30 m³/s range OpenLimno examples use.
        slope: channel slope.
        manning_n: Manning's n.
        plot: whether to render ``wua_q_curve.png`` alongside the
            other artefacts.

    Returns:
        :class:`HeadlessRunResult` with paths to every artefact the
        run produced.
    """
    from openlimno.case import Case

    case = Case.from_yaml(Path(case_yaml))
    if discharges_m3s is None:
        discharges_m3s = list(np.logspace(0, np.log10(30), 12))
    result = case.run(
        discharges_m3s=discharges_m3s, slope=slope, manning_n=manning_n,
    )

    # Read the quality grade out of the provenance the run just wrote.
    prov = json.loads(result.provenance_path.read_text())
    grade = prov.get("wua_quality_grade", "A")

    wua_q_plot: Path | None = None
    if plot:
        wua_q_plot = result.output_dir / "wua_q_curve.png"
        plot_wua_q(
            result.wua_q,
            wua_q_plot,
            title=f"WUA-Q curve\n(case: {case.name})",
            quality_grade=grade,
        )

    return HeadlessRunResult(
        case_name=case.name,
        output_dir=result.output_dir,
        wua_q_csv=result.output_dir / "wua_q.csv",
        wua_q_plot=wua_q_plot,
        provenance_json=result.provenance_path,
        wua_quality_grade=grade,
        n_discharges=len(discharges_m3s),
        warnings=list(result.warnings),
    )
