"""GIS-driven hydraulic cell generation.

This module connects real river GIS geometry to OpenLimno's hydraulic staging
tables. It creates clipped habitat/hydraulic cells from a river boundary and
centerline, builds cross-sections from a DEM when supplied, falls back to a
clearly marked synthetic section shape when DEM/bathymetry are unavailable,
then runs the built-in 1D solver to produce cell-level depth/velocity rows.

⚠️ MODULE BOUNDARY NOTE (R-IBM-HYDROSOLVER cleanup track, ADR-0016):
this module is workflow code, NOT a ``HydroSolver`` implementation.
It directly instantiates ``Builtin1D`` rather than implementing the
``HydroSolver`` protocol (``prepare`` / ``run`` / ``read_results``).
Round-22 codex A4 / gemini A3 (MEDIUM) flagged this as protocol
leakage in the hydro/ namespace.

The module STAYS in ``openlimno.hydro`` (rather than moving to
``openlimno.preprocess``) for now because it produces hydraulic
cells that ARE then consumed by the habitat surface — i.e., it's
upstream of the habitat pipeline, downstream of preprocessing.
Sibling to ``calibration.py``.

Future direction is the same as for ``calibration.py``: either
introduce a ``HydraulicWorkflow`` protocol or move to
``openlimno/workflows/``. Tracked under R-IBM-GOD-OBJECT.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from pyproj import CRS, Transformer
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, unary_union
from shapely.validation import make_valid

from openlimno.hydro.builtin_1d import Builtin1D, CrossSection

DEFAULT_DISCHARGES_M3S = (1.0, 2.0, 5.0, 10.0, 20.0)


@dataclass(frozen=True)
class GISHydraulicResult:
    """Files and diagnostics produced by the GIS hydraulic builder."""

    out_dir: Path
    hydraulic_cells_path: Path
    hydraulic_cells_geojson_path: Path
    static_cells_path: Path
    cross_sections_path: Path
    calibration_template_path: Path
    case_fragment_path: Path
    manifest_path: Path
    hydraulic_cells: pd.DataFrame
    warnings: tuple[str, ...]


def _iter_lines(geometry: BaseGeometry) -> Iterable[LineString]:
    if isinstance(geometry, LineString):
        yield geometry
    elif isinstance(geometry, MultiLineString | GeometryCollection):
        for part in geometry.geoms:
            yield from _iter_lines(part)


def _iter_polygons(geometry: BaseGeometry) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:  # type: ignore[attr-defined]
            yield from _iter_polygons(part)


def _longest_line(geometry: BaseGeometry) -> LineString:
    lines = [line for line in _iter_lines(geometry) if not line.is_empty and line.length > 0]
    if not lines:
        raise ValueError("No usable centerline geometry was found.")
    return max(lines, key=lambda line: line.length)


def _largest_polygon(geometry: BaseGeometry) -> Polygon | None:
    polygons = [poly for poly in _iter_polygons(geometry) if not poly.is_empty and poly.area > 0]
    if not polygons:
        return None
    return max(polygons, key=lambda poly: poly.area)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _read_gdf(
    path: str | Path, *, default_crs: str = "EPSG:4326"
) -> tuple[gpd.GeoDataFrame, list[str]]:
    gdf = gpd.read_file(path)
    warnings: list[str] = []
    if gdf.empty:
        raise ValueError(f"{path} contains no features.")
    if gdf.crs is None:
        gdf = gdf.set_crs(default_crs)
        warnings.append(f"{path} has no CRS; assuming {default_crs}.")
    return gdf, warnings


def _projected_crs(boundary: gpd.GeoDataFrame, centerline: gpd.GeoDataFrame) -> CRS:
    estimated = boundary.estimate_utm_crs() or centerline.estimate_utm_crs()
    if estimated is not None:
        return CRS.from_user_input(estimated)
    return CRS.from_epsg(3857)


def _tangent_normal(
    line: LineString, station_m: float, probe_m: float
) -> tuple[float, float, float, float]:
    before = line.interpolate(max(0.0, station_m - probe_m))
    after = line.interpolate(min(line.length, station_m + probe_m))
    dx = after.x - before.x
    dy = after.y - before.y
    length = math.hypot(dx, dy)
    if length <= 0:
        dx, dy, length = 1.0, 0.0, 1.0
    tx, ty = dx / length, dy / length
    return tx, ty, -ty, tx


def _make_strip(
    line: LineString, station_m: float, half_length_m: float, half_width_m: float
) -> Polygon:
    tx, ty, nx, ny = _tangent_normal(line, station_m, min(half_length_m, 30.0))
    center = line.interpolate(station_m)
    hx, hy = tx * half_length_m, ty * half_length_m
    wx, wy = nx * half_width_m, ny * half_width_m
    return Polygon(
        [
            (center.x - hx - wx, center.y - hy - wy),
            (center.x + hx - wx, center.y + hy - wy),
            (center.x + hx + wx, center.y + hy + wy),
            (center.x - hx + wx, center.y - hy + wy),
        ]
    )


def _make_transect(line: LineString, station_m: float, half_width_m: float) -> LineString:
    _, _, nx, ny = _tangent_normal(line, station_m, 30.0)
    center = line.interpolate(station_m)
    return LineString(
        [
            (center.x - nx * half_width_m, center.y - ny * half_width_m),
            (center.x + nx * half_width_m, center.y + ny * half_width_m),
        ]
    )


def _transect_clip(transect: LineString, boundary: BaseGeometry) -> LineString:
    clipped = transect.intersection(boundary)
    try:
        return _longest_line(clipped)
    except ValueError:
        return transect


def _sample_line(line: LineString, n_points: int) -> tuple[np.ndarray, list[Point]]:
    count = max(3, int(n_points))
    distances = np.linspace(0.0, line.length, count)
    return distances, [line.interpolate(float(distance)) for distance in distances]


def _dem_values(
    dem_path: str | Path,
    points: Sequence[Point],
    *,
    points_crs: CRS,
) -> tuple[np.ndarray | None, str | None]:
    try:
        import rasterio
    except ModuleNotFoundError as e:
        raise ImportError("DEM sampling requires rasterio.") from e

    with rasterio.open(dem_path) as src:
        if src.crs is None:
            raise ValueError(f"DEM {dem_path} has no CRS.")
        transformer = Transformer.from_crs(points_crs, CRS.from_user_input(src.crs), always_xy=True)
        xy = [transformer.transform(point.x, point.y) for point in points]
        values = np.array([sample[0] for sample in src.sample(xy)], dtype=float)
        nodata = src.nodata
    if nodata is not None:
        values = np.where(np.isclose(values, float(nodata)), np.nan, values)
    values = np.where(np.isfinite(values), values, np.nan)
    if np.count_nonzero(np.isfinite(values)) < 3:
        return (
            None,
            "DEM sampling returned fewer than three valid elevations; used fallback section.",
        )
    valid = pd.Series(values).interpolate(limit_direction="both").to_numpy(dtype=float)
    if float(np.nanmax(valid) - np.nanmin(valid)) < 0.03:
        return None, "DEM transect is effectively flat; used fallback section."
    return valid, None


def _synthetic_section(
    width_m: float,
    station_m: float,
    reach_length_m: float,
    *,
    slope: float,
    bank_height_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    width = max(width_m, 3.0)
    bottom_width = _clip(width * 0.35, 1.0, width * 0.8)
    left_toe = (width - bottom_width) / 2.0
    right_toe = left_toe + bottom_width
    bed = max(reach_length_m - station_m, 0.0) * max(slope, 1e-6)
    distances = np.array([0.0, left_toe, width * 0.5, right_toe, width], dtype=float)
    elevations = np.array(
        [
            bed + bank_height_m,
            bed,
            bed - min(0.15 * bank_height_m, 0.25),
            bed,
            bed + bank_height_m,
        ],
        dtype=float,
    )
    return distances, elevations


def _normalise_discharges(
    discharges_m3s: Sequence[float] | pd.DataFrame | None,
) -> pd.DataFrame:
    if discharges_m3s is None:
        discharges_m3s = DEFAULT_DISCHARGES_M3S
    if isinstance(discharges_m3s, pd.DataFrame):
        if "discharge_m3s" not in discharges_m3s:
            raise ValueError("discharge table must include a 'discharge_m3s' column.")
        flow = discharges_m3s.copy()
    else:
        flow = pd.DataFrame({"discharge_m3s": [float(q) for q in discharges_m3s]})
    flow["discharge_m3s"] = pd.to_numeric(flow["discharge_m3s"], errors="coerce")
    flow = flow[flow["discharge_m3s"].notna() & (flow["discharge_m3s"] >= 0.0)].copy()
    if flow.empty:
        raise ValueError("At least one non-negative discharge is required.")
    if "time_index" not in flow:
        flow["time_index"] = np.arange(len(flow), dtype=int)
    return flow.reset_index(drop=True)


def _source_value(row: pd.Series, key: str) -> Any:
    return row[key] if key in row and pd.notna(row[key]) else None


def _build_geometry_and_sections(
    *,
    boundary_path: str | Path,
    centerline_path: str | Path,
    dem_path: str | Path | None,
    n_cells: int,
    transect_points: int,
    manning_n: float,
    slope: float | None,
    bank_height_m: float,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, list[CrossSection], float, dict[str, Any], list[str]]:
    if n_cells < 1:
        raise ValueError("n_cells must be >= 1.")
    if transect_points < 3:
        raise ValueError("transect_points must be >= 3.")
    if manning_n <= 0:
        raise ValueError("manning_n must be positive.")
    if bank_height_m <= 0:
        raise ValueError("bank_height_m must be positive.")

    boundary_gdf, warnings = _read_gdf(boundary_path)
    centerline_gdf, center_warnings = _read_gdf(centerline_path)
    warnings.extend(center_warnings)
    crs_projected = _projected_crs(boundary_gdf, centerline_gdf)
    boundary_m = boundary_gdf.to_crs(crs_projected)
    centerline_m = centerline_gdf.to_crs(crs_projected)
    boundary = make_valid(unary_union(boundary_m.geometry))
    raw_centerline = unary_union(centerline_m.geometry)
    centerline_union = (
        raw_centerline if isinstance(raw_centerline, LineString) else linemerge(raw_centerline)
    )
    clipped_line = centerline_union.intersection(boundary.buffer(5.0))
    try:
        centerline = _longest_line(clipped_line)
    except ValueError:
        centerline = _longest_line(centerline_union)
        warnings.append("Centerline did not intersect boundary; used longest centerline feature.")
    if centerline.length <= 0:
        raise ValueError("Centerline length is zero after projection.")

    effective_slope = float(slope) if slope is not None else 0.001
    base_width_m = boundary.area / centerline.length
    half_width_m = _clip(base_width_m * 4.0, 10.0, 500.0)
    spacing_m = centerline.length / n_cells

    static_records: list[dict[str, Any]] = []
    static_geometries: list[Polygon] = []
    xs_rows: list[dict[str, Any]] = []
    sections: list[CrossSection] = []
    dem_sections = 0
    dem_warning_count = 0

    for cell_idx in range(n_cells):
        station_m = (cell_idx + 0.5) * spacing_m
        strip = _make_strip(centerline, station_m, spacing_m * 0.58, half_width_m)
        clipped_polygon = _largest_polygon(make_valid(strip.intersection(boundary)))
        if clipped_polygon is None:
            fallback = centerline.interpolate(station_m).buffer(max(base_width_m, 5.0))
            clipped_polygon = _largest_polygon(make_valid(fallback.intersection(boundary)))
        if clipped_polygon is None or clipped_polygon.area <= 1.0:
            warnings.append(f"Skipped empty cell at station {station_m:.2f} m.")
            continue

        transect = _transect_clip(_make_transect(centerline, station_m, half_width_m), boundary)
        distance_m, sample_points = _sample_line(transect, transect_points)
        elevations: np.ndarray | None = None
        source = "synthetic-boundary-width"
        if dem_path is not None:
            elevations, dem_warning = _dem_values(dem_path, sample_points, points_crs=crs_projected)
            if elevations is not None:
                source = "dem-transect"
                dem_sections += 1
            elif dem_warning is not None and dem_warning_count < 5:
                warnings.append(f"station {station_m:.2f} m: {dem_warning}")
                dem_warning_count += 1
        if elevations is None:
            width_m = max(transect.length, clipped_polygon.area / max(spacing_m, 1.0), 3.0)
            distance_m, elevations = _synthetic_section(
                width_m,
                station_m,
                centerline.length,
                slope=effective_slope,
                bank_height_m=bank_height_m,
            )

        if len(distance_m) != len(elevations) or len(distance_m) < 3:
            raise ValueError(f"Invalid cross-section at station {station_m:.2f} m.")
        if not np.all(np.diff(distance_m) > 0):
            order = np.argsort(distance_m)
            distance_m = np.asarray(distance_m, dtype=float)[order]
            elevations = np.asarray(elevations, dtype=float)[order]
        cell_id = f"gis-hydro-{len(static_records) + 1:03d}"
        representative = clipped_polygon.representative_point()
        width_attr_m = clipped_polygon.area / max(spacing_m, 1.0)
        static_records.append(
            {
                "cell_id": cell_id,
                "station_m": round(station_m, 3),
                "center_x_m": round(representative.x, 3),
                "center_y_m": round(representative.y, 3),
                "length_m": round(spacing_m, 3),
                "width_m": round(width_attr_m, 3),
                "area_m2": round(float(clipped_polygon.area), 3),
                "cross_section_source": source,
            }
        )
        static_geometries.append(clipped_polygon)
        sections.append(
            CrossSection(
                station_m=station_m,
                distance_m=np.asarray(distance_m, dtype=float),
                elevation_m=np.asarray(elevations, dtype=float),
                manning_n=manning_n,
            )
        )
        for point_idx, (distance, elevation) in enumerate(zip(distance_m, elevations, strict=True)):
            xs_rows.append(
                {
                    "station_m": round(station_m, 3),
                    "cell_id": cell_id,
                    "point_index": point_idx,
                    "distance_m": float(distance),
                    "elevation_m": float(elevation),
                    "source": source,
                    "manning_n": float(manning_n),
                }
            )

    if not static_records:
        raise ValueError("No hydraulic cells could be generated from the supplied GIS geometry.")

    if slope is None and dem_sections >= 2:
        thalwegs = [float(section.elevation_m.min()) for section in sections]
        estimated = abs(thalwegs[0] - thalwegs[-1]) / max(centerline.length, 1.0)
        if estimated >= 1e-6:
            effective_slope = _clip(estimated, 1e-6, 0.05)
            warnings.append(f"Estimated slope from DEM thalwegs: {effective_slope:.6g}.")
        else:
            warnings.append("DEM thalwegs produced near-zero slope; using default slope 0.001.")
    elif slope is None:
        warnings.append("No DEM-derived slope available; using default slope 0.001.")
    if dem_path is not None and dem_sections == 0:
        warnings.append("DEM was supplied but no valid DEM cross-sections were used.")

    static = gpd.GeoDataFrame(static_records, geometry=static_geometries, crs=crs_projected)
    cross_sections = pd.DataFrame(xs_rows)
    diagnostics = {
        "crs_projected": str(crs_projected),
        "river_area_m2": round(float(boundary.area), 3),
        "centerline_length_m": round(float(centerline.length), 3),
        "estimated_mean_width_m": round(float(base_width_m), 3),
        "n_cells": int(len(static_records)),
        "n_dem_sections": int(dem_sections),
        "slope": float(effective_slope),
        "manning_n": float(manning_n),
    }
    return static, cross_sections, sections, effective_slope, diagnostics, warnings


def _habitat_type(depth_m: float, velocity_ms: float, width_m: float, median_width_m: float) -> str:
    if width_m < 0.72 * median_width_m:
        return "margin"
    if depth_m > 0.8 and velocity_ms < 0.45:
        return "pool"
    if velocity_ms > 0.75:
        return "riffle"
    return "run"


def _write_geojson(static: gpd.GeoDataFrame, hydraulic_cells: pd.DataFrame, path: Path) -> None:
    means = (
        hydraulic_cells.groupby("cell_id", as_index=False)[
            ["depth_m", "velocity_ms", "water_surface_m", "flow_area_m2", "hydraulic_radius_m"]
        ]
        .mean()
        .round(6)
        .rename(
            columns={
                "depth_m": "mean_depth_m",
                "velocity_ms": "mean_velocity_ms",
                "water_surface_m": "mean_water_surface_m",
            }
        )
    )
    out = static.merge(means, on="cell_id", how="left").to_crs("EPSG:4326")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(path, driver="GeoJSON")


def _write_calibration_template(path: Path, static: pd.DataFrame, flow: pd.DataFrame) -> None:
    rows: list[dict[str, Any]] = []
    for _, cell in static.iterrows():
        first_q = float(flow["discharge_m3s"].iloc[0])
        rows.append(
            {
                "cell_id": cell["cell_id"],
                "station_m": cell["station_m"],
                "discharge_m3s": first_q,
                "observed_water_surface_m": "",
                "observed_depth_m": "",
                "observed_velocity_ms": "",
                "weight": 1.0,
                "note": "Fill observed fields for calibration of slope/manning_n.",
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_case_fragment(
    path: Path,
    *,
    hydraulic_cells_path: Path,
    cross_sections_path: Path,
    slope: float,
    manning_n: float,
) -> None:
    fragment = {
        "data": {
            "cross_section": str(cross_sections_path.name),
            "hydraulic_cells": str(hydraulic_cells_path.name),
        },
        "hydrodynamics": {
            "backend": "builtin-1d",
            "builtin_1d": {
                "scheme": "normal-depth",
                "slope": float(slope),
                "manning_n": float(manning_n),
            },
        },
        "ibm_forcing": {
            "habitat_cells": str(hydraulic_cells_path.name),
            "time_index_column": "time_index",
        },
    }
    path.write_text(yaml.safe_dump(fragment, sort_keys=False), encoding="utf-8")


def build_builtin1d_gis_hydraulics(
    *,
    boundary_path: str | Path,
    centerline_path: str | Path,
    out_dir: str | Path,
    discharges_m3s: Sequence[float] | pd.DataFrame | None = None,
    dem_path: str | Path | None = None,
    n_cells: int = 12,
    transect_points: int = 25,
    manning_n: float = 0.035,
    slope: float | None = None,
    bank_height_m: float = 1.5,
    output_format: str = "csv",
) -> GISHydraulicResult:
    """Build cell-level hydraulic depth/velocity from GIS via ``Builtin1D``.

    Parameters are intentionally explicit so this function can be called from
    CLI, notebooks, and example builders without a project YAML.
    """

    if output_format not in {"csv", "parquet"}:
        raise ValueError("output_format must be 'csv' or 'parquet'.")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    flow = _normalise_discharges(discharges_m3s)
    (
        static,
        cross_sections,
        sections,
        effective_slope,
        diagnostics,
        warnings,
    ) = _build_geometry_and_sections(
        boundary_path=boundary_path,
        centerline_path=centerline_path,
        dem_path=dem_path,
        n_cells=n_cells,
        transect_points=transect_points,
        manning_n=manning_n,
        slope=slope,
        bank_height_m=bank_height_m,
    )

    solver = Builtin1D(slope=effective_slope)
    static_df = pd.DataFrame(static.drop(columns="geometry"))
    median_width = float(static_df["width_m"].median())
    rows: list[dict[str, Any]] = []
    for _, flow_row in flow.iterrows():
        q = float(flow_row["discharge_m3s"])
        results = solver.solve_reach(sections, q, slope=effective_slope)
        for cell, result in zip(static_df.to_dict("records"), results, strict=True):
            depth_m = float(result.depth_mean_m)
            velocity_ms = float(result.velocity_mean_ms)
            row = {
                "time_index": int(flow_row["time_index"]),
                "cell_id": cell["cell_id"],
                "station_m": float(cell["station_m"]),
                "center_x_m": float(cell["center_x_m"]),
                "center_y_m": float(cell["center_y_m"]),
                "length_m": float(cell["length_m"]),
                "width_m": float(cell["width_m"]),
                "area_m2": float(cell["area_m2"]),
                "discharge_m3s": q,
                "water_surface_m": float(result.water_surface_m),
                "depth_m": depth_m,
                "velocity_ms": velocity_ms,
                "flow_area_m2": float(result.area_m2),
                "top_width_m": float(result.top_width_m),
                "hydraulic_radius_m": float(result.hydraulic_radius_m),
                "manning_n": float(manning_n),
                "slope": float(effective_slope),
                "habitat_type": _habitat_type(
                    depth_m, velocity_ms, float(cell["width_m"]), median_width
                ),
                "hydraulic_source": "builtin-1d-gis-dem" if dem_path else "builtin-1d-gis-boundary",
                "cross_section_source": cell["cross_section_source"],
            }
            for optional in ("date", "time", "scenario_id", "reach_id"):
                value = _source_value(flow_row, optional)
                if value is not None:
                    row[optional] = value
            rows.append(row)
    hydraulic_cells = pd.DataFrame(rows)

    suffix = ".parquet" if output_format == "parquet" else ".csv"
    hydraulic_cells_path = out / f"hydraulic_cells{suffix}"
    if output_format == "parquet":
        hydraulic_cells.to_parquet(hydraulic_cells_path, index=False)
    else:
        hydraulic_cells.to_csv(hydraulic_cells_path, index=False)
    static_cells_path = out / "hydraulic_cells_static.geojson"
    static.to_crs("EPSG:4326").to_file(static_cells_path, driver="GeoJSON")
    cross_sections_path = out / "cross_sections.parquet"
    cross_sections.to_parquet(cross_sections_path, index=False)
    hydraulic_cells_geojson_path = out / "hydraulic_cells.geojson"
    _write_geojson(static, hydraulic_cells, hydraulic_cells_geojson_path)
    calibration_template_path = out / "calibration_observed_template.csv"
    _write_calibration_template(calibration_template_path, static_df, flow)
    case_fragment_path = out / "case_fragment.yaml"
    _write_case_fragment(
        case_fragment_path,
        hydraulic_cells_path=hydraulic_cells_path,
        cross_sections_path=cross_sections_path,
        slope=effective_slope,
        manning_n=manning_n,
    )
    manifest_path = out / "hydraulic_manifest.json"
    manifest = {
        "builder": "openlimno.hydro.gis_hydraulics.build_builtin1d_gis_hydraulics",
        "boundary_path": str(boundary_path),
        "centerline_path": str(centerline_path),
        "dem_path": str(dem_path) if dem_path is not None else None,
        "solver": "builtin-1d",
        "output_format": output_format,
        "diagnostics": diagnostics,
        "files": {
            "hydraulic_cells": str(hydraulic_cells_path),
            "hydraulic_cells_geojson": str(hydraulic_cells_geojson_path),
            "static_cells": str(static_cells_path),
            "cross_sections": str(cross_sections_path),
            "calibration_template": str(calibration_template_path),
            "case_fragment": str(case_fragment_path),
        },
        "external_solver_import": {
            "schism_or_delft3d_netcdf": (
                "openlimno preprocess import-model --source delft3d-netcdf "
                "--in schout_or_ugrid_result.nc --out hydraulic_cells.csv"
            ),
            "telemac_selafin": (
                "openlimno preprocess import-model --source telemac-slf "
                "--in result.slf --out hydraulic_cells.csv"
            ),
            "hecras_hdf": (
                "openlimno preprocess import-model --source hecras-hdf "
                "--in plan.hdf --out hydraulic_cells.csv"
            ),
        },
        "warnings": warnings,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return GISHydraulicResult(
        out_dir=out,
        hydraulic_cells_path=hydraulic_cells_path,
        hydraulic_cells_geojson_path=hydraulic_cells_geojson_path,
        static_cells_path=static_cells_path,
        cross_sections_path=cross_sections_path,
        calibration_template_path=calibration_template_path,
        case_fragment_path=case_fragment_path,
        manifest_path=manifest_path,
        hydraulic_cells=hydraulic_cells,
        warnings=tuple(warnings),
    )


__all__ = [
    "DEFAULT_DISCHARGES_M3S",
    "GISHydraulicResult",
    "build_builtin1d_gis_hydraulics",
]
