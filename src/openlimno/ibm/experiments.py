"""Ensemble and calibration runners for versioned IBM scenarios."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from itertools import product
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from .native import NativeIBMResult, SpeciesProfile
from .scenario import (
    load_ibm_scenario,
    load_species_profile,
    run_ibm_scenario,
    write_species_profile,
)


@dataclass(frozen=True)
class IBMEnsembleResult:
    """Summary and artifact paths from an IBM ensemble run."""

    summary: pd.DataFrame
    daily_bands: pd.DataFrame
    sensitivity: pd.DataFrame
    paths: dict[str, str]


@dataclass(frozen=True)
class IBMCalibrationResult:
    """Summary, best parameter set, and artifact paths from an IBM calibration run."""

    summary: pd.DataFrame
    best_parameters: dict[str, float]
    paths: dict[str, str]


def _resolve_from(base_dir: Path, uri: str | Path) -> Path:
    p = Path(uri)
    return p if p.is_absolute() else base_dir / p


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, comment="#")


def _experiment_block(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    experiments = data.get("experiments")
    if not isinstance(experiments, dict):
        return {}
    block = experiments.get(name)
    return cast(dict[str, Any], block) if isinstance(block, dict) else {}


def _experiment_root(
    scenario_path: Path,
    data: Mapping[str, Any],
    name: str,
    output_dir: str | Path | None,
) -> Path:
    if output_dir is not None:
        return _resolve_from(scenario_path.parent, output_dir)
    block = _experiment_block(data, name)
    block_dir = block.get("dir")
    if isinstance(block_dir, str) and block_dir.strip():
        return _resolve_from(scenario_path.parent, block_dir)
    outputs = data.get("outputs")
    output_root = "out"
    if isinstance(outputs, dict) and isinstance(outputs.get("dir"), str):
        output_root = str(outputs["dir"])
    return _resolve_from(scenario_path.parent, Path(output_root) / name)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n")


def _final_metrics(result: NativeIBMResult) -> dict[str, object]:
    summary = result.population_summary
    if summary.empty:
        return {
            "final_day": 0,
            "final_abundance": 0,
            "final_biomass_g": 0.0,
            "final_mean_length_mm": math.nan,
        }
    final_day = int(summary["day"].max())
    final = summary[summary["day"] == final_day]
    abundance = int(pd.to_numeric(final["abundance"], errors="coerce").fillna(0).sum())
    biomass = float(pd.to_numeric(final["biomass_g"], errors="coerce").fillna(0.0).sum())
    if abundance > 0 and "mean_length_mm" in final:
        weighted = (
            pd.to_numeric(final["mean_length_mm"], errors="coerce").fillna(0.0)
            * pd.to_numeric(final["abundance"], errors="coerce").fillna(0)
        )
        mean_length = float(weighted.sum() / abundance)
    else:
        mean_length = math.nan
    return {
        "final_day": final_day,
        "final_abundance": abundance,
        "final_biomass_g": biomass,
        "final_mean_length_mm": mean_length,
    }


def _daily_metrics(result: NativeIBMResult) -> pd.DataFrame:
    summary = result.population_summary
    columns = ["day", "abundance", "biomass_g", "mean_length_mm"]
    if summary.empty:
        return pd.DataFrame(columns=columns)
    table = summary.copy()
    table["abundance"] = pd.to_numeric(table["abundance"], errors="coerce").fillna(0.0)
    table["biomass_g"] = pd.to_numeric(table["biomass_g"], errors="coerce").fillna(0.0)
    table["mean_length_mm"] = pd.to_numeric(table["mean_length_mm"], errors="coerce")
    table["weighted_length"] = table["mean_length_mm"].fillna(0.0) * table["abundance"]
    grouped = table.groupby("day", as_index=False).agg(
        abundance=("abundance", "sum"),
        biomass_g=("biomass_g", "sum"),
        weighted_length=("weighted_length", "sum"),
    )
    grouped["mean_length_mm"] = np.where(
        grouped["abundance"] > 0.0,
        grouped["weighted_length"] / grouped["abundance"],
        np.nan,
    )
    return grouped[columns]


def _ensemble_daily_bands(run_daily: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "day",
        "abundance_p05",
        "abundance_p50",
        "abundance_p95",
        "biomass_g_p05",
        "biomass_g_p50",
        "biomass_g_p95",
        "mean_length_mm_p05",
        "mean_length_mm_p50",
        "mean_length_mm_p95",
    ]
    if run_daily.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for day, group in run_daily.groupby("day", sort=True):
        row: dict[str, object] = {"day": int(day)}
        for metric in ("abundance", "biomass_g", "mean_length_mm"):
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                row[f"{metric}_p05"] = math.nan
                row[f"{metric}_p50"] = math.nan
                row[f"{metric}_p95"] = math.nan
            else:
                row[f"{metric}_p05"] = float(values.quantile(0.05))
                row[f"{metric}_p50"] = float(values.quantile(0.50))
                row[f"{metric}_p95"] = float(values.quantile(0.95))
        rows.append(row)
    return pd.DataFrame.from_records(rows, columns=columns)


def _sensitivity_ranking(summary: pd.DataFrame, target: str = "final_abundance") -> pd.DataFrame:
    columns = ["parameter", "target", "pearson_r", "abs_pearson_r", "n"]
    param_columns = [col for col in summary.columns if col.startswith("param_")]
    if summary.empty or not param_columns or target not in summary:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    target_values = pd.to_numeric(summary[target], errors="coerce")
    for column in param_columns:
        values = pd.to_numeric(summary[column], errors="coerce")
        valid = values.notna() & target_values.notna()
        n = int(valid.sum())
        # Also guard the target's variance: when target is constant across
        # runs (e.g. tiny demo where every seed yields the same final
        # abundance), np.corrcoef divides by stddev=0 and emits a
        # ``RuntimeWarning: invalid value encountered in divide``.
        # (2026-05-26 software-test minor N1, Codex + Gemini.)
        if (
            n < 2
            or float(values[valid].nunique()) < 2
            or float(target_values[valid].nunique()) < 2
        ):
            corr = math.nan
        else:
            corr = float(values[valid].corr(target_values[valid]))
        rows.append(
            {
                "parameter": column.removeprefix("param_"),
                "target": target,
                "pearson_r": corr,
                "abs_pearson_r": abs(corr) if not math.isnan(corr) else math.nan,
                "n": n,
            }
        )
    return (
        pd.DataFrame.from_records(rows, columns=columns)
        .sort_values(["abs_pearson_r", "parameter"], ascending=[False, True], kind="mergesort")
        .reset_index(drop=True)
    )


def run_ibm_ensemble(
    scenario_path: str | Path,
    *,
    seeds: Sequence[int] | None = None,
    output_dir: str | Path | None = None,
) -> IBMEnsembleResult:
    """Run a scenario repeatedly with different seeds and summarize final states."""

    path = Path(scenario_path).resolve()
    data = load_ibm_scenario(path)
    block = _experiment_block(data, "ensemble")
    if seeds is None:
        raw_seeds = block.get("seeds", ())
        seeds = tuple(int(seed) for seed in raw_seeds) if isinstance(raw_seeds, Sequence) else ()
    run_seeds = tuple(int(seed) for seed in seeds)
    if not run_seeds:
        raise ValueError("IBM ensemble requires at least one seed")
    raw_params = block.get("parameters")
    parameter_grid = (
        _normalise_parameter_grid(cast(Mapping[str, object], raw_params))
        if isinstance(raw_params, Mapping) and raw_params
        else {}
    )
    parameter_sets = _parameter_combinations(parameter_grid) if parameter_grid else [{}]

    root = _experiment_root(path, data, "ensemble", output_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    daily_frames: list[pd.DataFrame] = []
    run_index = 0
    for parameter_index, overrides in enumerate(parameter_sets):
        for seed in run_seeds:
            run_label = f"seed_{seed}_params_{parameter_index:03d}"
            run_dir = root / f"{run_index:03d}_{run_label}"
            result, paths = run_ibm_scenario(
                path,
                scenario_overrides={"seed": seed},
                profile_overrides=overrides,
                output_dir_override=run_dir,
                run_label=run_label,
            )
            row = {
                "run_index": run_index,
                "run_label": run_label,
                "seed": seed,
                "parameter_index": parameter_index,
                "output_dir": str(run_dir),
                "manifest_path": paths["ibm_run_manifest"],
            }
            row.update({f"param_{name}": value for name, value in overrides.items()})
            row.update(_final_metrics(result))
            rows.append(row)
            daily = _daily_metrics(result)
            daily["run_index"] = run_index
            daily["seed"] = seed
            daily["parameter_index"] = parameter_index
            daily_frames.append(daily)
            run_index += 1

    summary = pd.DataFrame.from_records(rows)
    run_daily = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    daily_bands = _ensemble_daily_bands(run_daily)
    sensitivity = _sensitivity_ranking(summary)
    summary_path = root / "ibm_ensemble_summary.csv"
    daily_bands_path = root / "ibm_ensemble_daily_bands.csv"
    sensitivity_path = root / "ibm_ensemble_sensitivity.csv"
    summary.to_csv(summary_path, index=False)
    daily_bands.to_csv(daily_bands_path, index=False)
    sensitivity.to_csv(sensitivity_path, index=False)
    manifest_path = root / "ibm_ensemble_manifest.json"
    _write_json(
        manifest_path,
        {
            "scenario_path": str(path),
            "seeds": list(run_seeds),
            "parameter_grid": {name: list(values) for name, values in parameter_grid.items()},
            "n_runs": len(rows),
            "summary_path": str(summary_path),
            "daily_bands_path": str(daily_bands_path),
            "sensitivity_path": str(sensitivity_path),
        },
    )
    return IBMEnsembleResult(
        summary=summary,
        daily_bands=daily_bands,
        sensitivity=sensitivity,
        paths={
            "ibm_ensemble_summary": str(summary_path),
            "ibm_ensemble_daily_bands": str(daily_bands_path),
            "ibm_ensemble_sensitivity": str(sensitivity_path),
            "ibm_ensemble_manifest": str(manifest_path),
        },
    )


def parse_parameter_grid(specs: Sequence[str]) -> dict[str, tuple[float, ...]]:
    """Parse CLI parameter specs like ``base_daily_survival=0.99,1.0``."""

    grid: dict[str, tuple[float, ...]] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"Parameter grid entry must be NAME=VALUE[,VALUE...], got {spec!r}")
        name, raw_values = spec.split("=", 1)
        param = name.strip()
        if not param:
            raise ValueError(f"Parameter grid entry has an empty name: {spec!r}")
        values = tuple(float(part.strip()) for part in raw_values.split(",") if part.strip())
        if not values:
            raise ValueError(f"Parameter grid entry has no values: {spec!r}")
        grid[param] = values
    return grid


def _normalise_parameter_grid(grid: Mapping[str, object] | None) -> dict[str, tuple[float, ...]]:
    if not grid:
        raise ValueError("IBM calibration requires at least one parameter grid entry")
    defaults = SpeciesProfile()
    numeric_fields = {
        field.name
        for field in fields(SpeciesProfile)
        if isinstance(getattr(defaults, field.name), (int, float))
        and not isinstance(getattr(defaults, field.name), bool)
    }
    normalised: dict[str, tuple[float, ...]] = {}
    for name, raw_values in grid.items():
        if name not in numeric_fields:
            raise ValueError(f"Calibration parameter {name!r} is not a numeric SpeciesProfile field")
        if isinstance(raw_values, str) or not isinstance(raw_values, Sequence):
            raise ValueError(f"Calibration parameter {name!r} must provide a list of numeric values")
        values = tuple(float(value) for value in raw_values)
        if not values:
            raise ValueError(f"Calibration parameter {name!r} has no candidate values")
        normalised[name] = values
    return normalised


def _parameter_combinations(grid: Mapping[str, Sequence[float]]) -> list[dict[str, float]]:
    names = list(grid)
    return [
        {name: float(value) for name, value in zip(names, values, strict=True)}
        for values in product(*(grid[name] for name in names))
    ]


def _normalise_parameter_priors(priors: Mapping[str, object] | None) -> dict[str, tuple[float, float]]:
    grid = _normalise_parameter_grid(priors)
    normalised: dict[str, tuple[float, float]] = {}
    for name, values in grid.items():
        if len(values) != 2:
            raise ValueError(f"ABC prior for {name!r} must provide [low, high]")
        low = float(min(values))
        high = float(max(values))
        if low == high:
            raise ValueError(f"ABC prior for {name!r} must have distinct low/high bounds")
        normalised[name] = (low, high)
    return normalised


def _sample_parameter_priors(
    priors: Mapping[str, tuple[float, float]],
    *,
    n: int,
    rng: np.random.Generator,
) -> list[dict[str, float]]:
    names = list(priors)
    samples: list[dict[str, float]] = []
    for _ in range(n):
        samples.append(
            {
                name: float(rng.uniform(priors[name][0], priors[name][1]))
                for name in names
            }
        )
    return samples


def _calibration_merge(summary: pd.DataFrame, observed: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    if "day" not in observed or "abundance" not in observed:
        raise ValueError("Observed calibration table requires day and abundance columns")
    key_columns = ["day"] + [
        col for col in ("reach_id", "species") if col in summary.columns and col in observed.columns
    ]
    model = summary.copy()
    model["abundance"] = pd.to_numeric(model["abundance"], errors="coerce").fillna(0.0)
    model["biomass_g"] = pd.to_numeric(model["biomass_g"], errors="coerce").fillna(0.0)
    model["mean_length_mm"] = pd.to_numeric(model.get("mean_length_mm", np.nan), errors="coerce")
    model["weighted_length_mm"] = model["mean_length_mm"].fillna(0.0) * model["abundance"]
    model_grouped = model.groupby(key_columns, dropna=False, as_index=False).agg(
        abundance=("abundance", "sum"),
        biomass_g=("biomass_g", "sum"),
        weighted_length_mm=("weighted_length_mm", "sum"),
    )
    model_grouped["mean_length_mm"] = np.where(
        model_grouped["abundance"] > 0.0,
        model_grouped["weighted_length_mm"] / model_grouped["abundance"],
        np.nan,
    )
    observed_table = observed.copy()
    observed_table["abundance"] = pd.to_numeric(observed_table["abundance"], errors="coerce").fillna(0.0)
    metric_columns = ["abundance"]
    if "biomass_g" in observed_table:
        observed_table["biomass_g"] = pd.to_numeric(observed_table["biomass_g"], errors="coerce").fillna(0.0)
        metric_columns.append("biomass_g")
    if "mean_length_mm" in observed_table:
        observed_table["mean_length_mm"] = pd.to_numeric(observed_table["mean_length_mm"], errors="coerce")
        observed_table["weighted_length_mm"] = observed_table["mean_length_mm"].fillna(0.0) * observed_table["abundance"]
        metric_columns.append("mean_length_mm")
    observed_aggs: dict[str, tuple[str, str]] = {"abundance": ("abundance", "sum")}
    if "biomass_g" in metric_columns:
        observed_aggs["biomass_g"] = ("biomass_g", "sum")
    if "mean_length_mm" in metric_columns:
        observed_aggs["weighted_length_mm"] = ("weighted_length_mm", "sum")
    observed_grouped = observed_table.groupby(key_columns, dropna=False, as_index=False).agg(**observed_aggs)
    if "mean_length_mm" in metric_columns:
        observed_grouped["mean_length_mm"] = np.where(
            observed_grouped["abundance"] > 0.0,
            observed_grouped["weighted_length_mm"] / observed_grouped["abundance"],
            np.nan,
        )
    merged = model_grouped.merge(
        observed_grouped[[*key_columns, *metric_columns]],
        on=key_columns,
        how="inner",
        suffixes=("_model", "_observed"),
    )
    if merged.empty:
        raise ValueError("Observed calibration table shares no day/reach/species keys with model output")
    return merged, key_columns, metric_columns


def _score_population_summary(summary: pd.DataFrame, observed: pd.DataFrame) -> dict[str, object]:
    merged, _, metric_columns = _calibration_merge(summary, observed)
    diff = (
        pd.to_numeric(merged["abundance_model"], errors="coerce").fillna(0.0)
        - pd.to_numeric(merged["abundance_observed"], errors="coerce").fillna(0.0)
    )
    abundance_rmse = float((diff.pow(2).mean()) ** 0.5)
    metrics: dict[str, object] = {
        "score": abundance_rmse,
        "rmse_abundance": abundance_rmse,
        "n_points": int(len(merged)),
    }
    for metric in metric_columns:
        if metric == "abundance":
            continue
        model_values = pd.to_numeric(merged[f"{metric}_model"], errors="coerce")
        observed_values = pd.to_numeric(merged[f"{metric}_observed"], errors="coerce")
        metric_diff = model_values - observed_values
        metrics[f"rmse_{metric}"] = float((metric_diff.pow(2).mean()) ** 0.5)
    return metrics


def _metric_tolerance(metric: str, observed_value: float) -> float:
    if metric == "abundance":
        return max(1.0, abs(observed_value) * 0.10)
    if metric == "biomass_g":
        return max(1.0, abs(observed_value) * 0.15)
    if metric == "mean_length_mm":
        return 5.0
    return math.nan


def _calibration_metric_rows(
    candidate_id: str,
    summary: pd.DataFrame,
    observed: pd.DataFrame,
) -> list[dict[str, object]]:
    merged, key_columns, metric_columns = _calibration_merge(summary, observed)
    rows: list[dict[str, object]] = []
    for _, row in merged.iterrows():
        key_payload = {column: row[column] for column in key_columns}
        for metric in metric_columns:
            model_value = float(pd.to_numeric(pd.Series([row[f"{metric}_model"]]), errors="coerce").iloc[0])
            observed_value = float(pd.to_numeric(pd.Series([row[f"{metric}_observed"]]), errors="coerce").iloc[0])
            abs_error = abs(model_value - observed_value)
            tolerance = _metric_tolerance(metric, observed_value)
            relative_error = abs_error / abs(observed_value) if abs(observed_value) > 1e-12 else math.nan
            rows.append(
                {
                    "candidate_id": candidate_id,
                    **key_payload,
                    "metric": metric,
                    "model_value": model_value,
                    "observed_value": observed_value,
                    "abs_error": abs_error,
                    "relative_error": relative_error,
                    "tolerance": tolerance,
                    "passed": bool(abs_error <= tolerance) if math.isfinite(tolerance) else pd.NA,
                }
            )
    return rows


def _profile_for_scenario(
    scenario_path: Path,
    data: Mapping[str, Any],
    overrides: Mapping[str, float],
) -> SpeciesProfile:
    population = data.get("population")
    species = "rainbow_trout"
    if isinstance(population, dict):
        species = str(population.get("default_species", species))
    profile = SpeciesProfile(species=species)
    profile_block = data.get("profile")
    if isinstance(profile_block, dict):
        profile_uri = profile_block.get("uri")
        if isinstance(profile_uri, str) and profile_uri.strip():
            profile = load_species_profile(_resolve_from(scenario_path.parent, profile_uri))
    return replace(profile, **dict(overrides))


def run_ibm_calibration(
    scenario_path: str | Path,
    *,
    observed_path: str | Path | None = None,
    parameter_grid: Mapping[str, object] | None = None,
    output_dir: str | Path | None = None,
    method: str = "grid",
    samples: int = 64,
    acceptance_fraction: float = 0.10,
    tolerance: float | None = None,
) -> IBMCalibrationResult:
    """Run a grid-search calibration against observed daily abundance."""

    path = Path(scenario_path).resolve()
    data = load_ibm_scenario(path)
    block = _experiment_block(data, "calibration")
    if method == "grid" and isinstance(block.get("method"), str):
        method = str(block["method"])
    if observed_path is None:
        raw_observed = block.get("observed")
        if not isinstance(raw_observed, str) or not raw_observed.strip():
            raise ValueError("IBM calibration requires --observed or experiments.calibration.observed")
        observed_path = raw_observed
    if parameter_grid is None:
        raw_grid = block.get("parameters")
        parameter_grid = cast(Mapping[str, object] | None, raw_grid if isinstance(raw_grid, dict) else None)
    if method == "abc":
        raw_samples = block.get("samples")
        if isinstance(raw_samples, int):
            samples = raw_samples
        raw_acceptance = block.get("acceptance_fraction")
        if isinstance(raw_acceptance, int | float):
            acceptance_fraction = float(raw_acceptance)
        raw_tolerance = block.get("tolerance")
        if isinstance(raw_tolerance, int | float):
            tolerance = float(raw_tolerance)
        return run_ibm_abc_calibration(
            path,
            observed_path=observed_path,
            parameter_priors=parameter_grid,
            output_dir=output_dir,
            samples=samples,
            acceptance_fraction=acceptance_fraction,
            tolerance=tolerance,
        )
    if method != "grid":
        raise ValueError(f"Unsupported IBM calibration method {method!r}; expected grid or abc")
    grid = _normalise_parameter_grid(parameter_grid)
    combinations = _parameter_combinations(grid)
    observed = _read_table(_resolve_from(path.parent, observed_path))

    root = _experiment_root(path, data, "calibration", output_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    for idx, overrides in enumerate(combinations):
        run_label = f"candidate_{idx:03d}"
        run_dir = root / run_label
        result, paths = run_ibm_scenario(
            path,
            profile_overrides=overrides,
            output_dir_override=run_dir,
            run_label=run_label,
        )
        row: dict[str, object] = {
            "candidate_id": run_label,
            "output_dir": str(run_dir),
            "manifest_path": paths["ibm_run_manifest"],
        }
        row.update({f"param_{name}": value for name, value in overrides.items()})
        row.update(_score_population_summary(result.population_summary, observed))
        row.update(_final_metrics(result))
        rows.append(row)
        metric_rows.extend(_calibration_metric_rows(run_label, result.population_summary, observed))

    summary = pd.DataFrame.from_records(rows).sort_values(
        ["score", "candidate_id"],
        kind="mergesort",
    )
    summary_path = root / "ibm_calibration_summary.csv"
    metrics_path = root / "ibm_calibration_metrics.csv"
    summary.to_csv(summary_path, index=False)
    pd.DataFrame.from_records(metric_rows).to_csv(metrics_path, index=False)
    best_row = summary.iloc[0]
    best_parameters = {name: float(best_row[f"param_{name}"]) for name in grid}
    best_profile_path = write_species_profile(
        _profile_for_scenario(path, data, best_parameters),
        root / "best_profile.yaml",
    )
    manifest_path = root / "ibm_calibration_manifest.json"
    _write_json(
        manifest_path,
        {
            "scenario_path": str(path),
            "observed_path": str(_resolve_from(path.parent, observed_path)),
            "n_candidates": len(rows),
            "objective": "rmse_abundance",
            "best_parameters": best_parameters,
            "summary_path": str(summary_path),
            "metrics_path": str(metrics_path),
            "best_profile_path": str(best_profile_path),
        },
    )
    return IBMCalibrationResult(
        summary=summary,
        best_parameters=best_parameters,
        paths={
            "ibm_calibration_summary": str(summary_path),
            "ibm_calibration_metrics": str(metrics_path),
            "ibm_calibration_manifest": str(manifest_path),
            "ibm_calibration_best_profile": str(best_profile_path),
        },
    )


def run_ibm_abc_calibration(
    scenario_path: str | Path,
    *,
    observed_path: str | Path,
    parameter_priors: Mapping[str, object] | None,
    output_dir: str | Path | None = None,
    samples: int = 64,
    acceptance_fraction: float = 0.10,
    tolerance: float | None = None,
) -> IBMCalibrationResult:
    """Run approximate Bayesian calibration by prior sampling and rejection."""

    if samples <= 0:
        raise ValueError("ABC calibration requires samples > 0")
    if not 0.0 < acceptance_fraction <= 1.0:
        raise ValueError("ABC acceptance_fraction must be in (0, 1]")
    path = Path(scenario_path).resolve()
    data = load_ibm_scenario(path)
    block = _experiment_block(data, "calibration")
    priors = _normalise_parameter_priors(parameter_priors)
    observed = _read_table(_resolve_from(path.parent, observed_path))
    seed = int(block.get("seed", 271828))
    rng = np.random.default_rng(seed)
    candidates = _sample_parameter_priors(priors, n=samples, rng=rng)

    root = _experiment_root(path, data, "calibration", output_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    for idx, overrides in enumerate(candidates):
        run_label = f"abc_{idx:03d}"
        run_dir = root / run_label
        result, paths = run_ibm_scenario(
            path,
            profile_overrides=overrides,
            output_dir_override=run_dir,
            run_label=run_label,
        )
        row: dict[str, object] = {
            "candidate_id": run_label,
            "output_dir": str(run_dir),
            "manifest_path": paths["ibm_run_manifest"],
        }
        row.update({f"param_{name}": value for name, value in overrides.items()})
        row.update(_score_population_summary(result.population_summary, observed))
        row.update(_final_metrics(result))
        rows.append(row)
        metric_rows.extend(_calibration_metric_rows(run_label, result.population_summary, observed))

    summary = pd.DataFrame.from_records(rows).sort_values(
        ["score", "candidate_id"],
        kind="mergesort",
    )
    accepted_n = max(1, int(math.ceil(len(summary) * acceptance_fraction)))
    if tolerance is not None:
        accepted = pd.to_numeric(summary["score"], errors="coerce") <= float(tolerance)
        if not bool(accepted.any()):
            accepted.iloc[:accepted_n] = True
    else:
        accepted = pd.Series(False, index=summary.index)
        accepted.iloc[:accepted_n] = True
    summary["accepted"] = accepted.to_numpy(dtype=bool)
    accepted_summary = summary[summary["accepted"]].copy()
    best_row = summary.iloc[0]
    best_parameters = {name: float(best_row[f"param_{name}"]) for name in priors}

    summary_path = root / "ibm_abc_summary.csv"
    accepted_path = root / "ibm_abc_accepted.csv"
    metrics_path = root / "ibm_abc_metrics.csv"
    summary.to_csv(summary_path, index=False)
    accepted_summary.to_csv(accepted_path, index=False)
    pd.DataFrame.from_records(metric_rows).to_csv(metrics_path, index=False)
    best_profile_path = write_species_profile(
        _profile_for_scenario(path, data, best_parameters),
        root / "best_profile.yaml",
    )
    manifest_path = root / "ibm_abc_manifest.json"
    posterior: dict[str, dict[str, float]] = {}
    for name in priors:
        values = pd.to_numeric(accepted_summary[f"param_{name}"], errors="coerce")
        posterior[name] = {
            "mean": float(values.mean()),
            "p05": float(values.quantile(0.05)),
            "p50": float(values.quantile(0.50)),
            "p95": float(values.quantile(0.95)),
        }
    _write_json(
        manifest_path,
        {
            "scenario_path": str(path),
            "observed_path": str(_resolve_from(path.parent, observed_path)),
            "method": "abc",
            "seed": seed,
            "samples": samples,
            "acceptance_fraction": acceptance_fraction,
            "tolerance": tolerance,
            "n_accepted": int(len(accepted_summary)),
            "objective": "rmse_abundance",
            "priors": {name: list(bounds) for name, bounds in priors.items()},
            "posterior_summary": posterior,
            "best_parameters": best_parameters,
            "summary_path": str(summary_path),
            "accepted_path": str(accepted_path),
            "metrics_path": str(metrics_path),
            "best_profile_path": str(best_profile_path),
        },
    )
    return IBMCalibrationResult(
        summary=summary,
        best_parameters=best_parameters,
        paths={
            "ibm_abc_summary": str(summary_path),
            "ibm_abc_accepted": str(accepted_path),
            "ibm_abc_metrics": str(metrics_path),
            "ibm_abc_manifest": str(manifest_path),
            "ibm_calibration_best_profile": str(best_profile_path),
        },
    )


__all__ = [
    "IBMCalibrationResult",
    "IBMEnsembleResult",
    "parse_parameter_grid",
    "run_ibm_abc_calibration",
    "run_ibm_calibration",
    "run_ibm_ensemble",
]
