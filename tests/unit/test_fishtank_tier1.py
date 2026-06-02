"""Tier-1 nitrogen-cycle tests for openlimno.fishtank.

Pins the SPEC v0.2 corrections (substrate-flux units, DO stoichiometry,
attached biofilm, weeks-long cycle) so the science can't silently
regress. See docs/fishtank/SPEC.md §10 validation strategy.
"""

from __future__ import annotations

import json
from pathlib import Path

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


def test_result_carries_events_log_and_provenance() -> None:
    r = simulate(Chemistry(), Params(), days=1)
    assert list(r.events_log.columns)[:4] == ["day", "kind", "target", "value"]
    assert r.provenance["schema"] == "openlimno-provenance/0.1+fishtank"
    assert r.provenance["outputs"]["timeseries_rows"] == len(r.timeseries)
    assert r.provenance["parameter_fingerprint"]


def test_provenance_fingerprint_includes_tap_water() -> None:
    from openlimno.fishtank.events import Event, EventSchedule, TapWater

    event = Event(day=1.0, kind="water_change", value=0.5)
    low_tap = EventSchedule(events=[event], tap_water=TapWater(NO3=0.0))
    high_tap = EventSchedule(events=[event], tap_water=TapWater(NO3=100.0))
    low = simulate(Chemistry(NO3=50.0), Params(ammonia_dose_mg_n_l_day=0.0), days=2, schedule=low_tap)
    high = simulate(
        Chemistry(NO3=50.0),
        Params(ammonia_dose_mg_n_l_day=0.0),
        days=2,
        schedule=high_tap,
    )

    assert float(low.timeseries["NO3"].iloc[-1]) != float(high.timeseries["NO3"].iloc[-1])
    assert low.provenance["parameter_fingerprint"] != high.provenance["parameter_fingerprint"]
    assert high.provenance["inputs"]["tap_water"]["NO3"] == 100.0


def test_simulate_rejects_invalid_run_window() -> None:
    with pytest.raises(ValueError, match="days"):
        simulate(days=-1)
    with pytest.raises(ValueError, match="dt_output_hours"):
        simulate(days=1, dt_output_hours=0)


def test_dt_output_hours_preserves_requested_cadence() -> None:
    r = simulate(days=1.0, dt_output_hours=7.0)
    days = r.timeseries["day"].tolist()
    assert days == pytest.approx([0.0, 7.0 / 24.0, 14.0 / 24.0, 21.0 / 24.0, 1.0])
    assert (r.timeseries["day"].diff().dropna() * 24.0).tolist() == pytest.approx(
        [7.0, 7.0, 7.0, 3.0]
    )


def test_zero_day_run_returns_initial_state() -> None:
    r = simulate(Chemistry(TAN=1.2), Params(), days=0)
    assert len(r.timeseries) == 1
    assert float(r.timeseries["day"].iloc[0]) == 0.0
    assert float(r.timeseries["TAN"].iloc[0]) == pytest.approx(1.2)


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


def test_invalid_event_rejected() -> None:
    from openlimno.fishtank.events import Event

    with pytest.raises(ValueError, match="unknown event kind"):
        Event(day=1.0, kind="typo", value=1.0)
    with pytest.raises(ValueError, match="fraction"):
        Event(day=1.0, kind="water_change", value=1.5)


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


