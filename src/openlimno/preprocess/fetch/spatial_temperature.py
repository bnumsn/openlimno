"""Spatial water-temperature raster fetcher built on Open-Meteo samples."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_bounds

from openlimno.preprocess.fetch.cache import CacheEntry
from openlimno.preprocess.fetch.openmeteo import (
    OPENMETEO_CITATION,
    fetch_open_meteo_daily,
)

BBox = tuple[float, float, float, float]


class TemperatureSeriesFetchResult(Protocol):
    df: pd.DataFrame
    cache: CacheEntry
    lat: float
    lon: float
    citation: str


@dataclass(frozen=True)
class SpatialTemperatureRasterResult:
    """Output of a sampled spatial temperature raster fetch."""

    tif_path: Path
    bbox: BBox
    grid_shape: tuple[int, int]
    start_year: int
    end_year: int
    aggregation: str
    sample_count: int
    mean_temperature_C: float
    min_temperature_C: float
    max_temperature_C: float
    cache_entries: tuple[CacheEntry, ...]
    citation: str = OPENMETEO_CITATION


def _validate_bbox(bbox: BBox) -> None:
    west, south, east, north = bbox
    if not (-180.0 <= west < east <= 180.0):
        raise ValueError(f"bbox longitude bounds invalid: {bbox}")
    if not (-90.0 <= south < north <= 90.0):
        raise ValueError(f"bbox latitude bounds invalid: {bbox}")


def fetch_open_meteo_temperature_raster(
    bbox: BBox,
    start_year: int,
    end_year: int,
    out_tif: str | Path,
    *,
    grid_shape: tuple[int, int] = (5, 5),
    temperature_column: str = "T_water_C_stefan",
    aggregation: str = "mean",
    fetcher: Callable[..., TemperatureSeriesFetchResult] = fetch_open_meteo_daily,
) -> SpatialTemperatureRasterResult:
    """Sample Open-Meteo over a bbox and write a temperature GeoTIFF.

    The Open-Meteo archive API is point-based, not a native raster
    endpoint. This fetcher samples a regular lon/lat grid, aggregates
    each point's daily water-temperature series, and writes the result
    as an EPSG:4326 GeoTIFF that can feed
    :func:`openlimno.habitat.thermal.thermal_si_per_section`.
    """
    _validate_bbox(bbox)
    width, height = grid_shape
    if width <= 0 or height <= 0:
        raise ValueError(f"grid_shape must be positive; got {grid_shape}")
    if aggregation != "mean":
        raise ValueError("only aggregation='mean' is currently supported")

    west, south, east, north = bbox
    # v2.5.1 (R8-3): sample at PIXEL CENTERS, not bbox edges, so the
    # sampled values align with the GeoTIFF affine transform built by
    # ``from_bounds(west, south, east, north, width, height)`` (whose
    # row/col 0 occupies the bbox top-left CORNER and whose pixel
    # centers sit a half-pixel inside the bbox). Sampling at corners
    # produced a half-pixel-equivalent geographic shift between the
    # raster's CRS-declared extent and its actual sampled values.
    dlon = (east - west) / width
    dlat = (north - south) / height
    lons = west + dlon * (np.arange(width) + 0.5)
    # GeoTIFF rows are north-to-south.
    lats = north - dlat * (np.arange(height) + 0.5)
    arr = np.full((height, width), np.nan, dtype=np.float32)
    caches: list[CacheEntry] = []
    citation = OPENMETEO_CITATION

    for row, lat in enumerate(lats):
        for col, lon in enumerate(lons):
            result = fetcher(float(lat), float(lon), start_year, end_year)
            caches.append(result.cache)
            citation = result.citation or citation
            df = result.df
            if temperature_column not in df.columns:
                raise KeyError(
                    f"temperature_column={temperature_column!r} not in "
                    f"Open-Meteo result columns {list(df.columns)}"
                )
            arr[row, col] = float(df[temperature_column].mean())

    out_path = Path(out_tif).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(west, south, east, north, width, height)
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(np.nan_to_num(arr, nan=-9999.0), 1)

    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        raise RuntimeError("Open-Meteo temperature raster has no valid samples")
    return SpatialTemperatureRasterResult(
        tif_path=out_path,
        bbox=bbox,
        grid_shape=grid_shape,
        start_year=start_year,
        end_year=end_year,
        aggregation=aggregation,
        sample_count=int(valid.size),
        mean_temperature_C=float(valid.mean()),
        min_temperature_C=float(valid.min()),
        max_temperature_C=float(valid.max()),
        cache_entries=tuple(caches),
        citation=citation,
    )


__all__ = [
    "BBox",
    "SpatialTemperatureRasterResult",
    "fetch_open_meteo_temperature_raster",
]
