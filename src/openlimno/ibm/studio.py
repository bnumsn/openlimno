"""Local browser UI for OpenLimno's native inSTREAM-like IBM.

⚠️ DEV/RESEARCH PREVIEW SURFACE (R-IBM-STUDIO-CONSOLIDATE)

This module is OpenLimno's third GUI surface, after:
  - ``openlimno.studio`` (PyQt6 desktop Studio — the canonical
    user-facing GUI)
  - ``openlimno.qgis.openlimno_qgis_plugin`` (M2-alpha QGIS plugin,
    maintenance-only since 2026-05-19)

Round-22 architectural review (codex A6, gemini A5; HIGH × 2) flagged
the existence of this third disconnected GUI surface as unsustainable.
Per ADR-0016 (author override; cleanup track R-IBM-STUDIO-CONSOLIDATE),
this surface is now classified as DEV-ONLY:

  - The CLI entry ``openlimno ibm-studio`` requires
    ``--i-understand-this-is-experimental`` to launch. Without that
    flag the command refuses to start.
  - This module's public API in ``openlimno.ibm.__init__`` is NOT
    in ``__all__``; users must import it via the full submodule path
    if they want to script the Studio.
  - No new UX features will be accepted here. The future direction
    is integration into the PyQt6 ``openlimno.studio`` shell OR
    outright deletion if the IBM workbench moves to a different
    deployment model.

The 3,286-LOC monolith is also on the R-IBM-GOD-OBJECT track for
splitting by responsibility (server / handlers / views / business
logic / HTML assets). That refactor is OPEN.
"""

from __future__ import annotations

import json
import math
import time
import uuid
import webbrowser
from collections.abc import Mapping
from dataclasses import fields
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import urlparse

import pandas as pd

from .experiments import parse_parameter_grid, run_ibm_calibration, run_ibm_ensemble
from .instream7 import (
    compare_instream7_native_to_brief,
    discover_instream7_cases,
    extract_instream7_archive,
    read_instream7_brief_population,
    run_instream7_official_benchmark,
    summarize_instream7_brief_population,
)
from .native import (
    SpeciesProfile,
)
from .scenario import (
    IBM_SCHEMA_VERSION,
    run_ibm_scenario,
    validate_ibm_scenario,
    validate_species_profile,
    write_species_profile,
)
from .submodels import default_submodel_selection, list_ibm_submodels, validate_submodel_selection


def _demo_cells() -> list[dict[str, object]]:
    return [
        {
            "cell_id": "upper-riffle",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "riffle",
            "station_m": 25.0,
            "center_x_m": 25.0,
            "center_y_m": 44.0,
            "length_m": 42.0,
            "width_m": 12.0,
            "area_m2": 504.0,
            "depth_m": 0.42,
            "velocity_ms": 0.74,
            "csi": 0.78,
            "temperature_c": 11.7,
            "turbidity_ntu": 2.0,
            "hiding_cover": 0.35,
            "feeding_cover": 0.72,
            "spawning_cover": 0.70,
        },
        {
            "cell_id": "left-margin",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "margin",
            "station_m": 62.0,
            "center_x_m": 62.0,
            "center_y_m": 30.0,
            "length_m": 44.0,
            "width_m": 8.0,
            "area_m2": 352.0,
            "depth_m": 0.22,
            "velocity_ms": 0.10,
            "csi": 0.42,
            "temperature_c": 12.0,
            "turbidity_ntu": 2.0,
            "hiding_cover": 0.58,
            "feeding_cover": 0.28,
            "spawning_cover": 0.18,
        },
        {
            "cell_id": "mid-run",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "run",
            "station_m": 104.0,
            "center_x_m": 104.0,
            "center_y_m": 58.0,
            "length_m": 58.0,
            "width_m": 14.0,
            "area_m2": 812.0,
            "depth_m": 0.64,
            "velocity_ms": 0.38,
            "csi": 0.88,
            "temperature_c": 11.9,
            "turbidity_ntu": 2.0,
            "hiding_cover": 0.50,
            "feeding_cover": 0.62,
            "spawning_cover": 0.42,
        },
        {
            "cell_id": "cottonwood-pool",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "pool",
            "station_m": 158.0,
            "center_x_m": 158.0,
            "center_y_m": 76.0,
            "length_m": 50.0,
            "width_m": 18.0,
            "area_m2": 900.0,
            "depth_m": 1.18,
            "velocity_ms": 0.16,
            "csi": 0.92,
            "temperature_c": 12.1,
            "turbidity_ntu": 3.0,
            "hiding_cover": 0.86,
            "feeding_cover": 0.52,
            "spawning_cover": 0.24,
        },
        {
            "cell_id": "gravel-tailout",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "tailout",
            "station_m": 208.0,
            "center_x_m": 208.0,
            "center_y_m": 52.0,
            "length_m": 46.0,
            "width_m": 11.0,
            "area_m2": 506.0,
            "depth_m": 0.36,
            "velocity_ms": 0.58,
            "csi": 0.82,
            "temperature_c": 12.0,
            "turbidity_ntu": 2.0,
            "hiding_cover": 0.30,
            "feeding_cover": 0.68,
            "spawning_cover": 0.84,
        },
        {
            "cell_id": "side-channel",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "side-channel",
            "station_m": 246.0,
            "center_x_m": 246.0,
            "center_y_m": 31.0,
            "length_m": 42.0,
            "width_m": 7.5,
            "area_m2": 315.0,
            "depth_m": 0.28,
            "velocity_ms": 0.20,
            "csi": 0.66,
            "temperature_c": 12.3,
            "turbidity_ntu": 2.5,
            "hiding_cover": 0.72,
            "feeding_cover": 0.36,
            "spawning_cover": 0.36,
        },
        {
            "cell_id": "lower-glide",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "glide",
            "station_m": 292.0,
            "center_x_m": 292.0,
            "center_y_m": 64.0,
            "length_m": 56.0,
            "width_m": 15.0,
            "area_m2": 840.0,
            "depth_m": 0.78,
            "velocity_ms": 0.31,
            "csi": 0.86,
            "temperature_c": 12.2,
            "turbidity_ntu": 2.0,
            "hiding_cover": 0.62,
            "feeding_cover": 0.55,
            "spawning_cover": 0.48,
        },
        {
            "cell_id": "boulder-chute",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "chute",
            "station_m": 344.0,
            "center_x_m": 344.0,
            "center_y_m": 42.0,
            "length_m": 36.0,
            "width_m": 9.5,
            "area_m2": 342.0,
            "depth_m": 0.48,
            "velocity_ms": 1.18,
            "csi": 0.38,
            "temperature_c": 12.0,
            "turbidity_ntu": 2.0,
            "hiding_cover": 0.18,
            "feeding_cover": 0.22,
            "spawning_cover": 0.12,
        },
    ]


def _demo_river() -> dict[str, object]:
    return {
        "name": "Lemhi River",
        "reach_name": "Hayden Creek demo reach",
        "length_m": 380.0,
        "flow_m3s": 5.8,
        "display_note": (
            "No real river boundary is bundled with the demo. Load a surveyed, "
            "remote-sensed, or GIS-derived boundary polygon to display the true river shape."
        ),
    }


def _profile_defaults() -> dict[str, object]:
    profile = SpeciesProfile()
    values: dict[str, object] = {}
    for item in fields(SpeciesProfile):
        value = getattr(profile, item.name)
        if isinstance(value, str | int | float | bool):
            values[item.name] = value
    return values


def _experiment_defaults() -> dict[str, object]:
    return {
        "ensemble": {
            "seeds": "20260524,20260525,20260526",
            "parameter_specs": "base_daily_survival=0.994,0.997,0.999",
        },
        "calibration": {
            "method": "grid",
            "observed": "",
            "parameter_specs": "base_daily_survival=0.994,0.997,0.999",
            "samples": 8,
            "acceptance_fraction": 0.25,
            "tolerance": "",
        },
    }


def _submodel_catalog() -> list[dict[str, object]]:
    return [
        {
            "slot": model.slot,
            "id": model.id,
            "label": model.label,
            "description": model.description,
            "profile_parameters": list(model.profile_parameters),
            "default": model.default,
        }
        for model in list_ibm_submodels()
    ]


def default_studio_scenario() -> dict[str, object]:
    """Return the default browser-studio scenario payload."""

    return {
        "config": {
            "scenario_id": "lemhi-river-trout-demo",
            "reach_id": "lemhi-hayden-demo",
            "species": "rainbow_trout",
            "initial_abundance": 120,
            "initial_length_mm": 115.0,
            "days": 45,
            "seed": 20260524,
            "stochastic": True,
            "record_individual_history": True,
        },
        "river": _demo_river(),
        "profile": _profile_defaults(),
        "cells": _demo_cells(),
        "submodels": default_submodel_selection(),
        "submodel_catalog": _submodel_catalog(),
        "experiments": _experiment_defaults(),
        "instream": {
            "fixture": "",
            "case_id": "ExampleA",
            "days": 2,
            "seed": 11,
            "stochastic": True,
            "native_summary": "",
            "brief_pop": "",
            "abundance_tolerance": 0,
            "biomass_relative_tolerance": 0.05,
            "mean_length_tolerance_mm": 1.0,
        },
    }


def _merged(default: Mapping[str, object], override: object) -> dict[str, object]:
    merged = dict(default)
    if isinstance(override, Mapping):
        for key, value in override.items():
            if isinstance(key, str):
                merged[key] = cast(object, value)
    return merged


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int | float):
        return bool(value)
    return default


def _as_int(value: object, default: int, *, min_value: int | None = None) -> int:
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None:
        parsed = max(parsed, min_value)
    return parsed


def _as_float(value: object, default: float, *, min_value: float | None = None) -> float:
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None:
        parsed = max(parsed, min_value)
    return parsed