def test_feed_event_sets_additive_feed_dose() -> None:
    """A feed event sets the SEPARATE feed_dose source and leaves the abiotic
    ammonia_dose intact, so dosing + feeding ADD (they no longer overwrite
    each other). This keeps the ODE consistent with the ABM, which sums the
    abiotic dose and per-fish excretion."""
    from openlimno.fishtank.events import Event, TapWater, apply_event
    from openlimno.fishtank.processes import derivatives

    p = Params(volume_l=100.0, a_exc=0.0276, ammonia_dose_mg_n_l_day=1.0)
    c = Chemistry()
    ev = Event(day=5.0, kind="feed", value=2.0)   # 2 g food/day
    _c2, p2 = apply_event(c, p, ev, TapWater())
    # feed_dose = a_exc[g-N/g] * F[g/day] / V[L] * 1000 → mg-N/L/day
    # = 0.0276 * 2 / 100 * 1000 = 0.552 mg-N/L/day
    assert p2.feed_dose_mg_n_l_day == pytest.approx(0.552)
    # The abiotic dose is NOT overwritten by feeding.
    assert p2.ammonia_dose_mg_n_l_day == pytest.approx(1.0)
    # derivatives() uses the SUM as the TAN source (1.0 + 0.552, minus rho1≈0
    # at the tiny seed/zero substrate start).
    y = Chemistry(TAN=0.0, X_AOB=0.0, X_NOB=0.0).to_vector()
    dTAN = derivatives(0.0, y, p2)[0]
    assert dTAN == pytest.approx(1.0 + 0.552, rel=1e-9)


