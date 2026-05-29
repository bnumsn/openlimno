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
    chemistry: dict[str, float] | None = None,
    ammonia_dose: float = 0.0,
    carbonate: tuple[float, float] = (2.5, 2.5),
    fish_count: int = 0,
    feed_g_day: float = 0.0,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble one coherent full Studio payload (ODE + ABM + carbonate)."""

    chem = {"TAN": 0.0, "NO2": 0.0, "NO3": 5.0, "X_AOB": 0.02, "X_NOB": 0.02, "DO": 7.5}
    chem.update(chemistry or {})
    alk, dic = carbonate
    return {
        "scenario_id": scenario_id,
        "tank": {"volume_l": 120.0, "temperature_c": 25.0, "ph": ph},
        "run": {"days": days, "dt_output_hours": 6.0},
        "chemistry": chem,
        "parameters": {"ammonia_dose_mg_n_l_day": ammonia_dose},
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
        "label": "Old-tank syndrome (pH crash)",
        "description": (
            "A heavily-loaded, low-alkalinity tank run for 60 days with no water "
            "changes. Cumulative nitrification eats the carbonate buffer and pH "
            "crashes — the Hour-4 carbonate capstone."
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