def _as_str(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _point_sequence(value: object) -> list[list[float]]:
    points: list[list[float]] = []
    if not isinstance(value, list | tuple):
        return points
    for item in value:
        if not isinstance(item, list | tuple) or len(item) < 2:
            continue
        try:
            x = float(cast(Any, item[0]))
            y = float(cast(Any, item[1]))
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            points.append([x, y])
    return points


def _linestring_from_geojson(value: object) -> list[list[float]]:
    if not isinstance(value, Mapping):
        return []
    kind = _as_str(value.get("type"), "")
    if kind == "Feature":
        return _linestring_from_geojson(value.get("geometry"))
    if kind == "FeatureCollection":
        features = value.get("features")
        if isinstance(features, list):
            for feature in features:
                points = _linestring_from_geojson(feature)
                if points:
                    return points
        return []
    if kind == "LineString":
        return _point_sequence(value.get("coordinates"))
    if kind == "MultiLineString":
        lines = value.get("coordinates")
        if isinstance(lines, list):
            best: list[list[float]] = []
            for line in lines:
                points = _point_sequence(line)
                if len(points) > len(best):
                    best = points
            return best
    return []


def _polygon_from_geojson(value: object) -> list[list[float]]:
    if not isinstance(value, Mapping):
        return []
    kind = _as_str(value.get("type"), "")
    if kind == "Feature":
        return _polygon_from_geojson(value.get("geometry"))
    if kind == "FeatureCollection":
        features = value.get("features")
        if isinstance(features, list):
            for feature in features:
                points = _polygon_from_geojson(feature)
                if points:
                    return points
        return []
    if kind == "Polygon":
        rings = value.get("coordinates")
        if isinstance(rings, list) and rings:
            return _point_sequence(rings[0])
    if kind == "MultiPolygon":
        polygons = value.get("coordinates")
        if isinstance(polygons, list):
            best: list[list[float]] = []
            for polygon in polygons:
                if isinstance(polygon, list) and polygon:
                    points = _point_sequence(polygon[0])
                    if len(points) > len(best):
                        best = points
            return best
    return []


def _polygon_quality_from_points(points: list[list[float]]) -> dict[str, object]:
    if len(points) < 3:
        return {"status": "missing", "boundary_vertices": 0, "channel_area_m2": 0.0}
    area = 0.0
    perimeter = 0.0
    for idx, point in enumerate(points):
        nxt = points[(idx + 1) % len(points)]
        area += point[0] * nxt[1] - nxt[0] * point[1]
        perimeter += math.hypot(nxt[0] - point[0], nxt[1] - point[1])
    area = abs(area) / 2.0
    status = "usable"
    if len(points) < 20:
        status = "coarse"
    if area <= 0.0 or perimeter <= 0.0:
        status = "invalid"
    return {
        "status": status,
        "boundary_vertices": len(points),
        "channel_area_m2": area,
        "channel_perimeter_m": perimeter,
    }


def _normalise_boundary_quality(value: object, polygon: list[list[float]]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return _polygon_quality_from_points(polygon)
    return {
        "status": _as_str(value.get("status"), "usable" if len(polygon) >= 3 else "missing"),
        "boundary_vertices": _as_int(value.get("boundary_vertices"), len(polygon), min_value=0),
        "channel_area_m2": _as_float(value.get("channel_area_m2"), 0.0, min_value=0.0),
        "channel_perimeter_m": _as_float(
            value.get("channel_perimeter_m"),
            0.0,
            min_value=0.0,
        ),
    }


def _normalise_river_geometry(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    centerline = (
        _point_sequence(value.get("centerline_m"))
        or _point_sequence(value.get("centerline"))
        or _linestring_from_geojson(value.get("centerline_geojson"))
        or _linestring_from_geojson(value.get("geojson"))
    )
    polygon = (
        _point_sequence(value.get("channel_polygon_m"))
        or _point_sequence(value.get("channel_polygon"))
        or _point_sequence(value.get("bank_polygon_m"))
        or _polygon_from_geojson(value.get("channel_geojson"))
    )
    if len(centerline) < 2 and len(polygon) < 3:
        return {}
    geometry: dict[str, object] = {
        "crs": _as_str(value.get("crs"), "local_m"),
        "source": _as_str(value.get("source"), "payload-geometry"),
        "provenance": _as_str(value.get("provenance"), ""),
    }
    if len(centerline) >= 2:
        geometry["centerline_m"] = centerline
    if len(polygon) >= 3:
        geometry["channel_polygon_m"] = polygon
        geometry["boundary_quality"] = _normalise_boundary_quality(
            value.get("boundary_quality"),
            polygon,
        )
    return geometry


def _line_length(points: list[list[float]]) -> float:
    total = 0.0
    for idx in range(1, len(points)):
        total += math.hypot(points[idx][0] - points[idx - 1][0], points[idx][1] - points[idx - 1][1])
    return total


def _sample_line(
    points: list[list[float]],
    station_m: float,
) -> tuple[float, float, float, float, float, float]:
    if len(points) < 2:
        return (station_m, 0.0, 1.0, 0.0, 0.0, 1.0)
    remaining = max(0.0, station_m)
    for idx in range(1, len(points)):
        x0, y0 = points[idx - 1]
        x1, y1 = points[idx]
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length <= 0.0:
            continue
        if remaining <= length:
            t = remaining / length
            tx = dx / length
            ty = dy / length
            return (x0 + dx * t, y0 + dy * t, tx, ty, -ty, tx)
        remaining -= length
    x0, y0 = points[-2]
    x1, y1 = points[-1]
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy) or 1.0
    tx = dx / length
    ty = dy / length
    return (x1, y1, tx, ty, -ty, tx)


def _oriented_cell_polygon(
    *,
    center_x: float,
    center_y: float,
    length_m: float,
    width_m: float,
    axis_x: float,
    axis_y: float,
    normal_x: float,
    normal_y: float,
) -> list[list[float]]:
    half_l = max(length_m, 1.0) / 2.0
    half_w = max(width_m, 1.0) / 2.0
    return [
        [
            center_x - axis_x * half_l - normal_x * half_w,
            center_y - axis_y * half_l - normal_y * half_w,
        ],
        [
            center_x + axis_x * half_l - normal_x * half_w,
            center_y + axis_y * half_l - normal_y * half_w,
        ],
        [
            center_x + axis_x * half_l + normal_x * half_w,
            center_y + axis_y * half_l + normal_y * half_w,
        ],
        [
            center_x - axis_x * half_l + normal_x * half_w,
            center_y - axis_y * half_l + normal_y * half_w,
        ],
    ]


def _vector_source(value: object) -> str | Path:
    raw = _as_str(value, "")
    if not raw:
        raise ValueError("GIS path is required")
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    path = Path(raw).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"GIS file not found: {path}")
    return path


def _is_vector_url(source: str | Path) -> bool:
    if not isinstance(source, str):
        return False
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _read_vector_file(source: str | Path, layer: object) -> Any:
    import geopandas as gpd

    layer_name = _as_str(layer, "")
    if layer_name and not _is_vector_url(source):
        return gpd.read_file(source, layer=layer_name)
    return gpd.read_file(source)


def _choose_metric_crs(gdfs: list[Any]) -> object | None:
    for gdf in gdfs:
        crs = getattr(gdf, "crs", None)
        if crs is None:
            continue
        if getattr(crs, "is_geographic", False):
            estimated = gdf.estimate_utm_crs()
            return estimated or "EPSG:3857"
        return crs
    return None


def _to_common_metric(gdf: Any, target_crs: object | None) -> Any:
    crs = getattr(gdf, "crs", None)
    if target_crs is not None and crs is not None:
        return gdf.to_crs(target_crs)
    if crs is not None and getattr(crs, "is_geographic", False):
        estimated = gdf.estimate_utm_crs()
        return gdf.to_crs(estimated or "EPSG:3857")
    return gdf


def _translated_geometries(gdf: Any, *, origin_x: float, origin_y: float) -> Any:
    from shapely import affinity

    out = gdf.copy()
    out.geometry = out.geometry.apply(
        lambda geom: affinity.translate(geom, xoff=-origin_x, yoff=-origin_y)
        if geom is not None and not geom.is_empty
        else geom
    )
    return out


def _geometry_parts(geom: object, geom_types: set[str]) -> list[Any]:
    if geom is None or bool(getattr(geom, "is_empty", True)):
        return []
    geom_type = str(getattr(geom, "geom_type", ""))
    if geom_type in geom_types:
        return [geom]
    geoms = getattr(geom, "geoms", None)
    if geoms is None:
        return []
    parts: list[Any] = []
    for item in geoms:
        parts.extend(_geometry_parts(item, geom_types))
    return parts


def _limit_points(points: list[list[float]], *, max_points: int = 1200) -> list[list[float]]:
    if len(points) <= max_points:
        return points
    stride = max(1, math.ceil(len(points) / max_points))
    limited = points[::stride]
    if limited[-1] != points[-1]:
        limited.append(points[-1])
    return limited


def _coords_from_line(line: Any) -> list[list[float]]:
    return _limit_points([[float(x), float(y)] for x, y, *_ in line.coords])


def _coords_from_polygon(polygon: Any) -> list[list[float]]:
    coords = [[float(x), float(y)] for x, y, *_ in polygon.exterior.coords]
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords.pop()
    return _limit_points(coords)


def _boundary_quality(channel_polygon: Any | None, messages: list[str]) -> dict[str, object]:
    if channel_polygon is None:
        return {"status": "missing", "boundary_vertices": 0, "channel_area_m2": 0.0}
    vertices = max(len(list(channel_polygon.exterior.coords)) - 1, 0)
    area_m2 = max(float(channel_polygon.area), 0.0)
    perimeter_m = max(float(channel_polygon.length), 0.0)
    status = "usable"
    if vertices < 20:
        status = "coarse"
        messages.append(
            f"Boundary polygon has only {vertices} vertices; treat it as coarse/schematic, not visual proof of a surveyed bank line."
        )
    if area_m2 <= 0.0 or perimeter_m <= 0.0:
        status = "invalid"
        messages.append("Boundary polygon has zero area or perimeter; no real channel boundary can be verified.")
    return {
        "status": status,
        "boundary_vertices": vertices,
        "channel_area_m2": area_m2,
        "channel_perimeter_m": perimeter_m,
    }


def _best_line(lines: list[Any]) -> Any | None:
    if not lines:
        return None
    try:
        from shapely.ops import linemerge, unary_union

        merged = linemerge(unary_union(lines))
        merged_lines = _geometry_parts(merged, {"LineString"})
        if merged_lines:
            return max(merged_lines, key=lambda geom: float(geom.length))
    except Exception:
        pass
    return max(lines, key=lambda geom: float(geom.length))


def _best_polygon(polygons: list[Any]) -> Any | None:
    if not polygons:
        return None
    try:
        from shapely.ops import unary_union

        merged = unary_union(polygons)
        merged_polygons = _geometry_parts(merged, {"Polygon"})
        if merged_polygons:
            return max(merged_polygons, key=lambda geom: float(geom.area))
    except Exception:
        pass
    return max(polygons, key=lambda geom: float(geom.area))


def _row_value(row: Any, candidates: tuple[str, ...], default: object) -> object:
    lookup = {str(column).lower(): column for column in row.index}
    for candidate in candidates:
        column = lookup.get(candidate.lower())
        if column is None:
            continue
        value = row[column]
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        try:
            if bool(pd.isna(value)):
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def _row_float(row: Any, candidates: tuple[str, ...], default: float) -> float:
    value = _row_value(row, candidates, default)
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _rotated_rectangle_size(geom: Any) -> tuple[float, float]:
    rect = geom.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    if len(coords) < 4:
        return (max(math.sqrt(float(geom.area)), 1.0), max(math.sqrt(float(geom.area)), 1.0))
    lengths = [
        math.hypot(coords[idx + 1][0] - coords[idx][0], coords[idx + 1][1] - coords[idx][1])
        for idx in range(min(4, len(coords) - 1))
    ]
    positive = [length for length in lengths if length > 0.0]
    if not positive:
        side = max(math.sqrt(float(geom.area)), 1.0)
        return (side, side)
    return (max(positive), min(positive))


def _geometry_from_gis(
    *,
    centerline_gdf: Any | None,
    boundary_gdf: Any | None,
    cells_gdf: Any | None,
    target_crs: object | None,
) -> tuple[dict[str, object], Any | None, list[Any], list[str]]:
    messages: list[str] = []
    line_parts: list[Any] = []
    boundary_polygons: list[Any] = []
    cell_polygons: list[Any] = []
    if centerline_gdf is not None:
        for geom in centerline_gdf.geometry:
            line_parts.extend(_geometry_parts(geom, {"LineString"}))
    if boundary_gdf is not None:
        for geom in boundary_gdf.geometry:
            boundary_polygons.extend(_geometry_parts(geom, {"Polygon"}))
    if cells_gdf is not None:
        for geom in cells_gdf.geometry:
            cell_polygons.extend(_geometry_parts(geom, {"Polygon"}))

    centerline = _best_line(line_parts)
    channel_polygon = _best_polygon(boundary_polygons)
    if centerline is None and centerline_gdf is not None:
        messages.append("Centerline GIS layer has no line geometry; no centerline was imported.")
    if channel_polygon is None and boundary_gdf is not None:
        messages.append("Boundary GIS layer has no polygon geometry; no river boundary was imported.")
    if centerline is None and channel_polygon is None and cell_polygons:
        messages.append("No river boundary/centerline imported; displaying habitat-cell polygons only.")
    geometry: dict[str, object] = {
        "crs": str(target_crs) if target_crs is not None else "source",
        "source": "gis-import",
        "provenance": "Imported directly from local GIS vector data.",
    }
    if centerline is not None:
        geometry["centerline_m"] = _coords_from_line(centerline)
    if channel_polygon is not None:
        geometry["channel_polygon_m"] = _coords_from_polygon(channel_polygon)
    geometry["boundary_quality"] = _boundary_quality(channel_polygon, messages)
    return geometry, centerline, cell_polygons, messages


def _gis_cells_from_polygons(
    gdf: Any,
    *,
    centerline: Any | None,
    reach_id: str,
) -> tuple[list[dict[str, object]], list[str]]:
    cells: list[dict[str, object]] = []
    messages: list[str] = []
    polygons: list[tuple[int, Any, Any]] = []
    for idx, row in gdf.iterrows():
        for polygon in _geometry_parts(row.geometry, {"Polygon"}):
            polygons.append((int(idx) if isinstance(idx, int) else len(polygons), row, polygon))
    if not polygons:
        return [], ["No polygon features found in habitat-cell GIS layer."]

    for order, row, polygon in polygons:
        point = polygon.representative_point()
        area_m2 = max(float(polygon.area), 0.0)
        length_m, width_m = _rotated_rectangle_size(polygon)
        station_default = float(centerline.project(point)) if centerline is not None else float(order)
        csi_raw = _row_value(row, ("csi", "CSI", "suitability", "si", "HSI"), None)
        wua_raw = _row_value(row, ("wua_m2", "WUA", "wua"), None)
        if csi_raw is None and wua_raw is not None and area_m2 > 0.0:
            try:
                csi = max(0.0, min(1.0, float(cast(Any, wua_raw)) / area_m2))
            except (TypeError, ValueError):
                csi = 0.65
        else:
            csi = max(0.0, min(1.0, _row_float(row, ("csi", "CSI", "suitability", "si", "HSI"), 0.65)))
        if csi_raw is None and wua_raw is None:
            messages.append("Missing CSI/WUA fields in some cells; defaulted CSI to 0.65.")
        cells.append(
            {
                "cell_id": str(
                    _row_value(row, ("cell_id", "cellid", "CELL_ID", "id", "ID"), f"gis-{order + 1}")
                ),
                "reach_id": str(_row_value(row, ("reach_id", "reach", "REACH"), reach_id)),
                "reach_order": int(_row_float(row, ("reach_order", "order", "ORDER"), 1.0)),
                "habitat_type": str(
                    _row_value(
                        row,
                        ("habitat_type", "habitat", "type", "mesohabitat", "HMU"),
                        "gis-cell",
                    )
                ),
                "station_m": _row_float(row, ("station_m", "station", "dist_m", "distance_m"), station_default),
                "center_x_m": float(point.x),
                "center_y_m": float(point.y),
                "length_m": length_m,
                "width_m": width_m,
                "polygon_m": _coords_from_polygon(polygon),
                "area_m2": area_m2,
                "depth_m": _row_float(row, ("depth_m", "depth", "DEPTH"), 0.5),
                "velocity_ms": _row_float(row, ("velocity_ms", "velocity", "vel_ms", "VEL"), 0.35),
                "csi": csi,
                "temperature_c": _row_float(row, ("temperature_c", "temp_c", "TEMP"), 12.0),
                "turbidity_ntu": _row_float(row, ("turbidity_ntu", "turbidity", "TURB"), 0.0),
                "hiding_cover": max(
                    0.0,
                    min(1.0, _row_float(row, ("hiding_cover", "hiding", "cover"), 0.25)),
                ),
                "feeding_cover": max(
                    0.0,
                    min(1.0, _row_float(row, ("feeding_cover", "feeding", "shelter"), 0.25)),
                ),
                "spawning_cover": max(
                    0.0,
                    min(1.0, _row_float(row, ("spawning_cover", "spawning", "spawn"), 0.20)),
                ),
            }
        )
    cells.sort(key=lambda item: float(cast(Any, item["station_m"])))
    return cells, sorted(set(messages))


def import_gis_for_studio(request: Mapping[str, object]) -> dict[str, object]:
    """Import local GIS vector files into the browser Studio payload contract."""

    legacy_river_path_value = _as_str(request.get("river_path"), "")
    centerline_path_value = _as_str(request.get("centerline_path"), "")
    boundary_path_value = _as_str(request.get("boundary_path"), "")
    cells_path_value = _as_str(request.get("cells_path"), "")
    if not legacy_river_path_value and not centerline_path_value and not boundary_path_value and not cells_path_value:
        raise ValueError(
            "provide a centerline path, river-boundary path, habitat-cell path, or legacy river path"
        )

    legacy_river_gdf = (
        _read_vector_file(_vector_source(legacy_river_path_value), request.get("river_layer"))
        if legacy_river_path_value
        else None
    )
    centerline_gdf = (
        _read_vector_file(_vector_source(centerline_path_value), request.get("centerline_layer"))
        if centerline_path_value
        else None
    )
    boundary_gdf = (
        _read_vector_file(_vector_source(boundary_path_value), request.get("boundary_layer"))
        if boundary_path_value
        else None
    )
    cells_gdf = (
        _read_vector_file(_vector_source(cells_path_value), request.get("cells_layer"))
        if cells_path_value
        else None
    )
    if legacy_river_gdf is not None and centerline_gdf is None and boundary_gdf is None:
        centerline_gdf = legacy_river_gdf
        boundary_gdf = legacy_river_gdf
    loaded = [gdf for gdf in (centerline_gdf, boundary_gdf, cells_gdf) if gdf is not None]
    if not loaded:
        raise ValueError("no GIS layers were loaded")
    target_crs = _choose_metric_crs(loaded)
    metric_centerline_gdf = _to_common_metric(centerline_gdf, target_crs) if centerline_gdf is not None else None
    metric_boundary_gdf = _to_common_metric(boundary_gdf, target_crs) if boundary_gdf is not None else None
    metric_cells_gdf = _to_common_metric(cells_gdf, target_crs) if cells_gdf is not None else None
    metric_loaded = [
        gdf for gdf in (metric_centerline_gdf, metric_boundary_gdf, metric_cells_gdf) if gdf is not None
    ]
    bounds = [gdf.total_bounds for gdf in metric_loaded if len(gdf) > 0 and not gdf.empty]
    if not bounds:
        raise ValueError("GIS layers contain no features")
    origin_x = min(float(bound[0]) for bound in bounds)
    origin_y = min(float(bound[1]) for bound in bounds)

    metric_centerline_gdf = (
        _translated_geometries(metric_centerline_gdf, origin_x=origin_x, origin_y=origin_y)
        if metric_centerline_gdf is not None
        else None
    )
    metric_boundary_gdf = (
        _translated_geometries(metric_boundary_gdf, origin_x=origin_x, origin_y=origin_y)
        if metric_boundary_gdf is not None
        else None
    )
    metric_cells_gdf = (
        _translated_geometries(metric_cells_gdf, origin_x=origin_x, origin_y=origin_y)
        if metric_cells_gdf is not None
        else None
    )

    geometry, centerline, cell_polygons, messages = _geometry_from_gis(
        centerline_gdf=metric_centerline_gdf,
        boundary_gdf=metric_boundary_gdf,
        cells_gdf=metric_cells_gdf,
        target_crs=target_crs,
    )
    if "centerline_m" not in geometry and "channel_polygon_m" not in geometry and not cell_polygons:
        raise ValueError("GIS data must contain river line/polygon geometry or habitat-cell polygons")
    if target_crs is None:
        messages.append("GIS layer has no CRS; coordinates were treated as already projected.")

    reach_id = _as_str(request.get("reach_id"), "gis-reach")
    cells: list[dict[str, object]] = []
    if metric_cells_gdf is not None:
        cells, cell_messages = _gis_cells_from_polygons(
            metric_cells_gdf,
            centerline=centerline,
            reach_id=reach_id,
        )
        messages.extend(cell_messages)

    length_m = _as_float(request.get("length_m"), 0.0, min_value=0.0)
    if centerline is not None:
        length_m = float(centerline.length)
    elif length_m <= 0.0 and cell_polygons:
        length_m = max((float(geom.bounds[2]) for geom in cell_polygons), default=1.0)
    elif length_m <= 0.0 and isinstance(geometry.get("channel_polygon_m"), list):
        points = _point_sequence(geometry.get("channel_polygon_m"))
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        length_m = max(max(xs) - min(xs), max(ys) - min(ys), 1.0) if xs and ys else 1.0
    river = {
        "name": _as_str(request.get("river_name"), "GIS river"),
        "reach_name": _as_str(request.get("reach_name"), "GIS reach"),
        "length_m": max(length_m, 1.0),
        "flow_m3s": _as_float(request.get("flow_m3s"), 0.0, min_value=0.0),
        "display_note": "GIS geometry imported directly from vector data; boundary quality is reported from the source polygon.",
        "geometry": geometry,
    }
    quality = cast(dict[str, object], geometry.get("boundary_quality", {}))
    return {
        "ok": True,
        "river": river,
        "cells": cells,
        "metrics": {
            "centerline_features": int(len(centerline_gdf)) if centerline_gdf is not None else 0,
            "boundary_features": int(len(boundary_gdf)) if boundary_gdf is not None else 0,
            "river_features": int(len(legacy_river_gdf)) if legacy_river_gdf is not None else 0,
            "cell_features": int(len(cells)) if cells else 0,
            "centerline_points": len(cast(list[object], geometry.get("centerline_m", []))),
            "channel_polygon_points": len(cast(list[object], geometry.get("channel_polygon_m", []))),
            "boundary_quality": _as_str(quality.get("status"), "missing"),
            "boundary_vertices": _as_int(quality.get("boundary_vertices"), 0, min_value=0),
            "channel_area_m2": _as_float(quality.get("channel_area_m2"), 0.0, min_value=0.0),
            "target_crs": str(target_crs) if target_crs is not None else "source",
        },
        "messages": sorted(set(messages)),
    }


def _profile_from_payload(value: object, *, species: str) -> SpeciesProfile:
    defaults = _profile_defaults()
    payload = _merged(defaults, value)
    payload["species"] = species
    kwargs: dict[str, Any] = {}
    for key, default_value in defaults.items():
        candidate = payload.get(key, default_value)
        if isinstance(default_value, bool):
            kwargs[key] = _as_bool(candidate, default_value)
        elif isinstance(default_value, int) and not isinstance(default_value, bool):
            kwargs[key] = _as_int(candidate, default_value)
        elif isinstance(default_value, float):
            kwargs[key] = _as_float(candidate, default_value)
        elif isinstance(default_value, str):
            kwargs[key] = _as_str(candidate, default_value)
    return SpeciesProfile(**kwargs)


def _cells_from_payload(value: object) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if isinstance(value, list):
        for row in value:
            if isinstance(row, Mapping):
                rows.append({str(key): cast(object, item) for key, item in row.items()})
    if not rows:
        rows = _demo_cells()
    return pd.DataFrame(rows)


def _int_list(value: object, default: tuple[int, ...]) -> tuple[int, ...]:
    if isinstance(value, str):
        tokens = [
            token.strip()
            for chunk in value.replace("\n", ",").split(",")
            for token in chunk.split()
            if token.strip()
        ]
        try:
            parsed = tuple(int(token) for token in tokens)
        except ValueError:
            parsed = ()
        return parsed or default
    if isinstance(value, list | tuple):
        parsed_items: list[int] = []
        for item in value:
            try:
                parsed_items.append(int(cast(Any, item)))
            except (TypeError, ValueError):
                continue
        return tuple(parsed_items) or default
    return default


def _parameter_grid_from_payload(value: object) -> dict[str, tuple[float, ...]]:
    if isinstance(value, Mapping):
        normalised: dict[str, tuple[float, ...]] = {}
        for key, raw in value.items():
            if not isinstance(key, str):
                continue
            if isinstance(raw, str):
                parts = [part.strip() for part in raw.split(",") if part.strip()]
            elif isinstance(raw, list | tuple):
                parts = list(raw)
            else:
                parts = [raw]
            try:
                normalised[key] = tuple(float(cast(Any, part)) for part in parts)
            except (TypeError, ValueError):
                continue
        return normalised
    if isinstance(value, str):
        specs = [line.strip() for line in value.replace(";", "\n").splitlines() if line.strip()]
        if not specs and value.strip():
            specs = [value.strip()]
        return parse_parameter_grid(specs) if specs else {}
    if isinstance(value, list | tuple):
        specs = [str(item).strip() for item in value if str(item).strip()]
        return parse_parameter_grid(specs) if specs else {}
    return {}


def _normalise_submodels(value: object) -> dict[str, str]:
    selection = default_submodel_selection()
    if isinstance(value, Mapping):
        for slot, raw_id in value.items():
            if isinstance(slot, str) and isinstance(raw_id, str) and raw_id.strip():
                selection[slot] = raw_id.strip()
    return selection


def _studio_experiments(value: object) -> dict[str, object]:
    defaults = _experiment_defaults()
    if not isinstance(value, Mapping):
        return defaults
    experiments = dict(defaults)
    for section in ("ensemble", "calibration"):
        experiments[section] = _merged(
            cast(Mapping[str, object], defaults[section]),
            value.get(section),
        )
    return experiments


def _scenario_experiments_from_payload(
    value: object,
    *,
    default_seed: int,
    calibration_observed: str | None = None,
) -> dict[str, object]:
    experiments = _studio_experiments(value)
    scenario_block: dict[str, object] = {}
    ensemble = cast(Mapping[str, object], experiments["ensemble"])
    seeds = _int_list(
        ensemble.get("seeds"),
        (default_seed, default_seed + 1, default_seed + 2),
    )
    ensemble_grid = _parameter_grid_from_payload(
        ensemble.get("parameter_specs") or ensemble.get("parameters")
    )
    scenario_block["ensemble"] = {
        "seeds": list(seeds),
        "parameters": {name: list(values) for name, values in ensemble_grid.items()},
    }

    calibration = cast(Mapping[str, object], experiments["calibration"])
    observed = calibration_observed or _as_str(calibration.get("observed"), "")
    calibration_grid = _parameter_grid_from_payload(
        calibration.get("parameter_specs") or calibration.get("parameters")
    )
    if observed and calibration_grid:
        method = _as_str(calibration.get("method"), "grid")
        block: dict[str, object] = {
            "observed": observed,
            "method": method if method in {"grid", "abc"} else "grid",
            "parameters": {name: list(values) for name, values in calibration_grid.items()},
            "samples": _as_int(calibration.get("samples"), 8, min_value=1),
            "acceptance_fraction": _as_float(
                calibration.get("acceptance_fraction"),
                0.25,
                min_value=0.000001,
            ),
            "seed": default_seed,
        }
        tolerance_value = calibration.get("tolerance")
        if tolerance_value not in (None, ""):
            block["tolerance"] = _as_float(tolerance_value, 0.0, min_value=0.0)
        scenario_block["calibration"] = block
    return scenario_block


def _records(df: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, object]]:
    if df.empty:
        return []
    table = df.head(limit).copy() if limit is not None else df.copy()
    table = table.astype(object).where(pd.notna(table), None)
    return cast(list[dict[str, object]], table.to_dict(orient="records"))


def _sum_numeric(df: pd.DataFrame, column: str) -> float:
    if column not in df:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _min_numeric(df: pd.DataFrame, column: str) -> float | None:
    if column not in df:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.min()) if not values.empty else None


def _max_numeric(df: pd.DataFrame, column: str) -> float | None:
    if column not in df:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.max()) if not values.empty else None


def _official_gis_metrics(river_view: object) -> dict[str, object]:
    if not isinstance(river_view, Mapping):
        return {
            "gis_cells": 0,
            "gis_boundary_vertices": 0,
            "gis_boundary_status": "missing",
            "gis_crs": "",
            "gis_source": "",
        }
    geometry = river_view.get("geometry", {})
    geometry_map = cast(Mapping[str, object], geometry) if isinstance(geometry, Mapping) else {}
    quality = geometry_map.get("boundary_quality", {})
    quality_map = cast(Mapping[str, object], quality) if isinstance(quality, Mapping) else {}
    channel = geometry_map.get("channel_polygon_m", [])
    cells = river_view.get("cells", [])
    raw_boundary_vertices = quality_map.get("boundary_vertices")
    boundary_vertices = (
        int(raw_boundary_vertices or 0)
        if isinstance(raw_boundary_vertices, (int, float))
        else 0
    )
    if not boundary_vertices and isinstance(channel, list):
        boundary_vertices = len(channel)
    return {
        "gis_cells": len(cells) if isinstance(cells, list) else 0,
        "gis_boundary_vertices": boundary_vertices,
        "gis_boundary_status": _as_str(quality_map.get("status"), "missing"),
        "gis_crs": _as_str(geometry_map.get("crs"), ""),
        "gis_source": _as_str(geometry_map.get("source"), ""),
    }


def _workflow_step(
    step_id: str,
    label: str,
    status: str,
    summary: str,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "id": step_id,
        "label": label,
        "status": status,
        "summary": summary,
        "evidence": dict(evidence),
    }


def _metric_int(metrics: Mapping[str, object], name: str) -> int:
    return int(_as_float(metrics.get(name), 0.0))


