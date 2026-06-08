"""Regression tests for the fishtank-module codex review fixes.

Each test pins one finding so the behaviour can't silently regress. The
teaching Tier-1 numbers are guarded by test_fishtank_tier1.py; these cover the
Tier-2 / robustness / event-timing corrections.
"""

from __future__ import annotations

import warnings

import pytest

from openlimno.fishtank import (
    Chemistry,
    Params,
    diagnostic_ph_trajectory,
    fish_timeseries,
    simulate,
    simulate_agent_based_model,
)
from openlimno.fishtank.events import Event, EventSchedule, TapWater


# --- single-fish observability: fish_timeseries -----------------------------
def test_fish_timeseries_tracks_one_individual():
    out = simulate_agent_based_model(
        {
            "run": {"days": 20, "dt_output_hours": 24},
            "chemistry": {"TAN": 2},
            "parameters": {"ammonia_dose_mg_n_l_day": 3.0},
            "agents": {"fish_count": 4, "seed": 3},
        }
    )
    df = fish_timeseries(out, "fish-1")
    # one row per snapshot, per-individual columns present
    assert len(df) == len(out["snapshots"])
    for col in ("day", "biomass_g", "stress", "activity", "alive", "x", "y", "z"):
        assert col in df.columns
    # stress rises then the fish dies (alive flips to False and stays)
    assert df["stress"].iloc[-1] > df["stress"].iloc[0]
    assert not df["alive"].iloc[-1]
    # two different fish have distinct trajectories (not clones)
    other = fish_timeseries(out, "fish-2")
    assert not df["biomass_g"].equals(other["biomass_g"])


def test_fish_timeseries_unknown_id_lists_available():
    out = simulate_agent_based_model({"run": {"days": 2, "dt_output_hours": 24}})
    with pytest.raises(KeyError, match="available ids"):
        fish_timeseries(out, "fish-999")


# --- round-2: events bypass validate (set_param / negative dose) -------------
@pytest.mark.parametrize(
    "event",
    [
        Event(0, "set_param", -1.0, "k_a"),
        Event(0, "set_param", 20.0, "ph"),
        Event(0, "set_param", 0.0, "DO_sat"),
        Event(0, "dose", -5.0, "TAN"),
    ],
)
def test_event_cannot_write_invalid_state_or_params(event):
    with pytest.raises(ValueError, match="invalid"):
        simulate(Chemistry(TAN=2), days=5, schedule=EventSchedule(events=[event]))


@pytest.mark.parametrize(
    "event",
    [
        Event(5, "set_param", 0.0, "k_a"),  # power outage: reaeration off
        Event(5, "set_param", 33.0, "temperature_c"),  # heat wave
        Event(5, "dose", 4.0, "DO"),  # aerate
    ],
)
def test_valid_events_still_accepted(event):
    # The post-event guard must not reject legitimate set_param / dose values.
    r = simulate(days=10, schedule=EventSchedule(events=[event]))
    assert len(r.timeseries) > 0


# --- round-2: tap DIC/Alk closes through Studio backend + provenance ---------
def test_studio_water_change_mixes_tap_buffer():
    from openlimno.fishtank.studio_http import run_studio_payload

    payload = {
        "scenario_id": "t",
        "tank": {"volume_l": 120, "temperature_c": 25, "ph": 7.4},
        "run": {"days": 30, "dt_output_hours": 24},
        "chemistry": {
            "TAN": 2,
            "NO3": 5,
            "X_AOB": 0.5,
            "X_NOB": 0.5,
            "DO": 7.5,
            "DIC": 2.0,
            "Alk": 2.0,
        },
        "parameters": {"ammonia_dose_mg_n_l_day": 4.0, "couple_ph": 1.0},
        "tap_water": {"NO3": 5, "DO": 8.5, "DIC": 2.0, "Alk": 10.0},
        "events": [{"day": 20, "kind": "water_change", "value": 0.8}],
    }
    out = run_studio_payload(payload)
    ts = out["timeseries"]
    before = [r["Alk"] for r in ts if r["day"] < 20][-1]
    after = [r["Alk"] for r in ts if r["day"] >= 20][0]
    assert before < 2.0 and after > before  # buffered tap rescued alkalinity
    # provenance fingerprint must record tap DIC/Alk (else buffer change is invisible)
    tap_prov = out["provenance"]["inputs"]["tap_water"]
    assert tap_prov["DIC"] == 2.0 and tap_prov["Alk"] == 10.0


# --- round-2: expand() caps a runaway repeat cadence -------------------------
def test_expand_rejects_runaway_repeat():
    sched = EventSchedule(events=[Event(0, "water_change", 0.1, repeat_days=0.0001)])
    with pytest.raises(ValueError, match="expands to"):
        sched.expand(42.0)


