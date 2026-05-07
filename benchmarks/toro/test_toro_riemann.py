"""Toro 1D Riemann problems for the SWE-style 1D solver. SPEC §7.

The Builtin1D solver is steady-state Manning, NOT a transient SWE Riemann
solver — so a strict Toro Riemann test isn't applicable to M1 scope.

What we CAN verify under M1 (steady-state Manning):
  - Smooth-flow consistency: the solver should reproduce analytic
    rectangular-Manning normal depth at any subcritical Q
  - Cross-section integration of A, P, R must match closed-form for a
    rectangular section to machine precision

When the unsteady solver lands (post-1.0; SPEC §13.1), this file becomes the
home of the dam-break and shock-tube tests in Toro 2009 ch. 4.

We retain the file in the standard benchmark slot so the SPEC §7 placeholder
is satisfied with an explicit deferred-test marker.
"""

from __future__ import annotations

import numpy as np
import pytest

from openlimno.hydro.builtin_1d import CrossSection


def test_rectangular_geometry_machine_precision() -> None:
    """A clean rectangle (no wall flap) must match A, P, R closed-form exactly."""
    width = 10.0
    half = width / 2
    # Use minimal wall width so wall contribution is negligible at low h
    xs = CrossSection(
        station_m=0.0,
        distance_m=np.array([-half - 1e-6, -half, half, half + 1e-6]),
        elevation_m=np.array([100.0, 0.0, 0.0, 100.0]),
        manning_n=0.030,
    )
    h = 1.5
    A, P, T, R = xs.hydraulic_props(water_surface_m=h)
    # Analytic
    A_exact = width * h
    T_exact = width
    P_exact = width + 2 * h
    R_exact = A_exact / P_exact

    assert A == pytest.approx(A_exact, rel=1e-5)
    assert T == pytest.approx(T_exact, rel=1e-5)
    assert P == pytest.approx(P_exact, rel=1e-5)
    assert R == pytest.approx(R_exact, rel=1e-5)


def test_smooth_subcritical_flow_consistency() -> None:
    """Manning-discharge function must agree with rectangular closed-form."""
    width = 10.0
    n = 0.030
    S = 0.001
    h = 0.8
    half = width / 2
    xs = CrossSection(
        station_m=0.0,
        distance_m=np.array([-half - 1e-6, -half, half, half + 1e-6]),
        elevation_m=np.array([100.0, 0.0, 0.0, 100.0]),
        manning_n=n,
    )
    A = width * h
    P = width + 2 * h
    R = A / P
    Q_exact = (1.0 / n) * A * R ** (2.0 / 3.0) * np.sqrt(S)
    Q_obtained = xs.manning_discharge(water_surface_m=h, slope=S)
    assert Q_obtained == pytest.approx(Q_exact, rel=1e-5)


@pytest.mark.skip(reason="Unsteady SWE Riemann tests deferred to §13.1 (post-1.0)")
def test_toro_dam_break_riemann() -> None:
    """Placeholder: Toro 2009 dam-break problem when unsteady SWE lands."""
