"""Fishtank model state + parameters (Tier-1 nitrogen cycle).

Teaching-first: plain dataclasses, units in every field comment. The
state vector order is fixed and shared with ``processes.derivatives``.
See docs/fishtank/SPEC.md §1 + §6.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# Fixed state-vector order. processes.derivatives unpacks in THIS order.
# Indices 0-5 are the Tier-1 nitrogen/oxygen core; B_plant (idx 6) is the
# Tier-2 plant nitrogen pool, inert unless mu_plant>0 (SPEC §4). DIC/Alk are
# added by the Tier-2 carbonate-coupling extension; B_fish stays ABM-only.
STATE_ORDER = ("TAN", "NO2", "NO3", "X_AOB", "X_NOB", "DO", "B_plant")


@dataclass
class Chemistry:
    """Tier-1 state. Dissolved species in mg/L (mg-N/L for N); attached
    bacteria in mg/L on a per-tank-volume bookkeeping basis (SPEC §1)."""

    TAN: float = 0.0      # total ammonia N (NH3 + NH4+)        [mg-N/L]
    NO2: float = 0.0      # nitrite N                            [mg-N/L]
    NO3: float = 5.0      # nitrate N                            [mg-N/L]
    X_AOB: float = 0.02   # ammonia-oxidiser biomass (attached)  [mg/L]
    X_NOB: float = 0.02   # nitrite-oxidiser biomass (attached)  [mg/L]
    DO: float = 7.5       # dissolved oxygen                     [mg-O2/L]
    B_plant: float = 0.0  # plant nitrogen pool (Tier-2)         [mg-N/L]

    def to_vector(self) -> list[float]:
        return [getattr(self, name) for name in STATE_ORDER]

    @classmethod
    def from_vector(cls, y: list[float]) -> Chemistry:
        return cls(**dict(zip(STATE_ORDER, (float(v) for v in y), strict=True)))


@dataclass
class Params:
    """Aquarium-tuned kinetics (SPEC §6). ASM1 FORMS, aquarium MAGNITUDES.

    Defaults aim for a 3-6 week fishless cycle; calibrate against a real
    log rather than trusting them (that's the Hour-3 lesson)."""

    # --- nitrification kinetics ---
    mu_AOB: float = 0.55       # AOB max specific growth         [1/day]
    mu_NOB: float = 0.40       # NOB max specific growth (slower) [1/day]
    Y_AOB: float = 0.15        # AOB yield                       [mg-VSS/mg-N]
    Y_NOB: float = 0.041       # NOB yield                       [mg-VSS/mg-N]
    K_TAN: float = 1.0         # TAN half-saturation             [mg-N/L]
    K_NO2: float = 1.3         # NO2 half-saturation             [mg-N/L]
    K_O_AOB: float = 0.50      # O2 half-sat (AOB)               [mg-O2/L]
    K_O_NOB: float = 0.68      # O2 half-sat (NOB)               [mg-O2/L]
    b_AOB: float = 0.10        # AOB decay                       [1/day]
    b_NOB: float = 0.10        # NOB decay                       [1/day]
    # --- biofilm carrying capacity (media-limited) ---
    X_AOB_max: float = 5.0     # AOB attached capacity           [mg/L]
    X_NOB_max: float = 5.0     # NOB attached capacity           [mg/L]
    # --- physical / forcing ---
    theta: float = 1.07        # Arrhenius factor per degC       [-]
    temperature_c: float = 25.0
    k_a: float = 2.0           # reaeration                      [1/day]
    DO_sat: float = 8.0        # O2 saturation (const Tier-1)    [mg-O2/L]
    R_fish: float = 0.0        # fish respiration (const Tier-1) [mg-O2/L/day]
    a_exc: float = 0.0276      # N excreted per g food           [g-N/g-food]
    volume_l: float = 120.0    # tank volume                     [L]
    ph: float = 7.4            # fixed pH in Tier-1              [-]
    # --- Tier-1 TAN sources (additive: total source = abiotic dose + feed) ---
    ammonia_dose_mg_n_l_day: float = 2.0   # abiotic bottled-ammonia dose [mg-N/L/day]
    feed_dose_mg_n_l_day: float = 0.0      # feed-derived TAN source (set by feed events) [mg-N/L/day]
    # --- Tier-2 plant nitrogen uptake (all 0 ⇒ no plants, Tier-1 unchanged) ---
    mu_plant: float = 0.0      # plant N-uptake max specific rate [1/day]
    K_plant_N: float = 0.3     # half-sat for plant N uptake      [mg-N/L]
    B_plant_max: float = 8.0   # plant N pool carrying capacity   [mg-N/L]
    b_plant: float = 0.02      # plant decay → mineralised to TAN [1/day]
    f_no3_pref: float = 0.4    # NO3 uptake relative to NH4 (plants prefer NH4) [-]
    # --- Tier-2 denitrification (k_denit=0 ⇒ no anoxic N loss, Tier-1) ---
    k_denit: float = 0.0       # 1st-order NO3→N2 loss rate       [1/day]
    K_O_denit: float = 0.3     # O2 half-INHIBITION for denit     [mg-O2/L]

    def with_overrides(self, **kw: float) -> Params:
        valid = {f.name for f in fields(self)}
        unknown = set(kw) - valid
        if unknown:
            raise ValueError(f"unknown parameter override(s): {sorted(unknown)}")
        merged = {f.name: getattr(self, f.name) for f in fields(self)}
        merged.update(kw)
        return Params(**merged)


def nh3_free_fraction(ph: float, temperature_c: float) -> float:
    """Unionised-ammonia fraction f = 1/(1 + 10^(pKa(T) - pH)).

    pKa(T) from Emerson et al. (1975): pKa = 0.09018 + 2729.92/(T_K).
    NH3_free = f * TAN; the free form is the toxic one (SPEC §2)."""
    t_k = temperature_c + 273.15
    pka = 0.09018 + 2729.92 / t_k
    return 1.0 / (1.0 + 10.0 ** (pka - ph))
