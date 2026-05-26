from __future__ import annotations

import json

import pandas as pd
import pytest

from openlimno.ibm import (
    NativeIBMConfig,
    SpeciesProfile,
    build_initial_population,
    run_native_ibm,
    write_native_ibm_result,
)


def _cells() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cell_id": [10, 20, 30],
            "area_m2": [25.0, 30.0, 20.0],
            "depth_m": [0.2, 0.7, 1.6],
            "velocity_ms": [0.1, 0.35, 1.1],
            "csi": [0.25, 0.95, 0.35],
            "temperature_c": [12.0, 12.0, 12.0],
            "hiding_cover": [0.1, 0.8, 0.2],
            "feeding_cover": [0.1, 0.6, 0.2],
        }
    )


def test_native_ibm_runs_daily_population_model() -> None:
    pop = build_initial_population(n=12, species="rainbow_trout", length_mm=130.0)
    result = run_native_ibm(
        _cells(),
        pop,
        config=NativeIBMConfig(days=7, seed=123, scenario_id="base", reach_id="r1"),
    )

    assert list(result.population_summary["day"]) == list(range(8))
    assert result.population_summary["abundance"].iloc[-1] >= 0
    assert set(result.final_individuals.columns) >= {
        "fish_id",
        "length_mm",
        "mass_g",
        "alive",
        "cell_id",
    }
    assert not result.cell_use.empty
    assert set(result.cell_use["phase"]).issubset({"dawn", "day", "dusk", "night"})


def test_native_ibm_prefers_high_value_habitat_cell() -> None:
    pop = build_initial_population(n=40, length_mm=100.0)
    result = run_native_ibm(
        _cells(),
        pop,
        config=NativeIBMConfig(days=2, seed=7, stochastic=False),
    )
    day_cell_use = result.cell_use[result.cell_use["phase"] == "day"]
    use_by_cell = day_cell_use.groupby("cell_id")["n_fish"].sum()

    assert int(use_by_cell.idxmax()) == 20


def test_native_ibm_accepts_string_cell_ids() -> None:
    cells = _cells()
    cells["cell_id"] = ["pool-a", "riffle-b", "run-c"]
    pop = build_initial_population(n=20, length_mm=100.0)

    result = run_native_ibm(
        cells,
        pop,
        config=NativeIBMConfig(days=2, seed=7, stochastic=False),
    )
    day_cell_use = result.cell_use[result.cell_use["phase"] == "day"]
    use_by_cell = day_cell_use.groupby("cell_id")["n_fish"].sum()

    assert str(use_by_cell.idxmax()) == "riffle-b"
    assert set(result.final_individuals["cell_id"]) <= {"", "pool-a", "riffle-b", "run-c"}


def test_native_ibm_uses_time_indexed_habitat_slices() -> None:
    day1 = _cells().iloc[:2].copy()
    day1["cell_id"] = ["a", "b"]
    day1["csi"] = [0.95, 0.1]
    day1["time_index"] = 0
    day2 = _cells().iloc[:2].copy()
    day2["cell_id"] = ["a", "b"]
    day2["csi"] = [0.1, 0.95]
    day2["time_index"] = 1
    cells = pd.concat([day1, day2], ignore_index=True)
    pop = build_initial_population(n=20, length_mm=100.0)

    result = run_native_ibm(
        cells,
        pop,
        config=NativeIBMConfig(days=2, seed=7, stochastic=False),
    )

    day_use = result.cell_use[result.cell_use["phase"] == "day"]
    day1_use = day_use[day_use["day"] == 1].groupby("cell_id")["n_fish"].sum()
    day2_use = day_use[day_use["day"] == 2].groupby("cell_id")["n_fish"].sum()
    assert str(day1_use.idxmax()) == "a"
    assert str(day2_use.idxmax()) == "b"


