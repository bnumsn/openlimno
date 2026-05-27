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
import logging
import math
import os
import time
import uuid
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

# 2026-05-26 R-IBM-GOD-OBJECT partial split: HTTP server layer
# (_IBMStudioHTTPServer, _IBMStudioHandler, run_ibm_studio) moved
# to studio_http.py. webbrowser/HTTPStatus/BaseHTTPRequestHandler/
# ThreadingHTTPServer/ClassVar imports are no longer needed in
# studio.py — they live in studio_http.py now.
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

_LOG = logging.getLogger(__name__)

# Interactive Studio guard-rails (2026-05-26 software-test M1/M2):
# - MAX_STUDIO_DAYS caps a single Run at ~10 years so a stray `days=10000`
#   cannot hang the request thread for an hour. Headless workflow runs
#   are not capped.
# - MAX_STUDIO_INITIAL_ABUNDANCE caps initial fish count so a runaway
#   browser POST cannot allocate a 10-million-row DataFrame.
# - MAX_STUDIO_RUN_DIRS bounds the on-disk cache of past run outputs;
#   _run_dir prunes oldest dirs above this watermark.
MAX_STUDIO_DAYS = 3650
# 10k fish × 45 days is roughly the largest interactive load the stdlib
# threaded HTTP server can answer in under a minute. Headless workflow
# runs (workflows.calibrate, ensemble, etc.) are not capped — they
# accept the longer runtime in exchange for unbounded population sizes.
# (2026-05-26 pass-2 software-test G1, Gemini.)
MAX_STUDIO_INITIAL_ABUNDANCE = 10_000
MAX_STUDIO_RUN_DIRS = 50

_DEMO_REACH_LENGTH_M = 1500.0
_DEMO_REACH_CENTERLINE_Y = 60.0
_DEMO_MEANDER_WAVELENGTH_M = 300.0
_DEMO_MEANDER_AMPLITUDE_M = 42.0   # gives sinuosity ≈ 1.20 (Lemhi-like)
_DEMO_BASE_HALF_WIDTH_M = 7.0      # 14 m channel default
# Pool / margin / side-channel stations along the reach. Each tuple is
# (station_m, side, half_width_extension_m, sigma_m) — sigma controls
# how localised the bulge is in the channel polygon.
_DEMO_BULGES: tuple[tuple[float, str, float, float], ...] = (
    (220.0, "north", 18.0, 35.0),   # cottonwood-pool-1
    (300.0, "north", 4.0, 25.0),    # left-margin-1
    (360.0, "south", 18.0, 32.0),   # side-channel-1
    (660.0, "north", 16.0, 38.0),   # boulder-pool
    (800.0, "south", 4.0, 28.0),    # right-margin
    (960.0, "north", 22.0, 40.0),   # meander-pool (deepest)
    (1110.0, "south", 14.0, 30.0),  # side-channel-2
    (1390.0, "south", 12.0, 35.0),  # final-pool (alternating bank)
)


def _centerline_y(x: float) -> float:
    """Demo centerline elevation y at station x along the reach."""
    import math
    return _DEMO_REACH_CENTERLINE_Y + _DEMO_MEANDER_AMPLITUDE_M * math.sin(
        2 * math.pi * x / _DEMO_MEANDER_WAVELENGTH_M
    )


