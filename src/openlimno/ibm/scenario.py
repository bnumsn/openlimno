"""Scenario/profile contracts for OpenLimno's native IBM."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, replace
from importlib import resources
from pathlib import Path
from typing import Any, cast

import pandas as pd
import yaml
from jsonschema import Draft202012Validator

from .native import (
    NativeIBMConfig,
    NativeIBMResult,
    SpeciesProfile,
    build_initial_population,
    run_native_ibm,
    write_native_ibm_result,
)
from .submodels import resolve_submodel_selection, validate_submodel_selection

IBM_SCHEMA_VERSION = "0.2"


def _schema_dir() -> Path:
    return Path(resources.files(__package__).joinpath("schemas"))


def load_ibm_schema(name: str) -> dict[str, Any]:
    """Load an IBM schema by basename without ``.schema.json``."""

    path = _schema_dir() / f"{name}.schema.json"
    with path.open("r", encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


def _read_document(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        if p.suffix.lower() == ".json":
            data = json.load(f)
        else:
            data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{p} must contain a mapping/object")
    return cast(dict[str, Any], data)


def _validate_document(path: str | Path, schema_name: str) -> list[str]:
    data = _read_document(path)
    schema = load_ibm_schema(schema_name)
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(x) for x in err.absolute_path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(data)
    ]


def validate_species_profile(path: str | Path) -> list[str]:
    """Validate an IBM species profile YAML/JSON document."""

    errors = _validate_document(path, "species_profile")
    if errors:
        return errors
    return _semantic_species_profile_errors(_read_document(path))


def validate_ibm_scenario(path: str | Path) -> list[str]:
    """Validate an IBM scenario YAML/JSON document."""

    errors = _validate_document(path, "ibm_scenario")
    if errors:
        return errors
    data = _read_document(path)
    raw_submodels = data.get("submodels")
    if raw_submodels is not None and isinstance(raw_submodels, dict):
        errors.extend(validate_submodel_selection(raw_submodels))
    return errors


def _param_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _flatten_profile_parameters(data: dict[str, Any]) -> dict[str, Any]:
    sections = (
        "parameters",
        "growth",
        "habitat_selection",
        "mortality",
        "movement",
        "spawning",
        "redds",
    )
    flat: dict[str, Any] = {}
    for section in sections:
        raw = data.get(section)
        if not isinstance(raw, dict):
            continue
        for key, value in raw.items():
            if isinstance(key, str):
                flat[key] = _param_value(value)
    return flat


_PROFILE_PROBABILITY_FIELDS = {
    "base_daily_survival",
    "max_mortality_risk",
    "spawner_female_fraction",
    "egg_to_fry_survival",
    "redd_base_daily_survival",
    "redd_dewatering_mortality",
    "redd_scour_mortality",
    "predation_base_risk",
    "predation_csi_risk",
    "thermal_stress_mortality",
    "hydraulic_stress_mortality",
    "feeding_cover_foraging_weight",
}
_PROFILE_NONNEGATIVE_FIELDS = {
    "max_daily_growth_mm",
    "weight_a_g_per_cm_b",
    "weight_b",
    "max_consumption_fraction",
    "respiration_fraction",
    "activity_respiration_fraction",
    "carrying_density_per_m2",
    "min_cell_capacity",
    "density_competition_strength",
    "default_light_phase_feeding_weight",
    "default_light_phase_predation_weight",
    "turbidity_half_saturation_ntu",
    "velocity_stress_threshold_ms",
    "velocity_stress_scale_ms",
    "utility_growth_weight",
    "utility_mortality_weight",
    "respiration_base_multiplier",
    "respiration_thermal_multiplier",
    "max_activity_velocity_ms",
    "max_mass_loss_fraction",
    "max_mass_gain_fraction",
    "max_daily_shrinkage_mm",
    "maturity_length_mm",
    "fecundity_per_female",
    "fecundity_length_exponent",
    "fecundity_reference_length_mm",
    "egg_incubation_degree_days",
    "spawning_cover_weight",
    "spawning_csi_weight",
    "redd_min_depth_m",
    "redd_scour_velocity_ms",
    "fry_length_mm",
    "fry_mass_g",
    "cross_reach_movement_penalty",
    "cross_reach_movement_rate",
    "cross_reach_movement_min_length_mm",
    "cross_reach_movement_length_scale_mm",
    "cross_reach_movement_max_steps",
    "cross_reach_interior_movement_multiplier",
    "cross_reach_habitat_utility_weight",
}


def _semantic_species_profile_errors(data: dict[str, Any]) -> list[str]:
    defaults = SpeciesProfile()
    valid_fields = {field.name for field in fields(SpeciesProfile)}
    numeric_defaults = {
        field.name: getattr(defaults, field.name)
        for field in fields(SpeciesProfile)
        if isinstance(getattr(defaults, field.name), (int, float))
        and not isinstance(getattr(defaults, field.name), bool)
    }
    raw_values = _flatten_profile_parameters(data)
    numeric_values = dict(numeric_defaults)
    errors: list[str] = []
    for key, raw_value in raw_values.items():
        if key not in valid_fields or key not in numeric_defaults:
            continue
        value = _param_value(raw_value)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{key}: expected a numeric SpeciesProfile value")
            continue
        numeric = float(value)
        if not math.isfinite(numeric):
            errors.append(f"{key}: value must be finite")
            continue
        numeric_values[key] = numeric
        if key in _PROFILE_PROBABILITY_FIELDS and not 0.0 <= numeric <= 1.0:
            errors.append(f"{key}: value must be within [0, 1]")
        if key in _PROFILE_NONNEGATIVE_FIELDS and numeric < 0.0:
            errors.append(f"{key}: value must be non-negative")
    start_day = numeric_values.get("spawn_start_day")
    end_day = numeric_values.get("spawn_end_day")
    for day_key, day_value in (("spawn_start_day", start_day), ("spawn_end_day", end_day)):
        if day_value is not None and not 1 <= int(day_value) <= 366:
            errors.append(f"{day_key}: value must be within [1, 366]")
    thermal_min = float(numeric_values["thermal_min_c"])
    thermal_optimum = float(numeric_values["thermal_optimum_c"])
    thermal_max = float(numeric_values["thermal_max_c"])
    if not thermal_min < thermal_optimum < thermal_max:
        errors.append("thermal_min_c, thermal_optimum_c, and thermal_max_c must be strictly ordered")
    return errors


def load_species_profile(path: str | Path) -> SpeciesProfile:
    """Load a versioned IBM species profile into ``SpeciesProfile``."""

    errors = validate_species_profile(path)
    if errors:
        raise ValueError("Species profile failed schema validation:\n  - " + "\n  - ".join(errors))
    data = _read_document(path)
    species_block = data.get("species", {})
    species = "rainbow_trout"
    if isinstance(species_block, dict):
        species_id = species_block.get("id")
        if isinstance(species_id, str) and species_id.strip():
            species = species_id.strip()

    valid_fields = {field.name for field in fields(SpeciesProfile)}
    kwargs: dict[str, Any] = {"species": species}
    for key, value in _flatten_profile_parameters(data).items():
        if key in valid_fields and key != "species":
            kwargs[key] = value
    return SpeciesProfile(**kwargs)


def write_species_profile(profile: SpeciesProfile, path: str | Path) -> Path:
    """Write a ``SpeciesProfile`` as a versioned IBM profile YAML."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "profile_version": IBM_SCHEMA_VERSION,
        "species": {"id": profile.species},
        "parameters": {},
        "calibration": {
            "accepted": False,
            "notes": "Generated from OpenLimno SpeciesProfile defaults.",
        },
    }
    params = cast(dict[str, Any], data["parameters"])
    for field in fields(SpeciesProfile):
        if field.name == "species":
            continue
        value = getattr(profile, field.name)
        if isinstance(value, str | int | float | bool):
            params[field.name] = {"value": value, "evidence": "generated-default"}
    with target.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return target


