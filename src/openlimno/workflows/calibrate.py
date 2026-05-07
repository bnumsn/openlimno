"""Hydraulic parameter calibration.

SPEC §3.5: ``calibrate`` workflow. M2 deliverable: scipy-based 1-parameter
calibration of Manning's n against an observed rating curve. PEST++ multi-
parameter inversion lands in 1.x.

Use case (Lemhi-typical):
    Given a measured rating curve at a USGS gauge (h, Q pairs) and a built
    cross-section, find the Manning's n that minimises sum-of-squared error
    between observed and Manning-predicted Q for a fixed slope.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from openlimno.hydro.builtin_1d import CrossSection


@dataclass
class CalibrationResult:
    """Outcome of a 1-parameter Manning calibration."""

    parameter: str  # "manning_n"
    calibrated_value: float
    initial_value: float
    rmse_initial: float
    rmse_final: float
    n_iterations: int
    converged: bool
    bounds: tuple[float, float]
    notes: str = ""


def _rmse(predicted: np.ndarray, observed: np.ndarray) -> float:
    return float(np.sqrt(np.mean((predicted - observed) ** 2)))


def _predicted_Q_at_h(
    xs: CrossSection, observed: pd.DataFrame, slope: float, n_value: float
) -> np.ndarray:
    """Predict Q at each observed h using Manning with given n."""
    base_n = xs.manning_n
    xs.manning_n = n_value
    try:
        # Translate observed h (depth above thalweg) to absolute WSE
        wse = xs.thalweg_elevation_m + observed["h_m"].to_numpy()
        Q_pred = np.array([xs.manning_discharge(float(w), slope) for w in wse])
    finally:
        xs.manning_n = base_n
    return Q_pred


def calibrate_manning_n(
    cross_section: CrossSection,
    observed_rating: pd.DataFrame,
    slope: float = 0.001,
    initial_n: float = 0.035,
    bounds: tuple[float, float] = (0.012, 0.08),
) -> CalibrationResult:
    """Calibrate Manning's n by minimising RMSE between observed and predicted Q.

    Parameters
    ----------
    cross_section
        A CrossSection (typically the gauge-vicinity section).
    observed_rating
        DataFrame with columns ``h_m`` and ``Q_m3s``.
    slope
        Bed slope assumed during calibration (constant; per-segment slope is M2+).
    initial_n
        Starting Manning's n estimate.
    bounds
        Reasonable physical range for Manning's n.
    """
    if not {"h_m", "Q_m3s"}.issubset(observed_rating.columns):
        raise ValueError("observed_rating must have columns 'h_m' and 'Q_m3s'")
    obs_Q = observed_rating["Q_m3s"].to_numpy()

    Q_pred_init = _predicted_Q_at_h(cross_section, observed_rating, slope, initial_n)
    rmse_init = _rmse(Q_pred_init, obs_Q)

    def objective(n_value: float) -> float:
        if not (bounds[0] <= n_value <= bounds[1]):
            return 1e9
        Q_pred = _predicted_Q_at_h(cross_section, observed_rating, slope, n_value)
        return _rmse(Q_pred, obs_Q)

    result = minimize_scalar(
        objective, bounds=bounds, method="bounded",
        options={"xatol": 1e-5, "maxiter": 200},
    )

    n_calib = float(result.x)
    rmse_final = float(result.fun)
    return CalibrationResult(
        parameter="manning_n",
        calibrated_value=n_calib,
        initial_value=initial_n,
        rmse_initial=rmse_init,
        rmse_final=rmse_final,
        n_iterations=int(result.nit) if hasattr(result, "nit") else -1,
        converged=bool(result.success),
        bounds=bounds,
        notes=f"slope={slope}, n_obs={len(observed_rating)}",
    )


__all__ = ["CalibrationResult", "calibrate_manning_n"]
