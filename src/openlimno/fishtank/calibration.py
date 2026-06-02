"""Parameter calibration against a measured aquarium log (Hour-3 [core]).

Teaching scope: align a simulated timeseries to observed measurements,
compute RMSE, and fit the most-sensitive rate parameters with
``scipy.optimize.minimize``. ``align`` + ``rmse`` are provided so the
Hour-3 class only fills in the objective and the minimize call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .events import EventSchedule
from .solver import simulate
from .state import Chemistry, Params

# Variables we calibrate against; observed CSV may contain any subset.
_FITTABLE_COLUMNS = ("TAN", "NO2", "NO3")


def align(sim: pd.DataFrame, obs: pd.DataFrame) -> pd.DataFrame:
    """Interpolate the simulation onto the observed days.

    ``obs`` must have a ``day`` column plus one or more of TAN/NO2/NO3.
    Returns a long-form frame [day, variable, sim, obs] over the
    variables present in BOTH frames.
    """
    if "day" not in obs.columns:
        raise ValueError("observation frame needs a 'day' column")
    shared = [c for c in _FITTABLE_COLUMNS if c in obs.columns and c in sim.columns]
    if not shared:
        raise ValueError(f"no shared fit columns; obs has {list(obs.columns)}")
    rows: list[dict[str, float | str]] = []
    sim_days = sim["day"].to_numpy(dtype=float)
    sim_lo, sim_hi = float(sim_days.min()), float(sim_days.max())
    obs_days = obs["day"].to_numpy(dtype=float)
    # Drop observations outside the simulated window; np.interp would
    # otherwise silently endpoint-extrapolate them, inflating/deflating
    # the fit with non-comparable points.
    in_range = (obs_days >= sim_lo) & (obs_days <= sim_hi)
    for var in shared:
        sim_interp = np.interp(obs_days, sim_days, sim[var].to_numpy(dtype=float))
        for d, s, o, ok in zip(obs_days, sim_interp, obs[var], in_range, strict=True):
            if ok and pd.notna(o):
                rows.append({"day": float(d), "variable": var, "sim": float(s), "obs": float(o)})
    return pd.DataFrame(rows)


def rmse(merged: pd.DataFrame) -> float:
    """Root-mean-square error over an aligned (sim, obs) frame.

    Per-variable normalisation keeps NO3 (large) from dominating TAN/NO2
    (small): each variable's residuals are divided by that variable's
    observed range before pooling."""
    if merged.empty:
        return float("inf")
    sq: list[float] = []
    for _var, grp in merged.groupby("variable"):
        # Normalise by the observed range, floored at 1 mg/L (a physical
        # concentration scale). The floor avoids divide-by-~0 when a
        # variable barely moves in the observed window, and keeps a
        # near-constant variable from dominating the pooled error.
        scale = max(float(grp["obs"].max() - grp["obs"].min()), 1.0)
        sq.extend(((grp["sim"] - grp["obs"]) / scale).to_numpy(dtype=float) ** 2)
    return float(np.sqrt(np.mean(sq)))


@dataclass
class CalibrationResult:
    best_params: dict[str, float]
    best_rmse: float
    n_evals: int
    converged: bool
    message: str = ""        # optimiser status message (helps debug non-convergence)


def fit(
    observation: pd.DataFrame,
    *,
    chemistry: Chemistry | None = None,
    base_params: Params | None = None,
    fit_names: Sequence[str] = ("mu_AOB", "mu_NOB"),
    bounds: Sequence[tuple[float, float]] = ((0.1, 1.5), (0.1, 1.5)),
    days: float | None = None,
    schedule: EventSchedule | None = None,
) -> CalibrationResult:
    """Fit ``fit_names`` parameters to minimise normalised RMSE vs the
    observed log. Defaults fit the two most-sensitive nitrification
    growth rates (Hour-3 sensitivity lesson).

    ``schedule`` should mirror the keeper actions behind the observed log
    (water changes, feeding, dose changes). It defaults to ``None`` — an
    event-free simulation, correct only for a steady fishless cycle. A real
    aquarium log always carries such events; omitting them then aligns an
    event-free simulation against event-affected observations and silently
    biases the fit."""
    if "day" not in observation.columns:
        raise ValueError("observation frame needs a 'day' column")
    if len(fit_names) != len(bounds):
        raise ValueError("fit_names and bounds must have the same length")
    chem = chemistry or Chemistry()
    base = base_params or Params()
    horizon = days if days is not None else float(observation["day"].max())
    n_eval = 0

    def objective(x: np.ndarray) -> float:
        nonlocal n_eval
        n_eval += 1
        p = base.with_overrides(**dict(zip(fit_names, (float(v) for v in x), strict=True)))
        sim = simulate(chem, p, days=horizon, schedule=schedule).timeseries
        return rmse(align(sim, observation))

    try:
        x0 = np.array([getattr(base, name) for name in fit_names], dtype=float)
    except AttributeError as exc:
        raise ValueError(f"unknown fit parameter: {exc}") from exc
    res = minimize(objective, x0, method="L-BFGS-B", bounds=list(bounds))
    return CalibrationResult(
        best_params=dict(zip(fit_names, (float(v) for v in res.x), strict=True)),
        best_rmse=float(res.fun),
        n_evals=n_eval,
        converged=bool(res.success),
        message=str(res.message),
    )
