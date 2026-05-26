"""Calibration helpers for OpenLimno hydraulic solvers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from openlimno.hydro.builtin_1d import Builtin1D, CrossSection


@dataclass(frozen=True)
class Builtin1DCalibrationScore:
    """Score for one builtin-1d normal-depth calibration candidate."""

    slope: float
    manning_n: float
    score: float
    wse_rmse_m: float
    wse_bias_m: float
    velocity_rmse_ms: float
    velocity_bias_ms: float
    n_wse: int
    n_velocity: int


@dataclass(frozen=True)
class Builtin1DCalibrationResult:
    """Grid-search result for builtin-1d normal-depth calibration."""

    best: Builtin1DCalibrationScore
    candidates: pd.DataFrame


def _clone_section_with_n(section: CrossSection, manning_n: float) -> CrossSection:
    return CrossSection(
        station_m=float(section.station_m),
        distance_m=np.asarray(section.distance_m, dtype=float),
        elevation_m=np.asarray(section.elevation_m, dtype=float),
        manning_n=float(manning_n),
    )


def _normalise_discharges(
    discharges_m3s: float | Sequence[float] | pd.Series | np.ndarray,
    n_sections: int,
) -> np.ndarray:
    # 2026-05-26 mypy --strict fix: numpy stubs reject ``dtype=float`` for
    # ``np.full`` _ScalarT (HEAD numpy types). Use np.float64 explicitly.
    if np.isscalar(discharges_m3s):
        out = np.full(n_sections, float(discharges_m3s), dtype=np.float64)
    else:
        out = np.asarray(discharges_m3s, dtype=np.float64)
    if out.shape != (n_sections,):
        raise ValueError("discharges_m3s must be scalar or match the number of sections")
    # 2026-05-26 mypy --strict fix: ``np.any(out < 0.0)`` is rejected by
    # mypy (operand types for <). Use the ndarray method form so the
    # comparison binds through numpy.
    if (~np.isfinite(out)).any() or (out < 0.0).any():
        raise ValueError("discharges_m3s values must be finite and non-negative")
    return out


def predict_builtin1d_normal_depth(
    sections: Sequence[CrossSection],
    discharges_m3s: float | Sequence[float] | pd.Series | np.ndarray,
    *,
    slope: float,
    manning_n: float,
) -> pd.DataFrame:
    """Predict per-section WSE and velocity for one slope/Manning-n candidate."""

    if slope <= 0.0:
        raise ValueError("slope must be positive")
    if manning_n <= 0.0:
        raise ValueError("manning_n must be positive")
    if not sections:
        raise ValueError("at least one cross-section is required")
    discharges = _normalise_discharges(discharges_m3s, len(sections))
    solver = Builtin1D(slope=float(slope))
    rows: list[dict[str, float]] = []
    for section, discharge in zip(sections, discharges, strict=True):
        xs = _clone_section_with_n(section, manning_n)
        result = solver.solve_normal_depth(xs, float(discharge), float(slope))
        rows.append(
            {
                "station_m": float(result.station_m),
                "discharge_m3s": float(result.discharge_m3s),
                "water_surface_m": float(result.water_surface_m),
                "depth_m": float(result.depth_mean_m),
                "velocity_ms": float(result.velocity_mean_ms),
                "area_m2": float(result.area_m2),
                "top_width_m": float(result.top_width_m),
                "hydraulic_radius_m": float(result.hydraulic_radius_m),
            }
        )
    return pd.DataFrame(rows)


def _nearest_error_stats(
    observed: pd.DataFrame | None,
    predicted: pd.DataFrame,
    *,
    station_column: str,
    observed_column: str,
    predicted_column: str,
) -> tuple[float, float, int]:
    if observed is None or observed.empty or observed_column not in observed:
        return float("nan"), float("nan"), 0
    if station_column not in observed:
        raise ValueError(f"observed table is missing station column {station_column!r}")
    obs = observed[[station_column, observed_column]].copy()
    obs[station_column] = pd.to_numeric(obs[station_column], errors="coerce")
    obs[observed_column] = pd.to_numeric(obs[observed_column], errors="coerce")
    obs = obs.dropna(subset=[station_column, observed_column])
    if obs.empty:
        return float("nan"), float("nan"), 0
    stations = predicted["station_m"].to_numpy(dtype=float)
    if len(stations) == 0:
        raise ValueError("predicted table is empty")
    indices = np.abs(obs[station_column].to_numpy(dtype=float)[:, None] - stations[None, :]).argmin(
        axis=1
    )
    predicted_values = predicted[predicted_column].to_numpy(dtype=float)[indices]
    errors = predicted_values - obs[observed_column].to_numpy(dtype=float)
    return float(np.sqrt(np.mean(errors**2))), float(np.mean(errors)), int(len(errors))


def calibrate_builtin1d_normal_depth(
    sections: Sequence[CrossSection],
    discharges_m3s: float | Sequence[float] | pd.Series | np.ndarray,
    *,
    wse_observations: pd.DataFrame | None = None,
    velocity_observations: pd.DataFrame | None = None,
    station_column: str = "station_m",
    wse_column: str = "water_surface_m",
    velocity_column: str = "velocity_ms",
    slopes: Sequence[float] | None = None,
    manning_ns: Sequence[float] | None = None,
    wse_weight: float = 1.0,
    velocity_weight: float = 1.0,
) -> Builtin1DCalibrationResult:
    """Grid-search slope and Manning n against nearest-station observations.

    The builtin normal-depth equation is sensitive to the ratio between
    Manning n and slope, so close candidates may be physically equifinal. The
    returned candidate table should be inspected before accepting a final
    parameter set.
    """

    if wse_observations is None and velocity_observations is None:
        raise ValueError("at least one observed WSE or velocity table is required")
    if wse_weight < 0.0 or velocity_weight < 0.0:
        raise ValueError("calibration weights must be non-negative")
    if wse_weight == 0.0 and velocity_weight == 0.0:
        raise ValueError("at least one calibration weight must be positive")

    slope_values = np.geomspace(5e-5, 1e-3, 16) if slopes is None else slopes
    manning_values = np.linspace(0.025, 0.08, 12) if manning_ns is None else manning_ns
    slope_grid = tuple(float(v) for v in slope_values)
    n_grid = tuple(float(v) for v in manning_values)
    if not slope_grid or any(v <= 0.0 for v in slope_grid):
        raise ValueError("slopes must contain positive values")
    if not n_grid or any(v <= 0.0 for v in n_grid):
        raise ValueError("manning_ns must contain positive values")

    rows: list[dict[str, float | int]] = []
    for slope in slope_grid:
        for manning_n in n_grid:
            predicted = predict_builtin1d_normal_depth(
                sections,
                discharges_m3s,
                slope=slope,
                manning_n=manning_n,
            )
            wse_rmse, wse_bias, n_wse = _nearest_error_stats(
                wse_observations,
                predicted,
                station_column=station_column,
                observed_column=wse_column,
                predicted_column="water_surface_m",
            )
            velocity_rmse, velocity_bias, n_velocity = _nearest_error_stats(
                velocity_observations,
                predicted,
                station_column=station_column,
                observed_column=velocity_column,
                predicted_column="velocity_ms",
            )
            score = 0.0
            scored = False
            if n_wse:
                score += wse_weight * wse_rmse
                scored = True
            if n_velocity:
                score += velocity_weight * velocity_rmse
                scored = True
            if not scored:
                score = float("inf")
            rows.append(
                {
                    "slope": slope,
                    "manning_n": manning_n,
                    "score": score,
                    "wse_rmse_m": wse_rmse,
                    "wse_bias_m": wse_bias,
                    "velocity_rmse_ms": velocity_rmse,
                    "velocity_bias_ms": velocity_bias,
                    "n_wse": n_wse,
                    "n_velocity": n_velocity,
                }
            )

    candidates = pd.DataFrame(rows).sort_values(["score", "wse_rmse_m", "velocity_rmse_ms"])
    if candidates.empty or not np.isfinite(float(candidates.iloc[0]["score"])):
        raise ValueError("no calibration candidate could be scored from the observations")
    row = candidates.iloc[0]
    best = Builtin1DCalibrationScore(
        slope=float(row["slope"]),
        manning_n=float(row["manning_n"]),
        score=float(row["score"]),
        wse_rmse_m=float(row["wse_rmse_m"]),
        wse_bias_m=float(row["wse_bias_m"]),
        velocity_rmse_ms=float(row["velocity_rmse_ms"]),
        velocity_bias_ms=float(row["velocity_bias_ms"]),
        n_wse=int(row["n_wse"]),
        n_velocity=int(row["n_velocity"]),
    )
    return Builtin1DCalibrationResult(best=best, candidates=candidates.reset_index(drop=True))