def load_ibm_scenario(path: str | Path) -> dict[str, Any]:
    """Load and validate a versioned IBM scenario document."""

    errors = validate_ibm_scenario(path)
    if errors:
        raise ValueError("IBM scenario failed schema validation:\n  - " + "\n  - ".join(errors))
    return _read_document(path)


def _resolve_from(base_dir: Path, uri: str | Path) -> Path:
    p = Path(uri)
    return p if p.is_absolute() else base_dir / p


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, comment="#")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _optional_file_sha(path: Path | None) -> str | None:
    if path is None:
        return None
    return _file_sha256(path)


def _apply_scenario_overrides(
    data: dict[str, Any],
    overrides: Mapping[str, object] | None,
) -> dict[str, Any]:
    if not overrides:
        return data
    updated = deepcopy(data)
    scenario = dict(cast(dict[str, Any], updated.get("scenario", {})))
    scenario.update(dict(overrides))
    updated["scenario"] = scenario
    return updated


def _apply_profile_overrides(
    profile: SpeciesProfile,
    overrides: Mapping[str, object] | None,
) -> SpeciesProfile:
    if not overrides:
        return profile
    valid_fields = {field.name for field in fields(SpeciesProfile)}
    invalid = sorted(set(overrides) - valid_fields)
    if invalid:
        raise ValueError(f"Unknown SpeciesProfile override(s): {', '.join(invalid)}")
    if "species" in overrides:
        raise ValueError("SpeciesProfile override 'species' is not supported; use a profile document")
    return replace(profile, **dict(overrides))


