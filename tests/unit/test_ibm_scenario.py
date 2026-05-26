from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from openlimno.ibm import (
    SpeciesProfile,
    list_ibm_submodels,
    load_species_profile,
    run_ibm_abc_calibration,
    run_ibm_calibration,
    run_ibm_ensemble,
    run_ibm_scenario,
    validate_ibm_scenario,
    validate_species_profile,
    write_species_profile,
)


def _write_habitat_cells(tmp_path: Path) -> Path:
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r1"],
            "cell_id": ["pool-a", "riffle-b"],
            "area_m2": [15.0, 25.0],
            "depth_m": [0.4, 0.8],
            "velocity_ms": [0.2, 0.35],
            "csi": [0.4, 0.9],
            "temperature_c": [12.0, 12.0],
            "hiding_cover": [0.1, 0.8],
            "feeding_cover": [0.1, 0.7],
            "spawning_cover": [0.0, 0.2],
        }
    )
    path = tmp_path / "habitat_cells.csv"
    cells.to_csv(path, index=False)
    return path


def _write_profile(tmp_path: Path) -> Path:
    path = tmp_path / "trout_profile.yaml"
    path.write_text(
        "profile_version: '0.2'\n"
        "species:\n"
        "  id: rainbow_trout\n"
        "growth:\n"
        "  max_daily_growth_mm:\n"
        "    value: 0.12\n"
        "    evidence: unit-test\n"
        "mortality:\n"
        "  base_daily_survival: 1.0\n"
        "  predation_base_risk: 0.0\n"
        "  predation_csi_risk: 0.0\n"
        "  thermal_stress_mortality: 0.0\n"
        "  hydraulic_stress_mortality: 0.0\n",
        encoding="utf-8",
    )
    return path


def test_species_profile_schema_round_trip(tmp_path: Path) -> None:
    path = write_species_profile(
        SpeciesProfile(species="coho_salmon", base_daily_survival=0.991),
        tmp_path / "coho_profile.yaml",
    )

    assert validate_species_profile(path) == []
    profile = load_species_profile(path)
    assert profile.species == "coho_salmon"
    assert profile.base_daily_survival == pytest.approx(0.991)


def test_species_profile_semantic_validation_rejects_bad_bounds(tmp_path: Path) -> None:
    path = tmp_path / "bad_profile.yaml"
    path.write_text(
        "profile_version: '0.2'\n"
        "species:\n"
        "  id: rainbow_trout\n"
        "mortality:\n"
        "  base_daily_survival: 1.4\n"
        "growth:\n"
        "  thermal_min_c: 20\n"
        "  thermal_optimum_c: 10\n"
        "  thermal_max_c: 5\n",
        encoding="utf-8",
    )

    errors = validate_species_profile(path)

    assert any("base_daily_survival" in error for error in errors)
    assert any("strictly ordered" in error for error in errors)


