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


def simulate(
    chemistry: Chemistry | None = None,
    params: Params | None = None,
    *,
    days: float = 42.0,
    dt_output_hours: float = 6.0,
) -> Result:
    """Integrate the Tier-1 fishless-cycle model.

    Returns a Result whose timeseries has one row per output step with
    the six state variables plus the derived NH3_free and (fixed) pH.
    """
    y0 = (chemistry or Chemistry()).to_vector()
    p = params or Params()

    n_out = int(round(days * 24.0 / dt_output_hours)) + 1
    t_eval = np.linspace(0.0, days, n_out)

    sol = solve_ivp(
        derivatives,
        t_span=(0.0, days),
        y0=y0,
        args=(p,),
        method="LSODA",
        max_step=0.25,
        t_eval=t_eval,
        rtol=1e-6,
        atol=1e-9,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed: {sol.message}")

    df = pd.DataFrame(sol.y.T, columns=list(STATE_ORDER))
    df.insert(0, "day", sol.t)
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
