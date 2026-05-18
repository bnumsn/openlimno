"""Cover habitat suitability from LULC (v1.3.0).

Closes the second fetcher × habitat loop (after v1.1.0 thermal):
ESA WorldCover 10 m LULC + a region geometry → cover suitability
score that multiplies into total HSI.

The mapping LULC class → cover SI is a literature-informed
defaults table:

* **Tree cover (10)** and **mangroves (95)** = SI 1.0 / 0.9 —
  canopy provides shading, allochthonous food input, root-mat
  refuge. The canonical "good fish habitat" cover.
* **Shrubland (20)** = 0.8 — undercut banks, woody-debris
  proxy.
* **Herbaceous wetland (90)** = 0.7 — emergent vegetation,
  high invertebrate productivity.
* **Open water (80)** = 0.5 — neutral (open water *is* the
  habitat for free-swimmers but offers no cover from predators).
* **Grassland (30)**, **moss/lichen (100)** = 0.4 / 0.3 —
  modest bankside cover.
* **Cropland (40)** = 0.2 — usually riprap-banked, denatured.
* **Bare/sparse (60)** = 0.1 — exposed substrate; mostly habitat
  for benthic specialists, low surface cover.
* **Built-up (50)**, **snow/ice (70)** = 0.0 — zero biological
  habitat value at the time of LULC observation.

The values above represent a default temperate-stream calibration.
Site-specific tuning is supported via the ``cover_si_table``
argument on every function.

Reference: Bain et al. 1985, Beechie & Bolton 1999 (woody debris
+ canopy cover as primary fish-habitat predictors in PNW streams);
adapted to the WorldCover 11-class LCCS schema.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from shapely.geometry import LineString, mapping, shape
from shapely.geometry.base import BaseGeometry

# Default WorldCover class → cover SI mapping. Override per case
# via the ``cover_si_table`` kwarg if site calibration data exists.
DEFAULT_RIPARIAN_COVER_SI: dict[int, float] = {
    10: 1.0,   # tree cover
    20: 0.8,   # shrubland
    30: 0.4,   # grassland
    40: 0.2,   # cropland
    50: 0.0,   # built-up
    60: 0.1,   # bare / sparse
    70: 0.0,   # snow / ice
    80: 0.5,   # permanent water bodies
    90: 0.7,   # herbaceous wetland
    95: 0.9,   # mangroves
    100: 0.3,  # moss / lichen
}


def _load_geometry_from_geojson(geojson_path: Path | str) -> BaseGeometry:
    """Parse a GeoJSON file into a single shapely geometry.

    Accepts FeatureCollection / Feature / Geometry roots; multiple
    features are merged into a MultiPolygon / collection.
    """
    data: Any = json.loads(Path(geojson_path).read_text())
    if data.get("type") == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in data["features"]]
        if len(geoms) == 1:
            return cast(BaseGeometry, geoms[0])
        from shapely.geometry import GeometryCollection
        return GeometryCollection(geoms)
    if data.get("type") == "Feature":
        return cast(BaseGeometry, shape(data["geometry"]))
    return cast(BaseGeometry, shape(data))


def cover_si_from_lulc_raster(
    lulc_tif: Path | str,
    geometry: BaseGeometry,
    *,
    cover_si_table: dict[int, float] | None = None,
    all_touched: bool = False,
) -> tuple[float, dict[int, int]]:
    """Compute pixel-weighted mean cover SI inside a region.

    Args:
        lulc_tif: path to a uint8 WorldCover GeoTIFF (the
            :func:`fetch_esa_worldcover` output).
        geometry: a shapely Geometry (Polygon / MultiPolygon /
            collection) in the same CRS as ``lulc_tif`` (EPSG:4326
            for WorldCover).
        cover_si_table: optional override of
            :data:`DEFAULT_RIPARIAN_COVER_SI`. Class codes missing
            from the table contribute SI = 0.
        all_touched: forwarded to :func:`rasterio.mask.mask`. Default
            ``False`` matches pre-v2.7.0 "center-inside polygon"
            semantics. Set ``True`` for sub-pixel buffer geometries
            (e.g. metres-scale point buffers from the v2.7.0 inline
            cover-raster path). Symmetric to the v2.6.1 R9-6 flag
            on :func:`thermal_si_from_temperature_raster`.

    Returns:
        ``(mean_si, class_pixels)`` where ``mean_si ∈ [0, 1]`` is
        the pixel-count-weighted cover SI and ``class_pixels`` is the
        WorldCover-code → pixel-count histogram inside the region
        (no-data 0 excluded).
    """
    table = cover_si_table or DEFAULT_RIPARIAN_COVER_SI
    with rasterio.open(lulc_tif) as src:
        out, _ = rasterio.mask.mask(
            src, [mapping(geometry)], crop=True, nodata=0, filled=True,
            all_touched=all_touched,
        )
        # ``mask.mask`` returns shape (n_bands, h, w); WorldCover is
        # single-band uint8.
        arr = out[0]
    class_pixels: dict[int, int] = {}
    weighted_sum = 0.0
    total = 0
    # Iterate the 11 known class codes. Any pixel value outside the
    # table (including 0 = no-data) is silently dropped from the
    # weight + count totals.
    for code, si in table.items():
        n = int(np.sum(arr == code))
        if n:
            class_pixels[code] = n
            weighted_sum += si * n
            total += n
    if total == 0:
        # All-no-data region — fail loudly rather than return NaN
        # silently (downstream habitat code would multiply by NaN
        # and quietly produce NaN WUA everywhere).
        raise RuntimeError(
            f"No LULC pixels matched table inside the region: every "
            f"pixel was either 0 (no-data) or a class not in the "
            f"cover_si_table. Table keys: {sorted(table)}."
        )
    return weighted_sum / total, class_pixels


def riparian_buffer_from_polyline(
    coords: list[tuple[float, float]],
    *,
    buffer_m: float = 50.0,
) -> BaseGeometry:
    """Build a riparian-buffer polygon around an EPSG:4326 polyline.

    The buffer is computed in metres but applied in degree-space
    via a local cosine-latitude rescaling — adequate for the 25 deg²
    case sizes WorldCover supports without reprojecting the geometry.

    Args:
        coords: ``[(lon, lat), ...]`` (matches GeoJSON LineString
            order: longitude first).
        buffer_m: buffer width in metres on each side. Default
            50 m is a literature-standard riparian-zone width.

    Returns:
        shapely Polygon (or MultiPolygon if the buffer self-overlaps).
    """
    if len(coords) < 2:
        raise ValueError(
            f"polyline must have ≥ 2 vertices; got {len(coords)}"
        )
    if buffer_m <= 0:
        raise ValueError(f"buffer_m={buffer_m} must be positive")
    # Mean latitude → cos correction so the lon-extent of the buffer
    # is physically right (deg ↔ metres is ~111 km/° in lat, scaled
    # by cos(lat) in lon).
    lats = [lat for _, lat in coords]
    lat_mean = sum(lats) / len(lats)
    cos_lat = np.cos(np.radians(lat_mean))
    if cos_lat <= 1e-6:
        raise ValueError(
            f"polyline crosses too close to the pole "
            f"(mean_lat={lat_mean}); buffer correction unreliable."
        )
    # Convert metres to degrees-of-latitude: 1 deg ≈ 111 320 m.
    # Rescale the polyline to a "metric" coord system where 1 unit =
    # 1 metre at the mean latitude, buffer in the same unit, then
    # unscale.
    METRES_PER_DEG_LAT = 111_320.0
    def to_metric(lon: float, lat: float) -> tuple[float, float]:
        return lon * METRES_PER_DEG_LAT * cos_lat, lat * METRES_PER_DEG_LAT
    def from_metric(x: float, y: float) -> tuple[float, float]:
        return x / (METRES_PER_DEG_LAT * cos_lat), y / METRES_PER_DEG_LAT

    metric_coords = [to_metric(lon, lat) for lon, lat in coords]
    line_m = LineString(metric_coords)
    buf_m = line_m.buffer(buffer_m, cap_style="round", join_style="round")
    # Unscale geometry back to lon/lat
    from shapely.ops import transform

    def unscale(
        x: float, y: float, z: float | None = None,
    ) -> tuple[float, float] | tuple[float, float, float]:
        lon, lat = from_metric(x, y)
        if z is not None:
            return lon, lat, z
        return lon, lat

    return cast(BaseGeometry, transform(unscale, buf_m))


def cover_si_from_polyline(
    lulc_tif: Path | str,
    coords: list[tuple[float, float]],
    *,
    buffer_m: float = 50.0,
    cover_si_table: dict[int, float] | None = None,
) -> tuple[float, dict[int, int]]:
    """Riparian-buffer cover SI: build a ``buffer_m``-metre buffer
    around the polyline, then aggregate LULC inside it."""
    geom = riparian_buffer_from_polyline(coords, buffer_m=buffer_m)
    return cover_si_from_lulc_raster(
        lulc_tif, geom, cover_si_table=cover_si_table,
    )


def watershed_cover_si(
    lulc_tif: Path | str,
    watershed_geojson: Path | str,
    *,
    cover_si_table: dict[int, float] | None = None,
) -> tuple[float, dict[int, int]]:
    """Watershed-scale cover SI: aggregate LULC inside the basin
    polygon produced by :func:`write_watershed_geojson`."""
    geom = _load_geometry_from_geojson(watershed_geojson)
    return cover_si_from_lulc_raster(
        lulc_tif, geom, cover_si_table=cover_si_table,
    )


def cover_si_summary(class_pixels: dict[int, int]) -> pd.DataFrame:
    """Pretty-print histogram into a DataFrame for reporting."""
    if not class_pixels:
        return pd.DataFrame(
            columns=["class_code", "pixel_count", "fraction", "cover_si"],
        )
    total = sum(class_pixels.values())
    rows = []
    for code, n in sorted(class_pixels.items(), key=lambda kv: -kv[1]):
        rows.append({
            "class_code": code,
            "pixel_count": n,
            "fraction": n / total,
            "cover_si": DEFAULT_RIPARIAN_COVER_SI.get(code, 0.0),
        })
    return pd.DataFrame(rows)


def cover_si_per_section(
    lulc_tif: Path | str,
    section_geometries: list,
    *,
    cover_si_table: dict[int, float] | None = None,
    all_touched: bool = False,
) -> np.ndarray:
    """Per-section cover SI for the v2.1.0 per-cell composite.

    Calls :func:`cover_si_from_lulc_raster` once per supplied geometry
    and returns the resulting SI values as a 1-D array, suitable as
    the ``cover_si_per_cell`` argument to
    :func:`openlimno.habitat.composite.apply_overlay_per_cell`.

    Args:
        lulc_tif: path to a single-band uint8 WorldCover GeoTIFF.
        section_geometries: list of shapely geometries (one per
            cross-section / cell). Typical input is the output of
            :func:`riparian_buffer_from_polyline` applied per section,
            or any per-section polygon you've reduced from a 2D mesh.
        cover_si_table: optional override of
            :data:`DEFAULT_RIPARIAN_COVER_SI`. Forwarded to
            :func:`cover_si_from_lulc_raster`.
        all_touched: forwarded to :func:`cover_si_from_lulc_raster`
            (v2.7.0). Default ``False`` for back-compat; set ``True``
            for sub-pixel buffers from the inline cover-raster path.

    Returns:
        1-D ``numpy.ndarray`` of length ``len(section_geometries)``,
        with ``si[i] ∈ [0, 1]`` the pixel-weighted mean cover SI inside
        section ``i``'s geometry. Sections whose geometry contains no
        valid LULC pixels propagate the existing ``RuntimeError`` from
        :func:`cover_si_from_lulc_raster` — fail loud is preferred over
        silent NaN for habitat code.
    """
    if not section_geometries:
        return np.zeros(0, dtype=float)
    out = np.empty(len(section_geometries), dtype=float)
    for i, geom in enumerate(section_geometries):
        si, _ = cover_si_from_lulc_raster(
            lulc_tif, geom, cover_si_table=cover_si_table,
            all_touched=all_touched,
        )
        out[i] = si
    return out
