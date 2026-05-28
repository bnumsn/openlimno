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
    # Cycle genuinely spans weeks (not days): NO2 peak ≥ 2 weeks in,
    # AND nitrite stays elevated (>1 mg-N/L) for at least 14 days — this
    # pins "weeks-long" more strongly than a single peak-day check.
    assert no2_peak_day >= 14.0
    elevated_no2_days = float(df[df["NO2"] > 1.0]["day"].max() - df[df["NO2"] > 1.0]["day"].min())
    assert elevated_no2_days >= 14.0, f"NO2 elevated only {elevated_no2_days:.0f} days"
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


# --- Hour-3: events + calibration ---------------------------------------


def test_water_change_dilutes_dissolved_not_biofilm() -> None:
    """A water change must dilute dissolved N toward tap but leave the
    ATTACHED biofilm (X) intact (SPEC §1/§5)."""
    from openlimno.fishtank.events import Event, EventSchedule, TapWater

    # Single big water change at day 21 on an established tank.
    p = Params()
    sched = EventSchedule(
        events=[Event(day=21.0, kind="water_change", value=0.50)],
        tap_water=TapWater(NO3=5.0),
    )
    r = simulate(Chemistry(), p, days=42, schedule=sched)
    df = r.timeseries
    before = df[df["day"] < 21.0].iloc[-1]
    after = df[df["day"] >= 21.0].iloc[0]
    # NO3 must drop substantially (50% toward tap)
    assert after["NO3"] < before["NO3"] * 0.7
    # X_AOB must NOT be halved — attached biofilm survives. (Allow the
    # small ODE change over the <=0.25-day sampling gap, not a 50% cut.)
    assert after["X_AOB"] > before["X_AOB"] * 0.95


def test_water_change_on_off_grid_day() -> None:
    """Regression for the off-grid event-boundary corruption: an event on
    a day that does NOT land on the output grid (e.g. 20.3 with a 6-hour
    grid) must still apply at its true time, not be mislabelled by the
    nearest grid point."""
    from openlimno.fishtank.events import Event, EventSchedule, TapWater

    sched = EventSchedule(
        events=[Event(day=20.3, kind="water_change", value=0.80)],
        tap_water=TapWater(NO3=5.0),
    )
    r = simulate(Chemistry(), Params(), days=42, schedule=sched, dt_output_hours=6.0)
    df = r.timeseries
    before = df[df["day"] < 20.3]["NO3"].iloc[-1]
    after = df[df["day"] >= 20.3]["NO3"].iloc[0]
    # An 80% water change must drop NO3 sharply right at ~20.3, not at 20.25
    # with the wrong (pre-event) value carried over.
    assert after < before * 0.5
    # And the first post-event timestamp is at/after the true event day.
    assert float(df[df["day"] >= 20.3]["day"].iloc[0]) >= 20.3


def test_repeat_days_expands_events() -> None:
    """repeat_days materialises an event on a regular cadence (SPEC §5)."""
    from openlimno.fishtank.events import Event, EventSchedule

    sched = EventSchedule(events=[Event(day=7.0, kind="water_change", value=0.25, repeat_days=7.0)])
    expanded_days = sorted({e.day for e in sched.expand(42.0)})
    assert expanded_days == [7.0, 14.0, 21.0, 28.0, 35.0]   # < 42, every 7


def test_day_zero_event_applies() -> None:
    """An event scheduled on day 0 must apply to the initial state
    (previously dropped because boundaries were strictly inside (0,days))."""
    from openlimno.fishtank.events import Event, EventSchedule

    sched = EventSchedule(events=[Event(day=0.0, kind="ammonia_dose", value=4.0)])
    r = simulate(Chemistry(), Params(ammonia_dose_mg_n_l_day=2.0), days=10, schedule=sched)
    # The day-0 override to 4.0 must take effect: more N in than the 2.0
    # default would give over 10 days.
    no_event = simulate(Chemistry(), Params(ammonia_dose_mg_n_l_day=2.0), days=10)
    total_with = r.timeseries[["TAN", "NO2", "NO3"]].iloc[-1].sum()
    total_without = no_event.timeseries[["TAN", "NO2", "NO3"]].iloc[-1].sum()
    assert total_with > total_without * 1.3


