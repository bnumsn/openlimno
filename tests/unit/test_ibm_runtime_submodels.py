from __future__ import annotations

import numpy as np
import pandas as pd

from openlimno.ibm import (
    BioenergeticGrowthModel,
    CalibratedReddPlacementModel,
    CrossReachMovementModel,
    GrowthRiskHabitatModel,
    NetworkMovementModel,
    ReddRecruitmentModel,
    SizePriorityCellChooser,
    SpeciesProfile,
)


def _runtime_cells() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "cell_id": ["safe-low", "risky-high"],
            "area_m2": [20.0, 20.0],
            "depth_m": [0.5, 0.7],
            "velocity_ms": [0.2, 1.7],
            "csi": [0.45, 0.95],
            "temperature_c": [12.0, 24.0],
            "turbidity_ntu": [0.0, 80.0],
            "hiding_cover": [0.9, 0.0],
            "feeding_cover": [0.2, 0.8],
        }
    )


def _redd_columns() -> list[str]:
    return [
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


def test_growth_risk_habitat_model_scores_foraging_and_mortality() -> None:
    model = GrowthRiskHabitatModel()
    profile = SpeciesProfile(
        base_daily_survival=0.99,
        predation_base_risk=0.01,
        predation_csi_risk=0.02,
        thermal_stress_mortality=0.1,
        hydraulic_stress_mortality=0.1,
    )
    cells = _runtime_cells()
    cells.loc[1, "temperature_c"] = 12.0
    cells.loc[1, "turbidity_ntu"] = 0.0

    values = model.phase_cell_values(cells, profile, "day").set_index("cell_id")

    assert values.loc["risky-high", "foraging"] > values.loc["safe-low", "foraging"]
    assert values.loc["risky-high", "mortality_risk"] > values.loc["safe-low", "mortality_risk"]
    assert set(values.columns) >= {"foraging", "growth_mm", "mortality_risk", "utility"}


def test_bioenergetic_growth_model_responds_to_foraging_and_cost() -> None:
    growth = BioenergeticGrowthModel()
    profile = SpeciesProfile(
        max_consumption_fraction=0.04,
        respiration_fraction=0.001,
        activity_respiration_fraction=0.001,
        max_daily_growth_mm=5.0,
    )
    values = pd.DataFrame(
        {
            "foraging": [0.0, 1.0],
            "temperature_factor": [1.0, 1.0],
            "velocity_ms": [0.1, 0.1],
        }
    )

    low = growth.growth_mm(100.0, values, 0, profile)
    high = growth.growth_mm(100.0, values, 1, profile)

    assert high > low
    assert high <= profile.max_daily_growth_mm


def test_size_priority_cell_chooser_gates_reach_selection() -> None:
    chooser = SizePriorityCellChooser()
    rng = np.random.default_rng(5)
    fish = pd.DataFrame(
        {
            "fish_id": [0],
            "length_mm": [150.0],
            "reach_id": ["r1"],
        }
    )
    values = pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "cell_id": ["r1-cell", "r2-cell"],
            "area_m2": [20.0, 20.0],
            "foraging": [0.1, 1.0],
            "temperature_factor": [1.0, 1.0],
            "velocity_ms": [0.1, 0.1],
            "mortality_risk": [0.0, 0.0],
            "utility": [0.1, 10.0],
        }
    )
    resident = SpeciesProfile(
        density_competition_strength=0.0,
        allow_cross_reach_movement=False,
    )
    mobile = SpeciesProfile(
        density_competition_strength=0.0,
        allow_cross_reach_movement=True,
        cross_reach_movement_penalty=0.0,
    )

    chosen, chosen_reach, _, _ = chooser.choose_cells(fish, values, resident, rng)
    assert list(chosen) == ["r1-cell"]
    assert chosen_reach is not None
    assert list(chosen_reach) == ["r1"]

    chosen, chosen_reach, _, _ = chooser.choose_cells(fish, values, mobile, rng)
    assert list(chosen) == ["r2-cell"]
    assert chosen_reach is not None
    assert list(chosen_reach) == ["r2"]


