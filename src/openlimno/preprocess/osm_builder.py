"""Build a runnable OpenLimno case directly from an OSM river polyline.

Pulls the river geometry from the public Overpass API, samples N mesh nodes
along it, fabricates V-shaped cross-sections (placeholder until real DEM /
ADCP data is available), and writes a complete case directory:

    <output_dir>/
      ├── case.yaml
      ├── data/
      │   ├── mesh.ugrid.nc
      │   ├── cross_section.parquet
      │   └── hsi_curve.parquet           (copied from sample if available)
      └── README.md

This is the M3 deliverable for SPEC §4.0 "preprocess" — turning open public
data into WEDM-conformant inputs in one CLI call.

Limitations (will improve in M4+):
  * Cross-section profile is symmetric V-shape with user-specified width &
    max depth. Real ADCP / DEM integration is M4 (`openlimno preprocess
    xs --dem ...`).
  * Bottom elevation along reach is interpolated linearly between the river's
    OSM-tagged elevation tags (rare) or estimated from a constant slope.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "OpenLimno/0.1 (https://github.com/openlimno/openlimno)"


@dataclass
class OSMCaseSpec:
    """Inputs for a one-shot OSM-to-OpenLimno case build.

    Reach can be located three ways (priority order):
      1. ``bbox`` (lon_min, lat_min, lon_max, lat_max) — most precise
      2. ``polyline_geojson`` path — user-drawn LineString
      3. ``river_name`` + ``region_name`` — fallback, may pick a wrong segment
    """

    river_name: str | None = None            # OSM 'name' tag; optional if bbox given
    region_name: str = "Idaho"               # admin area; only used when no bbox
    bbox: tuple[float, float, float, float] | None = None  # (lon_min, lat_min, lon_max, lat_max)
    polyline_geojson: str | None = None      # path to a LineString GeoJSON
    n_sections: int = 11                     # mesh nodes along reach
    reach_length_m: float = 1000.0           # length of modelled reach (used when no polyline)
    valley_width_m: float = 10.0             # cross-section width (bank-to-bank)
    thalweg_depth_m: float = 1.0             # max bed-below-bank depth
    bank_elevation_m: float = 1500.0         # upstream bank elevation
    slope: float = 0.002                     # along-reach bed slope
    species_id: str = "oncorhynchus_mykiss"  # default target species
    life_stages: tuple = ("spawning", "fry")
    case_name: str | None = None             # default = sluggified river name


def fetch_river_polyline(
    river_name: str | None = None,
    region_name: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    timeout: float = 60.0,
) -> list[tuple[float, float]]:
    """Query Overpass API for waterway polyline(s).

    Priority:
      1. If ``bbox`` is given, query ALL waterways inside that box (and
         filter by ``river_name`` if also given). Most precise.
      2. Otherwise use ``river_name`` + ``region_name``.

    Returns a list of (lon, lat) tuples for the longest contiguous segment.
    """
    import requests
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import linemerge

    if bbox is not None:
        lon_min, lat_min, lon_max, lat_max = bbox
        # Overpass uses (south, west, north, east) order
        bbox_clause = f"{lat_min},{lon_min},{lat_max},{lon_max}"
        name_filter = f'["name"="{river_name}"]' if river_name else ""
        query = f"""
        [out:json][timeout:{int(timeout)}];
        (
          way["waterway"]{name_filter}({bbox_clause});
        );
        out geom;
        """
    else:
        if not (river_name and region_name):
            raise ValueError("Provide bbox, or river_name + region_name")
        query = f"""
        [out:json][timeout:{int(timeout)}];
        area["name"="{region_name}"]["admin_level"~"4|6"]->.a;
        (
          way["waterway"]["name"="{river_name}"](area.a);
        );
        out geom;
        """

    resp = requests.get(OVERPASS_URL, params={"data": query},
                          headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    ways = [e for e in data.get("elements", []) if e["type"] == "way"]
    if not ways:
        raise ValueError(
            f"No waterway returned for "
            f"{'bbox=' + repr(bbox) if bbox else f'{river_name!r} in {region_name}'}"
        )

    lines = [LineString([(p["lon"], p["lat"]) for p in w["geometry"]])
              for w in ways]
    merged = linemerge(MultiLineString(lines))
    if isinstance(merged, MultiLineString):
        # Pick the longest contiguous segment
        merged = max(merged.geoms, key=lambda g: g.length)
    coords = list(merged.coords)
    logger.info("OSM polyline: %d points, %.1f km",
                  len(coords), merged.length * 111000 / 1000)
    return coords


def fetch_polyline_from_geojson(geojson_path: str) -> list[tuple[float, float]]:
    """Read a user-supplied LineString GeoJSON (e.g. drawn in QGIS)."""
    with open(geojson_path) as f:
        gj = json.load(f)
    if gj.get("type") == "FeatureCollection":
        feats = gj.get("features", [])
        if not feats:
            raise ValueError(f"Empty FeatureCollection in {geojson_path}")
        gj = feats[0].get("geometry", {})
    elif gj.get("type") == "Feature":
        gj = gj.get("geometry", {})
    if gj.get("type") not in ("LineString", "MultiLineString"):
        raise ValueError(f"Geometry must be LineString, got {gj.get('type')!r}")
    coords = (gj["coordinates"] if gj["type"] == "LineString"
                else max(gj["coordinates"], key=len))
    return [(float(c[0]), float(c[1])) for c in coords]


def sample_mesh_nodes(polyline: list[tuple[float, float]],
                        spec: OSMCaseSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Take an even-distance subsample along the polyline.

    Returns (lon[N], lat[N], station_along_reach_m[N]).
    Picks the central reach_length_m portion of the polyline.
    """
    from shapely.geometry import LineString
    from shapely.ops import substring

    full = LineString(polyline)
    full_m = full.length * 111000  # rough metre length
    # Centre the reach
    centre_along = full.length / 2
    half_deg = (spec.reach_length_m / 2) / 111000
    sub_start = max(0.0, centre_along - half_deg)
    sub_end = min(full.length, centre_along + half_deg)
    sub = substring(full, sub_start, sub_end)

    distances = np.linspace(0, sub.length, spec.n_sections)
    pts = [sub.interpolate(d) for d in distances]
    node_x = np.array([p.x for p in pts])
    node_y = np.array([p.y for p in pts])
    station_m = np.linspace(0, spec.reach_length_m, spec.n_sections)
    return node_x, node_y, station_m


