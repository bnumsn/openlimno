"""Small fishtank parameter library.

The teaching core keeps kinetics in :class:`Params`; this module gives the
release surface named presets for docs, CLI defaults, and future UI menus.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .events import TapWater
from .state import Params

_SPECIES: dict[str, dict[str, Any]] = {
    "goldfish": {
        "common_name": "Goldfish",
        "temperature_c": (18.0, 24.0),
        "note": "Hardy teaching species; use low feeding rates in small tanks.",
    },
    "zebrafish": {
        "common_name": "Zebrafish",
        "temperature_c": (24.0, 28.0),
        "note": "Warm-water lab species; useful for controlled classroom examples.",
    },
}

_EQUIPMENT: dict[str, dict[str, float | str]] = {
    "sponge_filter_120l": {
        "label": "120 L sponge filter",
        "volume_l": 120.0,
        "k_a": 2.0,
        "X_AOB_max": 5.0,
        "X_NOB_max": 5.0,
    },
    "seeded_media_120l": {
        "label": "120 L seeded mature media",
        "volume_l": 120.0,
        "k_a": 2.5,
        "X_AOB_max": 5.0,
        "X_NOB_max": 5.0,
        "X_AOB_seed": 0.5,
        "X_NOB_seed": 0.5,
    },
}


def _scenario(
    scenario_id: str,
    *,
    ph: float = 7.4,
    days: float = 42.0,
    temperature_c: float = 25.0,
    chemistry: dict[str, float] | None = None,
    ammonia_dose: float = 0.0,
    extra_params: dict[str, float] | None = None,
    carbonate: tuple[float, float] = (2.5, 2.5),
    fish_count: int = 0,
    feed_g_day: float = 0.0,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble one coherent full Studio payload (ODE + ABM + carbonate).

    ``extra_params`` merges into the ODE/ABM ``parameters`` block (e.g.
    ``{"k_a": 0.3}`` for a poorly-aerated tank) so a preset can tune any
    kinetic/physical constant, not just the ammonia dose."""

    chem = {"TAN": 0.0, "NO2": 0.0, "NO3": 5.0, "X_AOB": 0.02, "X_NOB": 0.02, "DO": 7.5}
    chem.update(chemistry or {})
    params: dict[str, float] = {"ammonia_dose_mg_n_l_day": ammonia_dose}
    params.update(extra_params or {})
    alk, dic = carbonate
    return {
        "scenario_id": scenario_id,
        "tank": {"volume_l": 120.0, "temperature_c": temperature_c, "ph": ph},
        "run": {"days": days, "dt_output_hours": 6.0},
        "chemistry": chem,
        "parameters": params,
        "tap_water": {"TAN": 0.0, "NO2": 0.0, "NO3": 5.0, "DO": 8.5},
        "carbonate": {"initial_alk_meq_l": alk, "dic_mmol_l": dic},
        "agents": {
            "seed": 42,
            "dt_days": 0.25,
            "fish_count": fish_count,
            "fish_biomass_g": 4.0,
            "feed_g_day": feed_g_day,
            "aob_agents": 36,
            "nob_agents": 36,
        },
        "events": list(events or []),
    }