def test_size_priority_cell_chooser_prefers_larger_fish_under_capacity() -> None:
    chooser = SizePriorityCellChooser()
    profile = SpeciesProfile(
        carrying_density_per_m2=0.05,
        density_competition_strength=100.0,
    )
    fish = pd.DataFrame(
        {
            "fish_id": [0, 1],
            "length_mm": [90.0, 220.0],
        }
    )
    values = pd.DataFrame(
        {
            "cell_id": ["best", "second"],
            "area_m2": [1.0, 1.0],
            "foraging": [1.0, 0.8],
            "temperature_factor": [1.0, 1.0],
            "velocity_ms": [0.1, 0.1],
            "mortality_risk": [0.0, 0.0],
            "utility": [10.0, 9.0],
        }
    )

    chosen, _, _, _ = chooser.choose_cells(fish, values, profile, np.random.default_rng(1))

    assert list(chosen) == ["second", "best"]


def test_cross_reach_movement_model_moves_to_best_adjacent_reach() -> None:
    model = CrossReachMovementModel()
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "reach_order": [1, 2],
            "cell_id": ["r1-cell", "r2-cell"],
            "area_m2": [20.0, 20.0],
            "depth_m": [0.4, 0.5],
            "velocity_ms": [0.2, 0.2],
            "csi": [0.2, 1.0],
            "temperature_c": [12.0, 12.0],
            "turbidity_ntu": [0.0, 0.0],
            "hiding_cover": [1.0, 1.0],
            "feeding_cover": [0.2, 1.0],
        }
    )
    fish = pd.DataFrame(
        {
            "fish_id": [1],
            "length_mm": [200.0],
            "cell_id": ["r1-cell"],
            "reach_id": ["r1"],
            "alive": [True],
        }
    )
    profile = SpeciesProfile(
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
        cross_reach_movement_rate=1.0,
        cross_reach_movement_min_length_mm=0.0,
        cross_reach_movement_length_scale_mm=1.0,
        cross_reach_movement_max_steps=1,
        cross_reach_habitat_utility_weight=1.0,
    )

    moved, counts = model.apply(fish, cells, profile, np.random.default_rng(10), stochastic=False)

    assert moved.loc[0, "reach_id"] == "r2"
    assert moved.loc[0, "reach_order"] == 2.0
    assert moved.loc[0, "cell_id"] == "r2-cell"
    assert counts == {"r2": 1}


def test_network_movement_model_respects_barrier_probability() -> None:
    model = NetworkMovementModel()
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "reach_order": [1, 2],
            "cell_id": ["r1-cell", "r2-cell"],
            "area_m2": [20.0, 20.0],
            "depth_m": [0.4, 0.5],
            "velocity_ms": [0.2, 0.2],
            "csi": [0.1, 1.0],
            "temperature_c": [12.0, 12.0],
            "turbidity_ntu": [0.0, 0.0],
            "hiding_cover": [1.0, 1.0],
            "feeding_cover": [0.1, 1.0],
        }
    )
    fish = pd.DataFrame(
        {
            "fish_id": [1],
            "length_mm": [200.0],
            "cell_id": ["r1-cell"],
            "reach_id": ["r1"],
            "alive": [True],
        }
    )
    profile = SpeciesProfile(
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        cross_reach_movement_rate=1.0,
        cross_reach_movement_min_length_mm=0.0,
        cross_reach_movement_length_scale_mm=1.0,
    )
    links = pd.DataFrame(
        {
            "source_reach_id": ["r1", "r1"],
            "target_reach_id": ["r2", "r1"],
            "passage_probability": [0.0, 1.0],
        }
    )

    blocked, counts = model.apply(
        fish.copy(),
        cells,
        profile,
        np.random.default_rng(13),
        stochastic=False,
        links=links,
    )
    assert blocked.loc[0, "reach_id"] == "r1"
    assert counts == {}

    links.loc[0, "passage_probability"] = 1.0
    moved, counts = model.apply(
        fish.copy(),
        cells,
        profile,
        np.random.default_rng(13),
        stochastic=False,
        links=links,
    )
    assert moved.loc[0, "reach_id"] == "r2"
    assert counts == {"r2": 1}