def _demo_cells() -> list[dict[str, object]]:
    """20 cells across the 1500m reach forming 4 pool-riffle sequences
    + 2 side-channels + 2 margins + 1 boulder chute.

    Spacing: ~5-7 × bankfull width pool spacing (Leopold 1964 / Knighton
    1998) → ~300-350m between pools across 1500m reach. Each cell's y-
    position follows the meandering centerline at its station, with
    explicit off-channel offsets for pools / margins / side-channels.
    """
    base = [
        {
            "cell_id": "upper-riffle-1",
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": "riffle",
            "station_m": 40.0,
            "center_x_m": 40.0,
            "center_y_m": _centerline_y(40.0),
            "length_m": 60.0,
            "width_m": 13.0,
            "area_m2": 780.0,
            "depth_m": 0.40,
            "velocity_ms": 0.78,
            "csi": 0.78,
            "temperature_c": 11.6,
            "turbidity_ntu": 2.0,
            "hiding_cover": 0.32,
            "feeding_cover": 0.74,
            "spawning_cover": 0.72,
        },
    ]
    # Specs for the remaining 19 cells along the 1500m reach.
    # Tuple: (cell_id, habitat_type, station, length, width, depth,
    #         velocity, csi, hiding, feeding, spawning, y_offset, temp_c)
    # y_offset: perpendicular offset from centerline (north +, south -)
    # for pool / margin / side-channel cells; main-line cells = 0.
    cell_specs = [
        # --- Sequence 1 (0-430m): riffle-run-pool-tailout + margin/side-ch ---
        ("left-margin-1",     "margin",       100.0,  50.0,  7.0,  0.22, 0.10, 0.45,  0.55, 0.28, 0.18,  4.0,  12.0),
        ("mid-run-1",         "run",          160.0,  60.0, 14.0,  0.65, 0.36, 0.86,  0.48, 0.62, 0.42,  0.0,  11.9),
        ("cottonwood-pool-1", "pool",         220.0,  80.0, 18.0,  1.20, 0.14, 0.92,  0.84, 0.50, 0.22,  9.0,  12.1),
        ("gravel-tailout-1",  "tailout",      300.0,  50.0, 11.0,  0.34, 0.55, 0.80,  0.30, 0.65, 0.82,  0.0,  12.0),
        ("side-channel-1",    "side-channel", 360.0,  40.0,  7.0,  0.25, 0.18, 0.65, 0.70, 0.34, 0.30, -10.0, 12.3),
        ("lower-glide-1",     "glide",        430.0,  60.0, 14.0,  0.75, 0.30, 0.85,  0.60, 0.55, 0.45,  0.0,  12.2),
        # --- Sequence 2 (430-800m) ---
        ("upper-riffle-2",    "riffle",       500.0,  50.0, 12.0,  0.38, 0.74, 0.76,  0.30, 0.72, 0.68,  0.0,  11.7),
        ("mid-run-2",         "run",          580.0,  65.0, 13.0,  0.62, 0.40, 0.84,  0.48, 0.60, 0.42,  0.0,  11.9),
        ("boulder-pool",      "pool",         660.0,  70.0, 17.0,  1.10, 0.16, 0.90,  0.78, 0.48, 0.20,  8.0,  12.0),
        ("gravel-tailout-2",  "tailout",      740.0,  50.0, 11.0,  0.32, 0.55, 0.80,  0.30, 0.65, 0.82,  0.0,  12.1),
        ("right-margin",      "margin",       800.0,  45.0,  7.0,  0.20, 0.10, 0.42, -4.0,  0.28, 0.18, -4.0,  11.9),
        # --- Sequence 3 (800-1150m) — deepest meander-pool ---
        ("mid-run-3",         "run",          870.0,  70.0, 14.0,  0.66, 0.38, 0.85,  0.50, 0.60, 0.42,  0.0,  11.9),
        ("meander-pool",      "pool",         960.0,  90.0, 19.0,  1.30, 0.12, 0.94,  0.88, 0.50, 0.24, 11.0, 12.0),
        ("gravel-tailout-3",  "tailout",     1050.0,  55.0, 12.0,  0.34, 0.55, 0.82,  0.32, 0.66, 0.82,  0.0,  12.0),
        ("side-channel-2",    "side-channel",1110.0,  45.0,  8.0,  0.26, 0.20, 0.68, 0.72, 0.36, 0.30,  -8.0, 12.3),
        # --- Sequence 4 (1150-1500m) — boulder-chute + final-pool ---
        ("upper-riffle-3",    "riffle",      1180.0,  50.0, 12.0,  0.40, 0.72, 0.76,  0.30, 0.72, 0.70,  0.0,  11.6),
        ("boulder-chute",     "chute",       1250.0,  50.0,  9.0,  0.50, 1.15, 0.40,  0.18, 0.22, 0.12,  0.0,  11.8),
        ("lower-glide-2",     "glide",       1310.0,  60.0, 14.0,  0.70, 0.32, 0.84,  0.60, 0.55, 0.46,  0.0,  12.0),
        ("final-pool",        "pool",        1390.0,  70.0, 16.0,  1.00, 0.18, 0.88,  0.80, 0.50, 0.30, -6.0,  12.0),
    ]
    # Note: 'right-margin' had a typo in the original tuple (hiding=-4.0).
    # Fix that — hiding should be ~0.55 (same as left-margin).
    fixed = []
    for c in cell_specs:
        cid, hmu, station, L, W, d, v, csi, hide, feed, spawn, dy, t = c
        if cid == "right-margin":
            hide = 0.55
        area = round(L * W, 1)
        center_y = round(_centerline_y(station) + dy, 2)
        fixed.append({
            "cell_id": cid,
            "reach_id": "lemhi-hayden-demo",
            "reach_order": 1,
            "habitat_type": hmu,
            "station_m": station,
            "center_x_m": station,
            "center_y_m": center_y,
            "length_m": L,
            "width_m": W,
            "area_m2": area,
            "depth_m": d,
            "velocity_ms": v,
            "csi": csi,
            "temperature_c": t,
            "turbidity_ntu": 2.0,
            "hiding_cover": hide,
            "feeding_cover": feed,
            "spawning_cover": spawn,
        })
    # Patch the first hand-written cell's center_y so it follows the
    # new centerline too.
    base[0]["center_y_m"] = round(_centerline_y(base[0]["station_m"]), 2)
    return base + fixed