def _official_workflow(
    metrics: Mapping[str, object],
    *,
    case_id: str,
    days: int,
    run_dir: Path,
) -> dict[str, object]:
    initial_fish = _metric_int(metrics, "initial_fish")
    adult_arrival_fish = _metric_int(metrics, "adult_arrival_fish")
    final_abundance = _metric_int(metrics, "final_abundance")
    gis_cells = _metric_int(metrics, "gis_cells")
    gis_boundary_vertices = _metric_int(metrics, "gis_boundary_vertices")
    population_rows = _metric_int(metrics, "population_rows")
    time_series_rows = _metric_int(metrics, "time_series_rows")
    status = "passed"
    steps = [
        _workflow_step(
            "case",
            "1 Case",
            "passed" if _metric_int(metrics, "case_count") else "warning",
            f"{case_id} parsed as {metrics.get('suite', 'official')}",
            {
                "Cases": metrics.get("case_count", 0),
                "Reaches": metrics.get("reach_count", 0),
                "Species": metrics.get("species_count", 0),
            },
        ),
        _workflow_step(
            "gis",
            "2 GIS",
            "passed" if gis_cells and gis_boundary_vertices >= 3 else "warning",
            "real official cell polygons and channel boundary",
            {
                "Cells": gis_cells,
                "Boundary vertices": gis_boundary_vertices,
                "CRS": metrics.get("gis_crs", ""),
            },
        ),
        _workflow_step(
            "hydraulics",
            "3 Hydraulics",
            "passed" if time_series_rows else "warning",
            "flow time series and depth/velocity lookups",
            {
                "Time-series rows": time_series_rows,
                "Depth flows": metrics.get("depth_flow_count", 0),
                "Velocity flows": metrics.get("velocity_flow_count", 0),
                "Flow range": (
                    f"{metrics.get('min_flow_m3s')} - {metrics.get('max_flow_m3s')} m3/s"
                    if metrics.get("min_flow_m3s") is not None
                    and metrics.get("max_flow_m3s") is not None
                    else "-"
                ),
            },
        ),
        _workflow_step(
            "population",
            "4 Population",
            "passed" if initial_fish + adult_arrival_fish > 0 else "warning",
            "initial fish plus scheduled adult arrivals",
            {
                "Initial fish": initial_fish,
                "Adult arrivals": adult_arrival_fish,
                "Species": ", ".join(cast(list[str], metrics.get("species", []))) or "-",
            },
        ),
        _workflow_step(
            "run",
            "5 Run",
            "passed" if population_rows else "warning",
            f"native IBM executed for {days} day(s)",
            {
                "Population rows": population_rows,
                "Inventory rows": metrics.get("inventory_rows", 0),
                "Events": sum(cast(dict[str, int], metrics.get("event_counts", {})).values()),
            },
        ),
        _workflow_step(
            "validation",
            "6 Acceptance",
            "passed" if population_rows and final_abundance >= 0 else "warning",
            "official fixture converted and captured",
            {
                "Final abundance": final_abundance,
                "Run directory": str(run_dir),
                "GIS source": metrics.get("gis_source", ""),
            },
        ),
    ]
    if any(step["status"] != "passed" for step in steps):
        status = "warning"
    return {"status": status, "steps": steps}


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # pragma: no cover - defensive JSON fallback
            pass
    return str(value)


