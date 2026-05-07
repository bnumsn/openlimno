"""SPEC §4.2.2.1 / ADR-0006 — HSI quality_grade watermark tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from openlimno.case import Case


CASE_YAML = Path(__file__).resolve().parents[2] / "examples" / "lemhi" / "case.yaml"


@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_wua_csv_has_grade_b_watermark_header_for_lemhi() -> None:
    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[1.0, 5.0, 12.0])
    csv_path = result.output_dir / "wua_q.csv"
    text = csv_path.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    # Lemhi HSI loaded as B grade (USFWS Blue Book transferred)
    assert first.startswith("#")
    assert "grade B" in first or "grade C" in first
    # Header must precede the column row
    second = text.splitlines()[1]
    assert second.startswith("discharge_m3s")


def test_grade_a_produces_no_watermark(tmp_path: Path) -> None:
    """Helper unit test on the static private method for A-grade."""
    from openlimno.case import Case as CaseClass

    # Use any Case object; only the helper is tested
    case = CaseClass(config={"case": {"name": "x"}}, case_yaml_path=tmp_path / "x.yaml")
    assert case._wua_csv_header("A") is None
    assert case._wua_csv_header("B").startswith("#")
    assert "TENTATIVE" in case._wua_csv_header("C")


@pytest.mark.skipif(not CASE_YAML.exists(), reason="Lemhi example missing")
def test_provenance_records_quality_grade() -> None:
    import json

    case = Case.from_yaml(CASE_YAML)
    result = case.run(discharges_m3s=[3.0, 6.0])
    prov = json.loads(result.provenance_path.read_text())
    assert prov["wua_quality_grade"] in {"A", "B", "C"}
