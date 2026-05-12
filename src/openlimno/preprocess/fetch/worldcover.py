"""ESA WorldCover 10 m global land cover fetcher (v0.3.4 P0).

ESA WorldCover (Zanaga et al. 2022) is the de-facto open global LULC
product at 10 m derived from Sentinel-1/2: 11 classes (LCCS-based),
two epochs (2020 v100 + 2021 v200), free, no auth, COG-hosted on a
public AWS S3 bucket. We stream a bbox subset via ``/vsicurl/`` and
return both the merged raster + a class histogram (pixel count → km²)
so cases can compute "% cropland / % built-up / % forest" of their
contributing area without rasterio-heavy downstream code.

For OpenLimno's fish-biology models we care about:

* **Drainage-area land cover** — feeds the rainfall-runoff regression
  (built-up % bumps Q peaks, cropland % shifts seasonality).
* **Riparian-buffer cover** — proxies cover/shading for fish habitat
  (the 50-200 m buffer along the river polyline picks up the strip
  most relevant to thermal regime + drift food supply).

Tile naming convention:
    s3://esa-worldcover/v200/2021/map/
        ESA_WorldCover_10m_2021_v200_{Nxx|Sxx}{Exxx|Wxxx}_Map.tif

Tiles are 3°×3° aligned on multiples of 3 degrees (SW-corner naming).
A single 3°×3° tile is ~100 MB; we use Cloud-Optimized-GeoTIFF window
reads so 1 km² bboxes only pull KBs.

Citation:
    Zanaga, D., Van De Kerchove, R., Daems, D., De Keersmaecker, W.,
    Brockmann, C., Kirches, G., Wevers, J., Cartus, O., Santoro, M.,
    Fritz, S., Lesiv, M., Herold, M., Tsendbazar, N.-E., Xu, P.,
    Ramoino, F., Arino, O. (2022). ESA WorldCover 10 m 2021 v200.
    doi:10.5281/zenodo.7254221. https://esa-worldcover.org/
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
import rasterio.merge
import rasterio.windows
from rasterio.io import MemoryFile

from openlimno.preprocess.fetch.cache import CacheEntry, cache_dir, cached_fetch

WORLDCOVER_S3_BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com"

# ESA WorldCover LCCS-based class codes (v100 + v200 share the schema).
# Code 0 = no data; codes are NOT contiguous (10 → 100 in steps of 10
# plus 95 for mangroves) — that gap matters for histogram fillers.
WORLDCOVER_CLASSES: dict[int, str] = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare_sparse_vegetation",
    70: "snow_and_ice",
    80: "permanent_water_bodies",
    90: "herbaceous_wetland",
    95: "mangroves",
    100: "moss_and_lichen",
}

# Released epochs. 2020 = v100, 2021 = v200. ESA only ships those two.
WORLDCOVER_EPOCHS: dict[int, str] = {2020: "v100", 2021: "v200"}

WORLDCOVER_CITATION = (
    "Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200. "
    "doi:10.5281/zenodo.7254221. https://esa-worldcover.org/ — "
    "CC-BY 4.0."
)

# Each tile is 3°×3°. Safety cap: a 9°×9° bbox = 9 tiles ≈ 900 MB raw
# at 10 m, ~3 GB during merge. Heavier than DEM (whose tiles are 1°),
# so cap tighter.
_TILE_DEG = 3
MAX_BBOX_DEG2 = 25.0  # ~9 tiles worst case (corner-overlap arithmetic)


@dataclass
class WorldCoverFetchResult:
    """Outcome of an ESA WorldCover fetch over a bbox.

    Attributes:
        path: local GeoTIFF holding the (merged) bbox subset, uint8.
        bounds: (lon_min, lat_min, lon_max, lat_max) of returned raster.
        crs: GDAL CRS string (EPSG:4326).
        n_tiles: number of 3°-tiles fetched.
        year: 2020 or 2021 (epoch chosen at fetch time).
        version: ``"v100"`` (2020) or ``"v200"`` (2021).
        class_pixels: ``{class_code: pixel_count}`` over the merged raster
            (no-data 0 stripped). Useful for fraction computation
            without re-reading the raster.
        class_km2: ``{class_code: area_km²}`` derived from ``class_pixels``
            using a latitude-aware pixel-area estimate (10 m × 10 m in
            equatorial regions; cos(lat) correction for the centroid).
        cache_entries: provenance trail (one CacheEntry per tile).
        citation: APA-style citation string.
    """

    path: Path
    bounds: tuple[float, float, float, float]
    crs: str
    n_tiles: int
    year: int
    version: str
    class_pixels: dict[int, int] = field(default_factory=dict)
    class_km2: dict[int, float] = field(default_factory=dict)
    cache_entries: list[CacheEntry] = field(default_factory=list)
    citation: str = WORLDCOVER_CITATION


def _tile_name(lat_sw: int, lon_sw: int) -> str:
    """ESA WorldCover tile stem for the 3°×3° tile whose SW corner is
    ``(lat_sw, lon_sw)`` (both must be multiples of 3).
    """
    ns = f"N{lat_sw:02d}" if lat_sw >= 0 else f"S{-lat_sw:02d}"
    ew = f"E{lon_sw:03d}" if lon_sw >= 0 else f"W{-lon_sw:03d}"
    return f"{ns}{ew}"


def _tiles_for_bbox(
    lon_min: float, lat_min: float, lon_max: float, lat_max: float,
) -> list[tuple[int, int]]:
    """Return the (lat_sw, lon_sw) corners of all 3°×3° tiles touching
    the bbox. SW corners are multiples of 3 in both axes (ESA grid).
    """
    def _floor3(v: float) -> int:
        return int(math.floor(v / _TILE_DEG)) * _TILE_DEG
    out: list[tuple[int, int]] = []
    la_lo = _floor3(lat_min)
    la_hi = _floor3(lat_max - 1e-9)  # exclusive top edge avoids extra tile
    lo_lo = _floor3(lon_min)
    lo_hi = _floor3(lon_max - 1e-9)
    for la in range(la_lo, la_hi + 1, _TILE_DEG):
        for lo in range(lo_lo, lo_hi + 1, _TILE_DEG):
            out.append((la, lo))
    return out


class _TileNotFoundError(Exception):
    """Internal: tile doesn't exist (e.g., open-ocean cell)."""


