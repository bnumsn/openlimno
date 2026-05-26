"""Native inSTREAM-like individual-based model.

The goal is not to execute NetLogo model files. This module provides a native,
headless IBM kernel that can be tested, versioned, and run inside OpenLimno's
existing WEDM/provenance workflows.
"""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from openlimno import __version__
from openlimno.ibm.events import (
    EVENT_COLUMNS as _EVENT_COLUMNS,
)
from openlimno.ibm.events import (
    counts_by_reach as _counts_by_reach,
)
from openlimno.ibm.events import (
    spawner_counts_by_reach as _spawner_counts_by_reach,
)
from openlimno.ibm.events import (
    write_event_report,
)
from openlimno.ibm.runtime_submodels import (
    BioenergeticGrowthModel,
    CalibratedReddPlacementModel,
    CrossReachMovementModel,
    GrowthRiskHabitatModel,
    NetworkMovementModel,
    ReddRecruitmentModel,
    SizePriorityCellChooser,
    length_to_mass_g,
    mass_to_length_mm,
)

_PHASE_FEED_WEIGHT = (
    ("dawn", 0.85),
    ("day", 1.0),
    ("dusk", 0.9),
    ("night", 0.35),
)
_PHASE_PREDATION_WEIGHT = (
    ("dawn", 0.65),
    ("day", 1.0),
    ("dusk", 0.7),
    ("night", 0.25),
)
_HABITAT_MODEL = GrowthRiskHabitatModel()
_GROWTH_MODEL = BioenergeticGrowthModel()
_CELL_CHOOSER = SizePriorityCellChooser(growth_model=_GROWTH_MODEL)
_MOVEMENT_MODEL = CrossReachMovementModel(habitat_model=_HABITAT_MODEL)
_NETWORK_MOVEMENT_MODEL = NetworkMovementModel(habitat_model=_HABITAT_MODEL)
_REDD_MODEL = ReddRecruitmentModel()
_CALIBRATED_REDD_MODEL = ReddRecruitmentModel(
    placement_model=CalibratedReddPlacementModel(use_hydraulic_survival=True)
)


@dataclass(frozen=True)
class SpeciesProfile:
    """Species and life-history parameters for the native IBM."""

    species: str = "rainbow_trout"
    thermal_min_c: float = 1.0
    thermal_optimum_c: float = 12.0
    thermal_max_c: float = 23.0
    max_daily_growth_mm: float = 0.32
    weight_a_g_per_cm_b: float = 0.0115
    weight_b: float = 3.0
    max_consumption_fraction: float = 0.018
    respiration_fraction: float = 0.004
    activity_respiration_fraction: float = 0.006
    base_daily_survival: float = 0.997
    carrying_density_per_m2: float = 0.08
    min_cell_capacity: float = 1.0
    density_competition_strength: float = 1.0
    light_phase_feeding_weights: tuple[tuple[str, float], ...] = _PHASE_FEED_WEIGHT
    light_phase_predation_weights: tuple[tuple[str, float], ...] = _PHASE_PREDATION_WEIGHT
    default_light_phase_feeding_weight: float = 0.75
    default_light_phase_predation_weight: float = 0.75
    turbidity_half_saturation_ntu: float = 45.0
    feeding_cover_foraging_weight: float = 0.25
    predation_base_risk: float = 0.006
    predation_csi_risk: float = 0.018
    thermal_stress_mortality: float = 0.03
    velocity_stress_threshold_ms: float = 1.4
    velocity_stress_scale_ms: float = 1.4
    hydraulic_stress_mortality: float = 0.025
    utility_growth_weight: float = 12.0
    utility_mortality_weight: float = 25.0
    max_mortality_risk: float = 0.95
    respiration_base_multiplier: float = 0.45
    respiration_thermal_multiplier: float = 0.55
    max_activity_velocity_ms: float = 2.0
    max_mass_loss_fraction: float = 0.02
    max_mass_gain_fraction: float = 0.05
    max_daily_shrinkage_mm: float = 0.08
    maturity_length_mm: float = 120.0
    spawn_start_day: int = 90
    spawn_end_day: int = 150
    spawner_female_fraction: float = 0.5
    fecundity_per_female: float = 80.0
    fecundity_length_exponent: float = 0.0
    fecundity_reference_length_mm: float = 120.0
    egg_to_fry_survival: float = 0.02
    egg_incubation_degree_days: float = 450.0
    spawning_cover_weight: float = 0.7
    spawning_csi_weight: float = 0.3
    redd_base_daily_survival: float = 0.995
    redd_min_depth_m: float = 0.05
    redd_scour_velocity_ms: float = 1.5
    redd_dewatering_mortality: float = 0.35
    redd_scour_mortality: float = 0.20
    fry_length_mm: float = 28.0
    fry_mass_g: float = 0.22
    allow_cross_reach_movement: bool = False
    cross_reach_movement_penalty: float = 8.0
    cross_reach_movement_rate: float = 0.0
    cross_reach_movement_min_length_mm: float = 0.0
    cross_reach_movement_length_scale_mm: float = 100.0
    cross_reach_movement_max_steps: int = 1
    cross_reach_interior_movement_multiplier: float = 1.0
    cross_reach_upstream_bias: float = 0.0
    cross_reach_habitat_utility_weight: float = 1.0


