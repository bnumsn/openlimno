"""Copernicus GLO-30 DEM fetcher + cross-section cutter.

Copernicus GLO-30 is a free global 30 m DEM (84°N–84°S, no auth) hosted
as Cloud-Optimized GeoTIFF on a public AWS S3 bucket. We use rasterio's
``/vsicurl/`` GDAL driver to stream a bbox subset without downloading
whole 1°-tile files.

We avoid NASA Earthdata SRTM because it requires login; Copernicus has
the same resolution + better polar coverage with anonymous access.

Tile naming convention:
    s3://copernicus-dem-30m/Copernicus_DSM_COG_10_{Nxx|Sxx}_00_{Wxxx|Exxx}_00_DEM/
        Copernicus_DSM_COG_10_{...}_DEM.tif

Where the tile covers a 1°×1° patch centered at the named integer
lat/lon. We pick all tiles overlapping the user bbox and merge them
with rasterio.merge.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np
import rasterio
import rasterio.merge
import rasterio.warp
import rasterio.windows
from rasterio.io import MemoryFile

from openlimno.preprocess.fetch.cache import CacheEntry, cache_dir, cached_fetch

COP_S3_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"


@dataclass
class DEMFetchResult:
    """Outcome of a DEM fetch over a bbox.

    Attributes:
        path: local GeoTIFF holding the (possibly merged) bbox subset.
        bounds: (lon_min, lat_min, lon_max, lat_max) of returned raster.
        crs: GDAL CRS string (EPSG:4326 for Copernicus).
        n_tiles: number of 1°-tiles fetched/cached.
        cache_entries: provenance trail (one per tile).
    """

    path: Path
    bounds: tuple[float, float, float, float]
    crs: str
    n_tiles: int
    cache_entries: list[CacheEntry] = field(default_factory=list)


def _tile_name(lat_int: int, lon_int: int) -> str:
    """Build Copernicus tile prefix for the 1°×1° patch containing the
    integer (lat_int, lon_int) — *the SW corner* (S3 layout convention).
    """
    ns = f"N{lat_int:02d}" if lat_int >= 0 else f"S{-lat_int:02d}"
    ew = f"E{lon_int:03d}" if lon_int >= 0 else f"W{-lon_int:03d}"
    stem = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
    return stem


def _tiles_for_bbox(
    lon_min: float, lat_min: float, lon_max: float, lat_max: float
) -> list[tuple[int, int]]:
    """Return the (lat_int, lon_int) SW corners of all 1°-tiles touching
    the bbox. Copernicus tile (Nxx, Wxxx) covers [xx, xx+1) × [-xxx, -xxx+1).
    """
    out: list[tuple[int, int]] = []
    for la in range(int(math.floor(lat_min)), int(math.floor(lat_max)) + 1):
        for lo in range(int(math.floor(lon_min)), int(math.floor(lon_max)) + 1):
            out.append((la, lo))
    return out


def fetch_copernicus_dem(
    lon_min: float, lat_min: float, lon_max: float, lat_max: float,
    out_path: str | Path | None = None,
) -> DEMFetchResult:
    """Fetch Copernicus GLO-30 DEM over a lat/lon bbox.

    Streams 1°-tiles from the public AWS S3 mirror via ``/vsicurl/``,
    crops each to the bbox, then merges. Per-tile cached locally so
    repeat fetches with overlapping bboxes are fast.

    Args:
        lon_min, lat_min, lon_max, lat_max: bbox in EPSG:4326 (decimal
            degrees, lon negative for W).
        out_path: where to write the merged GeoTIFF. Defaults to a path
            inside the openlimno cache.

    Returns:
        ``DEMFetchResult`` with path to merged GeoTIFF + provenance.
    """
    if lon_max <= lon_min or lat_max <= lat_min:
        raise ValueError(
            f"Invalid DEM bbox: lon_min={lon_min} lon_max={lon_max} "
            f"lat_min={lat_min} lat_max={lat_max}. Need lon_max > lon_min, "
            f"lat_max > lat_min."
        )
    if not (-84 < lat_min and lat_max < 84):
        raise ValueError(
            f"DEM bbox extends outside Copernicus GLO-30 coverage "
            f"(84°S to 84°N). Got lat_min={lat_min}, lat_max={lat_max}. "
            f"For polar areas, use a different DEM source (not yet wired)."
        )
    # Memory guard: each 30m tile is 3600×3600 px × 4 B = 51 MB raw +
    # ~2× during merge. A 10°×10° bbox = 121 tiles → ~12 GB peak. A
    # CONUS-sized bbox would OOMkill the process. Cap at MAX_BBOX_DEG²
    # of total area; v0.3 P0 targets reach-scale cases (a few km).
    MAX_BBOX_DEG2 = 9.0  # ≈ 3°×3° max, ~100 tiles peak
    bbox_area = (lon_max - lon_min) * (lat_max - lat_min)
    if bbox_area > MAX_BBOX_DEG2:
        raise ValueError(
            f"DEM bbox area {bbox_area:.2f} deg² exceeds the safety cap "
            f"of {MAX_BBOX_DEG2:.0f} deg² (~100 tiles, ~5 GB peak). "
            f"OpenLimno targets reach-scale cases; for continent-scale "
            f"DEM mosaics use a dedicated tool like `eio` (elevation) "
            f"or GDAL's `gdal_merge` directly."
        )

    tile_corners = _tiles_for_bbox(lon_min, lat_min, lon_max, lat_max)

    tile_paths: list[Path] = []
    cache_entries: list[CacheEntry] = []
    for la, lo in tile_corners:
        stem = _tile_name(la, lo)
        tile_url = f"{COP_S3_BASE}/{stem}/{stem}.tif"
        # Bbox MUST be in the cache key — same tile + different bbox =
        # different subset, otherwise a later call with a larger bbox
        # would reuse the smaller earlier subset and silently produce
        # mostly-zero rasters outside the original window.
        tile_params = {
            "lon_min": round(lon_min, 6), "lat_min": round(lat_min, 6),
            "lon_max": round(lon_max, 6), "lat_max": round(lat_max, 6),
        }
        try:
            ce = cached_fetch(
                subdir="dem/copernicus",
                url=tile_url,
                params=tile_params,
                suffix=".tif",
                fetch_fn=lambda u=tile_url: _stream_tile_subset(
                    u, lon_min, lat_min, lon_max, lat_max
                ),
            )
        except _TileNotFound:
            # Ocean tiles or missing — skip, real bbox might still have
            # land tiles.
            continue
        tile_paths.append(ce.path)
        cache_entries.append(ce)

    if not tile_paths:
        raise ValueError(
            f"No Copernicus DEM tiles available for bbox "
            f"({lon_min}, {lat_min}, {lon_max}, {lat_max}). All overlapping "
            f"tiles are ocean / missing. Verify the bbox is over land."
        )

    # Merge tile subsets
    srcs = [rasterio.open(p) for p in tile_paths]
    try:
        mosaic, out_transform = rasterio.merge.merge(
            srcs, bounds=(lon_min, lat_min, lon_max, lat_max)
        )
        out_meta = srcs[0].meta.copy()
        out_meta.update(
            {
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_transform,
            }
        )
    finally:
        for s in srcs:
            s.close()

    if out_path is None:
        out_path = cache_dir("dem") / (
            f"cop30_merge_{lon_min:.4f}_{lat_min:.4f}_"
            f"{lon_max:.4f}_{lat_max:.4f}.tif"
        )
    out_path = Path(out_path)
    with rasterio.open(out_path, "w", **out_meta) as dst:
        dst.write(mosaic)

    return DEMFetchResult(
        path=out_path,
        bounds=(lon_min, lat_min, lon_max, lat_max),
        crs="EPSG:4326",
        n_tiles=len(tile_paths),
        cache_entries=cache_entries,
    )


class _TileNotFound(Exception):
    """Internal: tile doesn't exist (e.g., ocean cell)."""