def _stream_tile_subset(
    tile_url: str, lon_min: float, lat_min: float, lon_max: float, lat_max: float,
) -> bytes:
    """Pull a bbox window from a remote WorldCover COG via /vsicurl/."""
    vsi_url = f"/vsicurl/{tile_url}"
    try:
        src = rasterio.open(vsi_url)
    except rasterio.errors.RasterioIOError as e:
        raise _TileNotFoundError(str(e)) from e
    try:
        window = rasterio.windows.from_bounds(
            lon_min, lat_min, lon_max, lat_max, src.transform
        )
        window = window.round_offsets(op="floor").round_lengths(op="ceil")
        full_window = rasterio.windows.Window(0, 0, src.width, src.height)
        try:
            window = window.intersection(full_window)
        except rasterio.errors.WindowError as e:
            raise _TileNotFoundError(
                f"Tile {tile_url} doesn't overlap bbox: {e}"
            ) from e
        if window.width <= 0 or window.height <= 0:
            raise _TileNotFoundError(
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


def _pixel_area_km2(lat_center: float, pixel_size_deg: float) -> float:
    """Approximate the on-the-ground area (km²) of a single
    ``pixel_size_deg``×``pixel_size_deg`` pixel at ``lat_center``.

    Uses cos(lat) longitude shrinkage on a spherical Earth (R = 6371 km).
    For ESA WorldCover at 10 m pixels (pixel_size_deg ≈ 1/12000 ≈
    8.33e-5°), the result is ≈ 1e-4 km² at the equator, scaling with
    cos(lat). Adequate for fraction summaries — for sub-percent accuracy
    use a proper equal-area reprojection.
    """
    R = 6371.0  # km
    dy_km = R * math.radians(pixel_size_deg)
    dx_km = R * math.radians(pixel_size_deg) * math.cos(math.radians(lat_center))
    return dx_km * dy_km


def _compute_class_histogram(
    raster_path: Path, lat_center: float,
) -> tuple[dict[int, int], dict[int, float]]:
    """Count pixels per class + convert to km².

    NULL (code 0) is excluded from the totals — it represents tile
    edges + ocean masks that would otherwise inflate "non-land".
    """
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        pixel_w_deg = abs(src.transform.a)
        pixel_h_deg = abs(src.transform.e)
        if pixel_w_deg != pixel_h_deg:
            # Use mean if not square (very rare for COG products).
            pixel_size_deg = (pixel_w_deg + pixel_h_deg) / 2.0
        else:
            pixel_size_deg = pixel_w_deg
    px_area = _pixel_area_km2(lat_center, pixel_size_deg)

    counts: dict[int, int] = {}
    for code in WORLDCOVER_CLASSES:
        n = int(np.sum(data == code))
        if n:
            counts[code] = n
    km2 = {code: n * px_area for code, n in counts.items()}
    return counts, km2


def fetch_esa_worldcover(
    lon_min: float, lat_min: float, lon_max: float, lat_max: float,
    *, year: int = 2021, out_path: str | Path | None = None,
) -> WorldCoverFetchResult:
    """Fetch ESA WorldCover 10 m LULC over a lat/lon bbox.

    Args:
        lon_min, lat_min, lon_max, lat_max: bbox in EPSG:4326.
        year: 2020 (v100) or 2021 (v200). Default 2021 (newer + more
            consistent training).
        out_path: where to write the merged GeoTIFF. Defaults to a
            cache path keyed on bbox + year.

    Returns:
        ``WorldCoverFetchResult`` with merged raster path, class
        histogram (pixels + km²), and one ``CacheEntry`` per tile.
    """
    if lon_max <= lon_min or lat_max <= lat_min:
        raise ValueError(
            f"Invalid bbox: lon_min={lon_min} lon_max={lon_max} "
            f"lat_min={lat_min} lat_max={lat_max}. Need lon_max > lon_min, "
            f"lat_max > lat_min."
        )
    if not (lat_min >= -60 and lat_max <= 84):
        raise ValueError(
            f"WorldCover coverage is 60°S to 84°N (Antarctica + most of "
            f"the Southern Ocean is masked). Got lat_min={lat_min}, "
            f"lat_max={lat_max}."
        )
    if not (lon_min >= -180 and lon_max <= 180):
        raise ValueError(
            f"WorldCover longitudes must be in [-180, 180]. Got "
            f"lon_min={lon_min}, lon_max={lon_max}. For bboxes that "
            f"cross the antimeridian, split into two queries."
        )
    if year not in WORLDCOVER_EPOCHS:
        raise ValueError(
            f"year={year} not a released WorldCover epoch. "
            f"Valid: {sorted(WORLDCOVER_EPOCHS)} (2020 v100, 2021 v200)."
        )
    bbox_area = (lon_max - lon_min) * (lat_max - lat_min)
    if bbox_area > MAX_BBOX_DEG2:
        raise ValueError(
            f"WorldCover bbox area {bbox_area:.2f} deg² exceeds the "
            f"safety cap of {MAX_BBOX_DEG2:.0f} deg² (~9 tiles at "
            f"3°×3° each, ~3 GB peak). OpenLimno targets reach- to "
            f"catchment-scale cases; for continent-scale mosaics use "
            f"GDAL gdal_merge directly."
        )

    version = WORLDCOVER_EPOCHS[year]
    tile_corners = _tiles_for_bbox(lon_min, lat_min, lon_max, lat_max)

    tile_paths: list[Path] = []
    cache_entries: list[CacheEntry] = []
    for la, lo in tile_corners:
        stem = _tile_name(la, lo)
        fname = f"ESA_WorldCover_10m_{year}_{version}_{stem}_Map.tif"
        tile_url = f"{WORLDCOVER_S3_BASE}/{version}/{year}/map/{fname}"
        tile_params = {
            "lon_min": round(lon_min, 6), "lat_min": round(lat_min, 6),
            "lon_max": round(lon_max, 6), "lat_max": round(lat_max, 6),
            "year": year,
        }
        try:
            ce = cached_fetch(
                subdir=f"worldcover/{version}",
                url=tile_url,
                params=tile_params,
                suffix=".tif",
                fetch_fn=lambda u=tile_url: _stream_tile_subset(
                    u, lon_min, lat_min, lon_max, lat_max
                ),
            )
        except _TileNotFoundError:
            continue
        tile_paths.append(ce.path)
        cache_entries.append(ce)

    if not tile_paths:
        raise ValueError(
            f"No WorldCover tiles available for bbox ({lon_min}, "
            f"{lat_min}, {lon_max}, {lat_max}). All overlapping tiles "
            f"are missing — verify the bbox is over land + within "
            f"(60°S, 84°N)."
        )

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
                "compress": "lzw",
            }
        )
    finally:
        for s in srcs:
            s.close()

    if out_path is None:
        out_path = cache_dir("worldcover") / (
            f"wc{year}_merge_{lon_min:.4f}_{lat_min:.4f}_"
            f"{lon_max:.4f}_{lat_max:.4f}.tif"
        )
    out_path = Path(out_path)
    with rasterio.open(out_path, "w", **out_meta) as dst:
        dst.write(mosaic)

    lat_center = (lat_min + lat_max) / 2.0
    counts, km2 = _compute_class_histogram(out_path, lat_center)

    return WorldCoverFetchResult(
        path=out_path,
        bounds=(lon_min, lat_min, lon_max, lat_max),
        crs="EPSG:4326",
        n_tiles=len(tile_paths),
        year=year,
        version=version,
        class_pixels=counts,
        class_km2=km2,
        cache_entries=cache_entries,
    )
