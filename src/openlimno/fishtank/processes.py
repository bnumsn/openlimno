"""Process rates + the ODE right-hand side (SPEC §3-§4).

The teaching heart: ``derivatives`` is the whole model dynamics in one
readable function. Read it and you have read the model.

Critical units point (SPEC §3.1): the substrate oxidation flux ρ
[mg-N/L/day] is the N that LEAVES the dissolved pool; it equals
growth / yield = (μ/Y)·X·M·M. Biomass growth is Y·ρ = μ·X [mg/L/day].
Do not confuse the two — that was the v0.1 bug.
"""

from __future__ import annotations

from .state import Params


def monod(s: float, k: float) -> float:
    """Monod saturation factor S/(K+S), dimensionless. Clipped to 0 for
    non-positive substrate so the solver can't drive concentrations
    negative through this term."""
    return s / (k + s) if s > 0.0 else 0.0


def oxidation_fluxes(y: list[float], p: Params) -> tuple[float, float]:
    """Return (ρ1, ρ2) — the TAN→NO2 and NO2→NO3 nitrogen fluxes
    [mg-N/L/day]. ρ = (μ/Y)·X·M(substrate)·M(O2)·θ."""
    TAN, NO2, _NO3, X_AOB, X_NOB, DO = y
    theta = p.theta ** (p.temperature_c - 20.0)
    rho1 = theta * (p.mu_AOB / p.Y_AOB) * X_AOB * monod(TAN, p.K_TAN) * monod(DO, p.K_O_AOB)
    rho2 = theta * (p.mu_NOB / p.Y_NOB) * X_NOB * monod(NO2, p.K_NO2) * monod(DO, p.K_O_NOB)
    return rho1, rho2


def derivatives(t: float, y: list[float], p: Params) -> list[float]:
    """Instantaneous rate of change of the Tier-1 state vector.

    State order: [TAN, NO2, NO3, X_AOB, X_NOB, DO] (state.STATE_ORDER).
    """
    # Only the attached-biomass and DO states appear explicitly below; the
    # dissolved TAN/NO2/NO3 enter through oxidation_fluxes(y, p).
    _TAN, _NO2, _NO3, X_AOB, X_NOB, DO = y
    rho1, rho2 = oxidation_fluxes(y, p)

    # Dissolved nitrogen pool
    E = p.ammonia_dose_mg_n_l_day          # Tier-1 fishless-cycle source
    dTAN = E - rho1
    dNO2 = rho1 - rho2
    dNO3 = rho2

    # Attached biofilm: growth = Y·ρ = μ·X, logistic-capped at media
    # capacity, first-order decay. (Water changes do NOT touch X — see
    # events.py — because the biofilm is attached.)
    dX_AOB = p.Y_AOB * rho1 * (1.0 - X_AOB / p.X_AOB_max) - p.b_AOB * X_AOB
    dX_NOB = p.Y_NOB * rho2 * (1.0 - X_NOB / p.X_NOB_max) - p.b_NOB * X_NOB

    # Oxygen: reaeration + mass-based nitrification demand (3.43 + 1.14
    # g-O2/g-N) + constant fish respiration.
    dDO = p.k_a * (p.DO_sat - DO) - 3.43 * rho1 - 1.14 * rho2 - p.R_fish

    return [dTAN, dNO2, dNO3, dX_AOB, dX_NOB, dDO]
