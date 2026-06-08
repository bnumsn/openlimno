"""Process rates + the ODE right-hand side (SPEC §3-§4).

The teaching heart: ``derivatives`` is the whole model dynamics in one
readable function. Read it and you have read the model.

Critical units point (SPEC §3.1): the substrate oxidation flux ρ
[mg-N/L/day] is the N that LEAVES the dissolved pool; it equals
growth / yield = (μ/Y)·X·M·M. Biomass growth is Y·ρ = μ·X [mg/L/day].
Do not confuse the two — that was the v0.1 bug.
"""

from __future__ import annotations

from .carbonate import ph_from_dic_alk
from .state import Params

# Alkalinity consumed by ammonia oxidation: NH4+ + 1.5 O2 → NO2- + H2O + 2H+
# releases 2 H+ per mol N (the nitratation step NO2-→NO3- releases none), so
# 2 equivalents of alkalinity per mol N nitritated. In mass units that is the
# familiar 7.14 g-CaCO3/g-N (= 2·50.04/14). meq/L per (mg-N/L) = 2/14.
_ALK_MEQ_PER_MG_N = 2.0 / 14.007


def monod(s: float, k: float) -> float:
    """Monod saturation factor S/(K+S), dimensionless. Clipped to 0 for
    non-positive substrate so the solver can't drive concentrations
    negative through this term."""
    return s / (k + s) if s > 0.0 else 0.0


def effective_ph(y: list[float], p: Params) -> float:
    """The pH the rates see. Tier-1 (couple_ph=0): the fixed scenario pH.
    Tier-2 coupled: solve pH from the current (DIC, Alk, T) carbonate state
    each call. If the buffer is driven outside the [3,12] bracket (fully
    crashed), clamp to the acid end so inhibition saturates instead of the
    solver raising — keeps the RHS total and finite."""
    if p.couple_ph <= 0.0:
        return p.ph
    dic, alk = y[7], y[8]
    try:
        return ph_from_dic_alk(dic, alk, p.temperature_c)
    except ValueError:
        return 3.0


def nitrification_ph_factor(ph: float, p: Params) -> float:
    """pH inhibition multiplier on nitrification (1 = no inhibition). Tier-1
    returns 1. Coupled: linear ramp from 0 at ``pH_min_nitrif`` to 1 at
    ``pH_opt_nitrif`` — nitrifiers stall as a crashing buffer acidifies the
    tank, which is the feedback that makes old-tank pH collapse self-limiting."""
    if p.couple_ph <= 0.0:
        return 1.0
    span = p.pH_opt_nitrif - p.pH_min_nitrif
    if span <= 0.0:
        return 1.0
    return max(0.0, min(1.0, (ph - p.pH_min_nitrif) / span))


def oxidation_fluxes(y: list[float], p: Params) -> tuple[float, float]:
    """Return (ρ1, ρ2) — the TAN→NO2 and NO2→NO3 nitrogen fluxes
    [mg-N/L/day]. ρ = (μ/Y)·X·M(substrate)·M(O2)·θ·f_pH, where f_pH=1 in
    Tier-1 and ramps to 0 under a crashing pH when coupling is on."""
    TAN, NO2, _NO3, X_AOB, X_NOB, DO = y[:6]
    theta = p.theta ** (p.temperature_c - 20.0)
    f_ph = nitrification_ph_factor(effective_ph(y, p), p)
    rho1 = f_ph * theta * (p.mu_AOB / p.Y_AOB) * X_AOB * monod(TAN, p.K_TAN) * monod(DO, p.K_O_AOB)
    rho2 = f_ph * theta * (p.mu_NOB / p.Y_NOB) * X_NOB * monod(NO2, p.K_NO2) * monod(DO, p.K_O_NOB)
    return rho1, rho2


def plant_uptake(y: list[float], p: Params) -> tuple[float, float, float]:
    """Tier-2 plant nitrogen uptake (SPEC §4 / §3.4).

    Macrophytes/algae assimilate dissolved N, preferring ammonium over
    nitrate. Returns (U_TAN, U_NO3, mineralisation) all in mg-N/L/day; the
    plant pool grows by (U_TAN+U_NO3) and decays back to TAN. With the
    default ``mu_plant=0`` every term is exactly zero, so Tier-1 is
    unchanged. Uptake is logistic-capped at ``B_plant_max``."""
    TAN, _NO2, NO3, _X_AOB, _X_NOB, _DO, B_plant = y[:7]
    if p.mu_plant <= 0.0 or B_plant <= 0.0:
        return 0.0, 0.0, 0.0
    cap = max(0.0, 1.0 - B_plant / p.B_plant_max)
    base = p.mu_plant * B_plant * cap
    u_tan = base * monod(TAN, p.K_plant_N)
    u_no3 = base * p.f_no3_pref * monod(NO3, p.K_plant_N)
    mineralisation = p.b_plant * B_plant
    return u_tan, u_no3, mineralisation