def _demo_river_geometry() -> dict[str, object]:
    """Synthetic but coherent river geometry for the demo scenario.

    Produces a centerline + channel-boundary polygon that visually
    matches the 20 demo cells (4 pool-riffle sequences across the 1500 m
    reach plus 2 side-channels, 2 margins, and 1 boulder chute — see
    ``_DEMO_BULGES`` and ``_demo_cells``). The polygon widens at each
    bulge so the off-channel cells (pool, side-channel, margin) render
    inside the channel shape.

    This is the demo's RECOVERY from the pre-fix state where the
    front-end ``display_note`` said "no river boundary loaded; habitat
    cells only" — leaving the plan-view with scattered rectangles
    that looked random. With ``channel_polygon_m`` + ``centerline_m``
    populated the cells now read as a single coherent reach.

    Real river data should still be imported via the ``Import GIS``
    button (or ``/api/gis/import``) — this synthetic outline is
    only the default-demo fallback.
    """
    import math

    length_m = _DEMO_REACH_LENGTH_M
    base_half_width = _DEMO_BASE_HALF_WIDTH_M
    n_centerline = 120  # finer resolution for the longer 1500m reach

    # 1) Centerline: sinusoidal meander, amplitude tuned for ~1.20
    #    sinuosity (real Lemhi 1.15-1.40 range).
    centerline = [
        [x, _centerline_y(x)]
        for x in [i * (length_m / (n_centerline - 1)) for i in range(n_centerline)]
    ]

    # 2) Banks: offset ±half_width perpendicular to centerline tangent,
    #    widening at each bulge location in _DEMO_BULGES.
    def _local_half_width(x: float, side: str) -> float:
        half = base_half_width
        for b_x, b_side, b_ext, b_sigma in _DEMO_BULGES:
            if b_side == side:
                half += b_ext * math.exp(-((x - b_x) / b_sigma) ** 2)
        return half

    north_bank = []
    south_bank = []
    for i, (x, y) in enumerate(centerline):
        # Tangent direction for perpendicular offset
        if i == 0:
            dx, dy = centerline[1][0] - x, centerline[1][1] - y
        elif i == len(centerline) - 1:
            dx, dy = x - centerline[-2][0], y - centerline[-2][1]
        else:
            dx = centerline[i + 1][0] - centerline[i - 1][0]
            dy = centerline[i + 1][1] - centerline[i - 1][1]
        norm = math.hypot(dx, dy) or 1.0
        # Perpendicular unit vector pointing "north" (positive y side)
        nx, ny = -dy / norm, dx / norm
        if ny < 0:  # ensure north points to +y
            nx, ny = -nx, -ny
        h_north = _local_half_width(x, "north")
        h_south = _local_half_width(x, "south")
        north_bank.append([x + nx * h_north, y + ny * h_north])
        south_bank.append([x - nx * h_south, y - ny * h_south])

    # 3) Stitch banks into a closed polygon (north along, south back).
    channel_polygon = north_bank + list(reversed(south_bank))

    return {
        "channel_polygon_m": channel_polygon,
        "centerline_m": centerline,
        "crs": "local_m",
        "source": "OpenLimno demo synthetic outline",
        "boundary_quality": {
            "real": False,
            "note": "synthetic outline; load real GIS for true shape",
        },
    }