def _stream_tile_subset(
    tile_url: str, lon_min: float, lat_min: float, lon_max: float, lat_max: float
) -> bytes:
    """Pull a bbox window from a remote COG via /vsicurl/, return GeoTIFF bytes."""
    vsi_url = f"/vsicurl/{tile_url}"
    try:
        src = rasterio.open(vsi_url)
    except rasterio.errors.RasterioIOError as e:
        raise _TileNotFound(str(e)) from e
    try:
        # Compute window from bbox
        window = rasterio.windows.from_bounds(
            lon_min, lat_min, lon_max, lat_max, src.transform
        )
        # Round to integer pixels (rasterio 1.5: keyword-only op) + clamp.
        window = window.round_offsets(op="floor").round_lengths(op="ceil")
        full_window = rasterio.windows.Window(0, 0, src.width, src.height)
        try:
            window = window.intersection(full_window)
        except rasterio.errors.WindowError as e:
            # Bbox edge touches tile boundary but no real overlap — common
            # when ``lat_max`` equals the next tile's SW lat (math.floor
            # promotes it to the upper tile, which has zero overlap).
            raise _TileNotFound(
                f"Tile {tile_url} doesn't overlap bbox: {e}"
            ) from e
        if window.width <= 0 or window.height <= 0:
            raise _TileNotFound(
                f"Tile {tile_url} doesn't overlap bbox after pixel snap"
            )
        data = src.read(window=window)
        transform = src.window_transform(window)
        profile = src.profile.copy()
        profile.update(
            {
                "driver": "GTiff",
                "height": data.shape[1],
                "width": data.shape[2],
                "transform": transform,
            }
        )
        with MemoryFile() as mf:
            with mf.open(**profile) as dst:
                dst.write(data)
            return mf.read()
    finally:
        src.close()


