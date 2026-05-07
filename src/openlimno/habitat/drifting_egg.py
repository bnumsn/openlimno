"""Drifting-egg evaluation. SPEC §4.2.6, ADR none yet (data model in §3.1.3).

Models 1D Lagrangian drift of pelagic fish eggs (e.g. Asian carps / silver carp /
copper fish) for downstream survival until hatch:

- Drift trajectory: dx/dt = u(x, t)
- Hatch time: integral of (1 / hatch_days(T)) until equals 1
- Mortality: cumulative time fraction below ``mortality_velocity_threshold``

Inputs (from ``drifting_egg_params.parquet`` + 1D hydraulic time series):
    * spawning point x0
    * 1D velocity field u(x) (M2: steady; M3+: u(x, t))
    * 1D temperature field T(x) supplied as forcing (1.0 doesn't run thermal)
    * drifting_egg_params row for the species
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class DriftingEggResult:
    """Per-spawning-point drift evaluation."""

    species: str
    spawning_station_m: float
    hatch_station_m: float        # downstream distance where hatch completed
    drift_distance_km: float
    hatch_temp_C_mean: float
    mortality_fraction: float     # ∈ [0,1]; fraction of trajectory in slow water
    success: bool                 # True if hatch reached AND mortality < 0.5
    trajectory: pd.DataFrame      # columns: time_s, station_m, depth_m, velocity_ms, temp_C, hatch_progress

    def summary(self) -> str:
        return (
            f"{self.species}: spawn at {self.spawning_station_m:.0f} m → "
            f"hatch at {self.hatch_station_m:.0f} m "
            f"({self.drift_distance_km:.1f} km), mortality={self.mortality_fraction:.2f}, "
            f"success={self.success}"
        )


def _hatch_days_at_temp(curve: list[tuple[float, float]], temp_C: float) -> float:
    """Interpolate hatch_temp_days curve. Returns days to hatch at given temp."""
    Ts = np.array([p[0] for p in curve])
    Ds = np.array([p[1] for p in curve])
    return float(np.interp(temp_C, Ts, Ds, left=Ds[0], right=Ds[-1]))


def evaluate_drifting_egg(
    *,
    species: str,
    spawning_station_m: float,
    velocity_along_reach: dict[float, float],  # station_m -> velocity_ms
    temperature_along_reach: dict[float, float],  # station_m -> temp_C
    hatch_temp_days_curve: list[tuple[float, float]],
    mortality_velocity_threshold_ms: float,
    dt_s: float = 60.0,
    max_drift_km: float = 200.0,
) -> DriftingEggResult:
    """Drift a single egg cohort downstream.

    Velocity and temperature fields are given as station→value mappings; we
    interpolate piecewise-linearly along the route. Marching downstream until
    hatch completed or ``max_drift_km`` exceeded.
    """
    stations = np.array(sorted(velocity_along_reach.keys()))
    velocities = np.array([velocity_along_reach[s] for s in stations])
    temperatures = np.array([temperature_along_reach[s] for s in stations])

    if velocities.max() <= 0:
        raise ValueError("All-zero velocities: eggs cannot drift")

    x = spawning_station_m
    t_s = 0.0
    hatch_progress = 0.0
    slow_time_s = 0.0
    total_time_s = 0.0
    rows: list[dict[str, float]] = []
    temps_drifted: list[float] = []

    while True:
        u = float(np.interp(x, stations, velocities))
        T = float(np.interp(x, stations, temperatures))

        # Mortality counter: low velocity time
        if u < mortality_velocity_threshold_ms:
            slow_time_s += dt_s
        total_time_s += dt_s

        # Advance hatch progress: 1 / hatch_days at this T
        hatch_days = _hatch_days_at_temp(hatch_temp_days_curve, T)
        hatch_seconds = hatch_days * 86400.0 if hatch_days > 0 else 1e30
        hatch_progress += dt_s / hatch_seconds
        temps_drifted.append(T)

        rows.append({
            "time_s": t_s,
            "station_m": x,
            "velocity_ms": u,
            "temp_C": T,
            "hatch_progress": hatch_progress,
        })

        # Step downstream
        x_next = x + u * dt_s
        # Boundary checks
        drift_km = (x_next - spawning_station_m) / 1000.0
        if drift_km > max_drift_km:
            break
        if hatch_progress >= 1.0:
            x = x_next
            t_s += dt_s
            break
        if x_next > stations.max():
            # Past the modeled reach end
            x = x_next
            t_s += dt_s
            break
        x = x_next
        t_s += dt_s

    df = pd.DataFrame(rows)
    drift_distance_km = (x - spawning_station_m) / 1000.0
    mortality = slow_time_s / total_time_s if total_time_s > 0 else 1.0

    return DriftingEggResult(
        species=species,
        spawning_station_m=spawning_station_m,
        hatch_station_m=x,
        drift_distance_km=drift_distance_km,
        hatch_temp_C_mean=float(np.mean(temps_drifted)),
        mortality_fraction=mortality,
        success=hatch_progress >= 1.0 and mortality < 0.5,
        trajectory=df,
    )


def load_drifting_egg_params(path: str | Path, species: str) -> dict[str, object]:
    """Load drifting_egg_params.parquet entry for a species."""
    df = pd.read_parquet(path)
    sub = df[df["species"] == species]
    if sub.empty:
        raise ValueError(f"No drifting_egg_params for species {species}")
    row = sub.iloc[0]
    return {
        "drift_distance_km_min": float(row["drift_distance_km_min"]),
        "drift_distance_km_max": float(row["drift_distance_km_max"]),
        "hatch_temp_days_curve": [
            (float(t), float(d)) for t, d in row["hatch_temp_days"]
        ],
        "mortality_velocity_threshold_ms": float(
            row["mortality_velocity_threshold_ms"]
        ),
    }


__all__ = [
    "DriftingEggResult",
    "evaluate_drifting_egg",
    "load_drifting_egg_params",
]
