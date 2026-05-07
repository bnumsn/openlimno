"""StudyPlan tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from openlimno.studyplan import StudyPlan, TUFOverride, merge_tuf


LEMHI_STUDYPLAN = (
    Path(__file__).resolve().parents[2] / "examples" / "lemhi" / "studyplan.yaml"
)


def test_tuf_override_invalid_length() -> None:
    with pytest.raises(ValueError, match="12 values"):
        TUFOverride(species="x", stage="adult", monthly=[1.0] * 11)


def test_tuf_override_invalid_range() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        TUFOverride(species="x", stage="adult", monthly=[1.5] + [0.0] * 11)


def test_studyplan_loads_lemhi_example() -> None:
    if not LEMHI_STUDYPLAN.exists():
        pytest.skip("Lemhi studyplan example not present")
    sp = StudyPlan.from_yaml(LEMHI_STUDYPLAN)
    assert "Lemhi River" in sp.problem_statement
    assert any(s["species"] == "oncorhynchus_mykiss" for s in sp.target_species)
    assert "wua-q" in sp.objective_variables


def test_studyplan_tuf_override_takes_precedence() -> None:
    if not LEMHI_STUDYPLAN.exists():
        pytest.skip("Lemhi studyplan example not present")
    sp = StudyPlan.from_yaml(LEMHI_STUDYPLAN)
    library_default = [1.0 / 12] * 12  # uniform
    monthly, source = sp.merge_tuf(
        "oncorhynchus_mykiss", "spawning", library_default_monthly=library_default
    )
    assert source == "case_override"
    # Override has zeros in winter
    assert monthly[0] == 0.0
    assert monthly[4] == 1.0  # May peak


def test_studyplan_falls_back_to_library_when_no_override() -> None:
    if not LEMHI_STUDYPLAN.exists():
        pytest.skip("Lemhi studyplan example not present")
    sp = StudyPlan.from_yaml(LEMHI_STUDYPLAN)
    library_default = [0.5] * 12
    monthly, source = sp.merge_tuf(
        "no_such_species", "adult", library_default_monthly=library_default
    )
    assert source == "library_default"
    assert all(m == 0.5 for m in monthly)


def test_studyplan_falls_back_to_uniform_when_no_library() -> None:
    if not LEMHI_STUDYPLAN.exists():
        pytest.skip("Lemhi studyplan example not present")
    sp = StudyPlan.from_yaml(LEMHI_STUDYPLAN)
    monthly, source = sp.merge_tuf("nope", "adult", library_default_monthly=None)
    assert source == "fallback_uniform"
    assert all(abs(m - 1.0 / 12) < 1e-9 for m in monthly)


def test_studyplan_report_contains_key_sections() -> None:
    if not LEMHI_STUDYPLAN.exists():
        pytest.skip("Lemhi studyplan example not present")
    sp = StudyPlan.from_yaml(LEMHI_STUDYPLAN)
    text = sp.report()
    assert "Problem statement" in text
    assert "Target species" in text
    assert "Objective variables" in text
    assert "TUF overrides" in text


def test_studyplan_invalid_yaml_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("problem_statement: x\n")  # too short and missing other required fields
    with pytest.raises(ValueError, match="failed schema validation"):
        StudyPlan.from_yaml(bad)


def test_module_merge_tuf_with_none_studyplan() -> None:
    monthly, source = merge_tuf(None, "x", "adult", library_default_monthly=[0.1] * 12)
    assert source == "library_default"
    assert all(m == 0.1 for m in monthly)
    monthly2, source2 = merge_tuf(None, "x", "adult", library_default_monthly=None)
    assert source2 == "fallback_uniform"
    assert len(monthly2) == 12