def test_native_ibm_injects_scheduled_population_arrivals() -> None:
    initial = build_initial_population(n=0, species="chinook")
    scheduled = build_initial_population(n=3, species="chinook", length_mm=620.0)
    scheduled["arrival_day"] = [1, 2, 2]
    scheduled["reach_id"] = "r1"

    result = run_native_ibm(
        _cells(),
        initial,
        scheduled_population=scheduled,
        config=NativeIBMConfig(days=2, reach_id="r1", stochastic=False),
    )

    summary = result.population_summary.set_index("day")
    assert int(summary.loc[0, "abundance"]) == 0
    assert int(summary.loc[1, "abundance"]) == 1
    assert int(summary.loc[2, "abundance"]) == 3
    arrivals = result.events[result.events["event"] == "arrival"]
    assert int(arrivals["n"].sum()) == 3


def test_native_ibm_larger_fish_get_priority_in_cell_competition() -> None:
    cells = pd.DataFrame(
        {
            "cell_id": ["best", "second"],
            "area_m2": [1.0, 1.0],
            "depth_m": [0.7, 0.65],
            "velocity_ms": [0.35, 0.36],
            "csi": [0.95, 0.90],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [0.8, 0.8],
            "feeding_cover": [0.8, 0.8],
        }
    )
    pop = build_initial_population(n=2, length_mm=90.0)
    pop.loc[1, "length_mm"] = 220.0
    pop["mass_g"] = [1.0, 10.0]
    profile = SpeciesProfile(carrying_density_per_m2=0.01)

    result = run_native_ibm(
        cells,
        pop,
        profile=profile,
        config=NativeIBMConfig(days=1, seed=7, stochastic=False),
    )

    final = result.final_individuals.set_index("fish_id")
    assert final.loc[1, "cell_id"] == "best"
    assert final.loc[0, "cell_id"] == "second"


def test_native_ibm_density_competition_strength_controls_cell_packing() -> None:
    cells = pd.DataFrame(
        {
            "cell_id": ["best", "second"],
            "area_m2": [1.0, 1.0],
            "depth_m": [0.7, 0.7],
            "velocity_ms": [0.35, 0.35],
            "csi": [0.95, 0.94],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [1.0, 1.0],
            "feeding_cover": [1.0, 1.0],
        }
    )
    pop = build_initial_population(n=6, length_mm=100.0)
    no_competition = SpeciesProfile(
        carrying_density_per_m2=1.0,
        density_competition_strength=0.0,
    )
    strong_competition = SpeciesProfile(
        carrying_density_per_m2=1.0,
        density_competition_strength=10.0,
    )

    packed = run_native_ibm(
        cells,
        pop,
        profile=no_competition,
        config=NativeIBMConfig(days=1, seed=7, stochastic=False),
    )
    distributed = run_native_ibm(
        cells,
        pop,
        profile=strong_competition,
        config=NativeIBMConfig(days=1, seed=7, stochastic=False),
    )

    packed_use = packed.cell_use[packed.cell_use["phase"] == "day"].set_index("cell_id")
    distributed_use = distributed.cell_use[distributed.cell_use["phase"] == "day"].set_index(
        "cell_id"
    )
    assert int(packed_use.loc["best", "n_fish"]) == 6
    assert int(distributed_use.loc["best", "n_fish"]) < 6
    assert int(distributed_use.loc["second", "n_fish"]) > 0


def test_native_ibm_tracks_reach_state_and_gates_cross_reach_movement() -> None:
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "cell_id": ["r1-best", "r2-best"],
            "area_m2": [20.0, 20.0],
            "depth_m": [0.7, 0.7],
            "velocity_ms": [0.35, 0.35],
            "csi": [0.2, 1.0],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [1.0, 1.0],
            "feeding_cover": [1.0, 1.0],
        }
    )
    pop = build_initial_population(n=2, length_mm=100.0)
    pop["reach_id"] = ["r1", "r2"]
    no_mortality = SpeciesProfile(
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
        density_competition_strength=0.0,
    )

    resident = run_native_ibm(
        cells,
        pop,
        profile=no_mortality,
        config=NativeIBMConfig(days=1, stochastic=False, light_phases=("day",)),
    )

    day1 = resident.population_summary[resident.population_summary["day"] == 1]
    assert dict(zip(day1["reach_id"], day1["abundance"], strict=True)) == {"r1": 1, "r2": 1}
    assert set(resident.final_individuals["reach_id"]) == {"r1", "r2"}

    mobile_profile = SpeciesProfile(
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
        density_competition_strength=0.0,
        allow_cross_reach_movement=True,
        cross_reach_movement_penalty=0.0,
    )
    mobile_pop = build_initial_population(n=1, length_mm=100.0)
    mobile_pop["reach_id"] = ["r1"]

    mobile = run_native_ibm(
        cells,
        mobile_pop,
        profile=mobile_profile,
        config=NativeIBMConfig(days=1, stochastic=False, light_phases=("day",)),
    )

    assert mobile.final_individuals["reach_id"].iloc[0] == "r2"


