"""Runtime submodel implementations used by the native IBM engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import Protocol

import numpy as np
import pandas as pd


class NativeIBMProfile(Protocol):
    """Structural profile contract needed by extracted runtime submodels."""

    thermal_min_c: float
    thermal_optimum_c: float
    thermal_max_c: float
    max_daily_growth_mm: float
    weight_a_g_per_cm_b: float
    weight_b: float
    max_consumption_fraction: float
    respiration_fraction: float
    activity_respiration_fraction: float
    base_daily_survival: float
    carrying_density_per_m2: float
    min_cell_capacity: float
    density_competition_strength: float
    light_phase_feeding_weights: tuple[tuple[str, float], ...]
    light_phase_predation_weights: tuple[tuple[str, float], ...]
    default_light_phase_feeding_weight: float
    default_light_phase_predation_weight: float
    turbidity_half_saturation_ntu: float
    feeding_cover_foraging_weight: float
    predation_base_risk: float
    predation_csi_risk: float
    thermal_stress_mortality: float
    velocity_stress_threshold_ms: float
    velocity_stress_scale_ms: float
    hydraulic_stress_mortality: float
    utility_growth_weight: float
    utility_mortality_weight: float
    max_mortality_risk: float
    respiration_base_multiplier: float
    respiration_thermal_multiplier: float
    max_activity_velocity_ms: float
    max_mass_loss_fraction: float
    max_mass_gain_fraction: float
    max_daily_shrinkage_mm: float
    species: str
    maturity_length_mm: float
    spawner_female_fraction: float
    fecundity_per_female: float
    fecundity_length_exponent: float
    fecundity_reference_length_mm: float
    egg_to_fry_survival: float
    egg_incubation_degree_days: float
    spawning_cover_weight: float
    spawning_csi_weight: float
    redd_base_daily_survival: float
    redd_min_depth_m: float
    redd_scour_velocity_ms: float
    redd_dewatering_mortality: float
    redd_scour_mortality: float
    fry_length_mm: float
    fry_mass_g: float
    allow_cross_reach_movement: bool
    cross_reach_movement_penalty: float
    cross_reach_movement_rate: float
    cross_reach_movement_min_length_mm: float
    cross_reach_movement_length_scale_mm: float
    cross_reach_movement_max_steps: int
    cross_reach_interior_movement_multiplier: float
    cross_reach_upstream_bias: float
    cross_reach_habitat_utility_weight: float


def triangular_factor(
    values: pd.Series | np.ndarray,
    *,
    low: float,
    optimum: float,
    high: float,
) -> np.ndarray:
    """Triangular suitability factor clipped to ``[0, 1]``."""

    arr = np.asarray(values, dtype=float)
    left = (arr - low) / max(optimum - low, 1e-9)
    right = (high - arr) / max(high - optimum, 1e-9)
    return np.clip(np.minimum(left, right), 0.0, 1.0)


def length_to_mass_g(
    length_mm: pd.Series | np.ndarray | float,
    profile: NativeIBMProfile,
) -> np.ndarray:
    """Approximate fish mass from fork length using ``W = a L^b``."""

    length_cm = np.maximum(np.asarray(length_mm, dtype=float) / 10.0, 0.0)
    return profile.weight_a_g_per_cm_b * length_cm**profile.weight_b


def mass_to_length_mm(
    mass_g: pd.Series | np.ndarray | float,
    profile: NativeIBMProfile,
) -> np.ndarray:
    """Invert the profile length-weight curve."""

    mass = np.maximum(np.asarray(mass_g, dtype=float), 0.0)
    exponent = max(float(profile.weight_b), 1e-9)
    coefficient = max(float(profile.weight_a_g_per_cm_b), 1e-12)
    return 10.0 * (mass / coefficient) ** (1.0 / exponent)


@dataclass(frozen=True)
class GrowthRiskHabitatModel:
    """Cell-level foraging, mortality, and utility calculations."""

    def phase_cell_values(
        self,
        cells: pd.DataFrame,
        profile: NativeIBMProfile,
        phase: str,
    ) -> pd.DataFrame:
        feed_weight = dict(profile.light_phase_feeding_weights).get(
            phase,
            profile.default_light_phase_feeding_weight,
        )
        pred_weight = dict(profile.light_phase_predation_weights).get(
            phase,
            profile.default_light_phase_predation_weight,
        )
        temp_factor = triangular_factor(
            cells["temperature_c"],
            low=profile.thermal_min_c,
            optimum=profile.thermal_optimum_c,
            high=profile.thermal_max_c,
        )
        turbidity_factor = 1.0 / (
            1.0
            + cells["turbidity_ntu"].to_numpy(dtype=float)
            / max(profile.turbidity_half_saturation_ntu, 1e-9)
        )
        feeding_cover = cells["feeding_cover"].to_numpy(dtype=float)
        hiding_cover = cells["hiding_cover"].to_numpy(dtype=float)
        velocity = cells["velocity_ms"].fillna(0.0).to_numpy(dtype=float)
        csi = cells["csi"].to_numpy(dtype=float)

        cover_weight = np.clip(profile.feeding_cover_foraging_weight, 0.0, 1.0)
        cover_factor = 1.0 - cover_weight + cover_weight * feeding_cover
        foraging = feed_weight * csi * temp_factor * turbidity_factor * cover_factor

        thermal_stress = 1.0 - temp_factor
        hydraulic_stress = np.clip(
            (velocity - profile.velocity_stress_threshold_ms)
            / max(profile.velocity_stress_scale_ms, 1e-9),
            0.0,
            1.0,
        )
        predation = pred_weight * (1.0 - hiding_cover) * (
            profile.predation_base_risk + profile.predation_csi_risk * (1.0 - csi)
        )
        mortality_risk = (
            1.0 - profile.base_daily_survival
            + predation
            + profile.thermal_stress_mortality * thermal_stress
            + profile.hydraulic_stress_mortality * hydraulic_stress
        )
        growth_mm = profile.max_daily_growth_mm * foraging
        data: dict[str, object] = {
            "cell_id": cells["cell_id"].astype(str).to_numpy(dtype=object),
            "area_m2": cells["area_m2"].to_numpy(dtype=float),
            "csi": csi,
            "foraging": foraging,
            "temperature_factor": temp_factor,
            "velocity_ms": velocity,
            "growth_mm": growth_mm,
            "mortality_risk": np.clip(mortality_risk, 0.0, profile.max_mortality_risk),
            "utility": (
                growth_mm * profile.utility_growth_weight
                - mortality_risk * profile.utility_mortality_weight
            ),
        }
        if "reach_id" in cells:
            data["reach_id"] = cells["reach_id"].astype(str).to_numpy(dtype=object)
        if "reach_order" in cells:
            data["reach_order"] = pd.to_numeric(cells["reach_order"], errors="coerce").to_numpy(
                dtype=float
            )
        return pd.DataFrame(data)


@dataclass(frozen=True)
class BioenergeticGrowthModel:
    """Individual length change from consumption, respiration, and activity cost."""

    def growth_mm(
        self,
        length_mm: float,
        cell_values: pd.DataFrame,
        selected_idx: int,
        profile: NativeIBMProfile,
    ) -> float:
        mass_g = float(length_to_mass_g(length_mm, profile))
        foraging = float(cell_values["foraging"].iloc[selected_idx])
        temp_factor = float(cell_values["temperature_factor"].iloc[selected_idx])
        velocity = max(float(cell_values["velocity_ms"].iloc[selected_idx]), 0.0)
        consumption_g = mass_g * profile.max_consumption_fraction * max(foraging, 0.0)
        respiration_multiplier = (
            profile.respiration_base_multiplier
            + profile.respiration_thermal_multiplier * (1.0 - temp_factor)
        )
        respiration_g = mass_g * (
            profile.respiration_fraction * respiration_multiplier
            + profile.activity_respiration_fraction * min(velocity, profile.max_activity_velocity_ms)
        )
        net_growth_g = np.clip(
            consumption_g - respiration_g,
            -profile.max_mass_loss_fraction * mass_g,
            profile.max_mass_gain_fraction * mass_g,
        )
        new_mass_g = max(mass_g + float(net_growth_g), float(profile.fry_mass_g))
        new_length_mm = float(mass_to_length_mm(new_mass_g, profile))
        return float(
            np.clip(
                new_length_mm - length_mm,
                -profile.max_daily_shrinkage_mm,
                profile.max_daily_growth_mm,
            )
        )


@dataclass(frozen=True)
class SizePriorityCellChooser:
    """Assign fish to cells by size-priority growth-risk utility."""

    growth_model: BioenergeticGrowthModel = BioenergeticGrowthModel()

    def choose_cells(
        self,
        fish: pd.DataFrame,
        cell_values: pd.DataFrame,
        profile: NativeIBMProfile,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray]:
        alive_count = len(fish)
        chosen = np.empty(alive_count, dtype=object)
        chosen_reach = np.empty(alive_count, dtype=object) if "reach_id" in cell_values else None
        growth = np.empty(alive_count, dtype=float)
        mortality = np.empty(alive_count, dtype=float)
        densities = np.zeros(len(cell_values), dtype=float)
        lengths = pd.to_numeric(fish["length_mm"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        order = np.argsort(-(lengths + rng.random(alive_count) * 1e-6))
        area = cell_values["area_m2"].to_numpy(dtype=float)
        base_utility = cell_values["utility"].to_numpy(dtype=float)
        cell_ids = cell_values["cell_id"].astype(str).to_numpy(dtype=object)
        reach_ids = (
            cell_values["reach_id"].astype(str).to_numpy(dtype=object)
            if "reach_id" in cell_values
            else None
        )
        fish_reaches = (
            fish["reach_id"].astype(str).to_numpy(dtype=object)
            if reach_ids is not None and "reach_id" in fish
            else None
        )
        mortality_by_cell = cell_values["mortality_risk"].to_numpy(dtype=float)
        carrying = np.maximum(area * profile.carrying_density_per_m2, profile.min_cell_capacity)

        for fish_idx in order:
            utility = (
                base_utility - profile.density_competition_strength * densities / carrying
            ).copy()
            if reach_ids is not None and fish_reaches is not None:
                same_reach = reach_ids == str(fish_reaches[fish_idx])
                if bool(same_reach.any()):
                    if profile.allow_cross_reach_movement:
                        utility = utility - np.where(
                            same_reach,
                            0.0,
                            float(profile.cross_reach_movement_penalty),
                        )
                    else:
                        utility = np.where(same_reach, utility, -np.inf)
            selected_idx = int(np.argmax(utility))
            densities[selected_idx] += 1.0
            chosen[fish_idx] = str(cell_ids[selected_idx])
            if chosen_reach is not None and reach_ids is not None:
                chosen_reach[fish_idx] = str(reach_ids[selected_idx])
            growth[fish_idx] = self.growth_model.growth_mm(
                float(lengths[fish_idx]),
                cell_values,
                selected_idx,
                profile,
            )
            mortality[fish_idx] = float(mortality_by_cell[selected_idx])
        return chosen, chosen_reach, growth, mortality


@dataclass(frozen=True)
class CrossReachMovementModel:
    """Ordered-adjacent cross-reach movement for mobile fish."""

    habitat_model: GrowthRiskHabitatModel = GrowthRiskHabitatModel()

    def apply(
        self,
        fish: pd.DataFrame,
        cells: pd.DataFrame,
        profile: NativeIBMProfile,
        rng: np.random.Generator,
        stochastic: bool,
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        rate = float(np.clip(profile.cross_reach_movement_rate, 0.0, 1.0))
        if rate <= 0.0:
            return fish, {}
        if "reach_id" not in fish or "reach_id" not in cells or "reach_order" not in cells:
            return fish, {}

        reach_lookup = (
            cells[["reach_id", "reach_order"]]
            .dropna(subset=["reach_order"])
            .drop_duplicates("reach_id")
            .set_index("reach_id")["reach_order"]
        )
        if reach_lookup.empty:
            return fish, {}

        if "reach_order" not in fish:
            fish["reach_order"] = fish["reach_id"].astype(str).map(reach_lookup)
        else:
            fish["reach_order"] = pd.to_numeric(fish["reach_order"], errors="coerce")
            missing_order = fish["reach_order"].isna()
            if bool(missing_order.any()):
                fish.loc[missing_order, "reach_order"] = fish.loc[
                    missing_order,
                    "reach_id",
                ].astype(str).map(reach_lookup)

        alive_idx = fish.index[fish["alive"]].to_numpy()
        if len(alive_idx) == 0:
            return fish, {}

        day_values = self.habitat_model.phase_cell_values(cells, profile, "day")
        if "reach_order" not in day_values:
            return fish, {}
        scored_values = day_values.dropna(subset=["reach_order"]).reset_index(drop=True)
        if scored_values.empty:
            return fish, {}
        best_idx = scored_values.groupby(["reach_id", "reach_order"])["utility"].idxmax()
        reach_scores = (
            scored_values.loc[best_idx, ["reach_id", "reach_order", "cell_id", "utility"]]
            .sort_values(["reach_order", "reach_id"], kind="mergesort")
            .reset_index(drop=True)
        )
        if len(reach_scores) < 2:
            return fish, {}

        min_length = float(profile.cross_reach_movement_min_length_mm)
        length_scale = max(float(profile.cross_reach_movement_length_scale_mm), 1e-9)
        max_steps = max(int(profile.cross_reach_movement_max_steps), 1)
        interior_multiplier = float(
            np.clip(profile.cross_reach_interior_movement_multiplier, 0.0, 1.0)
        )
        utility_weight = float(profile.cross_reach_habitat_utility_weight)
        upstream_bias = float(profile.cross_reach_upstream_bias)
        movement_counts: dict[str, int] = {}

        for idx in alive_idx:
            current_order_value = pd.to_numeric(
                pd.Series([fish.at[idx, "reach_order"]]),
                errors="coerce",
            ).iloc[0]
            if pd.isna(current_order_value):
                continue
            current_order = float(current_order_value)
            length = float(
                pd.to_numeric(pd.Series([fish.at[idx, "length_mm"]]), errors="coerce")
                .fillna(0.0)
                .iloc[0]
            )
            size_factor = float(np.clip((length - min_length) / length_scale, 0.0, 1.0))
            attempt_probability = rate * size_factor

            candidate = reach_scores[
                (reach_scores["reach_order"] - current_order).abs() <= float(max_steps)
            ].copy()
            if candidate.empty:
                continue
            current_rows = candidate[candidate["reach_order"] == current_order]
            if current_rows.empty:
                continue
            adjacent_count = int((candidate["reach_order"] != current_order).sum())
            if adjacent_count > 1:
                attempt_probability *= interior_multiplier
            if stochastic:
                if float(rng.random()) >= attempt_probability:
                    continue
            elif attempt_probability <= 0.0:
                continue
            candidate["migration_score"] = (
                utility_weight * candidate["utility"].astype(float)
                + upstream_bias * (current_order - candidate["reach_order"].astype(float))
            )
            selected = candidate.iloc[int(np.argmax(candidate["migration_score"].to_numpy(dtype=float)))]
            selected_order = float(selected["reach_order"])
            if selected_order == current_order:
                continue
            target_reach = str(selected["reach_id"])
            if target_reach == str(fish.at[idx, "reach_id"]):
                continue
            fish.at[idx, "reach_id"] = target_reach
            fish.at[idx, "reach_order"] = selected_order
            fish.at[idx, "cell_id"] = str(selected["cell_id"])
            movement_counts[target_reach] = movement_counts.get(target_reach, 0) + 1

        return fish, movement_counts


@dataclass(frozen=True)
class NetworkMovementModel:
    """Graph-based reach movement with optional barrier passage probabilities."""

    habitat_model: GrowthRiskHabitatModel = GrowthRiskHabitatModel()

    def _default_links(self, reach_scores: pd.DataFrame) -> pd.DataFrame:
        reaches = reach_scores[["reach_id", "reach_order"]].drop_duplicates().sort_values(
            ["reach_order", "reach_id"],
            kind="mergesort",
        )
        rows: list[dict[str, object]] = []
        records = reaches.to_dict("records")
        for left, right in pairwise(records):
            rows.append(
                {
                    "source_reach_id": str(left["reach_id"]),
                    "target_reach_id": str(right["reach_id"]),
                    "passage_probability": 1.0,
                }
            )
            rows.append(
                {
                    "source_reach_id": str(right["reach_id"]),
                    "target_reach_id": str(left["reach_id"]),
                    "passage_probability": 1.0,
                }
            )
        return pd.DataFrame.from_records(rows)

    def _normalise_links(
        self,
        cells: pd.DataFrame,
        reach_scores: pd.DataFrame,
        links: pd.DataFrame | None,
    ) -> pd.DataFrame:
        if links is not None:
            raw = links.copy()
        elif {"source_reach_id", "target_reach_id"}.issubset(cells.columns):
            link_columns = ["source_reach_id", "target_reach_id"]
            if "passage_probability" in cells:
                link_columns.append("passage_probability")
            raw = cells[link_columns].copy()
        else:
            raw = self._default_links(reach_scores)
        if raw.empty:
            return pd.DataFrame(columns=["source_reach_id", "target_reach_id", "passage_probability"])
        if "passage_probability" not in raw:
            raw["passage_probability"] = 1.0
        raw["source_reach_id"] = raw["source_reach_id"].astype(str)
        raw["target_reach_id"] = raw["target_reach_id"].astype(str)
        raw["passage_probability"] = (
            pd.to_numeric(raw["passage_probability"], errors="coerce").fillna(1.0).clip(0.0, 1.0)
        )
        return raw[["source_reach_id", "target_reach_id", "passage_probability"]]

    def apply(
        self,
        fish: pd.DataFrame,
        cells: pd.DataFrame,
        profile: NativeIBMProfile,
        rng: np.random.Generator,
        stochastic: bool,
        *,
        links: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        rate = float(np.clip(profile.cross_reach_movement_rate, 0.0, 1.0))
        if rate <= 0.0 or "reach_id" not in fish or "reach_id" not in cells:
            return fish, {}

        alive_idx = fish.index[fish["alive"]].to_numpy()
        if len(alive_idx) == 0:
            return fish, {}

        day_values = self.habitat_model.phase_cell_values(cells, profile, "day")
        if "reach_id" not in day_values:
            return fish, {}
        if "reach_order" not in day_values:
            day_values["reach_order"] = np.nan
        scored_values = day_values.reset_index(drop=True)
        best_idx = scored_values.groupby("reach_id")["utility"].idxmax()
        reach_scores = scored_values.loc[
            best_idx,
            ["reach_id", "reach_order", "cell_id", "utility"],
        ].reset_index(drop=True)
        link_table = self._normalise_links(cells, reach_scores, links)
        if link_table.empty:
            return fish, {}

        score_by_reach = reach_scores.set_index(reach_scores["reach_id"].astype(str), drop=False)
        min_length = float(profile.cross_reach_movement_min_length_mm)
        length_scale = max(float(profile.cross_reach_movement_length_scale_mm), 1e-9)
        utility_weight = float(profile.cross_reach_habitat_utility_weight)
        upstream_bias = float(profile.cross_reach_upstream_bias)
        movement_counts: dict[str, int] = {}

        for idx in alive_idx:
            current_reach = str(fish.at[idx, "reach_id"])
            candidate_links = link_table[link_table["source_reach_id"] == current_reach]
            if candidate_links.empty:
                continue
            length = float(
                pd.to_numeric(pd.Series([fish.at[idx, "length_mm"]]), errors="coerce")
                .fillna(0.0)
                .iloc[0]
            )
            size_factor = float(np.clip((length - min_length) / length_scale, 0.0, 1.0))
            candidate_rows: list[dict[str, object]] = []
            current_order = np.nan
            if current_reach in score_by_reach.index:
                current_order = float(score_by_reach.loc[current_reach, "reach_order"])
            for _, link in candidate_links.iterrows():
                target_reach = str(link["target_reach_id"])
                if target_reach not in score_by_reach.index:
                    continue
                target = score_by_reach.loc[target_reach]
                target_order = float(target["reach_order"]) if pd.notna(target["reach_order"]) else np.nan
                order_term = 0.0 if pd.isna(current_order) or pd.isna(target_order) else current_order - target_order
                candidate_rows.append(
                    {
                        "reach_id": target_reach,
                        "cell_id": str(target["cell_id"]),
                        "reach_order": target_order,
                        "passage_probability": float(link["passage_probability"]),
                        "migration_score": utility_weight * float(target["utility"])
                        + upstream_bias * order_term,
                    }
                )
            if not candidate_rows:
                continue
            candidate = pd.DataFrame.from_records(candidate_rows).sort_values(
                ["migration_score", "reach_id"],
                ascending=[False, True],
                kind="mergesort",
            )
            selected = candidate.iloc[0]
            attempt_probability = rate * size_factor * float(selected["passage_probability"])
            if stochastic:
                if float(rng.random()) >= attempt_probability:
                    continue
            elif attempt_probability <= 0.0:
                continue
            target_reach = str(selected["reach_id"])
            fish.at[idx, "reach_id"] = target_reach
            fish.at[idx, "cell_id"] = str(selected["cell_id"])
            if pd.notna(selected["reach_order"]):
                fish.at[idx, "reach_order"] = float(selected["reach_order"])
            movement_counts[target_reach] = movement_counts.get(target_reach, 0) + 1

        return fish, movement_counts


@dataclass(frozen=True)
class CalibratedReddPlacementModel:
    """Redd placement scoring with optional hydraulic survival terms."""

    use_hydraulic_survival: bool = False

    def score_cells(self, cells: pd.DataFrame, profile: NativeIBMProfile) -> pd.DataFrame:
        score = cells["spawning_cover"].to_numpy(dtype=float) * profile.spawning_cover_weight
        score += cells["csi"].to_numpy(dtype=float) * profile.spawning_csi_weight
        if "redd_placement_prior" in cells:
            score += pd.to_numeric(cells["redd_placement_prior"], errors="coerce").fillna(0.0).to_numpy(
                dtype=float
            )
        if self.use_hydraulic_survival and {"depth_m", "velocity_ms"}.issubset(cells.columns):
            depth = pd.to_numeric(cells["depth_m"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
            velocity = (
                pd.to_numeric(cells["velocity_ms"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
            )
            depth_ok = (depth >= float(profile.redd_min_depth_m)).astype(float)
            scour_ok = (velocity <= float(profile.redd_scour_velocity_ms)).astype(float)
            score += 0.5 * depth_ok + 0.5 * scour_ok
        scored = cells.copy()
        scored["redd_placement_score"] = score
        return scored

    def select_cell(
        self,
        cells: pd.DataFrame,
        profile: NativeIBMProfile,
        rng: np.random.Generator | None = None,
        *,
        stochastic: bool = False,
        reach_id: str | None = None,
    ) -> str:
        candidates = cells
        if reach_id and "reach_id" in cells:
            same_reach = cells[cells["reach_id"].astype(str) == str(reach_id)]
            if not same_reach.empty:
                candidates = same_reach
        scored = self.score_cells(candidates, profile)
        scores = np.maximum(scored["redd_placement_score"].to_numpy(dtype=float), 0.0)
        if stochastic and rng is not None and float(scores.sum()) > 0.0:
            selected_idx = int(rng.choice(np.arange(len(scored)), p=scores / float(scores.sum())))
        else:
            selected_idx = int(np.argmax(scores))
        return str(scored["cell_id"].iloc[selected_idx])


@dataclass(frozen=True)
class ReddRecruitmentModel:
    """Spawner-to-redd and redd-to-recruit state transitions."""

    placement_model: CalibratedReddPlacementModel = field(
        default_factory=CalibratedReddPlacementModel
    )

    def fallback_spawning_cell(self, cells: pd.DataFrame, profile: NativeIBMProfile) -> str:
        return self.placement_model.select_cell(cells, profile)

    def spawn_redds(
        self,
        fish: pd.DataFrame,
        redds: pd.DataFrame,
        cells: pd.DataFrame,
        *,
        sim_day: int,
        spawn_season: int | None,
        next_redd_id: int,
        profile: NativeIBMProfile,
        rng: np.random.Generator,
        stochastic: bool,
    ) -> tuple[pd.DataFrame, pd.DataFrame, int, int, int]:
        if spawn_season is None:
            return fish, redds, next_redd_id, 0, 0
        alive = fish["alive"]
        spawned_season = pd.to_numeric(fish["spawned_season"], errors="coerce").fillna(-1).astype(
            int
        )
        mature = (
            alive
            & (fish["length_mm"] >= profile.maturity_length_mm)
            & (spawned_season != int(spawn_season))
        )
        n_spawners = int(mature.sum())
        if n_spawners == 0:
            return fish, redds, next_redd_id, 0, 0

        spawner_lengths = fish.loc[mature, "length_mm"].to_numpy(dtype=float)
        reference_length = max(float(profile.fecundity_reference_length_mm), 1e-9)
        length_factor = np.clip(spawner_lengths / reference_length, 0.0, None) ** float(
            profile.fecundity_length_exponent
        )
        expected_eggs = profile.spawner_female_fraction * profile.fecundity_per_female * length_factor
        spawner_cols = ["cell_id"]
        if "reach_id" in fish:
            spawner_cols.append("reach_id")
        # Preserve the spawner's own species so each redd is labelled with
        # the parent's species, not the profile's default. 2026-05-28
        # multi-species follow-up — without this, ExampleB redds all
        # tagged "rainbow_trout" regardless of cohort.
        if "species" in fish:
            spawner_cols.append("species")
        mature_fish = fish.loc[mature, spawner_cols].copy()
        mature_fish["expected_eggs"] = expected_eggs
        valid_cells = set(cells["cell_id"].astype(str))
        fallback = self.fallback_spawning_cell(cells, profile)
        mature_fish["cell_id"] = mature_fish["cell_id"].astype(str)
        mature_fish.loc[~mature_fish["cell_id"].isin(valid_cells), "cell_id"] = fallback
        cell_reach = (
            cells.drop_duplicates("cell_id")
            .set_index(cells["cell_id"].astype(str))["reach_id"]
            .astype(str)
            if "reach_id" in cells
            else pd.Series(dtype=str)
        )
        if "reach_id" not in mature_fish:
            mature_fish["reach_id"] = mature_fish["cell_id"].map(cell_reach).fillna("")
        else:
            mature_fish["reach_id"] = mature_fish["reach_id"].astype(str)
            missing_reach = mature_fish["reach_id"].eq("") | mature_fish["reach_id"].eq("<NA>")
            mature_fish.loc[missing_reach, "reach_id"] = mature_fish.loc[
                missing_reach, "cell_id"
            ].map(cell_reach).fillna("")

        redd_rows: list[dict[str, object]] = []
        total_eggs = 0
        for _, spawner in mature_fish.sort_values(["reach_id", "cell_id"], kind="mergesort").iterrows():
            expected = float(spawner["expected_eggs"])
            egg_count = int(rng.poisson(expected)) if stochastic else int(round(expected))
            if egg_count <= 0:
                continue
            total_eggs += egg_count
            spawner_species = str(spawner["species"]) if "species" in mature_fish.columns else profile.species
            redd_rows.append(
                {
                    "redd_id": next_redd_id,
                    "species": spawner_species,
                    "cell_id": str(spawner["cell_id"]),
                    "reach_id": str(spawner["reach_id"]),
                    "spawn_day": int(sim_day),
                    "spawn_season": int(spawn_season),
                    "age_days": 0,
                    "eggs_initial": egg_count,
                    "eggs_remaining": egg_count,
                    "development_degree_days": 0.0,
                    "incubation_target_degree_days": float(profile.egg_incubation_degree_days),
                    "alive": True,
                    "emerged": False,
                    "emergence_day": pd.NA,
                }
            )
            next_redd_id += 1

        fish.loc[mature, "spawned_season"] = int(spawn_season)
        if redd_rows:
            redds = pd.concat([redds, pd.DataFrame.from_records(redd_rows)], ignore_index=True)
        return fish, redds, next_redd_id, n_spawners, total_eggs

    def update_redds(
        self,
        redds: pd.DataFrame,
        cells: pd.DataFrame,
        *,
        sim_day: int,
        next_fish_id: int,
        profile: NativeIBMProfile,
        rng: np.random.Generator,
        stochastic: bool,
    ) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
        if redds.empty:
            return redds, pd.DataFrame(), next_fish_id, 0
        active = redds["alive"].astype(bool) & ~redds["emerged"].astype(bool)
        active_idx = redds.index[active].to_numpy()
        if len(active_idx) == 0:
            return redds, pd.DataFrame(), next_fish_id, 0

        cell_lookup = cells.set_index(cells["cell_id"].astype(str), drop=False)
        recruit_frames: list[pd.DataFrame] = []
        total_recruits = 0
        for idx in active_idx:
            redd = redds.loc[idx]
            cell_id = str(redd["cell_id"])
            if cell_id in cell_lookup.index:
                cell = cell_lookup.loc[cell_id]
                if isinstance(cell, pd.DataFrame):
                    cell = cell.iloc[0]
                temperature_c = float(cell["temperature_c"])
                depth_m = float(cell["depth_m"]) if pd.notna(cell["depth_m"]) else 0.0
                velocity_ms = float(cell["velocity_ms"]) if pd.notna(cell["velocity_ms"]) else 0.0
            else:
                temperature_c = float(cells["temperature_c"].mean())
                depth_m = 0.0
                velocity_ms = 0.0

            eggs = int(redd["eggs_remaining"])
            survival = float(profile.redd_base_daily_survival)
            if depth_m < profile.redd_min_depth_m:
                survival *= 1.0 - float(profile.redd_dewatering_mortality)
            if velocity_ms > profile.redd_scour_velocity_ms:
                survival *= 1.0 - float(profile.redd_scour_mortality)
            survival = min(max(survival, 0.0), 1.0)
            eggs = int(rng.binomial(eggs, survival)) if stochastic else int(round(eggs * survival))
            development = float(redd["development_degree_days"]) + max(temperature_c, 0.0)

            redds.at[idx, "age_days"] = int(redd["age_days"]) + 1
            redds.at[idx, "eggs_remaining"] = eggs
            redds.at[idx, "development_degree_days"] = development
            if eggs <= 0:
                redds.at[idx, "alive"] = False
                continue
            target = float(redd["incubation_target_degree_days"])
            if development < target:
                continue

            expected_recruits = eggs * float(profile.egg_to_fry_survival)
            recruits = (
                int(rng.binomial(eggs, min(max(profile.egg_to_fry_survival, 0.0), 1.0)))
                if stochastic
                else int(round(expected_recruits))
            )
            redds.at[idx, "alive"] = False
            redds.at[idx, "emerged"] = True
            redds.at[idx, "emergence_day"] = int(sim_day)
            redds.at[idx, "eggs_remaining"] = 0
            if recruits <= 0:
                continue
            recruit_frames.append(
                pd.DataFrame(
                    {
                        "fish_id": np.arange(next_fish_id, next_fish_id + recruits, dtype=int),
                        "species": profile.species,
                        "age_days": np.zeros(recruits, dtype=int),
                        "length_mm": np.full(recruits, profile.fry_length_mm),
                        "mass_g": np.full(recruits, profile.fry_mass_g),
                        "cell_id": np.full(recruits, cell_id, dtype=object),
                        "reach_id": np.full(recruits, str(redd.get("reach_id", "")), dtype=object),
                        "alive": np.ones(recruits, dtype=bool),
                        "spawned_season": np.full(recruits, -1, dtype=int),
                        "origin_redd_id": np.full(recruits, int(redd["redd_id"]), dtype=int),
                    }
                )
            )
            next_fish_id += recruits
            total_recruits += recruits
        recruits_df = pd.concat(recruit_frames, ignore_index=True) if recruit_frames else pd.DataFrame()
        return redds, recruits_df, next_fish_id, total_recruits


__all__ = [
    "BioenergeticGrowthModel",
    "CalibratedReddPlacementModel",
    "CrossReachMovementModel",
    "GrowthRiskHabitatModel",
    "NativeIBMProfile",
    "NetworkMovementModel",
    "ReddRecruitmentModel",
    "SizePriorityCellChooser",
    "length_to_mass_g",
    "mass_to_length_mm",
    "triangular_factor",
]