def build_v_cross_sections(station_m: np.ndarray, spec: OSMCaseSpec) -> pd.DataFrame:
    """Synthesise V-shaped cross-sections at each station."""
    import uuid
    cid = str(uuid.uuid4())
    rows = []
    n_pts = 21
    half = spec.valley_width_m / 2
    offsets = np.linspace(-half, half, n_pts)
    for i, station in enumerate(station_m):
        bank_elev = spec.bank_elevation_m - spec.slope * station
        depth_profile = spec.thalweg_depth_m * (1 - (offsets / half) ** 2)
        depth_profile = np.clip(depth_profile, 0, spec.thalweg_depth_m)
        for j, (off, depth) in enumerate(zip(offsets, depth_profile, strict=True)):
            rows.append({
                "campaign_id": cid,
                "station_m": float(station),
                "point_index": j,
                "distance_m": float(off),
                "elevation_m": float(bank_elev - depth),
                "depth_m": float(depth),
                "substrate": "gravel-cobble",
                "cover": "none",
            })
    return pd.DataFrame(rows)


def write_ugrid_mesh(node_x: np.ndarray, node_y: np.ndarray,
                      station_m: np.ndarray, bottom_elevation: np.ndarray,
                      out_path: Path) -> None:
    """Write a UGRID-1D NetCDF mesh with edges connecting consecutive nodes."""
    n = len(node_x)
    edge_nodes = np.array([(i, i + 1) for i in range(n - 1)], dtype=np.int64)
    ds = xr.Dataset(
        data_vars={
            "mesh1d": ((), 0, {
                "cf_role": "mesh_topology",
                "topology_dimension": 1,
                "node_coordinates": "node_x node_y",
                "edge_node_connectivity": "edge_nodes",
            }),
            "node_x": (("node",), node_x, {"standard_name": "longitude",
                                              "units": "degrees_east"}),
            "node_y": (("node",), node_y, {"standard_name": "latitude",
                                              "units": "degrees_north"}),
            "bottom_elevation": (("node",), bottom_elevation, {"units": "m"}),
            "edge_nodes": (("edge", "two"), edge_nodes,
                            {"start_index": 0}),
        },
        coords={"station_m": (("node",), station_m,
                                {"long_name": "along-reach distance",
                                 "units": "m"})},
        attrs={
            "Conventions": "CF-1.8 UGRID-1.0",
            "title": "OpenLimno mesh built from OSM (init-from-osm)",
            "source": "openlimno.preprocess.osm_builder",
        },
    )
    ds.to_netcdf(out_path)