def _run_dir(output_dir: str | Path, prefix: str) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _write_studio_scenario_files(
    run_root: Path,
    *,
    scenario_id: str,
    reach_id: str,
    species: str,
    days: int,
    seed: int,
    stochastic: bool,
    record_history: bool,
    initial_abundance: int,
    initial_length_mm: float,
    profile: SpeciesProfile,
    cells: pd.DataFrame,
    submodels: Mapping[str, str],
    experiments: Mapping[str, object] | None,
    payload: Mapping[str, object],
) -> dict[str, str]:
    run_root.mkdir(parents=True, exist_ok=True)
    cells_path = run_root / "studio_habitat_cells.csv"
    profile_path = run_root / "studio_profile.yaml"
    scenario_path = run_root / "studio_scenario.json"
    payload_path = run_root / "studio_payload.json"
    cells.to_csv(cells_path, index=False)
    write_species_profile(profile, profile_path)
    scenario_doc: dict[str, object] = {
        "ibm_version": IBM_SCHEMA_VERSION,
        "scenario": {
            "id": scenario_id,
            "reach_id": reach_id,
            "days": days,
            "seed": seed,
            "stochastic": stochastic,
        },
        "profile": {"uri": profile_path.name},
        "forcing": {"habitat_cells": cells_path.name},
        "population": {
            "default_species": species,
            "initial_abundance": initial_abundance,
            "initial_length_mm": initial_length_mm,
        },
        "outputs": {
            "dir": ".",
            "individual_history": record_history,
            "manifest": True,
        },
    }
    if submodels:
        scenario_doc["submodels"] = dict(submodels)
    if experiments:
        scenario_doc["experiments"] = dict(experiments)
    scenario_path.write_text(
        json.dumps(scenario_doc, indent=2, default=_json_default),
        encoding="utf-8",
    )
    payload_path.write_text(
        json.dumps(payload, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return {
        "studio_scenario": str(scenario_path),
        "studio_profile": str(profile_path),
        "studio_habitat_cells": str(cells_path),
        "studio_payload": str(payload_path),
    }


def write_studio_scenario_files(
    payload: Mapping[str, object] | None,
    output_dir: str | Path,
) -> dict[str, str]:
    """Write a Studio payload as standard IBM scenario/profile/input files."""

    default = default_studio_scenario()
    payload = payload or {}
    config = _merged(cast(Mapping[str, object], default["config"]), payload.get("config"))
    species = _as_str(config.get("species"), "rainbow_trout")
    profile = _profile_from_payload(payload.get("profile", default["profile"]), species=species)
    submodels = _normalise_submodels(payload.get("submodels", default["submodels"]))
    experiments = _scenario_experiments_from_payload(
        payload.get("experiments", default["experiments"]),
        default_seed=_as_int(config.get("seed"), 42),
    )
    return _write_studio_scenario_files(
        Path(output_dir),
        scenario_id=_as_str(config.get("scenario_id"), "agent-studio-demo"),
        reach_id=_as_str(config.get("reach_id"), "reach-1"),
        species=species,
        days=_as_int(config.get("days"), 45, min_value=0),
        seed=_as_int(config.get("seed"), 42),
        stochastic=_as_bool(config.get("stochastic"), True),
        record_history=_as_bool(config.get("record_individual_history"), True),
        initial_abundance=_as_int(config.get("initial_abundance"), 80, min_value=0),
        initial_length_mm=_as_float(config.get("initial_length_mm"), 115.0, min_value=1.0),
        profile=profile,
        cells=_cells_from_payload(payload.get("cells", default["cells"])),
        submodels=submodels,
        experiments=experiments,
        payload=payload,
    )


def _cell_use_summary(cell_use: pd.DataFrame) -> pd.DataFrame:
    if cell_use.empty:
        return pd.DataFrame(
            columns=[
                "reach_id",
                "cell_id",
                "total_fish_use",
                "mean_growth_mm",
                "mean_mortality_risk",
            ]
        )
    return (
        cell_use.groupby(["reach_id", "cell_id"], as_index=False)
        .agg(
            total_fish_use=("n_fish", "sum"),
            mean_growth_mm=("mean_growth_mm", "mean"),
            mean_mortality_risk=("mean_mortality_risk", "mean"),
        )
        .sort_values("total_fish_use", ascending=False, kind="mergesort")
        .reset_index(drop=True)
    )


def _river_from_payload(value: object) -> dict[str, object]:
    values = _merged(_demo_river(), value)
    river: dict[str, object] = {
        "name": _as_str(values.get("name"), "Lemhi River"),
        "reach_name": _as_str(values.get("reach_name"), "Hayden Creek demo reach"),
        "length_m": _as_float(values.get("length_m"), 380.0, min_value=1.0),
        "flow_m3s": _as_float(values.get("flow_m3s"), 5.8, min_value=0.0),
        "display_note": _as_str(values.get("display_note"), ""),
    }
    geometry = _normalise_river_geometry(values.get("geometry"))
    if geometry:
        river["geometry"] = geometry
    return river


def _visual_cell_rows(
    cells: pd.DataFrame,
    cell_summary: pd.DataFrame,
    river: Mapping[str, object],
) -> tuple[list[dict[str, object]], dict[str, float]]:
    summary_by_cell = {str(row.get("cell_id", "")): row for row in _records(cell_summary)}
    geometry = river.get("geometry") if isinstance(river.get("geometry"), Mapping) else {}
    centerline = (
        _point_sequence(cast(Mapping[str, object], geometry).get("centerline_m"))
        if isinstance(geometry, Mapping)
        else []
    )
    channel_polygon = (
        _point_sequence(cast(Mapping[str, object], geometry).get("channel_polygon_m"))
        if isinstance(geometry, Mapping)
        else []
    )
    visual_cells: list[dict[str, object]] = []
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    def include_points(points: list[list[float]]) -> None:
        nonlocal min_x, min_y, max_x, max_y
        for x, y in points:
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

    include_points(centerline)
    include_points(channel_polygon)

    running_station = 0.0
    for index, row in enumerate(_records(cells)):
        area = _as_float(row.get("area_m2"), 100.0, min_value=0.0)
        length = _as_float(row.get("length_m"), 0.0, min_value=0.0)
        if length <= 0.0:
            length = max(18.0, min(72.0, area / 12.0 if area > 0.0 else 38.0))
        width = _as_float(row.get("width_m"), 0.0, min_value=0.0)
        if width <= 0.0:
            width = max(5.0, min(24.0, area / max(length, 1.0)))
        station = _as_float(row.get("station_m"), running_station + length / 2.0)
        running_station = max(running_station, station + length / 2.0)
        summary = summary_by_cell.get(str(row.get("cell_id", "")), {})
        sample_x, sample_y, axis_x, axis_y, normal_x, normal_y = _sample_line(centerline, station)
        fallback_y = 52.0 + float((index % 4) - 1.5) * 12.0
        has_center = row.get("center_x_m") not in (None, "") and row.get("center_y_m") not in (None, "")
        if has_center:
            center_x = _as_float(row.get("center_x_m"), station)
            center_y = _as_float(row.get("center_y_m"), fallback_y)
        elif centerline:
            lateral_offset = _as_float(row.get("lateral_offset_m"), 0.0)
            center_x = sample_x + normal_x * lateral_offset
            center_y = sample_y + normal_y * lateral_offset
        else:
            center_x = _as_float(row.get("center_x_m"), station)
            center_y = _as_float(row.get("center_y_m"), fallback_y)
            axis_x, axis_y, normal_x, normal_y = 1.0, 0.0, 0.0, 1.0

        polygon = _point_sequence(row.get("polygon_m"))
        if len(polygon) < 3:
            polygon = _oriented_cell_polygon(
                center_x=center_x,
                center_y=center_y,
                length_m=length,
                width_m=width,
                axis_x=axis_x,
                axis_y=axis_y,
                normal_x=normal_x,
                normal_y=normal_y,
            )
        include_points(polygon)
        visual_cells.append(
            {
                "cell_id": str(row.get("cell_id", index)),
                "reach_id": str(row.get("reach_id", "")),
                "habitat_type": str(row.get("habitat_type", "cell")),
                "station_m": station,
                "center_x_m": center_x,
                "center_y_m": center_y,
                "length_m": length,
                "width_m": width,
                "polygon_m": polygon,
                "axis_x": axis_x,
                "axis_y": axis_y,
                "normal_x": normal_x,
                "normal_y": normal_y,
                "area_m2": area,
                "depth_m": _as_float(row.get("depth_m"), 0.0, min_value=0.0),
                "velocity_ms": _as_float(row.get("velocity_ms"), 0.0, min_value=0.0),
                "csi": _as_float(row.get("csi"), 0.0, min_value=0.0),
                "hiding_cover": _as_float(row.get("hiding_cover"), 0.0, min_value=0.0),
                "feeding_cover": _as_float(row.get("feeding_cover"), 0.0, min_value=0.0),
                "spawning_cover": _as_float(row.get("spawning_cover"), 0.0, min_value=0.0),
                "total_fish_use": _as_int(summary.get("total_fish_use"), 0, min_value=0),
                "mean_growth_mm": _as_float(summary.get("mean_growth_mm"), 0.0),
                "mean_mortality_risk": _as_float(
                    summary.get("mean_mortality_risk"),
                    0.0,
                    min_value=0.0,
                ),
            }
        )
    has_bounds = math.isfinite(min_x) and math.isfinite(min_y) and math.isfinite(max_x) and math.isfinite(max_y)
    if not visual_cells and not has_bounds:
        return [], {"min_x": 0.0, "max_x": 1.0, "min_y": 0.0, "max_y": 1.0}
    padding = max(max(max_x - min_x, max_y - min_y) * 0.04, 12.0)
    return visual_cells, {
        "min_x": min_x - padding,
        "max_x": max_x + padding,
        "min_y": min_y - padding,
        "max_y": max_y + padding,
    }


def _stable_unit(value: int, salt: int) -> float:
    mixed = (value * 1103515245 + salt * 12345 + 0x9E3779B9) & 0xFFFFFFFF
    return mixed / 0xFFFFFFFF


def _visual_fish_rows(
    final_individuals: pd.DataFrame,
    visual_cells: list[dict[str, object]],
) -> list[dict[str, object]]:
    cells_by_id = {str(cell["cell_id"]): cell for cell in visual_cells}
    fish_rows: list[dict[str, object]] = []
    for index, row in enumerate(_records(final_individuals, limit=500)):
        cell = cells_by_id.get(str(row.get("cell_id", "")))
        if cell is None:
            continue
        fish_id = _as_int(row.get("fish_id"), index)
        length = _as_float(row.get("length_mm"), 0.0, min_value=0.0)
        alive_value = row.get("alive", True)
        alive = bool(alive_value) if alive_value is not None else False
        center_x = _as_float(cell.get("center_x_m"), 0.0)
        center_y = _as_float(cell.get("center_y_m"), 0.0)
        cell_length = _as_float(cell.get("length_m"), 10.0, min_value=1.0)
        cell_width = _as_float(cell.get("width_m"), 4.0, min_value=1.0)
        axis_x = _as_float(cell.get("axis_x"), 1.0)
        axis_y = _as_float(cell.get("axis_y"), 0.0)
        normal_x = _as_float(cell.get("normal_x"), 0.0)
        normal_y = _as_float(cell.get("normal_y"), 1.0)
        longitudinal = (_stable_unit(fish_id, 17) - 0.5) * cell_length * 0.72
        lateral = (_stable_unit(fish_id, 43) - 0.5) * cell_width * 0.70
        x = center_x + axis_x * longitudinal + normal_x * lateral
        y = center_y + axis_y * longitudinal + normal_y * lateral
        fish_rows.append(
            {
                "fish_id": fish_id,
                "species": _as_str(row.get("species"), "fish"),
                "cell_id": str(row.get("cell_id", "")),
                "reach_id": str(row.get("reach_id", "")),
                "x_m": x,
                "y_m": y,
                "length_mm": length,
                "mass_g": _as_float(row.get("mass_g"), 0.0, min_value=0.0),
                "alive": alive,
                "display_size": max(2.4, min(7.0, 2.4 + length / 55.0)),
            }
        )
    return fish_rows


def _visual_redd_rows(
    redds: pd.DataFrame,
    visual_cells: list[dict[str, object]],
) -> list[dict[str, object]]:
    if redds.empty:
        return []
    latest = redds.copy()
    if "redd_id" in latest:
        sort_columns = ["redd_id"]
        if "day" in latest:
            sort_columns.append("day")
        elif "age_days" in latest:
            sort_columns.append("age_days")
        latest = latest.sort_values(sort_columns, kind="mergesort")
        latest = latest.drop_duplicates("redd_id", keep="last")
    cells_by_id = {str(cell["cell_id"]): cell for cell in visual_cells}
    rows: list[dict[str, object]] = []
    for index, row in enumerate(_records(latest, limit=200)):
        cell = cells_by_id.get(str(row.get("cell_id", "")))
        if cell is None:
            continue
        redd_id = _as_int(row.get("redd_id"), index)
        eggs = _as_int(row.get("eggs_remaining"), 0, min_value=0)
        center_x = _as_float(cell.get("center_x_m"), 0.0)
        center_y = _as_float(cell.get("center_y_m"), 0.0)
        cell_length = _as_float(cell.get("length_m"), 10.0, min_value=1.0)
        cell_width = _as_float(cell.get("width_m"), 4.0, min_value=1.0)
        axis_x = _as_float(cell.get("axis_x"), 1.0)
        axis_y = _as_float(cell.get("axis_y"), 0.0)
        normal_x = _as_float(cell.get("normal_x"), 0.0)
        normal_y = _as_float(cell.get("normal_y"), 1.0)
        longitudinal = (_stable_unit(redd_id, 71) - 0.5) * cell_length * 0.42
        lateral = (_stable_unit(redd_id, 97) - 0.5) * cell_width * 0.42
        rows.append(
            {
                "redd_id": redd_id,
                "cell_id": str(row.get("cell_id", "")),
                "reach_id": str(row.get("reach_id", "")),
                "x_m": center_x + axis_x * longitudinal + normal_x * lateral,
                "y_m": center_y + axis_y * longitudinal + normal_y * lateral,
                "eggs_remaining": eggs,
                "active": _as_bool(row.get("alive"), True)
                and not _as_bool(row.get("emerged"), False),
                "display_size": max(4.0, min(12.0, 4.0 + eggs / 80.0)),
            }
        )
    return rows


def _build_river_view(
    river: Mapping[str, object],
    cells: pd.DataFrame,
    cell_summary: pd.DataFrame,
    final_individuals: pd.DataFrame,
    redds: pd.DataFrame,
) -> dict[str, object]:
    visual_cells, bounds = _visual_cell_rows(cells, cell_summary, river)
    fish_rows = _visual_fish_rows(final_individuals, visual_cells)
    redd_rows = _visual_redd_rows(redds, visual_cells)
    geometry = river.get("geometry")
    return {
        "river": dict(river),
        "geometry": dict(cast(Mapping[str, object], geometry)) if isinstance(geometry, Mapping) else {},
        "bounds": bounds,
        "cells": visual_cells,
        "fish": fish_rows,
        "redds": redd_rows,
        "fish_display_limit": 500,
    }


def _field_lookup(columns: object, name: str) -> str | None:
    lookup = {str(column).lower(): str(column) for column in columns}
    return lookup.get(name.lower())


def _official_display_crs(gdfs: list[Any]) -> object | None:
    for gdf in gdfs:
        try:
            estimated = gdf.estimate_utm_crs()
        except Exception:
            estimated = None
        if estimated is not None:
            return estimated
    return _choose_metric_crs(gdfs)


def _official_case_river_view(
    root: str | Path,
    *,
    case_id: str,
    result: object,
) -> dict[str, object] | None:
    try:
        import geopandas as gpd
        from shapely.ops import unary_union
    except Exception:
        return None

    case = next((item for item in discover_instream7_cases(root) if item.case_id == case_id), None)
    if case is None:
        return None

    raw_by_path: dict[Path, Any] = {}
    for reach in case.reaches:
        if reach.shapefile not in raw_by_path:
            raw_by_path[reach.shapefile] = gpd.read_file(reach.shapefile)
    raw_gdfs = [gdf for gdf in raw_by_path.values() if len(gdf) > 0 and not gdf.empty]
    if not raw_gdfs:
        return None
    target_crs = _official_display_crs(raw_gdfs)
    metric_by_path = {path: _to_common_metric(gdf, target_crs) for path, gdf in raw_by_path.items()}
    bounds = [gdf.total_bounds for gdf in metric_by_path.values() if len(gdf) > 0 and not gdf.empty]
    if not bounds:
        return None
    origin_x = min(float(bound[0]) for bound in bounds)
    origin_y = min(float(bound[1]) for bound in bounds)
    translated_by_path = {
        path: _translated_geometries(gdf, origin_x=origin_x, origin_y=origin_y)
        for path, gdf in metric_by_path.items()
    }

    cells: list[dict[str, object]] = []
    polygons: list[Any] = []
    for reach_order, reach in enumerate(case.reaches, start=1):
        gdf = translated_by_path[reach.shapefile]
        cell_col = _field_lookup(gdf.columns, reach.cell_id_field)
        reach_col = _field_lookup(gdf.columns, reach.reach_field)
        area_col = _field_lookup(gdf.columns, reach.area_field)
        shelter_col = _field_lookup(gdf.columns, reach.velocity_shelter_field)
        hiding_col = _field_lookup(gdf.columns, reach.hiding_places_field)
        spawn_col = _field_lookup(gdf.columns, reach.spawning_fraction_field)
        if cell_col is None:
            continue
        sub = (
            gdf[gdf[reach_col].astype(str) == reach.reach_id].copy()
            if reach_col is not None
            else gdf.copy()
        )
        for _index, row in sub.iterrows():
            for polygon in _geometry_parts(row.geometry, {"Polygon"}):
                if polygon is None or polygon.is_empty:
                    continue
                polygons.append(polygon)
                point = polygon.representative_point()
                length_m, width_m = _rotated_rectangle_size(polygon)
                area_m2 = max(float(polygon.area), 0.0)
                official_area = (
                    _row_float(row, (area_col,), area_m2)
                    if area_col is not None
                    else area_m2
                )
                shelter = (
                    max(0.0, min(1.0, _row_float(row, (shelter_col,), 0.0)))
                    if shelter_col is not None
                    else 0.0
                )
                hiding_places = (
                    max(0.0, _row_float(row, (hiding_col,), 0.0))
                    if hiding_col is not None
                    else 0.0
                )
                spawning = (
                    max(0.0, min(1.0, _row_float(row, (spawn_col,), 0.0)))
                    if spawn_col is not None
                    else 0.0
                )
                cell_id = str(row[cell_col])
                cells.append(
                    {
                        "cell_id": cell_id,
                        "reach_id": reach.reach_id,
                        "reach_order": reach_order,
                        "habitat_type": "official-cell",
                        "station_m": float(point.x),
                        "center_x_m": float(point.x),
                        "center_y_m": float(point.y),
                        "length_m": length_m,
                        "width_m": width_m,
                        "polygon_m": _coords_from_polygon(polygon),
                        "area_m2": official_area if official_area > 0.0 else area_m2,
                        "depth_m": 0.0,
                        "velocity_ms": 0.0,
                        "csi": max(spawning, shelter, min(1.0, hiding_places / 10.0), 0.15),
                        "temperature_c": 12.0,
                        "turbidity_ntu": 0.0,
                        "hiding_cover": max(shelter, min(1.0, hiding_places / 10.0)),
                        "feeding_cover": shelter,
                        "spawning_cover": spawning,
                    }
                )

    if not cells or not polygons:
        return None
    try:
        union = unary_union(polygons)
        union_polygons = _geometry_parts(union, {"Polygon"})
    except Exception:
        union_polygons = polygons
    boundary = max(union_polygons, key=lambda geom: float(geom.area)) if union_polygons else None
    messages: list[str] = []
    geometry: dict[str, object] = {
        "crs": str(target_crs) if target_crs is not None else "source",
        "source": f"official {case_id} shapefile",
        "provenance": str(next(iter(raw_by_path))),
        "boundary_quality": _boundary_quality(boundary, messages),
    }
    if boundary is not None:
        geometry["channel_polygon_m"] = _coords_from_polygon(boundary)

    cell_summary = _cell_use_summary(cast(Any, result).cell_use)
    river: dict[str, object] = {
        "name": f"Official {case_id}",
        "reach_name": " / ".join(reach.reach_id for reach in case.reaches),
        "length_m": max((float(cell["center_x_m"]) for cell in cells), default=1.0),
        "flow_m3s": 0.0,
        "display_note": "Official GIS shapefile geometry from the inSTREAM/InSALMO fixture.",
        "geometry": geometry,
    }
    return _build_river_view(
        river,
        pd.DataFrame.from_records(cells),
        cell_summary,
        cast(Any, result).final_individuals,
        cast(Any, result).redds,
    )


def run_studio_scenario(
    payload: Mapping[str, object] | None,
    output_dir: str | Path,
) -> dict[str, object]:
    """Run one browser-studio native IBM scenario and return JSON-safe tables."""

    default = default_studio_scenario()
    payload = payload or {}
    config = _merged(cast(Mapping[str, object], default["config"]), payload.get("config"))
    species = _as_str(config.get("species"), "rainbow_trout")
    reach_id = _as_str(config.get("reach_id"), "reach-1")
    days = _as_int(config.get("days"), 45, min_value=0)
    seed = _as_int(config.get("seed"), 42)
    initial_abundance = _as_int(config.get("initial_abundance"), 80, min_value=0)
    initial_length_mm = _as_float(config.get("initial_length_mm"), 115.0, min_value=1.0)
    scenario_id = _as_str(config.get("scenario_id"), "agent-studio-demo")
    stochastic = _as_bool(config.get("stochastic"), True)
    record_history = _as_bool(config.get("record_individual_history"), True)

    river = _river_from_payload(payload.get("river", default.get("river")))
    cells = _cells_from_payload(payload.get("cells", default["cells"]))
    profile = _profile_from_payload(payload.get("profile", default["profile"]), species=species)
    submodels = _normalise_submodels(payload.get("submodels", default["submodels"]))
    experiments = _scenario_experiments_from_payload(
        payload.get("experiments", default["experiments"]),
        default_seed=seed,
    )

    run_root = _run_dir(output_dir, "native")
    studio_paths = _write_studio_scenario_files(
        run_root,
        scenario_id=scenario_id,
        reach_id=reach_id,
        species=species,
        days=days,
        seed=seed,
        stochastic=stochastic,
        record_history=record_history,
        initial_abundance=initial_abundance,
        initial_length_mm=initial_length_mm,
        profile=profile,
        cells=cells,
        submodels=submodels,
        experiments=experiments,
        payload=payload,
    )

    result, paths = run_ibm_scenario(
        studio_paths["studio_scenario"],
        output_dir_override=run_root,
        run_label="studio",
    )
    paths.update(studio_paths)
    final = result.population_summary.iloc[-1]
    cell_summary = _cell_use_summary(result.cell_use)
    events = (
        result.events.sort_values(["day", "event"], kind="mergesort")
        if not result.events.empty
        else result.events
    )
    redds = (
        result.redds.sort_values(["day", "redd_id"], kind="mergesort")
        if not result.redds.empty
        else result.redds
    )

    return {
        "ok": True,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": paths,
        "metrics": {
            "initial_abundance": initial_abundance,
            "final_abundance": int(final["abundance"]),
            "final_biomass_g": float(final["biomass_g"]),
            "final_mean_length_mm": float(final["mean_length_mm"]),
            "survival_rate": float(final["survival_rate"]),
            "event_count": int(result.events["n"].sum()) if not result.events.empty else 0,
            "redd_count": int(len(result.redds)),
            "history_rows": int(len(result.individual_history)),
        },
        "population_summary": _records(result.population_summary),
        "cell_use_summary": _records(cell_summary),
        "river_view": _build_river_view(
            river,
            cells,
            cell_summary,
            result.final_individuals,
            redds,
        ),
        "cell_use": _records(result.cell_use, limit=800),
        "events": _records(events, limit=500),
        "final_individuals": _records(result.final_individuals, limit=500),
        "redds": _records(redds, limit=500),
        "individual_history_sample": _records(result.individual_history, limit=500),
        "input_cells": _records(cells),
    }


def _check(area: str, status: str, message: str, detail: str = "") -> dict[str, str]:
    return {"area": area, "status": status, "message": message, "detail": detail}


def _numeric_series(table: pd.DataFrame, column: str) -> pd.Series:
    if column not in table:
        return pd.Series(dtype="float64")
    return pd.to_numeric(table[column], errors="coerce")


def validate_studio_payload(
    payload: Mapping[str, object] | None,
    output_dir: str | Path,
) -> dict[str, object]:
    """Validate Studio scenario/profile/cell inputs without running a simulation."""

    checks: list[dict[str, str]] = []
    run_root = _run_dir(output_dir, "validate")
    try:
        paths = write_studio_scenario_files(payload, run_root)
    except Exception as exc:
        checks.append(_check("contract", "error", f"{type(exc).__name__}: {exc}"))
        return {
            "ok": False,
            "run_id": run_root.name,
            "run_dir": str(run_root),
            "paths": {},
            "checks": checks,
            "metrics": {"errors": 1, "warnings": 0, "passes": 0},
        }

    scenario_errors = validate_ibm_scenario(paths["studio_scenario"])
    if scenario_errors:
        checks.extend(_check("scenario", "error", err) for err in scenario_errors)
    else:
        checks.append(_check("scenario", "pass", "Scenario schema and submodel selection are valid"))

    profile_errors = validate_species_profile(paths["studio_profile"])
    if profile_errors:
        checks.extend(_check("profile", "error", err) for err in profile_errors)
    else:
        checks.append(_check("profile", "pass", "Species profile schema is valid"))

    default = default_studio_scenario()
    payload = payload or {}
    cells = _cells_from_payload(payload.get("cells", default["cells"]))
    required_cell_columns = {
        "cell_id",
        "reach_id",
        "area_m2",
        "depth_m",
        "velocity_ms",
        "csi",
        "temperature_c",
    }
    missing = sorted(required_cell_columns - set(cells.columns))
    if missing:
        checks.append(_check("habitat", "error", "Missing habitat cell columns", ", ".join(missing)))
    else:
        checks.append(_check("habitat", "pass", f"{len(cells)} habitat cells have required columns"))
    if "cell_id" in cells:
        duplicate_ids = cells["cell_id"][cells["cell_id"].duplicated()].astype(str).unique().tolist()
        if duplicate_ids:
            checks.append(_check("habitat", "error", "Duplicate cell IDs", ", ".join(duplicate_ids)))
    for column in ("area_m2", "depth_m", "velocity_ms", "temperature_c"):
        values = _numeric_series(cells, column)
        if not values.empty and bool(values.isna().any()):
            checks.append(_check("habitat", "error", f"{column} contains non-numeric values"))
    if bool((_numeric_series(cells, "area_m2") <= 0).any()):
        checks.append(_check("habitat", "error", "area_m2 must be positive"))
    for column in ("depth_m", "velocity_ms"):
        if bool((_numeric_series(cells, column) < 0).any()):
            checks.append(_check("habitat", "error", f"{column} must be non-negative"))
    csi = _numeric_series(cells, "csi")
    if not csi.empty and bool(((csi < 0) | (csi > 1)).any()):
        checks.append(_check("habitat", "warning", "CSI values outside 0..1 will distort utility colors"))

    config = _merged(cast(Mapping[str, object], default["config"]), payload.get("config"))
    if _as_int(config.get("days"), 0, min_value=0) == 0:
        checks.append(_check("run", "warning", "Scenario has zero simulated days"))
    if _as_int(config.get("initial_abundance"), 0, min_value=0) == 0:
        checks.append(_check("population", "warning", "Initial abundance is zero"))

    species = _as_str(config.get("species"), "rainbow_trout")
    profile = _profile_from_payload(payload.get("profile", default["profile"]), species=species)
    if not profile.thermal_min_c < profile.thermal_optimum_c < profile.thermal_max_c:
        checks.append(_check("profile", "error", "Thermal min/optimum/max must be increasing"))
    for name in ("base_daily_survival", "egg_to_fry_survival", "redd_base_daily_survival"):
        value = float(getattr(profile, name))
        if not 0.0 <= value <= 1.0:
            checks.append(_check("profile", "error", f"{name} must be within 0..1"))

    raw_submodels = _normalise_submodels(payload.get("submodels", default["submodels"]))
    submodel_errors = validate_submodel_selection(raw_submodels)
    if submodel_errors:
        checks.extend(_check("submodels", "error", err) for err in submodel_errors)
    else:
        checks.append(_check("submodels", "pass", "Submodel choices are registered"))

    errors = sum(1 for item in checks if item["status"] == "error")
    warnings = sum(1 for item in checks if item["status"] == "warning")
    passes = sum(1 for item in checks if item["status"] == "pass")
    return {
        "ok": errors == 0,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": paths,
        "checks": checks,
        "metrics": {"errors": errors, "warnings": warnings, "passes": passes},
    }


def run_studio_ensemble(
    payload: Mapping[str, object] | None,
    output_dir: str | Path,
) -> dict[str, object]:
    """Run the Studio scenario as a multi-seed/parameter ensemble."""

    default = default_studio_scenario()
    payload = payload or {}
    config = _merged(cast(Mapping[str, object], default["config"]), payload.get("config"))
    seed = _as_int(config.get("seed"), 42)
    experiments = _studio_experiments(payload.get("experiments", default["experiments"]))
    ensemble = cast(Mapping[str, object], experiments["ensemble"])
    seeds = _int_list(ensemble.get("seeds"), (seed, seed + 1, seed + 2))

    run_root = _run_dir(output_dir, "ensemble")
    studio_paths = write_studio_scenario_files(payload, run_root / "scenario")
    result = run_ibm_ensemble(
        studio_paths["studio_scenario"],
        seeds=seeds,
        output_dir=run_root / "runs",
    )
    paths = dict(result.paths)
    paths.update(studio_paths)
    final_mean = (
        float(result.summary["final_abundance"].mean()) if not result.summary.empty else 0.0
    )
    return {
        "ok": True,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": paths,
        "metrics": {
            "n_runs": int(len(result.summary)),
            "n_seeds": int(len(seeds)),
            "mean_final_abundance": final_mean,
        },
        "summary": _records(result.summary, limit=500),
        "daily_bands": _records(result.daily_bands),
        "sensitivity": _records(result.sensitivity),
    }


def _write_observed_from_scenario(scenario_path: str, output_dir: Path) -> tuple[str, dict[str, str]]:
    result, paths = run_ibm_scenario(
        scenario_path,
        output_dir_override=output_dir / "observed_source",
        run_label="observed_source",
    )
    summary = result.population_summary.copy()
    observed = summary.groupby("day", as_index=False).agg(
        abundance=("abundance", "sum"),
        biomass_g=("biomass_g", "sum"),
    )
    observed_path = output_dir / "observed_abundance.csv"
    observed.to_csv(observed_path, index=False)
    paths["studio_observed_abundance"] = str(observed_path)
    return str(observed_path), paths


def _rewrite_calibration_block(
    scenario_path: str,
    payload: Mapping[str, object],
    *,
    observed_path: str,
    default_seed: int,
) -> None:
    path = Path(scenario_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    experiments = _scenario_experiments_from_payload(
        payload.get("experiments"),
        default_seed=default_seed,
        calibration_observed=observed_path,
    )
    data["experiments"] = experiments
    path.write_text(json.dumps(data, indent=2, default=_json_default), encoding="utf-8")


def run_studio_calibration(
    payload: Mapping[str, object] | None,
    output_dir: str | Path,
) -> dict[str, object]:
    """Run grid or ABC calibration from the browser Studio payload."""

    default = default_studio_scenario()
    payload = payload or {}
    config = _merged(cast(Mapping[str, object], default["config"]), payload.get("config"))
    seed = _as_int(config.get("seed"), 42)
    experiments = _studio_experiments(payload.get("experiments", default["experiments"]))
    calibration = cast(Mapping[str, object], experiments["calibration"])
    method = _as_str(calibration.get("method"), "grid")
    if method not in {"grid", "abc"}:
        raise ValueError("calibration method must be grid or abc")
    grid = _parameter_grid_from_payload(
        calibration.get("parameter_specs") or calibration.get("parameters")
    )
    if not grid:
        raise ValueError("calibration requires at least one parameter spec")
    samples = _as_int(calibration.get("samples"), 8, min_value=1)
    acceptance_fraction = min(
        1.0,
        _as_float(calibration.get("acceptance_fraction"), 0.25, min_value=0.000001),
    )
    tolerance_raw = calibration.get("tolerance")
    tolerance = (
        None
        if tolerance_raw in (None, "")
        else _as_float(tolerance_raw, 0.0, min_value=0.0)
    )

    run_root = _run_dir(output_dir, "calibrate")
    studio_paths = write_studio_scenario_files(payload, run_root / "scenario")
    observed = _as_str(calibration.get("observed"), "")
    observed_paths: dict[str, str] = {}
    if observed:
        observed_path = str(Path(observed).expanduser())
        if not Path(observed_path).exists():
            raise ValueError("observed calibration CSV does not exist")
    else:
        observed_path, observed_paths = _write_observed_from_scenario(
            studio_paths["studio_scenario"],
            run_root,
        )
    _rewrite_calibration_block(
        studio_paths["studio_scenario"],
        payload,
        observed_path=observed_path,
        default_seed=seed,
    )
    result = run_ibm_calibration(
        studio_paths["studio_scenario"],
        observed_path=observed_path,
        parameter_grid=grid,
        output_dir=run_root / "runs",
        method=method,
        samples=samples,
        acceptance_fraction=acceptance_fraction,
        tolerance=tolerance,
    )
    paths = dict(result.paths)
    paths.update(studio_paths)
    paths.update(observed_paths)
    best_score = float(result.summary.iloc[0]["score"]) if not result.summary.empty else 0.0
    accepted = (
        int(pd.to_numeric(result.summary["accepted"], errors="coerce").fillna(0).sum())
        if "accepted" in result.summary
        else 0
    )
    return {
        "ok": True,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": paths,
        "metrics": {
            "method": method,
            "n_candidates": int(len(result.summary)),
            "n_accepted": accepted,
            "best_score": best_score,
        },
        "best_parameters": result.best_parameters,
        "summary": _records(result.summary, limit=500),
    }


def run_instream7_benchmark_for_studio(
    payload: Mapping[str, object] | None,
    output_dir: str | Path,
) -> dict[str, object]:
    """Run official inSTREAM 7 native benchmark from the browser UI."""

    default = default_studio_scenario()
    payload = payload or {}
    values = _merged(cast(Mapping[str, object], default["instream"]), payload)
    fixture = _as_str(values.get("fixture"), "")
    if not fixture:
        raise ValueError("fixture is required")
    case_id = _as_str(values.get("case_id"), "ExampleA")
    days = _as_int(values.get("days"), 2, min_value=1)
    seed = _as_int(values.get("seed"), 11)
    stochastic = _as_bool(values.get("stochastic"), True)

    run_root = _run_dir(output_dir, "instream7")
    source = Path(fixture)
    if source.suffix.lower() == ".zip":
        root = extract_instream7_archive(source, run_root / "_official_instream7")
    else:
        root = source
    result = run_instream7_official_benchmark(
        root,
        run_root,
        case_ids=(case_id,),
        days=days,
        seed=seed,
        stochastic=stochastic,
    )
    final = result.population_summary.groupby(
        ["scenario_id", "reach_id", "species"], as_index=False
    ).tail(1)
    initial_fish = int(_sum_numeric(result.inventory, "n_initial_fish"))
    adult_arrival_fish = int(_sum_numeric(result.inventory, "n_adult_arrival_fish"))
    events = result.events.copy()
    event_counts = (
        {
            str(key): int(value)
            for key, value in events.groupby(events["event"].astype(str))["n"].sum().items()
        }
        if not events.empty and "event" in events and "n" in events
        else {}
    )
    river_view = _official_case_river_view(root, case_id=case_id, result=result)
    species = sorted(
        {
            item
            for joined in result.inventory.get("species", pd.Series(dtype=str)).astype(str)
            for item in joined.split("|")
            if item
        }
    )
    metrics: dict[str, object] = {
        "suite": "InSALMO" if adult_arrival_fish else "inSTREAM",
        "case_count": int(result.inventory["case_id"].nunique())
        if "case_id" in result.inventory
        else 0,
        "reach_count": int(result.inventory["reach_id"].nunique())
        if "reach_id" in result.inventory
        else 0,
        "species_count": len(species),
        "species": species,
        "inventory_rows": int(len(result.inventory)),
        "population_rows": int(len(result.population_summary)),
        "final_abundance": int(_sum_numeric(final, "abundance")),
        "initial_fish": initial_fish,
        "adult_arrival_fish": adult_arrival_fish,
        "official_cells": int(_sum_numeric(result.inventory, "n_cells")),
        "time_series_rows": int(_sum_numeric(result.inventory, "n_time_series_rows")),
        "depth_flow_count": int(_sum_numeric(result.inventory, "n_depth_flows")),
        "velocity_flow_count": int(_sum_numeric(result.inventory, "n_velocity_flows")),
        "min_flow_m3s": _min_numeric(result.inventory, "min_flow_m3s"),
        "max_flow_m3s": _max_numeric(result.inventory, "max_flow_m3s"),
        "event_counts": event_counts,
    }
    metrics.update(_official_gis_metrics(river_view))
    return {
        "ok": True,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": result.paths,
        "metrics": metrics,
        "workflow": _official_workflow(metrics, case_id=case_id, days=days, run_dir=run_root),
        "inventory": _records(result.inventory),
        "population_summary": _records(result.population_summary),
        "final_population": _records(final),
        "cell_use": _records(result.cell_use, limit=800),
        "final_individuals": _records(result.final_individuals, limit=500),
        "events": _records(result.events, limit=500),
        "redds": _records(result.redds, limit=500),
        "river_view": river_view,
    }


def compare_instream7_for_studio(
    payload: Mapping[str, object] | None,
    output_dir: str | Path,
) -> dict[str, object]:
    """Compare native summary and NetLogo BriefPop from the browser UI."""

    default = default_studio_scenario()
    payload = payload or {}
    values = _merged(cast(Mapping[str, object], default["instream"]), payload)
    native_summary = Path(_as_str(values.get("native_summary"), ""))
    brief_pop = Path(_as_str(values.get("brief_pop"), ""))
    if not native_summary.exists():
        raise ValueError("native_summary must point to an existing CSV")
    if not brief_pop.exists():
        raise ValueError("brief_pop must point to an existing BriefPopOut CSV")

    native = pd.read_csv(native_summary)
    brief_raw = read_instream7_brief_population(brief_pop)
    brief_summary = summarize_instream7_brief_population(brief_raw)
    comparison = compare_instream7_native_to_brief(
        native,
        brief_summary,
        abundance_tolerance=_as_int(values.get("abundance_tolerance"), 0, min_value=0),
        biomass_relative_tolerance=_as_float(
            values.get("biomass_relative_tolerance"), 0.05, min_value=0.0
        ),
        mean_length_tolerance_mm=_as_float(
            values.get("mean_length_tolerance_mm"), 1.0, min_value=0.0
        ),
    )
    run_root = _run_dir(output_dir, "compare")
    run_root.mkdir(parents=True, exist_ok=True)
    brief_summary_path = run_root / "netlogo_brief_summary.csv"
    comparison_path = run_root / "native_vs_netlogo_comparison.csv"
    brief_summary.to_csv(brief_summary_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    passed = (
        comparison["passed"].fillna(False).astype(bool)
        if "passed" in comparison
        else pd.Series(dtype=bool)
    )
    return {
        "ok": True,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": {
            "netlogo_brief_summary": str(brief_summary_path),
            "native_vs_netlogo_comparison": str(comparison_path),
        },
        "metrics": {
            "rows": int(len(comparison)),
            "outside_tolerance": int((~passed).sum()) if len(passed) else 0,
        },
        "brief_summary": _records(brief_summary),
        "comparison": _records(comparison),
    }


class _IBMStudioHTTPServer(ThreadingHTTPServer):
    output_dir: Path

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        output_dir: Path,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.output_dir = output_dir


class _IBMStudioHandler(BaseHTTPRequestHandler):
    server_version = "OpenLimnoIBMStudio/0.1"
    routes: ClassVar[dict[str, str]] = {
        "/": "index",
        "/index.html": "index",
        "/api/default": "default",
        "/favicon.ico": "favicon",
        "/api/run": "run",
        "/api/validate": "validate",
        "/api/ensemble": "ensemble",
        "/api/calibrate": "calibrate",
        "/api/gis/import": "gis_import",
        "/api/instream7/benchmark": "instream7_benchmark",
        "/api/instream7/compare": "instream7_compare",
    }

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    @property
    def studio_server(self) -> _IBMStudioHTTPServer:
        return cast(_IBMStudioHTTPServer, self.server)

    def _send_bytes(
        self, body: bytes, *, content_type: str, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self, payload: Mapping[str, object], *, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self._send_bytes(body, content_type="application/json; charset=utf-8", status=status)

    def _read_json(self) -> Mapping[str, object]:
        length = _as_int(self.headers.get("Content-Length"), 0, min_value=0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("request body must be a JSON object")
        return cast(Mapping[str, object], data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        route = self.routes.get(path)
        if route == "index":
            self._send_bytes(_INDEX_HTML.encode("utf-8"), content_type="text/html; charset=utf-8")
            return
        if route == "default":
            self._send_json(default_studio_scenario())
            return
        if route == "favicon":
            self._send_bytes(b"", content_type="image/x-icon")
            return
        self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        route = self.routes.get(path)
        if route in {"index", "default", "favicon"}:
            self.send_response(int(HTTPStatus.OK))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(int(HTTPStatus.NOT_FOUND))
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        route = self.routes.get(path)
        try:
            payload = self._read_json()
            if route == "run":
                self._send_json(run_studio_scenario(payload, self.studio_server.output_dir))
                return
            if route == "validate":
                self._send_json(validate_studio_payload(payload, self.studio_server.output_dir))
                return
            if route == "ensemble":
                self._send_json(run_studio_ensemble(payload, self.studio_server.output_dir))
                return
            if route == "calibrate":
                self._send_json(run_studio_calibration(payload, self.studio_server.output_dir))
                return
            if route == "gis_import":
                self._send_json(import_gis_for_studio(payload))
                return
            if route == "instream7_benchmark":
                self._send_json(
                    run_instream7_benchmark_for_studio(payload, self.studio_server.output_dir)
                )
                return
            if route == "instream7_compare":
                self._send_json(
                    compare_instream7_for_studio(payload, self.studio_server.output_dir)
                )
                return
            self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:  # pragma: no cover - exercised through browser/server smoke
            self._send_json(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                status=HTTPStatus.BAD_REQUEST,
            )


def run_ibm_studio(
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
    output_dir: str | Path = "/tmp/openlimno_ibm_studio",
    open_browser: bool = True,
) -> None:
    """Serve the local browser IBM Studio until interrupted."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    server = _IBMStudioHTTPServer((host, port), _IBMStudioHandler, out)
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}/"
    print(f"OpenLimno IBM Studio serving {url}", flush=True)
    print(f"Run output directory: {out}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


_INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenLimno IBM Studio</title>
<style>
:root {
  --bg: #f4f6f8;
  --panel: #ffffff;
  --ink: #18212c;
  --muted: #5e6b78;
  --line: #dce3ea;
  --teal: #0f766e;
  --green: #2f855a;
  --amber: #b7791f;
  --red: #c2410c;
  --blue: #2563eb;
  --shadow: 0 8px 24px rgba(24, 33, 44, 0.08);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.45 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  button, input, select, textarea { font: inherit; }
.app { min-height: 100vh; display: grid; grid-template-rows: 54px 1fr; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 0 18px; background: #ffffff; border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; }
.mark { width: 28px; height: 28px; border-radius: 7px; background: linear-gradient(135deg, var(--teal), #2f855a); display: grid; place-items: center; color: white; font-size: 13px; }
.status { color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shell { display: grid; grid-template-columns: minmax(360px, 420px) minmax(0, 1fr); min-height: 0; min-width: 0; }
.sidebar { border-right: 1px solid var(--line); background: #fbfcfd; overflow: auto; padding: 14px; min-width: 0; }
.workspace { overflow: auto; padding: 14px; min-width: 0; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); margin-bottom: 14px; min-width: 0; }
.panel > header { height: 42px; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 12px; border-bottom: 1px solid var(--line); }
.panel h2 { margin: 0; font-size: 14px; }
.panel-body { padding: 12px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.field { display: grid; gap: 5px; min-width: 0; }
label { color: var(--muted); font-size: 12px; }
  input, select, textarea { width: 100%; border: 1px solid #cfd8e3; border-radius: 6px; background: white; color: var(--ink); padding: 7px 8px; min-width: 0; }
  textarea { resize: vertical; min-height: 62px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
input[type="checkbox"] { width: 16px; height: 16px; }
.check { display: flex; align-items: center; gap: 8px; height: 34px; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.tab { border: 1px solid #cfd8e3; background: #fff; border-radius: 6px; padding: 6px 9px; cursor: pointer; }
.tab.active { background: #e7f5f3; border-color: #9bd4cb; color: #075b54; }
.profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
.btn { border: 1px solid #c8d3df; background: white; color: var(--ink); border-radius: 6px; padding: 7px 10px; cursor: pointer; }
.btn.primary { background: var(--teal); border-color: var(--teal); color: white; }
.btn.warn { background: #fff7ed; border-color: #fdba74; color: #9a3412; }
.btn:disabled { opacity: .55; cursor: wait; }
.table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e7edf3; padding: 7px 8px; text-align: left; vertical-align: top; }
th { background: #f7f9fb; color: #425466; font-weight: 650; position: sticky; top: 0; z-index: 1; }
td input { padding: 5px 6px; min-width: 82px; }
.kpis { display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)); gap: 10px; margin-bottom: 14px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; box-shadow: var(--shadow); }
.kpi .label { color: var(--muted); font-size: 12px; }
.kpi .value { font-size: 22px; font-weight: 750; margin-top: 4px; }
.official-result { background: #ffffff; border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); padding: 12px; margin-bottom: 14px; }
.official-result-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.official-result-head h2 { margin: 0; font-size: 15px; }
.official-subtitle { color: var(--muted); font-size: 12px; margin-top: 2px; }
.acceptance-grid { display: grid; grid-template-columns: repeat(6, minmax(105px, 1fr)); gap: 8px; margin-bottom: 12px; }
.acceptance-card { border: 1px solid #dbe5ee; border-radius: 8px; background: #fbfdff; padding: 10px; min-width: 0; }
.acceptance-card .label { color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.acceptance-card .value { font-weight: 750; font-size: 18px; margin-top: 3px; overflow-wrap: anywhere; }
.official-workflow { display: grid; grid-template-columns: repeat(6, minmax(105px, 1fr)); gap: 8px; margin: 0 0 12px; }
.workflow-step { border: 1px solid #dbe5ee; border-radius: 8px; background: #f8fafc; padding: 9px; min-height: 72px; display: grid; align-content: space-between; gap: 6px; min-width: 0; }
.workflow-step.passed { border-color: #86efac; background: #f0fdf4; }
.workflow-step.warning { border-color: #fcd34d; background: #fffbeb; }
.workflow-step.error { border-color: #fca5a5; background: #fef2f2; }
.workflow-step-label { font-size: 12px; font-weight: 750; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.workflow-step-summary { color: #475569; font-size: 12px; line-height: 1.25; overflow-wrap: anywhere; }
.workflow-step-status { justify-self: start; border-radius: 999px; padding: 2px 7px; font-size: 11px; font-weight: 750; text-transform: uppercase; background: #e2e8f0; color: #334155; }
.workflow-step.passed .workflow-step-status { background: #bbf7d0; color: #166534; }
.workflow-step.warning .workflow-step-status { background: #fde68a; color: #92400e; }
.workflow-step.error .workflow-step-status { background: #fecaca; color: #991b1b; }
.workflow-detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
.workflow-detail-card { border: 1px solid #e2e8f0; border-radius: 8px; background: #fbfdff; padding: 10px; min-width: 0; }
.workflow-detail-title { font-size: 13px; font-weight: 750; color: #1f2937; margin-bottom: 4px; }
.workflow-detail-summary { color: #475569; font-size: 12px; margin-bottom: 8px; line-height: 1.25; }
.workflow-evidence { display: grid; grid-template-columns: minmax(0, .86fr) minmax(0, 1.14fr); gap: 5px 8px; margin: 0; font-size: 12px; }
.workflow-evidence dt { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workflow-evidence dd { margin: 0; color: #0f172a; font-weight: 650; overflow-wrap: anywhere; }
.workflow-empty { grid-column: 1 / -1; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 12px; color: var(--muted); font-size: 12px; background: #fbfdff; }
.official-setup-steps { display: grid; gap: 10px; }
.official-setup-block { border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #fbfdff; }
.official-setup-title { font-weight: 750; font-size: 13px; margin-bottom: 8px; color: #1f2937; }
.result-split { align-items: start; }
.result-table-title { color: #334155; font-weight: 700; font-size: 13px; margin: 0 0 6px; }
.official-events { margin-top: 12px; }
.chart-card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); padding: 12px; margin-bottom: 14px; min-width: 0; }
.chart-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.river-card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); padding: 12px; margin-bottom: 14px; min-width: 0; }
.river-card.fullscreen { position: fixed; inset: 10px; z-index: 40; display: grid; grid-template-rows: auto 1fr; }
.river-card.fullscreen #riverView { height: calc(100vh - 164px); }
body.map-fullscreen-open { overflow: hidden; }
.river-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.river-head h2 { margin: 0; font-size: 14px; }
.river-title { color: var(--muted); font-size: 12px; margin-top: 2px; }
.river-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.river-controls select { width: 150px; }
.map-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.icon-btn { min-width: 32px; height: 32px; border: 1px solid #c8d3df; border-radius: 6px; background: white; color: var(--ink); cursor: pointer; padding: 0 9px; }
.icon-btn.active { background: #e7f5f3; border-color: #8bcfc4; color: #075b54; }
.map-layers { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 0 10px; border-top: 1px solid #edf2f7; border-bottom: 1px solid #edf2f7; margin-bottom: 10px; }
.map-layers .check { height: 24px; }
.quality-strip { display: flex; flex-wrap: wrap; gap: 7px; margin: 0 0 10px; }
.quality-pill { display: inline-flex; align-items: center; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 650; border: 1px solid #cbd5e1; background: #f8fafc; color: #334155; }
.quality-pill.good { background: #dcfce7; color: #166534; border-color: #86efac; }
.quality-pill.warn { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
.quality-pill.bad { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
.river-stage { display: grid; grid-template-columns: minmax(0, 1fr) 230px; gap: 12px; align-items: stretch; }
.river-svg-wrap { position: relative; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: linear-gradient(#f7fbfd, #eef6f8); }
#riverView { width: 100%; height: 360px; display: block; }
.map-coordinates { position: absolute; left: 10px; bottom: 8px; padding: 3px 7px; border: 1px solid rgba(49,95,114,.24); border-radius: 5px; background: rgba(255,255,255,.86); color: #334155; font-size: 11px; pointer-events: none; }
.river-side { display: grid; gap: 10px; align-content: start; }
.river-meta, .river-legend { border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #fbfdff; color: #334155; font-size: 12px; }
.river-meta strong { display: block; color: var(--ink); font-size: 13px; margin-bottom: 5px; }
.river-warning { color: #991b1b; font-weight: 700; }
.legend-row { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
.legend-swatch { width: 16px; height: 12px; border-radius: 3px; border: 1px solid rgba(15, 23, 42, .18); }
.bank-shape { fill: #9fd3e7; stroke: #315f72; stroke-width: 1.5; opacity: .86; }
.centerline-shape { fill: none; stroke: rgba(255,255,255,.78); stroke-width: 2; stroke-dasharray: 8 9; }
.centerline-only { fill: none; stroke: #1f5f78; stroke-width: 5; stroke-linecap: round; stroke-linejoin: round; }
.cell-shape { stroke: rgba(15, 23, 42, .42); stroke-width: 1.4; }
.cell-label { fill: #16324a; font-size: 10px; paint-order: stroke; stroke: rgba(255,255,255,.82); stroke-width: 3px; stroke-linejoin: round; }
.fish-shape { stroke: rgba(29, 78, 216, .36); stroke-width: .35; }
.redd-shape { fill: #dc6b19; stroke: #7c2d12; stroke-width: 1; }
.preview-badge { fill: rgba(146,64,14,.92); }
svg { width: 100%; height: 280px; display: block; }
.axis { stroke: #8b9bad; stroke-width: 1; }
.grid { stroke: #e7edf3; stroke-width: 1; }
.line { fill: none; stroke: var(--teal); stroke-width: 3; }
  .split { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(320px, .8fr); gap: 14px; }
  .triptych { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
  .log { min-height: 78px; max-height: 180px; overflow: auto; background: #101820; color: #d6e2ee; border-radius: 8px; padding: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.path-list { margin: 0; padding-left: 18px; }
.path-list li { margin: 4px 0; word-break: break-all; }
  .badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 7px; font-size: 12px; background: #eef2f7; color: #425466; }
  .status-pill { display: inline-flex; align-items: center; justify-content: center; min-width: 56px; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 650; }
  .status-pill.pass { background: #dcfce7; color: #166534; }
  .status-pill.warning { background: #fef3c7; color: #92400e; }
  .status-pill.error { background: #fee2e2; color: #991b1b; }
  .compact-list { margin: 0; padding-left: 18px; color: #334155; }
  .compact-list li { margin: 3px 0; }
  .mini-note { color: var(--muted); font-size: 12px; }
.gis-steps { display: grid; gap: 10px; }
.gis-step { border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #fbfdff; }
.gis-step-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.gis-step-title { font-weight: 700; font-size: 13px; }
.gis-required { color: #991b1b; font-size: 12px; }
.gis-checks { display: grid; gap: 5px; margin-top: 10px; color: #334155; font-size: 12px; }
.gis-check { display: flex; align-items: center; gap: 7px; }
.gis-dot { width: 9px; height: 9px; border-radius: 999px; background: #cbd5e1; }
.gis-dot.ok { background: #16a34a; }
.gis-dot.warn { background: #d97706; }
  @media (max-width: 1100px) { .shell { grid-template-columns: minmax(0, 1fr); } .sidebar { border-right: 0; border-bottom: 1px solid var(--line); } .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } .acceptance-grid, .official-workflow, .workflow-detail-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } .split, .triptych { grid-template-columns: minmax(0, 1fr); } .river-stage { grid-template-columns: minmax(0, 1fr); } }
  @media (max-width: 640px) { .app { grid-template-rows: auto 1fr; } .topbar { align-items: flex-start; flex-direction: column; padding: 10px 12px; gap: 6px; } .brand { flex-wrap: wrap; } .status { width: 100%; white-space: normal; } .sidebar, .workspace { padding: 10px; } .grid2, .profile-grid { grid-template-columns: minmax(0, 1fr); } .actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } .actions .btn { width: 100%; } .kpis, .acceptance-grid, .official-workflow, .workflow-detail-grid { grid-template-columns: minmax(0, 1fr); } .official-result-head, .river-head, .chart-head { align-items: flex-start; flex-direction: column; } .river-controls { width: 100%; } .river-controls select { width: 100%; } #riverView { height: 280px; } }
</style>
</head>
<body>
<div class="app">
  <div class="topbar"><div class="brand"><div class="mark">OL</div><div>OpenLimno IBM Studio</div><span class="badge">native agent model</span></div><div id="status" class="status">Ready</div></div>
  <div class="shell">
    <aside class="sidebar">
      <section class="panel"><header><h2>Run Setup</h2></header><div class="panel-body"><div class="grid2">
        <div class="field"><label>Scenario</label><input id="scenario_id"></div><div class="field"><label>Reach</label><input id="reach_id"></div>
        <div class="field"><label>Species</label><input id="species"></div><div class="field"><label>Initial fish</label><input id="initial_abundance" type="number" min="0"></div>
        <div class="field"><label>Initial length mm</label><input id="initial_length_mm" type="number" step="0.1" min="1"></div><div class="field"><label>Days</label><input id="days" type="number" min="0"></div>
        <div class="field"><label>Seed</label><input id="seed" type="number"></div><div class="field check"><input id="stochastic" type="checkbox"><label for="stochastic">Stochastic</label></div>
        <div class="field check"><input id="record_individual_history" type="checkbox"><label for="record_individual_history">Fish history</label></div>
      </div><div class="actions" style="margin-top: 12px;"><button id="runBtn" class="btn primary">Run</button><button id="validateBtn" class="btn">Validate</button><button id="stepBtn" class="btn">Step +1 day</button><button id="resetBtn" class="btn">Reset</button><button id="exportBtn" class="btn">Export JSON</button><button id="importBtn" class="btn">Import JSON</button><input id="importFile" type="file" accept="application/json" style="display:none"></div></div></section>
      <section class="panel"><header><h2>River</h2></header><div class="panel-body"><div class="grid2">
        <div class="field"><label>River name</label><input id="river_name"></div><div class="field"><label>Reach name</label><input id="river_reach_name"></div>
        <div class="field"><label>Length m</label><input id="river_length_m" type="number" min="1" step="1"></div><div class="field"><label>Flow m3/s</label><input id="river_flow_m3s" type="number" min="0" step="0.1"></div>
      </div></div></section>
      <section class="panel"><header><h2>GIS Import</h2><span class="badge">boundary first</span></header><div class="panel-body">
        <div class="gis-steps">
          <div class="gis-step">
            <div class="gis-step-head"><div class="gis-step-title">1. River Boundary</div><div class="gis-required">required for true channel shape</div></div>
            <div class="grid2"><div class="field"><label>Boundary path or URL</label><input id="gis_boundary_path" placeholder="/path/banks_or_channel_polygon.geojson, .shp, .gpkg, or https://...f=geojson"></div><div class="field"><label>Boundary layer</label><input id="gis_boundary_layer"></div></div>
          </div>
          <div class="gis-step">
            <div class="gis-step-head"><div class="gis-step-title">2. Flow Centerline</div><span class="badge">optional</span></div>
            <div class="grid2"><div class="field"><label>Centerline path or URL</label><input id="gis_centerline_path" placeholder="/path/centerline.geojson, .shp, .gpkg, or https://...f=geojson"></div><div class="field"><label>Centerline layer</label><input id="gis_centerline_layer"></div></div>
          </div>
          <div class="gis-step">
            <div class="gis-step-head"><div class="gis-step-title">3. Habitat Cells</div><span class="badge">required for IBM fish positions</span></div>
            <div class="grid2"><div class="field"><label>Habitat cells path or URL</label><input id="gis_cells_path" placeholder="/path/habitat_cells.geojson, .shp, .gpkg, or https://...f=geojson"></div><div class="field"><label>Cells layer</label><input id="gis_cells_layer"></div></div>
          </div>
        </div>
        <div id="gisChecks" class="gis-checks"></div>
        <div class="actions" style="margin-top: 12px;"><button id="gisImportBtn" class="btn primary">Import GIS</button></div>
      </div></section>
      <section class="panel"><header><h2>Species Profile</h2></header><div class="panel-body"><div class="tabs" id="profileTabs"></div><div class="profile-grid" id="profileFields"></div></div></section>
      <section class="panel"><header><h2>Submodels</h2></header><div class="panel-body"><div class="profile-grid" id="submodelFields"></div></div></section>
      <section class="panel"><header><h2>Experiments</h2></header><div class="panel-body">
        <div class="field"><label>Ensemble seeds</label><input id="ensemble_seeds"></div>
        <div class="field" style="margin-top: 10px;"><label>Ensemble parameters</label><textarea id="ensemble_params"></textarea></div>
        <div class="actions" style="margin-top: 12px;"><button id="ensembleBtn" class="btn">Run ensemble</button></div>
        <div class="grid2" style="margin-top: 12px;">
          <div class="field"><label>Calibration method</label><select id="calibration_method"><option value="grid">grid</option><option value="abc">abc</option></select></div>
          <div class="field"><label>ABC samples</label><input id="calibration_samples" type="number" min="1"></div>
          <div class="field"><label>Acceptance fraction</label><input id="acceptance_fraction" type="number" min="0.001" max="1" step="0.01"></div>
          <div class="field"><label>Tolerance</label><input id="calibration_tolerance" type="number" min="0" step="0.1"></div>
        </div>
        <div class="field" style="margin-top: 10px;"><label>Observed CSV</label><input id="observed_path" placeholder="leave blank to use current run"></div>
        <div class="field" style="margin-top: 10px;"><label>Calibration parameters</label><textarea id="calibration_params"></textarea></div>
        <div class="actions" style="margin-top: 12px;"><button id="calibrateBtn" class="btn">Calibrate</button></div>
      </div></section>
      <section class="panel"><header><h2>Habitat Cells</h2><button id="addCellBtn" class="btn">Add row</button></header><div class="panel-body"><div class="table-wrap"><table id="cellsTable"></table></div></div></section>
      <section class="panel"><header><h2>Official IBM Workflow</h2><span class="badge">inSTREAM / InSALMO</span></header><div class="panel-body">
        <div class="official-setup-steps">
          <div class="official-setup-block"><div class="official-setup-title">1. Official case source</div><div class="grid2"><div class="field"><label>Official fixture</label><input id="instream_fixture" placeholder="/path/to/InSTREAM-7.4 or InSALMO-7.4 zip"></div><div class="field"><label>Case</label><input id="instream_case_id"></div></div></div>
          <div class="official-setup-block"><div class="official-setup-title">2. Native IBM run</div><div class="grid2"><div class="field"><label>Days</label><input id="instream_days" type="number" min="1"></div><div class="field"><label>Seed</label><input id="instream_seed" type="number"></div></div></div>
          <div class="official-setup-block"><div class="official-setup-title">3. NetLogo comparison</div><div class="grid2"><div class="field"><label>Native summary CSV</label><input id="native_summary" placeholder="instream7_native_population_summary.csv"></div><div class="field"><label>BriefPop CSV</label><input id="brief_pop" placeholder="BriefPopOut-r1.csv"></div></div></div>
        </div>
        <div class="actions" style="margin-top: 12px;"><button id="benchBtn" class="btn primary">Run workflow</button><button id="compareBtn" class="btn">Compare BriefPop</button></div>
      </div></section>
    </aside>
    <main class="workspace">
      <div class="kpis" id="kpis"></div>
      <section id="officialResult" class="official-result">
        <div class="official-result-head"><div><h2>Official Acceptance Result</h2><div id="officialSubtitle" class="official-subtitle">Run an official inSTREAM or InSALMO fixture to populate this capture panel.</div></div><span id="officialStatus" class="status-pill warning">no run</span></div>
        <div id="officialWorkflow" class="official-workflow"></div>
        <div id="officialWorkflowDetails" class="workflow-detail-grid"></div>
        <div id="officialSummary" class="acceptance-grid"></div>
        <div class="split result-split">
          <div><div class="result-table-title">Final Population</div><div class="table-wrap"><table id="officialFinalTable"></table></div></div>
          <div><div class="result-table-title">Official Inventory</div><div class="table-wrap"><table id="officialInventoryTable"></table></div></div>
        </div>
        <div class="official-events"><div class="result-table-title">Acceptance Events</div><div class="table-wrap"><table id="officialEventsTable"></table></div></div>
      </section>
      <section id="riverCard" class="river-card"><div class="river-head"><div><h2>River View</h2><div id="riverTitle" class="river-title">No run loaded</div></div><div class="river-controls"><label for="cellColorMetric">Cell color</label><select id="cellColorMetric"><option value="csi">CSI</option><option value="depth_m">Depth</option><option value="velocity_ms">Velocity</option><option value="total_fish_use">Fish use</option><option value="habitat_type">Habitat</option></select><div class="map-toolbar"><button id="zoomInBtn" class="icon-btn" title="Zoom in">+</button><button id="zoomOutBtn" class="icon-btn" title="Zoom out">-</button><button id="fitMapBtn" class="icon-btn" title="Fit map">Fit</button><button id="inspectMapBtn" class="icon-btn" title="Inspect features">Inspect</button><button id="fullMapBtn" class="icon-btn" title="Fullscreen map">Full</button></div></div></div><div id="qualityStrip" class="quality-strip"></div><div class="map-layers"><div class="check"><input id="showBoundary" type="checkbox" checked><label for="showBoundary">Boundary</label></div><div class="check"><input id="showCenterline" type="checkbox" checked><label for="showCenterline">Centerline</label></div><div class="check"><input id="showCells" type="checkbox" checked><label for="showCells">Cells</label></div><div class="check"><input id="showFish" type="checkbox" checked><label for="showFish">Fish</label></div><div class="check"><input id="showDeadFish" type="checkbox"><label for="showDeadFish">Dead fish</label></div><div class="check"><input id="showRedds" type="checkbox" checked><label for="showRedds">Redds</label></div></div><div class="river-stage"><div class="river-svg-wrap"><svg id="riverView" viewBox="0 0 900 360" role="img" aria-label="River reach with habitat cells and fish"></svg><div id="mapCoords" class="map-coordinates">x -, y -</div></div><div class="river-side"><div id="riverMeta" class="river-meta"></div><div id="riverLegend" class="river-legend"></div></div></div></section>
      <section class="chart-card"><div class="chart-head"><h2>Population Trajectory</h2><select id="metricSelect"><option value="abundance">Abundance</option><option value="biomass_g">Biomass</option><option value="mean_length_mm">Mean length</option></select></div><svg id="chart" viewBox="0 0 900 280"></svg></section>
      <section class="chart-card"><div class="chart-head"><h2>Uncertainty Bands</h2><select id="bandMetricSelect"><option value="abundance">Abundance</option><option value="biomass_g">Biomass</option><option value="mean_length_mm">Mean length</option></select></div><svg id="bandChart" viewBox="0 0 900 280"></svg></section>
      <div class="triptych"><section class="panel"><header><h2>Validation</h2></header><div class="panel-body"><div class="table-wrap"><table id="validationTable"></table></div></div></section><section class="panel"><header><h2>Run History</h2></header><div class="panel-body"><div class="table-wrap"><table id="historyTable"></table></div></div></section><section class="panel"><header><h2>Calibration</h2></header><div class="panel-body"><div id="bestParams" class="mini-note"></div><div class="table-wrap" style="margin-top: 8px;"><table id="calibrationTable"></table></div></div></section></div>
      <div class="split"><section class="panel"><header><h2>Ensemble Summary</h2></header><div class="panel-body"><div class="table-wrap"><table id="ensembleTable"></table></div></div></section><section class="panel"><header><h2>Sensitivity</h2></header><div class="panel-body"><div class="table-wrap"><table id="sensitivityTable"></table></div></div></section></div>
      <div class="split"><section class="panel"><header><h2>Habitat Use</h2></header><div class="panel-body"><div class="table-wrap"><table id="cellUseTable"></table></div></div></section><section class="panel"><header><h2>Events</h2></header><div class="panel-body"><div class="table-wrap"><table id="eventsTable"></table></div></div></section></div>
      <section class="panel"><header><h2>Fish State</h2></header><div class="panel-body"><div class="table-wrap"><table id="fishTable"></table></div></div></section>
      <section class="panel"><header><h2>Redds</h2></header><div class="panel-body"><div class="table-wrap"><table id="reddsTable"></table></div></div></section>
      <section class="panel"><header><h2>inSTREAM Comparison</h2></header><div class="panel-body"><div class="table-wrap"><table id="compareTable"></table></div></div></section>
      <section class="panel"><header><h2>Output</h2></header><div class="panel-body"><ul id="paths" class="path-list"></ul><div id="log" class="log"></div></div></section>
    </main>
  </div>
</div>
<script>
const profileGroups = {
  Growth: ['thermal_min_c','thermal_optimum_c','thermal_max_c','max_daily_growth_mm','weight_a_g_per_cm_b','weight_b','max_consumption_fraction','respiration_fraction','activity_respiration_fraction','respiration_base_multiplier','respiration_thermal_multiplier'],
  Survival: ['base_daily_survival','predation_base_risk','predation_csi_risk','thermal_stress_mortality','velocity_stress_threshold_ms','velocity_stress_scale_ms','hydraulic_stress_mortality','max_mortality_risk','max_mass_loss_fraction','max_mass_gain_fraction','max_daily_shrinkage_mm'],
  Behavior: ['carrying_density_per_m2','min_cell_capacity','density_competition_strength','turbidity_half_saturation_ntu','feeding_cover_foraging_weight','utility_growth_weight','utility_mortality_weight','max_activity_velocity_ms'],
  Spawning: ['maturity_length_mm','spawn_start_day','spawn_end_day','spawner_female_fraction','fecundity_per_female','fecundity_length_exponent','fecundity_reference_length_mm','egg_to_fry_survival','egg_incubation_degree_days','spawning_cover_weight','spawning_csi_weight','redd_base_daily_survival','redd_min_depth_m','redd_scour_velocity_ms','redd_dewatering_mortality','redd_scour_mortality','fry_length_mm','fry_mass_g'],
  Movement: ['allow_cross_reach_movement','cross_reach_movement_penalty','cross_reach_movement_rate','cross_reach_movement_min_length_mm','cross_reach_movement_length_scale_mm','cross_reach_movement_max_steps','cross_reach_interior_movement_multiplier','cross_reach_upstream_bias','cross_reach_habitat_utility_weight']
};
const cellColumns = ['cell_id','habitat_type','station_m','center_x_m','center_y_m','length_m','width_m','reach_id','reach_order','area_m2','depth_m','velocity_ms','csi','temperature_c','turbidity_ntu','hiding_cover','feeding_cover','spawning_cover'];
const habitatColors = {riffle:'#77c8a6',run:'#70b7d5',pool:'#3b82c4',margin:'#b7d48b',tailout:'#d9c16f','side-channel':'#88d4c0',glide:'#7ab7e8',chute:'#e18b5a',cell:'#9fc5d8'};
let state = null;
let activeProfileGroup = 'Growth';
let lastResult = null;
let lastEnsemble = null;
let runHistory = [];
let lastRiverViewPayload = null;
let dragStart = null;
const mapState = {
  zoom: 1,
  panX: 0,
  panY: 0,
  signature: '',
  inspect: false,
  showBoundary: true,
  showCenterline: true,
  showCells: true,
  showFish: true,
  showRedds: true,
  transform: null
};
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = v => {
  if (v === '' || v === null || v === undefined) return v;
  const p = Number(v);
  return Number.isFinite(p) ? p : v;
};
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const fmt = (value, digits = 1) => {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : '-';
};
function riverDefaults(){return {name:'Lemhi River', reach_name:'Hayden Creek demo reach', length_m:380, flow_m3s:5.8, display_note:'', geometry:null};}
function gisDefaults(){return {centerline_path:'', centerline_layer:'', boundary_path:'', boundary_layer:'', cells_path:'', cells_layer:''};}
function setStatus(t){$('status').textContent=t;}
function log(t){const el=$('log'); el.textContent=`${new Date().toLocaleTimeString()}  ${t}\n`+el.textContent;}
async function api(path,payload){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const data=await res.json(); if(!res.ok||data.ok===false) throw new Error(data.error||res.statusText); return data;}
async function loadDefault(){const res=await fetch('/api/default'); state=await res.json(); bindState(); renderAll(); await runModel();}
function bindState(){
  state.river = {...riverDefaults(), ...(state.river || {})};
  state.gis = {...gisDefaults(), ...(state.gis || {})};
  state.submodels = state.submodels || {};
  state.submodel_catalog = state.submodel_catalog || [];
  state.experiments = state.experiments || {ensemble:{}, calibration:{}};
  state.experiments.ensemble = state.experiments.ensemble || {};
  state.experiments.calibration = state.experiments.calibration || {};
  const c=state.config;
  ['scenario_id','reach_id','species','initial_abundance','initial_length_mm','days','seed'].forEach(id=>{$(id).value=c[id];});
  $('stochastic').checked=!!c.stochastic;
  $('record_individual_history').checked=!!c.record_individual_history;
  $('river_name').value=state.river.name || '';
  $('river_reach_name').value=state.river.reach_name || '';
  $('river_length_m').value=state.river.length_m ?? '';
  $('river_flow_m3s').value=state.river.flow_m3s ?? '';
  $('gis_centerline_path').value=state.gis.centerline_path || state.gis.river_path || '';
  $('gis_centerline_layer').value=state.gis.centerline_layer || state.gis.river_layer || '';
  $('gis_boundary_path').value=state.gis.boundary_path || '';
  $('gis_boundary_layer').value=state.gis.boundary_layer || '';
  $('gis_cells_path').value=state.gis.cells_path || '';
  $('gis_cells_layer').value=state.gis.cells_layer || '';
  const i=state.instream;
  $('instream_fixture').value=i.fixture||'';
  $('instream_case_id').value=i.case_id||'ExampleA';
  $('instream_days').value=i.days||2;
  $('instream_seed').value=i.seed||11;
  $('native_summary').value=i.native_summary||'';
  $('brief_pop').value=i.brief_pop||'';
  const e=state.experiments.ensemble;
  $('ensemble_seeds').value=e.seeds || '20260524,20260525,20260526';
  $('ensemble_params').value=e.parameter_specs || '';
  const cal=state.experiments.calibration;
  $('calibration_method').value=cal.method || 'grid';
  $('observed_path').value=cal.observed || '';
  $('calibration_params').value=cal.parameter_specs || '';
  $('calibration_samples').value=cal.samples ?? 8;
  $('acceptance_fraction').value=cal.acceptance_fraction ?? 0.25;
  $('calibration_tolerance').value=cal.tolerance ?? '';
}
function collectState(){
  const config={scenario_id:$('scenario_id').value,reach_id:$('reach_id').value,species:$('species').value,initial_abundance:Number($('initial_abundance').value),initial_length_mm:Number($('initial_length_mm').value),days:Number($('days').value),seed:Number($('seed').value),stochastic:$('stochastic').checked,record_individual_history:$('record_individual_history').checked};
  const river={...riverDefaults(), name:$('river_name').value, reach_name:$('river_reach_name').value, length_m:Number($('river_length_m').value), flow_m3s:Number($('river_flow_m3s').value), display_note:state.river?.display_note || '', geometry:state.river?.geometry || null};
  const profile={...state.profile};
  document.querySelectorAll('[data-profile]').forEach(input=>{const key=input.getAttribute('data-profile'); profile[key]=input.type==='checkbox'?input.checked:num(input.value);});
  const submodels={...state.submodels};
  document.querySelectorAll('[data-submodel]').forEach(select=>{submodels[select.dataset.submodel]=select.value;});
  const cells=[...document.querySelectorAll('#cellsTable tbody tr')].map((tr,idx)=>{const row={...(state.cells?.[idx]||{})}; tr.querySelectorAll('input').forEach(input=>row[input.dataset.column]=num(input.value)); return row;});
  const experiments={ensemble:{seeds:$('ensemble_seeds').value,parameter_specs:$('ensemble_params').value},calibration:{method:$('calibration_method').value,observed:$('observed_path').value,parameter_specs:$('calibration_params').value,samples:Number($('calibration_samples').value),acceptance_fraction:Number($('acceptance_fraction').value),tolerance:$('calibration_tolerance').value}};
  const instream={fixture:$('instream_fixture').value,case_id:$('instream_case_id').value,days:Number($('instream_days').value),seed:Number($('instream_seed').value),native_summary:$('native_summary').value,brief_pop:$('brief_pop').value,abundance_tolerance:state.instream.abundance_tolerance??0,biomass_relative_tolerance:state.instream.biomass_relative_tolerance??0.05,mean_length_tolerance_mm:state.instream.mean_length_tolerance_mm??1.0};
  const gis={centerline_path:$('gis_centerline_path').value,centerline_layer:$('gis_centerline_layer').value,boundary_path:$('gis_boundary_path').value,boundary_layer:$('gis_boundary_layer').value,cells_path:$('gis_cells_path').value,cells_layer:$('gis_cells_layer').value};
  state={config,river,gis,profile,cells,submodels,submodel_catalog:state.submodel_catalog||[],experiments,instream};
  return state;
}
function renderGisGuidance(){
  const gis=state?.gis || {};
  const geometry=state?.river?.geometry || {};
  const quality=geometry.boundary_quality || {};
  const rows=[
    {ok:!!gis.boundary_path || Array.isArray(geometry.channel_polygon_m), warn:!gis.boundary_path && !geometry.channel_polygon_m, text:'Boundary polygon loaded or selected'},
    {ok:quality.status==='usable', warn:quality.status==='coarse', text:`Boundary quality: ${quality.status || 'not checked'}`},
    {ok:!!gis.cells_path || (state?.cells || []).some(cell=>Array.isArray(cell.polygon_m)), warn:!gis.cells_path, text:'Habitat-cell polygons for IBM fish positions'},
    {ok:!!gis.centerline_path || Array.isArray(geometry.centerline_m), warn:!gis.centerline_path, text:'Centerline for flow direction and stationing'}
  ];
  $('gisChecks').innerHTML=rows.map(row=>`<div class="gis-check"><span class="gis-dot ${row.ok?'ok':row.warn?'warn':''}"></span><span>${esc(row.text)}</span></div>`).join('');
}
function renderProfileTabs(){$('profileTabs').innerHTML=Object.keys(profileGroups).map(name=>`<button class="tab ${name===activeProfileGroup?'active':''}" data-tab="${esc(name)}">${esc(name)}</button>`).join(''); document.querySelectorAll('[data-tab]').forEach(btn=>btn.addEventListener('click',()=>{activeProfileGroup=btn.dataset.tab; renderProfileTabs(); renderProfileFields();}));}
function renderProfileFields(){const keys=profileGroups[activeProfileGroup]; $('profileFields').innerHTML=keys.map(key=>{const value=state.profile[key]; if(typeof value==='boolean') return `<div class="field check"><input data-profile="${key}" id="p_${key}" type="checkbox" ${value?'checked':''}><label for="p_${key}">${key}</label></div>`; const step=Number.isInteger(value)?'1':'0.001'; return `<div class="field"><label>${key}</label><input data-profile="${key}" type="number" step="${step}" value="${esc(value)}"></div>`;}).join('');}
function renderSubmodels(){const catalog=state.submodel_catalog||[]; const slots=[...new Set(catalog.map(m=>m.slot))]; $('submodelFields').innerHTML=slots.map(slot=>{const options=catalog.filter(m=>m.slot===slot).map(m=>`<option value="${esc(m.id)}" ${state.submodels?.[slot]===m.id?'selected':''}>${esc(m.label)}</option>`).join(''); return `<div class="field"><label>${esc(slot)}</label><select data-submodel="${esc(slot)}">${options}</select></div>`;}).join('');}
function renderCells(){const head=`<thead><tr>${cellColumns.map(c=>`<th>${c}</th>`).join('')}<th></th></tr></thead>`; const body=state.cells.map((row,idx)=>`<tr>${cellColumns.map(c=>`<td><input data-column="${c}" value="${esc(row[c]??'')}"></td>`).join('')}<td><button class="btn warn" data-del-cell="${idx}">Del</button></td></tr>`).join(''); $('cellsTable').innerHTML=`${head}<tbody>${body}</tbody>`; document.querySelectorAll('[data-del-cell]').forEach(btn=>btn.addEventListener('click',()=>{state.cells.splice(Number(btn.dataset.delCell),1); renderCells();}));}
function renderAll(){renderProfileTabs(); renderProfileFields(); renderSubmodels(); renderCells(); renderGisGuidance(); renderOfficialPlaceholder();}
function renderKpis(m){const items=[['Initial',m?.initial_abundance??'-'],['Final',m?.final_abundance??'-'],['Biomass g',m?.final_biomass_g?.toFixed?m.final_biomass_g.toFixed(1):'-'],['Mean length',m?.final_mean_length_mm?.toFixed?m.final_mean_length_mm.toFixed(1):'-'],['Survival',m?.survival_rate?.toFixed?m.survival_rate.toFixed(3):'-']]; $('kpis').innerHTML=items.map(([l,v])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');}
function acceptanceCard(label,value){return `<div class="acceptance-card"><div class="label">${esc(label)}</div><div class="value">${esc(value ?? '-')}</div></div>`;}
function workflowStatusClass(value){return ['passed','warning','error'].includes(value)?value:'warning';}
function workflowEvidence(evidence){
  const rows=Object.entries(evidence||{});
  if(!rows.length) return '<div class="mini-note">No evidence captured.</div>';
  return `<dl class="workflow-evidence">${rows.map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(value ?? '-')}</dd>`).join('')}</dl>`;
}
function renderOfficialWorkflowPlaceholder(){
  const steps=[
    {label:'1 Case',summary:'select fixture and case'},
    {label:'2 GIS',summary:'read official polygons'},
    {label:'3 Hydraulics',summary:'load flow and velocity tables'},
    {label:'4 Population',summary:'build fish cohorts'},
    {label:'5 Run',summary:'execute native IBM'},
    {label:'6 Acceptance',summary:'capture outputs'}
  ];
  $('officialWorkflow').innerHTML=steps.map(step=>`<div class="workflow-step warning"><div class="workflow-step-label">${esc(step.label)}</div><div class="workflow-step-summary">${esc(step.summary)}</div><span class="workflow-step-status">waiting</span></div>`).join('');
  $('officialWorkflowDetails').innerHTML='<div class="workflow-empty">No official case has been run. The workflow will show the exact modeling evidence after execution.</div>';
}
function renderOfficialWorkflow(result){
  const steps=result?.workflow?.steps || [];
  if(!steps.length){renderOfficialWorkflowPlaceholder(); return;}
  $('officialWorkflow').innerHTML=steps.map(step=>{const cls=workflowStatusClass(step.status); return `<div class="workflow-step ${cls}"><div class="workflow-step-label">${esc(step.label)}</div><div class="workflow-step-summary">${esc(step.summary)}</div><span class="workflow-step-status">${esc(step.status)}</span></div>`;}).join('');
  $('officialWorkflowDetails').innerHTML=steps.map(step=>{const cls=workflowStatusClass(step.status); return `<div class="workflow-detail-card ${cls}"><div class="workflow-detail-title">${esc(step.label)}</div><div class="workflow-detail-summary">${esc(step.summary)}</div>${workflowEvidence(step.evidence)}</div>`;}).join('');
}
function renderOfficialPlaceholder(){
  $('officialStatus').textContent='no run';
  $('officialStatus').className='status-pill warning';
  $('officialSubtitle').textContent='Run an official inSTREAM or InSALMO fixture to populate this capture panel.';
  renderOfficialWorkflowPlaceholder();
  $('officialSummary').innerHTML=[
    acceptanceCard('Suite','-'),
    acceptanceCard('Cases','-'),
    acceptanceCard('Reaches','-'),
    acceptanceCard('Species','-'),
    acceptanceCard('Final abundance','-'),
    acceptanceCard('Adult arrivals','-')
  ].join('');
  table('officialFinalTable',[]);
  table('officialInventoryTable',[]);
  table('officialEventsTable',[]);
}
function renderOfficialBenchmark(result){
  const m=result.metrics||{};
  const events=m.event_counts||{};
  const eventSummary=Object.entries(events).map(([k,v])=>`${k}:${v}`).join(', ') || 'none';
  $('officialStatus').textContent='passed';
  $('officialStatus').className='status-pill pass';
  $('officialSubtitle').textContent=`${m.suite||'official'} ${result.run_id||''} · ${result.run_dir||''}`;
  renderOfficialWorkflow(result);
  $('officialSummary').innerHTML=[
    acceptanceCard('Suite',m.suite||'official'),
    acceptanceCard('Cases',m.case_count),
    acceptanceCard('Reaches',m.reach_count),
    acceptanceCard('Species',Array.isArray(m.species)?m.species.join(', '):m.species_count),
    acceptanceCard('GIS cells',m.gis_cells),
    acceptanceCard('Boundary vertices',m.gis_boundary_vertices),
    acceptanceCard('Final abundance',m.final_abundance),
    acceptanceCard('Adult arrivals',m.adult_arrival_fish),
    acceptanceCard('Flow range',m.min_flow_m3s!==null&&m.min_flow_m3s!==undefined?`${m.min_flow_m3s} - ${m.max_flow_m3s}`:'-'),
    acceptanceCard('Population rows',m.population_rows),
    acceptanceCard('Events',eventSummary)
  ].join('');
  table('officialFinalTable',result.final_population||[],['scenario_id','reach_id','species','day','abundance','biomass_g','mean_length_mm','n_spawners','n_recruits']);
  table('officialInventoryTable',result.inventory||[],['case_id','reach_id','species','n_initial_fish','n_adult_arrival_fish','n_cells','n_time_series_rows','min_flow_m3s','max_flow_m3s']);
  table('officialEventsTable',result.events||[],['day','event','reach_id','species','n','n_eggs']);
  table('compareTable',result.final_population||[],['scenario_id','reach_id','species','day','abundance','biomass_g','mean_length_mm']);
  table('cellUseTable',result.cell_use||[],['scenario_id','reach_id','species','day','phase','cell_id','n_fish','mean_growth_mm','mean_mortality_risk']);
  table('eventsTable',result.events||[],['day','event','reach_id','species','n','n_eggs']);
  table('fishTable',result.final_individuals||[],['fish_id','species','age_days','length_mm','mass_g','cell_id','alive','reach_id']);
  table('reddsTable',result.redds||[],['redd_id','day','reach_id','cell_id','eggs_remaining','degree_days','active']);
  if(result.river_view) drawRiverView(result);
}
function drawChart(rows){const metric=$('metricSelect').value, svg=$('chart'); const w=900,h=280,l=48,r=18,t=18,b=34,pw=w-l-r,ph=h-t-b; if(!rows||!rows.length){svg.innerHTML='';return;} const xs=rows.map(d=>Number(d.day)), ys=rows.map(d=>Number(d[metric])); const maxX=Math.max(...xs,1); let minY=Math.min(...ys), maxY=Math.max(...ys); if(minY===maxY){minY-=1; maxY+=1;} const point=(x,y)=>[l+x/maxX*pw,t+(1-(y-minY)/(maxY-minY))*ph]; const pts=rows.map(d=>point(Number(d.day),Number(d[metric])).map(v=>v.toFixed(1)).join(',')).join(' '); svg.innerHTML=`<line class="axis" x1="${l}" y1="${t}" x2="${l}" y2="${t+ph}"/><line class="axis" x1="${l}" y1="${t+ph}" x2="${l+pw}" y2="${t+ph}"/><line class="grid" x1="${l}" y1="${t}" x2="${l+pw}" y2="${t}"/><line class="grid" x1="${l}" y1="${t+ph/2}" x2="${l+pw}" y2="${t+ph/2}"/><polyline class="line" points="${pts}"/><text x="8" y="${t+4}" font-size="12" fill="#526173">${maxY.toFixed(1)}</text><text x="8" y="${t+ph+4}" font-size="12" fill="#526173">${minY.toFixed(1)}</text><text x="${l}" y="${h-8}" font-size="12" fill="#526173">day 0</text><text x="${l+pw-54}" y="${h-8}" font-size="12" fill="#526173">day ${maxX}</text>`;}
function drawBandChart(rows){const metric=$('bandMetricSelect').value, svg=$('bandChart'); const w=900,h=280,l=48,r=18,t=18,b=34,pw=w-l-r,ph=h-t-b; if(!rows||!rows.length){svg.innerHTML='';return;} const lo=`${metric}_p05`, mid=`${metric}_p50`, hi=`${metric}_p95`; const xs=rows.map(d=>Number(d.day)), lows=rows.map(d=>Number(d[lo])), mids=rows.map(d=>Number(d[mid])), highs=rows.map(d=>Number(d[hi])); const maxX=Math.max(...xs,1); let minY=Math.min(...lows.filter(Number.isFinite),...mids.filter(Number.isFinite)), maxY=Math.max(...highs.filter(Number.isFinite),...mids.filter(Number.isFinite)); if(!Number.isFinite(minY)||!Number.isFinite(maxY)){svg.innerHTML='';return;} if(minY===maxY){minY-=1; maxY+=1;} const point=(x,y)=>[l+x/maxX*pw,t+(1-(y-minY)/(maxY-minY))*ph]; const upper=rows.map(d=>point(Number(d.day),Number(d[hi])).map(v=>v.toFixed(1)).join(',')).join(' '); const lower=[...rows].reverse().map(d=>point(Number(d.day),Number(d[lo])).map(v=>v.toFixed(1)).join(',')).join(' '); const median=rows.map(d=>point(Number(d.day),Number(d[mid])).map(v=>v.toFixed(1)).join(',')).join(' '); svg.innerHTML=`<line class="axis" x1="${l}" y1="${t}" x2="${l}" y2="${t+ph}"/><line class="axis" x1="${l}" y1="${t+ph}" x2="${l+pw}" y2="${t+ph}"/><polygon points="${upper} ${lower}" fill="#0f766e" opacity=".18"/><polyline class="line" points="${median}"/><text x="8" y="${t+4}" font-size="12" fill="#526173">${maxY.toFixed(1)}</text><text x="8" y="${t+ph+4}" font-size="12" fill="#526173">${minY.toFixed(1)}</text><text x="${l}" y="${h-8}" font-size="12" fill="#526173">day 0</text><text x="${l+pw-54}" y="${h-8}" font-size="12" fill="#526173">day ${maxX}</text>`;}
function hexToRgb(hex){const m=hex.replace('#',''); return [parseInt(m.slice(0,2),16),parseInt(m.slice(2,4),16),parseInt(m.slice(4,6),16)];}
function mixHex(a,b,t){const ar=hexToRgb(a), br=hexToRgb(b), p=clamp(t,0,1); const out=ar.map((v,i)=>Math.round(v+(br[i]-v)*p)); return `rgb(${out[0]},${out[1]},${out[2]})`;}
function cellColor(cell, metric, cells){
  if(metric==='habitat_type') return habitatColors[String(cell.habitat_type || 'cell')] || habitatColors.cell;
  const raw = Number(cell[metric] ?? 0);
  let t = 0;
  if(metric==='csi') t = clamp(raw,0,1);
  else if(metric==='depth_m') t = clamp(raw / 1.3,0,1);
  else if(metric==='velocity_ms') t = clamp(raw / 1.3,0,1);
  else if(metric==='total_fish_use') {const maxUse=Math.max(1,...cells.map(c=>Number(c.total_fish_use||0))); t=clamp(raw/maxUse,0,1);}
  if(metric==='velocity_ms') return mixHex('#d7f0ff','#e36c42',t);
  if(metric==='total_fish_use') return mixHex('#f4e9b5','#0f766e',t);
  return mixHex('#e8f6ec','#2563eb',t);
}
function renderRiverLegend(view, metric){
  const cells=Array.isArray(view?.cells)?view.cells:[];
  const fish=Array.isArray(view?.fish)?view.fish:[];
  const redds=Array.isArray(view?.redds)?view.redds:[];
  const riverGeometry=view?.river?.geometry || {};
  const showDead=$('showDeadFish')?.checked;
  const liveFishVisible=mapState.showFish && fish.some(f=>f.alive);
  const deadFishVisible=mapState.showFish && showDead && fish.some(f=>!f.alive);
  const reddsVisible=mapState.showRedds && redds.length;
  if(!cells.length){
    const rows=[
      mapState.showBoundary && Array.isArray(riverGeometry.channel_polygon_m) && riverGeometry.channel_polygon_m.length>=3 ? '<div class="legend-row"><span class="legend-swatch" style="background:#9fd3e7"></span>River boundary</div>' : '',
      mapState.showCenterline && Array.isArray(riverGeometry.centerline_m) && riverGeometry.centerline_m.length>=2 ? '<div class="legend-row"><span class="legend-swatch" style="background:#2563eb"></span>Centerline</div>' : '',
      liveFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#f59e0b"></span>Preview fish</div>' : '',
      deadFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#6b7280"></span>Dead fish</div>' : '',
      reddsVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#dc6b19"></span>Redd</div>' : '',
    ].join('');
    $('riverLegend').innerHTML=`<strong>Layers</strong>${rows || '<div class="legend-row">No visible layers</div>'}`;
    return;
  }
  if(metric==='habitat_type'){
    const rows=Object.entries(habitatColors).slice(0,8).map(([name,color])=>`<div class="legend-row"><span class="legend-swatch" style="background:${color}"></span>${esc(name)}</div>`).join('');
    $('riverLegend').innerHTML=`<strong>Habitat</strong>${rows}`;
    return;
  }
  const label={csi:'CSI low to high',depth_m:'Depth shallow to deep',velocity_ms:'Velocity slow to fast',total_fish_use:'Fish use low to high'}[metric] || metric;
  const overlayRows=[
    liveFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#f59e0b"></span>Live fish</div>' : '',
    deadFishVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#6b7280"></span>Dead fish</div>' : '',
    reddsVisible ? '<div class="legend-row"><span class="legend-swatch" style="background:#dc6b19"></span>Redd</div>' : '',
  ].join('');
  $('riverLegend').innerHTML=`<strong>${esc(label)}</strong><div class="legend-row"><span class="legend-swatch" style="background:#e8f6ec"></span>Low</div><div class="legend-row"><span class="legend-swatch" style="background:#2563eb"></span>High</div>${overlayRows}`;
}
function svgPoints(points,sx,sy){return (points||[]).map(p=>`${sx(Number(p[0])).toFixed(1)},${sy(Number(p[1])).toFixed(1)}`).join(' ');}
function previewBounds(river,cells){
  const geometry=river?.geometry || {}; const points=[];
  ['centerline_m','channel_polygon_m'].forEach(key=>{if(Array.isArray(geometry[key])) geometry[key].forEach(point=>points.push(point));});
  (cells||[]).forEach(cell=>{if(Array.isArray(cell.polygon_m)) cell.polygon_m.forEach(point=>points.push(point)); else points.push([cell.center_x_m || 0, cell.center_y_m || 0]);});
  const valid=points.map(point=>[Number(point[0]),Number(point[1])]).filter(point=>Number.isFinite(point[0])&&Number.isFinite(point[1]));
  if(!valid.length) return {min_x:0,max_x:1,min_y:0,max_y:1};
  const xs=valid.map(point=>point[0]), ys=valid.map(point=>point[1]); const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys); const pad=Math.max(Math.max(maxX-minX,maxY-minY)*0.04,12);
  return {min_x:minX-pad,max_x:maxX+pad,min_y:minY-pad,max_y:maxY+pad};
}
function seededUnit(index,salt){let v=(index*1103515245+salt*12345+0x9e3779b9)>>>0; v^=v<<13; v^=v>>>17; v^=v<<5; return ((v>>>0)%1000000)/1000000;}
function pointInPolygon(x,y,polygon){
  let inside=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
    const xi=Number(polygon[i][0]), yi=Number(polygon[i][1]), xj=Number(polygon[j][0]), yj=Number(polygon[j][1]);
    const intersect=((yi>y)!==(yj>y)) && (x < (xj-xi)*(y-yi)/(yj-yi+1e-12)+xi);
    if(intersect) inside=!inside;
  }
  return inside;
}
function previewFish(river){
  const polygon=river?.geometry?.channel_polygon_m;
  if(!Array.isArray(polygon) || polygon.length<3) return [];
  const xs=polygon.map(p=>Number(p[0])).filter(Number.isFinite), ys=polygon.map(p=>Number(p[1])).filter(Number.isFinite);
  if(!xs.length || !ys.length) return [];
  const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
  const target=Math.min(Math.max(Number(state.config?.initial_abundance || 0),0),80);
  const fish=[];
  for(let attempt=0; fish.length<target && attempt<target*120+400; attempt++){
    const x=minX+seededUnit(attempt,17)*(maxX-minX);
    const y=minY+seededUnit(attempt,29)*(maxY-minY);
    if(!pointInPolygon(x,y,polygon)) continue;
    fish.push({fish_id:`preview-${fish.length+1}`,species:state.config?.species || 'fish',age_days:0,length_mm:Number(state.config?.initial_length_mm || 100),x_m:x,y_m:y,cell_id:'boundary-preview',alive:true,display_size:3.2});
  }
  return fish;
}
function riverViewSignature(view){
  const b=view?.bounds || {};
  const g=view?.geometry || {};
  return [b.min_x,b.max_x,b.min_y,b.max_y,(g.channel_polygon_m||[]).length,(g.centerline_m||[]).length,(view?.cells||[]).length,(view?.fish||[]).length,!!view?.fish_preview].join('|');
}
function syncLayerState(){
  ['showBoundary','showCenterline','showCells','showFish','showRedds'].forEach(id=>{const el=$(id); if(el) mapState[id]=el.checked;});
}
function resetMapView(){
  mapState.zoom=1;
  mapState.panX=0;
  mapState.panY=0;
  mapState.signature='';
}
function rerenderRiverView(){
  if(lastRiverViewPayload) drawRiverView(lastRiverViewPayload);
}
function zoomMap(multiplier){
  mapState.zoom=clamp(mapState.zoom*multiplier,0.4,8);
  rerenderRiverView();
}
function niceScaleLength(raw){
  if(!Number.isFinite(raw) || raw<=0) return 1;
  const power=Math.pow(10,Math.floor(Math.log10(raw)));
  const scaled=raw/power;
  const base=scaled>=5?5:scaled>=2?2:1;
  return base*power;
}
function renderQualityStrip(view){
  const geometry=view?.geometry || {};
  const quality=geometry.boundary_quality || {};
  const status=quality.status || 'missing';
  const statusClass=status==='usable'?'good':status==='coarse'?'warn':status==='invalid'?'bad':'';
  const cells=Array.isArray(view?.cells)?view.cells.length:0;
  const fishMode=view?.fish_preview?'preview fish':(Array.isArray(view?.fish)&&view.fish.length?'IBM fish':'no fish');
  const items=[
    {label:`Boundary ${status}`, cls:statusClass},
    {label:`CRS ${geometry.crs || '-'}`, cls:''},
    {label:`Vertices ${quality.boundary_vertices || 0}`, cls:''},
    {label:`Cells ${cells}`, cls:cells?'good':'warn'},
    {label:fishMode, cls:view?.fish_preview?'warn':fishMode==='IBM fish'?'good':''}
  ];
  $('qualityStrip').innerHTML=items.map(item=>`<span class="quality-pill ${item.cls}">${esc(item.label)}</span>`).join('');
}
function renderGisPreview(){
  const river=state.river || {}; const cells=state.cells || [];
  const fish=cells.length?[]:previewFish(river);
  const payload={river_view:{river,cells,fish,redds:[],geometry:river.geometry || {},bounds:previewBounds(river,cells),fish_preview:!cells.length && fish.length>0}};
  drawRiverView(payload);
}
function drawRiverView(result){
  const svg=$('riverView'); const view=result?.river_view;
  lastRiverViewPayload=result;
  syncLayerState();
  if(!view){svg.innerHTML=''; $('riverMeta').innerHTML=''; $('qualityStrip').innerHTML=''; return;}
  const cells=Array.isArray(view.cells)?[...view.cells].sort((a,b)=>Number(a.station_m)-Number(b.station_m)):[];
  const geometry=view.geometry || {}; const centerline=Array.isArray(geometry.centerline_m)?geometry.centerline_m:[]; const channel=Array.isArray(geometry.channel_polygon_m)?geometry.channel_polygon_m:[];
  if(!cells.length && centerline.length<2 && channel.length<3){svg.innerHTML=''; $('riverMeta').innerHTML=''; $('qualityStrip').innerHTML=''; return;}
  const signature=riverViewSignature(view);
  if(signature!==mapState.signature){mapState.signature=signature; mapState.zoom=1; mapState.panX=0; mapState.panY=0;}
  renderQualityStrip(view);
  const w=900,h=360,pad=42, bounds=view.bounds || {}; const minX=Number(bounds.min_x ?? 0), maxX=Number(bounds.max_x ?? 1), minY=Number(bounds.min_y ?? 0), maxY=Number(bounds.max_y ?? 1); const spanX=Math.max(maxX-minX,1), spanY=Math.max(maxY-minY,1);
  const scale=Math.min((w-pad*2)/spanX,(h-pad*2)/spanY);
  const drawW=spanX*scale, drawH=spanY*scale, offsetX=(w-drawW)/2, offsetY=(h-drawH)/2;
  mapState.transform={minX,maxY,scale,offsetX,offsetY};
  const sx=x=>offsetX+(Number(x)-minX)*scale; const sy=y=>offsetY+(maxY-Number(y))*scale;
  const metric=$('cellColorMetric').value;
  let water='';
  if(mapState.showBoundary && channel.length>=3){
    water=`<polygon class="bank-shape" points="${svgPoints(channel,sx,sy)}"><title>${esc(geometry.source || 'river channel geometry')}</title></polygon>`;
  }
  const centerlineShape=mapState.showCenterline&&centerline.length>=2?`<polyline class="${channel.length>=3?'centerline-shape':'centerline-only'}" points="${svgPoints(centerline,sx,sy)}"><title>${channel.length>=3?'flow centerline':'GIS centerline only; no channel polygon imported'}</title></polyline>`:'';
  const showCellLabels=cells.length<=180;
  const cellShapes=mapState.showCells?cells.map(cell=>{const fill=cellColor(cell,metric,cells); const polygon=Array.isArray(cell.polygon_m)?cell.polygon_m:[]; const title=`${esc(cell.cell_id)} | ${esc(cell.habitat_type)} | CSI ${fmt(cell.csi,2)} | depth ${fmt(cell.depth_m,2)} m | velocity ${fmt(cell.velocity_ms,2)} m/s | fish-use ${esc(cell.total_fish_use)}`; if(polygon.length>=3){const label=showCellLabels?`<text class="cell-label" x="${sx(cell.center_x_m).toFixed(1)}" y="${(sy(cell.center_y_m)+3).toFixed(1)}" text-anchor="middle">${esc(cell.cell_id)}</text>`:''; return `<g><polygon class="cell-shape" points="${svgPoints(polygon,sx,sy)}" fill="${fill}" opacity=".78"><title>${title}</title></polygon>${label}</g>`;} const x1=sx(Number(cell.center_x_m)-Number(cell.length_m)/2), x2=sx(Number(cell.center_x_m)+Number(cell.length_m)/2), y1=sy(Number(cell.center_y_m)-Number(cell.width_m)/2), y2=sy(Number(cell.center_y_m)+Number(cell.width_m)/2); const x=Math.min(x1,x2), y=Math.min(y1,y2), cw=Math.max(Math.abs(x2-x1),22), ch=Math.max(Math.abs(y2-y1),12); const label=showCellLabels?`<text class="cell-label" x="${(x+cw/2).toFixed(1)}" y="${(y+ch/2+3).toFixed(1)}" text-anchor="middle">${esc(cell.cell_id)}</text>`:''; return `<g><rect class="cell-shape" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${cw.toFixed(1)}" height="${ch.toFixed(1)}" rx="7" fill="${fill}" opacity=".78"><title>${title}</title></rect>${label}</g>`;}).join(''):'';
  const showDead=$('showDeadFish').checked; const fish=mapState.showFish?(view.fish||[]).filter(f=>showDead || f.alive):[];
  const fishShapes=fish.map(f=>{const x=sx(f.x_m), y=sy(f.y_m), s=Number(f.display_size || 3)/3.1, fill=f.alive?'#f59e0b':'#6b7280', stroke=f.alive?'#1d4ed8':'#374151'; return `<g transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${s.toFixed(2)})"><title>fish ${esc(f.fish_id)} | ${esc(f.cell_id)} | ${fmt(f.length_mm,1)} mm | ${f.alive?'alive':'dead'}</title><path class="fish-shape" d="M-2.6 0 C-1.2 -1.45 1.35 -1.45 2.75 0 C1.35 1.45 -1.2 1.45 -2.6 0 Z" fill="${fill}" stroke="${stroke}"/><path d="M-2.45 0 L-4.0 -1.25 L-4.0 1.25 Z" fill="${fill}" stroke="${stroke}" stroke-width=".35"/><circle cx="1.5" cy="-.32" r=".22" fill="#102030"/></g>`;}).join('');
  const reddShapes=mapState.showRedds?(view.redds||[]).map(r=>{const x=sx(r.x_m), y=sy(r.y_m), s=Number(r.display_size || 5); return `<g><title>redd ${esc(r.redd_id)} | ${esc(r.cell_id)} | eggs ${esc(r.eggs_remaining)}</title><path class="redd-shape" d="M ${x.toFixed(1)} ${(y-s).toFixed(1)} L ${(x+s).toFixed(1)} ${y.toFixed(1)} L ${x.toFixed(1)} ${(y+s).toFixed(1)} L ${(x-s).toFixed(1)} ${y.toFixed(1)} Z" opacity="${r.active ? '.92' : '.42'}"/></g>`;}).join(''):'';
  const arrow=`<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#1f5f78"/></marker></defs><line x1="${w-160}" y1="34" x2="${w-72}" y2="34" stroke="#1f5f78" stroke-width="3" marker-end="url(#arrow)"/><text x="${w-158}" y="24" fill="#1f5f78" font-size="12">flow</text>`;
  const metersPerPx=1/(scale*mapState.zoom);
  const scaleMeters=niceScaleLength(110*metersPerPx);
  const scalePx=scaleMeters/metersPerPx;
  const scaleLabel=scaleMeters>=1000?`${fmt(scaleMeters/1000,1)} km`:`${fmt(scaleMeters,0)} m`;
  const scaleBar=`<g><line x1="28" y1="${h-28}" x2="${(28+scalePx).toFixed(1)}" y2="${h-28}" stroke="#1f5f78" stroke-width="3"/><line x1="28" y1="${h-33}" x2="28" y2="${h-23}" stroke="#1f5f78" stroke-width="2"/><line x1="${(28+scalePx).toFixed(1)}" y1="${h-33}" x2="${(28+scalePx).toFixed(1)}" y2="${h-23}" stroke="#1f5f78" stroke-width="2"/><text x="28" y="${h-36}" fill="#1f5f78" font-size="12">${scaleLabel}</text></g>`;
  const previewBadge=view.fish_preview?`<g><rect class="preview-badge" x="28" y="24" width="186" height="24" rx="5"/><text x="38" y="40" fill="#fff7ed" font-size="12" font-weight="700">Preview fish, not IBM output</text></g>`:'';
  const transform=`translate(${mapState.panX.toFixed(1)} ${mapState.panY.toFixed(1)}) scale(${mapState.zoom.toFixed(3)})`;
  svg.innerHTML=`<rect x="0" y="0" width="${w}" height="${h}" fill="#f4f8f6"/><g id="mapContent" transform="${transform}">${water}${centerlineShape}${cellShapes}${reddShapes}${fishShapes}</g>${arrow}${scaleBar}${previewBadge}`;
  const river=view.river || {}; const alive=fish.filter(f=>f.alive).length; const dead=fish.length-alive; const reddCount=mapState.showRedds?(view.redds||[]).length:0;
  $('riverTitle').textContent=`${river.name || 'River'} / ${river.reach_name || 'Reach'}`;
  const shapeLabel=channel.length>=3?'channel polygon':(centerline.length>=2?'centerline only':'no river geometry');
  const quality=geometry.boundary_quality || {};
  const vertexLabel=Number(quality.boundary_vertices || 0)>0?` · ${Number(quality.boundary_vertices)} boundary vertices`:'';
  const qualityLabel=quality.status?` · ${esc(quality.status)}`:'';
  const geometryLabel=centerline.length||channel.length?`${esc(geometry.source || 'payload geometry')} · ${esc(geometry.crs || 'local_m')} · ${shapeLabel}${vertexLabel}${qualityLabel}`:'no river boundary loaded; habitat cells only';
  const warning=quality.status==='coarse'||quality.status==='invalid'?`<div class="river-warning">Boundary quality: ${esc(quality.status)}. Do not treat this view as surveyed bank-line evidence.</div>`:'';
  const fishLayer=view.fish_preview?'<div>Fish layer: preview only inside boundary; import habitat cells for IBM positions.</div>':'';
  const note=river.display_note?`<div>Note: ${esc(river.display_note)}</div>`:'';
  $('riverMeta').innerHTML=`<strong>${esc(river.name || 'River')}</strong><div>${esc(river.reach_name || '')}</div><div>Geometry: ${geometryLabel}</div>${warning}<div>Length: ${fmt(river.length_m,0)} m</div><div>Flow: ${fmt(river.flow_m3s,1)} m3/s</div><div>Cells: ${cells.length}</div><div>Fish visible: ${fish.length} (${alive} alive, ${dead} dead)</div>${fishLayer}<div>Redds: ${reddCount}</div>${note}`;
  renderRiverLegend(view, metric);
}
function updateMapCoordinates(event){
  const tr=mapState.transform;
  if(!tr){$('mapCoords').textContent='x -, y -'; return;}
  const rect=$('riverView').getBoundingClientRect();
  const px=(event.clientX-rect.left)*(900/rect.width);
  const py=(event.clientY-rect.top)*(360/rect.height);
  const baseX=(px-mapState.panX)/mapState.zoom;
  const baseY=(py-mapState.panY)/mapState.zoom;
  const x=tr.minX+(baseX-tr.offsetX)/tr.scale;
  const y=tr.maxY-(baseY-tr.offsetY)/tr.scale;
  if(Number.isFinite(x)&&Number.isFinite(y)) $('mapCoords').textContent=`x ${fmt(x,1)} m, y ${fmt(y,1)} m`;
}
function inspectFeature(event){
  if(!mapState.inspect) return;
  const holder=event.target.closest('g, polygon, polyline, rect, path');
  const title=holder?.querySelector?.('title')?.textContent || event.target.querySelector?.('title')?.textContent || '';
  if(title) setStatus(`Inspect: ${title}`);
}
function setInspectMode(enabled){
  mapState.inspect=enabled;
  $('inspectMapBtn').classList.toggle('active',enabled);
  $('riverView').style.cursor=enabled?'crosshair':'grab';
}
function toggleFullscreen(){
  const card=$('riverCard');
  card.classList.toggle('fullscreen');
  const enabled=card.classList.contains('fullscreen');
  document.body.classList.toggle('map-fullscreen-open',enabled);
  $('fullMapBtn').classList.toggle('active',enabled);
  $('fullMapBtn').textContent=enabled?'Exit':'Full';
  setTimeout(rerenderRiverView,0);
}
function cellValue(c,v){if(c==='status') return `<span class="status-pill ${esc(v)}">${esc(v)}</span>`; return esc(v);}
function table(id,rows,columns){if(!rows||!rows.length){$(id).innerHTML='<tbody><tr><td>No rows</td></tr></tbody>';return;} const cols=columns||Object.keys(rows[0]).slice(0,12); const body=rows.map(row=>`<tr>${cols.map(c=>`<td>${cellValue(c,row[c])}</td>`).join('')}</tr>`).join(''); $(id).innerHTML=`<thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${body}</tbody>`;}
function renderPaths(paths){$('paths').innerHTML=Object.entries(paths||{}).map(([name,path])=>`<li><strong>${esc(name)}</strong>: ${esc(path)}</li>`).join('');}
function addHistory(result){if(!result?.metrics) return; runHistory.unshift({run_id:result.run_id,final_abundance:result.metrics.final_abundance,biomass_g:fmt(result.metrics.final_biomass_g,1),mean_length_mm:fmt(result.metrics.final_mean_length_mm,1),survival:fmt(result.metrics.survival_rate,3),run_dir:result.run_dir}); runHistory=runHistory.slice(0,12); table('historyTable',runHistory,['run_id','final_abundance','biomass_g','mean_length_mm','survival']);}
function renderValidation(result){table('validationTable',result.checks||[],['area','status','message','detail']);}
function renderEnsemble(result){lastEnsemble=result; table('ensembleTable',result.summary||[],['run_index','seed','parameter_index','final_abundance','final_biomass_g','final_mean_length_mm']); table('sensitivityTable',result.sensitivity||[],['parameter','target','pearson_r','abs_pearson_r','n']); drawBandChart(result.daily_bands||[]); renderPaths(result.paths); log(`Ensemble ${result.run_id}: ${result.metrics.n_runs} runs`); setStatus(`Ensemble complete: ${result.run_dir}`);}
function renderCalibration(result){const params=Object.entries(result.best_parameters||{}).map(([k,v])=>`${esc(k)}=${fmt(v,4)}`).join(', '); $('bestParams').innerHTML=params?`Best: ${params} · score ${fmt(result.metrics.best_score,3)}`:''; table('calibrationTable',result.summary||[],['candidate_id','score','accepted','final_abundance','param_base_daily_survival','param_predation_base_risk']); renderPaths(result.paths); log(`Calibration ${result.run_id}: score ${fmt(result.metrics.best_score,3)}`); setStatus(`Calibration complete: ${result.run_dir}`);}
function renderResult(result){lastResult=result; renderKpis(result.metrics); drawRiverView(result); drawChart(result.population_summary); addHistory(result); table('cellUseTable',result.cell_use_summary,['cell_id','total_fish_use','mean_growth_mm','mean_mortality_risk']); table('eventsTable',result.events,['day','event','n','n_eggs']); table('fishTable',result.final_individuals,['fish_id','species','age_days','length_mm','mass_g','cell_id','alive','reach_id']); table('reddsTable',result.redds,['redd_id','day','reach_id','cell_id','eggs_remaining','degree_days','active']); renderPaths(result.paths);}
async function runModel(){setBusy(true); try{const result=await api('/api/run',collectState()); renderResult(result); log(`Run ${result.run_id}: final abundance ${result.metrics.final_abundance}`); setStatus(`Run complete: ${result.run_dir}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function validateModel(){setBusy(true); try{const result=await api('/api/validate',collectState()); renderValidation(result); renderPaths(result.paths); log(`Validation ${result.run_id}: ${result.metrics.errors} errors, ${result.metrics.warnings} warnings`); setStatus(result.ok?`Validation passed: ${result.run_dir}`:`Validation needs attention: ${result.run_dir}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function runEnsemble(){setBusy(true); try{const result=await api('/api/ensemble',collectState()); renderEnsemble(result);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function runCalibration(){setBusy(true); try{const result=await api('/api/calibrate',collectState()); renderCalibration(result);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function importGIS(){setBusy(true); try{collectState(); const result=await api('/api/gis/import',{...state.gis,river_name:state.river.name,reach_name:state.river.reach_name,flow_m3s:state.river.flow_m3s,reach_id:state.config.reach_id}); state.river={...state.river,...result.river}; state.cells=Array.isArray(result.cells)?result.cells:[]; bindState(); renderAll(); const msg=(result.messages||[]).join(' '); log(`GIS import: ${result.metrics.centerline_points} centerline points, ${result.metrics.channel_polygon_points} channel points, ${result.metrics.cell_features} cells, boundary ${result.metrics.boundary_quality}/${result.metrics.boundary_vertices} vertices${msg?` · ${msg}`:''}`); if(!state.cells.length){renderGisPreview(); setStatus(`GIS imported: ${result.metrics.target_crs} · boundary ${result.metrics.boundary_quality} · no habitat cells`); return;} const run=await api('/api/run',collectState()); renderResult(run); setStatus(`GIS imported: ${result.metrics.target_crs} · boundary ${result.metrics.boundary_quality}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
function setBusy(busy){['runBtn','validateBtn','stepBtn','ensembleBtn','calibrateBtn','gisImportBtn','benchBtn','compareBtn'].forEach(id=>$(id).disabled=busy);}
async function runBenchmark(){setBusy(true); try{const result=await api('/api/instream7/benchmark',collectState().instream); renderOfficialBenchmark(result); renderPaths(result.paths); log(`Official acceptance ${result.run_id}: ${result.metrics.suite} final abundance ${result.metrics.final_abundance}`); setStatus(`Official acceptance complete: ${result.run_dir}`); $('officialResult').scrollIntoView({block:'start',behavior:'smooth'});}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
async function runCompare(){setBusy(true); try{const result=await api('/api/instream7/compare',collectState().instream); table('compareTable',result.comparison); renderPaths(result.paths); log(`Compare ${result.run_id}: ${result.metrics.outside_tolerance} outside tolerance`); setStatus(`Comparison complete: ${result.run_dir}`);}catch(err){log(err.message); setStatus(err.message);}finally{setBusy(false);}}
$('runBtn').addEventListener('click',runModel);
$('validateBtn').addEventListener('click',validateModel);
$('stepBtn').addEventListener('click',()=>{collectState(); $('days').value=Number(state.config.days)+1; runModel();});
$('resetBtn').addEventListener('click',loadDefault);
$('addCellBtn').addEventListener('click',()=>{collectState(); const maxStation=Math.max(0,...state.cells.map(c=>Number(c.station_m||0))); const station=maxStation+42; state.cells.push({cell_id:`cell-${state.cells.length+1}`,habitat_type:'run',station_m:station,center_x_m:station,center_y_m:52,length_m:40,width_m:10,reach_id:state.config.reach_id,reach_order:1,area_m2:400,depth_m:.5,velocity_ms:.3,csi:.6,temperature_c:12,turbidity_ntu:0,hiding_cover:.2,feeding_cover:.2,spawning_cover:.2}); renderCells();});
$('exportBtn').addEventListener('click',()=>{const blob=new Blob([JSON.stringify(collectState(),null,2)],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='openlimno-ibm-scenario.json'; a.click(); URL.revokeObjectURL(a.href);});
$('importBtn').addEventListener('click',()=>$('importFile').click());
$('importFile').addEventListener('change',async event=>{const file=event.target.files[0]; if(!file) return; state=JSON.parse(await file.text()); bindState(); renderAll();});
$('ensembleBtn').addEventListener('click',runEnsemble);
$('calibrateBtn').addEventListener('click',runCalibration);
$('gisImportBtn').addEventListener('click',importGIS);
$('benchBtn').addEventListener('click',runBenchmark);
$('compareBtn').addEventListener('click',runCompare);
$('zoomInBtn').addEventListener('click',()=>zoomMap(1.25));
$('zoomOutBtn').addEventListener('click',()=>zoomMap(0.8));
$('fitMapBtn').addEventListener('click',()=>{resetMapView(); rerenderRiverView();});
$('inspectMapBtn').addEventListener('click',()=>setInspectMode(!mapState.inspect));
$('fullMapBtn').addEventListener('click',toggleFullscreen);
['showBoundary','showCenterline','showCells','showFish','showRedds'].forEach(id=>$(id).addEventListener('change',rerenderRiverView));
['gis_boundary_path','gis_boundary_layer','gis_centerline_path','gis_centerline_layer','gis_cells_path','gis_cells_layer'].forEach(id=>$(id).addEventListener('input',()=>{
  if(!state) return;
  const key=id.replace('gis_','');
  state.gis[key]=$(id).value;
  renderGisGuidance();
}));
$('riverView').addEventListener('mousemove',event=>{
  updateMapCoordinates(event);
  if(dragStart && !mapState.inspect){
    mapState.panX=dragStart.panX+(event.clientX-dragStart.x)*(900/$('riverView').getBoundingClientRect().width);
    mapState.panY=dragStart.panY+(event.clientY-dragStart.y)*(360/$('riverView').getBoundingClientRect().height);
    rerenderRiverView();
  }
});
$('riverView').addEventListener('mousedown',event=>{if(!mapState.inspect) dragStart={x:event.clientX,y:event.clientY,panX:mapState.panX,panY:mapState.panY};});
window.addEventListener('mouseup',()=>{dragStart=null;});
$('riverView').addEventListener('mouseleave',()=>{$('mapCoords').textContent='x -, y -';});
$('riverView').addEventListener('click',inspectFeature);
$('riverView').addEventListener('wheel',event=>{event.preventDefault(); zoomMap(event.deltaY<0?1.12:0.9);},{passive:false});
$('metricSelect').addEventListener('change',()=>{if(lastResult) drawChart(lastResult.population_summary);});
$('bandMetricSelect').addEventListener('change',()=>{if(lastEnsemble) drawBandChart(lastEnsemble.daily_bands);});
$('cellColorMetric').addEventListener('change',rerenderRiverView);
$('showDeadFish').addEventListener('change',rerenderRiverView);
loadDefault();
</script>
</body>
</html>
"""

__all__ = [
    "compare_instream7_for_studio",
    "default_studio_scenario",
    "run_ibm_studio",
    "run_instream7_benchmark_for_studio",
    "run_studio_calibration",
    "run_studio_ensemble",
    "run_studio_scenario",
    "validate_studio_payload",
    "write_studio_scenario_files",
]
