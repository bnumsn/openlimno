"""Tier-1 nitrogen-cycle tests for openlimno.fishtank.

Pins the SPEC v0.2 corrections (substrate-flux units, DO stoichiometry,
attached biofilm, weeks-long cycle) so the science can't silently
regress. See docs/fishtank/SPEC.md §10 validation strategy.
"""

from __future__ import annotations

import pytest

from openlimno.fishtank import (
    Chemistry,
    Params,
    monod,
    nh3_free_fraction,
    oxidation_fluxes,
    simulate,
)


def test_monod_edges() -> None:
    assert monod(0.0, 1.0) == 0.0
    assert monod(-1.0, 1.0) == 0.0          # clipped, no negative
    assert monod(1.0, 1.0) == pytest.approx(0.5)
    assert monod(1e9, 1.0) == pytest.approx(1.0, abs=1e-6)


def test_nh3_free_fraction_25c() -> None:
    # Emerson 1975: pKa ≈ 9.25 at 25 C → at pH 9.25 free fraction = 0.5
    assert nh3_free_fraction(9.25, 25.0) == pytest.approx(0.5, abs=0.02)
    # Lower pH → far less free (toxic) ammonia
    assert nh3_free_fraction(7.0, 25.0) < 0.01


def test_oxidation_flux_units_are_substrate_not_biomass() -> None:
    """ρ must equal (μ/Y)·X·M·M, i.e. growth/yield — the substrate-flux
    form, NOT the v0.1 biomass-rate μ·X. Verify ρ1 = growth/Y."""
    p = Params(temperature_c=20.0)  # θ = 1 at 20 C
    y = Chemistry(TAN=5.0, NO2=2.0, X_AOB=1.0, X_NOB=1.0, DO=8.0).to_vector()
    rho1, rho2 = oxidation_fluxes(y, p)
    # Hand-compute ρ1 = (μ_AOB/Y_AOB)·X·M(TAN)·M(DO)
    m_tan = 5.0 / (p.K_TAN + 5.0)
    m_do = 8.0 / (p.K_O_AOB + 8.0)
    expected = (p.mu_AOB / p.Y_AOB) * 1.0 * m_tan * m_do
    assert rho1 == pytest.approx(expected, rel=1e-9)
    # And biomass growth = Y·ρ = μ·X·M·M (yield cancels)
    growth = p.Y_AOB * rho1
    assert growth == pytest.approx(p.mu_AOB * 1.0 * m_tan * m_do, rel=1e-9)


def test_fishless_cycle_dissolved_n_conserved() -> None:
    """SPEC §10 #1: Tier-1 has no dissolved-N sink, so final dissolved N
    must equal initial + cumulative ammonia dose, to integrator tolerance."""
    c0 = Chemistry()
    p = Params()
    days = 42.0
    r = simulate(c0, p, days=days)
    df = r.timeseries
    n0 = c0.TAN + c0.NO2 + c0.NO3
    n_end = float(df["TAN"].iloc[-1] + df["NO2"].iloc[-1] + df["NO3"].iloc[-1])
    expected = n0 + p.ammonia_dose_mg_n_l_day * days
    assert n_end == pytest.approx(expected, rel=1e-4)


def test_fishless_cycle_qualitative_pattern() -> None:
    """The textbook sequence: TAN spikes first, NO2 spikes later (NOB is
    slower), NO3 accumulates — over weeks, not days (SPEC §11)."""
    r = simulate(Chemistry(), Params(), days=42)
    df = r.timeseries
    tan_peak_day = float(df.loc[df["TAN"].idxmax(), "day"])
    no2_peak_day = float(df.loc[df["NO2"].idxmax(), "day"])

    # NO2 peak lags TAN peak (NOB slower than AOB)
    assert no2_peak_day > tan_peak_day
    # Cycle spans weeks: NO2 peak must be at least 2 weeks in
    assert no2_peak_day >= 14.0
    # NO3 accumulates monotonically once nitrification is established
    no3 = df[df["day"] >= 28]["NO3"]
    assert (no3.diff().dropna() >= -1e-6).all()
    # NO3 ends well above its initial value
    assert float(df["NO3"].iloc[-1]) > 50.0


def test_attached_biomass_grows_from_seed_to_capacity() -> None:
    """Biofilm starts at the tiny seed and approaches (never exceeds) the
    media carrying capacity X_max — the logistic colonisation S-curve."""
    p = Params(X_AOB_max=5.0)
    r = simulate(Chemistry(X_AOB=0.02), p, days=42)
    df = r.timeseries
    assert float(df["X_AOB"].iloc[0]) == pytest.approx(0.02, abs=1e-6)
    assert float(df["X_AOB"].max()) <= p.X_AOB_max + 1e-6   # never exceeds cap
    assert float(df["X_AOB"].iloc[-1]) > 1.0                 # did colonise


def test_do_stoichiometry_demand_is_mass_based() -> None:
    """Heavy nitrification must draw DO down materially via the 3.43/1.14
    g-O2/g-N mass demand (not the v0.1 molar 1.5)."""
    r = simulate(Chemistry(), Params(), days=42)
    df = r.timeseries
    # During peak nitrification DO should dip well below saturation
    assert float(df["DO"].min()) < 4.0


def test_params_with_overrides_rejects_unknown() -> None:
    p = Params()
    p2 = p.with_overrides(mu_AOB=0.9)
    assert p2.mu_AOB == 0.9
    assert p.mu_AOB == 0.55          # original unchanged (returns a copy)
    with pytest.raises(ValueError, match="unknown parameter"):
        p.with_overrides(not_a_param=1.0)


def test_state_vector_roundtrip() -> None:
    c = Chemistry(TAN=1.5, NO2=0.3, NO3=12.0, X_AOB=2.0, X_NOB=1.0, DO=6.5)
    v = c.to_vector()
    assert v == [1.5, 0.3, 12.0, 2.0, 1.0, 6.5]
    assert Chemistry.from_vector(v) == c


def test_higher_dose_gives_higher_nitrate() -> None:
    """Monotonicity sanity: more ammonia in → more nitrate out."""
    low = simulate(Chemistry(), Params(ammonia_dose_mg_n_l_day=1.0), days=42)
    high = simulate(Chemistry(), Params(ammonia_dose_mg_n_l_day=3.0), days=42)
    assert float(high.timeseries["NO3"].iloc[-1]) > float(low.timeseries["NO3"].iloc[-1])
