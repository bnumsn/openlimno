"""Passage tests: culvert hydraulics + η_P + attraction-passage decomposition."""

from __future__ import annotations

import numpy as np
import pytest

from openlimno.passage import (
    Culvert,
    PassageResult,
    SwimmingModel,
    load_swimming_model_from_parquet,
    passage_success_rate,
)


def test_culvert_circular_partial_flow_velocity_increases_with_q() -> None:
    cv = Culvert(length_m=20, diameter_or_width_m=1.5, slope_percent=0.5,
                 material="concrete", shape="circular")
    v_lo, h_lo = cv.barrel_velocity(0.5)
    v_hi, h_hi = cv.barrel_velocity(2.0)
    assert v_lo < v_hi
    assert h_lo < h_hi
    # Velocities reasonable: a 1.5 m concrete culvert at 0.5% slope at Q=2
    # should give ~2-3 m/s
    assert 0.5 < v_hi < 5.0


def test_culvert_box_velocity() -> None:
    cv = Culvert(length_m=20, diameter_or_width_m=2.0, slope_percent=1.0,
                 material="concrete", shape="box", height_m=2.0)
    v, h = cv.barrel_velocity(3.0)
    assert v > 0
    assert 0 < h < 2.0


def test_culvert_zero_q_zero_velocity() -> None:
    cv = Culvert(length_m=10, diameter_or_width_m=1.0, slope_percent=0.5)
    v, h = cv.barrel_velocity(0.0)
    assert v == 0
    assert h == 0


def make_steelhead_swim() -> SwimmingModel:
    """60 cm adult steelhead, T-dependent, 10/4/2 BL/s."""
    BL = 0.6
    temps = [4, 8, 12, 16, 20]
    return SwimmingModel(
        species="oncorhynchus_mykiss",
        stage="adult",
        body_length_m=BL,
        burst_curve=[(t, 10 * BL * (1 - 0.04 * abs(t - 13))) for t in temps],
        prolonged_curve=[(t, 4 * BL * (1 - 0.04 * abs(t - 13))) for t in temps],
        sustained_curve=[(t, 2 * BL * (1 - 0.04 * abs(t - 13))) for t in temps],
    )


def test_swimming_model_temperature_response() -> None:
    swim = make_steelhead_swim()
    # Peak around 13 C
    v_peak = swim.burst(13.0)
    v_cold = swim.burst(4.0)
    v_hot = swim.burst(20.0)
    assert v_peak > v_cold
    assert v_peak > v_hot


def test_passage_eta_p_low_at_high_q() -> None:
    """High discharge → high barrel velocity → low η_P (juvenile fish, smooth concrete)."""
    BL = 0.10  # 10 cm juvenile, burst speed ≈ 1.0 m/s
    swim = SwimmingModel(
        species="oncorhynchus_mykiss", stage="juvenile", body_length_m=BL,
        burst_curve=[(t, 10 * BL) for t in [4, 12, 20]],
        prolonged_curve=[(t, 4 * BL) for t in [4, 12, 20]],
        sustained_curve=[(t, 2 * BL) for t in [4, 12, 20]],
    )
    cv = Culvert(length_m=20, diameter_or_width_m=0.6, slope_percent=3.0,
                 material="concrete", shape="circular")
    res_low = passage_success_rate(cv, swim, discharge_m3s=0.05, temp_C=12.0)
    res_high = passage_success_rate(cv, swim, discharge_m3s=0.5, temp_C=12.0)
    assert res_low.eta_P > res_high.eta_P
    # Juvenile against 3% slope concrete pipe at Q=0.5 → barrel velocity high
    assert res_high.eta_P < 0.5


def test_passage_zero_q_perfect_passage() -> None:
    cv = Culvert(length_m=10, diameter_or_width_m=1.0, slope_percent=1.0)
    swim = make_steelhead_swim()
    res = passage_success_rate(cv, swim, discharge_m3s=0.0)
    assert res.eta_P == 1.0


def test_passage_monte_carlo_returns_std() -> None:
    cv = Culvert(length_m=15, diameter_or_width_m=1.2, slope_percent=1.0)
    swim = make_steelhead_swim()
    res = passage_success_rate(
        cv, swim, discharge_m3s=1.0, monte_carlo=200, seed=42
    )
    assert res.monte_carlo_std > 0
    assert 0 <= res.eta_P <= 1


def test_swim_band_selection_short_culvert_uses_burst() -> None:
    """A short (<10 m) culvert should be navigable in burst mode."""
    cv = Culvert(length_m=5, diameter_or_width_m=1.0, slope_percent=1.0)
    swim = make_steelhead_swim()
    res = passage_success_rate(cv, swim, discharge_m3s=0.5)
    assert res.swim_band == "burst"


def test_attraction_passage_decomposition_documented() -> None:
    """ADR-0007: η = η_A × η_P; ensure result type carries η_P only,
    leaving η_A composition to caller."""
    cv = Culvert(length_m=10, diameter_or_width_m=1.0, slope_percent=1.0)
    swim = make_steelhead_swim()
    res = passage_success_rate(cv, swim, discharge_m3s=0.5)
    # η_P alone; user composes η_A
    eta_A_user = 0.5  # user-supplied empirical value
    eta = eta_A_user * res.eta_P
    assert 0 <= eta <= 1
    # Ensure result type explicitly does NOT include attraction efficiency
    assert not hasattr(res, "attraction_efficiency")


def test_load_swimming_model_from_lemhi_parquet() -> None:
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "data" / "lemhi" / "swimming_performance.parquet"
    if not p.exists():
        pytest.skip("Lemhi data not built")
    swim = load_swimming_model_from_parquet(p, "oncorhynchus_mykiss", "adult")
    assert swim.body_length_m == pytest.approx(0.6, rel=0.01)
    assert swim.burst(12.0) > swim.prolonged(12.0) > swim.sustained(12.0)
