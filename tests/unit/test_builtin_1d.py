"""Unit tests for Builtin1D MANSQ solver."""

from __future__ import annotations

import numpy as np
import pytest

from openlimno.hydro.builtin_1d import Builtin1D, CrossSection


def make_trapezoid_xs(
    bottom_width: float = 5.0,
    side_slope: float = 2.0,  # horizontal:vertical
    top_width: float = 25.0,
    bed_elev: float = 0.0,
    station: float = 0.0,
    n: float = 0.035,
) -> CrossSection:
    """Build a symmetric trapezoidal cross-section."""
    half_top = top_width / 2.0
    half_bot = bottom_width / 2.0
    rise = (half_top - half_bot) / side_slope
    distance = np.array([-half_top, -half_bot, half_bot, half_top])
    elevation = np.array([bed_elev + rise, bed_elev, bed_elev, bed_elev + rise])
    return CrossSection(station_m=station, distance_m=distance, elevation_m=elevation, manning_n=n)


def test_dry_section_zero_discharge() -> None:
    xs = make_trapezoid_xs()
    A, P, T, R = xs.hydraulic_props(xs.thalweg_elevation_m)
    assert A == 0
    assert P == 0
    assert T == 0
    assert R == 0


def test_full_wet_trapezoid_geometry() -> None:
    """Trapezoidal section, 1.0 m depth, b=5, m=2:  A = (5+m*h)*h = (5+2)*1 = 7"""
    xs = make_trapezoid_xs(bottom_width=5.0, side_slope=2.0, top_width=25.0, bed_elev=0.0)
    A, P, T, R = xs.hydraulic_props(water_surface_m=1.0)
    # A = h*(b + m*h) = 1*(5 + 2*1) = 7
    assert pytest.approx(7.0, rel=1e-3) == A
    # T = b + 2*m*h = 5 + 2*2*1 = 9
    assert pytest.approx(9.0, rel=1e-3) == T
    # P = b + 2*h*sqrt(1+m^2) = 5 + 2*1*sqrt(5) ≈ 9.472
    assert pytest.approx(5.0 + 2.0 * np.sqrt(5.0), rel=1e-3) == P


def test_manning_normal_depth_self_consistent() -> None:
    """The returned WSE must back-substitute into Manning to give the input Q.

    Channel: b=5 m, side slope 2:1, n=0.025, S=0.001, Q=10 m3/s.
    """
    xs = make_trapezoid_xs(bottom_width=5.0, side_slope=2.0, top_width=25.0, bed_elev=0.0, n=0.025)
    solver = Builtin1D(slope=0.001)
    Q_in = 10.0
    result = solver.solve_normal_depth(xs, discharge_m3s=Q_in)
    Q_back = xs.manning_discharge(result.water_surface_m, slope=0.001)
    assert Q_back == pytest.approx(Q_in, rel=1e-4)
    # u = Q/A consistency
    assert result.velocity_mean_ms == pytest.approx(Q_in / result.area_m2, rel=1e-4)


def test_manning_textbook_chow_example() -> None:
    """Hand-verified: b=5 m, m=2, n=0.025, S=0.001 → at h=1 m, Q ≈ 7.24 m3/s.

    Chow 1959 Eq. 5-7: Q = (1/n) A R^(2/3) S^(1/2).
    A = h(b+mh) = 1*(5+2) = 7
    P = b + 2h*sqrt(1+m^2) = 5 + 2*sqrt(5) = 9.472
    R = 0.7390
    Q = 40 * 7 * 0.7390^(2/3) * 0.0316 = 7.24
    """
    xs = make_trapezoid_xs(bottom_width=5.0, side_slope=2.0, top_width=25.0, bed_elev=0.0, n=0.025)
    Q_at_1m = xs.manning_discharge(water_surface_m=1.0, slope=0.001)
    assert Q_at_1m == pytest.approx(7.24, rel=0.01)

    # Now solve inverse: for Q=7.24, depth should come back to ~1.0
    solver = Builtin1D(slope=0.001)
    result = solver.solve_normal_depth(xs, discharge_m3s=7.24)
    assert result.water_surface_m == pytest.approx(1.0, rel=0.005)


def test_zero_discharge_returns_thalweg() -> None:
    xs = make_trapezoid_xs(bed_elev=10.0)
    solver = Builtin1D()
    result = solver.solve_normal_depth(xs, discharge_m3s=0.0)
    assert result.water_surface_m == 10.0
    assert result.depth_mean_m == 0.0
    assert result.velocity_mean_ms == 0.0


def test_higher_q_yields_deeper_water() -> None:
    xs = make_trapezoid_xs()
    solver = Builtin1D(slope=0.001)
    r_low = solver.solve_normal_depth(xs, discharge_m3s=1.0)
    r_high = solver.solve_normal_depth(xs, discharge_m3s=10.0)
    assert r_high.depth_mean_m > r_low.depth_mean_m
    assert r_high.water_surface_m > r_low.water_surface_m


def test_solve_reach_n_sections() -> None:
    sections = [make_trapezoid_xs(station=i * 100.0) for i in range(5)]
    solver = Builtin1D(slope=0.002)
    results = solver.solve_reach(sections, discharge_m3s=5.0)
    assert len(results) == 5
    # All sections identical → all depths equal
    depths = [r.depth_mean_m for r in results]
    assert max(depths) - min(depths) < 1e-6


def test_partially_wet_segment() -> None:
    """Section with bank too high to fully wet; ensure partial wetting integrates correctly."""
    xs = CrossSection(
        station_m=0.0,
        distance_m=np.array([0.0, 1.0, 2.0, 3.0, 4.0]),
        elevation_m=np.array([5.0, 0.5, 0.0, 0.5, 5.0]),  # cup shape
        manning_n=0.03,
    )
    A, _, T, _ = xs.hydraulic_props(water_surface_m=1.0)
    # Wetted only between x ≈ 0.89 and 3.11; T < 4.0
    assert 0 < T < 4.0
    assert A > 0