def test_native_ibm_maps_initial_cell_ids_to_reaches() -> None:
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "reach_order": [1, 2],
            "cell_id": ["r1-cell", "r2-cell"],
            "area_m2": [20.0, 20.0],
            "depth_m": [0.7, 0.7],
            "velocity_ms": [0.35, 0.35],
            "csi": [1.0, 1.0],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [1.0, 1.0],
            "feeding_cover": [1.0, 1.0],
        }
    )
    pop = build_initial_population(n=2, length_mm=100.0)
    pop["cell_id"] = ["r1-cell", "r2-cell"]

    result = run_native_ibm(
        cells,
        pop,
        config=NativeIBMConfig(days=0, stochastic=False, reach_id="network"),
    )

    day0 = result.population_summary[result.population_summary["day"] == 0]
    assert dict(zip(day0["reach_id"], day0["abundance"], strict=True)) == {"r1": 1, "r2": 1}
    assert dict(zip(day0["reach_id"], day0["survival_rate"], strict=True)) == {"r1": 1.0, "r2": 1.0}
    assert dict(
        zip(result.final_individuals["cell_id"], result.final_individuals["reach_id"], strict=True)
    ) == {
        "r1-cell": "r1",
        "r2-cell": "r2",
    }
    assert dict(
        zip(
            result.final_individuals["cell_id"],
            result.final_individuals["reach_order"],
            strict=True,
        )
    ) == {
        "r1-cell": 1,
        "r2-cell": 2,
    }


def test_native_ibm_can_move_fish_to_adjacent_ordered_reaches() -> None:
    cells = pd.DataFrame(
        {
            "reach_id": ["upstream", "middle", "downstream"],
            "reach_order": [0, 1, 2],
            "cell_id": ["up-cell", "mid-cell", "down-cell"],
            "area_m2": [50.0, 50.0, 50.0],
            "depth_m": [0.7, 0.7, 0.7],
            "velocity_ms": [0.35, 0.35, 0.35],
            "csi": [0.8, 0.8, 0.8],
            "temperature_c": [12.0, 12.0, 12.0],
            "hiding_cover": [1.0, 1.0, 1.0],
            "feeding_cover": [1.0, 1.0, 1.0],
        }
    )
    pop = build_initial_population(n=3, length_mm=150.0)
    pop["reach_id"] = ["upstream", "middle", "downstream"]
    pop["reach_order"] = [0, 1, 2]
    profile = SpeciesProfile(
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
        density_competition_strength=0.0,
        cross_reach_movement_rate=1.0,
        cross_reach_movement_min_length_mm=0.0,
        cross_reach_movement_length_scale_mm=1.0,
        cross_reach_movement_max_steps=1,
        cross_reach_upstream_bias=5.0,
        cross_reach_habitat_utility_weight=0.0,
    )

    result = run_native_ibm(
        cells,
        pop,
        profile=profile,
        config=NativeIBMConfig(days=1, stochastic=False, light_phases=("day",)),
    )

    day1 = result.population_summary[result.population_summary["day"] == 1]
    assert dict(zip(day1["reach_id"], day1["abundance"], strict=True)) == {
        "downstream": 0,
        "middle": 1,
        "upstream": 2,
    }
    assert set(result.events["event"]) == {"movement"}


