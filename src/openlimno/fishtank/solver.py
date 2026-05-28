"""ODE integration wrapper (SPEC §7 solver.py [core]).

Tier-1: a single ``scipy.integrate.solve_ivp`` call over the run window.
Discrete events (water change etc.) add a stop/apply/restart segment
loop in Hour 3 — kept out of the Tier-1 path so the Hour-2 build is
minimal.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from .events import EventSchedule, apply_event
from .processes import derivatives
from .state import STATE_ORDER, Chemistry, Params, nh3_free_fraction


@dataclass
class Result:
    """Simulation output (SPEC §9)."""

    timeseries: pd.DataFrame          # day + state columns + NH3_free + pH
    params: Params
    warnings: list[str]


# Toxicity thresholds (literature, SPEC §9)
_NH3_FREE_STRESS = 0.05   # mg/L free NH3 → chronic fish stress
_NO2_STRESS = 0.5         # mg-N/L → "brown blood"
_NO3_WC_DUE = 50.0        # mg-N/L → water change due


def _integrate_segment(
    y0: list[float], p: Params, t0: float, t1: float, t_eval: np.ndarray,
) -> np.ndarray:
    """Integrate one event-free segment and return the state at t_eval."""
    sol = solve_ivp(
        derivatives,
        t_span=(t0, t1),
        y0=y0,
        args=(p,),
        method="LSODA",
        max_step=0.25,
        t_eval=t_eval,
        rtol=1e-6,
        atol=1e-9,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed on [{t0}, {t1}]: {sol.message}")
    return sol.y


def simulate(
    chemistry: Chemistry | None = None,
    params: Params | None = None,
    *,
    days: float = 42.0,
    dt_output_hours: float = 6.0,
    schedule: EventSchedule | None = None,
) -> Result:
    """Integrate the fishtank model.

    Without ``schedule`` this is a single-segment Tier-1 fishless cycle.
    With a ``schedule``, the solver stops at each event day, applies the
    event's instantaneous state/parameter map, and restarts — so water
    changes, dose changes, and feeding take effect mid-run (SPEC §5).

    Returns a Result whose timeseries has one row per output step with
    the six state variables plus the derived NH3_free and (fixed) pH.
    """
    chem = chemistry or Chemistry()
    p = params or Params()

    n_out = int(round(days * 24.0 / dt_output_hours)) + 1
    full_grid = np.linspace(0.0, days, n_out)

    boundaries = schedule.boundaries(days) if schedule else []
    seg_edges = [0.0, *boundaries, days]

    y = chem.to_vector()
    times: list[float] = []
    states: list[np.ndarray] = []
    for i in range(len(seg_edges) - 1):
        t0, t1 = seg_edges[i], seg_edges[i + 1]
        # Output grid points within this segment; drop the duplicated
        # right edge except on the final segment so events show a clean
        # discontinuity.
        mask = (full_grid >= t0) & (full_grid <= t1)
        t_eval = full_grid[mask]
        if t_eval.size == 0 or t_eval[0] > t0:
            t_eval = np.insert(t_eval, 0, t0)
        seg_y = _integrate_segment(y, p, t0, t1, t_eval)
        # Record all but the last column to avoid duplicate boundary rows
        keep = slice(None) if i == len(seg_edges) - 2 else slice(0, -1)
        times.extend(t_eval[keep].tolist())
        states.append(seg_y[:, keep])
        # Advance to the segment end and apply any events on this boundary.
        y = seg_y[:, -1].tolist()
        if schedule and t1 in boundaries:
            chem_end = Chemistry.from_vector(y)
            for ev in schedule.at(t1):
                chem_end, p = apply_event(chem_end, p, ev, schedule.tap_water)
            y = chem_end.to_vector()

    arr = np.concatenate(states, axis=1)
    df = pd.DataFrame(arr.T, columns=list(STATE_ORDER))
    df.insert(0, "day", times)
    f_free = nh3_free_fraction(p.ph, p.temperature_c)
    df["NH3_free"] = (df["TAN"].clip(lower=0.0) * f_free).round(6)
    df["pH"] = p.ph

    warnings: list[str] = []
    _flag(warnings, df, "NH3_free", _NH3_FREE_STRESS, "free NH3 > 0.05 mg/L (chronic fish stress)")
    _flag(warnings, df, "NO2", _NO2_STRESS, "NO2 > 0.5 mg-N/L (brown-blood risk)")
    _flag(warnings, df, "NO3", _NO3_WC_DUE, "NO3 > 50 mg-N/L (water change due)")

    return Result(timeseries=df, params=p, warnings=warnings)


def _flag(warnings: list[str], df: pd.DataFrame, col: str, thresh: float, msg: str) -> None:
    over = df[df[col] > thresh]
    if not over.empty:
        first_day = float(over["day"].iloc[0])
        warnings.append(f"{msg} — first crossed on day {first_day:.1f}")
