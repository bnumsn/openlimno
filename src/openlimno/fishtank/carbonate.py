"""Carbonate / pH chemistry (Tier-2, Hour-4 [core] exercise).

pH is solved (not integrated) from the carbonate system given dissolved
inorganic carbon (DIC), alkalinity (Alk), and temperature, by root-finding
on [H+]. Nitrification consumes alkalinity (7.14 g-CaCO3 per g-N), so a
heavily-fed tank drifts down in pH — which shifts the toxic free-NH3
fraction. This module provides the pH solver used both diagnostically
(post-hoc) AND inside the integrated ODE when ``couple_ph>0``
(processes.derivatives consumes Alk via nitrification and re-solves pH
from (DIC, Alk, T) each step, feeding it back into the rates). DIC gas
exchange is still NOT in the continuous ODE state (dDIC=0; the deeper
Tier-2 exercise, SPEC §4.5).

Teaching note: the equilibrium constants here use simple temperature
correlations adequate for freshwater aquaria; they are NOT the full
Millero seawater formulation (out of scope, SPEC §0).
"""

from __future__ import annotations

import math
from typing import Any

from scipy.optimize import brentq

# Alkalinity consumed by nitrification: 2 mol H+ produced per mol N
# oxidised NH4->NO3 → 7.14 g CaCO3 per g N (SPEC §4.5 / §6).
ALK_PER_N_G_CACO3 = 7.14
_MEQ_PER_MG_CACO3 = 1.0 / 50.04  # 1 meq alkalinity = 50.04 mg CaCO3


def k1_k2_kw(temperature_c: float) -> tuple[float, float, float]:
    """Freshwater carbonate dissociation constants K1, K2 and water Kw
    as functions of temperature (°C). Plummer & Busenberg (1982)
    simplified; adequate for teaching freshwater pH dynamics."""
    t_k = temperature_c + 273.15
    # log10 K1, K2 (Harned & Davis / Harned & Scholes freshwater fits)
    pk1 = 3404.71 / t_k + 0.032786 * t_k - 14.8435
    pk2 = 2902.39 / t_k + 0.02379 * t_k - 6.498
    # Kw temperature dependence
    pkw = 4471.33 / t_k + 0.017053 * t_k - 6.0846
    return 10.0 ** (-pk1), 10.0 ** (-pk2), 10.0 ** (-pkw)


def ph_from_dic_alk(dic_mmol_l: float, alk_meq_l: float, temperature_c: float) -> float:
    """Solve pH from DIC [mmol/L], alkalinity [meq/L], temperature.

    Charge/alkalinity balance:
        Alk = [HCO3-] + 2[CO3^2-] + [OH-] - [H+]
    with carbonate speciation a function of [H+] and DIC. Root-solved on
    [H+] over pH ∈ [3, 12].
    """
    k1, k2, kw = k1_k2_kw(temperature_c)
    dic = dic_mmol_l * 1e-3  # mol/L
    alk = alk_meq_l * 1e-3  # eq/L

    def residual(h: float) -> float:
        denom = h * h + k1 * h + k1 * k2
        hco3 = dic * k1 * h / denom
        co3 = dic * k1 * k2 / denom
        oh = kw / h
        return (hco3 + 2.0 * co3 + oh - h) - alk

    h_lo, h_hi = 10.0**-12.0, 10.0**-3.0  # pH 12 .. 3
    # brentq requires a sign change on the bracket; residual is monotone
    # in pH so the only way it fails is genuinely out-of-range input
    # (e.g. alkalinity exceeding what this DIC can carry). Surface that as
    # a clear ValueError instead of brentq's opaque message.
    f_lo, f_hi = residual(h_lo), residual(h_hi)
    if f_lo == 0.0:
        return 12.0
    if f_hi == 0.0:
        return 3.0
    if (f_lo > 0) == (f_hi > 0):
        raise ValueError(
            f"no pH solution in [3, 12] for DIC={dic_mmol_l} mmol/L, "
            f"Alk={alk_meq_l} meq/L, T={temperature_c} C "
            "(alkalinity inconsistent with this DIC?)"
        )
    h_root = brentq(residual, h_lo, h_hi, xtol=1e-14, rtol=1e-10, maxiter=200)
    return -math.log10(h_root)


def alkalinity_drop_meq(delta_n_mg_l: float) -> float:
    """Alkalinity [meq/L] consumed by oxidising ``delta_n_mg_l`` mg-N/L
    of ammonia through to nitrate."""
    mg_caco3 = ALK_PER_N_G_CACO3 * delta_n_mg_l
    return mg_caco3 * _MEQ_PER_MG_CACO3


def diagnostic_ph_trajectory(
    result: Any,
    *,
    initial_alk_meq_l: float = 1.4,
    dic_mmol_l: float = 1.45,
    floor_alk_meq_l: float = 0.1,
) -> Any:
    """Tier-2 Hour-4 capstone: compute a pH trajectory diagnostically from
    a finished Tier-1 Result, by subtracting the alkalinity consumed by
    cumulative nitrification (NO3 produced) from the starting buffer.

    This is the "old-tank-syndrome" demo — a heavily-fed tank drifts the
    pH down as its carbonate buffer is eaten. It is diagnostic (post-hoc),
    not a fully-coupled state integration; coupling DIC/Alk into the ODE
    vector is the deeper Tier-2 exercise (SPEC §4.5).

    Returns the input timeseries DataFrame with added ``alk_meq_l`` and
    ``ph_dynamic`` columns.
    """
    df = result.timeseries.copy()
    # NO3 produced since t0 = nitrogen fully oxidised to nitrate.
    no3_produced = (df["NO3"] - float(df["NO3"].iloc[0])).clip(lower=0.0)
    alk = initial_alk_meq_l - no3_produced.map(alkalinity_drop_meq)
    alk = alk.clip(lower=floor_alk_meq_l)
    df["alk_meq_l"] = alk.round(4)
    temps = float(result.params.temperature_c)
    df["ph_dynamic"] = [round(ph_from_dic_alk(dic_mmol_l, float(a), temps), 3) for a in alk]
    return df
