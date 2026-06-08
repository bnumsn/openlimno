from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import openlimno.ibm.studio as studio
from openlimno.ibm.studio import (
    default_studio_scenario,
    import_gis_for_studio,
    run_instream7_benchmark_for_studio,
    run_studio_calibration,
    run_studio_ensemble,
    run_studio_scenario,
    validate_studio_payload,
    write_studio_scenario_files,
)


def test_run_studio_scenario_writes_native_outputs(tmp_path: Path) -> None:
    payload = default_studio_scenario()
    config = payload["config"]
    assert isinstance(config, dict)
    config["days"] = 3
    config["initial_abundance"] = 10
    config["record_individual_history"] = True

    result = run_studio_scenario(payload, tmp_path)

    assert result["ok"] is True
    assert result["metrics"]["initial_abundance"] == 10  # type: ignore[index]
    assert result["metrics"]["final_abundance"] >= 0  # type: ignore[index]
    assert len(result["population_summary"]) == 4  # type: ignore[arg-type]
    river_view = result["river_view"]
    assert isinstance(river_view, dict)
    assert river_view["river"]["name"] == "Lemhi River"  # type: ignore[index]
    geometry = river_view["geometry"]  # type: ignore[index]
    assert isinstance(geometry, dict)
    # 2026-05-26: demo now ships a synthetic outline so the plan-view
    # reads as a coherent reach. Both centerline + boundary polygon
    # round-trip through ``run_studio_scenario``.
    assert "centerline_m" in geometry
    assert "channel_polygon_m" in geometry
    assert len(geometry["centerline_m"]) > 10
    assert len(geometry["channel_polygon_m"]) > 20
    assert len(river_view["cells"]) >= 8  # type: ignore[arg-type]
    first_cell = river_view["cells"][0]  # type: ignore[index]
    assert len(first_cell["polygon_m"]) == 4
    assert len(river_view["fish"]) <= 10  # type: ignore[arg-type]
    first_fish = river_view["fish"][0]  # type: ignore[index]
    assert "x_m" in first_fish
    assert "y_m" in first_fish
    paths = result["paths"]
    assert isinstance(paths, dict)
    assert Path(paths["native_ibm_population_summary"]).exists()
    assert Path(paths["native_ibm_final_individuals"]).exists()
    assert Path(paths["native_ibm_cell_use"]).exists()
    assert Path(paths["native_ibm_individual_history"]).exists()
    assert Path(paths["studio_scenario"]).exists()
    assert Path(paths["studio_profile"]).exists()
    assert Path(paths["studio_habitat_cells"]).exists()


def test_default_studio_scenario_has_editable_sections() -> None:
    payload = default_studio_scenario()

    assert set(payload) == {
        "config",
        "river",
        "profile",
        "cells",
        "submodels",
        "submodel_catalog",
        "experiments",
        "instream",
    }
    river = payload["river"]
    assert isinstance(river, dict)
    assert river["name"] == "Lemhi River"
    # 2026-05-26 UI walkthrough fix: the demo now ships a synthetic
    # but coherent river outline so the 8 cells render on a single
    # connected channel. Real GIS boundaries still come via the
    # ``Import GIS`` UI surface.
    assert "geometry" in river
    geom = river["geometry"]
    assert isinstance(geom, dict)
    assert isinstance(geom["channel_polygon_m"], list) and len(geom["channel_polygon_m"]) > 20
    assert isinstance(geom["centerline_m"], list) and len(geom["centerline_m"]) > 10
    assert geom["crs"] == "local_m"
    # The display note must still point users at Import GIS for the
    # real shape so the synthetic outline isn't mistaken for survey data.
    # (Triple-review caught the old "or 'real Lemhi shape'" disjunct
    # was dead code — first clause is always true.)
    note = str(river["display_note"])
    assert "Import GIS" in note
    assert isinstance(payload["cells"], list)
    assert len(payload["cells"]) >= 8
    first_cell = payload["cells"][0]
    assert isinstance(first_cell, dict)
    assert {"station_m", "center_x_m", "center_y_m", "length_m", "width_m"} <= set(first_cell)
    profile = payload["profile"]
    assert isinstance(profile, dict)
    assert "base_daily_survival" in profile
    assert "cross_reach_movement_rate" in profile
    assert isinstance(payload["submodels"], dict)
    assert isinstance(payload["submodel_catalog"], list)
    assert isinstance(payload["experiments"], dict)


def test_write_studio_scenario_files_emits_versioned_contract(tmp_path: Path) -> None:
    payload = default_studio_scenario()
    paths = write_studio_scenario_files(payload, tmp_path)

    assert Path(paths["studio_scenario"]).exists()
    assert Path(paths["studio_profile"]).exists()
    assert Path(paths["studio_habitat_cells"]).exists()
    scenario_doc = Path(paths["studio_scenario"]).read_text()
    assert '"submodels"' in scenario_doc
    assert '"experiments"' in scenario_doc