def test_calibrated_redd_placement_uses_hydraulic_survival_terms() -> None:
    model = CalibratedReddPlacementModel(use_hydraulic_survival=True)
    cells = pd.DataFrame(
        {
            "cell_id": ["dry-prior", "wet-safe"],
            "reach_id": ["r1", "r1"],
            "spawning_cover": [1.0, 0.8],
            "csi": [1.0, 0.8],
            "redd_placement_prior": [0.0, 0.0],
            "depth_m": [0.01, 0.4],
            "velocity_ms": [2.5, 0.3],
        }
    )
    profile = SpeciesProfile(
        spawning_cover_weight=0.2,
        spawning_csi_weight=0.2,
        redd_min_depth_m=0.05,
        redd_scour_velocity_ms=1.0,
    )

    assert model.select_cell(cells, profile, reach_id="r1") == "wet-safe"


def test_redd_recruitment_model_spawns_redds_from_mature_fish() -> None:
    model = ReddRecruitmentModel()
    fish = pd.DataFrame(
        {
            "fish_id": [1],
            "length_mm": [150.0],
            "cell_id": ["missing-cell"],
            "reach_id": ["r1"],
            "alive": [True],
            "spawned_season": [-1],
        }
    )
    cells = pd.DataFrame(
        {
            "cell_id": ["spawn-cell", "low-cell"],
            "reach_id": ["r1", "r1"],
            "spawning_cover": [1.0, 0.1],
            "csi": [1.0, 0.1],
        }
    )
    profile = SpeciesProfile(
        maturity_length_mm=100.0,
        spawner_female_fraction=1.0,
        fecundity_per_female=20.0,
        fecundity_length_exponent=0.0,
        egg_incubation_degree_days=10.0,
    )

    out_fish, redds, next_redd_id, n_spawners, n_eggs = model.spawn_redds(
        fish,
        pd.DataFrame(columns=_redd_columns()),
        cells,
        sim_day=5,
        spawn_season=0,
        next_redd_id=100,
        profile=profile,
        rng=np.random.default_rng(11),
        stochastic=False,
    )

    assert n_spawners == 1
    assert n_eggs == 20
    assert next_redd_id == 101
    assert out_fish.loc[0, "spawned_season"] == 0
    assert redds.loc[0, "redd_id"] == 100
    assert redds.loc[0, "cell_id"] == "spawn-cell"
    assert redds.loc[0, "eggs_initial"] == 20


def test_redd_recruitment_model_emerges_fry_after_degree_days() -> None:
    model = ReddRecruitmentModel()
    redds = pd.DataFrame(
        [
            {
                "redd_id": 7,
                "species": "rainbow_trout",
                "cell_id": "spawn-cell",
                "reach_id": "r1",
                "spawn_day": 0,
                "spawn_season": 0,
                "age_days": 2,
                "eggs_initial": 10,
                "eggs_remaining": 10,
                "development_degree_days": 9.0,
                "incubation_target_degree_days": 10.0,
                "alive": True,
                "emerged": False,
                "emergence_day": pd.NA,
            }
        ],
        columns=_redd_columns(),
    )
    cells = pd.DataFrame(
        {
            "cell_id": ["spawn-cell"],
            "temperature_c": [2.0],
            "depth_m": [0.4],
            "velocity_ms": [0.2],
        }
    )
    profile = SpeciesProfile(
        egg_to_fry_survival=0.5,
        egg_incubation_degree_days=10.0,
        redd_base_daily_survival=1.0,
        fry_length_mm=30.0,
        fry_mass_g=0.3,
    )

    updated, recruits, next_fish_id, n_recruits = model.update_redds(
        redds,
        cells,
        sim_day=3,
        next_fish_id=1000,
        profile=profile,
        rng=np.random.default_rng(12),
        stochastic=False,
    )

    assert n_recruits == 5
    assert next_fish_id == 1005
    assert not bool(updated.loc[0, "alive"])
    assert bool(updated.loc[0, "emerged"])
    assert updated.loc[0, "emergence_day"] == 3
    assert len(recruits) == 5
    assert list(recruits["fish_id"]) == [1000, 1001, 1002, 1003, 1004]
    assert set(recruits["origin_redd_id"]) == {7}


def test_runtime_submodel_exports_are_available_from_package() -> None:
    assert GrowthRiskHabitatModel().phase_cell_values
    assert BioenergeticGrowthModel().growth_mm
    assert SizePriorityCellChooser().choose_cells
    assert CrossReachMovementModel().apply
    assert NetworkMovementModel().apply
    assert CalibratedReddPlacementModel().score_cells
    assert ReddRecruitmentModel().update_redds
    assert SpeciesProfile().species == "rainbow_trout"