def clip_centerline_to_bbox(
    centerline: Sequence[tuple[float, float]],
    lon_min: float, lat_min: float, lon_max: float, lat_max: float,
) -> list[tuple[float, float]]:
    """Restrict a (lon, lat) polyline to vertices inside a bbox.

    OSM's ``fetch_river_polyline`` returns the WHOLE waterway matched
    by a name/bbox query, not just the bbox slice — so a small
    case-area query against the Lemhi River yields 1000+ vertices
    spanning many degrees. Use this to clip back to the area of
    interest before xs-cutting.

    Returns vertices inside the bbox preserving original order. If
    fewer than 2 vertices remain, raises ``ValueError`` so the
    caller can fall back to a different reach selection.
    """
    out = [
        (lon, lat) for lon, lat in centerline
        if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max
    ]
    if len(out) < 2:
        raise ValueError(
            f"After clipping to bbox ({lon_min}, {lat_min}, {lon_max}, "
            f"{lat_max}), only {len(out)} centerline vertices remain. "
            f"Try a larger bbox or check that the bbox actually overlaps "
            f"the river."
        )
    return out


def cut_cross_sections_from_dem(
    dem_path: str | Path,
    centerline: Sequence[tuple[float, float]],
    n_sections: int = 11,
    section_width_m: float = 30.0,
    points_per_section: int = 21,
    campaign_id: str | None = None,
) -> "pd.DataFrame":
    """Cut perpendicular cross-sections from a DEM along a centerline.

    Produces a WEDM-shaped ``cross_section.parquet`` DataFrame ready
    for direct use by the case runner — replacing the V-section
    synthesis that ``init-from-osm`` currently does.

    Args:
        dem_path: a GeoTIFF in any CRS rasterio can read.
        centerline: ordered (lon, lat) vertices in EPSG:4326. Output of
            ``osm_builder.fetch_river_polyline``.
        n_sections: how many cross-sections to cut, evenly spaced along
            the centerline by arc length.
        section_width_m: total bank-to-bank width sampled.
        points_per_section: samples per cross-section (>= 5).
        campaign_id: WEDM campaign UUID (auto-generated if omitted).
    """
    import uuid as _uuid

    import pandas as pd

    if campaign_id is None:
        campaign_id = str(_uuid.uuid4())
    if points_per_section < 5:
        raise ValueError("points_per_section must be >= 5")
    if len(centerline) < 2:
        raise ValueError("centerline must have at least 2 vertices")

    centerline = np.asarray(centerline, dtype=float)  # (N, 2) lon, lat

    # Cumulative arc length in METERS — convert lat/lon segments to
    # local-tangent meters via small-angle approximation (good to <1 m
    # for typical 1-km reaches).
    lat_mean = float(np.mean(centerline[:, 1]))
    m_per_deg_lat = 111_132.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_mean))
    seg_m = np.zeros(len(centerline))
    for i in range(1, len(centerline)):
        dlon = (centerline[i, 0] - centerline[i - 1, 0]) * m_per_deg_lon
        dlat = (centerline[i, 1] - centerline[i - 1, 1]) * m_per_deg_lat
        seg_m[i] = seg_m[i - 1] + math.hypot(dlon, dlat)
    total_m = float(seg_m[-1])
    if total_m <= 0:
        raise ValueError("centerline has zero arc length")

    # Sample n_sections stations evenly along the centerline
    stations_m = np.linspace(0.0, total_m, n_sections)

    # For each station: interpolate centerline (lon, lat) + local tangent,
    # then build a perpendicular line of length section_width_m.
    rows: list[dict] = []
    with rasterio.open(dem_path) as dem_src:
        # Reproject centerline to DEM CRS for sampling
        if dem_src.crs.to_epsg() != 4326:
            from pyproj import Transformer
            xf = Transformer.from_crs("EPSG:4326", dem_src.crs, always_xy=True)
        else:
            xf = None
        sample_lats = []
        sample_lons = []
        sample_meta: list[tuple[float, int, float]] = []
        for stn_m in stations_m:
            # Interpolate centerline at arc length stn_m
            lon_c, lat_c, tan_lon, tan_lat = _interp_centerline(
                centerline, seg_m, stn_m, m_per_deg_lat, m_per_deg_lon
            )
            # Perpendicular direction (rotate tangent 90°)
            perp_lon = -tan_lat
            perp_lat = tan_lon
            half_m = section_width_m / 2.0
            for j in range(points_per_section):
                t = (j / (points_per_section - 1)) - 0.5  # -0.5..+0.5
                dx_m = t * section_width_m
                lon_pt = lon_c + (perp_lon * dx_m) / m_per_deg_lon
                lat_pt = lat_c + (perp_lat * dx_m) / m_per_deg_lat
                sample_lons.append(lon_pt)
                sample_lats.append(lat_pt)
                sample_meta.append((float(stn_m), j, dx_m + half_m))

        # Bulk DEM sample
        if xf is not None:
            xs, ys = xf.transform(sample_lons, sample_lats)
        else:
            xs, ys = sample_lons, sample_lats
        elevations = list(dem_src.sample(zip(xs, ys)))

    for (stn_m, j, dist_m), z_arr in zip(sample_meta, elevations):
        z = float(z_arr[0]) if len(z_arr) > 0 else float("nan")
        rows.append(
            {
                "campaign_id": campaign_id,
                "station_m": stn_m,
                "point_index": j,
                "distance_m": dist_m,
                "elevation_m": z,
            }
        )
    return pd.DataFrame(rows)


