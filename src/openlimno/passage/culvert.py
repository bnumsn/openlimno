"""Culvert hydraulics for fish passage. SPEC §4.3.1; HY-8 inspired.

M1 simplification: compute outlet velocity and barrel velocity assuming
inlet-controlled flow with normal depth in the barrel (subcritical).
For a rigorous HY-8 implementation see HEC-22 / HY-8 source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

CulvertShape = Literal["circular", "box", "arch", "elliptical"]
CulvertMaterial = Literal[
    "concrete", "corrugated_metal", "smooth_metal", "plastic", "natural"
]

# Manning's n by material (Chow 1959 + FHWA HY-8)
MANNING_N: dict[CulvertMaterial, float] = {
    "concrete": 0.013,
    "corrugated_metal": 0.024,
    "smooth_metal": 0.012,
    "plastic": 0.011,
    "natural": 0.030,
}


@dataclass
class Culvert:
    """A single road-crossing culvert.

    M1: only circular and box supported in barrel velocity calc; others coerce
    to equivalent hydraulic radius approximations.
    """

    length_m: float
    diameter_or_width_m: float
    slope_percent: float
    material: CulvertMaterial = "concrete"
    shape: CulvertShape = "circular"
    embedment_m: float = 0.0
    height_m: float | None = None  # for box/arch; defaults to width

    @property
    def manning_n(self) -> float:
        return MANNING_N[self.material]

    @property
    def slope(self) -> float:
        return self.slope_percent / 100.0

    def barrel_velocity(self, discharge_m3s: float) -> tuple[float, float]:
        """Return (mean velocity in barrel, water depth in barrel).

        Solves Manning's equation for normal depth in the barrel cross-section.
        """
        n = self.manning_n
        S = self.slope
        if S <= 0 or discharge_m3s <= 0:
            return 0.0, 0.0

        if self.shape == "circular":
            return self._circular_normal(discharge_m3s, n, S)
        if self.shape == "box":
            return self._box_normal(discharge_m3s, n, S)
        # Arch/elliptical fallback: approximate as box of equivalent hydraulic radius
        return self._box_normal(discharge_m3s, n, S)

    def _circular_normal(
        self, Q: float, n: float, S: float
    ) -> tuple[float, float]:
        """Normal depth in a partial-flowing circular culvert."""
        D = self.diameter_or_width_m

        def Q_at_h(h: float) -> float:
            if h <= 0:
                return 0.0
            if h >= D:
                # Full flow; use full-pipe formula
                A = np.pi * (D / 2) ** 2
                P = np.pi * D
                R = A / P  # = D/4
                return (1.0 / n) * A * R ** (2.0 / 3.0) * S ** 0.5
            # Partial: chord + circular segment
            r = D / 2
            theta = 2 * np.arccos(1 - h / r)  # central angle
            A = (r ** 2) * (theta - np.sin(theta)) / 2
            P = r * theta
            R = A / P if P > 0 else 0.0
            return (1.0 / n) * A * R ** (2.0 / 3.0) * S ** 0.5

        # Bisection to find h
        lo, hi = 1e-4, D - 1e-4
        if Q_at_h(hi) < Q:  # overflow regime; return full pipe
            A = np.pi * (D / 2) ** 2
            return Q / A, D
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if Q_at_h(mid) < Q:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-5:
                break
        h = 0.5 * (lo + hi)
        # Recompute area at h
        r = D / 2
        theta = 2 * np.arccos(1 - h / r)
        A = (r ** 2) * (theta - np.sin(theta)) / 2
        v = Q / A if A > 0 else 0.0
        return v, h

    def _box_normal(
        self, Q: float, n: float, S: float
    ) -> tuple[float, float]:
        """Normal depth in a rectangular box culvert."""
        b = self.diameter_or_width_m
        H = self.height_m or b

        def Q_at_h(h: float) -> float:
            if h <= 0:
                return 0.0
            h_eff = min(h, H)
            A = b * h_eff
            P = b + 2 * h_eff
            R = A / P if P > 0 else 0.0
            return (1.0 / n) * A * R ** (2.0 / 3.0) * S ** 0.5

        lo, hi = 1e-4, H - 1e-4
        if Q_at_h(hi) < Q:
            return Q / (b * H), H  # pressurised; rough approximation
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if Q_at_h(mid) < Q:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-5:
                break
        h = 0.5 * (lo + hi)
        v = Q / (b * h) if h > 0 else 0.0
        return v, h