# --- round-2: pH-inhibition thresholds need [0,14] and min < opt -------------
def test_ph_nitrif_thresholds_validated():
    with pytest.raises(ValueError, match="pH_min_nitrif"):
        Params(pH_min_nitrif=8.0, pH_opt_nitrif=7.0).validate()
    with pytest.raises(ValueError, match=r"pH_opt_nitrif.*\[0, 14\]"):
        Params(pH_opt_nitrif=20.0).validate()


# --- #6 input physical-domain validation ----------------------------------
@pytest.mark.parametrize(
    "kw",
    [
        {"Y_AOB": 0.0},
        {"X_AOB_max": 0.0},
        {"volume_l": 0.0},
        {"K_TAN": 0.0},
        {"mu_AOB": -1.0},
        {"ph": 15.0},
        {"temperature_c": -300.0},
    ],
)
def test_params_validate_rejects_pathological(kw):
    with pytest.raises(ValueError, match="invalid parameters"):
        simulate(params=Params(**kw), days=1)


def test_chemistry_validate_rejects_negative():
    with pytest.raises(ValueError, match="invalid initial chemistry"):
        simulate(chemistry=Chemistry(TAN=-1.0), days=1)


def test_defaults_validate_cleanly():
    # The shipped defaults must pass — a no-op guard, not a footgun.
    Params().validate()
    Chemistry().validate()


# --- #1 water change mixes DIC/Alk (rescues a coupled pH crash) ------------
def test_water_change_restores_alkalinity_when_coupled():
    p = Params(couple_ph=1.0, ammonia_dose_mg_n_l_day=4.0)
    sched = EventSchedule(
        events=[Event(day=20, kind="water_change", value=0.8)],
        tap_water=TapWater(),  # default tap Alk=2.0
    )
    rc = simulate(Chemistry(DIC=2.0, Alk=2.0), p, days=30, schedule=sched).timeseries
    before = rc[rc.day < 20].Alk.iloc[-1]
    after = rc[rc.day >= 20].Alk.iloc[0]
    assert before < 2.0  # nitrification ate the buffer
    assert after > before  # the water change swapped in fresh buffer


def test_water_change_dic_alk_noop_at_tier1_defaults():
    # Default tap DIC/Alk match the tank, so a water change must not perturb them.
    sched = EventSchedule(
        events=[Event(day=10, kind="water_change", value=0.5)], tap_water=TapWater()
    )
    r = simulate(Chemistry(DIC=2.0, Alk=2.0), Params(), days=20, schedule=sched).timeseries
    assert r.DIC.iloc[-1] == pytest.approx(2.0)
    assert r.Alk.iloc[-1] == pytest.approx(2.0)


# --- #5 DO stays non-negative ---------------------------------------------
def test_do_never_goes_negative_under_heavy_respiration():
    # Strong constant fish respiration would otherwise drive DO < 0.
    r = simulate(Chemistry(DO=1.0), Params(R_fish=50.0, k_a=0.1), days=10).timeseries
    assert r.DO.min() >= 0.0


# --- #2 diagnostic pH applicability warning --------------------------------
def test_diagnostic_ph_warns_when_no3_proxy_unreliable():
    r = simulate(Chemistry(TAN=3), Params(mu_plant=0.5), days=20)
    with pytest.warns(UserWarning, match="unreliable"):
        diagnostic_ph_trajectory(r)


def test_diagnostic_ph_silent_for_pure_tier1():
    r = simulate(Chemistry(TAN=3), Params(), days=20)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        diagnostic_ph_trajectory(r)


# --- #4 ABM applies events at their scheduled time -------------------------
def test_abm_off_grid_event_applied_on_time():
    # An off-grid water change (day 0.1, output grid every 1 day) should land
    # near day 0.1, not be deferred — NO3 drops between the day-0 and day-1 rows.
    scenario = {
        "run": {"days": 3.0, "dt_output_hours": 24.0},
        "chemistry": {"NO3": 40.0},
        "events": [{"day": 0.1, "kind": "water_change", "value": 0.9}],
    }
    out = simulate_agent_based_model(scenario)
    no3 = [row["NO3"] for row in out["timeseries"]]
    # Big 90% dilution toward tap NO3=5: the day-1 row must already reflect it.
    assert no3[1] < 0.5 * no3[0]


# --- 🟢#2 repeat_days preserved on expansion -------------------------------
def test_expanded_repeating_events_keep_cadence():
    sched = EventSchedule(events=[Event(day=7, kind="water_change", value=0.25, repeat_days=7)])
    expanded = sched.expand(30)
    assert len(expanded) >= 3
    assert all(e.repeat_days == 7 for e in expanded)


# --- 🟢#3 non-target event kinds carry no target ---------------------------
def test_non_target_event_clears_stray_target():
    e = Event(day=1, kind="water_change", value=0.5, target="DO")
    assert e.target == ""
    # dose still keeps its (validated) target
    assert Event(day=1, kind="dose", value=1.0, target="DO").target == "DO"
