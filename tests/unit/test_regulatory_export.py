"""SL-712 regulatory export tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from openlimno.habitat.regulatory_export import cn_sl712


def make_synthetic_wua_q() -> pd.DataFrame:
    """Synthetic unimodal WUA-Q curve, peak ≈ 100 m² at Q=5."""
    Qs = np.array([0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0])
    # Triangular peak at Q=5
    W = np.maximum(0, 100 * (1 - np.abs(np.log(Qs / 5)) / np.log(4)))
    return pd.DataFrame({
        "discharge_m3s": Qs,
        "wua_m2_oncorhynchus_mykiss_spawning": W,
    })


def make_synthetic_discharge_series(n_years: int = 5) -> pd.DataFrame:
    """Annual cycle with some inter-year variability."""
    rng = np.random.default_rng(42)
    times = pd.date_range("2020-01-01", periods=n_years * 365, freq="D")
    doys = times.dayofyear.values
    # Snowmelt peak in May-June, baseflow in winter
    Q_base = 3.0 + 8.0 * np.exp(-((doys - 150) ** 2) / (2 * 30 ** 2))
    Q = Q_base * (1.0 + 0.2 * rng.standard_normal(len(times)))
    Q = np.clip(Q, 0.5, 50.0)
    return pd.DataFrame({"time": times, "discharge_m3s": Q})


def test_compute_sl712_returns_12_rows() -> None:
    wua_q = make_synthetic_wua_q()
    Q = make_synthetic_discharge_series()
    res = cn_sl712.compute_sl712(
        Q, wua_q, "oncorhynchus_mykiss", "spawning"
    )
    assert len(res.monthly) == 12
    assert (res.monthly["month"] == range(1, 13)).all()


def test_compute_sl712_columns_present() -> None:
    wua_q = make_synthetic_wua_q()
    Q = make_synthetic_discharge_series()
    res = cn_sl712.compute_sl712(Q, wua_q, "oncorhynchus_mykiss", "spawning")
    expected = {
        "month", "monthly_avg_q_m3s", "min_eco_flow_m3s",
        "suitable_eco_flow_m3s", "multi_year_avg_pct", "min_eco_flow_p90_m3s",
    }
    assert expected.issubset(set(res.monthly.columns))


def test_compute_sl712_min_lt_suitable() -> None:
    wua_q = make_synthetic_wua_q()
    Q = make_synthetic_discharge_series()
    res = cn_sl712.compute_sl712(Q, wua_q, "oncorhynchus_mykiss", "spawning",
                                  target_wua_pct=0.6, min_wua_pct=0.3)
    # min < suitable always
    assert (res.monthly["min_eco_flow_m3s"] < res.monthly["suitable_eco_flow_m3s"]).all()


def test_compute_sl712_p90_lt_monthly_avg() -> None:
    """The 90%-guarantee minimum should be ≤ monthly average."""
    wua_q = make_synthetic_wua_q()
    Q = make_synthetic_discharge_series()
    res = cn_sl712.compute_sl712(Q, wua_q, "oncorhynchus_mykiss", "spawning")
    assert (res.monthly["min_eco_flow_p90_m3s"] <= res.monthly["monthly_avg_q_m3s"]).all()


def test_compute_sl712_invalid_pct_thresholds() -> None:
    wua_q = make_synthetic_wua_q()
    Q = make_synthetic_discharge_series()
    with pytest.raises(ValueError, match="min_wua_pct"):
        cn_sl712.compute_sl712(Q, wua_q, "oncorhynchus_mykiss", "spawning",
                                target_wua_pct=0.3, min_wua_pct=0.6)


def test_compute_sl712_missing_wua_column() -> None:
    wua_q = make_synthetic_wua_q()
    Q = make_synthetic_discharge_series()
    with pytest.raises(ValueError, match="WUA column"):
        cn_sl712.compute_sl712(Q, wua_q, "nonexistent_species", "spawning")


def test_render_csv_writes_file_with_header(tmp_path: Path) -> None:
    wua_q = make_synthetic_wua_q()
    Q = make_synthetic_discharge_series()
    res = cn_sl712.compute_sl712(Q, wua_q, "oncorhynchus_mykiss", "spawning")
    out = res.to_csv(tmp_path / "sl712.csv")
    assert out.exists()
    text = out.read_text()
    assert "SL/Z 712-2014" in text
    assert "min_eco_flow_p90_m3s" in text
    # Header lines present
    assert text.count("\n") > 12


def test_compute_sl712_lemhi_real_data() -> None:
    """End-to-end with the M0 Lemhi sample data + a Lemhi WUA-Q from M1."""
    discharge_path = Path(__file__).resolve().parents[2] / "data" / "lemhi" / "Q_2024.csv"
    if not discharge_path.exists():
        pytest.skip("Lemhi data not built")

    Q = pd.read_csv(discharge_path)
    # Build a tiny WUA-Q curve (synthetic, just to drive the SL712 pipeline)
    wua_q = make_synthetic_wua_q().rename(columns={
        "wua_m2_oncorhynchus_mykiss_spawning": "wua_m2_oncorhynchus_mykiss_spawning"
    })
    res = cn_sl712.compute_sl712(Q, wua_q, "oncorhynchus_mykiss", "spawning")
    assert res.discharge_series_n >= 360
    # Lemhi annual average is ~5 m3/s
    assert 2.0 < res.annual_avg_m3s < 15.0
