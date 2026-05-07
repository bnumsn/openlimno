"""Bovee 1997 PHABSIM standard regression. SPEC §7 mandatory verification.

Strategy: build a wide rectangular prismatic reach where Manning normal depth
has a closed-form solution, hand-compute WUA, and require Builtin1D + habitat
to reproduce within 1e-3 (table-level, per ADR-0009).
"""

from __future__ import annotations

import numpy as np
import pytest

from openlimno.habitat import (
    HSICurve,
    cell_wua,
    composite_csi,
    require_independence_ack,
)
from openlimno.hydro.builtin_1d import Builtin1D, CrossSection


def make_rectangular_section(station: float, bed_elev: float,
                             width: float = 10.0, manning_n: float = 0.030,
                             height: float = 5.0) -> CrossSection:
    """Wide rectangular section (vertical walls + flat bed).

    Walls so high they're never overtopped at the test Qs.
    """
    half = width / 2
    return CrossSection(
        station_m=station,
        distance_m=np.array([-half - 0.01, -half, half, half + 0.01]),
        elevation_m=np.array([bed_elev + height, bed_elev, bed_elev, bed_elev + height]),
        manning_n=manning_n,
    )


def manning_rect_depth(Q: float, n: float, b: float, S: float) -> float:
    """Exact rectangular Manning normal depth (full P = b + 2h)."""
    from scipy.optimize import brentq

    def residual(h: float) -> float:
        A = b * h
        P = b + 2 * h
        R = A / P
        return (1.0 / n) * A * R ** (2.0 / 3.0) * np.sqrt(S) - Q

    return float(brentq(residual, 1e-4, 50.0))


def make_bovee_reach() -> list[CrossSection]:
    sections = []
    for i in range(6):
        bed = 1.0 - 0.001 * i * 100  # slope 0.001, 100 m spacing → 0.1 m drop per section
        sections.append(make_rectangular_section(station=i * 100.0, bed_elev=bed))
    return sections


# Stylised Bovee 1978 steelhead spawning HSI curves
def hsi_depth() -> HSICurve:
    return HSICurve(
        species="oncorhynchus_mykiss", life_stage="spawning", variable="depth",
        points=[(0.0, 0.0), (0.30, 1.0), (0.60, 1.0), (1.20, 0.5), (2.00, 0.0)],
        category="III", geographic_origin="Pacific-Northwest-USA",
        transferability_score=0.6, quality_grade="B",
    )


def hsi_velocity() -> HSICurve:
    return HSICurve(
        species="oncorhynchus_mykiss", life_stage="spawning", variable="velocity",
        points=[(0.00, 0.0), (0.50, 1.0), (1.00, 1.0), (1.50, 0.3), (2.00, 0.0)],
        category="III", geographic_origin="Pacific-Northwest-USA",
        transferability_score=0.6, quality_grade="B",
    )


def expected_wua(Q: float, b: float = 10.0, n: float = 0.030, S: float = 0.001,
                 reach_length_m: float = 500.0) -> float:
    """Hand-computed WUA for the prismatic reach at given Q."""
    h = manning_rect_depth(Q, n, b, S)
    u = Q / (b * h)
    s_h = float(np.interp(h, [p[0] for p in hsi_depth().points],
                            [p[1] for p in hsi_depth().points]))
    s_u = float(np.interp(u, [p[0] for p in hsi_velocity().points],
                            [p[1] for p in hsi_velocity().points]))
    csi = float(np.sqrt(s_h * s_u))  # geometric mean
    # Each cell area = wetted area = b * h * dx; we integrate over a per-section
    # cell with extent equal to one whole spacing
    area_per_section = b * h * 100.0  # 100 m per section
    return csi * area_per_section * 6  # 6 sections


# ----------------------------------------------------------
# Tests
# ----------------------------------------------------------
@pytest.mark.parametrize("Q", [0.5, 1.5, 4.0, 8.0])
def test_normal_depth_matches_closed_form(Q: float) -> None:
    sections = make_bovee_reach()
    solver = Builtin1D(slope=0.001)
    h_expected = manning_rect_depth(Q, 0.030, 10.0, 0.001)
    result = solver.solve_normal_depth(sections[0], discharge_m3s=Q)
    # depth_mean (= A/T) for a wide rectangular section equals normal depth
    assert result.depth_mean_m == pytest.approx(h_expected, rel=1e-3)


@pytest.mark.parametrize("Q,wua_target", [
    (0.5, expected_wua(0.5)),
    (1.5, expected_wua(1.5)),
    (4.0, expected_wua(4.0)),
    (8.0, expected_wua(8.0)),
])
def test_wua_matches_expected(Q: float, wua_target: float) -> None:
    sections = make_bovee_reach()
    solver = Builtin1D(slope=0.001)
    require_independence_ack("geometric_mean", acknowledged=True)

    results = solver.solve_reach(sections, discharge_m3s=Q)
    h_arr = np.array([r.depth_mean_m for r in results])
    u_arr = np.array([r.velocity_mean_ms for r in results])
    a_arr = np.array([r.area_m2 for r in results])

    s_h = hsi_depth().evaluate(h_arr)
    s_u = hsi_velocity().evaluate(u_arr)
    csi = composite_csi({"d": s_h, "v": s_u}, method="geometric_mean")

    # Each section contributes area = wetted_area * spacing_m / section_count_factor;
    # we use wetted_area * 100 m (spacing) to match expected_wua's integral.
    wua_each = csi * a_arr * 100.0 / a_arr  # = csi * 100 * (a_arr/a_arr) = csi*100*1
    # Actually: area_m2 from MANSQ is wetted-cross-section area (m^2).
    # Hand-comp uses b*h*100 = wetted_area * 100. So multiply by 100:
    wua_total = float((csi * a_arr * 100.0).sum())

    assert wua_total == pytest.approx(wua_target, rel=1e-3, abs=1e-3)


def test_wua_q_curve_unimodal_in_bovee_reach() -> None:
    """Sweep across Q; resulting WUA-Q curve must be unimodal (rise then fall)."""
    sections = make_bovee_reach()
    solver = Builtin1D(slope=0.001)
    Qs = np.array([0.2, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 20.0])
    wuas = []
    for Q in Qs:
        results = solver.solve_reach(sections, discharge_m3s=float(Q))
        h = np.array([r.depth_mean_m for r in results])
        u = np.array([r.velocity_mean_ms for r in results])
        a = np.array([r.area_m2 for r in results])
        csi = composite_csi(
            {"d": hsi_depth().evaluate(h), "v": hsi_velocity().evaluate(u)},
            method="geometric_mean",
        )
        wuas.append(float((csi * a * 100.0).sum()))
    wuas_arr = np.array(wuas)
    peak_idx = int(np.argmax(wuas_arr))
    assert 0 < peak_idx < len(wuas_arr) - 1, (
        f"WUA curve not unimodal: {wuas_arr.round(2)}"
    )
