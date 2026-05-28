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

    # Expand repeats ONCE so boundaries + per-day lookup are consistent.
    expanded: list = schedule.expand(days) if schedule else []

    def events_on(day: float) -> list:
        same = [e for e in expanded if e.day == day]
        return sorted(same, key=lambda e: e.priority)

    boundaries = sorted({e.day for e in expanded if 0.0 < e.day < days})
    seg_edges = [0.0, *boundaries, days]

    # Day-0 events apply to the initial state before any integration
    # (e.g. an ammonia_dose set at day 0). Without this they'd be lost,
    # since segment boundaries are strictly inside (0, days).
    if schedule:
        chem = Chemistry(**vars(chem))
        for ev in events_on(0.0):
            chem, p = apply_event(chem, p, ev, schedule.tap_water)

    y = chem.to_vector()
    times: list[float] = []
    states: list[np.ndarray] = []
    n_seg = len(seg_edges) - 1
    for i in range(n_seg):
        t0, t1 = seg_edges[i], seg_edges[i + 1]
        is_last = i == n_seg - 1
        # Always evaluate at BOTH segment edges plus the interior grid
        # points, so the pre-event state at t1 is available to carry
        # across the boundary regardless of whether t1 lands on the
        # output grid (the off-grid corruption fixed here).
        inner = full_grid[(full_grid > t0) & (full_grid < t1)]
        t_eval = np.unique(np.concatenate(([t0], inner, [t1])))
        seg_y = _integrate_segment(y, p, t0, t1, t_eval)
        # Record [t0 .. t1): drop the pre-event boundary row on non-final
        # segments — the post-event t1 row is recorded by the next
        # segment, which starts from the post-event state. Final segment
        # keeps t1 (= days). Each grid point thus appears exactly once,
        # with post-event state at boundaries.
        keep_mask = np.ones(t_eval.size, dtype=bool) if is_last else (t_eval < t1)
        times.extend(t_eval[keep_mask].tolist())
        states.append(seg_y[:, keep_mask])
        # Carry the pre-event state at t1 forward, then apply events.
        y = seg_y[:, -1].tolist()
        if schedule and not is_last:
            chem_end = Chemistry.from_vector(y)
            for ev in events_on(t1):
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
