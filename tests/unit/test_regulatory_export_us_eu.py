"""US-FERC-4e and EU-WFD regulatory output tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from openlimno.habitat.regulatory_export import eu_wfd, us_ferc_4e


def make_synthetic_wua_q() -> pd.DataFrame:
    Qs = np.array([0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0])
    W = np.maximum(0, 100 * (1 - np.abs(np.log(Qs / 5)) / np.log(4)))
    return pd.DataFrame(
        {
            "discharge_m3s": Qs,
            "wua_m2_oncorhynchus_mykiss_spawning": W,
        }
    )


def make_multiyear_discharge(n_years: int = 8) -> pd.DataFrame:
    """Synthetic series with year-to-year variability."""
    rng = np.random.default_rng(2026)
    times = pd.date_range("2018-01-01", periods=n_years * 365, freq="D")
    doys = times.dayofyear.values
    base = 3.0 + 8.0 * np.exp(-((doys - 150) ** 2) / (2 * 30**2))
    # Year-to-year multiplier (some wet, some dry)
    year = times.year.values
    year_mult = {y: float(rng.uniform(0.5, 1.5)) for y in np.unique(year)}
    multiplier = np.array([year_mult[y] for y in year])
    Q = np.clip(base * multiplier * (1.0 + 0.1 * rng.standard_normal(len(times))), 0.3, 50.0)
    return pd.DataFrame({"time": times, "discharge_m3s": Q})


# -----------------------------------------------------------------
# FERC 4(e) tests
# -----------------------------------------------------------------
def test_ferc_returns_12_months() -> None:
    res = us_ferc_4e.compute_ferc_4e(
        make_multiyear_discharge(),
        make_synthetic_wua_q(),
        "oncorhynchus_mykiss",
        "spawning",
    )
    assert len(res.monthly_by_year_type) == 12


def test_ferc_wet_year_higher_than_dry() -> None:
    res = us_ferc_4e.compute_ferc_4e(
        make_multiyear_discharge(),
        make_synthetic_wua_q(),
        "oncorhynchus_mykiss",
        "spawning",
    )
    df = res.monthly_by_year_type.dropna()
    # On average, wet year flows must exceed dry
    assert (df["wet_year_q_m3s"] > df["dry_year_q_m3s"]).mean() > 0.7


def test_ferc_csv_export(tmp_path: Path) -> None:
    res = us_ferc_4e.compute_ferc_4e(
        make_multiyear_discharge(),
        make_synthetic_wua_q(),
        "oncorhynchus_mykiss",
        "spawning",
    )
    path = res.to_csv(tmp_path / "ferc.csv")
    assert path.exists()
    text = path.read_text()
    assert "FERC 4(e)" in text
    assert "wet_year_q_m3s" in text


def test_ferc_missing_wua_column() -> None:
    with pytest.raises(ValueError, match="WUA column"):
        us_ferc_4e.compute_ferc_4e(
            make_multiyear_discharge(),
            make_synthetic_wua_q(),
            "no_such_species",
            "spawning",
        )


# -----------------------------------------------------------------
# WFD tests
# -----------------------------------------------------------------
def test_wfd_classify_thresholds() -> None:
    from openlimno.habitat.regulatory_export.eu_wfd import _classify

    assert _classify(0.85) == "high"
    assert _classify(0.65) == "good"
    assert _classify(0.45) == "moderate"
    assert _classify(0.25) == "poor"
    assert _classify(0.10) == "bad"


def test_wfd_compute_returns_status() -> None:
    res = eu_wfd.compute_wfd(
        make_multiyear_discharge(),
        make_synthetic_wua_q(),
        "oncorhynchus_mykiss",
        "spawning",
    )
    assert res.status in ("high", "good", "moderate", "poor", "bad")
    assert 0 <= res.eqr <= 1.0


def test_wfd_monthly_eqr_per_month() -> None:
    res = eu_wfd.compute_wfd(
        make_multiyear_discharge(),
        make_synthetic_wua_q(),
        "oncorhynchus_mykiss",
        "spawning",
    )
    assert len(res.monthly_eqr) == 12
    assert "status" in res.monthly_eqr.columns


def test_wfd_csv_export(tmp_path: Path) -> None:
    res = eu_wfd.compute_wfd(
        make_multiyear_discharge(),
        make_synthetic_wua_q(),
        "oncorhynchus_mykiss",
        "spawning",
    )
    path = res.to_csv(tmp_path / "wfd.csv")
    assert path.exists()
    text = path.read_text()
    assert "WFD" in text
    assert "ecological status" in text


def test_wfd_zero_reference_raises() -> None:
    """Reference Q outside the curve gives WUA=0 → must raise."""
    wua_q = pd.DataFrame(
        {
            "discharge_m3s": [1.0, 2.0],
            "wua_m2_oncorhynchus_mykiss_spawning": [0.0, 0.0],
        }
    )
    with pytest.raises(ValueError, match="Reference WUA is zero"):
        eu_wfd.compute_wfd(
            make_multiyear_discharge(),
            wua_q,
            "oncorhynchus_mykiss",
            "spawning",
            reference_q_m3s=1.5,
        )
