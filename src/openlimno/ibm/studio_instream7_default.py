"""Build the IBM Studio default scenario from a local inSTREAM 7.4 archive.

DEV-ONLY surface (R-IBM-STUDIO-CONSOLIDATE). The Studio in turn is a
dev/research preview surface — see ``studio.py`` for the full advisory.

The Cal Poly Humboldt inSTREAM 7.4 distribution is GPL-3.0; OpenLimno
is Apache-2.0 + CC-BY-4.0, so we cannot redistribute the archive inside
this repository. Users either point ``OPENLIMNO_INSTREAM7_ARCHIVE`` at
a directory containing the unpacked archive, drop the unpacked archive
under ``~/.cache/openlimno/instream7_official/``, or — for developers —
let the dev-time fetcher unpack it under ``<repo>/output/instream7_official/``.

When found, the Studio's ``/api/default`` returns the real ExampleA case
(1373 surveyed cells, 10-year time series, real shapefile, GPL-licensed
parameter file). When absent, callers fall back to the synthetic demo
in :mod:`openlimno.ibm.studio`.
"""

from __future__ import annotations

import dataclasses
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .instream7 import (
    build_reach_habitat_cells,
    discover_instream7_cases,
    read_official_initial_population,
    species_profile_from_official_case,
)

_ARCHIVE_ENV = "OPENLIMNO_INSTREAM7_ARCHIVE"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANDIDATE_DIRS: tuple[Path, ...] = (
    Path.home() / ".cache" / "openlimno" / "instream7_official",
    _REPO_ROOT / "output" / "instream7_official",
)


def find_instream7_archive_root() -> Path | None:
    """Locate an unpacked inSTREAM 7.4 archive on the local filesystem.

    Search order: ``$OPENLIMNO_INSTREAM7_ARCHIVE`` env var, then the
    user XDG cache dir, then the dev-time repo-relative output dir.
    """
    env = os.environ.get(_ARCHIVE_ENV)
    if env:
        candidate = Path(env).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate
    for candidate in _CANDIDATE_DIRS:
        if candidate.exists() and candidate.is_dir() and any(candidate.iterdir()):
            return candidate
    return None


def _classify_hmu(depth_m: float, vel_ms: float) -> str:
    """Coarse HMU classification per Hawkins (1993) / Kondolf (2003).

    Pure geometric bucketing for UI grouping only; the IBM uses per-cell
    depth + velocity directly, not the HMU label.
    """
    if depth_m < 0.10:
        return "margin"
    if depth_m < 0.30:
        return "riffle" if vel_ms > 0.50 else "glide"
    if vel_ms > 0.80:
        return "run"
    if vel_ms <= 0.30:
        return "pool"
    return "run"


def _shapefile_axis_projection(gdf: Any) -> tuple[Any, Any, tuple[float, float], float]:
    """Project polygon centroids onto principal axis. Returns (proj_m, axis,
    origin_xy_native, unit_to_metres_factor).
    """
    import numpy as np

    cents = gdf.geometry.centroid
    xs = cents.x.values.astype(float)
    ys = cents.y.values.astype(float)
    mx = float(xs.mean())
    my = float(ys.mean())
    centred = np.vstack([xs - mx, ys - my])
    cov = centred @ centred.T / max(centred.shape[1] - 1, 1)
    _, evec = np.linalg.eigh(cov)
    axis = evec[:, -1]
    proj_native = centred.T @ axis

    factor = 1.0
    crs = gdf.crs
    if crs is not None:
        try:
            unit = crs.axis_info[0].unit_name.lower()
            if "foot" in unit:
                factor = 0.3048
        except (AttributeError, IndexError):
            factor = 1.0

    proj_m = proj_native * factor
    proj_m = proj_m - proj_m.min()
    return proj_m, axis, (mx, my), factor