def test_native_ibm_records_mortality_events_by_reach() -> None:
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "cell_id": ["r1-cell", "r2-cell"],
            "area_m2": [20.0, 20.0],
            "depth_m": [0.7, 0.7],
            "velocity_ms": [0.35, 0.35],
            "csi": [1.0, 1.0],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [1.0, 1.0],
            "feeding_cover": [1.0, 1.0],
        }
    )
    pop = build_initial_population(n=2, length_mm=100.0)
    pop["reach_id"] = ["r1", "r2"]
    profile = SpeciesProfile(
        base_daily_survival=0.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
        density_competition_strength=0.0,
    )

    result = run_native_ibm(
        cells,
        pop,
        profile=profile,
        config=NativeIBMConfig(days=1, stochastic=False, light_phases=("day",)),
    )

    mortality = result.events[result.events["event"] == "mortality"]
    assert dict(zip(mortality["reach_id"], mortality["n"], strict=True)) == {"r1": 1, "r2": 1}


def test_native_ibm_records_spawning_events_by_reach() -> None:
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r2"],
            "cell_id": ["r1-cell", "r2-cell"],
            "area_m2": [20.0, 20.0],
            "depth_m": [0.7, 0.7],
            "velocity_ms": [0.35, 0.35],
            "csi": [1.0, 1.0],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [1.0, 1.0],
            "feeding_cover": [1.0, 1.0],
            "spawning_cover": [1.0, 1.0],
        }
    )
    pop = build_initial_population(n=2, length_mm=180.0)
    pop["reach_id"] = ["r1", "r2"]
    pop["cell_id"] = ["r1-cell", "r2-cell"]
    profile = SpeciesProfile(
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
        density_competition_strength=0.0,
        spawn_start_day=1,
        spawn_end_day=1,
        fecundity_per_female=10.0,
        egg_to_fry_survival=0.0,
    )

    result = run_native_ibm(
        cells,
        pop,
        profile=profile,
        config=NativeIBMConfig(days=1, stochastic=False, light_phases=("day",)),
    )

    spawning = result.events[result.events["event"] == "spawning"]
    assert dict(zip(spawning["reach_id"], spawning["n"], strict=True)) == {"r1": 1, "r2": 1}
    assert dict(zip(spawning["reach_id"], spawning["n_eggs"], strict=True)) == {"r1": 5, "r2": 5}
    assert len(result.redds) == 2


def test_native_ibm_light_phase_feeding_weights_control_growth() -> None:
    cells = pd.DataFrame(
        {
            "cell_id": ["best"],
            "area_m2": [20.0],
            "depth_m": [0.7],
            "velocity_ms": [0.35],
            "csi": [1.0],
            "temperature_c": [12.0],
            "hiding_cover": [1.0],
            "feeding_cover": [1.0],
        }
    )
    pop = build_initial_population(n=1, length_mm=100.0)
    no_feeding = SpeciesProfile(
        light_phase_feeding_weights=(("day", 0.0),),
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
    )
    full_feeding = SpeciesProfile(
        light_phase_feeding_weights=(("day", 1.0),),
        base_daily_survival=1.0,
        predation_base_risk=0.0,
        predation_csi_risk=0.0,
        thermal_stress_mortality=0.0,
        hydraulic_stress_mortality=0.0,
    )

    low = run_native_ibm(
        cells,
        pop,
        profile=no_feeding,
        config=NativeIBMConfig(days=1, light_phases=("day",), stochastic=False),
    )
    high = run_native_ibm(
        cells,
        pop,
        profile=full_feeding,
        config=NativeIBMConfig(days=1, light_phases=("day",), stochastic=False),
    )

    assert high.final_individuals["length_mm"].iloc[0] > low.final_individuals["length_mm"].iloc[0]


def test_native_ibm_hot_water_reduces_survival() -> None:
    pop = build_initial_population(n=200, length_mm=90.0)
    cool = _cells()
    hot = _cells()
    hot["temperature_c"] = 28.0
    cfg = NativeIBMConfig(days=20, seed=99)

    cool_result = run_native_ibm(cool, pop, config=cfg)
    hot_result = run_native_ibm(hot, pop, config=cfg)

    assert (
        hot_result.population_summary["abundance"].iloc[-1]
        < (cool_result.population_summary["abundance"].iloc[-1])
    )