@dataclass(frozen=True)
class NativeIBMConfig:
    """Run configuration for the native IBM."""

    days: int = 365
    seed: int = 42
    start_day: int = 1
    start_year: int = 0
    scenario_id: str = "baseline"
    reach_id: str = "reach-1"
    light_phases: tuple[str, ...] = ("dawn", "day", "dusk", "night")
    stochastic: bool = True
    record_individual_history: bool = False
    movement_submodel: str = "native-adjacent-reach-movement-v0"
    spawning_submodel: str = "native-redd-recruitment-v0"
    time_index_column: str = "time_index"


@dataclass(frozen=True)
class NativeIBMResult:
    """Output tables from a native IBM run."""

    population_summary: pd.DataFrame
    final_individuals: pd.DataFrame
    cell_use: pd.DataFrame
    events: pd.DataFrame
    redds: pd.DataFrame
    individual_history: pd.DataFrame


def _length_to_mass_g(
    length_mm: pd.Series | np.ndarray | float,
    profile: SpeciesProfile | None = None,
) -> np.ndarray:
    """Approximate salmonid mass from fork length using W = a L^b."""

    return length_to_mass_g(length_mm, profile or SpeciesProfile())


def _mass_to_length_mm(
    mass_g: pd.Series | np.ndarray | float,
    profile: SpeciesProfile,
) -> np.ndarray:
    return mass_to_length_mm(mass_g, profile)


def build_initial_population(
    *,
    n: int,
    species: str = "rainbow_trout",
    length_mm: float = 110.0,
    mass_g: float | None = None,
    age_days: int = 365,
    profile: SpeciesProfile | None = None,
) -> pd.DataFrame:
    """Create an initial individual table for :func:`run_native_ibm`.

    If ``profile`` is supplied its ``weight_a``/``weight_b`` are used for
    length→mass; otherwise a default ``SpeciesProfile(species=species)``
    is constructed (which is what callers got before the 2026-05-26
    triple-AI software test caught a silent day-0/day-1 mass jump caused
    by initial-mass using default weight_a/b and the runtime later
    recomputing mass from length using the loaded archive's weight_a/b).
    """

    if n < 0:
        raise ValueError("initial population size must be non-negative")
    lengths = np.full(n, float(length_mm))
    if mass_g is None:
        mass_profile = profile if profile is not None else SpeciesProfile(species=species)
        masses = _length_to_mass_g(lengths, mass_profile)
    else:
        masses = np.full(n, float(mass_g))
    return pd.DataFrame(
        {
            "fish_id": np.arange(n, dtype=int),
            "species": species,
            "age_days": np.full(n, int(age_days), dtype=int),
            "length_mm": lengths,
            "mass_g": masses,
            "cell_id": np.full(n, "", dtype=object),
            "alive": np.ones(n, dtype=bool),
        }
    )