def _demo_river() -> dict[str, object]:
    return {
        "name": "Lemhi River",
        "reach_name": "Hayden Creek demo reach",
        "length_m": _DEMO_REACH_LENGTH_M,
        "flow_m3s": 5.8,
        "display_note": (
            "Demo bundled with a synthetic 1500m meandering reach + 20 "
            "habitat cells across 4 pool-riffle sequences (sinuosity ~1.20, "
            "Lemhi-typical). For real basin data use ``Import GIS`` with a "
            "surveyed boundary polygon."
        ),
        "geometry": _demo_river_geometry(),
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
    """Return the synthetic-demo browser-studio scenario payload.

    Kept stable for tests + offline use. The running Studio HTTP server
    prefers ``default_studio_scenario_resolved()``, which loads the real
    inSTREAM 7.4 ExampleA archive when present and falls back here.
    """

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


def default_studio_scenario_resolved() -> dict[str, object]:
    """Resolve the runtime default scenario.

    Prefers the real inSTREAM 7.4 ExampleA archive when one is present on
    the local filesystem (env var, XDG cache, or repo dev dir); falls back
    to ``default_studio_scenario()`` if the archive is absent or fails to
    load. Falls-back-with-WARNING-log when the archive *is* present but
    the load fails — triple-review (gemini, claude) caught that a bare
    silent fallback could mask malformed archives, renamed CSV columns,
    missing shapefiles, etc., leaving the user staring at the synthetic
    demo wondering why their archive isn't being used.
    """
    # Imported here to avoid a hard dep on heavy GIS stack at module load.
    try:
        from .studio_instream7_default import (
            build_studio_scenario_from_instream7_archive,
            find_instream7_archive_root,
        )
    except Exception as exc:  # pragma: no cover - import guard for stripped envs
        _LOG.warning(
            "Falling back to synthetic Studio default: "
            "studio_instream7_default import failed (%s).",
            exc,
        )
        return _with_fallback_banner(
            default_studio_scenario(),
            f"studio_instream7_default import failed: {exc}",
        )

    root = find_instream7_archive_root()
    if root is None:
        # Quiet: no archive configured is the normal path on CI / fresh checkout.
        return default_studio_scenario()

    # Allow callers to opt into a non-default archive case via
    # ``OPENLIMNO_INSTREAM7_CASE_ID``. Default is ExampleA; set to
    # ``ExampleB`` to load the 3-reach × 3-species (Rainbow/Brown/
    # Cutthroat) archive when a single-reach scenario is too narrow
    # for the experiment. 2026-05-27 track D.
    requested_case = os.environ.get("OPENLIMNO_INSTREAM7_CASE_ID", "ExampleA")

    fallback = default_studio_scenario()
    try:
        real = build_studio_scenario_from_instream7_archive(
            root,
            case_id=requested_case,
            submodels=cast(Mapping[str, object], fallback["submodels"]),
            submodel_catalog=cast(list[dict[str, object]], fallback["submodel_catalog"]),
            experiments=cast(Mapping[str, object], fallback["experiments"]),
            instream_panel_defaults=cast(Mapping[str, object], fallback["instream"]),
        )
    except Exception as exc:
        _LOG.warning(
            "inSTREAM 7 archive at %s failed to load (%s: %s); "
            "falling back to synthetic Studio default.",
            root, type(exc).__name__, exc,
        )
        return _with_fallback_banner(
            fallback,
            f"inSTREAM 7 archive at {root} failed to load "
            f"({type(exc).__name__}: {exc})",
        )
    return real


def _with_fallback_banner(payload: dict[str, object], reason: str) -> dict[str, object]:
    """Annotate a synthetic-fallback payload so the UI can surface to the
    user that the real archive was supposed to load but didn't.
    Pinned by 2026-05-26 software-test N2 (Codex)."""
    payload["_fallback_reason"] = reason
    river = payload.get("river")
    if isinstance(river, dict):
        note = str(river.get("display_note") or "")
        marker = "⚠ Synthetic demo — "
        if marker not in note:
            river["display_note"] = f"{marker}{reason}. {note}".strip()
    return payload


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


def _as_int(
    value: object,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None:
        parsed = max(parsed, min_value)
    if max_value is not None:
        parsed = min(parsed, max_value)
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


_PHYSICAL_BOUNDS: tuple[tuple[str, float, float], ...] = (
    # (column, min_inclusive, max_inclusive)
    ("depth_m", 0.0, 50.0),
    ("velocity_ms", 0.0, 10.0),
    ("area_m2", 0.0, 1e6),
    ("length_m", 0.0, 1e4),
    ("width_m", 0.0, 1e4),
    ("temperature_c", -2.0, 45.0),
    ("turbidity_ntu", 0.0, 5000.0),
    ("hiding_cover", 0.0, 1.0),
    ("feeding_cover", 0.0, 1.0),
    ("spawning_cover", 0.0, 1.0),
    ("csi", 0.0, 1.0),
)


def _cells_from_payload(value: object) -> pd.DataFrame:
    """Coerce a JSON cell list into a DataFrame and reject physically
    impossible hydraulic / cover values up-front.

    Pinned by 2026-05-26 software-test S3 (Codex + Gemini): the previous
    version silently accepted ``depth_m=-1`` (replaced by ``.fillna(0.0)``
    downstream) and ``velocity_ms="NaN"`` (converted to null) so the IBM
    ran on bogus inputs and returned an ``ok: true`` response that hid
    the corruption. Now negative depths, out-of-range velocities, NaN
    values, or coverages outside [0, 1] raise a ``ValueError`` that the
    HTTP layer surfaces as a 400.
    """
    rows: list[dict[str, object]] = []
    if isinstance(value, list):
        for row in value:
            if isinstance(row, Mapping):
                rows.append({str(key): cast(object, item) for key, item in row.items()})
    if not rows:
        rows = _demo_cells()
    frame = pd.DataFrame(rows)

    errors: list[str] = []
    for column, lo, hi in _PHYSICAL_BOUNDS:
        if column not in frame.columns:
            continue
        series = pd.to_numeric(frame[column], errors="coerce")
        nan_mask = series.isna()
        if nan_mask.any():
            errors.append(
                f"{column}: {int(nan_mask.sum())} cell(s) have NaN/non-numeric values "
                f"(first offending cell_id={_first_offending_cell_id(frame, nan_mask)!r})"
            )
            continue
        out_of_range = (series < lo) | (series > hi)
        if out_of_range.any():
            bad = series[out_of_range]
            errors.append(
                f"{column}: {int(out_of_range.sum())} cell(s) outside [{lo}, {hi}] "
                f"(range observed [{float(bad.min())}, {float(bad.max())}], "
                f"first offending cell_id={_first_offending_cell_id(frame, out_of_range)!r})"
            )
    if errors:
        raise ValueError(
            "Habitat cells failed physical-range validation:\n  - "
            + "\n  - ".join(errors)
        )
    return frame


def _normalise_population_cohorts(value: object) -> list[dict[str, object]] | None:
    """Coerce a JSON-typed cohort list (from config.population_cohorts) into
    the dict-of-dicts shape build_initial_population expects, or return None
    if the field is absent/empty. 2026-05-27 stratified-init track A.
    """
    if not isinstance(value, list) or not value:
        return None
    out: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        try:
            n = int(cast(Any, raw.get("number", 0)))
            mode = float(cast(Any, raw["length_mm_mode"]))
        except (KeyError, TypeError, ValueError):
            continue
        if n <= 0:
            continue
        cohort: dict[str, object] = {
            "number": n,
            "length_mm_mode": mode,
            "age_days": int(cast(Any, raw.get("age_days", 365))),
        }
        for key in ("length_mm_min", "length_mm_max"):
            if key in raw:
                try:
                    cohort[key] = float(cast(Any, raw[key]))
                except (TypeError, ValueError):
                    pass
        sp = raw.get("species")
        if isinstance(sp, str) and sp.strip():
            cohort["species"] = sp.strip()
        out.append(cohort)
    return out or None


def _first_offending_cell_id(frame: pd.DataFrame, mask: pd.Series) -> str:
    """Return a printable cell_id (or row index) for the first masked row."""
    if "cell_id" in frame.columns:
        first = frame.loc[mask, "cell_id"].head(1)
        if not first.empty:
            return str(first.iloc[0])
    first_idx = mask[mask].index
    return f"row#{int(first_idx[0])}" if len(first_idx) else "?"


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


def _aggregate_last_day(
    population_summary: pd.DataFrame, *, initial_n: int,
) -> dict[str, object]:
    """Collapse the final day's per-species rows into one whole-population
    snapshot. Returns a dict with the same keys daily rows use
    (``abundance``, ``biomass_g``, ``mean_length_mm``, ``survival_rate``,
    ``n_recruits``, ``n_spawners``, ``n_active_redds``, ``n_eggs_remaining``)
    but aggregated across species. Mean length is biomass-weighted so it
    stays well-defined across heterogeneous body sizes.

    Pinned by the 2026-05-28 multi-species walkthrough (ExampleB had 3
    species → previous ``iloc[-1]`` returned one species' tail row).
    """
    if population_summary.empty:
        return {
            "abundance": 0,
            "biomass_g": 0.0,
            "mean_length_mm": 0.0,
            "survival_rate": None,
            "n_recruits": 0,
            "n_spawners": 0,
            "n_active_redds": 0,
            "n_eggs_remaining": 0,
        }
    last_day = int(population_summary["day"].max())
    last_rows = population_summary[population_summary["day"] == last_day]
    abundance = int(pd.to_numeric(last_rows["abundance"]).sum())
    biomass = float(pd.to_numeric(last_rows["biomass_g"]).sum())
    # Biomass-weighted mean length: ΣL·m / Σm. Falls back to simple mean
    # when biomass is zero (e.g. abundance=0).
    lengths = pd.to_numeric(last_rows["mean_length_mm"])
    biomasses = pd.to_numeric(last_rows["biomass_g"])
    if biomass > 0:
        mean_length = float((lengths * biomasses).sum() / biomass)
    elif abundance > 0:
        mean_length = float(lengths.mean())
    else:
        mean_length = 0.0
    survival = (abundance / initial_n) if initial_n > 0 else None

    def _sum_or_zero(col: str) -> int:
        if col in last_rows.columns:
            return int(pd.to_numeric(last_rows[col]).sum())
        return 0

    return {
        "abundance": abundance,
        "biomass_g": biomass,
        "mean_length_mm": mean_length,
        "survival_rate": survival,
        "n_recruits": _sum_or_zero("n_recruits"),
        "n_spawners": _sum_or_zero("n_spawners"),
        "n_active_redds": _sum_or_zero("n_active_redds"),
        "n_eggs_remaining": _sum_or_zero("n_eggs_remaining"),
    }


def _is_nan(value: object) -> bool:
    """True iff value is a float NaN. Robust to numpy scalars."""
    if isinstance(value, float):
        return value != value  # noqa: PLR0124 — NaN!=NaN trick
    item = getattr(value, "item", None)
    if callable(item):
        try:
            v = item()
        except Exception:  # pragma: no cover
            return False
        return isinstance(v, float) and v != v  # noqa: PLR0124
    return False


def _sanitize_for_json(value: object) -> object:
    """Recursively replace NaN / +Inf / -Inf with ``None`` so the result
    round-trips through ``json.dumps(..., allow_nan=False)`` (and through
    browsers' ``response.json()``). Catches the case where an empty IBM
    population produces ``final_mean_length_mm = NaN`` and Python's
    default ``allow_nan=True`` writes the non-standard ``NaN`` token.

    Pinned by 2026-05-26 software-test S2 (Codex).
    """
    if isinstance(value, float):
        if value != value or value in (math.inf, -math.inf):  # noqa: PLR0124 — NaN!=NaN trick
            return None
        return value
    if isinstance(value, Mapping):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_sanitize_for_json(v) for v in value]
    return value


def _run_dir(output_dir: str | Path, prefix: str) -> Path:
    """Reserve a unique run directory under ``output_dir`` and prune the
    oldest historical run dirs above ``MAX_STUDIO_RUN_DIRS`` so the on-disk
    cache cannot grow forever (2026-05-26 software-test M1, Codex + Gemini).
    Headless workflow runners that need permanent history should pass a
    separate ``output_dir`` per case.
    """
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    # Prune to ``keep - 1`` so that after we create the next run dir the
    # steady-state total is exactly MAX_STUDIO_RUN_DIRS, not +1
    # (2026-05-26 pass-2 software-test N4', Codex off-by-one).
    _prune_oldest_run_dirs(root, prefix, keep=max(MAX_STUDIO_RUN_DIRS - 1, 0))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _prune_oldest_run_dirs(root: Path, prefix: str, *, keep: int) -> None:
    """Remove oldest matching ``{prefix}-*`` subdirectories until at most
    ``keep`` remain. Quietly skips dirs whose names don't match the
    naming convention (so unrelated co-located files survive).
    """
    try:
        entries = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(f"{prefix}-")]
    except OSError:  # pragma: no cover - directory race
        return
    if len(entries) <= keep:
        return
    entries.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    import shutil  # noqa: PLC0415  — kept lazy: cleanup is rare
    for victim in entries[: len(entries) - keep]:
        try:
            shutil.rmtree(victim, ignore_errors=True)
        except OSError:  # pragma: no cover - permission race
            _LOG.warning("Could not prune old run dir %s", victim)


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
    population_cohorts: list[dict[str, object]] | None = None,
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
            **(
                {"cohorts": population_cohorts}
                if population_cohorts else {}
            ),
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
    # MAX_STUDIO_DAYS caps interactive runs at 10 years so a stray
    # `days=10000` POST cannot hang the request thread indefinitely
    # (2026-05-26 software-test M2, Codex). Long simulations should
    # use the workflow runner, not the interactive Studio API.
    requested_days = _as_int(config.get("days"), 45, min_value=0)
    days = min(requested_days, MAX_STUDIO_DAYS)
    requested_initial_abundance = _as_int(config.get("initial_abundance"), 80, min_value=0)
    initial_abundance = min(
        requested_initial_abundance, MAX_STUDIO_INITIAL_ABUNDANCE,
    )
    seed = _as_int(config.get("seed"), 42)
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
    population_cohorts = _normalise_population_cohorts(config.get("population_cohorts"))

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
        population_cohorts=population_cohorts,
    )

    result, paths = run_ibm_scenario(
        studio_paths["studio_scenario"],
        output_dir_override=run_root,
        run_label="studio",
    )
    paths.update(studio_paths)
    # Single-species scenarios produce one summary row per day; multi-species
    # scenarios produce one row per (day, species) pair. ``iloc[-1]`` would
    # pick one species' tail for the last day, masking the total abundance
    # for ExampleB-style 3-species runs. Aggregate across species on the
    # last day so the top-level metrics are always whole-population values.
    # 2026-05-28 follow-up to commit 05ae04a.
    final = _aggregate_last_day(result.population_summary, initial_n=initial_abundance)
    cell_summary = _cell_use_summary(result.cell_use)
    events = (
        result.events.sort_values(["day", "event"], kind="mergesort")
        if not result.events.empty
        else result.events
    )
    # Redds use ``spawn_day`` (the day the redd was created), not ``day``;
    # the wrong column name shipped silently until the 2026-05-27 1-year
    # walkthrough exercised the post-spawning-window code path for the
    # first time.
    redds = (
        result.redds.sort_values(["spawn_day", "redd_id"], kind="mergesort")
        if not result.redds.empty
        else result.redds
    )

    # Surface any quietly-applied caps so the response body answers the
    # question "did I actually get what I asked for?" (2026-05-26 pass-2
    # software-test M2', Codex).
    cap_warnings: list[str] = []
    if requested_days != days:
        cap_warnings.append(
            f"days clamped from requested {requested_days} to MAX_STUDIO_DAYS={MAX_STUDIO_DAYS}; "
            "use the headless workflow runner for longer horizons."
        )
    if requested_initial_abundance != initial_abundance:
        cap_warnings.append(
            f"initial_abundance clamped from requested {requested_initial_abundance} "
            f"to MAX_STUDIO_INITIAL_ABUNDANCE={MAX_STUDIO_INITIAL_ABUNDANCE} for "
            "interactive responsiveness."
        )

    # survival_rate is None when initial_abundance=0 (undefined ratio);
    # native.py:496 already returns None in that case (pass-2 M3', Codex).
    raw_survival = final["survival_rate"]
    metric_survival = (
        float(raw_survival) if raw_survival is not None and not _is_nan(raw_survival) else None
    )

    return {
        "ok": True,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": paths,
        "warnings": cap_warnings,
        "metrics": {
            "initial_abundance": initial_abundance,
            "requested_initial_abundance": requested_initial_abundance,
            "final_abundance": int(cast(int, final["abundance"])),
            "final_biomass_g": float(cast(float, final["biomass_g"])),
            "final_mean_length_mm": float(cast(float, final["mean_length_mm"])),
            "survival_rate": metric_survival,
            "requested_days": requested_days,
            "effective_days": days,
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
    # Surface the per-run distribution as ensemble metrics so callers can
    # render bands without re-loading the CSV. 2026-05-28 Step-8 follow-up
    # (Codex flagged metrics.seeds=[] in the pass-2 probe).
    summary_df = result.summary
    if not summary_df.empty:
        finals = pd.to_numeric(summary_df["final_abundance"], errors="coerce")
        biomass = pd.to_numeric(summary_df["final_biomass_g"], errors="coerce")
        param_cols = [c for c in summary_df.columns if c.startswith("param_")]
        parameter_grid_size = (
            int(summary_df[param_cols].drop_duplicates().shape[0]) if param_cols else 1
        )
        ensemble_metrics: dict[str, object] = {
            "n_runs": int(len(summary_df)),
            "n_seeds": int(len(seeds)),
            "seeds": list(int(s) for s in seeds),
            "parameter_grid_size": parameter_grid_size,
            "mean_final_abundance": float(finals.mean()) if not finals.empty else 0.0,
            "median_final_abundance": float(finals.median()) if not finals.empty else 0.0,
            "min_final_abundance": int(finals.min()) if not finals.empty else 0,
            "max_final_abundance": int(finals.max()) if not finals.empty else 0,
            "std_final_abundance": float(finals.std(ddof=0)) if not finals.empty else 0.0,
            "mean_final_biomass_g": float(biomass.mean()) if not biomass.empty else 0.0,
        }
    else:
        ensemble_metrics = {
            "n_runs": 0,
            "n_seeds": int(len(seeds)),
            "seeds": list(int(s) for s in seeds),
            "parameter_grid_size": 0,
            "mean_final_abundance": 0.0,
            "median_final_abundance": 0.0,
            "min_final_abundance": 0,
            "max_final_abundance": 0,
            "std_final_abundance": 0.0,
            "mean_final_biomass_g": 0.0,
        }
    return {
        "ok": True,
        "run_id": run_root.name,
        "run_dir": str(run_root),
        "paths": paths,
        "metrics": ensemble_metrics,
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





__all__ = [
    "compare_instream7_for_studio",
    "default_studio_scenario",
    "default_studio_scenario_resolved",
    "run_ibm_studio",
    "run_instream7_benchmark_for_studio",
    "run_studio_calibration",
    "run_studio_ensemble",
    "run_studio_scenario",
    "validate_studio_payload",
    "write_studio_scenario_files",
]

# 2026-05-26 R-IBM-GOD-OBJECT partial split (ADR-0016):
# - HTTP server + run_ibm_studio moved to studio_http.py
# - 720-line _INDEX_HTML template moved to studio_assets.py
#
# These re-exports preserve the existing public-API paths:
# ``from openlimno.ibm.studio import run_ibm_studio`` (cli.py, tests/)
# and ``getattr(studio_module, "_INDEX_HTML")`` (acceptance.py)
# both keep working unchanged.
from .studio_assets import _INDEX_HTML  # noqa: E402, F401
from .studio_http import run_ibm_studio  # noqa: E402, F401