def run_ibm_scenario(
    scenario_path: str | Path,
    *,
    scenario_overrides: Mapping[str, object] | None = None,
    profile_overrides: Mapping[str, object] | None = None,
    output_dir_override: str | Path | None = None,
    run_label: str | None = None,
) -> tuple[NativeIBMResult, dict[str, str]]:
    """Run an IBM scenario document through the current native engine."""

    path = Path(scenario_path).resolve()
    data = _apply_scenario_overrides(load_ibm_scenario(path), scenario_overrides)
    base_dir = path.parent

    scenario = cast(dict[str, Any], data.get("scenario", {}))
    forcing = cast(dict[str, Any], data.get("forcing", {}))
    population = cast(dict[str, Any], data.get("population", {}))
    outputs = cast(dict[str, Any], data.get("outputs", {}))
    profile_block = cast(dict[str, Any], data.get("profile", {}))
    submodels = resolve_submodel_selection(cast(dict[str, object] | None, data.get("submodels")))

    species = str(population.get("default_species", "rainbow_trout"))
    profile_path: Path | None = None
    profile = SpeciesProfile(species=species)
    profile_uri = profile_block.get("uri")
    if isinstance(profile_uri, str) and profile_uri.strip():
        profile_path = _resolve_from(base_dir, profile_uri)
        profile = load_species_profile(profile_path)
        species = profile.species
    profile = _apply_profile_overrides(profile, profile_overrides)

    cells_path = _resolve_from(base_dir, str(forcing["habitat_cells"]))
    cells = _read_table(cells_path)

    population_path: Path | None = None
    initial_population_uri = population.get("initial_population")
    if isinstance(initial_population_uri, str) and initial_population_uri.strip():
        population_path = _resolve_from(base_dir, initial_population_uri)
        fish = _read_table(population_path)
    else:
        # Pass the loaded profile so initial mass matches the runtime
        # length→mass formula. Without this the day-0 mass uses default
        # SpeciesProfile() weight_a/b and the day-1 mass uses the loaded
        # archive's weight_a/b, producing a silent mass jump between days
        # (2026-05-26 software-test S1; Codex + Gemini both verified live).
        #
        # If the scenario carries ``population.cohorts``, build a
        # stratified initial population (per-age, per-length-mode) —
        # 2026-05-27 stratified-init track A. This closes the ~35%
        # biomass offset against NetLogo BriefPop reference (Step 9).
        cohort_specs = population.get("cohorts")
        fish = build_initial_population(
            n=int(population.get("initial_abundance", 100)),
            species=species,
            length_mm=float(population.get("initial_length_mm", 110.0)),
            profile=profile,
            cohorts=cohort_specs if isinstance(cohort_specs, (list, tuple)) else None,
        )

    light_phases_raw = scenario.get("light_phases", ("dawn", "day", "dusk", "night"))
    light_phases = (
        tuple(str(item) for item in light_phases_raw)
        if isinstance(light_phases_raw, (list, tuple))
        else ("dawn", "day", "dusk", "night")
    )
    config = NativeIBMConfig(
        days=int(scenario.get("days", 365)),
        seed=int(scenario.get("seed", 42)),
        start_day=int(scenario.get("start_day", 1)),
        start_year=int(scenario.get("start_year", 0)),
        scenario_id=str(scenario.get("id", "ibm-scenario")),
        reach_id=str(scenario.get("reach_id", "reach-1")),
        light_phases=light_phases,
        stochastic=bool(scenario.get("stochastic", True)),
        record_individual_history=bool(outputs.get("individual_history", False)),
        movement_submodel=submodels.get("movement", "native-adjacent-reach-movement-v0"),
        spawning_submodel=submodels.get("spawning", "native-redd-recruitment-v0"),
        time_index_column=str(forcing.get("time_index_column", "time_index")),
    )
    result = run_native_ibm(cells, fish, profile=profile, config=config)

    output_uri = str(output_dir_override) if output_dir_override is not None else str(outputs["dir"])
    output_dir = _resolve_from(base_dir, output_uri)
    output_formats = tuple(str(item) for item in outputs.get("formats", ["csv"]))
    manifest = {
        "ibm_version": IBM_SCHEMA_VERSION,
        "scenario_path": str(path),
        "scenario_sha256": _file_sha256(path),
        "profile_path": str(profile_path) if profile_path is not None else None,
        "profile_sha256": _optional_file_sha(profile_path),
        "forcing_path": str(cells_path),
        "forcing_sha256": _file_sha256(cells_path),
        "initial_population_path": str(population_path) if population_path is not None else None,
        "initial_population_sha256": _optional_file_sha(population_path),
        "run_label": run_label,
        "seed": config.seed,
        "stochastic": config.stochastic,
        "scenario_overrides": dict(scenario_overrides or {}),
        "profile_overrides": dict(profile_overrides or {}),
        "submodels": submodels,
        "output_formats": list(output_formats),
    }
    paths = write_native_ibm_result(result, output_dir, manifest=manifest, formats=output_formats)
    return result, paths


__all__ = [
    "IBM_SCHEMA_VERSION",
    "load_ibm_scenario",
    "load_ibm_schema",
    "load_species_profile",
    "run_ibm_scenario",
    "validate_ibm_scenario",
    "validate_species_profile",
    "write_species_profile",
]
