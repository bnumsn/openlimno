"""v1.1.0 thermal habitat suitability tests.

Pin the trapezoidal curve shape, FishBase-defaults helper, series
adapter (DataFrame + Series), and the summary-metrics dict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_thermal_range_validates_ordering():
    from openlimno.habitat import ThermalRange
    # OK
    ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    # Inverted: T_opt_min > T_opt_max
    with pytest.raises(ValueError, match="T_lethal_min"):
        ThermalRange(T_lethal_min=0.0, T_opt_min=18.0, T_opt_max=10.0, T_lethal_max=23.0)
    # Lethal not bracketing opt
    with pytest.raises(ValueError, match="T_lethal_min"):
        ThermalRange(T_lethal_min=12.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    with pytest.raises(ValueError, match="T_lethal_min"):
        ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=15.0)


def test_thermal_range_from_fishbase_defaults():
    """Default lethal margin = ±5 °C."""
    from openlimno.habitat import ThermalRange
    tr = ThermalRange.from_fishbase(10.0, 18.0)
    assert tr.T_opt_min == 10.0 and tr.T_opt_max == 18.0
    assert tr.T_lethal_min == 5.0 and tr.T_lethal_max == 23.0
    assert "FishBase" in tr.source


def test_thermal_range_from_fishbase_rejects_zero_margin():
    from openlimno.habitat import ThermalRange
    with pytest.raises(ValueError, match="lethal_margin_C"):
        ThermalRange.from_fishbase(10.0, 18.0, lethal_margin_C=0.0)


def test_thermal_hsi_curve_shape_scalar():
    """SI=0 below T_lethal_min, ramp to 1 across the bottom shoulder,
    1 across the optimum, ramp to 0 across the top shoulder, 0 above."""
    from openlimno.habitat import ThermalRange, thermal_hsi
    tr = ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    # Below lethal
    assert thermal_hsi(-5.0, tr) == 0.0
    assert thermal_hsi(0.0, tr) == 0.0  # at lethal floor still 0
    # Mid-ramp left: T=5.0 → halfway between 0 and 10 → SI = 0.5
    assert thermal_hsi(5.0, tr) == pytest.approx(0.5)
    # At T_opt_min: SI=1.0
    assert thermal_hsi(10.0, tr) == pytest.approx(1.0)
    # Inside optimum
    assert thermal_hsi(14.0, tr) == pytest.approx(1.0)
    assert thermal_hsi(18.0, tr) == pytest.approx(1.0)
    # Mid-ramp right: T=20.5 → halfway between 18 and 23 → SI = 0.5
    assert thermal_hsi(20.5, tr) == pytest.approx(0.5)
    # At T_lethal_max: SI=0
    assert thermal_hsi(23.0, tr) == pytest.approx(0.0)
    # Above lethal max
    assert thermal_hsi(30.0, tr) == 0.0


def test_thermal_hsi_curve_vectorised():
    from openlimno.habitat import ThermalRange, thermal_hsi
    tr = ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    arr = np.array([-1.0, 5.0, 14.0, 20.5, 30.0])
    out = thermal_hsi(arr, tr)
    assert isinstance(out, np.ndarray)
    np.testing.assert_allclose(out, [0.0, 0.5, 1.0, 0.5, 0.0])


def test_thermal_suitability_series_from_dataframe():
    """Default temperature_column is T_water_C_stefan to match the
    Daymet / Open-Meteo fetcher schema."""
    from openlimno.habitat import ThermalRange, thermal_suitability_series
    tr = ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    df = pd.DataFrame({
        "time": ["2024-01-01", "2024-07-01", "2024-12-01"],
        "T_water_C_stefan": [2.0, 14.0, 25.0],
    })
    out = thermal_suitability_series(df, tr)
    assert list(out.columns) == ["time", "T_water_C", "thermal_SI"]
    assert len(out) == 3
    # 2.0 is in left ramp: (2-0)/(10-0)=0.2
    assert out.iloc[0]["thermal_SI"] == pytest.approx(0.2)
    # 14.0 is in optimum: 1.0
    assert out.iloc[1]["thermal_SI"] == pytest.approx(1.0)
    # 25.0 is above lethal max: 0
    assert out.iloc[2]["thermal_SI"] == 0.0


def test_thermal_suitability_series_from_series():
    """Accept a plain pd.Series of temperatures keyed by date."""
    from openlimno.habitat import ThermalRange, thermal_suitability_series
    tr = ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    s = pd.Series(
        [5.0, 14.0, 20.5],
        index=pd.to_datetime(["2024-01-01", "2024-07-01", "2024-10-01"]),
        name="T_water_C_stefan",
    )
    out = thermal_suitability_series(s, tr)
    assert list(out.columns) == ["time", "T_water_C", "thermal_SI"]
    assert len(out) == 3
    np.testing.assert_allclose(
        out["thermal_SI"].values, [0.5, 1.0, 0.5],
    )


def test_thermal_suitability_series_rejects_missing_column():
    from openlimno.habitat import ThermalRange, thermal_suitability_series
    tr = ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    df = pd.DataFrame({"time": ["2024-01-01"], "tair_C": [5.0]})  # wrong col
    with pytest.raises(KeyError, match="T_water_C_stefan"):
        thermal_suitability_series(df, tr)


def test_thermal_metrics_summary():
    from openlimno.habitat import ThermalRange, thermal_metrics, thermal_suitability_series
    tr = ThermalRange(T_lethal_min=0.0, T_opt_min=10.0, T_opt_max=18.0, T_lethal_max=23.0)
    df = pd.DataFrame({
        "time": ["d1", "d2", "d3", "d4", "d5"],
        "T_water_C_stefan": [2.0, 14.0, 14.0, 25.0, 16.0],
    })
    series = thermal_suitability_series(df, tr)
    m = thermal_metrics(series)
    assert m["days_total"] == 5
    assert m["days_optimal"] == 3  # 14, 14, 16 all == 1.0
    assert m["days_lethal"] == 1  # 25 > T_lethal_max
    assert m["optimal_fraction"] == pytest.approx(0.6)
    assert m["mean_SI"] == pytest.approx((0.2 + 1.0 + 1.0 + 0.0 + 1.0) / 5)


def test_thermal_metrics_handles_empty_series():
    from openlimno.habitat import thermal_metrics
    empty = pd.DataFrame({"time": [], "T_water_C": [], "thermal_SI": []})
    m = thermal_metrics(empty)
    assert m["days_total"] == 0
    assert m["days_optimal"] == 0
    assert np.isnan(m["mean_SI"])
    assert np.isnan(m["optimal_fraction"])


def test_thermal_chain_with_fishbase_and_openmeteo_schema(tmp_path):
    """End-to-end: take FishBase preferred range → ThermalRange → eval
    against a synthetic Open-Meteo-schema climate DataFrame. Pins the
    fetcher × habitat coupling that v1.1.0 ships."""
    from openlimno.habitat import (
        ThermalRange, thermal_suitability_series, thermal_metrics,
    )
    from openlimno.preprocess.fetch import fetch_fishbase_traits
    # Rainbow trout: T 9..18 °C from FishBase
    traits = fetch_fishbase_traits("Oncorhynchus mykiss")
    assert traits is not None
    tr = ThermalRange.from_fishbase(
        traits.temperature_min_C, traits.temperature_max_C,
    )
    # Simulate a year of Open-Meteo output (T_water_C_stefan column)
    days = pd.date_range("2024-01-01", periods=365, freq="D")
    # Sinusoidal water temp 4 → 22 °C peaking mid-summer
    T = 13.0 + 9.0 * np.sin(2 * np.pi * (np.arange(365) - 100) / 365.0)
    clim = pd.DataFrame({
        "time": days.strftime("%Y-%m-%d"),
        "T_water_C_stefan": T,
    })
    series = thermal_suitability_series(clim, tr)
    m = thermal_metrics(series)
    # Rainbow trout has a narrow optimum 9..18; with the synthetic
    # annual swing 4..22 °C we expect a non-trivial mix of all three
    # regimes (lethal, ramp, optimum).
    assert 50 < m["days_optimal"] < 250
    assert 0 < m["mean_SI"] < 1
    # Some days should hit the upper lethal limit (>=23 °C) — sine
    # peaks at 22 which is below T_lethal_max=23, so 0 lethal days
    # in the upper tail; the lower tail (<4 °C) also doesn't quite
    # reach T_lethal_min=4 (peak min = 4). Just assert metric is
    # internally consistent.
    assert m["days_optimal"] + m["days_lethal"] <= m["days_total"]
