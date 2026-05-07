"""Built-in 1D hydraulic solver. SPEC §4.1.1, ADR-0003.

M1 scope: per-section Manning normal-depth solver (PHABSIM/MANSQ equivalent).
M2 scope: standard-step backwater profile (PHABSIM/IFG4 equivalent).

References:
    Chow, V.T. (1959) Open-Channel Hydraulics, McGraw-Hill, ch. 5 + 10.
    Bovee 1986, PHABSIM Reference Manual.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import brentq

if TYPE_CHECKING:
    pass


@dataclass
class CrossSection:
    """A single cross-section's geometry.

    Distance and elevation arrays are paired floor-to-floor across the channel.
    """

    station_m: float
    distance_m: np.ndarray
    elevation_m: np.ndarray
    manning_n: float = 0.035

    def __post_init__(self) -> None:
        self.distance_m = np.asarray(self.distance_m, dtype=float)
        self.elevation_m = np.asarray(self.elevation_m, dtype=float)
        if self.distance_m.shape != self.elevation_m.shape:
            raise ValueError("distance_m and elevation_m must have same shape")
        if len(self.distance_m) < 3:
            raise ValueError("Cross-section needs at least 3 points")
        if not np.all(np.diff(self.distance_m) > 0):
            raise ValueError("distance_m must be strictly monotonically increasing")

    @property
    def thalweg_elevation_m(self) -> float:
        return float(self.elevation_m.min())

    def hydraulic_props(self, water_surface_m: float) -> tuple[float, float, float, float]:
        """Compute (area A, wetted perimeter P, top width T, hydraulic radius R) at given WSE.

        Linear interpolation across each segment, exact (not numerical) integration.
        Standard cross-section integration; see Chow (1959) §2.
        """
        h_water = water_surface_m - self.elevation_m
        # Process segment by segment
        A = 0.0
        P = 0.0
        T = 0.0
        for i in range(len(self.distance_m) - 1):
            x0, x1 = self.distance_m[i], self.distance_m[i + 1]
            z0, z1 = self.elevation_m[i], self.elevation_m[i + 1]
            d0 = h_water[i]
            d1 = h_water[i + 1]
            dx = x1 - x0
            if d0 <= 0 and d1 <= 0:
                continue  # fully dry segment
            if d0 > 0 and d1 > 0:
                # fully wet trapezoid
                seg_A = 0.5 * (d0 + d1) * dx
                seg_P = float(np.hypot(dx, z1 - z0))
                seg_T = dx
            else:
                # partially wet: find waterline crossing
                # interpolate where elevation == water_surface
                if d0 > 0:  # d0 wet, d1 dry
                    frac = d0 / (d0 - d1)
                    wet_dx = dx * frac
                    seg_A = 0.5 * d0 * wet_dx
                    seg_P = float(np.hypot(wet_dx, water_surface_m - z0))
                    seg_T = wet_dx
                else:  # d0 dry, d1 wet
                    frac = d1 / (d1 - d0)
                    wet_dx = dx * frac
                    seg_A = 0.5 * d1 * wet_dx
                    seg_P = float(np.hypot(wet_dx, water_surface_m - z1))
                    seg_T = wet_dx
            A += seg_A
            P += seg_P
            T += seg_T
        R = A / P if P > 0 else 0.0
        return A, P, T, R

    def manning_discharge(self, water_surface_m: float, slope: float) -> float:
        """Q = (1/n) A R^(2/3) S^(1/2), Manning."""
        A, _, _, R = self.hydraulic_props(water_surface_m)
        if A <= 0 or R <= 0 or slope <= 0:
            return 0.0
        return (1.0 / self.manning_n) * A * R ** (2.0 / 3.0) * slope**0.5


@dataclass
class MANSQResult:
    """Per-section steady solution."""

    station_m: float
    discharge_m3s: float
    water_surface_m: float
    depth_mean_m: float
    velocity_mean_ms: float
    area_m2: float
    top_width_m: float
    hydraulic_radius_m: float


@dataclass
class Builtin1D:
    """OpenLimno's built-in 1D solver.

    M1 capability: ``solve_normal_depth(xs, Q)`` returns per-section MANSQResult.
    M2 capability: ``solve_standard_step(...)`` for backwater (not yet implemented).
    """

    slope: float = 0.001  # default 0.1% bed slope; case can override per section
    max_iter: int = 100
    tol_m: float = 1e-5

    def solve_normal_depth(
        self, xs: CrossSection, discharge_m3s: float, slope: float | None = None
    ) -> MANSQResult:
        """Solve Manning normal depth: find WSE such that Q(WSE) = discharge_m3s."""
        if discharge_m3s <= 0:
            wse = xs.thalweg_elevation_m
            return MANSQResult(
                station_m=xs.station_m,
                discharge_m3s=0.0,
                water_surface_m=wse,
                depth_mean_m=0.0,
                velocity_mean_ms=0.0,
                area_m2=0.0,
                top_width_m=0.0,
                hydraulic_radius_m=0.0,
            )

        s = slope if slope is not None else self.slope
        z_min = xs.thalweg_elevation_m
        z_max = xs.elevation_m.max()
        # Bracket: from thalweg + tiny depth to top of section
        lo = z_min + 1e-3
        hi = z_max - 1e-6

        def residual(wse: float) -> float:
            return xs.manning_discharge(wse, s) - discharge_m3s

        # Expand hi if needed (overtopping)
        if residual(hi) < 0:
            hi = z_max + 5.0  # arbitrary overtopping headroom; flag for user

        wse = brentq(residual, lo, hi, xtol=self.tol_m, maxiter=self.max_iter)
        A, _, T, R = xs.hydraulic_props(wse)
        h_mean = A / T if T > 0 else 0.0
        u_mean = discharge_m3s / A if A > 0 else 0.0
        return MANSQResult(
            station_m=xs.station_m,
            discharge_m3s=discharge_m3s,
            water_surface_m=wse,
            depth_mean_m=h_mean,
            velocity_mean_ms=u_mean,
            area_m2=A,
            top_width_m=T,
            hydraulic_radius_m=R,
        )

    def solve_reach(
        self,
        sections: list[CrossSection],
        discharge_m3s: float,
        slope: float | None = None,
    ) -> list[MANSQResult]:
        """Solve all sections at given discharge. Independent per section (MANSQ)."""
        return [self.solve_normal_depth(xs, discharge_m3s, slope) for xs in sections]

    # ------------------------------------------------------------------
    # Standard step method (M2 PHABSIM/IFG4 equivalent)
    # ------------------------------------------------------------------
    def solve_standard_step(
        self,
        sections: list[CrossSection],
        discharge_m3s: float,
        downstream_wse_m: float,
        station_distances_m: list[float] | None = None,
    ) -> list[MANSQResult]:
        """Standard-step backwater from downstream-known WSE.

        Solves the energy equation segment by segment, marching upstream:

            E_up = E_dn + h_f
            (z_up + h_up) + V_up²/(2g) = (z_dn + h_dn) + V_dn²/(2g) + S_f_avg · dx

        where S_f = n²V²/R^(4/3) (Manning friction slope, SI units).

        Assumes subcritical flow throughout. Supercritical detection is M2+ (ADR-0003).

        Parameters
        ----------
        sections
            Ordered upstream → downstream. Last section is the boundary.
        discharge_m3s
            Steady discharge.
        downstream_wse_m
            Known WSE at the downstream-most section (e.g. rating curve).
        station_distances_m
            Optional explicit dx between consecutive sections; defaults to
            ``diff(station_m)``. Useful when sections aren't sorted in space.
        """
        if len(sections) < 2:
            raise ValueError("Standard step needs ≥ 2 sections")

        # Stations expected ascending by x (e.g. 0..1000 upstream to downstream).
        # Convention: index N-1 is downstream boundary.
        stations = np.array([s.station_m for s in sections])
        if station_distances_m is None:
            dx = np.diff(stations)
        else:
            dx = np.asarray(station_distances_m, dtype=float)
        if (dx <= 0).any():
            raise ValueError("Section spacing must be positive (sort upstream-first)")

        g = 9.81

        # Seed downstream
        results: list[MANSQResult] = [None] * len(sections)  # type: ignore[list-item]
        results[-1] = self._eval_at_wse(sections[-1], discharge_m3s, downstream_wse_m)

        # March upstream
        for i in range(len(sections) - 2, -1, -1):
            xs_up = sections[i]
            xs_dn = sections[i + 1]
            r_dn = results[i + 1]
            seg_dx = float(dx[i])

            # Initial guess: WSE_up = WSE_dn (no head loss)
            wse_guess = r_dn.water_surface_m

            # Standard-step iteration: solve for h_up such that
            #   E_up = E_dn + h_f_avg * dx
            def residual(wse_up: float) -> float:
                A_up, _, _, R_up = xs_up.hydraulic_props(wse_up)
                if A_up <= 0 or R_up <= 0:
                    return 1.0  # infeasible; push solver away
                V_up = discharge_m3s / A_up
                Sf_up = (xs_up.manning_n**2) * V_up**2 / R_up ** (4.0 / 3.0)
                Sf_dn = (
                    (xs_dn.manning_n**2)
                    * r_dn.velocity_mean_ms**2
                    / max(r_dn.hydraulic_radius_m, 1e-9) ** (4.0 / 3.0)
                )
                Sf_avg = 0.5 * (Sf_up + Sf_dn)
                E_up = wse_up + V_up**2 / (2 * g)
                E_dn = r_dn.water_surface_m + r_dn.velocity_mean_ms**2 / (2 * g)
                return E_up - E_dn - Sf_avg * seg_dx

            # Bracket: between thalweg+small and several meters above
            z_min = xs_up.thalweg_elevation_m + 1e-3
            z_max = max(xs_up.elevation_m.max(), wse_guess + 5.0)
            try:
                wse_up = brentq(residual, z_min, z_max, xtol=self.tol_m, maxiter=self.max_iter)
            except ValueError:
                # Bracket failed — fall back to MANSQ for this section
                results[i] = self.solve_normal_depth(xs_up, discharge_m3s)
                continue

            results[i] = self._eval_at_wse(xs_up, discharge_m3s, wse_up)

        return results

    @staticmethod
    def _eval_at_wse(xs: CrossSection, discharge_m3s: float, wse: float) -> MANSQResult:
        A, _, T, R = xs.hydraulic_props(wse)
        if A <= 0:
            return MANSQResult(
                station_m=xs.station_m,
                discharge_m3s=discharge_m3s,
                water_surface_m=wse,
                depth_mean_m=0.0,
                velocity_mean_ms=0.0,
                area_m2=0.0,
                top_width_m=T,
                hydraulic_radius_m=R,
            )
        return MANSQResult(
            station_m=xs.station_m,
            discharge_m3s=discharge_m3s,
            water_surface_m=wse,
            depth_mean_m=A / T if T > 0 else 0.0,
            velocity_mean_ms=discharge_m3s / A,
            area_m2=A,
            top_width_m=T,
            hydraulic_radius_m=R,
        )

    # ------------------------------------------------------------------
    # HydroSolver Protocol (real implementation)
    # ------------------------------------------------------------------
    def prepare(
        self,
        case_yaml: str | Path,
        work_dir: str | Path,
        sections: list[CrossSection] | None = None,
        discharges_m3s: list[float] | None = None,
        downstream_wse_m: float | None = None,
    ) -> Path:
        """Stage a Builtin1D run directory.

        Stores enough state in ``work_dir`` for ``run()`` + ``read_results()``
        to operate without keeping references to live Python objects.
        """
        import json
        import pickle

        work_dir = Path(work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

        if sections is None or discharges_m3s is None:
            raise ValueError("Builtin1D.prepare requires sections= and discharges_m3s=")

        # Pickle the geometry (cheap, small) + JSON metadata
        with (work_dir / "sections.pkl").open("wb") as f:
            pickle.dump(sections, f)
        meta = {
            "case_yaml": str(case_yaml),
            "discharges_m3s": list(discharges_m3s),
            "slope": self.slope,
            "downstream_wse_m": downstream_wse_m,
            "schema": "builtin1d/0.1",
        }
        (work_dir / "config.json").write_text(json.dumps(meta, indent=2))
        (work_dir / ".openlimno_prepared").write_text("builtin-1d")
        return work_dir

    def run(self, work_dir: str | Path) -> BuiltinRunResult:
        """Solve the prepared case and pickle results to work_dir."""
        import json
        import pickle

        work_dir = Path(work_dir).resolve()
        marker = work_dir / ".openlimno_prepared"
        if not marker.exists() or marker.read_text().strip() != "builtin-1d":
            raise RuntimeError(f"work_dir {work_dir} not prepared by Builtin1D")
        meta = json.loads((work_dir / "config.json").read_text())
        with (work_dir / "sections.pkl").open("rb") as f:
            sections = pickle.load(f)

        results: dict[float, list[MANSQResult]] = {}
        for Q in meta["discharges_m3s"]:
            if meta.get("downstream_wse_m") is not None:
                results[Q] = self.solve_standard_step(
                    sections,
                    float(Q),
                    downstream_wse_m=float(meta["downstream_wse_m"]),
                )
            else:
                results[Q] = self.solve_reach(sections, float(Q), slope=meta["slope"])

        with (work_dir / "results.pkl").open("wb") as f:
            pickle.dump(results, f)
        return BuiltinRunResult(work_dir=work_dir, n_discharges=len(results))

    def read_results(self, work_dir: str | Path) -> dict[float, list[MANSQResult]]:
        """Read pickled per-section results back as dict {Q -> [MANSQResult]}."""
        import pickle

        work_dir = Path(work_dir).resolve()
        results_path = work_dir / "results.pkl"
        if not results_path.exists():
            raise FileNotFoundError(f"No results.pkl in {work_dir}; was run() called?")
        with results_path.open("rb") as f:
            return pickle.load(f)


@dataclass
class BuiltinRunResult:
    """Marker result type returned by Builtin1D.run()."""

    work_dir: Path
    n_discharges: int


# -----------------------------------------------------------------
# Helpers to load sections from WEDM cross_section.parquet
# -----------------------------------------------------------------
def load_sections_from_parquet(
    path: str | Path,
    manning_n: float = 0.035,
) -> list[CrossSection]:
    """Load cross-sections from a WEDM cross_section.parquet table."""
    import pandas as pd

    df = pd.read_parquet(path)
    sections: list[CrossSection] = []
    for station, sub in df.groupby("station_m"):
        sub = sub.sort_values("point_index")
        sections.append(
            CrossSection(
                station_m=float(station),
                distance_m=sub["distance_m"].to_numpy(),
                elevation_m=sub["elevation_m"].to_numpy(),
                manning_n=manning_n,
            )
        )
    return sections


__all__ = [
    "Builtin1D",
    "CrossSection",
    "MANSQResult",
    "load_sections_from_parquet",
]
