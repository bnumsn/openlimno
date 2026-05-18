"""Harness-level tests for the multi-model comparison contract.

These tests run on EVERY PR (no `benchmark` marker) because they
verify the contract is wired up — not that any reference platform
runs. Reference-platform-specific benchmarks (PHABSIM, River2D,
HABBY, FishXing) live in their own packages and use the
``benchmark`` pytest marker so CI can skip them on PR runs.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from benchmarks._compare import (
    ModelAdapter,
    OpenLimnoSelfAdapter,  # type: ignore[attr-defined]
    ReferenceResult,
    compare_against,
    load_acceptance_threshold,
)


def _make_result(platform: str, q: list[float], wua: list[float]) -> ReferenceResult:
    return ReferenceResult(
        platform=platform,
        wua_q=pd.DataFrame({
            "discharge_m3s": q,
            "wua_m2_sp_juv": wua,
        }),
        provenance={"test": True},
    )


def test_compare_against_identical_results_passes():
    a = _make_result("openlimno", [1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    b = _make_result("phabsim", [1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    cmp = compare_against(a, b, threshold={"max_abs_m2": 1e-9, "max_rel": 1e-9})
    assert cmp.max_abs_error_m2 == pytest.approx(0.0)
    assert cmp.max_rel_error == pytest.approx(0.0)
    assert cmp.n_compared == 3
    assert cmp.passed is True
    assert cmp.platform_a == "openlimno"
    assert cmp.platform_b == "phabsim"


def test_compare_against_detects_difference_above_threshold():
    a = _make_result("openlimno", [1.0, 2.0], [10.0, 20.0])
    b = _make_result("river2d", [1.0, 2.0], [10.5, 19.0])
    cmp = compare_against(
        a, b, threshold={"max_abs_m2": 0.1, "max_rel": 0.01},
    )
    assert cmp.max_abs_error_m2 == pytest.approx(1.0)
    assert cmp.max_rel_error == pytest.approx(1.0 / 20.0)
    assert cmp.passed is False


def test_compare_against_within_threshold_passes_loose():
    a = _make_result("openlimno", [1.0, 2.0], [10.0, 20.0])
    b = _make_result("river2d", [1.0, 2.0], [10.5, 19.0])
    cmp = compare_against(
        a, b, threshold={"max_abs_m2": 2.0, "max_rel": 0.10},
    )
    # max_abs = 1.0 ≤ 2.0, max_rel = 0.05 ≤ 0.10 → pass
    assert cmp.passed is True


def test_compare_against_intersects_discharges_and_columns():
    """Comparison must intersect (Q, species/stage) — platforms emit
    overlapping but not identical tables."""
    a = ReferenceResult(
        platform="openlimno",
        wua_q=pd.DataFrame({
            "discharge_m3s": [1.0, 2.0, 3.0, 4.0],
            "wua_m2_sp_juv": [10.0, 20.0, 30.0, 40.0],
            "wua_m2_sp_adult": [5.0, 10.0, 15.0, 20.0],
        }),
        provenance={},
    )
    b = ReferenceResult(
        platform="habby",
        wua_q=pd.DataFrame({
            "discharge_m3s": [2.0, 3.0],
            "wua_m2_sp_juv": [20.0, 30.0],
            # No sp_adult — should be ignored.
        }),
        provenance={},
    )
    cmp = compare_against(a, b, threshold={"max_abs_m2": 1e-9, "max_rel": 1e-9})
    # Only sp_juv at q=2 and q=3 (2 cells), exact match
    assert cmp.n_compared == 2
    assert cmp.passed is True


def test_compare_against_zero_reference_relative_is_none():
    a = _make_result("openlimno", [1.0], [0.0])
    b = _make_result("phabsim", [1.0], [0.0])
    cmp = compare_against(a, b, threshold={"max_abs_m2": 1e-9})
    assert cmp.max_rel_error is None
    assert cmp.passed is True


def test_compare_against_accepts_velocity_domain_threshold():
    """FishXing comparisons use velocity thresholds, not WUA-area labels."""
    a = ReferenceResult(
        platform="openlimno",
        wua_q=pd.DataFrame({
            "discharge_m3s": [1.0],
            "velocity_ms_sp_juv": [1.20],
        }),
        provenance={},
    )
    b = ReferenceResult(
        platform="fishxing",
        wua_q=pd.DataFrame({
            "discharge_m3s": [1.0],
            "velocity_ms_sp_juv": [1.24],
        }),
        provenance={},
    )
    cmp = compare_against(
        a, b, threshold={"max_abs_m_per_s": 0.05, "max_rel": 0.05},
    )
    assert cmp.max_abs_error_m2 == pytest.approx(0.04)
    assert cmp.passed is True


def test_compare_against_empty_intersection_returns_failed():
    """No shared discharges → harness must NOT silently pass."""
    a = _make_result("openlimno", [1.0, 2.0], [10.0, 20.0])
    b = _make_result("fishxing", [10.0, 20.0], [100.0, 200.0])
    cmp = compare_against(a, b, threshold={"max_abs_m2": 1e6, "max_rel": 1.0})
    assert cmp.n_compared == 0
    assert cmp.passed is False  # No data → cannot certify equivalence


def test_acceptance_threshold_files_load():
    """Benchmark thresholds are declarative YAML files beside adapters."""
    root = Path(__file__).resolve().parents[1]
    expected = {
        "phabsim_bovee1997": ("max_abs_m2", 1.0e-3),
        "river2d": ("max_abs_m2", 50.0),
        "habby": ("max_abs_m2", 1.0e-6),
        "fishxing": ("max_abs_m_per_s", 0.05),
    }
    for name, (key, value) in expected.items():
        threshold = load_acceptance_threshold(root / name / "acceptance.yaml")
        assert threshold[key] == pytest.approx(value)
        assert "max_rel" in threshold


def test_river2d_adapter_unavailable_without_reference_dir(monkeypatch):
    """River2D adapter is unavailable until an export directory is supplied."""
    from benchmarks.river2d import River2DAdapter

    monkeypatch.delenv("RIVER2D_REFERENCE_DIR", raising=False)
    adapter: ModelAdapter = River2DAdapter()
    assert adapter.platform == "river2d"
    assert adapter.is_available() is False
    with pytest.raises(FileNotFoundError, match="RIVER2D_REFERENCE_DIR"):
        adapter.run("does/not/matter")


def test_river2d_adapter_reads_reference_export(tmp_path, monkeypatch):
    from benchmarks.river2d import River2DAdapter

    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("case: {}\n")
    pd.DataFrame({
        "Q": [1.0, 2.0],
        "species": ["sp", "sp"],
        "stage": ["juv", "juv"],
        "WUA": [10.0, 20.0],
    }).to_csv(tmp_path / "case.csv", index=False)
    monkeypatch.setenv("RIVER2D_REFERENCE_DIR", str(tmp_path))

    adapter = River2DAdapter()
    assert adapter.is_available() is True
    result = adapter.run(case_yaml)
    assert result.platform == "river2d"
    assert list(result.wua_q["wua_m2_sp_juv"]) == [10.0, 20.0]


def test_habby_adapter_availability_matches_import():
    """v2.2.0 stub contract: HABBY adapter is_available() reflects
    whether the ``habby`` Python package is importable."""
    import importlib
    try:
        importlib.import_module("habby")
        habby_importable = True
    except ImportError:
        habby_importable = False

    from benchmarks.habby import HabbyAdapter

    adapter = HabbyAdapter()
    assert adapter.platform == "habby"
    assert adapter.is_available() is habby_importable


def test_habby_adapter_reads_reference_export(tmp_path, monkeypatch):
    from benchmarks.habby import HabbyAdapter

    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("case: {}\n")
    pd.DataFrame({
        "discharge_m3s": [1.0],
        "species": ["trout"],
        "life_stage": ["adult"],
        "wua_m2": [12.5],
    }).to_csv(tmp_path / "case.csv", index=False)
    monkeypatch.setenv("HABBY_REFERENCE_DIR", str(tmp_path))

    adapter = HabbyAdapter()
    assert adapter.is_available() is True
    result = adapter.run(case_yaml)
    assert result.platform == "habby"
    assert result.wua_q.loc[0, "wua_m2_trout_adult"] == pytest.approx(12.5)


def test_fishxing_adapter_env_var_gate(monkeypatch):
    """v2.2.0 stub contract: FishXing adapter is_available() flips
    on $FISHXING_REPORT_DIR."""
    from benchmarks.fishxing import FishXingAdapter

    adapter = FishXingAdapter()
    monkeypatch.delenv("FISHXING_REPORT_DIR", raising=False)
    assert adapter.is_available() is False
    monkeypatch.setenv("FISHXING_REPORT_DIR", "/tmp/whatever")
    assert adapter.is_available() is False


def test_fishxing_adapter_reads_velocity_report(tmp_path, monkeypatch):
    from benchmarks.fishxing import FishXingAdapter

    case_yaml = tmp_path / "case.yaml"
    case_yaml.write_text("case: {}\n")
    pd.DataFrame({
        "Q": [1.0, 2.0],
        "species": ["salmon", "salmon"],
        "stage": ["adult", "adult"],
        "velocity": [0.8, 1.1],
    }).to_csv(tmp_path / "case.csv", index=False)
    monkeypatch.setenv("FISHXING_REPORT_DIR", str(tmp_path))

    adapter = FishXingAdapter()
    assert adapter.is_available() is True
    result = adapter.run(case_yaml)
    assert result.platform == "fishxing"
    assert list(result.wua_q["velocity_ms_salmon_adult"]) == [0.8, 1.1]


def test_openlimno_self_adapter_platform_id():
    """The self-adapter must announce its platform as 'openlimno'
    so the harness can label the side-A column correctly."""
    adapter = OpenLimnoSelfAdapter()
    assert adapter.platform == "openlimno"
    assert adapter.is_available() is True