def build_studio_scenario_from_instream7_archive(
    archive_root: Path | str,
    *,
    case_id: str = "ExampleA",
    submodels: Mapping[str, object] | None = None,
    submodel_catalog: list[dict[str, object]] | None = None,
    experiments: Mapping[str, object] | None = None,
    instream_panel_defaults: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Construct a Studio scenario payload from the real inSTREAM 7.4 archive."""
    import geopandas as gpd  # noqa: PLC0415  — heavy import, defer
    import numpy as np

    root = Path(archive_root)
    cases = discover_instream7_cases(root)
    target = next((c for c in cases if c.case_id == case_id), None)
    if target is None:
        raise FileNotFoundError(
            f"inSTREAM 7 case '{case_id}' not found under {root}"
        )
    reach = target.reaches[0]

    ts = pd.read_csv(reach.time_series_file, comment=";")
    q_med = float(ts["flow"].median())
    t_med = float(ts["temperature"].median())
    tur_med = float(ts["turbidity"].median())

    cells_df = build_reach_habitat_cells(
        reach, flow_m3s=q_med, temperature_c=t_med, turbidity_ntu=tur_med
    )

    gdf = gpd.read_file(reach.shapefile)
    proj_m, axis, origin, factor = _shapefile_axis_projection(gdf)
    reach_length_m = float(proj_m.max() - proj_m.min())

    cents = gdf.geometry.centroid
    cx = (cents.x.values - origin[0]) * factor
    cy = (cents.y.values - origin[1]) * factor

    perp = np.array([-axis[1], axis[0]])

    order = np.argsort(proj_m)
    cells: list[dict[str, object]] = []
    for src_idx in order:
        row = cells_df.iloc[int(src_idx)]
        area = float(row["area_m2"])
        depth = float(row["depth_m"])
        vel = float(row["velocity_ms"])
        edge = math.sqrt(max(area, 1e-6))
        feed = float(row["feeding_cover"])
        spawn = float(row["spawning_cover"])
        hide = float(row["hiding_cover"])
        depth_score = 1.0 - min(abs(depth - 0.5) / 1.0, 1.0)
        vel_score = 1.0 - min(abs(vel - 0.4) / 1.0, 1.0)
        csi = round(0.5 * (depth_score * vel_score) + 0.3 * feed + 0.2 * spawn, 3)
        cells.append(
            {
                "cell_id": f"ExampleA-{int(row['cell_id'])}",
                "reach_id": reach.reach_id,
                "reach_order": 1,
                "habitat_type": _classify_hmu(depth, vel),
                "station_m": round(float(proj_m[int(src_idx)]), 2),
                "center_x_m": round(float(cx[int(src_idx)]), 2),
                "center_y_m": round(float(cy[int(src_idx)]), 2),
                "length_m": round(edge, 2),
                "width_m": round(edge, 2),
                "area_m2": round(area, 3),
                "depth_m": round(depth, 3),
                "velocity_ms": round(vel, 3),
                "csi": csi,
                "temperature_c": round(t_med, 2),
                "turbidity_ntu": round(tur_med, 2),
                "hiding_cover": round(hide, 3),
                "feeding_cover": round(feed, 3),
                "spawning_cover": round(spawn, 3),
            }
        )

    try:
        outline = gdf.geometry.unary_union.buffer(0).convex_hull
        xs_ext, ys_ext = outline.exterior.coords.xy
        channel_polygon = [
            [round((float(x) - origin[0]) * factor, 2),
             round((float(y) - origin[1]) * factor, 2)]
            for x, y in zip(xs_ext, ys_ext, strict=True)
        ]
    except (AttributeError, ValueError):
        channel_polygon = [
            [0.0, -20.0],
            [reach_length_m, -20.0],
            [reach_length_m, 20.0],
            [0.0, 20.0],
            [0.0, -20.0],
        ]

    n_bins = 80
    bin_edges = np.linspace(0.0, max(reach_length_m, 1.0), n_bins + 1)
    centerline_m: list[list[float]] = []
    for i in range(n_bins):
        mask = (proj_m >= bin_edges[i]) & (proj_m < bin_edges[i + 1])
        if int(mask.sum()) < 2:
            continue
        local_xy = np.vstack([cx[mask], cy[mask]]).T
        lateral = local_xy @ perp
        centerline_m.append(
            [
                round(float((bin_edges[i] + bin_edges[i + 1]) / 2), 2),
                round(float(lateral.mean()), 2),
            ]
        )
    if len(centerline_m) < 2:
        centerline_m = [
            [round(float(s), 2), 0.0]
            for s in np.linspace(0.0, reach_length_m, 40)
        ]

    initial_population = read_official_initial_population(target.initial_population_file)
    total_init = int(initial_population["Number"].sum())
    mode_lengths = initial_population["Length mode"].astype(float).tolist()
    initial_length_mm = float(sum(mode_lengths) / len(mode_lengths)) if mode_lengths else 80.0

    profile = species_profile_from_official_case(target, target.species[0])
    profile_dict: dict[str, object] = {}
    for field in dataclasses.fields(profile):
        value = getattr(profile, field.name)
        if isinstance(value, str | int | float | bool):
            profile_dict[field.name] = value

    river: dict[str, object] = {
        "name": "inSTREAM 7.4 Example Project A",
        "reach_name": f"{reach.reach_id} (Cal Poly Humboldt official archive)",
        "length_m": round(reach_length_m, 2),
        "flow_m3s": round(q_med, 3),
        "display_note": (
            f"Real inSTREAM 7.4 ExampleA archive: {len(cells_df)} surveyed cells, "
            f"{len(ts)}-day time series, shapefile CRS={gdf.crs}. "
            "Geometry comes from the official archive — Import GIS still works "
            "for replacing the shape with a different surveyed reach."
        ),
        "geometry": {
            "channel_polygon_m": channel_polygon,
            "centerline_m": centerline_m,
            "crs": "local_m",
            "source": "inSTREAM 7.4 ExampleA shapefile (Cal Poly Humboldt)",
            "boundary_quality": {
                "real": True,
                "note": "Convex hull of 1373 surveyed polygon cells.",
            },
        },
    }

    config: dict[str, object] = {
        "scenario_id": "instream7-example-a-real-archive",
        "reach_id": reach.reach_id,
        "species": "rainbow_trout",
        "initial_abundance": total_init,
        "initial_length_mm": round(initial_length_mm, 2),
        "days": 45,
        "seed": 20260526,
        "stochastic": True,
        "record_individual_history": True,
    }

    payload: dict[str, object] = {
        "config": config,
        "river": river,
        "profile": profile_dict,
        "cells": cells,
        "submodels": dict(submodels) if submodels else {},
        "submodel_catalog": list(submodel_catalog) if submodel_catalog else [],
        "experiments": dict(experiments) if experiments else {},
        "instream": dict(instream_panel_defaults) if instream_panel_defaults else {},
        "_provenance": {
            "source": "Cal Poly Humboldt inSTREAM 7.4 ExampleA",
            "license": "GPL-3.0",
            "archive_filename": "InSTREAM-7.4_2026-02-11.zip",
            "case_id": target.case_id,
            "reach_id": reach.reach_id,
            "shapefile_crs": str(gdf.crs),
            "real_cells": int(len(cells_df)),
            "time_series_days": int(len(ts)),
            "median_flow_m3s": q_med,
            "median_temperature_c": t_med,
            "median_turbidity_ntu": tur_med,
            "initial_population_total": total_init,
            "loaded_from": str(root),
        },
    }
    return payload


__all__ = [
    "build_studio_scenario_from_instream7_archive",
    "find_instream7_archive_root",
]
