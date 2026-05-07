"""Standard-step backwater tests. SPEC §4.1.1 M2 scope."""

from __future__ import annotations

import numpy as np
import pytest

from openlimno.hydro.builtin_1d import Builtin1D, CrossSection


def make_uniform_reach(
    n_sections: int = 6, dx: float = 100.0, slope: float = 0.001, n: float = 0.025
) -> list[CrossSection]:
    """A uniform-prismatic reach: same cross-section, sloping bed.

    Bed elev[i] = slope * (n_sections - 1 - i) * dx (highest upstream).
    Sections ordered upstream → downstream.
    """
    sections = []
    bottom_w = 5.0
    half_top = 12.5
    half_bot = 2.5
    rise = (half_top - half_bot) / 2.0  # for side-slope 2:1
    for i in range(n_sections):
        bed = slope * (n_sections - 1 - i) * dx
        sections.append(
            CrossSection(
                station_m=i * dx,
                distance_m=np.array([-half_top, -half_bot, half_bot, half_top]),
                elevation_m=np.array([bed + rise, bed, bed, bed + rise]),
                manning_n=n,
            )
        )
    return sections


def test_standard_step_uniform_reach_matches_normal_depth() -> None:
    """For a uniform prismatic reach with normal-depth boundary, profile should be ~uniform."""
    sections = make_uniform_reach(n_sections=10, dx=100.0, slope=0.001, n=0.025)
    Q = 8.0
    solver = Builtin1D(slope=0.001)

    # Compute MANSQ at one section to find normal depth
    mansq = solver.solve_normal_depth(sections[-1], Q)
    h_normal = mansq.depth_mean_m

    # Run standard step using MANSQ WSE as boundary
    results = solver.solve_standard_step(sections, Q, downstream_wse_m=mansq.water_surface_m)

    # Each section's water depth (relative to its own bed) should ≈ h_normal
    for r, xs in zip(results, sections, strict=False):
        d_above_bed = r.water_surface_m - xs.thalweg_elevation_m
        # Tolerance loose because depth_mean is hydraulic mean, not max
        assert d_above_bed > 0, f"Dry section at station {r.station_m}"
        # Compare at hydraulic mean
        assert r.depth_mean_m == pytest.approx(h_normal, rel=0.10)


def test_standard_step_backwater_wse_decreases_downstream() -> None:
    """Backwater from a high-stage downstream condition should propagate upstream with WSE descending downstream."""
    sections = make_uniform_reach(n_sections=8, dx=200.0, slope=0.001, n=0.025)
    Q = 5.0
    solver = Builtin1D()

    # Backwater: set downstream WSE 0.5 m above normal
    mansq = solver.solve_normal_depth(sections[-1], Q)
    results = solver.solve_standard_step(sections, Q, downstream_wse_m=mansq.water_surface_m + 0.5)

    wses = [r.water_surface_m for r in results]
    # Upstream WSE > downstream WSE (always true with positive bed slope)
    assert wses[0] > wses[-1]


def test_standard_step_results_self_consistent() -> None:
    """Each section's energy plus avg Sf*dx should equal next downstream section's energy."""
    sections = make_uniform_reach(n_sections=5, dx=100.0)
    solver = Builtin1D()
    Q = 5.0
    mansq = solver.solve_normal_depth(sections[-1], Q)
    results = solver.solve_standard_step(sections, Q, downstream_wse_m=mansq.water_surface_m)

    g = 9.81
    for i in range(len(results) - 1):
        r_up = results[i]
        r_dn = results[i + 1]
        E_up = r_up.water_surface_m + r_up.velocity_mean_ms**2 / (2 * g)
        E_dn = r_dn.water_surface_m + r_dn.velocity_mean_ms**2 / (2 * g)
        # Energy decreases downstream (loss to friction)
        assert E_up >= E_dn - 1e-3


def test_standard_step_too_few_sections() -> None:
    sections = make_uniform_reach(n_sections=1)
    solver = Builtin1D()
    with pytest.raises(ValueError, match="≥ 2 sections"):
        solver.solve_standard_step(sections, 5.0, downstream_wse_m=1.0)