def _normalise_population_frame(
    population: pd.DataFrame,
    *,
    cfg: NativeIBMConfig,
    all_cells: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    fish = population.copy()
    required = {"fish_id", "species", "age_days", "length_mm", "mass_g", "cell_id", "alive"}
    missing = required - set(fish.columns)
    if missing:
        raise ValueError(f"{label} population missing columns: {sorted(missing)}")

    fish["fish_id"] = pd.to_numeric(fish["fish_id"], errors="raise").astype(int)
    if fish["fish_id"].duplicated().any():
        duplicates = sorted(fish.loc[fish["fish_id"].duplicated(), "fish_id"].unique().tolist())
        raise ValueError(f"{label} population fish_id values must be unique: {duplicates}")
    fish["alive"] = fish["alive"].astype(bool)
    fish["age_days"] = pd.to_numeric(fish["age_days"], errors="coerce").fillna(0).astype(int)
    fish["length_mm"] = pd.to_numeric(fish["length_mm"], errors="coerce")
    fish["mass_g"] = pd.to_numeric(fish["mass_g"], errors="coerce")
    fish["cell_id"] = fish["cell_id"].astype("string").fillna("").astype(str)
    cell_reach_lookup = pd.Series(dtype=object)
    if {"cell_id", "reach_id"} <= set(all_cells.columns):
        cell_reach_lookup = (
            all_cells[["cell_id", "reach_id"]]
            .dropna(subset=["cell_id", "reach_id"])
            .drop_duplicates("cell_id")
            .set_index("cell_id")["reach_id"]
            .astype(str)
        )
    mapped_reach = (
        fish["cell_id"].map(cell_reach_lookup)
        if not cell_reach_lookup.empty
        else pd.Series(pd.NA, index=fish.index, dtype="object")
    )
    if "spawned_season" in fish:
        fish["spawned_season"] = (
            pd.to_numeric(fish["spawned_season"], errors="coerce").fillna(-1).astype(int)
        )
    else:
        fish["spawned_season"] = -1
    if "origin_redd_id" in fish:
        fish["origin_redd_id"] = (
            pd.to_numeric(fish["origin_redd_id"], errors="coerce").fillna(-1).astype(int)
        )
    else:
        fish["origin_redd_id"] = -1
    if "reach_id" in fish:
        reach_values = fish["reach_id"].astype("string").str.strip()
        fish["reach_id"] = (
            reach_values.mask(reach_values.isna() | (reach_values == ""), mapped_reach)
            .fillna(cfg.reach_id)
            .astype(str)
        )
    elif "reach_id" in all_cells:
        fish["reach_id"] = mapped_reach.fillna(cfg.reach_id).astype(str)

    mapped_order = pd.Series(np.nan, index=fish.index, dtype="float64")
    if {"cell_id", "reach_order"} <= set(all_cells.columns):
        cell_order_lookup = (
            all_cells[["cell_id", "reach_order"]]
            .dropna(subset=["cell_id", "reach_order"])
            .drop_duplicates("cell_id")
            .set_index("cell_id")["reach_order"]
        )
        mapped_order = pd.to_numeric(fish["cell_id"].map(cell_order_lookup), errors="coerce")
    if {"reach_id", "reach_order"} <= set(all_cells.columns) and "reach_id" in fish:
        reach_order_lookup = (
            all_cells[["reach_id", "reach_order"]]
            .dropna(subset=["reach_id", "reach_order"])
            .drop_duplicates("reach_id")
            .set_index("reach_id")["reach_order"]
        )
        mapped_order = mapped_order.fillna(
            pd.to_numeric(fish["reach_id"].astype(str).map(reach_order_lookup), errors="coerce")
        )
    if "reach_order" in fish:
        fish["reach_order"] = pd.to_numeric(fish["reach_order"], errors="coerce").fillna(
            mapped_order
        )
    elif "reach_order" in all_cells and "reach_id" in fish:
        fish["reach_order"] = mapped_order
    return fish


def _required_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df:
        raise ValueError(f"habitat cells require {column!r}")
    return pd.to_numeric(df[column], errors="coerce")


def _normalise_habitat_cells(
    cells: pd.DataFrame,
    *,
    time_index_column: str = "time_index",
) -> pd.DataFrame:
    out = pd.DataFrame(index=cells.index)
    default_ids = pd.Series(np.arange(len(cells)), index=cells.index).astype(str)
    has_direct_csi = "csi" in cells or "wua_m2" in cells
    has_hydraulic_inputs = "depth_m" in cells and "velocity_ms" in cells
    if not has_direct_csi and not has_hydraulic_inputs:
        raise ValueError("habitat cells require csi, wua_m2, or both depth_m and velocity_ms")
    if "cell_id" in cells:
        cell_ids = cells["cell_id"].astype("string").str.strip()
        out["cell_id"] = cell_ids.mask(cell_ids.isna() | (cell_ids == ""), default_ids)
    else:
        out["cell_id"] = default_ids
    out["area_m2"] = _required_numeric(cells, "area_m2").clip(lower=0.0)
    out["depth_m"] = pd.to_numeric(cells.get("depth_m", np.nan), errors="coerce")
    out["velocity_ms"] = pd.to_numeric(cells.get("velocity_ms", np.nan), errors="coerce")
    if "csi" in cells:
        out["csi"] = pd.to_numeric(cells["csi"], errors="coerce")
    elif "wua_m2" in cells:
        wua = pd.to_numeric(cells["wua_m2"], errors="coerce")
        out["csi"] = np.where(out["area_m2"] > 0.0, wua / out["area_m2"], 0.0)
    else:
        out["csi"] = np.nan
    if has_hydraulic_inputs:
        hydraulic_csi = pd.Series(_hydraulic_suitability(out), index=out.index)
    else:
        hydraulic_csi = pd.Series(np.nan, index=out.index)
    out["csi"] = out["csi"].fillna(hydraulic_csi).clip(0.0, 1.0)
    if not bool(out["csi"].notna().any()):
        raise ValueError("habitat cells require at least one valid csi, wua_m2, or hydraulic value")
    out["temperature_c"] = pd.to_numeric(cells.get("temperature_c", 12.0), errors="coerce")
    out["temperature_c"] = out["temperature_c"].fillna(12.0)
    out["turbidity_ntu"] = pd.to_numeric(cells.get("turbidity_ntu", 0.0), errors="coerce")
    out["turbidity_ntu"] = out["turbidity_ntu"].fillna(0.0).clip(lower=0.0)
    out["hiding_cover"] = pd.to_numeric(cells.get("hiding_cover", 0.0), errors="coerce")
    out["hiding_cover"] = out["hiding_cover"].fillna(0.0).clip(0.0, 1.0)
    out["feeding_cover"] = pd.to_numeric(cells.get("feeding_cover", 0.0), errors="coerce")
    out["feeding_cover"] = out["feeding_cover"].fillna(0.0).clip(0.0, 1.0)
    out["spawning_cover"] = pd.to_numeric(cells.get("spawning_cover", 0.0), errors="coerce")
    out["spawning_cover"] = out["spawning_cover"].fillna(0.0).clip(0.0, 1.0)
    if "reach_id" in cells:
        reach_ids = cells["reach_id"].astype("string").str.strip()
        out["reach_id"] = reach_ids.mask(reach_ids.isna() | (reach_ids == ""), "reach-1").astype(
            str
        )
    if "reach_order" in cells:
        out["reach_order"] = pd.to_numeric(cells["reach_order"], errors="coerce")
    if "discharge_m3s" in cells:
        out["discharge_m3s"] = pd.to_numeric(cells["discharge_m3s"], errors="coerce")
    if time_index_column in cells:
        out["time_index"] = pd.to_numeric(cells[time_index_column], errors="coerce")
    elif time_index_column != "time_index" and "time_index" in cells:
        out["time_index"] = pd.to_numeric(cells["time_index"], errors="coerce")
    if (out["area_m2"] <= 0.0).all():
        raise ValueError("habitat cells need at least one positive-area cell")
    return out.reset_index(drop=True)


def _triangular_factor(
    values: pd.Series | np.ndarray,
    *,
    low: float,
    optimum: float,
    high: float,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    left = (arr - low) / max(optimum - low, 1e-9)
    right = (high - arr) / max(high - optimum, 1e-9)
    return np.clip(np.minimum(left, right), 0.0, 1.0)


def _hydraulic_suitability(cells: pd.DataFrame) -> np.ndarray:
    depth = pd.to_numeric(cells.get("depth_m", np.nan), errors="coerce").fillna(0.0)
    velocity = pd.to_numeric(cells.get("velocity_ms", np.nan), errors="coerce").fillna(0.0)
    depth_si = _triangular_factor(depth, low=0.05, optimum=0.65, high=2.5)
    velocity_si = _triangular_factor(velocity, low=0.0, optimum=0.35, high=1.8)
    return np.sqrt(depth_si * velocity_si)


def _cells_for_sim_day(cells: pd.DataFrame, offset: int) -> pd.DataFrame:
    if "time_index" not in cells:
        return cells
    available = (
        pd.Series(cells["time_index"].dropna().unique()).sort_values(kind="mergesort").to_list()
    )
    if not available:
        return cells.drop(columns=["time_index"])
    selected = available[min(offset, len(available) - 1)]
    day_cells = (
        cells[cells["time_index"] == selected].drop(columns=["time_index"]).reset_index(drop=True)
    )
    if day_cells.empty:
        raise ValueError(f"no habitat cells found for time_index {selected!r}")
    return day_cells


def _phase_cell_values(
    cells: pd.DataFrame,
    profile: SpeciesProfile,
    phase: str,
) -> pd.DataFrame:
    return _HABITAT_MODEL.phase_cell_values(cells, profile, phase)


def _bioenergetic_growth_mm(
    length_mm: float,
    cell_values: pd.DataFrame,
    selected_idx: int,
    profile: SpeciesProfile,
) -> float:
    return _GROWTH_MODEL.growth_mm(length_mm, cell_values, selected_idx, profile)


def _choose_cells(
    fish: pd.DataFrame,
    cell_values: pd.DataFrame,
    profile: SpeciesProfile,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray]:
    return _CELL_CHOOSER.choose_cells(fish, cell_values, profile, rng)


def _apply_cross_reach_migration(
    fish: pd.DataFrame,
    cells: pd.DataFrame,
    profile: SpeciesProfile,
    rng: np.random.Generator,
    stochastic: bool,
    movement_submodel: str = "native-adjacent-reach-movement-v0",
) -> tuple[pd.DataFrame, dict[str, int]]:
    if movement_submodel == "native-network-reach-movement-v0":
        return _NETWORK_MOVEMENT_MODEL.apply(fish, cells, profile, rng, stochastic)
    return _MOVEMENT_MODEL.apply(fish, cells, profile, rng, stochastic)


def _summarise_population(
    fish: pd.DataFrame,
    redds: pd.DataFrame,
    *,
    day: int,
    scenario_id: str,
    reach_id: str,
    species: str,
    initial_n: int,
    n_recruits: int,
    n_spawners: int,
) -> dict[str, object]:
    if "reach_id" in fish:
        fish = fish[fish["reach_id"].astype(str) == str(reach_id)]
    if "reach_id" in redds:
        redds = redds[redds["reach_id"].astype(str) == str(reach_id)]
    if "species" in fish:
        fish = fish[fish["species"].astype(str) == str(species)]
    if "species" in redds:
        redds = redds[redds["species"].astype(str) == str(species)]
    alive = fish[fish["alive"]]
    abundance = int(len(alive))
    biomass = float(alive["mass_g"].sum()) if abundance else 0.0
    mean_length = float(alive["length_mm"].mean()) if abundance else np.nan
    if redds.empty:
        active_redds = 0
        eggs_remaining = 0
    else:
        active = redds["alive"].astype(bool) & ~redds["emerged"].astype(bool)
        active_redds = int(active.sum())
        eggs_remaining = int(
            pd.to_numeric(redds.loc[active, "eggs_remaining"], errors="coerce").sum()
        )
    return {
        "scenario_id": scenario_id,
        "reach_id": reach_id,
        "day": day,
        "species": species,
        "abundance": abundance,
        "biomass_g": biomass,
        "mean_length_mm": mean_length,
        # When the simulation starts with zero fish, survival is undefined
        # (0/0). Report None instead of a misleading 0.0 — pinned by the
        # 2026-05-26 pass-2 software test (Codex M3').
        "survival_rate": (abundance / initial_n) if initial_n else None,
        "n_recruits": n_recruits,
        "n_spawners": n_spawners,
        "n_active_redds": active_redds,
        "n_eggs_remaining": eggs_remaining,
    }


_REDD_COLUMNS = [
    "redd_id",
    "species",
    "cell_id",
    "reach_id",
    "spawn_day",
    "spawn_season",
    "age_days",
    "eggs_initial",
    "eggs_remaining",
    "development_degree_days",
    "incubation_target_degree_days",
    "alive",
    "emerged",
    "emergence_day",
]
_HISTORY_COLUMNS = [
    "scenario_id",
    "reach_id",
    "day",
    "fish_id",
    "species",
    "age_days",
    "length_mm",
    "mass_g",
    "cell_id",
    "alive",
    "spawned_season",
    "origin_redd_id",
]


def _empty_redds() -> pd.DataFrame:
    return pd.DataFrame(columns=_REDD_COLUMNS)


def _history_rows(
    fish: pd.DataFrame,
    *,
    day: int,
    scenario_id: str,
    reach_id: str,
) -> list[dict[str, object]]:
    base_columns = [col for col in _HISTORY_COLUMNS[3:] if col != "reach_id"]
    rows = fish[base_columns].copy()
    if "reach_id" in fish:
        rows.insert(0, "reach_id", fish["reach_id"].astype(str).to_numpy())
    else:
        rows.insert(0, "reach_id", reach_id)
    rows.insert(0, "day", int(day))
    rows.insert(0, "scenario_id", scenario_id)
    return rows.to_dict("records")


def _fallback_spawning_cell(cells: pd.DataFrame, profile: SpeciesProfile) -> str:
    return _REDD_MODEL.fallback_spawning_cell(cells, profile)


def _spawn_redds(
    fish: pd.DataFrame,
    redds: pd.DataFrame,
    cells: pd.DataFrame,
    *,
    sim_day: int,
    spawn_season: int | None,
    next_redd_id: int,
    profile: SpeciesProfile,
    rng: np.random.Generator,
    stochastic: bool,
    spawning_submodel: str = "native-redd-recruitment-v0",
) -> tuple[pd.DataFrame, pd.DataFrame, int, int, int]:
    model = (
        _CALIBRATED_REDD_MODEL
        if spawning_submodel == "native-calibrated-redd-placement-v0"
        else _REDD_MODEL
    )
    return model.spawn_redds(
        fish,
        redds,
        cells,
        sim_day=sim_day,
        spawn_season=spawn_season,
        next_redd_id=next_redd_id,
        profile=profile,
        rng=rng,
        stochastic=stochastic,
    )


def _update_redds(
    redds: pd.DataFrame,
    cells: pd.DataFrame,
    *,
    sim_day: int,
    next_fish_id: int,
    profile: SpeciesProfile,
    rng: np.random.Generator,
    stochastic: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    return _REDD_MODEL.update_redds(
        redds,
        cells,
        sim_day=sim_day,
        next_fish_id=next_fish_id,
        profile=profile,
        rng=rng,
        stochastic=stochastic,
    )


def _spawn_season_for_day(profile: SpeciesProfile, day_of_year: int, year: int) -> int | None:
    start = int(profile.spawn_start_day)
    end = int(profile.spawn_end_day)
    if start <= end:
        return year if start <= day_of_year <= end else None
    if day_of_year >= start:
        return year
    if day_of_year <= end:
        return year - 1
    return None


def run_native_ibm(
    habitat_cells: pd.DataFrame,
    initial_population: pd.DataFrame,
    *,
    profile: SpeciesProfile | None = None,
    config: NativeIBMConfig | None = None,
    scheduled_population: pd.DataFrame | None = None,
) -> NativeIBMResult:
    """Run the native individual-based population model."""

    cfg = config or NativeIBMConfig()
    if cfg.days < 0:
        raise ValueError("days must be non-negative")
    prof = profile or SpeciesProfile()
    all_cells = _normalise_habitat_cells(habitat_cells, time_index_column=cfg.time_index_column)
    fish = _normalise_population_frame(
        initial_population,
        cfg=cfg,
        all_cells=all_cells,
        label="initial",
    )
    if scheduled_population is None:
        scheduled = pd.DataFrame(columns=["arrival_day"])
    else:
        if "arrival_day" not in scheduled_population:
            raise ValueError("scheduled population missing columns: ['arrival_day']")
        scheduled = _normalise_population_frame(
            scheduled_population.drop(columns=["arrival_day"]),
            cfg=cfg,
            all_cells=all_cells,
            label="scheduled",
        )
        scheduled.insert(
            0,
            "arrival_day",
            pd.to_numeric(scheduled_population["arrival_day"], errors="coerce").astype("Int64"),
        )
        scheduled = scheduled.dropna(subset=["arrival_day"]).copy()
        scheduled["arrival_day"] = scheduled["arrival_day"].astype(int)
        if not scheduled.empty:
            invalid = scheduled["arrival_day"] < 1
            if bool(invalid.any()):
                days = sorted(scheduled.loc[invalid, "arrival_day"].unique().tolist())
                raise ValueError(f"scheduled population arrival_day must be >= 1: {days}")
    scheduled_ids = set(scheduled["fish_id"].astype(int)) if "fish_id" in scheduled else set()
    duplicate_ids = sorted(set(fish["fish_id"].astype(int)).intersection(scheduled_ids))
    if duplicate_ids:
        raise ValueError(
            f"initial and scheduled population fish_id values overlap: {duplicate_ids}"
        )

    rng = np.random.default_rng(cfg.seed)
    initial_n = int(fish["alive"].sum())
    all_known_ids = pd.concat(
        [
            fish["fish_id"].astype(int),
            scheduled["fish_id"].astype(int) if "fish_id" in scheduled else pd.Series(dtype=int),
        ],
        ignore_index=True,
    )
    next_fish_id = int(all_known_ids.max()) + 1 if len(all_known_ids) else 0
    next_redd_id = 0
    redds = _empty_redds()
    species_values = (
        sorted(
            set(fish["species"].astype(str))
            | (set(scheduled["species"].astype(str)) if "species" in scheduled else set())
        )
        if ("species" in fish and not fish.empty)
        or ("species" in scheduled and not scheduled.empty)
        else [prof.species]
    )
    if "reach_id" in fish:
        cell_reaches = (
            all_cells["reach_id"].astype(str) if "reach_id" in all_cells else pd.Series(dtype=str)
        )
        scheduled_reaches = (
            set(scheduled["reach_id"].astype(str))
            if "reach_id" in scheduled and not scheduled.empty
            else set()
        )
        summary_reach_ids = sorted(
            set(fish["reach_id"].astype(str)) | set(cell_reaches) | scheduled_reaches
        )
    else:
        summary_reach_ids = [cfg.reach_id]
    if "reach_id" in fish and "species" in fish:
        initial_by_key = {
            (str(reach_id), str(species_id)): int(value)
            for (reach_id, species_id), value in fish[fish["alive"]]
            .groupby([fish["reach_id"].astype(str), fish["species"].astype(str)])
            .size()
            .items()
        }
    elif "species" in fish and not fish.empty:
        initial_by_key = {
            (cfg.reach_id, str(species_id)): int(value)
            for species_id, value in fish[fish["alive"]]
            .groupby(fish["species"].astype(str))
            .size()
            .items()
        }
    else:
        initial_by_key = {(cfg.reach_id, prof.species): initial_n}
    summary_rows: list[dict[str, object]] = [
        _summarise_population(
            fish,
            redds,
            day=0,
            scenario_id=cfg.scenario_id,
            reach_id=reach_id,
            species=species_id,
            initial_n=initial_by_key.get((reach_id, species_id), 0),
            n_recruits=0,
            n_spawners=0,
        )
        for reach_id in summary_reach_ids
        for species_id in species_values
    ]
    cell_use_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    individual_history_rows: list[dict[str, object]] = []
    if cfg.record_individual_history:
        individual_history_rows.extend(
            _history_rows(
                fish,
                day=0,
                scenario_id=cfg.scenario_id,
                reach_id=cfg.reach_id,
            )
        )

    for offset in range(cfg.days):
        sim_day = offset + 1
        absolute_day = int(cfg.start_day) - 1 + offset
        simulation_year = int(cfg.start_year) + absolute_day // 365
        day_of_year = (absolute_day % 365) + 1
        cells = _cells_for_sim_day(all_cells, offset)
        if not scheduled.empty:
            arrivals_today = scheduled[scheduled["arrival_day"] == sim_day]
            if not arrivals_today.empty:
                arrivals = arrivals_today.drop(columns=["arrival_day"]).copy()
                fish = pd.concat([fish, arrivals], ignore_index=True)
                initial_n += int(arrivals["alive"].sum())
                if "reach_id" in arrivals and "species" in arrivals:
                    for (arrival_reach, arrival_species), n_arrivals in (
                        arrivals[arrivals["alive"]]
                        .groupby(
                            [arrivals["reach_id"].astype(str), arrivals["species"].astype(str)]
                        )
                        .size()
                        .items()
                    ):
                        key = (str(arrival_reach), str(arrival_species))
                        initial_by_key[key] = initial_by_key.get(key, 0) + int(n_arrivals)
                for arrival_reach_id, n_arrivals in _counts_by_reach(
                    arrivals, cfg.reach_id
                ).items():
                    event_rows.append(
                        {
                            "scenario_id": cfg.scenario_id,
                            "reach_id": arrival_reach_id,
                            "day": sim_day,
                            "event": "arrival",
                            "n": n_arrivals,
                            "n_eggs": 0,
                        }
                    )
        fish, movement_counts = _apply_cross_reach_migration(
            fish,
            cells,
            prof,
            rng,
            cfg.stochastic,
            cfg.movement_submodel,
        )
        for moved_reach_id, n_moved in movement_counts.items():
            event_rows.append(
                {
                    "scenario_id": cfg.scenario_id,
                    "reach_id": moved_reach_id,
                    "day": sim_day,
                    "event": "movement",
                    "n": n_moved,
                }
            )
        daily_growth = pd.Series(0.0, index=fish.index)
        daily_mortality = pd.Series(0.0, index=fish.index)

        for phase in cfg.light_phases:
            alive_idx = fish.index[fish["alive"]].to_numpy()
            if len(alive_idx) == 0:
                continue
            cell_values = _phase_cell_values(cells, prof, phase)
            chosen, chosen_reach, growth, mortality = _choose_cells(
                fish.loc[alive_idx],
                cell_values,
                prof,
                rng,
            )
            fish.loc[alive_idx, "cell_id"] = chosen
            if chosen_reach is not None:
                fish.loc[alive_idx, "reach_id"] = chosen_reach
            daily_growth.loc[alive_idx] += growth / max(len(cfg.light_phases), 1)
            daily_mortality.loc[alive_idx] += mortality / max(len(cfg.light_phases), 1)

            use_frame = pd.DataFrame(
                {
                    "cell_id": chosen,
                    "growth_mm": growth,
                    "mortality_risk": mortality,
                }
            )
            group_cols = ["cell_id"]
            if chosen_reach is not None:
                use_frame["reach_id"] = chosen_reach
                group_cols.insert(0, "reach_id")
            use = use_frame.groupby(group_cols, as_index=False).agg(
                n_fish=("cell_id", "size"),
                mean_growth_mm=("growth_mm", "mean"),
                mean_mortality_risk=("mortality_risk", "mean"),
            )
            for row in use.to_dict("records"):
                row.update(
                    {
                        "scenario_id": cfg.scenario_id,
                        "reach_id": str(row.get("reach_id", cfg.reach_id)),
                        "day": sim_day,
                        "phase": phase,
                    }
                )
                cell_use_rows.append(row)

        alive_idx = fish.index[fish["alive"]]
        if len(alive_idx):
            fish.loc[alive_idx, "length_mm"] = (
                fish.loc[alive_idx, "length_mm"] + daily_growth.loc[alive_idx]
            ).clip(lower=prof.fry_length_mm)
            fish.loc[alive_idx, "mass_g"] = _length_to_mass_g(
                fish.loc[alive_idx, "length_mm"].to_numpy(dtype=float),
                prof,
            )
            fish.loc[alive_idx, "age_days"] = fish.loc[alive_idx, "age_days"] + 1
            if cfg.stochastic:
                deaths = rng.random(len(alive_idx)) < daily_mortality.loc[alive_idx].to_numpy()
            else:
                deaths = daily_mortality.loc[alive_idx].to_numpy() >= 0.5
            if deaths.any():
                dead_idx = alive_idx[deaths]
                dead_fish = fish.loc[dead_idx].copy()
                fish.loc[dead_idx, "alive"] = False
                for dead_reach_id, n_dead in _counts_by_reach(dead_fish, cfg.reach_id).items():
                    event_rows.append(
                        {
                            "scenario_id": cfg.scenario_id,
                            "reach_id": dead_reach_id,
                            "day": sim_day,
                            "event": "mortality",
                            "n": n_dead,
                        }
                    )

        redds, emerged, next_fish_id, n_recruits = _update_redds(
            redds,
            cells,
            sim_day=sim_day,
            next_fish_id=next_fish_id,
            profile=prof,
            rng=rng,
            stochastic=cfg.stochastic,
        )
        if not emerged.empty:
            fish = pd.concat([fish, emerged], ignore_index=True)
        if n_recruits:
            for recruit_reach_id, n_reach_recruits in _counts_by_reach(
                emerged,
                cfg.reach_id,
            ).items():
                event_rows.append(
                    {
                        "scenario_id": cfg.scenario_id,
                        "reach_id": recruit_reach_id,
                        "day": sim_day,
                        "event": "recruitment",
                        "n": n_reach_recruits,
                    }
                )

        spawn_season = _spawn_season_for_day(prof, day_of_year, simulation_year)
        spawners_by_reach = _spawner_counts_by_reach(fish, prof, spawn_season, cfg.reach_id)
        redd_count_before_spawn = len(redds)
        fish, redds, next_redd_id, n_spawners, _n_eggs = _spawn_redds(
            fish,
            redds,
            cells,
            sim_day=sim_day,
            spawn_season=spawn_season,
            next_redd_id=next_redd_id,
            profile=prof,
            rng=rng,
            stochastic=cfg.stochastic,
            spawning_submodel=cfg.spawning_submodel,
        )
        if n_spawners:
            new_redds = redds.iloc[redd_count_before_spawn:]
            eggs_by_reach = (
                {
                    str(key): int(value)
                    for key, value in new_redds.groupby(new_redds["reach_id"].astype(str))[
                        "eggs_initial"
                    ]
                    .sum()
                    .items()
                }
                if not new_redds.empty and "reach_id" in new_redds
                else {}
            )
            for spawn_reach_id, n_reach_spawners in spawners_by_reach.items():
                event_rows.append(
                    {
                        "scenario_id": cfg.scenario_id,
                        "reach_id": spawn_reach_id,
                        "day": sim_day,
                        "event": "spawning",
                        "n": n_reach_spawners,
                        "n_eggs": eggs_by_reach.get(spawn_reach_id, 0),
                    }
                )
        recruits_by_reach = (
            {
                str(key): int(value)
                for key, value in emerged.groupby(emerged["reach_id"].astype(str)).size().items()
            }
            if not emerged.empty and "reach_id" in emerged
            else {}
        )
        for reach_id in summary_reach_ids:
            for species_id in species_values:
                summary_rows.append(
                    _summarise_population(
                        fish,
                        redds,
                        day=sim_day,
                        scenario_id=cfg.scenario_id,
                        reach_id=reach_id,
                        species=species_id,
                        initial_n=initial_by_key.get((reach_id, species_id), 0),
                        n_recruits=(
                            recruits_by_reach.get(
                                reach_id,
                                n_recruits if len(summary_reach_ids) == 1 else 0,
                            )
                            if species_id == prof.species
                            else 0
                        ),
                        n_spawners=spawners_by_reach.get(reach_id, 0)
                        if species_id == prof.species
                        else 0,
                    )
                )
        if cfg.record_individual_history:
            individual_history_rows.extend(
                _history_rows(
                    fish,
                    day=sim_day,
                    scenario_id=cfg.scenario_id,
                    reach_id=cfg.reach_id,
                )
            )

    return NativeIBMResult(
        population_summary=pd.DataFrame.from_records(summary_rows),
        final_individuals=fish.reset_index(drop=True),
        cell_use=pd.DataFrame.from_records(cell_use_rows),
        events=pd.DataFrame.from_records(event_rows, columns=_EVENT_COLUMNS),
        redds=redds.reset_index(drop=True),
        individual_history=pd.DataFrame.from_records(
            individual_history_rows,
            columns=_HISTORY_COLUMNS,
        ),
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_native_ibm_result(
    result: NativeIBMResult,
    output_dir: str | Path,
    *,
    manifest: Mapping[str, object] | None = None,
    formats: Sequence[str] | None = None,
) -> dict[str, str]:
    """Write native IBM result tables and a machine-readable run manifest."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output_formats = _normalise_output_formats(formats)
    tables = {
        "native_ibm_population_summary": result.population_summary,
        "native_ibm_final_individuals": result.final_individuals,
        "native_ibm_cell_use": result.cell_use,
        "native_ibm_events": result.events,
        "native_ibm_redds": result.redds,
    }
    if not result.individual_history.empty:
        tables["native_ibm_individual_history"] = result.individual_history
    paths: dict[str, str] = {}
    for stem, table in tables.items():
        first_target: Path | None = None
        for output_format in output_formats:
            target = out / f"{stem}.{output_format}"
            if output_format == "csv":
                table.to_csv(target, index=False)
                paths[stem] = str(target)
            elif output_format == "parquet":
                table.to_parquet(target, index=False)
                paths[f"{stem}_parquet"] = str(target)
            if first_target is None:
                first_target = target
        if stem not in paths and first_target is not None:
            paths[stem] = str(first_target)
    event_report_paths = write_event_report(result.events, out)
    paths.update(event_report_paths)
    manifest_outputs: dict[str, dict[str, object]] = {}
    for stem, table in tables.items():
        for output_format in output_formats:
            target = out / f"{stem}.{output_format}"
            manifest_outputs[target.name] = {
                "path": str(target),
                "rows": int(len(table)),
                "sha256": _sha256_file(target),
            }
    for path_str in event_report_paths.values():
        target = Path(path_str)
        manifest_outputs[target.name] = {
            "path": str(target),
            "rows": int(len(pd.read_csv(target, comment="#"))),
            "sha256": _sha256_file(target),
        }
    manifest_payload: dict[str, object] = {
        "openlimno_version": __version__,
        "ibm_result_version": "0.2",
        "output_formats": list(output_formats),
    }
    if manifest is not None:
        manifest_payload.update(dict(manifest))
    manifest_payload["outputs"] = manifest_outputs
    manifest_path = out / "ibm_run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    paths["ibm_run_manifest"] = str(manifest_path)

    # 2026-05-26 R-IBM-PROVENANCE (ADR-0016 cleanup track; round-22
    # codex A5 / gemini A4 HIGH): bridge the IBM-specific manifest
    # to a Case-compatible ``provenance.json`` schema.
    manifest_sha = _sha256_file(manifest_path)
    # Best-effort git SHA (matches Case._emit_provenance pattern).
    git_sha: str | None = None
    try:
        import subprocess as _subprocess
        _git_result = _subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if _git_result.returncode == 0:
            git_sha = _git_result.stdout.strip() or None
    except Exception:  # noqa: BLE001
        git_sha = None
    # Fingerprint over STABLE INPUT identifiers only. Excludes
    # ``outputs`` (whose values carry absolute filesystem paths) and
    # any time-sensitive fields. This keeps the fingerprint
    # reproducible across reruns of the same seed even when the
    # output dir differs (e.g. /tmp/test-a vs /tmp/test-b).
    _fp_payload = {
        "openlimno_version": __version__,
        "ibm_result_version": "0.2",
        "output_formats": list(output_formats),
        "input_manifest": dict(manifest) if manifest is not None else {},
    }
    fingerprint = hashlib.sha256(
        json.dumps(_fp_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    case_compat_provenance: dict[str, object] = {
        "openlimno_version": __version__,
        "schema": "openlimno-provenance/0.1+ibm",
        "run_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "machine": {
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version,
        },
        "parameter_fingerprint": fingerprint,
        "inputs": {
            # We don't have direct access to a Case here, so the
            # input identifiers are the IBM-config snapshot in
            # manifest_payload (if provided) + the fingerprint.
            "ibm_config_fingerprint": fingerprint,
        },
        "outputs": manifest_outputs,
        "dependencies": {
            "pixi_lock_sha256": None,  # not in scope of standalone IBM run
            "container_image_sha": None,
        },
        "ibm": {
            "ibm_result_version": "0.2",
            "manifest_path": str(manifest_path.name),
            "manifest_sha256": manifest_sha,
            "output_formats": list(output_formats),
        },
        "warnings": [],
        "studyplan_present": False,
    }
    provenance_path = out / "provenance.json"
    provenance_path.write_text(
        json.dumps(case_compat_provenance, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    paths["provenance"] = str(provenance_path)
    return paths


def _normalise_output_formats(formats: Sequence[str] | None) -> tuple[str, ...]:
    if formats is None:
        return ("csv",)
    requested: list[str] = []
    for value in formats:
        output_format = str(value).strip().lower()
        if not output_format:
            continue
        if output_format not in {"csv", "parquet"}:
            raise ValueError(f"Unsupported IBM output format {output_format!r}")
        if output_format not in requested:
            requested.append(output_format)
    return tuple(requested or ["csv"])
