"""WUA computation. SPEC §4.2.3.

Cell-level only in M1; HMU/reach aggregation lands in M2 (§4.2.3.2-3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import pandas as pd

from .hsi import HSICurve, composite_csi, require_independence_ack

if TYPE_CHECKING:
    pass


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
    """Compute CSI at a single section given (depth, velocity, [extras])."""
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
    sections_solver: callable,  # type: ignore[type-arg]  (callable signature documented below)
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

    Parameters
    ----------
    sections_solver
        Callable ``(sections, Q) -> list[MANSQResult]``.
    sections
        Cross-sections to evaluate.
    discharges_m3s
        Q values to sweep.
    hsi_curves
        HSI curves dict from ``load_hsi_from_parquet``.
    species, life_stage
        Target combination.
    section_areas_m2
        Area weight per section (e.g. half-distance to neighbors). If None,
        each section contributes its area_m2 from the hydraulic solution.
    composite
        Composite method; if geom/arith requires acknowledge_independence.
    acknowledge_independence
        SPEC §4.2.2.2 hard guard; required for geom/arith.
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
            cell_area = (
                section_areas_m2[i] if section_areas_m2 is not None else r.area_m2
            )
            wua += csi * cell_area
            n_used += 1
        rows.append({
            "discharge_m3s": Q,
            "wua_m2": wua,
            "n_sections_used": n_used,
        })
    return pd.DataFrame(rows)