def test_validate_studio_payload_reports_checks(tmp_path: Path) -> None:
    payload = default_studio_scenario()
    config = payload["config"]
    assert isinstance(config, dict)
    config["days"] = 1

    result = validate_studio_payload(payload, tmp_path)

    assert result["ok"] is True
    assert result["metrics"]["errors"] == 0  # type: ignore[index]
    checks = result["checks"]
    assert isinstance(checks, list)
    assert any(check["area"] == "scenario" for check in checks)


def test_run_studio_ensemble_returns_uncertainty_tables(tmp_path: Path) -> None:
    payload = default_studio_scenario()
    config = payload["config"]
    assert isinstance(config, dict)
    config["days"] = 1
    config["initial_abundance"] = 5
    experiments = payload["experiments"]
    assert isinstance(experiments, dict)
    ensemble = experiments["ensemble"]
    assert isinstance(ensemble, dict)
    ensemble["seeds"] = "1,2"
    ensemble["parameter_specs"] = "base_daily_survival=0.996,0.997"

    result = run_studio_ensemble(payload, tmp_path)

    assert result["ok"] is True
    assert result["metrics"]["n_runs"] == 4  # type: ignore[index]
    assert result["summary"]
    assert result["daily_bands"]
    assert Path(result["paths"]["ibm_ensemble_summary"]).exists()  # type: ignore[index]


def test_run_studio_calibration_can_generate_observed_series(tmp_path: Path) -> None:
    payload = default_studio_scenario()
    config = payload["config"]
    assert isinstance(config, dict)
    config["days"] = 1
    config["initial_abundance"] = 5
    experiments = payload["experiments"]
    assert isinstance(experiments, dict)
    calibration = experiments["calibration"]
    assert isinstance(calibration, dict)
    calibration["method"] = "grid"
    calibration["observed"] = ""
    calibration["parameter_specs"] = "base_daily_survival=0.997"

    result = run_studio_calibration(payload, tmp_path)

    assert result["ok"] is True
    assert result["metrics"]["n_candidates"] == 1  # type: ignore[index]
    assert result["best_parameters"]["base_daily_survival"] == 0.997  # type: ignore[index]
    assert Path(result["paths"]["studio_observed_abundance"]).exists()  # type: ignore[index]