def test_native_ibm_spawning_creates_recruits() -> None:
    pop = build_initial_population(n=20, length_mm=180.0)
    profile = SpeciesProfile(
        spawn_start_day=1,
        spawn_end_day=3,
        fecundity_per_female=40.0,
        egg_to_fry_survival=0.05,
        egg_incubation_degree_days=24.0,
    )
    result = run_native_ibm(
        _cells(),
        pop,
        profile=profile,
        config=NativeIBMConfig(days=3, seed=2, stochastic=False),
    )

    assert result.population_summary["n_recruits"].sum() > 0
    assert "recruitment" in set(result.events["event"])
    assert "spawning" in set(result.events["event"])
    assert not result.redds.empty


def test_native_ibm_spawns_adults_once_per_season() -> None:
    pop = build_initial_population(n=20, length_mm=180.0)
    profile = SpeciesProfile(
        spawn_start_day=1,
        spawn_end_day=3,
        fecundity_per_female=40.0,
        egg_to_fry_survival=0.05,
        egg_incubation_degree_days=24.0,
    )
    result = run_native_ibm(
        _cells(),
        pop,
        profile=profile,
        config=NativeIBMConfig(days=3, seed=2, stochastic=False),
    )

    summary = result.population_summary.set_index("day")
    assert int(summary.loc[1, "n_spawners"]) == 20
    assert int(summary.loc[2, "n_spawners"]) == 0
    assert int(summary.loc[3, "n_spawners"]) == 0
    assert int(summary["n_recruits"].sum()) == 20
    assert int(result.redds["eggs_initial"].sum()) == 400


def test_native_ibm_length_dependent_fecundity() -> None:
    pop = build_initial_population(n=2, length_mm=100.0)
    pop.loc[1, "length_mm"] = 200.0
    pop["mass_g"] = [1.0, 8.0]
    profile = SpeciesProfile(
        spawn_start_day=1,
        spawn_end_day=1,
        maturity_length_mm=50.0,
        fecundity_per_female=10.0,
        fecundity_length_exponent=1.0,
        fecundity_reference_length_mm=100.0,
        egg_to_fry_survival=1.0,
    )

    result = run_native_ibm(
        _cells(),
        pop,
        profile=profile,
        config=NativeIBMConfig(days=1, seed=2, stochastic=False),
    )

    assert int(result.redds["eggs_initial"].sum()) == 15


def test_native_ibm_spawner_female_fraction_controls_egg_count() -> None:
    pop = build_initial_population(n=4, length_mm=180.0)
    profile = SpeciesProfile(
        spawn_start_day=1,
        spawn_end_day=1,
        maturity_length_mm=50.0,
        spawner_female_fraction=1.0,
        fecundity_per_female=10.0,
        egg_to_fry_survival=0.0,
    )

    result = run_native_ibm(
        _cells(),
        pop,
        profile=profile,
        config=NativeIBMConfig(days=1, seed=2, stochastic=False),
    )

    assert int(result.redds["eggs_initial"].sum()) == 40


def test_native_ibm_redd_incubation_delays_recruitment() -> None:
    pop = build_initial_population(n=10, length_mm=180.0)
    profile = SpeciesProfile(
        spawn_start_day=1,
        spawn_end_day=1,
        fecundity_per_female=20.0,
        egg_to_fry_survival=1.0,
        egg_incubation_degree_days=24.0,
        redd_base_daily_survival=1.0,
    )

    result = run_native_ibm(
        _cells(),
        pop,
        profile=profile,
        config=NativeIBMConfig(days=3, seed=2, stochastic=False),
    )

    summary = result.population_summary.set_index("day")
    assert int(summary.loc[1, "n_recruits"]) == 0
    assert int(summary.loc[2, "n_recruits"]) == 0
    assert int(summary.loc[3, "n_recruits"]) == 100
    assert bool(result.redds["emerged"].iloc[0])
    assert int(result.redds["emergence_day"].iloc[0]) == 3


