"""Watershed-aware climate aggregator (v1.2.0).

The v0.3.1 / v0.3.2 climate fetchers (Daymet, Open-Meteo) pull
**single-point** time series — one (lat, lon) per call. For
reach-scale fish-ecology work that's usually adequate (the climate
gradient across a 1-10 km reach is dwarfed by the cross-source
uncertainty in the air→water Stefan transform).

Catchment-scale work is different: a HydroSHEDS watershed that spans
500-5000 km² will have a non-trivial climate gradient (lapse rate,
maritime → continental, shadowed slopes). Reporting a single-point
climate as "the basin climate" is misleading. v1.2.0 adds a 5-point
samples-and-aggregates wrapper:

* Sample the climate at the watershed centroid + 4 bbox corners.
* Average to a regional time series + carry per-day SD as a
  confidence proxy.

5 points is the smallest count that captures both N-S and E-W
gradients in one pass. For finer work (≥ 10 points or a real grid
intersection) a future v1.3+ enhancement can extend
:func:`watershed_sample_points` while keeping the same return shape.

The aggregator is reach-source-agnostic: pass any one-point fetcher
that returns a DataFrame with ``T_water_C_stefan`` (or another named
column) and we'll spread it over the watershed.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# Source-agnostic interface: a callable that takes (lat, lon, sy, ey)
# and returns an object with a ``.df`` DataFrame containing a daily
# climate series. Both :func:`fetch_daymet_daily` and
# :func:`fetch_open_meteo_daily` already satisfy this protocol.
ClimateFetcher = Callable[[float, float, int, int], object]


@dataclass
class WatershedClimateResult:
    """Outcome of a watershed-aggregated climate fetch.

    Attributes:
        df: long-form DataFrame with columns
            ``[time, T_water_C_mean, T_water_C_sd, n_samples,
            T_air_C_mean, prcp_mm_total]`` (the last two are only
            populated if the underlying fetcher produced them).
            ``time`` is ``YYYY-MM-DD``.
        sample_points: list of (lat, lon) actually sampled.
        watershed_bbox: ``(lon_min, lat_min, lon_max, lat_max)``
            of the watershed.
        per_point_results: the individual single-point fetcher
            results, kept around so the caller can audit the
            spread without re-fetching.
        citation: citation string from the underlying fetcher.
    """

    df: pd.DataFrame
    sample_points: list[tuple[float, float]]
    watershed_bbox: tuple[float, float, float, float]
    per_point_results: list[object] = field(default_factory=list)
    citation: str = ""


def watershed_sample_points(
    bbox: tuple[float, float, float, float],
    *,
    inset_fraction: float = 0.1,
) -> list[tuple[float, float]]:
    """Pick 5 sample points (lat, lon) inside a watershed bbox.

    The corners are inset by ``inset_fraction`` of each side so a tile
    grid that aligns exactly to the bbox doesn't put a sample on the
    seam between two source tiles (Daymet / Open-Meteo grid origin is
    not bbox-aware). 10 % default keeps the inset large enough to
    stay safely inside the catchment perimeter for typical
    HydroSHEDS L12 polygons.

    Returns:
        ``[(lat, lon), ...]`` of length 5: centroid + 4 inset corners.
    """
    if not 0.0 <= inset_fraction < 0.5:
        raise ValueError(
            f"inset_fraction={inset_fraction} must be in [0, 0.5)"
        )
    lo_min, la_min, lo_max, la_max = bbox
    if lo_max <= lo_min or la_max <= la_min:
        raise ValueError(
            f"Invalid bbox: {bbox}. Need lon_max>lon_min, lat_max>lat_min."
        )
    dx = (lo_max - lo_min) * inset_fraction
    dy = (la_max - la_min) * inset_fraction
    centroid = ((la_min + la_max) / 2.0, (lo_min + lo_max) / 2.0)
    corners = [
        (la_min + dy, lo_min + dx),
        (la_min + dy, lo_max - dx),
        (la_max - dy, lo_min + dx),
        (la_max - dy, lo_max - dx),
    ]
    return [centroid, *corners]


def _watershed_bbox_from_geojson(
    geojson_path: Path | str,
) -> tuple[float, float, float, float]:
    """Compute (lon_min, lat_min, lon_max, lat_max) of all
    coordinates in a watershed GeoJSON file. Walks every position
    tuple — no shapely / geopandas dependency.
    """
    data = json.loads(Path(geojson_path).read_text())
    lons: list[float] = []
    lats: list[float] = []

    def _walk(coords: object) -> None:
        # Position is [lon, lat] or [lon, lat, z]; anything else is a
        # nested ring / polygon / multipolygon list.
        if (
            isinstance(coords, list)
            and len(coords) >= 2
            and all(isinstance(v, (int, float)) for v in coords[:2])
        ):
            lons.append(float(coords[0]))
            lats.append(float(coords[1]))
            return
        if isinstance(coords, list):
            for inner in coords:
                _walk(inner)

    if data.get("type") == "FeatureCollection":
        for feat in data.get("features", []):
            _walk(feat.get("geometry", {}).get("coordinates", []))
    elif data.get("type") == "Feature":
        _walk(data.get("geometry", {}).get("coordinates", []))
    else:
        _walk(data.get("coordinates", []))

    if not lons or not lats:
        raise ValueError(
            f"No coordinates found in {geojson_path}; not a "
            f"valid GeoJSON watershed."
        )
    return (min(lons), min(lats), max(lons), max(lats))


def fetch_watershed_climate(
    watershed_geojson: Path | str,
    fetcher: ClimateFetcher,
    start_year: int,
    end_year: int,
    *,
    inset_fraction: float = 0.1,
) -> WatershedClimateResult:
    """Aggregate a one-point climate fetcher over a watershed.

    Args:
        watershed_geojson: path to the GeoJSON produced by
            :func:`write_watershed_geojson` (any GeoJSON with a
            recoverable bbox works).
        fetcher: one-point climate fetcher. Must accept
            ``(lat, lon, start_year, end_year)`` and return an object
            with a ``.df`` DataFrame containing at minimum
            ``time`` + ``T_water_C_stefan`` columns. Both
            :func:`fetch_daymet_daily` and
            :func:`fetch_open_meteo_daily` satisfy this protocol.
        start_year, end_year: same semantics as the underlying fetcher.
        inset_fraction: corner-inset for the 5-point sample.

    Returns:
        :class:`WatershedClimateResult` with the daily mean + SD
        across the 5 sample points + the per-point raw results.
    """
    bbox = _watershed_bbox_from_geojson(watershed_geojson)
    points = watershed_sample_points(bbox, inset_fraction=inset_fraction)
    raw_results: list[object] = []
    per_point_frames: list[pd.DataFrame] = []
    for lat, lon in points:
        res = fetcher(lat, lon, start_year, end_year)
        df = getattr(res, "df", None)
        if df is None or "time" not in df.columns:
            raise RuntimeError(
                f"fetcher returned no `.df` or no `time` column at "
                f"point ({lat:.4f}, {lon:.4f}); cannot aggregate."
            )
        if "T_water_C_stefan" not in df.columns:
            raise RuntimeError(
                f"fetcher's `.df` lacks `T_water_C_stefan` at point "
                f"({lat:.4f}, {lon:.4f}); columns: {list(df.columns)}"
            )
        raw_results.append(res)
        per_point_frames.append(df)

    # Stack to a (n_days × n_points) matrix on each available column.
    times = per_point_frames[0]["time"].values
    n_days = len(times)
    n_pts = len(per_point_frames)
    t_water = np.zeros((n_days, n_pts), dtype=float)
    for i, df in enumerate(per_point_frames):
        if len(df) != n_days:
            raise RuntimeError(
                f"fetcher returned different-length series across "
                f"points (point {i}: {len(df)} vs reference {n_days}); "
                f"cannot align."
            )
        t_water[:, i] = df["T_water_C_stefan"].astype(float).values

    out_df = pd.DataFrame({
        "time": times,
        "T_water_C_mean": t_water.mean(axis=1),
        "T_water_C_sd": t_water.std(axis=1, ddof=0),
        "n_samples": np.full(n_days, n_pts, dtype=int),
    })

    # Optional columns the underlying fetcher may carry.
    if "T_air_C_mean" in per_point_frames[0].columns:
        t_air = np.stack(
            [df["T_air_C_mean"].astype(float).values
             for df in per_point_frames], axis=1,
        )
        out_df["T_air_C_mean"] = t_air.mean(axis=1)
    if "prcp_mm" in per_point_frames[0].columns:
        prcp = np.stack(
            [df["prcp_mm"].astype(float).values
             for df in per_point_frames], axis=1,
        )
        out_df["prcp_mm_total"] = prcp.sum(axis=1)

    citation = getattr(raw_results[0], "citation", "")
    return WatershedClimateResult(
        df=out_df, sample_points=points, watershed_bbox=bbox,
        per_point_results=raw_results, citation=citation,
    )