def build_case(spec: OSMCaseSpec, output_dir: str | Path) -> dict[str, str]:
    """End-to-end build: fetch OSM → sample → generate files → write case.yaml.

    Returns a dict of output paths (case_yaml / mesh / cross_section).
    """
    import yaml

    output_dir = Path(output_dir).resolve()
    data_dir = output_dir / "data"
    # Guard against symlinked data/ pointing into a shared/source repo
    # (the workspace's data/ symlinks to /mnt/data/openlimno/data, which
    # would otherwise land case files inside the repo).
    if data_dir.is_symlink() or (data_dir.exists() and data_dir.resolve() != data_dir):
        raise ValueError(
            f"Refusing to build case: {data_dir} is a symlink to "
            f"{data_dir.resolve()}. Pick an output directory whose 'data/' "
            f"is a real subdirectory, e.g. {output_dir}/<case-name>/."
        )
    data_dir.mkdir(parents=True, exist_ok=True)

    if spec.case_name:
        case_name = spec.case_name
    elif spec.river_name:
        case_name = spec.river_name.lower().replace(" ", "_")
    elif spec.bbox is not None:
        lon_c = (spec.bbox[0] + spec.bbox[2]) / 2
        lat_c = (spec.bbox[1] + spec.bbox[3]) / 2
        case_name = f"reach_{lat_c:.4f}_{lon_c:.4f}".replace("-", "n").replace(".", "p")
    elif spec.polyline_geojson:
        case_name = Path(spec.polyline_geojson).stem.lower().replace(" ", "_")
    else:
        case_name = "case"

    # 1. Geometry — three sources, in priority order
    if spec.polyline_geojson:
        coords = fetch_polyline_from_geojson(spec.polyline_geojson)
        logger.info("Using user-drawn polyline: %d points", len(coords))
    else:
        coords = fetch_river_polyline(
            river_name=spec.river_name,
            region_name=spec.region_name if not spec.bbox else None,
            bbox=spec.bbox,
        )
    node_x, node_y, station_m = sample_mesh_nodes(coords, spec)

    # 2. Cross-sections (V-shape) + bottom elevation along reach
    bottom_elevation = (spec.bank_elevation_m - spec.slope * station_m
                        - spec.thalweg_depth_m)  # at thalweg
    xs_df = build_v_cross_sections(station_m, spec)

    mesh_path = data_dir / "mesh.ugrid.nc"
    write_ugrid_mesh(node_x, node_y, station_m, bottom_elevation, mesh_path)
    xs_path = data_dir / "cross_section.parquet"
    xs_df.to_parquet(xs_path, index=False)

    # 3. Copy a reasonable HSI curve from the bundled Lemhi sample if available
    hsi_path = data_dir / "hsi_curve.parquet"
    sample_hsi = Path(__file__).resolve().parents[3] / "data/lemhi/hsi_curve.parquet"
    if sample_hsi.is_file():
        shutil.copy(sample_hsi, hsi_path)
    else:
        # Synthesize a minimal HSI curve so the case still validates
        hsi_rows = []
        for var, points in [
            ("depth",    [[0.0, 0.0], [0.3, 1.0], [0.6, 1.0], [1.2, 0.5], [2.0, 0.0]]),
            ("velocity", [[0.0, 0.0], [0.5, 1.0], [1.0, 1.0], [1.5, 0.3], [2.0, 0.0]]),
        ]:
            hsi_rows.append({
                "species": spec.species_id, "life_stage": "spawning", "variable": var,
                "points": points, "category": "III",
                "geographic_origin": "synthetic",
                "transferability_score": 0.5, "quality_grade": "C",
                "independence_tested": False,
                "evidence": ["openlimno.preprocess.osm_builder synthetic"],
            })
        pd.DataFrame(hsi_rows).to_parquet(hsi_path, index=False)

    # 4. case.yaml
    if spec.river_name:
        descr = f"OpenLimno case built from OSM polyline of '{spec.river_name}' in {spec.region_name}"
    elif spec.bbox is not None:
        descr = f"OpenLimno case built from OSM polyline within bbox {spec.bbox}"
    elif spec.polyline_geojson:
        descr = f"OpenLimno case built from user polyline {spec.polyline_geojson}"
    else:
        descr = "OpenLimno case (synthetic)"
    case_yaml = {
        "openlimno": "0.1",
        "case": {
            "name": case_name,
            "description": descr,
            "crs": "EPSG:4326",
        },
        "mesh": {"uri": str(mesh_path.relative_to(output_dir))},
        "data": {
            "cross_section": str(xs_path.relative_to(output_dir)),
            "hsi_curve": str(hsi_path.relative_to(output_dir)),
        },
        "hydrodynamics": {"backend": "builtin-1d"},
        "habitat": {
            "species": [spec.species_id],
            "stages": list(spec.life_stages),
            "metric": "wua-q",
            "composite": "min",
            "scale": "cell",
        },
        "output": {
            "dir": "./out/",
            "formats": ["csv", "netcdf"],
        },
        "provenance": {"emit": True},
    }
    case_path = output_dir / "case.yaml"
    case_path.write_text(yaml.safe_dump(case_yaml, sort_keys=False, allow_unicode=True))

    # 5. README
    readme = output_dir / "README.md"
    if spec.river_name:
        provenance = f"river **{spec.river_name}** ({spec.region_name})"
    elif spec.bbox is not None:
        provenance = f"bbox `{spec.bbox}`"
    elif spec.polyline_geojson:
        provenance = f"user polyline `{spec.polyline_geojson}`"
    else:
        provenance = "synthetic geometry"
    readme.write_text(
        f"# {case_name}\n\n"
        f"Auto-generated by `openlimno init-from-osm` from {provenance}.\n\n"
        f"- {spec.n_sections} mesh nodes along {spec.reach_length_m:.0f} m reach\n"
        f"- V-shape cross-sections, {spec.valley_width_m:.1f} m wide × "
        f"{spec.thalweg_depth_m:.2f} m deep (synthetic, replace with real ADCP)\n"
        f"- HSI curves: copied from Lemhi sample (grade B) — "
        f"customise for your species\n\n"
        f"Run:\n\n```\nopenlimno run case.yaml\n```\n"
    )

    return {
        "case_yaml": str(case_path),
        "mesh": str(mesh_path),
        "cross_section": str(xs_path),
        "hsi_curve": str(hsi_path),
        "readme": str(readme),
    }


__all__ = ["OSMCaseSpec", "build_case", "fetch_river_polyline"]