def test_feed_event_changes_ammonia_source() -> None:
    from openlimno.fishtank.events import Event, TapWater, apply_event

    p = Params(volume_l=100.0, a_exc=0.0276)
    c = Chemistry()
    ev = Event(day=5.0, kind="feed", value=2.0)   # 2 g food/day
    _c2, p2 = apply_event(c, p, ev, TapWater())
    # dose = a_exc[g-N/g] * F[g/day] / V[L] * 1000 → mg-N/L/day
    # = 0.0276 * 2 / 100 * 1000 = 0.552 mg-N/L/day (NOT 0.000552 — the
    # 1000x unit bug that this test previously encoded).
    assert p2.ammonia_dose_mg_n_l_day == pytest.approx(0.0276 * 2.0 / 100.0 * 1000.0)
    assert p2.ammonia_dose_mg_n_l_day == pytest.approx(0.552)


def test_calibration_recovers_known_truth() -> None:
    """Hour-3 capstone: fitting the synthetic log must recover the
    parameters it was generated with (mu_AOB≈0.62, mu_NOB≈0.35)."""
    import pandas as pd

    from openlimno.fishtank.calibration import fit

    here = __import__("pathlib").Path(__file__).resolve()
    repo = here.parents[2]
    obs = pd.read_csv(repo / "data" / "aquarium_logs" / "tank_A_fishless.csv")
    result = fit(obs, base_params=Params(ammonia_dose_mg_n_l_day=2.0))
    assert result.converged
    assert result.best_params["mu_AOB"] == pytest.approx(0.62, abs=0.08)
    assert result.best_params["mu_NOB"] == pytest.approx(0.35, abs=0.08)


def test_calibration_rmse_normalises_across_variables() -> None:
    """rmse() must normalise per variable so large-magnitude NO3 doesn't
    swamp small TAN/NO2 (SPEC Hour-3 common-mistake note)."""
    import pandas as pd

    from openlimno.fishtank.calibration import rmse

    merged = pd.DataFrame(
        [
            {"day": 1, "variable": "TAN", "sim": 2.0, "obs": 1.0},   # off by 1, TAN range 1
            {"day": 2, "variable": "TAN", "sim": 1.0, "obs": 2.0},
            {"day": 1, "variable": "NO3", "sim": 80.0, "obs": 40.0}, # off by 40, NO3 range 40
            {"day": 2, "variable": "NO3", "sim": 40.0, "obs": 80.0},
        ]
    )
    # Both variables are off by their full range → normalised residual ≈1
    # each, so pooled RMSE ≈ 1 — NO3's large magnitude does NOT dominate.
    assert rmse(merged) == pytest.approx(1.0, abs=0.01)


# --- Hour-4: carbonate / pH (Tier-2) ------------------------------------


def test_ph_decreases_as_alkalinity_drops() -> None:
    """Lower alkalinity → lower pH (carbonate buffer exhaustion)."""
    from openlimno.fishtank import ph_from_dic_alk

    ph_high = ph_from_dic_alk(2.0, 2.0, 25.0)
    ph_low = ph_from_dic_alk(2.0, 0.5, 25.0)
    assert ph_low < ph_high


def test_alkalinity_drop_stoichiometry() -> None:
    """7.14 g-CaCO3 per g-N → meq via /50.04."""
    from openlimno.fishtank import alkalinity_drop_meq

    # 10 mg-N/L oxidised → 71.4 mg-CaCO3/L → 71.4/50.04 meq/L
    assert alkalinity_drop_meq(10.0) == pytest.approx(71.4 / 50.04, rel=1e-6)
    assert alkalinity_drop_meq(0.0) == 0.0


def test_diagnostic_ph_trajectory_crashes_under_heavy_load() -> None:
    """Old-tank-syndrome: a heavily-fed tank drifts pH down as its
    carbonate buffer is consumed by cumulative nitrification."""
    from openlimno.fishtank import diagnostic_ph_trajectory

    r = simulate(Chemistry(), Params(ammonia_dose_mg_n_l_day=2.0), days=42)
    df = diagnostic_ph_trajectory(r, initial_alk_meq_l=3.0, dic_mmol_l=2.0)
    assert "ph_dynamic" in df.columns
    assert "alk_meq_l" in df.columns
    ph0 = float(df["ph_dynamic"].iloc[0])
    ph_end = float(df["ph_dynamic"].iloc[-1])
    assert ph_end < ph0 - 1.0          # at least a full pH unit crash
    # Alkalinity is monotone non-increasing (only consumed, never made here)
    assert (df["alk_meq_l"].diff().dropna() <= 1e-9).all()


def test_plot_result_returns_figure_without_streamlit() -> None:
    """plot_result must work with matplotlib only (no Streamlit needed)."""
    from openlimno.fishtank.studio import plot_result

    r = simulate(Chemistry(), Params(), days=14)
    fig = plot_result(r)
    assert fig is not None
    assert len(fig.axes) == 2        # two stacked panels