def denitrification_flux(y: list[float], p: Params) -> float:
    """Tier-2 anoxic NO3→N2 loss [mg-N/L/day] (SPEC §3.4).

    First-order in nitrate, INHIBITED by oxygen (denitrifiers switch on in
    anoxic microsites), so the O2 factor is K/(K+DO) — the complement of the
    nitrifiers' Monod O2 term. This nitrogen leaves the tank as N2 gas, so it
    is the one Tier-2 process that genuinely breaks dissolved-N conservation.
    ``k_denit=0`` (default) ⇒ no loss, Tier-1 unchanged."""
    _TAN, _NO2, NO3, _X_AOB, _X_NOB, DO, _B_plant = y[:7]
    if p.k_denit <= 0.0 or NO3 <= 0.0:
        return 0.0
    o2_inhibit = p.K_O_denit / (p.K_O_denit + max(DO, 0.0))
    return p.k_denit * NO3 * o2_inhibit


def derivatives(t: float, y: list[float], p: Params) -> list[float]:
    """Instantaneous rate of change of the state vector.

    State order: [TAN, NO2, NO3, X_AOB, X_NOB, DO, B_plant, DIC, Alk]
    (state.STATE_ORDER). Indices 0-5 are the Tier-1 core; B_plant + the
    plant/denitrification terms and the DIC/Alk carbonate pool are Tier-2 and
    vanish at the defaults (mu_plant=0, k_denit=0, couple_ph=0), leaving
    Tier-1 byte-identical.
    """
    # Only the attached-biomass and DO states appear explicitly below; the
    # dissolved TAN/NO2/NO3 enter through oxidation_fluxes(y, p).
    _TAN, _NO2, _NO3, X_AOB, X_NOB, DO, _B_plant, _DIC, _Alk = y
    rho1, rho2 = oxidation_fluxes(y, p)
    u_tan, u_no3, mineralisation = plant_uptake(y, p)
    denit = denitrification_flux(y, p)

    # Dissolved nitrogen pool. The TAN source is ADDITIVE: the abiotic
    # bottled-ammonia dose (fishless cycle) plus any feed-derived source set
    # by a feed event (events.apply_event). Keeping them separate lets a
    # scenario dose AND feed without one silently overwriting the other, and
    # mirrors the agent-based model's dose + excretion sum. Tier-2 plants then
    # draw N down (and return decayed N to TAN); denitrification voids NO3 as
    # N2 gas.
    E = p.ammonia_dose_mg_n_l_day + p.feed_dose_mg_n_l_day
    dTAN = E - rho1 - u_tan + mineralisation
    dNO2 = rho1 - rho2
    dNO3 = rho2 - u_no3 - denit

    # Attached biofilm: growth = Y·ρ = μ·X, logistic-capped at media
    # capacity, first-order decay. (Water changes do NOT touch X — see
    # events.py — because the biofilm is attached.)
    dX_AOB = p.Y_AOB * rho1 * (1.0 - X_AOB / p.X_AOB_max) - p.b_AOB * X_AOB
    dX_NOB = p.Y_NOB * rho2 * (1.0 - X_NOB / p.X_NOB_max) - p.b_NOB * X_NOB

    # Oxygen: reaeration + mass-based nitrification demand (3.43 + 1.14
    # g-O2/g-N) + fish respiration. The nitrifier O2 demand already tapers via
    # the Monod O2 terms in rho1/rho2; fish respiration gets the same O2
    # limitation (a fish can't consume a pool that isn't there) so DO stays
    # physically non-negative with a smooth RHS — without it a large constant
    # R_fish integrates DO below 0 while the ABM clamps at 0. At DO->0 every sink
    # vanishes and only positive reaeration acts, so DO is pushed back up.
    # K_O_fish=0.1 mg/L: negligible effect at normal DO, full taper near zero.
    dDO = p.k_a * (p.DO_sat - DO) - 3.43 * rho1 - 1.14 * rho2 - p.R_fish * monod(DO, 0.1)

    # Tier-2 plant N pool: grows by total uptake, decays (mineralised to TAN).
    dB_plant = (u_tan + u_no3) - mineralisation

    # Tier-2 carbonate pool. Coupled: ammonia oxidation releases 2 H+ per N,
    # eating alkalinity (the old-tank pH crash); DIC is held constant (CO2 gas
    # exchange is out of scope, SPEC §0). Uncoupled: both inert ⇒ Tier-1.
    if p.couple_ph > 0.0:
        dAlk = -_ALK_MEQ_PER_MG_N * rho1
    else:
        dAlk = 0.0
    dDIC = 0.0

    return [dTAN, dNO2, dNO3, dX_AOB, dX_NOB, dDO, dB_plant, dDIC, dAlk]
