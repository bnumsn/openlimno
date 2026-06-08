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
import logging
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd

from .instream7 import (
    build_reach_habitat_cells,
    discover_instream7_cases,
    read_official_initial_population,
    species_profile_from_official_case,
)

_LOG = logging.getLogger(__name__)

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


def _crs_unit_factor(crs: Any) -> float:
    """Return the multiplier that converts the CRS's linear unit to metres.

    Rejects geographic CRSes (degrees), where centroid arithmetic + linear
    distances are undefined. Recognises metres and US/intl survey foot;
    anything else (or missing axis info) is rejected so a silent mis-scaling
    cannot ship undetected. Triple-review (gemini, claude) flagged the
    earlier foot-or-nothing detector as exactly this hazard.
    """
    if crs is None:
        raise ValueError("shapefile has no CRS — cannot translate coordinates to metres.")
    try:
        unit = crs.axis_info[0].unit_name.lower()
    except (AttributeError, IndexError) as exc:
        raise ValueError(
            f"shapefile CRS {crs!r} has no axis_info — refusing to guess units."
        ) from exc
    if "degree" in unit or getattr(crs, "is_geographic", False):
        raise ValueError(
            f"shapefile CRS {crs!r} is geographic (unit={unit!r}); a projected "
            "CRS is required so reach length, station, and area are well-defined."
        )
    if "metre" in unit or "meter" in unit:
        return 1.0
    if "foot" in unit:
        return 0.3048
    raise ValueError(f"shapefile CRS {crs!r} has unrecognised linear unit {unit!r}.")


