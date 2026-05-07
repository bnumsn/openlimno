"""Unit tests for habitat module: HSI evaluation, composite, WUA."""

from __future__ import annotations

import numpy as np
import pytest

from openlimno.habitat import (
    HSICurve,
    cell_wua,
    composite_csi,
    require_independence_ack,
)
from openlimno.habitat.hsi import load_hsi_from_parquet


def steelhead_depth_curve() -> HSICurve:
    return HSICurve(
        species="oncorhynchus_mykiss",
        life_stage="spawning",
        variable="depth",
        points=[(0.0, 0.0), (0.3, 1.0), (0.9, 1.0), (1.5, 0.3), (3.0, 0.0)],
        category="III",
        geographic_origin="Pacific-Northwest-USA",
        transferability_score=0.6,
        quality_grade="B",
    )


def test_hsi_evaluate_shape_and_bounds() -> None:
    c = steelhead_depth_curve()
    s = c.evaluate(np.array([0.0, 0.3, 0.6, 0.9, 1.5, 3.0]))
    assert s.shape == (6,)
    assert (s >= 0).all() and (s <= 1).all()
    # Monotonic check up to peak
    assert s[1] == pytest.approx(1.0)
    assert s[2] == pytest.approx(1.0)
    assert s[5] == pytest.approx(0.0)


def test_hsi_extrapolation_clamped() -> None:
    c = steelhead_depth_curve()
    s = c.evaluate(np.array([-1.0, 100.0]))
    assert s[0] == 0.0  # clipped to first
    assert s[1] == 0.0  # clipped to last


def test_hsi_invalid_x_monotonicity() -> None:
    with pytest.raises(ValueError, match="non-decreasing"):
        HSICurve(
            species="x",
            life_stage="adult",
            variable="depth",
            points=[(0.0, 0.0), (0.3, 1.0), (0.1, 0.5)],
            category="I",
            geographic_origin="x",
            transferability_score=0.5,
            quality_grade="C",
        )


def test_hsi_invalid_suitability_range() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        HSICurve(
            species="x",
            life_stage="adult",
            variable="depth",
            points=[(0.0, 0.0), (0.3, 1.5)],
            category="I",
            geographic_origin="x",
            transferability_score=0.5,
            quality_grade="C",
        )


def test_composite_min() -> None:
    suits = {"depth": np.array([1.0, 0.5]), "velocity": np.array([0.3, 0.8])}
    csi = composite_csi(suits, method="min")
    assert csi.tolist() == [0.3, 0.5]


def test_composite_geometric_mean_requires_ack() -> None:
    with pytest.raises(ValueError, match="acknowledge_independence"):
        require_independence_ack("geometric_mean", acknowledged=False)
    require_independence_ack("geometric_mean", acknowledged=True)


def test_composite_geometric_mean_value() -> None:
    suits = {"d": np.array([1.0, 0.25]), "v": np.array([1.0, 0.81])}
    csi = composite_csi(suits, method="geometric_mean")
    # geom-mean(1, 1) = 1; geom-mean(0.25, 0.81) = sqrt(0.2025) = 0.45
    assert csi[0] == pytest.approx(1.0)
    assert csi[1] == pytest.approx(0.45, rel=1e-3)


def test_cell_wua_basic() -> None:
    csi = np.array([0.5, 1.0, 0.0])
    area = np.array([10.0, 5.0, 100.0])
    assert cell_wua(csi, area) == pytest.approx(0.5 * 10 + 1.0 * 5 + 0.0)  # 10.0


def test_cell_wua_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape"):
        cell_wua(np.array([0.5]), np.array([1.0, 2.0]))


def test_load_hsi_from_lemhi_parquet() -> None:
    """Round-trip from the M0 Lemhi sample data."""
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "data" / "lemhi" / "hsi_curve.parquet"
    if not p.exists():
        pytest.skip("Lemhi data not built; run tools/build_lemhi_dataset.py")
    curves = load_hsi_from_parquet(p)
    # 8 curves expected
    assert len(curves) == 8
    spawn_depth = curves[("oncorhynchus_mykiss", "spawning", "depth")]
    # peak should be ≈ 1.0 between 0.3 and 0.6 m
    s = spawn_depth.evaluate(np.array([0.4]))
    assert s[0] == pytest.approx(1.0, rel=0.05)
    # 0 at 0 m
    assert spawn_depth.evaluate(np.array([0.0]))[0] == 0.0
