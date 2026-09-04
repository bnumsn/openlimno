"""WUA computation. SPEC §4.2.3.

Cell-level only in M1; HMU/reach aggregation lands in M2 (§4.2.3.2-3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from .hsi import HSICurve, composite_csi, require_independence_ack

#: Column contract of :func:`wua_q_curve`, held even for an empty Q sweep.
_WUA_Q_COLUMNS: tuple[str, ...] = ("discharge_m3s", "wua_m2", "n_sections_used")


def cell_wua(csi: npt.ArrayLike, area: npt.ArrayLike) -> float:
    """WUA = sum(A_i * CSI_i). SPEC §4.2.3.1."""
    csi = np.asarray(csi, dtype=float)
    area = np.asarray(area, dtype=float)
    if csi.shape != area.shape:
        raise ValueError(f"csi shape {csi.shape} != area shape {area.shape}")
    return float((csi * area).sum())


def evaluate_section_csi(
    depth: float,
    velocity: float,
    hsi_curves: dict[tuple[str, str, str], HSICurve],
    species: str,
    life_stage: str,
    composite: str = "geometric_mean",
    acknowledge_independence: bool = False,
    extras: dict[str, float] | None = None,
) -> float:
    """Compute CSI at a single section given (depth, velocity, [extras]).

    Scalar counterpart of the array-wise composite used by
    :meth:`openlimno.case.Case._compute_cell_csi_and_area`; both build the
    same ``{variable: SI}`` mapping and hand it to
    :func:`openlimno.habitat.hsi.composite_csi`.

    Parameters
    ----------
    depth, velocity
        Section-mean hydraulics (m, m/s).
    hsi_curves
        Curves keyed ``(species, life_stage, variable)``. Variables with no
        curve for this ``(species, life_stage)`` are silently dropped from the
        composite — unlike the ``Case`` path, there is no warnings channel.
    extras
        Additional ``{variable: value}`` pairs (substrate, cover, temperature)
        to fold into the composite when a matching curve exists.

    Returns
    -------
    float
        CSI ∈ [0, 1], or ``0.0`` when no variable resolved to a curve.

    Raises
    ------
    ValueError
        If ``composite`` is a geometric/arithmetic mean and
        ``acknowledge_independence`` is False (SPEC §4.2.2.2 / ADR-0006).
    """
    require_independence_ack(composite, acknowledge_independence)  # type: ignore[arg-type]

    suits: dict[str, np.ndarray] = {}
    used_vars: list[str] = []
    for var_name, value in [("depth", depth), ("velocity", velocity), *(extras or {}).items()]:
        key = (species, life_stage, var_name)
        if key in hsi_curves:
            suits[var_name] = hsi_curves[key].evaluate(np.array([value]))
            used_vars.append(var_name)
    if not suits:
        return 0.0
    csi = composite_csi(suits, method=composite)  # type: ignore[arg-type]
    return float(csi[0])


def wua_q_curve(
    sections_solver: Callable[..., list[Any]],
    sections: list,
    discharges_m3s: list[float],
    hsi_curves: dict[tuple[str, str, str], HSICurve],
    species: str,
    life_stage: str,
    section_areas_m2: list[float] | None = None,
    composite: str = "geometric_mean",
    acknowledge_independence: bool = False,
) -> pd.DataFrame:
    """Compute WUA as a function of Q.

    Library-level entry point for a WUA-Q sweep: it needs only a solver
    callable, cross-sections and HSI curves, so callers can sweep discharge
    without assembling a full :class:`openlimno.case.Case` (case YAML, WEDM
    inputs, output directory). It is also the only surface that accepts
    explicit per-section area weights — see ``section_areas_m2``.

    Numerically it is the same computation ``Case.run`` writes into
    ``wua_q.csv``: ``tests/unit/test_habitat_wua_api.py`` cross-validates it
    against :meth:`openlimno.case.Case._compute_cell_wua` (``composite_csi``
    over per-cell arrays plus :func:`cell_wua`) and requires agreement to
    floating-point identity for every composite method, so regulatory
    deliverables cannot depend on which entry point was used.

    Parameters
    ----------
    sections_solver
        Callable ``(sections, Q) -> list[MANSQResult]``, e.g.
        :meth:`openlimno.hydro.builtin_1d.Builtin1D.solve_reach`.
    sections
        Cross-sections to evaluate.
    discharges_m3s
        Q values to sweep.
    hsi_curves
        HSI curves dict from ``load_hsi_from_parquet``.
    species, life_stage
        Target combination.
    section_areas_m2
        Area weight per section (e.g. half-distance to neighbors), indexed
        positionally against ``sections_solver``'s result list. If None, each
        section contributes its ``area_m2`` from the hydraulic solution —
        which is what the ``Case`` pipeline always does.
    composite
        Composite method; if geom/arith requires acknowledge_independence.
    acknowledge_independence
        SPEC §4.2.2.2 hard guard; required for geom/arith. Checked before the
        solver runs, so a rejected sweep does no hydraulic work.

    Returns
    -------
    pandas.DataFrame
        One row per entry of ``discharges_m3s``, in the order given, with
        columns ``discharge_m3s``, ``wua_m2`` and ``n_sections_used``.
        ``n_sections_used`` counts *wetted* sections (``area_m2 > 0``), not
        sections with non-zero suitability.

    Notes
    -----
    Sections that come back dewatered (``area_m2 <= 0``) are skipped entirely,
    including their ``section_areas_m2`` weight; the remaining weights stay
    aligned to their original section index.
    """
    require_independence_ack(composite, acknowledge_independence)  # type: ignore[arg-type]

    rows: list[dict[str, float]] = []
    for Q in discharges_m3s:
        results = sections_solver(sections, Q)
        wua = 0.0
        n_used = 0
        for i, r in enumerate(results):
            if r.area_m2 <= 0:
                continue
            csi = evaluate_section_csi(
                depth=r.depth_mean_m,
                velocity=r.velocity_mean_ms,
                hsi_curves=hsi_curves,
                species=species,
                life_stage=life_stage,
                composite=composite,
                acknowledge_independence=acknowledge_independence,
            )
            cell_area = section_areas_m2[i] if section_areas_m2 is not None else r.area_m2
            wua += csi * cell_area
            n_used += 1
        rows.append(
            {
                "discharge_m3s": Q,
                "wua_m2": wua,
                "n_sections_used": n_used,
            }
        )
    # An empty sweep still has to carry the column contract: callers do
    # ``df["wua_m2"]`` unconditionally, and a bare ``DataFrame([])`` has no
    # columns at all, so it raises KeyError instead of yielding an empty Series.
    return pd.DataFrame(rows, columns=list(_WUA_Q_COLUMNS))
