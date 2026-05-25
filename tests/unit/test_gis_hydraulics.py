from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from click.testing import CliRunner

from openlimno.cli import main
from openlimno.hydro import build_builtin1d_gis_hydraulics


def _write_geojson(path: Path, geometry: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": geometry,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_test_river(tmp_path: Path) -> tuple[Path, Path]:
    boundary = tmp_path / "boundary.geojson"
    centerline = tmp_path / "centerline.geojson"
    _write_geojson(
        boundary,
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [-116.010, 43.000],
                    [-115.990, 43.000],
                    [-115.990, 43.004],
                    [-116.010, 43.004],
                    [-116.010, 43.000],
                ]
            ],
        },
    )
    _write_geojson(
        centerline,
        {
            "type": "LineString",
            "coordinates": [
                [-116.009, 43.002],
                [-115.991, 43.002],
            ],
        },
    )
    return boundary, centerline


def test_build_builtin1d_gis_hydraulics_from_boundary_and_centerline(tmp_path: Path) -> None:
    boundary, centerline = _write_test_river(tmp_path)
    result = build_builtin1d_gis_hydraulics(
        boundary_path=boundary,
        centerline_path=centerline,
        out_dir=tmp_path / "hydro",
        discharges_m3s=[2.0, 5.0],
        n_cells=4,
        transect_points=7,
        slope=0.001,
    )

    assert result.hydraulic_cells_path.exists()
    assert result.hydraulic_cells_geojson_path.exists()
    assert result.cross_sections_path.exists()
    assert result.calibration_template_path.exists()
    assert len(result.hydraulic_cells) == 8
    assert result.hydraulic_cells["cell_id"].nunique() == 4
    assert set(result.hydraulic_cells["discharge_m3s"]) == {2.0, 5.0}
    assert (result.hydraulic_cells["depth_m"] > 0).all()
    assert (result.hydraulic_cells["velocity_ms"] > 0).all()

    cross_sections = pd.read_parquet(result.cross_sections_path)
    assert {"station_m", "distance_m", "elevation_m", "cell_id"}.issubset(cross_sections.columns)


def test_preprocess_gis_hydraulics_cli(tmp_path: Path) -> None:
    boundary, centerline = _write_test_river(tmp_path)
    out_dir = tmp_path / "cli_hydro"

    result = CliRunner().invoke(
        main,
        [
            "preprocess",
            "gis-hydraulics",
            "--boundary",
            str(boundary),
            "--centerline",
            str(centerline),
            "--out-dir",
            str(out_dir),
            "--discharges",
            "1.5,3.0",
            "--cells",
            "3",
            "--slope",
            "0.001",
        ],
    )

    assert result.exit_code == 0, result.output
    cells = pd.read_csv(out_dir / "hydraulic_cells.csv")
    assert len(cells) == 6
    assert {"depth_m", "velocity_ms", "water_surface_m", "area_m2"}.issubset(cells.columns)
    assert "GIS hydraulic cells" in result.output
