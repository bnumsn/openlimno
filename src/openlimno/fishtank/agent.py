"""Agent-based fishtank model.

This module complements the ODE solver with an explicit individual/patch
simulation for teaching. Fish are individual agents; nitrifiers are attached
biofilm patches split into AOB and NOB guilds. The model is deterministic for a
given seed, JSON-safe, and intentionally small enough to run inside the local
browser Studio.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any

from .events import Event, EventSchedule, TapWater, apply_event, event_from_mapping
from .processes import monod
from .state import Chemistry, Params, nh3_free_fraction


@dataclass
class FishAgent:
    """One fish individual in the ABM tank."""

    id: str
    biomass_g: float
    x: float
    y: float
    z: float
    activity: float = 1.0
    stress: float = 0.0
    alive: bool = True


@dataclass
class MicrobePatch:
    """One attached biofilm patch on filter media or hardscape."""

    id: str
    guild: str
    biomass_mg_l: float
    x: float
    y: float
    z: float
    local_factor: float
    activity: float = 0.0


def simulate_agent_based_model(scenario: dict[str, Any]) -> dict[str, Any]:
    """Run the fishtank agent-based model and return JSON-safe results.

    The ABM uses the same state variables and event semantics as the ODE model
    but advances them by aggregating fish and biofilm-agent activity at each
    discrete step.
    """

    tank = _mapping(scenario.get("tank", {}), "tank")
    run = _mapping(scenario.get("run", {}), "run")
    chemistry_doc = _mapping(scenario.get("chemistry", {}), "chemistry")
    params_doc = _mapping(scenario.get("parameters", {}), "parameters")
    tap_doc = _mapping(scenario.get("tap_water", {}), "tap_water")
    agent_doc = _mapping(scenario.get("agents", {}), "agents")

    days = _float(run.get("days", 42.0), "run.days")
    dt_output_hours = _float(run.get("dt_output_hours", 6.0), "run.dt_output_hours")
    if days < 0.0:
        raise ValueError(f"run.days must be non-negative, got {days!r}")
    if dt_output_hours <= 0.0:
        raise ValueError(f"run.dt_output_hours must be greater than zero, got {dt_output_hours!r}")
    output_dt_days = dt_output_hours / 24.0
    dt_days = _bounded(
        _float(agent_doc.get("dt_days", min(0.25, output_dt_days)), "agents.dt_days"),
        "agents.dt_days",
        0.02,
        1.0,
    )
    seed = _int(agent_doc.get("seed", 42), "agents.seed")
    rng = random.Random(seed)

    chem = Chemistry(
        TAN=_float(chemistry_doc.get("TAN", 0.0), "chemistry.TAN"),
        NO2=_float(chemistry_doc.get("NO2", 0.0), "chemistry.NO2"),
        NO3=_float(chemistry_doc.get("NO3", 5.0), "chemistry.NO3"),
        X_AOB=_float(chemistry_doc.get("X_AOB", 0.02), "chemistry.X_AOB"),
        X_NOB=_float(chemistry_doc.get("X_NOB", 0.02), "chemistry.X_NOB"),
        DO=_float(chemistry_doc.get("DO", 7.5), "chemistry.DO"),
    )
    # Ingest the FULL parameter set (mirrors io.scenario_from_mapping) so the
    # ABM honours k_a, DO_sat and every kinetic constant from the scenario —
    # not just volume/temp/pH/dose. Otherwise the ABM is "islanded" from
    # calibration and equipment overrides while the ODE responds to them.
    param_overrides: dict[str, float] = {}
    for key in ("volume_l", "temperature_c", "ph", "DO_sat", "k_a"):
        if key in tank:
            param_overrides[key] = _float(tank[key], f"tank.{key}")
    for key, value in params_doc.items():
        param_overrides[str(key)] = _float(value, f"parameters.{key}")
    params = Params().with_overrides(**param_overrides)
    tap = TapWater(
        TAN=_float(tap_doc.get("TAN", 0.0), "tap_water.TAN"),
        NO2=_float(tap_doc.get("NO2", 0.0), "tap_water.NO2"),
        NO3=_float(tap_doc.get("NO3", 5.0), "tap_water.NO3"),
        DO=_float(tap_doc.get("DO", 8.5), "tap_water.DO"),
    )
    schedule = _schedule_from_payload(scenario.get("events", []), tap, days)

    fish_count = _bounded_int(agent_doc.get("fish_count", 6), "agents.fish_count", 0, 80)
    fish_biomass_g = _bounded(
        _float(agent_doc.get("fish_biomass_g", 4.0), "agents.fish_biomass_g"),
        "agents.fish_biomass_g",
        0.1,
        2000.0,
    )
    feed_g_day = _bounded(
        _float(agent_doc.get("feed_g_day", 0.3), "agents.feed_g_day"),
        "agents.feed_g_day",
        0.0,
        2000.0,
    )
    aob_count = _bounded_int(agent_doc.get("aob_agents", 36), "agents.aob_agents", 1, 500)
    nob_count = _bounded_int(agent_doc.get("nob_agents", 36), "agents.nob_agents", 1, 500)

    fish = _seed_fish(rng, fish_count, fish_biomass_g)
    patches = [
        *_seed_patches(rng, "AOB", aob_count, chem.X_AOB),
        *_seed_patches(rng, "NOB", nob_count, chem.X_NOB),
    ]
    event_rows: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    expanded_events = sorted(schedule.expand(days), key=lambda event: (event.day, event.priority))
    event_cursor = 0

    # Day-0 events define the initial post-action state.
    while event_cursor < len(expanded_events) and expanded_events[event_cursor].day <= 0.0:
        chem, params, feed_g_day = _apply_agent_event(
            chem, params, feed_g_day, expanded_events[event_cursor], tap, event_rows, patches
        )
        event_cursor += 1

    step_index = 0
    time = 0.0
    _record(rows, snapshots, time, chem, params, fish, patches, snapshot=True)
    while time < days - 1e-10:
        step = min(dt_days, days - time)
        chem = _advance_agents(chem, params, fish, patches, step, feed_g_day, rng)
        time = round(time + step, 10)
        while event_cursor < len(expanded_events) and expanded_events[event_cursor].day <= time + 1e-10:
            chem, params, feed_g_day = _apply_agent_event(
                chem, params, feed_g_day, expanded_events[event_cursor], tap, event_rows, patches
            )
            event_cursor += 1
        step_index += 1
        _record(
            rows,
            snapshots,
            time,
            chem,
            params,
            fish,
            patches,
            snapshot=(step_index % max(1, round(1.0 / dt_days)) == 0 or time >= days),
        )

    summary = _summary(rows, fish, patches)
    return {
        "ok": True,
        "schema": "openlimno-fishtank-abm/0.1",
        "model": "agent-based",
        "config": {
            "seed": seed,
            "dt_days": dt_days,
            "fish_count": fish_count,
            "fish_biomass_g": fish_biomass_g,
            "feed_g_day": feed_g_day,
            "aob_agents": aob_count,
            "nob_agents": nob_count,
        },
        "summary": summary,
        "timeseries": rows,
        "snapshots": snapshots,
        "agents": _agent_snapshot(fish, patches),
        "event_log": event_rows,
        "provenance": {
            "seed": seed,
            "agent_count": fish_count + aob_count + nob_count,
            "fish_agents": fish_count,
            "microbe_patches": aob_count + nob_count,
            "state_variables": ["TAN", "NO2", "NO3", "DO", "NH3_free"],
        },
    }


def _advance_agents(
    chem: Chemistry,
    params: Params,
    fish: list[FishAgent],
    patches: list[MicrobePatch],
    dt_days: float,
    feed_g_day: float,
    rng: random.Random,
) -> Chemistry:
    c = Chemistry(**vars(chem))
    alive = [agent for agent in fish if agent.alive]
    initial_fish_biomass = sum(max(agent.biomass_g, 0.0) for agent in fish)
    alive_biomass = sum(max(agent.biomass_g, 0.0) for agent in alive)
    live_fraction = alive_biomass / initial_fish_biomass if initial_fish_biomass > 0.0 else 0.0

    # TAN sources mirror the ODE model: the abiotic ammonia dose (fishless
    # cycle) always applies, and live fish add excretion from feeding. These
    # are SUMMED — not either/or — so a scenario that doses ammonia *and*
    # stocks fish stays comparable to the ODE solver. The old code dropped
    # the dose entirely whenever any fish were present, which silently
    # starved the ABM of its main N source and made the Studio's ODE-vs-ABM
    # panels diverge by ~10x at the default payload.
    dose_source = max(0.0, params.ammonia_dose_mg_n_l_day)
    feed_source = (
        params.a_exc * feed_g_day / params.volume_l * 1000.0 * live_fraction
        if fish
        else 0.0
    )
    c.TAN += (dose_source + max(0.0, feed_source)) * dt_days

    stress_signal = _stress_signal(c, params)
    feed_per_fish = feed_g_day / max(1, len(alive))
    for agent in alive:
        agent.stress = _clamp(0.86 * agent.stress + 0.14 * stress_signal, 0.0, 6.0)
        agent.activity = _clamp(1.05 - 0.16 * agent.stress + rng.uniform(-0.035, 0.035), 0.18, 1.2)
        growth = (feed_per_fish * 0.25 - 0.012 * agent.biomass_g - agent.stress * 0.015) * dt_days
        agent.biomass_g = max(0.05, agent.biomass_g + growth)
        if agent.stress > 2.4 and rng.random() < min(0.45, (agent.stress - 2.4) * 0.04 * dt_days):
            agent.alive = False
            agent.activity = 0.0
        _move_fish(agent, rng, dt_days)

    aob_fluxes = _patch_fluxes(patches, "AOB", c.TAN, c.DO, params, is_aob=True)
    raw_rho1 = sum(flux for _patch, flux in aob_fluxes)
    tan_oxidized = min(max(c.TAN, 0.0), raw_rho1 * dt_days)
    actual_rho1 = tan_oxidized / dt_days if dt_days > 0.0 else 0.0

    no2_available = max(c.NO2, 0.0) + tan_oxidized
    nob_fluxes = _patch_fluxes(patches, "NOB", no2_available, c.DO, params, is_aob=False)
    raw_rho2 = sum(flux for _patch, flux in nob_fluxes)
    no2_oxidized = min(no2_available, raw_rho2 * dt_days)
    actual_rho2 = no2_oxidized / dt_days if dt_days > 0.0 else 0.0

    _grow_patches(aob_fluxes, actual_rho1, raw_rho1, params.Y_AOB, params.b_AOB, params.X_AOB_max, dt_days)
    _grow_patches(nob_fluxes, actual_rho2, raw_rho2, params.Y_NOB, params.b_NOB, params.X_NOB_max, dt_days)

    fish_o2 = alive_biomass * 0.014 / params.volume_l * 1000.0
    c.TAN = max(0.0, c.TAN - tan_oxidized)
    c.NO2 = max(0.0, c.NO2 + tan_oxidized - no2_oxidized)
    c.NO3 = max(0.0, c.NO3 + no2_oxidized)
    oxygen_demand = 3.43 * tan_oxidized + 1.14 * no2_oxidized + fish_o2 * dt_days
    c.DO = _clamp(c.DO - oxygen_demand + params.k_a * (params.DO_sat - c.DO) * dt_days, 0.0, 14.0)
    c.X_AOB = sum(patch.biomass_mg_l for patch in patches if patch.guild == "AOB")
    c.X_NOB = sum(patch.biomass_mg_l for patch in patches if patch.guild == "NOB")
    return c


def _patch_fluxes(
    patches: list[MicrobePatch],
    guild: str,
    substrate: float,
    do_value: float,
    params: Params,
    *,
    is_aob: bool,
) -> list[tuple[MicrobePatch, float]]:
    temp = params.theta ** (params.temperature_c - 20.0)
    if is_aob:
        mu = params.mu_AOB
        yield_coeff = params.Y_AOB
        k_sub = params.K_TAN
        k_o = params.K_O_AOB
    else:
        mu = params.mu_NOB
        yield_coeff = params.Y_NOB
        k_sub = params.K_NO2
        k_o = params.K_O_NOB
    out: list[tuple[MicrobePatch, float]] = []
    for patch in patches:
        if patch.guild != guild:
            continue
        activity = temp * monod(substrate, k_sub) * monod(do_value, k_o) * patch.local_factor
        patch.activity = _clamp(activity, 0.0, 3.0)
        out.append((patch, (mu / yield_coeff) * patch.biomass_mg_l * patch.activity))
    return out


def _grow_patches(
    fluxes: list[tuple[MicrobePatch, float]],
    actual_rho: float,
    raw_rho: float,
    yield_coeff: float,
    decay: float,
    capacity: float,
    dt_days: float,
) -> None:
    if not fluxes:
        return
    total_before = sum(patch.biomass_mg_l for patch, _flux in fluxes)
    cap_factor = _clamp(1.0 - total_before / max(capacity, 1e-9), 0.0, 1.0)
    for patch, raw_flux in fluxes:
        share = raw_flux / raw_rho if raw_rho > 0.0 else 1.0 / len(fluxes)
        growth = yield_coeff * actual_rho * share * cap_factor
        patch.biomass_mg_l = max(0.0001, patch.biomass_mg_l + (growth - decay * patch.biomass_mg_l) * dt_days)


def _record(
    rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    day: float,
    chem: Chemistry,
    params: Params,
    fish: list[FishAgent],
    patches: list[MicrobePatch],
    *,
    snapshot: bool,
) -> None:
    live_fish = [agent for agent in fish if agent.alive]
    mean_stress = sum(agent.stress for agent in live_fish) / len(live_fish) if live_fish else 0.0
    row = {
        "day": round(day, 4),
        "TAN": round(chem.TAN, 6),
        "NO2": round(chem.NO2, 6),
        "NO3": round(chem.NO3, 6),
        "DO": round(chem.DO, 6),
        "NH3_free": round(max(0.0, chem.TAN) * nh3_free_fraction(params.ph, params.temperature_c), 6),
        "pH": round(params.ph, 4),
        "fish_alive": len(live_fish),
        "fish_biomass_g": round(sum(agent.biomass_g for agent in live_fish), 6),
        "fish_stress_mean": round(mean_stress, 6),
        "AOB_biomass": round(sum(patch.biomass_mg_l for patch in patches if patch.guild == "AOB"), 6),
        "NOB_biomass": round(sum(patch.biomass_mg_l for patch in patches if patch.guild == "NOB"), 6),
    }
    rows.append(row)
    if snapshot:
        snapshots.append({"day": row["day"], **_agent_snapshot(fish, patches)})


def _summary(
    rows: list[dict[str, Any]],
    fish: list[FishAgent],
    patches: list[MicrobePatch],
) -> dict[str, Any]:
    final = rows[-1]
    return {
        "final_TAN": final["TAN"],
        "final_NO2": final["NO2"],
        "final_NO3": final["NO3"],
        "min_DO": round(min(row["DO"] for row in rows), 6),
        "max_NH3_free": round(max(row["NH3_free"] for row in rows), 6),
        "fish_alive": sum(1 for agent in fish if agent.alive),
        "fish_mortality": sum(1 for agent in fish if not agent.alive),
        "mean_fish_stress": final["fish_stress_mean"],
        "AOB_biomass": round(sum(patch.biomass_mg_l for patch in patches if patch.guild == "AOB"), 6),
        "NOB_biomass": round(sum(patch.biomass_mg_l for patch in patches if patch.guild == "NOB"), 6),
    }


def _agent_snapshot(fish: list[FishAgent], patches: list[MicrobePatch]) -> dict[str, Any]:
    return {
        "fish": [
            {
                "id": agent.id,
                "x": round(agent.x, 4),
                "y": round(agent.y, 4),
                "z": round(agent.z, 4),
                "biomass_g": round(agent.biomass_g, 4),
                "activity": round(agent.activity, 4),
                "stress": round(agent.stress, 4),
                "alive": agent.alive,
            }
            for agent in fish
        ],
        "microbes": [
            {
                "id": patch.id,
                "guild": patch.guild,
                "x": round(patch.x, 4),
                "y": round(patch.y, 4),
                "z": round(patch.z, 4),
                "biomass_mg_l": round(patch.biomass_mg_l, 6),
                "activity": round(patch.activity, 4),
            }
            for patch in patches
        ],
    }


def _seed_fish(rng: random.Random, count: int, biomass_g: float) -> list[FishAgent]:
    return [
        FishAgent(
            id=f"fish-{i + 1}",
            biomass_g=biomass_g * rng.uniform(0.86, 1.14),
            x=rng.uniform(-0.85, 0.85),
            y=rng.uniform(-0.35, 0.45),
            z=rng.uniform(-0.55, 0.55),
            activity=rng.uniform(0.85, 1.1),
        )
        for i in range(count)
    ]


def _seed_patches(
    rng: random.Random,
    guild: str,
    count: int,
    total_biomass: float,
) -> list[MicrobePatch]:
    weights = [rng.uniform(0.65, 1.35) for _ in range(count)]
    total_weight = sum(weights)
    patches: list[MicrobePatch] = []
    for i, weight in enumerate(weights):
        if guild == "AOB":
            x = rng.uniform(0.35, 0.95)
            color_band = rng.uniform(-0.15, 0.35)
        else:
            x = rng.uniform(0.15, 0.92)
            color_band = rng.uniform(-0.55, -0.12)
        patches.append(
            MicrobePatch(
                id=f"{guild.lower()}-{i + 1}",
                guild=guild,
                biomass_mg_l=max(0.0001, total_biomass * weight / total_weight),
                x=x,
                y=rng.uniform(-0.78, 0.78),
                z=color_band,
                local_factor=rng.uniform(0.82, 1.18),
            )
        )
    return patches


def _move_fish(agent: FishAgent, rng: random.Random, dt_days: float) -> None:
    speed = 0.18 * agent.activity * math.sqrt(max(dt_days, 0.02))
    agent.x = _reflect(agent.x + rng.uniform(-speed, speed), -0.95, 0.95)
    agent.y = _reflect(agent.y + rng.uniform(-speed * 0.55, speed * 0.55), -0.7, 0.7)
    agent.z = _reflect(agent.z + rng.uniform(-speed * 0.45, speed * 0.45), -0.65, 0.65)


def _reflect(value: float, low: float, high: float) -> float:
    if value < low:
        return low + (low - value)
    if value > high:
        return high - (value - high)
    return value


def _stress_signal(chem: Chemistry, params: Params) -> float:
    nh3 = max(0.0, chem.TAN) * nh3_free_fraction(params.ph, params.temperature_c)
    nh3_term = nh3 / 0.05
    no2_term = max(0.0, chem.NO2) / 0.5
    do_term = max(0.0, 5.0 - chem.DO) / 2.0
    return _clamp(max(nh3_term, no2_term, do_term), 0.0, 6.0)


def _apply_agent_event(
    chem: Chemistry,
    params: Params,
    feed_g_day: float,
    event: Event,
    tap: TapWater,
    event_rows: list[dict[str, Any]],
    patches: list[MicrobePatch],
) -> tuple[Chemistry, Params, float]:
    before = asdict(chem)
    if event.kind == "feed":
        # The ABM drives feeding through explicit fish excretion (the
        # feed_g_day source in _advance_agents), so a feed event updates only
        # that rate. It must NOT also fold into the scalar ammonia_dose the
        # way the ODE's apply_event does — otherwise the same food would be
        # counted twice (once as a dose, once as excretion).
        new_chem, new_params = chem, params
        feed_g_day = event.value
    elif event.kind == "wipe_biofilm":
        # The ABM's biofilm IS the patch list; _advance_agents recomputes
        # chem.X_AOB/X_NOB from it each step, so scaling chem alone would be
        # overwritten. Knock back every patch by the same fraction, then sync
        # chem so the post-event row reflects the wipe immediately.
        f = event.value
        for patch in patches:
            patch.biomass_mg_l = max(0.0001, patch.biomass_mg_l * (1.0 - f))
        new_chem, new_params = apply_event(chem, params, event, tap)
        new_chem.X_AOB = sum(p.biomass_mg_l for p in patches if p.guild == "AOB")
        new_chem.X_NOB = sum(p.biomass_mg_l for p in patches if p.guild == "NOB")
    else:
        new_chem, new_params = apply_event(chem, params, event, tap)
    event_rows.append(
        {
            "day": round(event.day, 4),
            "kind": event.kind,
            "target": event.target,
            "value": event.value,
            "repeat_days": event.repeat_days,
            "TAN_before": round(before["TAN"], 6),
            "TAN_after": round(new_chem.TAN, 6),
            "NO2_before": round(before["NO2"], 6),
            "NO2_after": round(new_chem.NO2, 6),
            "NO3_before": round(before["NO3"], 6),
            "NO3_after": round(new_chem.NO3, 6),
            "DO_before": round(before["DO"], 6),
            "DO_after": round(new_chem.DO, 6),
        }
    )
    return new_chem, new_params, feed_g_day


def _schedule_from_payload(value: Any, tap: TapWater, days: float) -> EventSchedule:
    if not isinstance(value, list):
        raise ValueError("events must be a list")
    events: list[Event] = []
    for index, item in enumerate(value):
        events.append(event_from_mapping(item, index))
    return EventSchedule(events=events, tap_water=tap, horizon=days)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _float(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, got {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return out


def _int(value: Any, label: str) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer, got {value!r}") from exc
    return out


def _bounded(value: float, label: str, low: float, high: float) -> float:
    if not low <= value <= high:
        raise ValueError(f"{label} must be in [{low}, {high}], got {value!r}")
    return value


def _bounded_int(value: Any, label: str, low: int, high: int) -> int:
    out = _int(value, label)
    if not low <= out <= high:
        raise ValueError(f"{label} must be in [{low}, {high}], got {out!r}")
    return out


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


__all__ = [
    "FishAgent",
    "MicrobePatch",
    "simulate_agent_based_model",
]
