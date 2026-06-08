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
    simulate,
    simulate_agent_based_model,
)
from openlimno.fishtank.events import Event, EventSchedule, TapWater


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