def _shapefile_axis_projection(gdf: Any) -> tuple[Any, Any, tuple[float, float], float]:
    """Project polygon centroids onto principal axis.

    Returns (proj_m, axis, origin_xy_native, unit_to_metres_factor).
    The principal axis sign is fixed by the convention "station 0 = the
    centroid with the smallest native x"; this makes reach orientation
    deterministic across LAPACK builds (the eigenvector sign returned by
    ``np.linalg.eigh`` is otherwise arbitrary — Claude review flagged).
    """
    import numpy as np

    factor = _crs_unit_factor(gdf.crs)

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
    # Deterministic axis sign: orient so the axis vector points generally
    # east (positive x) — falling back to north (positive y) when the axis
    # is purely meridional. ``np.linalg.eigh`` returns sign-arbitrary
    # eigenvectors, so without this the same dataset can pick "station 0
    # = upstream" or "= downstream" across builds (Claude review).
    if axis[0] < 0 or (axis[0] == 0.0 and axis[1] < 0):
        axis = -axis
        proj_native = -proj_native

    proj_m = (proj_native - proj_native.min()) * factor
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
    from shapely.ops import unary_union as _unary_union

    root = Path(archive_root)
    cases = discover_instream7_cases(root)
    target = next((c for c in cases if c.case_id == case_id), None)
    if target is None:
        raise FileNotFoundError(f"inSTREAM 7 case '{case_id}' not found under {root}")
    if not target.species:
        raise ValueError(
            f"inSTREAM 7 case '{target.case_id}' has no species — cannot build a Studio scenario."
        )
    # Pick a single reach (multi-reach scenarios are loaded one reach at a
    # time; the Studio is single-reach by design). Initial-population
    # cohorts will be filtered to this reach below so the abundance and
    # biomass numbers stay consistent — triple-AI review A5 (Codex P2)
    # caught that the previous build pulled cohorts from ALL reaches and
    # implicitly piled them into reaches[0].
    reach = target.reaches[0]
    selected_reach_id = reach.reach_id

    ts = pd.read_csv(reach.time_series_file, comment=";")
    q_med = float(ts["flow"].median())
    t_med = float(ts["temperature"].median())
    tur_med = float(ts["turbidity"].median())

    cells_df = build_reach_habitat_cells(
        reach, flow_m3s=q_med, temperature_c=t_med, turbidity_ntu=tur_med
    )

    # ExampleB's shapefile is shared across all three reaches (5631 rows
    # combined), but ``cells_df`` only carries the per-reach subset
    # (1353 / 1604 / 2674 cells per reach). Filter the GeoDataFrame to
    # the same cell_id set so projection indices line up — without this
    # the per-cell loop hits ``IndexError: iloc out-of-bounds`` for
    # multi-reach archives. 2026-05-27 track D.
    gdf = gpd.read_file(reach.shapefile)
    # ExampleA uses ``ID_TEXT`` while ExampleB uses ``ID_text``. Resolve
    # the cell-id column case-insensitively before filtering.
    cell_col = next(
        (c for c in gdf.columns if c.lower() == reach.cell_id_field.lower()),
        reach.cell_id_field,
    )
    if cell_col in gdf.columns:
        keep = set(cells_df["cell_id"].astype(str).tolist())
        gdf = gdf[gdf[cell_col].astype(str).isin(keep)].reset_index(drop=True)
    # If the filter still leaves a row mismatch (e.g. duplicate cell_ids
    # in the shapefile, or missing CSV rows), align cells_df to gdf by
    # cell_id so the by-position loop below is safe.
    if len(gdf) != len(cells_df) and cell_col in gdf.columns:
        order_map = {str(cid): i for i, cid in enumerate(gdf[cell_col].astype(str).tolist())}
        cells_df = (
            cells_df.assign(_order=cells_df["cell_id"].astype(str).map(order_map))
            .dropna(subset=["_order"])
            .sort_values("_order", kind="mergesort")
            .drop(columns="_order")
            .reset_index(drop=True)
        )
        # And keep only gdf rows whose cell_id is in cells_df (drop dupes).
        wanted = set(cells_df["cell_id"].astype(str).tolist())
        gdf = (
            gdf[gdf[cell_col].astype(str).isin(wanted)]
            .drop_duplicates(subset=[cell_col])
            .reset_index(drop=True)
        )
    proj_m, axis, origin, factor = _shapefile_axis_projection(gdf)
    reach_length_m = float(proj_m.max() - proj_m.min())

    # Unify the whole scene in a single "principal-axis" frame:
    # x = along-reach station (metres, 0 = upstream), y = perpendicular
    # lateral offset (metres, 0 = thalweg-ish). The previous version
    # mixed translated source x/y for polygon+cells with (station, lateral)
    # for the centerline, so all three layers were drawn on different axes
    # (Codex P2). With the unified frame, polygon, cells, and centerline
    # all overlay correctly in the Studio plan view.
    perp = np.array([-axis[1], axis[0]])

    cents = gdf.geometry.centroid
    raw_centred = np.vstack([cents.x.values - origin[0], cents.y.values - origin[1]]).T
    proj_native = raw_centred @ axis
    lateral_native = raw_centred @ perp
    cx = (proj_native - proj_native.min()) * factor  # = station_m
    cy = lateral_native * factor  # = lateral offset

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
                "cell_id": f"{target.case_id}-{row['cell_id']}",
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
        # Project the dissolved outline into the principal-axis frame too,
        # so the polygon, cells, and centerline live on the same axes.
        # ``shapely.ops.unary_union`` is the canonical idiom — the
        # GeoSeries ``.unary_union`` property is deprecated in
        # geopandas ≥1.0 in favour of ``.union_all()`` (Claude review).
        outline = _unary_union(list(gdf.geometry)).buffer(0).convex_hull
        xs_ext, ys_ext = outline.exterior.coords.xy
        vertices = np.vstack(
            [np.asarray(xs_ext, float) - origin[0], np.asarray(ys_ext, float) - origin[1]],
        ).T
        v_station = (vertices @ axis - proj_native.min()) * factor
        v_lateral = (vertices @ perp) * factor
        channel_polygon = [
            [round(float(s), 2), round(float(la), 2)]
            for s, la in zip(v_station.tolist(), v_lateral.tolist(), strict=True)
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
        mask = (proj_m >= bin_edges[i]) & (proj_m <= bin_edges[i + 1])
        if int(mask.sum()) < 2:
            continue
        centerline_m.append(
            [
                round(float((bin_edges[i] + bin_edges[i + 1]) / 2), 2),
                round(float(cy[mask].mean()), 2),
            ]
        )
    if len(centerline_m) < 2:
        centerline_m = [[round(float(s), 2), 0.0] for s in np.linspace(0.0, reach_length_m, 40)]

    # Triple-review caught the cm→mm bug here (Codex P1, Claude
    # "cohort structure collapsed"). The official ``Length mode`` column
    # is in CENTIMETRES; the Studio config expects MILLIMETRES. Also
    # weight by abundance so the dominant cohort (300 age-0 fry at 6.1 cm)
    # drives the mean, not an unweighted average of cohort modes.
    initial_population = read_official_initial_population(target.initial_population_file)
    # Filter cohorts to the loaded reach when the official table is keyed
    # by reach. ExampleA has 1 reach so this is a no-op; ExampleB has 3
    # and the file lists 9 cohorts per reach — without filtering, all 27
    # would pile into the single loaded reach, inflating abundance 3×.
    if "Reach" in initial_population.columns:
        reach_filtered = initial_population[
            initial_population["Reach"].astype(str) == str(selected_reach_id)
        ]
        if not reach_filtered.empty:
            initial_population = reach_filtered
    total_init = int(initial_population["Number"].sum())
    if total_init <= 0:
        raise ValueError(f"inSTREAM 7 case '{target.case_id}' has an empty initial population.")
    weighted_cm = float((initial_population["Number"] * initial_population["Length mode"]).sum())
    initial_length_mm = (weighted_cm * 10.0) / total_init
    cohorts = [
        {
            "species": str(row["Species"]),
            "reach": str(row["Reach"]),
            "age": int(row["Age"]),
            "number": int(row["Number"]),
            "length_min_cm": float(row["Length min"]),
            "length_mode_cm": float(row["Length mode"]),
            "length_max_cm": float(row["Length max"]),
        }
        for row in initial_population.to_dict(orient="records")
    ]

    species_name = target.species[0]
    profile = species_profile_from_official_case(target, species_name)
    profile_dict: dict[str, object] = {}
    for field in dataclasses.fields(profile):
        value = getattr(profile, field.name)
        if isinstance(value, str | int | float | bool):
            profile_dict[field.name] = value

    n_real_cells = int(len(cells_df))
    river: dict[str, object] = {
        "name": "inSTREAM 7.4 Example Project A",
        "reach_name": f"{reach.reach_id} (Cal Poly Humboldt official archive)",
        "length_m": round(reach_length_m, 2),
        "flow_m3s": round(q_med, 3),
        "display_note": (
            f"Real inSTREAM 7.4 ExampleA archive: {n_real_cells} surveyed cells, "
            f"{len(ts)}-day time series, shapefile CRS={gdf.crs}. The plan-view "
            f"polygon is the convex envelope of the {n_real_cells} surveyed cells "
            "(not a concave bank trace). Import GIS to replace with a different "
            "surveyed reach."
        ),
        "geometry": {
            "channel_polygon_m": channel_polygon,
            "centerline_m": centerline_m,
            "crs": "local_m",
            "source": "inSTREAM 7.4 ExampleA shapefile (Cal Poly Humboldt)",
            "boundary_quality": {
                "real": True,
                "note": (
                    f"Convex envelope of {n_real_cells} surveyed polygon cells, "
                    "rotated into the principal-axis (along-reach) frame."
                ),
            },
        },
    }

    # Convert provenance cohorts (cm-based) to the IBM's
    # ``population.cohorts`` format (mm-based, ready to consume).
    # Triangular sampling (min/mode/max) per cohort preserves the
    # within-age length variability the official archive carries.
    cohort_specs: list[dict[str, object]] = [
        {
            "age_days": 365 * int(cast(int, c["age"])),
            "number": int(cast(int, c["number"])),
            "length_mm_min": float(cast(float, c["length_min_cm"])) * 10.0,
            "length_mm_mode": float(cast(float, c["length_mode_cm"])) * 10.0,
            "length_mm_max": float(cast(float, c["length_max_cm"])) * 10.0,
            "species": str(c["species"]),
        }
        for c in cohorts
    ]

    config: dict[str, object] = {
        "scenario_id": "instream7-example-a-real-archive",
        "reach_id": reach.reach_id,
        "species": "rainbow_trout",
        "initial_abundance": total_init,
        "initial_length_mm": round(initial_length_mm, 2),
        # Stratified initial population (2026-05-27 track A) — picked up
        # by scenario.py / build_initial_population so the day-0 mass
        # matches the official Cal Poly Humboldt 3-cohort biomass.
        "population_cohorts": cohort_specs,
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
            "species_name": species_name,
            "shapefile_crs": str(gdf.crs),
            "crs_unit_to_metres_factor": factor,
            "real_cells": n_real_cells,
            "time_series_days": int(len(ts)),
            "median_flow_m3s": q_med,
            "median_temperature_c": t_med,
            "median_turbidity_ntu": tur_med,
            "initial_population_total": total_init,
            "initial_population_cohorts": cohorts,
            "initial_length_mm_weighting": (
                "abundance-weighted mean of Length mode column "
                "(cm → mm); cohort structure preserved under "
                "initial_population_cohorts."
            ),
            "loaded_from": str(root),
        },
    }
    return payload


__all__ = [
    "build_studio_scenario_from_instream7_archive",
    "find_instream7_archive_root",
]
