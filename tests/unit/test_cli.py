"""CLI tests via Click's CliRunner. Covers the previously-stubbed commands."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from openlimno.cli import main

HERE = Path(__file__).resolve().parents[2]
LEMHI_CASE = HERE / "examples" / "lemhi" / "case.yaml"
LEMHI_DATA = HERE / "data" / "lemhi"


def test_init_creates_skeleton(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(tmp_path / "myproj"), "--basin", "test"])
    assert result.exit_code == 0
    assert (tmp_path / "myproj" / "case.yaml").exists()
    assert (tmp_path / "myproj" / "studyplan.yaml").exists()
    assert (tmp_path / "myproj" / "data").is_dir()
    assert (tmp_path / "myproj" / "README.md").exists()


def test_init_refuses_existing_dir(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "exists"
    target.mkdir()
    result = runner.invoke(main, ["init", str(target)])
    assert result.exit_code == 1


def test_validate_lemhi_case() -> None:
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi case missing")
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(LEMHI_CASE)])
    assert result.exit_code == 0


def test_studyplan_init_non_interactive(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "study.yaml"
    result = runner.invoke(
        main,
        [
            "studyplan",
            "init",
            str(out),
            "--problem",
            "Establish ecological flow recommendations for the Lemhi River for steelhead spawning.",
            "--species",
            "oncorhynchus_mykiss",
        ],
    )
    assert result.exit_code == 0
    assert out.exists()
    # The generated plan must validate
    result2 = runner.invoke(main, ["studyplan", "validate", str(out)])
    assert result2.exit_code == 0


def test_hsi_upgrade_bulk_grade(tmp_path: Path) -> None:
    if not (LEMHI_DATA / "hsi_curve.parquet").exists():
        pytest.skip("Lemhi data missing")
    src = tmp_path / "hsi_test.parquet"
    pd.read_parquet(LEMHI_DATA / "hsi_curve.parquet").to_parquet(src)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "hsi",
            "upgrade",
            str(src),
            "--set-grade",
            "A",
            "--out",
            str(tmp_path / "upgraded.parquet"),
        ],
    )
    assert result.exit_code == 0
    df = pd.read_parquet(tmp_path / "upgraded.parquet")
    assert (df["quality_grade"] == "A").all()


def test_reproduce_check_only_on_lemhi() -> None:
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi case missing")
    # First run to create provenance
    runner = CliRunner()
    runner.invoke(main, ["run", str(LEMHI_CASE)])
    prov = LEMHI_CASE.parent / "out" / "lemhi_2024" / "provenance.json"
    assert prov.exists()
    # Now reproduce check-only
    result = runner.invoke(main, ["reproduce", str(prov)])
    assert result.exit_code == 0
    assert "case YAML SHA matches" in result.output


def test_passage_cli_smoke(tmp_path: Path) -> None:
    if not (LEMHI_DATA / "swimming_performance.parquet").exists():
        pytest.skip("Lemhi data missing")
    cv_yaml = tmp_path / "cv.yaml"
    cv_yaml.write_text(
        "length_m: 18\n"
        "diameter_or_width_m: 1.2\n"
        "slope_percent: 1.5\n"
        "material: corrugated_metal\n"
        "shape: circular\n"
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "passage",
            "--culvert",
            str(cv_yaml),
            "--swim",
            str(LEMHI_DATA / "swimming_performance.parquet"),
            "--species",
            "oncorhynchus_mykiss",
            "--stage",
            "juvenile",
            "--discharge",
            "0.5",
            "--attraction-eta",
            "0.6",
        ],
    )
    assert result.exit_code == 0
    assert "η_P" in result.output or "eta_P" in result.output
    assert "η = η_A × η_P" in result.output


def test_wua_cli_outputs_table(tmp_path: Path) -> None:
    if not LEMHI_CASE.exists():
        pytest.skip("Lemhi case missing")
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "wua",
            str(LEMHI_CASE),
            "--species",
            "oncorhynchus_mykiss",
            "--stage",
            "spawning",
            "--n-q",
            "5",
        ],
    )
    assert result.exit_code == 0
    assert "discharge_m3s" in result.output
    assert "wua_m2" in result.output