def test_write_native_ibm_result_writes_tables(tmp_path) -> None:
    pop = build_initial_population(n=5)
    result = run_native_ibm(_cells(), pop, config=NativeIBMConfig(days=1, seed=1))
    paths = write_native_ibm_result(result, tmp_path)

    assert set(paths) == {
        "native_ibm_population_summary",
        "native_ibm_final_individuals",
        "native_ibm_cell_use",
        "native_ibm_events",
        "native_ibm_event_daily",
        "native_ibm_event_summary",
        "native_ibm_redds",
        "ibm_run_manifest",
        # 2026-05-26 R-IBM-PROVENANCE: write_native_ibm_result now
        # also emits a Case-compatible provenance.json alongside the
        # IBM-specific manifest (ADR-0016 cleanup track).
        "provenance",
    }
    assert pd.read_csv(tmp_path / "native_ibm_population_summary.csv").shape[0] == 2
    assert (tmp_path / "native_ibm_redds.csv").exists()
    assert (tmp_path / "native_ibm_event_summary.csv").exists()
    manifest = json.loads((tmp_path / "ibm_run_manifest.json").read_text())
    assert manifest["outputs"]["native_ibm_population_summary.csv"]["rows"] == 2
    assert "native_ibm_event_summary.csv" in manifest["outputs"]


def test_native_ibm_optional_individual_history_writes_daily_states(tmp_path) -> None:
    pop = build_initial_population(n=3)
    result = run_native_ibm(
        _cells(),
        pop,
        config=NativeIBMConfig(days=2, seed=1, record_individual_history=True),
    )
    paths = write_native_ibm_result(result, tmp_path)

    assert "native_ibm_individual_history" in paths
    history = pd.read_csv(tmp_path / "native_ibm_individual_history.csv")
    assert len(history) == 9
    assert set(history["day"]) == {0, 1, 2}
    assert set(history["fish_id"]) == {0, 1, 2}


def test_native_ibm_rejects_missing_area() -> None:
    pop = build_initial_population(n=1)
    with pytest.raises(ValueError, match="area_m2"):
        run_native_ibm(pd.DataFrame({"csi": [1.0]}), pop)


def test_native_ibm_rejects_missing_habitat_suitability_inputs() -> None:
    pop = build_initial_population(n=1)
    cells = pd.DataFrame({"area_m2": [10.0], "temperature_c": [12.0]})

    with pytest.raises(ValueError, match="csi, wua_m2, or both depth_m and velocity_ms"):
        run_native_ibm(cells, pop)


def test_native_ibm_rejects_invalid_direct_csi_without_hydraulics() -> None:
    pop = build_initial_population(n=1)
    cells = pd.DataFrame({"area_m2": [10.0], "csi": [None], "temperature_c": [12.0]})

    with pytest.raises(ValueError, match="at least one valid csi"):
        run_native_ibm(cells, pop)


def test_native_ibm_accepts_direct_csi_without_hydraulics() -> None:
    pop = build_initial_population(n=2)
    cells = pd.DataFrame({"area_m2": [10.0], "csi": [0.8]})

    result = run_native_ibm(cells, pop, config=NativeIBMConfig(days=1, stochastic=False))

    assert int(result.population_summary["abundance"].iloc[-1]) == 2


def test_native_ibm_summarizes_multiple_species_separately() -> None:
    cells = pd.DataFrame({"area_m2": [10.0], "csi": [0.8]})
    pop = build_initial_population(n=2, species="rainbow_trout")
    pop.loc[1, "species"] = "brown_trout"

    result = run_native_ibm(cells, pop, config=NativeIBMConfig(days=0, reach_id="r1"))
    summary = result.population_summary.set_index("species")

    assert int(summary.loc["rainbow_trout", "abundance"]) == 1
    assert int(summary.loc["brown_trout", "abundance"]) == 1


def test_native_ibm_rejects_duplicate_fish_ids() -> None:
    pop = build_initial_population(n=2)
    pop.loc[1, "fish_id"] = 0

    with pytest.raises(ValueError, match="fish_id values must be unique"):
        run_native_ibm(_cells(), pop)