def test_run_instream7_benchmark_for_studio_returns_capture_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_instream7_official_benchmark(
        root: Path,
        output_dir: Path,
        *,
        case_ids: tuple[str, ...] | None,
        days: int,
        seed: int,
        stochastic: bool,
    ) -> SimpleNamespace:
        assert root == tmp_path
        assert case_ids == ("ExampleA",)
        assert days == 1
        assert seed == 11
        assert stochastic is False
        return SimpleNamespace(
            inventory=pd.DataFrame(
                {
                    "case_id": ["ExampleA"],
                    "reach_id": ["ExampleA"],
                    "species": ["Chinook-Spring"],
                    "n_initial_fish": [0],
                    "n_adult_arrival_fish": [20],
                    "n_cells": [3],
                    "n_depth_flows": [2],
                    "n_velocity_flows": [2],
                    "n_time_series_rows": [1],
                    "min_flow_m3s": [1.2],
                    "max_flow_m3s": [4.8],
                }
            ),
            population_summary=pd.DataFrame(
                {
                    "scenario_id": ["ExampleA"],
                    "reach_id": ["ExampleA"],
                    "species": ["Chinook-Spring"],
                    "day": [1],
                    "abundance": [20],
                    "biomass_g": [1500.0],
                    "mean_length_mm": [610.0],
                }
            ),
            final_individuals=pd.DataFrame(),
            cell_use=pd.DataFrame(),
            events=pd.DataFrame(
                {
                    "scenario_id": ["ExampleA"],
                    "reach_id": ["ExampleA"],
                    "day": [1],
                    "event": ["arrival"],
                    "n": [20],
                    "n_eggs": [0],
                    "species": ["Chinook-Spring"],
                }
            ),
            redds=pd.DataFrame(),
            paths={"instream7_official_inventory": str(output_dir / "inventory.csv")},
        )

    monkeypatch.setattr(
        studio, "run_instream7_official_benchmark", fake_run_instream7_official_benchmark
    )
    monkeypatch.setattr(
        studio,
        "_official_case_river_view",
        lambda root, case_id, result: {
            "geometry": {
                "channel_polygon_m": [[0.0, 0.0], [10.0, 0.0], [10.0, 4.0]],
                "crs": "EPSG:32610",
                "source": "official ExampleA shapefile",
            },
            "cells": [{"cell_id": "1", "polygon_m": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]}],
        },
    )

    result = run_instream7_benchmark_for_studio(
        {
            "fixture": str(tmp_path),
            "case_id": "ExampleA",
            "days": 1,
            "seed": 11,
            "stochastic": False,
        },
        tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["metrics"]["suite"] == "InSALMO"  # type: ignore[index]
    assert result["metrics"]["adult_arrival_fish"] == 20  # type: ignore[index]
    assert result["metrics"]["event_counts"] == {"arrival": 20}  # type: ignore[index]
    assert result["metrics"]["gis_cells"] == 1  # type: ignore[index]
    assert result["metrics"]["gis_boundary_vertices"] == 3  # type: ignore[index]
    assert result["metrics"]["depth_flow_count"] == 2  # type: ignore[index]
    assert result["workflow"]["status"] == "passed"  # type: ignore[index]
    assert [step["id"] for step in result["workflow"]["steps"]] == [  # type: ignore[index]
        "case",
        "gis",
        "hydraulics",
        "population",
        "run",
        "validation",
    ]
    assert result["final_population"]
    assert "final_individuals" in result
    assert "cell_use" in result
    assert "redds" in result
    assert result["river_view"]["cells"]  # type: ignore[index]


def test_import_gis_for_studio_builds_river_geometry_and_cells(tmp_path: Path) -> None:
    river_path = tmp_path / "river.geojson"
    river_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "surveyed centerline"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [-113.95, 45.02],
                                [-113.949, 45.021],
                                [-113.948, 45.0205],
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cells_path = tmp_path / "cells.geojson"
    cells_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "cell_id": "cell-a",
                            "habitat_type": "riffle",
                            "csi": 0.8,
                            "depth_m": 0.4,
                            "velocity_ms": 0.6,
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-113.9500, 45.0198],
                                    [-113.9494, 45.0200],
                                    [-113.9496, 45.0204],
                                    [-113.9502, 45.0202],
                                    [-113.9500, 45.0198],
                                ]
                            ],
                        },
                    },
                    {
                        "type": "Feature",
                        "properties": {
                            "cell_id": "cell-b",
                            "habitat_type": "pool",
                            "csi": 0.9,
                            "depth_m": 0.8,
                            "velocity_ms": 0.2,
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-113.9492, 45.0205],
                                    [-113.9485, 45.0207],
                                    [-113.9488, 45.0211],
                                    [-113.9494, 45.0209],
                                    [-113.9492, 45.0205],
                                ]
                            ],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    imported = import_gis_for_studio(
        {
            "centerline_path": str(river_path),
            "cells_path": str(cells_path),
            "river_name": "Survey River",
            "reach_name": "Reach 1",
            "reach_id": "reach-1",
            "flow_m3s": 3.2,
        }
    )

    assert imported["ok"] is True
    assert imported["metrics"]["boundary_quality"] == "missing"  # type: ignore[index]
    river = imported["river"]
    assert river["name"] == "Survey River"  # type: ignore[index]
    geometry = river["geometry"]  # type: ignore[index]
    assert len(geometry["centerline_m"]) >= 3  # type: ignore[index]
    assert "channel_polygon_m" not in geometry
    cells = imported["cells"]
    assert len(cells) == 2  # type: ignore[arg-type]
    first_cell = cells[0]  # type: ignore[index]
    assert first_cell["cell_id"] == "cell-a"
    assert len(first_cell["polygon_m"]) == 4

    payload = default_studio_scenario()
    payload["river"] = river
    payload["cells"] = cells
    config = payload["config"]
    assert isinstance(config, dict)
    config["days"] = 1
    config["initial_abundance"] = 4
    run = run_studio_scenario(payload, tmp_path)

    assert run["ok"] is True
    assert run["river_view"]["geometry"]["source"] == "gis-import"  # type: ignore[index]
    assert "channel_polygon_m" not in run["river_view"]["geometry"]  # type: ignore[index]


def test_import_gis_for_studio_uses_only_river_polygons_for_channel(tmp_path: Path) -> None:
    river_path = tmp_path / "river_polygon.geojson"
    river_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "surveyed bank polygon"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-113.9504, 45.0197],
                                    [-113.9474, 45.0203],
                                    [-113.9470, 45.0212],
                                    [-113.9501, 45.0207],
                                    [-113.9504, 45.0197],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    imported = import_gis_for_studio({"boundary_path": str(river_path)})

    geometry = imported["river"]["geometry"]  # type: ignore[index]
    assert "centerline_m" not in geometry
    assert len(geometry["channel_polygon_m"]) == 4  # type: ignore[index]
    assert geometry["boundary_quality"]["status"] == "coarse"  # type: ignore[index]
    assert imported["metrics"]["boundary_vertices"] == 4  # type: ignore[index]
    assert imported["metrics"]["boundary_quality"] == "coarse"  # type: ignore[index]
    assert any("coarse/schematic" in message for message in imported["messages"])  # type: ignore[union-attr]

    payload = default_studio_scenario()
    payload["river"] = imported["river"]
    config = payload["config"]
    assert isinstance(config, dict)
    config["days"] = 1
    run = run_studio_scenario(payload, tmp_path)

    run_quality = run["river_view"]["geometry"]["boundary_quality"]  # type: ignore[index]
    assert run_quality["status"] == "coarse"
    assert run_quality["boundary_vertices"] == 4