def test_scenario_io_and_cli(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from openlimno.fishtank.cli import main
    from openlimno.fishtank.io import load_scenario, write_result

    scenario_path = Path("examples/fishless_cycle.yaml")
    scenario = load_scenario(scenario_path)
    result = scenario.run()
    assert result.provenance["scenario"]["sha256"]
    assert len(result.events_log) == 2

    paths = write_result(result, tmp_path)
    assert paths["timeseries"].exists()
    assert paths["events_log"].exists()
    prov = json.loads(paths["provenance"].read_text())
    assert prov["schema"] == "openlimno-provenance/0.1+fishtank"
    assert "timeseries" in prov["outputs"]["files"]

    runner = CliRunner()
    validate = runner.invoke(main, ["validate", str(scenario_path)])
    assert validate.exit_code == 0, validate.output
    run = runner.invoke(main, ["run", str(scenario_path), "--out-dir", str(tmp_path / "cli")])
    assert run.exit_code == 0, run.output
    assert (tmp_path / "cli" / "provenance.json").exists()


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


def test_browser_studio_payload_contract() -> None:
    """The commercial browser Studio backend should run without Streamlit."""
    from openlimno.fishtank.studio_assets import INDEX_HTML
    from openlimno.fishtank.studio_http import (
        default_studio_payload,
        run_agent_based_studio_payload,
        run_studio_payload,
    )

    payload = default_studio_payload()
    payload["run"]["days"] = 7
    payload["agents"]["fish_count"] = 6   # default scenario is fishless; add fish to exercise the snapshot
    result = run_studio_payload(payload)
    abm = run_agent_based_studio_payload(payload)
    assert result["ok"] is True
    assert result["summary"]["final_NO3"] >= 5.0
    assert result["timeseries"]
    assert result["ph_diagnostic"]
    assert result["provenance"]["schema"] == "openlimno-provenance/0.1+fishtank"
    assert abm["ok"] is True
    assert abm["schema"] == "openlimno-fishtank-abm/0.1"
    assert abm["timeseries"]
    assert abm["agents"]["fish"]
    assert abm["agents"]["microbes"]
    assert 'id="tankCanvas"' in INDEX_HTML
    assert "ABM Agents" in INDEX_HTML
    assert "/api/agents" in INDEX_HTML
    assert "three.module.min.js" in INDEX_HTML
    assert "fishtank:result" in INDEX_HTML
    assert "Click Calibrate to fit bundled tank_A_fishless.csv" in INDEX_HTML
    assert "rows omitted" in INDEX_HTML
    assert "table-note" in INDEX_HTML


def test_studio_partial_payloads_use_browser_default_baseline() -> None:
    from openlimno.fishtank.studio_http import (
        default_studio_payload,
        run_agent_based_studio_payload,
        run_studio_payload,
    )

    default_payload = default_studio_payload()
    empty_ode = run_studio_payload({})
    default_ode = run_studio_payload(default_payload)
    assert empty_ode["summary"] == default_ode["summary"]
    assert empty_ode["ph_diagnostic"][-1]["ph_dynamic"] == default_ode["ph_diagnostic"][-1]["ph_dynamic"]

    empty_abm = run_agent_based_studio_payload({})
    default_abm = run_agent_based_studio_payload(default_payload)
    assert empty_abm["summary"] == default_abm["summary"]

    partial = {"run": {"days": 7.0}}
    expected = default_studio_payload()
    expected["run"]["days"] = 7.0
    assert run_studio_payload(partial)["summary"] == run_studio_payload(expected)["summary"]


def test_event_aliases_are_shared_by_studio_and_abm() -> None:
    from openlimno.fishtank.studio_http import (
        run_agent_based_studio_payload,
        run_studio_payload,
    )

    payload = {
        "tank": {"volume_l": 120.0, "temperature_c": 25.0, "ph": 7.4},
        "run": {"days": 2.0, "dt_output_hours": 12.0},
        "chemistry": {"TAN": 0.0, "NO2": 0.0, "NO3": 50.0, "X_AOB": 0.02, "X_NOB": 0.02, "DO": 7.5},
        "parameters": {"ammonia_dose_mg_n_l_day": 0.0},
        "tap_water": {"TAN": 0.0, "NO2": 0.0, "NO3": 0.0, "DO": 8.5},
        "agents": {"seed": 4, "dt_days": 0.25, "fish_count": 0, "aob_agents": 4, "nob_agents": 4},
        "events": [{"day": 1.0, "type": "water_change", "fraction": 0.5}],
    }
    ode = run_studio_payload(payload)
    abm = run_agent_based_studio_payload(payload)

    assert ode["events_log"][0]["kind"] == "water_change"
    assert abm["event_log"][0]["kind"] == "water_change"
    assert ode["summary"]["final_NO3"] < 30.0
    assert abm["summary"]["final_NO3"] < 30.0


def test_studio_payload_limits_reject_expensive_runs() -> None:
    from openlimno.fishtank.studio_http import (
        default_studio_payload,
        run_agent_based_studio_payload,
        run_studio_payload,
    )

    payload = default_studio_payload()
    payload["run"]["days"] = 366.0
    with pytest.raises(ValueError, match="run.days must be <= 365"):
        run_studio_payload(payload)

    payload = default_studio_payload()
    payload["run"]["days"] = 121.0
    with pytest.raises(ValueError, match="run.days must be <= 120"):
        run_agent_based_studio_payload(payload)

    payload = default_studio_payload()
    payload["run"]["dt_output_hours"] = 0.01
    with pytest.raises(ValueError, match="output grid is too large"):
        run_studio_payload(payload)

    payload = default_studio_payload()
    payload["events"] = [
        {"day": 0.0, "kind": "ammonia_dose", "value": 2.0}
        for _ in range(201)
    ]
    with pytest.raises(ValueError, match="at most 200"):
        run_studio_payload(payload)

    payload = default_studio_payload()
    payload["events"] = [
        {"day": 0.0, "kind": "water_change", "value": 0.1, "repeat_days": 0.01}
    ]
    with pytest.raises(ValueError, match="repeat_days"):
        run_studio_payload(payload)


def test_studio_http_rejects_oversized_body() -> None:
    import http.client
    import threading

    from openlimno.fishtank.studio_http import (
        _REQUEST_BODY_LIMIT_BYTES,
        _FishtankStudioHandler,
        _FishtankStudioServer,
        find_free_port,
    )

    port = find_free_port()
    server = _FishtankStudioServer(("127.0.0.1", port), _FishtankStudioHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/api/run", body=b"x" * (_REQUEST_BODY_LIMIT_BYTES + 1))
        response = conn.getresponse()
        body = response.read()
        conn.close()
        assert response.status == 413
        assert b"request body too large" in body
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_agent_based_model_is_seeded_and_agent_explicit() -> None:
    from openlimno.fishtank import simulate_agent_based_model
    from openlimno.fishtank.studio_http import default_studio_payload

    payload = default_studio_payload()
    payload["run"]["days"] = 5
    payload["agents"].update(
        {
            "seed": 123,
            "fish_count": 4,
            "feed_g_day": 1.6,
            "aob_agents": 6,
            "nob_agents": 6,
            "dt_days": 0.25,
        }
    )
    first = simulate_agent_based_model(payload)
    second = simulate_agent_based_model(payload)
    assert first["summary"] == second["summary"]
    assert first["agents"]["fish"][0] == second["agents"]["fish"][0]
    assert len(first["agents"]["fish"]) == 4
    assert len(first["agents"]["microbes"]) == 12
    assert first["timeseries"][0]["fish_alive"] == 4
    assert first["summary"]["AOB_biomass"] > payload["chemistry"]["X_AOB"]
    assert first["summary"]["NOB_biomass"] > 0.0


def test_abm_fishless_dissolved_n_conserved() -> None:
    """ABM mirror of test_fishless_cycle_dissolved_n_conserved: with no fish
    the only N source is the ammonia dose and oxidation is an internal
    transfer, so dissolved N (TAN+NO2+NO3) must close to dose × days. Pins
    that the ABM doesn't silently create/destroy N through its clamps."""
    from openlimno.fishtank import simulate_agent_based_model

    days = 42.0
    payload = {
        "tank": {"volume_l": 120.0, "temperature_c": 25.0, "ph": 7.4},
        "run": {"days": days, "dt_output_hours": 6.0},
        "chemistry": {"TAN": 0.0, "NO2": 0.0, "NO3": 5.0, "X_AOB": 0.02, "X_NOB": 0.02, "DO": 7.5},
        "parameters": {"ammonia_dose_mg_n_l_day": 2.0},
        "agents": {"seed": 1, "dt_days": 0.25, "fish_count": 0, "aob_agents": 12, "nob_agents": 12,
                   "feed_g_day": 0.0},
    }
    ts = simulate_agent_based_model(payload)["timeseries"]
    n0 = 0.0 + 0.0 + 5.0
    n_end = ts[-1]["TAN"] + ts[-1]["NO2"] + ts[-1]["NO3"]
    assert n_end == pytest.approx(n0 + 2.0 * days, rel=1e-3)


def test_abm_applies_ammonia_dose_with_fish_present() -> None:
    """Regression: the ABM must keep applying the abiotic ammonia dose even
    when fish are stocked (the old either/or logic dropped it whenever any
    fish existed, starving the ABM of its main N source). A dosed tank with
    fish must accumulate far more nitrate than the same fish with no dose."""
    from openlimno.fishtank import simulate_agent_based_model

    base = {
        "tank": {"volume_l": 120.0, "temperature_c": 25.0, "ph": 7.4},
        "run": {"days": 30.0, "dt_output_hours": 6.0},
        "chemistry": {"TAN": 0.0, "NO2": 0.0, "NO3": 5.0, "X_AOB": 0.02, "X_NOB": 0.02, "DO": 7.5},
        "agents": {"seed": 7, "dt_days": 0.25, "fish_count": 4, "fish_biomass_g": 4.0,
                   "feed_g_day": 0.3, "aob_agents": 12, "nob_agents": 12},
    }
    dosed = {**base, "parameters": {"ammonia_dose_mg_n_l_day": 2.0}}
    undosed = {**base, "parameters": {"ammonia_dose_mg_n_l_day": 0.0}}
    no3_dosed = simulate_agent_based_model(dosed)["summary"]["final_NO3"]
    no3_undosed = simulate_agent_based_model(undosed)["summary"]["final_NO3"]
    assert no3_dosed > no3_undosed * 3.0


def test_abm_rejects_invalid_run_window() -> None:
    """ABM mirrors the ODE solver's run-arg validation (no silent no-op runs)."""
    from openlimno.fishtank import simulate_agent_based_model

    with pytest.raises(ValueError, match="run.days"):
        simulate_agent_based_model({"run": {"days": -1.0}})
    with pytest.raises(ValueError, match="dt_output_hours"):
        simulate_agent_based_model({"run": {"days": 1.0, "dt_output_hours": 0.0}})


def test_abm_honours_full_parameter_overrides() -> None:
    """The ABM must ingest the whole Params set (not just volume/temp/pH/dose),
    so a kinetic override from the scenario actually changes the ABM — it used
    to be silently ignored, islanding the ABM from calibration/equipment."""
    from openlimno.fishtank import simulate_agent_based_model

    base = {
        "tank": {"volume_l": 120.0, "temperature_c": 25.0, "ph": 7.4},
        "run": {"days": 20.0, "dt_output_hours": 6.0},
        "chemistry": {"TAN": 0.0, "NO2": 0.0, "NO3": 5.0, "X_AOB": 0.02, "X_NOB": 0.02, "DO": 7.5},
        "agents": {"seed": 3, "dt_days": 0.25, "fish_count": 0, "aob_agents": 12, "nob_agents": 12,
                   "feed_g_day": 0.0},
    }
    fast = {**base, "parameters": {"ammonia_dose_mg_n_l_day": 2.0, "mu_AOB": 1.2}}
    slow = {**base, "parameters": {"ammonia_dose_mg_n_l_day": 2.0, "mu_AOB": 0.25}}
    aob_fast = simulate_agent_based_model(fast)["summary"]["AOB_biomass"]
    aob_slow = simulate_agent_based_model(slow)["summary"]["AOB_biomass"]
    assert aob_fast > aob_slow      # faster AOB growth ⇒ more biofilm by day 20
    # Unknown parameter keys are rejected, matching io.scenario_from_mapping.
    with pytest.raises(ValueError, match="unknown parameter"):
        simulate_agent_based_model({**base, "parameters": {"not_a_param": 1.0}})


# --- Scenario library: a coherent case for each typical situation ----------


def test_scenario_library_default_is_fishless() -> None:
    from openlimno.fishtank.library import scenario_payload, scenarios
    from openlimno.fishtank.studio_http import DEFAULT_SCENARIO, default_studio_payload

    lib = scenarios()
    assert set(lib) == {
        "fishless_cycle",
        "seeded_instant_cycle",
        "fish_in_disaster",
        "mature_stocked_tank",
        "old_tank_syndrome",
    }
    assert DEFAULT_SCENARIO == "fishless_cycle"
    assert default_studio_payload() == scenario_payload("fishless_cycle")
    # Returned payloads are deep copies — mutating one must not corrupt the lib.
    p = scenario_payload("fishless_cycle")
    p["tank"]["volume_l"] = 999.0
    assert scenario_payload("fishless_cycle")["tank"]["volume_l"] == 120.0


def test_scenario_library_unknown_name_raises() -> None:
    from openlimno.fishtank.library import scenario_payload

    with pytest.raises(ValueError, match="unknown scenario"):
        scenario_payload("not_a_scenario")


def test_every_scenario_runs_ode_and_abm() -> None:
    """Each library scenario must be coherent for BOTH Studio panels."""
    from openlimno.fishtank.library import scenarios
    from openlimno.fishtank.studio_http import run_agent_based_studio_payload, run_studio_payload

    for name, entry in scenarios().items():
        ode = run_studio_payload(entry["payload"])
        abm = run_agent_based_studio_payload(entry["payload"])
        assert ode["ok"] is True, name
        assert abm["ok"] is True, name
        assert ode["timeseries"], name
        assert abm["timeseries"], name


def test_scenario_contracts_match_their_teaching_point() -> None:
    """Pin the qualitative behaviour each scenario is supposed to demonstrate
    so a parameter drift can't silently turn a healthy tank lethal etc."""
    from openlimno.fishtank.library import scenario_payload
    from openlimno.fishtank.studio_http import run_agent_based_studio_payload, run_studio_payload

    def ode(name: str) -> dict:
        return run_studio_payload(scenario_payload(name))

    def abm(name: str) -> dict:
        return run_agent_based_studio_payload(scenario_payload(name))["summary"]

    # Fishless cycle: no fish, but a clear toxic ammonia spike (the cascade).
    fishless = ode("fishless_cycle")
    assert fishless["summary"]["max_NH3_free"] > 0.05
    assert abm("fishless_cycle")["fish_mortality"] == 0
    assert abm("fishless_cycle")["fish_alive"] == 0

    # Seeded media suppresses the spike (instant cycle).
    assert ode("seeded_instant_cycle")["summary"]["max_NH3_free"] < 0.03

    # Fish-in disaster: toxic ammonia and most fish die.
    disaster = abm("fish_in_disaster")
    assert disaster["fish_mortality"] >= 5
    assert ode("fish_in_disaster")["summary"]["max_NH3_free"] > 0.05

    # Mature stocked tank: every fish survives and ammonia stays safe.
    mature = abm("mature_stocked_tank")
    assert mature["fish_alive"] == 6
    assert mature["fish_mortality"] == 0
    assert ode("mature_stocked_tank")["summary"]["max_NH3_free"] < 0.01

    # Old-tank syndrome: the carbonate buffer is eaten and pH crashes.
    ph = ode("old_tank_syndrome")["ph_diagnostic"]
    assert ph[-1]["ph_dynamic"] < ph[0]["ph_dynamic"] - 1.5


def test_api_scenarios_listing() -> None:
    from openlimno.fishtank.studio_assets import INDEX_HTML
    from openlimno.fishtank.studio_http import list_studio_scenarios

    listing = list_studio_scenarios()
    assert next(s["id"] for s in listing) == "fishless_cycle"
    assert all({"id", "label", "description", "payload"} <= set(s) for s in listing)
    # The preset dropdown + loader are wired into the shipped UI.
    assert 'id="scenarioPreset"' in INDEX_HTML
    assert "/api/scenarios" in INDEX_HTML


def test_build_along_solution_checkpoints_pass() -> None:
    """Guard the teaching answer-key: docs/fishtank/notebooks/build_along_solution.py
    rebuilds the [core] from scratch (no openlimno import) and self-asserts its 4
    CHECKPOINTs. Run it here so the build-along stays teachable as the science
    evolves — a drift in defaults/kinetics that breaks the lesson fails CI."""
    import importlib.util
    import sys

    sol = Path("docs/fishtank/notebooks/build_along_solution.py")
    assert sol.exists(), sol
    spec = importlib.util.spec_from_file_location("build_along_solution", sol)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod   # dataclasses needs the module registered to resolve
    try:
        spec.loader.exec_module(mod)
        mod.run_checkpoints()   # raises AssertionError if any checkpoint regresses
    finally:
        sys.modules.pop(spec.name, None)


def test_lab1_dimension_check_runs() -> None:
    """Guard the Hour-1 'ρ dimension' teaching demo: the worked check that
    contrasts correct ρ=(μ/Y)XMMθ with the buggy ρ=μX must keep producing the
    'tank never cycles' symptom (it self-asserts). Restores the patched
    module global via the script's own try/finally."""
    import importlib.util

    path = Path("docs/fishtank/exercises/lab1_dimension_check.py")
    assert path.exists(), path
    spec = importlib.util.spec_from_file_location("lab1_dimension_check", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()   # raises AssertionError if the correct/buggy contrast regresses


def test_example_scenario_files_validate() -> None:
    from openlimno.fishtank.io import load_scenario, validate_scenario

    files = sorted(Path("examples/fishtank").glob("*.yaml"))
    assert {p.stem for p in files} == {
        "fishless_cycle",
        "seeded_instant_cycle",
        "fish_in_disaster",
        "mature_stocked_tank",
        "old_tank_syndrome",
    }
    for path in files:
        assert validate_scenario(path) == [], path
        load_scenario(path).run()
