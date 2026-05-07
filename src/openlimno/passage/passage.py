"""Fish swimming model + passage success rate (η_P).

SPEC §4.3, ADR-0007. Three-band swimming model (Bell 1986):
- burst (< 20 s)
- prolonged (20 s – 200 min)
- sustained (> 200 min)

Each band's max speed depends on body length (~10/4/2 BL/s) and temperature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from .culvert import Culvert

LifeStage = Literal["fry", "juvenile", "adult", "spawner"]


@dataclass
class SwimmingModel:
    """Per-stage burst/prolonged/sustained speeds with temperature dependence.

    Stored as a table keyed by (species, stage); each entry has a 1-D
    interpolation against temperature for each speed regime.
    """

    species: str
    stage: LifeStage
    body_length_m: float
    # Each list: [(temp_C, speed_ms), ...]
    burst_curve: list[tuple[float, float]] = field(default_factory=list)
    prolonged_curve: list[tuple[float, float]] = field(default_factory=list)
    sustained_curve: list[tuple[float, float]] = field(default_factory=list)

    def _interp(self, curve: list[tuple[float, float]], temp_C: float) -> float:
        if not curve:
            return 0.0
        Ts = np.array([p[0] for p in curve])
        Vs = np.array([p[1] for p in curve])
        return float(np.interp(temp_C, Ts, Vs, left=Vs[0], right=Vs[-1]))

    def burst(self, temp_C: float) -> float:
        return self._interp(self.burst_curve, temp_C)

    def prolonged(self, temp_C: float) -> float:
        return self._interp(self.prolonged_curve, temp_C)

    def sustained(self, temp_C: float) -> float:
        return self._interp(self.sustained_curve, temp_C)


@dataclass
class PassageResult:
    """Result of η_P calculation."""

    discharge_m3s: float
    barrel_velocity_ms: float
    barrel_depth_m: float
    fish_speed_ms: float  # the swim speed used
    swim_band: Literal["burst", "prolonged", "sustained"]
    eta_P: float  # passage success rate ∈ [0,1]
    monte_carlo_std: float = 0.0  # std-dev of η_P if MC; else 0

    def summary(self) -> str:
        return (
            f"Q={self.discharge_m3s:.2f} m3/s  V_barrel={self.barrel_velocity_ms:.2f} m/s  "
            f"V_fish_{self.swim_band}={self.fish_speed_ms:.2f} m/s  "
            f"eta_P={self.eta_P:.3f}"
        )


def _select_swim_band(
    barrel_length_m: float,
    swim: SwimmingModel,
    temp_C: float,
) -> tuple[Literal["burst", "prolonged", "sustained"], float]:
    """Select the appropriate swim regime from culvert length.

    Heuristic (Bell 1986):
      length < V_burst * 20 s       → burst
      length < V_prolonged * 12000 s→ prolonged
      else                          → sustained
    """
    Vb, Vp, Vs = swim.burst(temp_C), swim.prolonged(temp_C), swim.sustained(temp_C)
    # Time to traverse at each speed
    if Vb > 0 and barrel_length_m < Vb * 20.0:
        return "burst", Vb
    if Vp > 0 and barrel_length_m < Vp * 200.0 * 60.0:
        return "prolonged", Vp
    return "sustained", Vs


def passage_success_rate(
    culvert: Culvert,
    swim: SwimmingModel,
    discharge_m3s: float,
    temp_C: float = 12.0,
    monte_carlo: int = 0,
    seed: int | None = None,
) -> PassageResult:
    """Compute η_P (passage success rate) for given conditions.

    Deterministic mode (default, monte_carlo=0):
        η_P = 1 if V_fish > V_barrel else 0; smoothed via logistic to ∈ [0,1].

    Monte-Carlo mode (monte_carlo > 0):
        Sample fish length (lognormal around swim.body_length_m, CV=0.15) and
        temperature (±2 °C). Return mean η_P and std.

    Note: η_P only. Combining with η_A is the user's responsibility (ADR-0007).
    """
    if discharge_m3s <= 0:
        return PassageResult(
            discharge_m3s=discharge_m3s,
            barrel_velocity_ms=0.0,
            barrel_depth_m=0.0,
            fish_speed_ms=0.0,
            swim_band="sustained",
            eta_P=1.0,
        )

    V_barrel, h_barrel = culvert.barrel_velocity(discharge_m3s)
    band, V_fish = _select_swim_band(culvert.length_m, swim, temp_C)

    def smoothed_eta(v_fish: float, v_barrel: float) -> float:
        # Logistic transition centered at v_barrel; half-width = 0.05 m/s
        # eta_P → 1 when v_fish >> v_barrel; 0 when v_fish << v_barrel
        if v_barrel <= 0:
            return 1.0
        z = (v_fish - v_barrel) / 0.1
        return float(1.0 / (1.0 + np.exp(-z)))

    if monte_carlo <= 0:
        eta = smoothed_eta(V_fish, V_barrel)
        return PassageResult(
            discharge_m3s=discharge_m3s,
            barrel_velocity_ms=V_barrel,
            barrel_depth_m=h_barrel,
            fish_speed_ms=V_fish,
            swim_band=band,
            eta_P=eta,
        )

    # Monte Carlo
    rng = np.random.default_rng(seed)
    eta_samples = np.empty(monte_carlo)
    bands: list[str] = []
    for i in range(monte_carlo):
        L_factor = rng.lognormal(mean=0.0, sigma=0.15)
        T_sample = float(rng.normal(temp_C, 2.0))
        # Scale fish swim speeds by length factor (BL-proportional)
        Vb = swim.burst(T_sample) * L_factor
        Vp = swim.prolonged(T_sample) * L_factor
        Vs = swim.sustained(T_sample) * L_factor
        if Vb > 0 and culvert.length_m < Vb * 20.0:
            v_fish, b = Vb, "burst"
        elif Vp > 0 and culvert.length_m < Vp * 200.0 * 60.0:
            v_fish, b = Vp, "prolonged"
        else:
            v_fish, b = Vs, "sustained"
        eta_samples[i] = smoothed_eta(v_fish, V_barrel)
        bands.append(b)

    return PassageResult(
        discharge_m3s=discharge_m3s,
        barrel_velocity_ms=V_barrel,
        barrel_depth_m=h_barrel,
        fish_speed_ms=V_fish,
        swim_band=band,  # central
        eta_P=float(eta_samples.mean()),
        monte_carlo_std=float(eta_samples.std()),
    )


# ----------------------------------------------------------
# WEDM loader
# ----------------------------------------------------------
def load_swimming_model_from_parquet(
    path: str | Path, species: str, stage: LifeStage
) -> SwimmingModel:
    """Load swimming_performance.parquet and build a SwimmingModel.

    Expects rows with: species, stage, temp_C, burst_ms, prolonged_ms, sustained_ms,
    body_length_m.
    """
    df = pd.read_parquet(path)
    sub = df[(df["species"] == species) & (df["stage"] == stage)].sort_values("temp_C")
    if sub.empty:
        raise ValueError(f"No swim data for ({species}, {stage}) in {path}")
    body_length = float(sub["body_length_m"].iloc[0])
    return SwimmingModel(
        species=species,
        stage=stage,  # type: ignore[arg-type]
        body_length_m=body_length,
        burst_curve=list(zip(sub["temp_C"], sub["burst_ms"], strict=False)),
        prolonged_curve=list(zip(sub["temp_C"], sub["prolonged_ms"], strict=False)),
        sustained_curve=list(zip(sub["temp_C"], sub["sustained_ms"], strict=False)),
    )
