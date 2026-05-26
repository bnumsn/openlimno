"""IBM acceptance matrix tests."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from openlimno.cli import main
from openlimno.ibm import build_ibm_acceptance_report, write_ibm_acceptance_report


def _write_acceptance_manifest(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "hydraulic_parameter_calibration": {
                    "wse_rmse_m": 0.58,
                    "velocity_rmse_ms": 0.071,
                    "n_wse": 4715,
                    "n_velocity": 4,
                },
                "schism_handoff": {
                    "return_code": 0,
                    "n_nodes": 303,
                    "n_open_boundaries": 8,
                    "n_land_boundaries": 8,
                    "schism_results": {
                        "available": True,
                        "rows": 109080,
                        "n_nodes": 303,
                        "n_times": 360,
                        "warnings": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_ibm_acceptance_report_passes_local_evidence_with_official_warning(
    tmp_path: Path,
) -> None:
    manifest = _write_acceptance_manifest(tmp_path / "source_manifest.json")

    report = build_ibm_acceptance_report(
        project_root=tmp_path,
        wallens_manifest=manifest,
    )

    assert report["summary"]["failed"] == 0
    assert report["summary"]["warning"] >= 1
    assert report["summary"]["accepted"] is True
    statuses = {item["id"]: item["status"] for item in report["items"]}
    assert statuses["schism_real_numerical_solve"] == "passed"
    assert statuses["true_gis_river_boundary_handoff"] == "passed"
    assert statuses["official_instream_insalmo_fixture_sweep"] == "warning"

    paths = write_ibm_acceptance_report(report, tmp_path / "acceptance")
    assert Path(paths["ibm_acceptance_report"]).exists()
    assert Path(paths["ibm_acceptance_matrix"]).exists()
    assert Path(paths["ibm_acceptance_markdown"]).exists()


def test_ibm_acceptance_report_strict_official_fails_without_fixture(tmp_path: Path) -> None:
    manifest = _write_acceptance_manifest(tmp_path / "source_manifest.json")

    report = build_ibm_acceptance_report(
        project_root=tmp_path,
        wallens_manifest=manifest,
        strict_official=True,
    )

    assert report["summary"]["failed"] >= 1
    statuses = {item["id"]: item["status"] for item in report["items"]}
    assert statuses["official_instream_insalmo_fixture_sweep"] == "failed"


def test_ibm_acceptance_report_cli_writes_artifacts(tmp_path: Path) -> None:
    manifest = _write_acceptance_manifest(tmp_path / "source_manifest.json")
    out = tmp_path / "out"

    result = CliRunner().invoke(
        main,
        [
            "ibm-acceptance-report",
            "--wallens-manifest",
            str(manifest),
            "--out-dir",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out / "ibm_acceptance_report.json").exists()
    assert (out / "ibm_acceptance_matrix.csv").exists()
    assert (out / "ibm_acceptance_report.md").exists()