def _interp_centerline(
    cl: np.ndarray, seg_m: np.ndarray, target_m: float,
    m_per_deg_lat: float, m_per_deg_lon: float,
) -> tuple[float, float, float, float]:
    """Linear-interpolate (lon, lat) + local tangent direction at arc
    length ``target_m`` along the centerline.

    Returns (lon, lat, tan_lon_unit, tan_lat_unit) where the tangent is
    in degree-per-degree units (unit vector in lat/lon).
    """
    # Find segment containing target_m
    target_m = max(0.0, min(float(seg_m[-1]), target_m))
    i = int(np.searchsorted(seg_m, target_m, side="right")) - 1
    i = max(0, min(len(cl) - 2, i))
    seg_len = seg_m[i + 1] - seg_m[i]
    if seg_len <= 0:
        f = 0.0
    else:
        f = (target_m - seg_m[i]) / seg_len
    lon = cl[i, 0] + f * (cl[i + 1, 0] - cl[i, 0])
    lat = cl[i, 1] + f * (cl[i + 1, 1] - cl[i, 1])
    # Tangent in METERS
    dlon = (cl[i + 1, 0] - cl[i, 0]) * m_per_deg_lon
    dlat = (cl[i + 1, 1] - cl[i, 1]) * m_per_deg_lat
    n = math.hypot(dlon, dlat) or 1.0
    # Convert back to deg/deg unit vector for downstream offset
    tan_lon = (dlon / n) / m_per_deg_lon  # degrees longitude per "unit"
    tan_lat = (dlat / n) / m_per_deg_lat
    # Normalize again in lat/lon space
    nn = math.hypot(tan_lon, tan_lat) or 1.0
    return lon, lat, tan_lon / nn, tan_lat / nn