def test_ibm_scenario_runs_with_manifest(tmp_path: Path) -> None:
    _write_habitat_cells(tmp_path)
    _write_profile(tmp_path)
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: manifest-smoke\n"
        "  reach_id: r1\n"
        "  days: 2\n"
        "  seed: 5\n"
        "  stochastic: false\n"
        "  light_phases: [day]\n"
        "profile:\n"
        "  uri: trout_profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 4\n"
        "  initial_length_mm: 100.0\n"
        "submodels:\n"
        "  habitat_selection: native-habitat-utility-v0\n"
        "outputs:\n"
        "  dir: out\n"
        "  individual_history: true\n",
        encoding="utf-8",
    )

    assert validate_ibm_scenario(scenario_path) == []
    result, paths = run_ibm_scenario(scenario_path)

    assert len(result.population_summary) == 3
    assert "ibm_run_manifest" in paths
    manifest_path = Path(paths["ibm_run_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["scenario_path"] == str(scenario_path.resolve())
    assert manifest["scenario_sha256"]
    assert manifest["profile_sha256"]
    assert manifest["forcing_sha256"]
    assert manifest["seed"] == 5
    assert manifest["stochastic"] is False
    assert manifest["submodels"]["habitat_selection"] == "native-habitat-utility-v0"
    assert manifest["outputs"]["native_ibm_population_summary.csv"]["rows"] == len(
        result.population_summary
    )
    assert (tmp_path / "out" / "native_ibm_individual_history.csv").exists()


def test_ibm_scenario_honors_custom_time_index_column(tmp_path: Path) -> None:
    cells = pd.DataFrame(
        {
            "reach_id": ["r1", "r1", "r1", "r1"],
            "cell_id": ["a", "b", "a", "b"],
            "flow_day": [10, 10, 20, 20],
            "area_m2": [15.0, 15.0, 15.0, 15.0],
            "depth_m": [0.4, 0.8, 0.8, 0.4],
            "velocity_ms": [0.2, 0.35, 0.35, 0.2],
            "csi": [0.95, 0.1, 0.1, 0.95],
            "temperature_c": [12.0, 12.0, 12.0, 12.0],
            "hiding_cover": [1.0, 1.0, 1.0, 1.0],
            "feeding_cover": [1.0, 1.0, 1.0, 1.0],
        }
    )
    cells.to_csv(tmp_path / "habitat_cells.csv", index=False)
    _write_profile(tmp_path)
    scenario_path = tmp_path / "time_column.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: time-column-smoke\n"
        "  days: 2\n"
        "  stochastic: false\n"
        "  light_phases: [day]\n"
        "profile:\n"
        "  uri: trout_profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "  time_index_column: flow_day\n"
        "population:\n"
        "  initial_abundance: 8\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )

    result, _paths = run_ibm_scenario(scenario_path)

    day_use = result.cell_use[result.cell_use["phase"] == "day"]
    day1 = day_use[day_use["day"] == 1].groupby("cell_id")["n_fish"].sum()
    day2 = day_use[day_use["day"] == 2].groupby("cell_id")["n_fish"].sum()
    assert str(day1.idxmax()) == "a"
    assert str(day2.idxmax()) == "b"


def test_ibm_scenario_writes_requested_parquet_outputs(tmp_path: Path) -> None:
    _write_habitat_cells(tmp_path)
    _write_profile(tmp_path)
    scenario_path = tmp_path / "parquet.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: parquet-smoke\n"
        "  days: 1\n"
        "profile:\n"
        "  uri: trout_profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 4\n"
        "outputs:\n"
        "  dir: out\n"
        "  formats: [csv, parquet]\n",
        encoding="utf-8",
    )

    _result, paths = run_ibm_scenario(scenario_path)
    manifest = json.loads(Path(paths["ibm_run_manifest"]).read_text(encoding="utf-8"))

    assert Path(paths["native_ibm_population_summary_parquet"]).exists()
    assert "native_ibm_population_summary.parquet" in manifest["outputs"]
    assert manifest["output_formats"] == ["csv", "parquet"]


def test_ibm_submodel_registry_semantically_validates_scenarios(tmp_path: Path) -> None:
    _write_habitat_cells(tmp_path)
    scenario_path = tmp_path / "bad_submodel.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: bad-submodel\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "submodels:\n"
        "  growth: imaginary-growth-v9\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )

    errors = validate_ibm_scenario(scenario_path)
    assert any("unsupported submodel id" in error for error in errors)
    assert any(model.slot == "habitat_selection" for model in list_ibm_submodels())


def test_ibm_ensemble_runs_seed_replicates_from_scenario_block(tmp_path: Path) -> None:
    _write_habitat_cells(tmp_path)
    _write_profile(tmp_path)
    scenario_path = tmp_path / "ensemble.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: ensemble-smoke\n"
        "  days: 1\n"
        "profile:\n"
        "  uri: trout_profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 4\n"
        "experiments:\n"
        "  ensemble:\n"
        "    seeds: [1, 2]\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )

    result = run_ibm_ensemble(scenario_path)

    assert list(result.summary["seed"]) == [1, 2]
    assert (tmp_path / "out" / "ensemble" / "ibm_ensemble_summary.csv").exists()
    assert (tmp_path / "out" / "ensemble" / "ibm_ensemble_daily_bands.csv").exists()
    assert list(result.daily_bands["day"]) == [0, 1]
    assert result.summary["manifest_path"].map(lambda p: Path(str(p)).exists()).all()


def test_ibm_ensemble_parameter_sensitivity_ranking(tmp_path: Path) -> None:
    _write_habitat_cells(tmp_path)
    _write_profile(tmp_path)
    scenario_path = tmp_path / "ensemble_params.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: ensemble-param-smoke\n"
        "  days: 1\n"
        "profile:\n"
        "  uri: trout_profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 4\n"
        "experiments:\n"
        "  ensemble:\n"
        "    seeds: [1, 2]\n"
        "    parameters:\n"
        "      base_daily_survival: [0.5, 1.0]\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )

    result = run_ibm_ensemble(scenario_path)

    assert len(result.summary) == 4
    assert "param_base_daily_survival" in result.summary
    assert list(result.sensitivity["parameter"]) == ["base_daily_survival"]
    assert (tmp_path / "out" / "ensemble" / "ibm_ensemble_sensitivity.csv").exists()


def test_ibm_calibration_grid_writes_best_profile(tmp_path: Path) -> None:
    _write_habitat_cells(tmp_path)
    _write_profile(tmp_path)
    observed_path = tmp_path / "observed.csv"
    pd.DataFrame(
        {
            "day": [1],
            "abundance": [4],
            "biomass_g": [20.0],
            "mean_length_mm": [100.0],
        }
    ).to_csv(observed_path, index=False)
    scenario_path = tmp_path / "calibration.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: calibration-smoke\n"
        "  days: 1\n"
        "  stochastic: false\n"
        "  light_phases: [day]\n"
        "profile:\n"
        "  uri: trout_profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 4\n"
        "experiments:\n"
        "  calibration:\n"
        "    observed: observed.csv\n"
        "    parameters:\n"
        "      base_daily_survival: [0.5, 1.0]\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )

    result = run_ibm_calibration(scenario_path)

    assert result.best_parameters == {"base_daily_survival": 1.0}
    assert float(result.summary.iloc[0]["score"]) == pytest.approx(0.0)
    assert "rmse_biomass_g" in result.summary
    assert "rmse_mean_length_mm" in result.summary
    metrics = pd.read_csv(tmp_path / "out" / "calibration" / "ibm_calibration_metrics.csv")
    assert {"abundance", "biomass_g", "mean_length_mm"} <= set(metrics["metric"])
    assert {"candidate_id", "model_value", "observed_value", "passed"} <= set(metrics.columns)
    assert (tmp_path / "out" / "calibration" / "best_profile.yaml").exists()


def test_ibm_abc_calibration_accepts_prior_samples(tmp_path: Path) -> None:
    _write_habitat_cells(tmp_path)
    _write_profile(tmp_path)
    observed_path = tmp_path / "observed.csv"
    pd.DataFrame({"day": [1], "abundance": [4]}).to_csv(observed_path, index=False)
    scenario_path = tmp_path / "abc.yaml"
    scenario_path.write_text(
        "ibm_version: '0.2'\n"
        "scenario:\n"
        "  id: abc-smoke\n"
        "  days: 1\n"
        "  stochastic: false\n"
        "  light_phases: [day]\n"
        "profile:\n"
        "  uri: trout_profile.yaml\n"
        "forcing:\n"
        "  habitat_cells: habitat_cells.csv\n"
        "population:\n"
        "  initial_abundance: 4\n"
        "experiments:\n"
        "  calibration:\n"
        "    observed: observed.csv\n"
        "    method: abc\n"
        "    samples: 4\n"
        "    acceptance_fraction: 0.5\n"
        "    parameters:\n"
        "      base_daily_survival: [0.5, 1.0]\n"
        "outputs:\n"
        "  dir: out\n",
        encoding="utf-8",
    )

    result = run_ibm_abc_calibration(
        scenario_path,
        observed_path=observed_path,
        parameter_priors={"base_daily_survival": [0.5, 1.0]},
        samples=4,
        acceptance_fraction=0.5,
    )

    assert int(result.summary["accepted"].sum()) == 2
    assert "base_daily_survival" in result.best_parameters
    assert (tmp_path / "out" / "calibration" / "ibm_abc_accepted.csv").exists()
