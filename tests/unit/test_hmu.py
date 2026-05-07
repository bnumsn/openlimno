"""HMU classification + aggregation tests."""

from __future__ import annotations

import numpy as np
import pytest

from openlimno.habitat import (
    aggregate_wua_by_hmu,
    aggregate_wua_by_reach,
    classify_hmu,
    classify_reach,
)


def test_classify_supercritical_cascade() -> None:
    # Fr = 4 / sqrt(9.81 * 0.1) ≈ 4.04
    assert classify_hmu(velocity_ms=4.0, depth_m=0.1) == "cascade"


def test_classify_riffle_typical() -> None:
    # Fr = 0.8 / sqrt(9.81 * 0.4) ≈ 0.40 → riffle (boundary)
    label = classify_hmu(velocity_ms=0.9, depth_m=0.4)
    assert label in ("riffle", "run")  # near boundary; either acceptable


def test_classify_pool_deep_slow() -> None:
    # Fr = 0.05 / sqrt(9.81 * 2.0) ≈ 0.011 → pool
    assert classify_hmu(velocity_ms=0.05, depth_m=2.0) == "pool"


def test_classify_backwater_zero_velocity() -> None:
    assert classify_hmu(velocity_ms=0.0, depth_m=1.0) == "backwater"


def test_classify_dry_section() -> None:
    assert classify_hmu(velocity_ms=0.5, depth_m=0.0) == "backwater"


def test_classify_reach_returns_list_per_section() -> None:
    v = np.array([3.0, 0.9, 0.3, 0.1, 0.02])
    d = np.array([0.1, 0.4, 0.6, 1.5, 3.0])
    labels = classify_reach(v, d)
    assert len(labels) == 5
    assert labels[0] in ("cascade", "step")
    assert labels[-1] in ("pool", "backwater")


def test_aggregate_wua_by_hmu_sums_correctly() -> None:
    csi = np.array([1.0, 0.5, 0.5, 1.0])
    area = np.array([10.0, 20.0, 30.0, 40.0])
    labels = ["riffle", "pool", "riffle", "pool"]
    df = aggregate_wua_by_hmu(csi, area, labels)
    pool_row = df[df["hmu_type"] == "pool"].iloc[0]
    riffle_row = df[df["hmu_type"] == "riffle"].iloc[0]
    # pool: 0.5*20 + 1.0*40 = 50; riffle: 1.0*10 + 0.5*30 = 25
    assert pool_row["wua_m2"] == pytest.approx(50.0)
    assert riffle_row["wua_m2"] == pytest.approx(25.0)
    assert pool_row["n_sections"] == 2
    assert riffle_row["n_sections"] == 2


def test_aggregate_wua_by_reach() -> None:
    csi = np.array([1.0, 1.0, 1.0])
    area = np.array([10.0, 20.0, 30.0])
    reaches = ["upper", "upper", "lower"]
    df = aggregate_wua_by_reach(csi, area, reaches)
    upper = df[df["reach"] == "upper"].iloc[0]
    assert upper["wua_m2"] == 30.0
    assert upper["n_sections"] == 2
