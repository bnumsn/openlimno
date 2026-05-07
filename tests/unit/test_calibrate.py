"""Calibration workflow tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from openlimno.hydro.builtin_1d import CrossSection
from openlimno.workflows import calibrate_manning_n


def make_rect(width: float = 10.0, n: float = 0.035) -> CrossSection:
    half = width / 2
    return CrossSection(
        station_m=0.0,
        distance_m=np.array([-half - 1e-6, -half, half, half + 1e-6]),
        elevation_m=np.array([10.0, 0.0, 0.0, 10.0]),
        manning_n=n,
    )


def test_calibrate_recovers_known_n() -> None:
    """Synthesize observed rating with n=0.030, calibrate from initial 0.045."""
    xs = make_rect(n=0.030)
    obs_h = np.array([0.3, 0.5, 0.8, 1.2, 1.6])
    obs_Q = np.array([
        xs.manning_discharge(h, slope=0.001) for h in obs_h
    ])
    obs = pd.DataFrame({"h_m": obs_h, "Q_m3s": obs_Q})

    res = calibrate_manning_n(
        cross_section=xs, observed_rating=obs, slope=0.001,
        initial_n=0.045,
    )
    assert res.calibrated_value == pytest.approx(0.030, rel=1e-3)
    assert res.rmse_final < res.rmse_initial
    assert res.rmse_final < 0.01
    assert res.converged


def test_calibrate_does_not_modify_section_n() -> None:
    """Calibration must restore the original n on the input section."""
    xs = make_rect(n=0.040)
    obs = pd.DataFrame({"h_m": [0.5, 1.0], "Q_m3s": [3.0, 8.0]})
    calibrate_manning_n(xs, obs, slope=0.001)
    assert xs.manning_n == 0.040


def test_calibrate_missing_columns_raises() -> None:
    xs = make_rect()
    obs = pd.DataFrame({"depth": [0.5], "discharge": [3.0]})
    with pytest.raises(ValueError, match="h_m.*Q_m3s"):
        calibrate_manning_n(xs, obs)


def test_calibrate_respects_bounds() -> None:
    """Out-of-bounds optimum should clamp to bounds."""
    xs = make_rect(n=0.005)
    obs_h = np.array([0.5, 1.0])
    obs_Q = np.array([
        xs.manning_discharge(h, slope=0.001) for h in obs_h
    ])
    obs = pd.DataFrame({"h_m": obs_h, "Q_m3s": obs_Q})

    res = calibrate_manning_n(
        xs, obs, slope=0.001, initial_n=0.030,
        bounds=(0.012, 0.080),  # excludes the true 0.005
    )
    # Calibrated value should be at lower bound
    assert res.calibrated_value == pytest.approx(0.012, rel=0.05)
