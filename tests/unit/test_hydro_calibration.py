from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from openlimno.hydro import (
    CrossSection,
    calibrate_builtin1d_normal_depth,
    predict_builtin1d_normal_depth,
)


def _trapezoid(station_m: float) -> CrossSection:
    return CrossSection(
        station_m=station_m,
        distance_m=np.array([0.0, 3.0, 9.0, 12.0]),
        elevation_m=np.array([2.0, 0.0, 0.0, 2.0]),
        manning_n=0.04,
    )


def test_predict_builtin1d_normal_depth_returns_section_predictions() -> None:
    sections = [_trapezoid(0.0), _trapezoid(100.0)]

    result = predict_builtin1d_normal_depth(
        sections,
        [2.0, 5.0],
        slope=0.0004,
        manning_n=0.035,
    )

    assert list(result["station_m"]) == [0.0, 100.0]
    assert (result["water_surface_m"] > 0.0).all()
    assert (result["velocity_ms"] > 0.0).all()


def test_calibrate_builtin1d_normal_depth_recovers_synthetic_candidate() -> None:
    sections = [_trapezoid(0.0), _trapezoid(100.0)]
    discharges = [2.0, 5.0]
    truth = predict_builtin1d_normal_depth(
        sections,
        discharges,
        slope=0.0004,
        manning_n=0.035,
    )
    wse_observed = truth[["station_m", "water_surface_m"]].copy()
    velocity_observed = truth[["station_m", "velocity_ms"]].copy()

    result = calibrate_builtin1d_normal_depth(
        sections,
        discharges,
        wse_observations=wse_observed,
        velocity_observations=velocity_observed,
        slopes=[0.0002, 0.0004, 0.0008],
        manning_ns=[0.030, 0.035, 0.040],
    )

    assert result.best.slope == pytest.approx(0.0004)
    assert result.best.manning_n == pytest.approx(0.035)
    assert result.best.score == pytest.approx(0.0, abs=1e-8)
    assert set(result.candidates.columns) >= {"slope", "manning_n", "score", "wse_rmse_m"}


def test_calibrate_builtin1d_normal_depth_rejects_missing_observations() -> None:
    with pytest.raises(ValueError, match="at least one observed"):
        calibrate_builtin1d_normal_depth([_trapezoid(0.0)], 2.0)


def test_calibrate_builtin1d_normal_depth_accepts_velocity_only() -> None:
    sections = [_trapezoid(0.0)]
    truth = predict_builtin1d_normal_depth(sections, 2.0, slope=0.0004, manning_n=0.035)
    velocity_observed = pd.DataFrame(
        {
            "station_m": [0.0],
            "velocity_ms": [float(truth["velocity_ms"].iloc[0])],
        }
    )

    result = calibrate_builtin1d_normal_depth(
        sections,
        2.0,
        velocity_observations=velocity_observed,
        slopes=[0.0004],
        manning_ns=[0.035],
    )

    assert result.best.n_wse == 0
    assert result.best.n_velocity == 1
    assert result.best.velocity_rmse_ms == pytest.approx(0.0)


def test_calibrate_builtin1d_normal_depth_accepts_numpy_grids() -> None:
    sections = [_trapezoid(0.0)]
    truth = predict_builtin1d_normal_depth(sections, 2.0, slope=0.0004, manning_n=0.035)
    wse_observed = truth[["station_m", "water_surface_m"]].copy()

    result = calibrate_builtin1d_normal_depth(
        sections,
        2.0,
        wse_observations=wse_observed,
        slopes=np.array([0.0004]),
        manning_ns=np.array([0.035]),
    )

    assert result.best.slope == pytest.approx(0.0004)
    assert result.best.manning_n == pytest.approx(0.035)