# Ordered library of the typical aquarium teaching scenarios. Each entry is a
# single payload that is COHERENT for both the ODE and the ABM panel of the
# Studio (the key constraint: a fishless nitrogen spike is lethal, so fish-in
# scenarios drive nitrogen through `feed` events rather than the abiotic
# ammonia dose, and stocked tanks that are meant to survive start with an
# established biofilm). See docs/fishtank/SPEC.md §8 and COURSE_PLAN.md.
_SCENARIOS: dict[str, dict[str, Any]] = {
    "fishless_cycle": {
        "label": "Fishless cycle (classic)",
        "description": (
            "The textbook cascade: dose 2 mg-N/L/day of bottled ammonia into a "
            "new tank and watch ammonia spike, then nitrite (lagged), then "
            "nitrate accumulate over weeks. No fish at risk."
        ),
        "payload": _scenario(
            "fishless-cycle",
            ammonia_dose=2.0,
            events=[{"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "seeded_instant_cycle": {
        "label": "Seeded / instant cycle",
        "description": (
            "Start from mature, seeded media (high X_AOB/X_NOB). The same "
            "ammonia dose now barely spikes — colonisation, not dosing, sets "
            "the timescale. This is how hobbyists 'instant-cycle'."
        ),
        "payload": _scenario(
            "seeded-instant-cycle",
            chemistry={"X_AOB": 0.8, "X_NOB": 0.8},
            ammonia_dose=2.0,
            events=[{"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "fish_in_disaster": {
        "label": "Fish-in disaster (new-tank syndrome)",
        "description": (
            "Stock 10 fish in an uncycled tank and feed heavily. Fish excretion "
            "outpaces the tiny biofilm, free ammonia turns toxic, and most fish "
            "die — the cautionary tale for why you cycle fishless first. Watch "
            "the ABM nitrate fall below the ODE as dead fish stop excreting."
        ),
        "payload": _scenario(
            "fish-in-disaster",
            ph=7.6,
            fish_count=10,
            feed_g_day=4.0,
            events=[{"day": 0.0, "kind": "feed", "value": 4.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "mature_stocked_tank": {
        "label": "Mature stocked tank (healthy)",
        "description": (
            "An established filter (seeded biofilm) carries six moderately-fed "
            "fish with weekly 25% water changes. Ammonia/nitrite stay near zero, "
            "nitrate is managed, pH holds, and every fish survives."
        ),
        "payload": _scenario(
            "mature-stocked-tank",
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5, "NO3": 10.0},
            fish_count=6,
            feed_g_day=1.2,
            events=[
                {"day": 0.0, "kind": "feed", "value": 1.2, "target": "", "repeat_days": 0.0},
                {"day": 7.0, "kind": "water_change", "value": 0.25, "target": "", "repeat_days": 7.0},
            ],
        ),
    },
    "old_tank_syndrome": {
        "label": "Old-tank syndrome (fishless pH crash)",
        "description": (
            "A fishless carbonate-exhaustion demo: a heavily-dosed, "
            "low-alkalinity tank run for 60 days with no water changes. "
            "Cumulative nitrification eats the carbonate buffer and pH crashes "
            "— the Hour-4 carbonate capstone. (No fish: it isolates the "
            "chemistry; in a real stocked old tank the crash also stresses fish.)"
        ),
        "payload": _scenario(
            "old-tank-syndrome",
            days=60.0,
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5},
            ammonia_dose=3.0,
            carbonate=(1.0, 1.2),
            events=[{"day": 0.0, "kind": "ammonia_dose", "value": 3.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "low_oxygen": {
        "label": "Low oxygen (under-aerated tank)",
        "description": (
            "Same fishless dose, but a weak filter / no airstone: reaeration "
            "k_a is cut from 2.0 to 0.3 /day. DO crashes toward zero and — "
            "because nitrification is O2-limited via the M(DO) terms — the "
            "cycle stalls: NO3 reaches only ~6.6 mg-N/L over 42 days instead "
            "of ~88. The lesson: oxygen, not just ammonia, gates nitrification."
        ),
        "payload": _scenario(
            "low-oxygen",
            ammonia_dose=2.0,
            extra_params={"k_a": 0.3},
            events=[{"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "staged_stocking": {
        "label": "Staged stocking (add fish gradually)",
        "description": (
            "The right way to add fish to a lightly-seeded tank: feeding ramps "
            "up in steps (0.5 → 1.5 → 3.0 g/day at days 0/14/28) so the biofilm "
            "keeps pace. Free NH3 stays ~0.006 mg/L (well under the 0.05 stress "
            "line) — the safe counterpoint to the fish-in disaster."
        ),
        "payload": _scenario(
            "staged-stocking",
            chemistry={"X_AOB": 0.5, "X_NOB": 0.5},
            fish_count=6,
            feed_g_day=0.5,
            events=[
                {"day": 0.0, "kind": "feed", "value": 0.5, "target": "", "repeat_days": 0.0},
                {"day": 14.0, "kind": "feed", "value": 1.5, "target": "", "repeat_days": 0.0},
                {"day": 28.0, "kind": "feed", "value": 3.0, "target": "", "repeat_days": 0.0},
            ],
        ),
    },
    "nitrate_control": {
        "label": "Nitrate control (weekly water change)",
        "description": (
            "An established tank dosed at 2 mg-N/L/day with a weekly 30% water "
            "change. The change can't touch the attached biofilm, but it does "
            "export accumulated nitrate: NO3 ends ~45 mg-N/L instead of ~88 "
            "with no changes. Why routine water changes are the nitrate brake."
        ),
        "payload": _scenario(
            "nitrate-control",
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5},
            ammonia_dose=2.0,
            events=[
                {"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0},
                {"day": 7.0, "kind": "water_change", "value": 0.30, "target": "", "repeat_days": 7.0},
            ],
        ),
    },
    "filter_crash": {
        "label": "Filter crash (washed media / medication)",
        "description": (
            "A mature stocked tank whose biofilm is wiped 85% on day 20 — the "
            "classic mistake of rinsing filter media under chlorinated tap "
            "water, or an antibiotic that kills nitrifiers. Ammonia and nitrite "
            "rebound until the colony re-establishes. Demonstrates the new "
            "wipe_biofilm event: the mirror of a water change."
        ),
        "payload": _scenario(
            "filter-crash",
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5, "NO3": 10.0},
            fish_count=6,
            feed_g_day=1.2,
            events=[
                {"day": 0.0, "kind": "feed", "value": 1.2, "target": "", "repeat_days": 0.0},
                {"day": 20.0, "kind": "wipe_biofilm", "value": 0.85, "target": "", "repeat_days": 0.0},
            ],
        ),
    },
    "power_outage": {
        "label": "Power outage (aeration lost then restored)",
        "description": (
            "A two-day blackout: reaeration k_a is cut to 0.2 /day on day 10 "
            "and restored to 2.0 on day 12 via set_param events. DO plunges "
            "toward zero during the outage, then recovers — the transient that "
            "kills fish overnight when the air pump stops. Shows time-varying "
            "drivers (set_param), not just instantaneous state bumps."
        ),
        "payload": _scenario(
            "power-outage",
            chemistry={"X_AOB": 1.5, "X_NOB": 1.5},
            ammonia_dose=2.0,
            days=25.0,
            events=[
                {"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0},
                {"day": 10.0, "kind": "set_param", "value": 0.2, "target": "k_a", "repeat_days": 0.0},
                {"day": 12.0, "kind": "set_param", "value": 2.0, "target": "k_a", "repeat_days": 0.0},
            ],
        ),
    },
    "heat_wave": {
        "label": "Heat wave (temperature step raises toxicity)",
        "description": (
            "A fishless cycle where temperature steps from 25 to 32 °C on day "
            "5 — just as ammonia is climbing toward its peak. Warmer water "
            "shifts the ammonia pKa, so the toxic free-NH3 fraction of the same "
            "TAN is larger: the peak free NH3 rises from ~0.14 to ~0.20 mg/L. "
            "Why a heat wave turns a survivable tank lethal without any change "
            "in total ammonia. (The step must precede the TAN peak to bite — "
            "warming a tank whose ammonia has already cleared does little.)"
        ),
        "payload": _scenario(
            "heat-wave",
            ammonia_dose=2.0,
            events=[
                {"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0},
                {"day": 5.0, "kind": "set_param", "value": 32.0, "target": "temperature_c", "repeat_days": 0.0},
            ],
        ),
    },
    "overfeeding": {
        "label": "Overfeeding (too much food, weak biofilm)",
        "description": (
            "Six fish in a barely-cycled tank (X≈0.3) fed a heavy 8 g/day. "
            "Excretion outpaces the thin biofilm: free NH3 peaks ~0.026 mg/L "
            "and DO is drawn down hard. The fish hang on but stay stressed — "
            "the everyday version of 'I just fed them more and the water went "
            "bad', distinct from the uncycled fish-in disaster."
        ),
        "payload": _scenario(
            "overfeeding",
            chemistry={"X_AOB": 0.3, "X_NOB": 0.3},
            days=30.0,
            fish_count=6,
            feed_g_day=8.0,
            events=[{"day": 0.0, "kind": "feed", "value": 8.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "planted_tank": {
        "label": "Planted tank (plants as a nitrogen sink, Tier-2)",
        "description": (
            "A dosed tank with live plants (Tier-2 plant uptake on): the plant "
            "nitrogen pool grows from 3 toward its ~15 mg-N/L cap, drawing the "
            "final nitrate down to ~82 vs ~93 with no plants (same tank). Plants "
            "prefer ammonium, so they also shave the free-NH3 peak. The lesson: "
            "plants are a real N sink, but a partial one — they reduce, not "
            "erase, nitrate. Only the ODE models plants; the ABM panel has none."
        ),
        "payload": _scenario(
            "planted-tank",
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5, "NO3": 10.0, "B_plant": 3.0},
            ammonia_dose=2.0,
            extra_params={"mu_plant": 1.0, "B_plant_max": 15.0},
            events=[{"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "denitrification_substrate": {
        "label": "Denitrification (anoxic substrate removes nitrate, Tier-2)",
        "description": (
            "A deep-substrate / low-flow tank where anoxic microsites host "
            "denitrifiers (Tier-2 k_denit on). With reaeration low, NO3 is "
            "converted to N2 gas and leaves the system: final nitrate falls to "
            "~5 vs ~38 mg-N/L. This is the one process that genuinely removes "
            "nitrogen from a closed tank — the chemistry behind a working "
            "deep-sand-bed or planted-substrate refugium."
        ),
        "payload": _scenario(
            "denitrification-substrate",
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5},
            ammonia_dose=2.0,
            extra_params={"k_denit": 0.15, "k_a": 0.6},
            events=[{"day": 0.0, "kind": "ammonia_dose", "value": 2.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "ph_crash_coupled": {
        "label": "pH crash — fully coupled (Tier-2 research)",
        "description": (
            "The old-tank crash with pH FULLY COUPLED (couple_ph on): "
            "nitrification eats alkalinity, the solved pH falls from ~7.4 to "
            "~6.0, and the low pH then throttles the nitrifiers — so nitrate "
            "self-limits at ~13 mg-N/L instead of running to ~184 in the "
            "diagnostic-only old_tank_syndrome. This is the feedback the "
            "diagnostic version omits, and the SPEC's research-grade step."
        ),
        "payload": _scenario(
            "ph-crash-coupled",
            days=60.0,
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5, "DIC": 2.0, "Alk": 1.85},
            ammonia_dose=3.0,
            extra_params={"couple_ph": 1.0},
            carbonate=(1.85, 2.0),
            events=[{"day": 0.0, "kind": "ammonia_dose", "value": 3.0, "target": "", "repeat_days": 0.0}],
        ),
    },
    "buffer_dosing": {
        "label": "Buffer dosing (rescue the pH crash, Tier-2)",
        "description": (
            "The same coupled crash, but the keeper doses alkalinity (+0.5 "
            "meq/L weekly via a dose→Alk event). Holding the buffer up keeps "
            "nitrification running: nitrate sustains ~30 mg-N/L vs ~13 with no "
            "dosing — the management fix for old-tank pH collapse, and a demo "
            "of dosing a Tier-2 carbonate state directly."
        ),
        "payload": _scenario(
            "buffer-dosing",
            days=60.0,
            chemistry={"X_AOB": 2.5, "X_NOB": 2.5, "DIC": 2.0, "Alk": 1.85},
            ammonia_dose=3.0,
            extra_params={"couple_ph": 1.0},
            carbonate=(1.85, 2.0),
            events=[
                {"day": 0.0, "kind": "ammonia_dose", "value": 3.0, "target": "", "repeat_days": 0.0},
                {"day": 7.0, "kind": "dose", "value": 0.5, "target": "Alk", "repeat_days": 7.0},
            ],
        ),
    },
}


def scenarios() -> dict[str, dict[str, Any]]:
    """Return the named library of typical teaching scenarios.

    Each value has ``label``, ``description`` and a full ``payload`` (the same
    superset format the Studio uses; ``io.load_scenario`` consumes the ODE
    subset and ignores ``agents``/``carbonate``)."""

    return deepcopy(_SCENARIOS)


def scenario_payload(name: str = "fishless_cycle") -> dict[str, Any]:
    """Return a fresh copy of one named scenario's full payload."""

    try:
        return deepcopy(_SCENARIOS[name]["payload"])
    except KeyError as exc:
        raise ValueError(f"unknown scenario {name!r}; choose {sorted(_SCENARIOS)}") from exc


def default_params() -> Params:
    """Return a fresh copy of the default aquarium kinetics."""

    return Params()


def tap_water(name: str = "moderate_nitrate") -> TapWater:
    """Return named replacement-water chemistry."""

    waters = {
        "moderate_nitrate": TapWater(TAN=0.0, NO2=0.0, NO3=5.0, DO=8.5),
        "ro_di": TapWater(TAN=0.0, NO2=0.0, NO3=0.0, DO=8.0),
    }
    try:
        return waters[name]
    except KeyError as exc:
        raise ValueError(f"unknown tap-water preset {name!r}; choose {sorted(waters)}") from exc


def species() -> dict[str, dict[str, Any]]:
    """Return fish-species metadata used by teaching examples."""

    return deepcopy(_SPECIES)


def equipment() -> dict[str, dict[str, float | str]]:
    """Return named equipment presets."""

    return deepcopy(_EQUIPMENT)


__all__ = [
    "default_params",
    "equipment",
    "scenario_payload",
    "scenarios",
    "species",
    "tap_water",
]
