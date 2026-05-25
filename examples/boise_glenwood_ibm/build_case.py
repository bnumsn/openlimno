"""Build a real-data IBM example for Boise River at Glenwood Bridge.

The script downloads public USGS data and writes a complete OpenLimno IBM
case under this example directory:

* USGS NWIS daily mean discharge for station 13206000
* USGS National Hydrography Dataset river area and flowline GeoJSON
* Derived habitat-cell forcing clipped to the NHD river boundary

Hydraulic depth, velocity, and cover are screening-level derivations from
the observed discharge and NHD geometry. They are not a substitute for a
site-calibrated hydraulic model.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Polygon
from shapely.ops import linemerge, unary_union
from shapely.validation import make_valid

from openlimno.hydro import build_builtin1d_gis_hydraulics

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
GIS_DIR = DATA_DIR / "gis"

STATION_ID = "13206000"
SITE_NAME = "BOISE RIVER AT GLENWOOD BRIDGE NR BOISE ID"
START_DATE = "2025-10-01"
END_DATE = "2025-10-14"
START_DAY_OF_YEAR = 274
REACH_ID = "boise-glenwood-nhd-120008049"
NHD_WBAREA_ID = "120008049"
FLOWLINE_BBOX = "-116.35,43.55,-116.05,43.75"
NWIS_BASE = "https://waterservices.usgs.gov/nwis/dv/"
NHD_BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"
FT3S_TO_M3S = 0.028316846592


def _json_get(url: str, params: dict[str, str]) -> tuple[dict[str, Any], str]:
    full_url = f"{url}?{urlencode(params)}"
    request = Request(
        full_url,
        headers={
            "User-Agent": "OpenLimno real-data example builder "
            "(https://github.com/openlimno/openlimno)"
        },
    )
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8")), full_url


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _property_ci(properties: dict[str, Any], key: str) -> Any:
    key_lower = key.lower()
    for name, value in properties.items():
        if name.lower() == key_lower:
            return value
    return None


def _download_nwis(*, offline: bool) -> tuple[pd.DataFrame, dict[str, Any], str]:
    raw_path = RAW_DIR / f"nwis_{STATION_ID}_daily_{START_DATE}_{END_DATE}.json"
    params = {
        "format": "json",
        "sites": STATION_ID,
        "startDT": START_DATE,
        "endDT": END_DATE,
        "parameterCd": "00060",
        "statCd": "00003",
        "siteStatus": "all",
    }
    if offline:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
        source_url = f"{NWIS_BASE}?{urlencode(params)}"
    else:
        data, source_url = _json_get(NWIS_BASE, params)
        _write_json(raw_path, data)

    series = data["value"]["timeSeries"][0]
    source_info = series["sourceInfo"]
    site_code = source_info["siteCode"][0]["value"]
    location = source_info["geoLocation"]["geogLocation"]
    values = series["values"][0]["value"]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        discharge_ft3s = float(item["value"])
        qualifiers = ",".join(str(q) for q in item.get("qualifiers", []))
        rows.append(
            {
                "time_index": index,
                "date": item["dateTime"][:10],
                "discharge_ft3s": discharge_ft3s,
                "discharge_m3s": discharge_ft3s * FT3S_TO_M3S,
                "qualifier": qualifiers,
            }
        )
    flow = pd.DataFrame(rows)
    flow.to_csv(DATA_DIR / "flow_daily.csv", index=False)
    metadata = {
        "station_id": site_code,
        "site_name": source_info.get("siteName", SITE_NAME),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "parameter": "00060 daily mean discharge",
        "statistic": "00003 mean",
        "unit": series["variable"]["unit"]["unitCode"],
        "start_date": START_DATE,
        "end_date": END_DATE,
    }
    return flow, metadata, source_url


def _download_nhd(*, offline: bool) -> tuple[Path, Path, dict[str, str]]:
    area_path = GIS_DIR / f"boise_river_nhd_area_{NHD_WBAREA_ID}.geojson"
    flow_raw_path = RAW_DIR / f"nhd_boise_river_flowline_bbox_{NHD_WBAREA_ID}.geojson"
    flow_path = GIS_DIR / f"boise_river_nhd_flowline_{NHD_WBAREA_ID}.geojson"

    area_params = {
        "where": f"permanent_identifier='{NHD_WBAREA_ID}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    flow_params = {
        "where": "GNIS_NAME='Boise River'",
        "geometry": FLOWLINE_BBOX,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "returnExceededLimitFeatures": "true",
        "f": "geojson",
    }
    area_url = f"{NHD_BASE}/9/query?{urlencode(area_params)}"
    flow_url = f"{NHD_BASE}/6/query?{urlencode(flow_params)}"

    if offline:
        area_data = json.loads(area_path.read_text(encoding="utf-8"))
        flow_data = json.loads(flow_raw_path.read_text(encoding="utf-8"))
    else:
        area_data, area_url = _json_get(f"{NHD_BASE}/9/query", area_params)
        flow_data, flow_url = _json_get(f"{NHD_BASE}/6/query", flow_params)
        _write_json(area_path, area_data)
        _write_json(flow_raw_path, flow_data)

    if not area_data.get("features"):
        raise RuntimeError(f"NHD area {NHD_WBAREA_ID} returned no features")

    filtered_features = []
    for feature in flow_data.get("features", []):
        properties = feature.get("properties") or {}
        if str(_property_ci(properties, "wbarea_permanent_identifier")) == NHD_WBAREA_ID:
            filtered_features.append(feature)
    if not filtered_features:
        raise RuntimeError(
            "NHD flowline query returned no Boise River features linked to "
            f"waterbody area {NHD_WBAREA_ID}"
        )
    flow_filtered = {
        "type": "FeatureCollection",
        "features": filtered_features,
    }
    _write_json(flow_path, flow_filtered)
    return area_path, flow_path, {"nhd_area_url": area_url, "nhd_flowline_url": flow_url}


def _iter_lines(geometry: Any) -> Iterable[LineString]:
    if isinstance(geometry, LineString):
        yield geometry
    elif isinstance(geometry, MultiLineString):
        yield from geometry.geoms
    elif isinstance(geometry, GeometryCollection):
        for part in geometry.geoms:
            yield from _iter_lines(part)


def _iter_polygons(geometry: Any) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _iter_polygons(part)


def _longest_line(geometry: Any) -> LineString:
    lines = [line for line in _iter_lines(geometry) if not line.is_empty and line.length > 0]
    if not lines:
        raise RuntimeError("No usable line geometry was found")
    return max(lines, key=lambda line: line.length)


def _largest_polygon(geometry: Any) -> Polygon | None:
    polygons = [poly for poly in _iter_polygons(geometry) if not poly.is_empty and poly.area > 0]
    if not polygons:
        return None
    return max(polygons, key=lambda poly: poly.area)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _triangular(value: float, *, low: float, optimum: float, high: float) -> float:
    if value <= low or value >= high:
        return 0.0
    if value <= optimum:
        return (value - low) / max(optimum - low, 1e-9)
    return (high - value) / max(high - optimum, 1e-9)


def _estimate_habitat_type(depth_m: float, velocity_ms: float, width_m: float, median_width: float) -> str:
    if width_m < median_width * 0.72:
        return "margin"
    if depth_m > 0.78 and velocity_ms < 0.45:
        return "pool"
    if velocity_ms > 0.72:
        return "riffle"
    return "run"


def _make_strip(line: LineString, station_m: float, half_length_m: float, half_width_m: float) -> Polygon:
    before = line.interpolate(max(0.0, station_m - min(half_length_m, 30.0)))
    after = line.interpolate(min(line.length, station_m + min(half_length_m, 30.0)))
    dx = after.x - before.x
    dy = after.y - before.y
    length = math.hypot(dx, dy)
    if length <= 0:
        dx, dy, length = 1.0, 0.0, 1.0
    tx, ty = dx / length, dy / length
    nx, ny = -ty, tx
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


def _build_habitat_cells(
    *,
    area_path: Path,
    flowline_path: Path,
    flow: pd.DataFrame,
    n_cells: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    area = gpd.read_file(area_path)
    flowline = gpd.read_file(flowline_path)
    if area.crs is None:
        area = area.set_crs("EPSG:4326")
    if flowline.crs is None:
        flowline = flowline.set_crs("EPSG:4326")
    utm_crs = area.estimate_utm_crs() or "EPSG:32611"
    area_m = area.to_crs(utm_crs)
    flowline_m = flowline.to_crs(utm_crs)

    boundary = make_valid(unary_union(area_m.geometry))
    merged_line = linemerge(unary_union(flowline_m.geometry))
    centerline = _longest_line(merged_line.intersection(boundary.buffer(5.0)))

    reach_length_m = centerline.length
    if reach_length_m <= 0:
        raise RuntimeError("NHD centerline has zero length after clipping to river boundary")
    base_width_m = boundary.area / reach_length_m
    cell_spacing_m = reach_length_m / n_cells
    half_width_m = _clip(base_width_m * 4.0, 55.0, 260.0)

    static_records: list[dict[str, Any]] = []
    static_geometries: list[Polygon] = []
    for i in range(n_cells):
        station_m = (i + 0.5) * cell_spacing_m
        strip = _make_strip(centerline, station_m, cell_spacing_m * 0.58, half_width_m)
        clipped = make_valid(strip.intersection(boundary))
        polygon = _largest_polygon(clipped)
        if polygon is None:
            fallback = centerline.interpolate(station_m).buffer(max(base_width_m * 0.5, 5.0))
            polygon = _largest_polygon(make_valid(fallback.intersection(boundary)))
        if polygon is None or polygon.area <= 1.0:
            continue
        representative = polygon.representative_point()
        width_m = polygon.area / max(cell_spacing_m, 1.0)
        static_records.append(
            {
                "cell_id": f"boise-glenwood-{len(static_records) + 1:03d}",
                "reach_id": REACH_ID,
                "reach_order": 1,
                "station_m": round(station_m, 2),
                "center_x_m": round(representative.x, 2),
                "center_y_m": round(representative.y, 2),
                "length_m": round(cell_spacing_m, 2),
                "width_m": round(width_m, 2),
                "area_m2": round(polygon.area, 2),
            }
        )
        static_geometries.append(polygon)
    if len(static_records) < 3:
        raise RuntimeError("Too few habitat cells were generated from the NHD boundary")

    static = pd.DataFrame(static_records)
    median_width = float(static["width_m"].median())
    median_q = float(flow["discharge_m3s"].median())
    forcing_rows: list[dict[str, Any]] = []
    for _, flow_row in flow.iterrows():
        time_index = int(flow_row["time_index"])
        q_m3s = float(flow_row["discharge_m3s"])
        discharge_factor = (q_m3s / median_q) ** 0.42 if median_q > 0 else 1.0
        temperature_c = 10.7 + 0.75 * math.sin((time_index / max(len(flow) - 1, 1)) * math.pi)
        for cell_index, cell in static.iterrows():
            morph = 1.0 + 0.22 * math.sin((cell_index + 1) * 1.73)
            depth_m = _clip(0.55 * discharge_factor * morph, 0.16, 1.85)
            width_m = max(float(cell["width_m"]), 1.0)
            velocity_morph = 1.0 + 0.28 * math.cos((cell_index + 1) * 1.21)
            velocity_ms = _clip(q_m3s / max(width_m * depth_m, 1.0) * velocity_morph, 0.04, 1.65)
            depth_si = _triangular(depth_m, low=0.05, optimum=0.65, high=2.5)
            velocity_si = _triangular(velocity_ms, low=0.0, optimum=0.35, high=1.8)
            csi = _clip(math.sqrt(depth_si * velocity_si), 0.0, 1.0)
            habitat_type = _estimate_habitat_type(depth_m, velocity_ms, width_m, median_width)
            margin_cover = 0.18 if habitat_type == "margin" else 0.0
            hiding_cover = _clip(0.18 + margin_cover + 0.24 * (width_m / max(median_width, 1.0)), 0.05, 0.75)
            feeding_cover = _clip(0.18 + 0.35 * csi + 0.10 * (1.0 - min(velocity_ms, 1.0)), 0.05, 0.80)
            spawning_cover = _clip(
                0.12
                + 0.55 * _triangular(velocity_ms, low=0.08, optimum=0.45, high=1.1)
                * _triangular(depth_m, low=0.08, optimum=0.45, high=1.2),
                0.02,
                0.70,
            )
            forcing_rows.append(
                {
                    "time_index": time_index,
                    "date": flow_row["date"],
                    "cell_id": cell["cell_id"],
                    "reach_id": cell["reach_id"],
                    "reach_order": int(cell["reach_order"]),
                    "station_m": float(cell["station_m"]),
                    "area_m2": float(cell["area_m2"]),
                    "width_m": width_m,
                    "depth_m": round(depth_m, 4),
                    "velocity_ms": round(velocity_ms, 4),
                    "csi": round(csi, 4),
                    "temperature_c": round(temperature_c, 3),
                    "turbidity_ntu": 2.0,
                    "hiding_cover": round(hiding_cover, 4),
                    "feeding_cover": round(feeding_cover, 4),
                    "spawning_cover": round(spawning_cover, 4),
                    "discharge_m3s": round(q_m3s, 6),
                    "habitat_type": habitat_type,
                    "hydraulic_note": "derived_from_nwis_flow_and_nhd_geometry",
                }
            )

    forcing = pd.DataFrame(forcing_rows)
    forcing.to_csv(DATA_DIR / "habitat_cells.csv", index=False)

    static_geo = gpd.GeoDataFrame(static.copy(), geometry=static_geometries, crs=utm_crs).to_crs("EPSG:4326")
    daily_mean = (
        forcing.groupby("cell_id", as_index=False)[
            ["depth_m", "velocity_ms", "csi", "temperature_c", "hiding_cover", "feeding_cover", "spawning_cover"]
        ]
        .mean()
        .round(4)
    )
    static_geo = static_geo.merge(daily_mean, on="cell_id", how="left")
    static_geo["source"] = "NHD area 120008049 clipped habitat cells; attributes derived from NWIS daily flow"
    static_geo.to_file(GIS_DIR / "habitat_cells.geojson", driver="GeoJSON")
    static.to_csv(DATA_DIR / "habitat_cells_static.csv", index=False)

    diagnostics = {
        "crs_projected": str(utm_crs),
        "nhd_area_m2": round(float(boundary.area), 2),
        "centerline_length_m": round(float(reach_length_m), 2),
        "estimated_mean_width_m": round(float(base_width_m), 2),
        "habitat_cell_count": int(len(static)),
        "forcing_row_count": int(len(forcing)),
        "discharge_m3s_min": round(float(flow["discharge_m3s"].min()), 6),
        "discharge_m3s_max": round(float(flow["discharge_m3s"].max()), 6),
    }
    return static, forcing, diagnostics


def _write_profile() -> None:
    profile = {
        "profile_version": "0.2",
        "species": {
            "id": "rainbow_trout",
            "scientific_name": "Oncorhynchus mykiss",
            "common_name": "Rainbow trout",
            "evidence_status": "screening profile; defaults aligned to native OpenLimno IBM",
        },
        "parameters": {
            "thermal_min_c": {"value": 1.0, "source": "OpenLimno native IBM default"},
            "thermal_optimum_c": {"value": 12.0, "source": "OpenLimno native IBM default"},
            "thermal_max_c": {"value": 23.0, "source": "OpenLimno native IBM default"},
            "base_daily_survival": {"value": 0.997, "source": "OpenLimno native IBM default"},
            "carrying_density_per_m2": {"value": 0.08, "source": "OpenLimno native IBM default"},
            "maturity_length_mm": {"value": 120.0, "source": "OpenLimno native IBM default"},
            "spawn_start_day": {"value": 90, "source": "OpenLimno native IBM default"},
            "spawn_end_day": {"value": 150, "source": "OpenLimno native IBM default"},
        },
        "calibration": {
            "accepted": False,
            "notes": (
                "Demonstration profile for the Boise Glenwood real-data example. "
                "Use local monitoring and calibration before management decisions."
            ),
        },
    }
    (EXAMPLE_DIR / "profile_rainbow_trout.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False),
        encoding="utf-8",
    )


def _write_initial_population(static: pd.DataFrame) -> None:
    rng = random.Random(13206000)
    cell_ids = static["cell_id"].tolist()
    rows: list[dict[str, Any]] = []
    for fish_id in range(180):
        length_mm = _clip(rng.gauss(115.0, 22.0), 45.0, 210.0)
        mass_g = 0.0115 * (length_mm / 10.0) ** 3.0
        rows.append(
            {
                "fish_id": fish_id,
                "species": "rainbow_trout",
                "age_days": int(_clip(rng.gauss(365.0, 120.0), 90.0, 900.0)),
                "length_mm": round(length_mm, 3),
                "mass_g": round(mass_g, 5),
                "cell_id": rng.choice(cell_ids),
                "alive": True,
            }
        )
    pd.DataFrame(rows).to_csv(DATA_DIR / "initial_population.csv", index=False)


def _write_scenario() -> None:
    scenario = {
        "ibm_version": "0.2",
        "scenario": {
            "id": "boise-glenwood-rainbow-trout-real-data",
            "description": (
                "Rainbow trout IBM screening example using USGS NWIS discharge "
                "and NHD river boundary/flowline at Boise River Glenwood Bridge."
            ),
            "reach_id": REACH_ID,
            "days": 14,
            "start_day": START_DAY_OF_YEAR,
            "start_year": 2025,
            "seed": 13206000,
            "stochastic": True,
            "light_phases": ["dawn", "day", "dusk", "night"],
        },
        "profile": {"uri": "profile_rainbow_trout.yaml"},
        "forcing": {
            "habitat_cells": "data/hydraulics/hydraulic_cells.csv",
            "time_index_column": "time_index",
        },
        "population": {
            "initial_population": "data/initial_population.csv",
            "default_species": "rainbow_trout",
            "initial_abundance": 180,
            "initial_length_mm": 115.0,
        },
        "outputs": {
            "dir": "out/native",
            "formats": ["csv"],
            "individual_history": True,
            "manifest": True,
        },
    }
    (EXAMPLE_DIR / "scenario.yaml").write_text(
        yaml.safe_dump(scenario, sort_keys=False),
        encoding="utf-8",
    )


def _write_manifest(
    *,
    nwis_metadata: dict[str, Any],
    nwis_url: str,
    nhd_urls: dict[str, str],
    diagnostics: dict[str, Any],
    hydraulics_manifest: Path,
) -> None:
    manifest = {
        "case_id": "boise_glenwood_ibm",
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "description": "OpenLimno IBM real-data example for Boise River at Glenwood Bridge.",
        "nwis": {
            **nwis_metadata,
            "url": nwis_url,
        },
        "nhd": {
            "river_area_permanent_identifier": NHD_WBAREA_ID,
            "area_url": nhd_urls["nhd_area_url"],
            "flowline_url": nhd_urls["nhd_flowline_url"],
            "bbox": FLOWLINE_BBOX,
        },
        "diagnostics": diagnostics,
        "hydraulics": {
            "solver": "builtin-1d",
            "manifest": str(hydraulics_manifest.relative_to(EXAMPLE_DIR)),
            "forcing": "data/hydraulics/hydraulic_cells.csv",
            "calibration_template": "data/hydraulics/calibration_observed_template.csv",
        },
        "limitations": [
            "NHD provides river geometry, not surveyed hydraulic mesh.",
            "Builtin1D depth/velocity uses generated cross-sections unless a DEM is supplied.",
            "Use local hydraulic calibration before regulatory or management decisions.",
        ],
    }
    _write_json(DATA_DIR / "source_manifest.json", manifest)


def build_case(*, offline: bool, n_cells: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    GIS_DIR.mkdir(parents=True, exist_ok=True)
    flow, nwis_metadata, nwis_url = _download_nwis(offline=offline)
    area_path, flowline_path, nhd_urls = _download_nhd(offline=offline)
    static, _forcing, diagnostics = _build_habitat_cells(
        area_path=area_path,
        flowline_path=flowline_path,
        flow=flow,
        n_cells=n_cells,
    )
    hydraulic_result = build_builtin1d_gis_hydraulics(
        boundary_path=area_path,
        centerline_path=flowline_path,
        out_dir=DATA_DIR / "hydraulics",
        discharges_m3s=flow,
        n_cells=n_cells,
        manning_n=0.035,
        slope=0.001,
        output_format="csv",
    )
    _write_profile()
    _write_initial_population(static)
    _write_scenario()
    _write_manifest(
        nwis_metadata=nwis_metadata,
        nwis_url=nwis_url,
        nhd_urls=nhd_urls,
        diagnostics=diagnostics,
        hydraulics_manifest=hydraulic_result.manifest_path,
    )
    print(json.dumps(diagnostics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Reuse downloaded raw files instead of calling USGS services.",
    )
    parser.add_argument("--cells", type=int, default=12, help="Number of longitudinal habitat cells.")
    args = parser.parse_args()
    if args.cells < 3:
        raise SystemExit("--cells must be at least 3")
    build_case(offline=args.offline, n_cells=args.cells)


if __name__ == "__main__":
    main()
