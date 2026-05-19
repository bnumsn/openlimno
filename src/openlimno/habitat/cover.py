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

import functools
import json
import math
from collections.abc import Callable
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
            from the table are EXCLUDED from both the weighted sum
            and the pixel-count denominator (v2.7.1 R10-3 doc fix:
            the pre-v2.7.1 wording incorrectly described unmapped
            pixels as "contributing SI = 0", but the actual
            implementation skips them — equivalent to "average over
            known-class pixels only"). If every pixel in the
            geometry is unmapped or no-data, the function raises
            ``RuntimeError`` rather than returning a misleading
            mean of zero.
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

    For temperate / sub-tropical reaches (mean latitude ≤ ±60°) the
    buffer is computed in degree-space via a local cosine-latitude
    rescaling — adequate for the 25 deg² case sizes WorldCover
    supports without reprojecting the geometry.

    v3.4.0 R9-3 (gemini, deferred from v2.6.1): above ±60° the
    cosine-latitude approximation distorts the buffer's E-W extent
    (a 200 m buffer becomes a 200 N–S × ~100 E–W ellipse at 60°,
    worse closer to the pole). For high-latitude reaches we now
    switch to a proper geodesic buffer via ``pyproj.Geod`` on the
    WGS84 ellipsoid: each vertex gets a 360° / 36-step great-circle
    walk-around at the requested radius, the points are unioned via
    Shapely, and the result is a true equal-distance polygon. This
    is slower (Geod calls instead of arithmetic) but the only way
    to keep the buffer physically right near the poles.

    Threshold: 60° absolute latitude. Below → cos-lat path
    (compatible with all pre-v3.4 fixtures, no API change). Above
    → geodesic path. The switch is transparent — same return type
    + same coords convention.

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
    lats = [lat for _, lat in coords]
    lat_mean = sum(lats) / len(lats)

    # v3.4.0 R9-3: high-latitude path.
    if abs(lat_mean) > 60.0:
        return _riparian_buffer_geodesic(coords, buffer_m=buffer_m)

    # Original cos-latitude path for temperate / sub-tropical reaches.
    cos_lat = np.cos(np.radians(lat_mean))
    if cos_lat <= 1e-6:
        raise ValueError(
            f"polyline crosses too close to the pole "
            f"(mean_lat={lat_mean}); buffer correction unreliable."
        )
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


@functools.lru_cache(maxsize=256)
def _aeqd_transformer_to(lat_key: int, lon_key: int) -> Callable[..., tuple[float, float]]:
    """v3.6.0 R17-5: cached EPSG:4326 → AEQD transformer factory.
    lat_key/lon_key are integer-rounded centres."""
    from pyproj import Transformer
    proj = f"+proj=aeqd +lat_0={lat_key} +lon_0={lon_key} +ellps=WGS84"
    return Transformer.from_crs("EPSG:4326", proj, always_xy=True).transform


@functools.lru_cache(maxsize=256)
def _aeqd_transformer_from(lat_key: int, lon_key: int) -> Callable[..., tuple[float, float]]:
    """v3.6.0 R17-5: cached AEQD → EPSG:4326 transformer factory."""
    from pyproj import Transformer
    proj = f"+proj=aeqd +lat_0={lat_key} +lon_0={lon_key} +ellps=WGS84"
    return Transformer.from_crs(proj, "EPSG:4326", always_xy=True).transform


def _riparian_buffer_geodesic(
    coords: list[tuple[float, float]],
    *,
    buffer_m: float,
) -> BaseGeometry:
    """v3.4.0 R9-3 + v3.5.0 R16-1: high-latitude continuous-strip
    geodesic buffer.

    v3.4.0 first cut walked 36 azimuths per vertex and unioned
    vertex-centered circles. claude + gemini's 16th-round review
    caught the "string of sausages" bug: segments between
    consecutive vertices were NOT buffered, so for any polyline
    with vertex spacing > buffer_m the result had visible gaps
    between successive vertex disks. v3.5.0 closes the gap by
    projecting the polyline to a local AEQD (Azimuthal
    Equidistant Projection) centred on the polyline mean, calling
    shapely's regular ``LineString.buffer`` in the projected
    metric CRS (which DOES produce a continuous strip), then
    projecting the buffered geometry back to EPSG:4326.

    AEQD is distance-preserving from its centre point — exactly
    what we want for a metres-buffer that stays equal-distance at
    high latitude. The ~few-km accuracy at the polyline ends
    (where you've moved away from the AEQD centre) is well within
    the tolerance the buffer-distance contract promises.

    Antimeridian handling (R16-4 / R17-4): v3.5.0's first cut
    naively averaged longitudes — a polyline with vertices at
    +179 and -179 (crossing the dateline) collapsed to mean
    lon ≈ 0, placing the AEQD centre on the opposite side of the
    planet. v3.6.0 R17-4 (claude + gemini) fixes this with
    circular-mean (atan2 of unit vectors) which handles wraps
    correctly: the mean of +179 and -179 becomes ±180 (the
    midpoint along the short arc), not 0.

    Empty-coords guard: v3.5.0 would have raised ``ZeroDivisionError``
    on an empty list; v3.6.0 short-circuits earlier (the caller's
    ``len(coords) < 2`` check already covers this for the public
    entry point, but the internal helper now also validates).
    """
    from shapely.ops import transform as shapely_transform

    if not coords:
        raise ValueError("_riparian_buffer_geodesic: empty coords")

    # v3.6.0 R17-4: circular-mean longitude (atan2 of unit vectors)
    # so a polyline crossing ±180° centres correctly on the short
    # arc instead of collapsing to lon≈0 on the opposite side.
    # Latitude doesn't wrap, so arithmetic mean is fine.
    lats = [lat for _, lat in coords]
    lons = [lon for lon, _ in coords]
    lat_c = sum(lats) / len(lats)
    rad_lons = np.radians(lons)
    sum_sin = float(np.sum(np.sin(rad_lons)))
    sum_cos = float(np.sum(np.cos(rad_lons)))
    # v3.6.1 R18-3 (codex MEDIUM): atan2(0, 0) is mathematically
    # undefined. The resultant unit-vector magnitude reaches zero
    # when longitudes are antipodal in pairs (e.g. {0°, 180°} or
    # {-90°, +90°}) — i.e. the polyline is so globally distributed
    # that no single local AEQD centre makes sense. Surface this
    # as a clear ValueError instead of letting atan2(0,0) return
    # an arbitrary platform-dependent angle (0 on glibc, but the
    # spec leaves it implementation-defined).
    if math.hypot(sum_sin, sum_cos) < 1e-9:
        raise ValueError(
            f"_riparian_buffer_geodesic: polyline is too globally "
            f"distributed for a local AEQD buffer — circular-mean "
            f"longitude is undefined (resultant magnitude near 0). "
            f"Got {len(coords)} vertices spanning lon "
            f"[{min(lons):.3f}, {max(lons):.3f}]. Split the polyline "
            f"into regional segments before buffering."
        )
    lon_c = float(np.degrees(np.arctan2(sum_sin, sum_cos)))
    # v3.6.0 R17-5 (claude + gemini): cache Transformer instances
    # keyed on rounded centre. PROJ.4 initialisation is non-trivial
    # (~ms per call); a basin-wide per-reach loop would hit it
    # hundreds of times. Round to 1° because AEQD precision drops
    # well outside that anyway, so a per-1° cache key is the right
    # granularity.
    lat_key = round(lat_c)
    lon_key = round(lon_c)
    to_aeqd = _aeqd_transformer_to(lat_key, lon_key)
    from_aeqd = _aeqd_transformer_from(lat_key, lon_key)

    line_lonlat = LineString(coords)
    line_metric = shapely_transform(to_aeqd, line_lonlat)
    buf_metric = line_metric.buffer(
        buffer_m, cap_style="round", join_style="round",
    )
    buf_lonlat = shapely_transform(from_aeqd, buf_metric)
    # v3.6.1 R18-2 (codex MEDIUM): AEQD inverse projection of a
    # buffer that straddles the antimeridian produces a polygon
    # whose coordinates are valid in metric space but span nearly
    # 360° in lon/lat space when interpreted naively (Shapely is
    # planar; it has no notion of "wrap"). Downstream
    # rasterio.mask.mask(crop=True) then crops the WRONG global
    # bbox instead of the small dateline-local strip. Detect the
    # over-wide case (lon bounds span > 180°) and split into a
    # MultiPolygon that respects the ±180° seam.
    buf_lonlat = _split_at_antimeridian(buf_lonlat, lon_c)
    return cast(BaseGeometry, buf_lonlat)


def _split_at_antimeridian(
    geom: BaseGeometry, centre_lon: float,
) -> BaseGeometry:
    """v3.6.1 R18-2: rewrap a Shapely geometry that an AEQD inverse
    projection produced across the ±180° seam.

    Strategy: shift longitudes into an unwrapped frame around
    ``centre_lon`` (so the buffer is a connected blob in that
    frame), then split the unwrapped polygon at ±180° lines, and
    finally remap each piece back into the canonical [-180, 180]
    range. The result is a MultiPolygon whose parts each respect
    the seam — what ``rasterio.mask.mask(crop=True)`` and any GIS
    consumer expect.

    For geometries that don't actually cross the seam, this is a
    near no-op (the lon-bounds-span guard short-circuits).
    """
    minx, _miny, maxx, _maxy = geom.bounds
    if (maxx - minx) <= 180.0:
        # Doesn't straddle the seam — pass through untouched.
        return geom

    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import transform as shapely_transform

    # Unwrap: shift longitudes into [centre - 180, centre + 180].
    def _unwrap(lon: float, lat: float, z: float | None = None) -> tuple[float, ...]:
        # Move lon to its representative within ±180° of centre_lon.
        shifted = ((lon - centre_lon + 180.0) % 360.0) - 180.0 + centre_lon
        if z is not None:
            return shifted, lat, z
        return shifted, lat

    unwrapped = shapely_transform(_unwrap, geom)
    u_minx, u_miny, u_maxx, u_maxy = unwrapped.bounds

    # Split at every ±180°·k line inside the unwrapped bounds.
    parts: list[BaseGeometry] = []
    k_lo = int(np.floor((u_minx + 180.0) / 360.0))
    k_hi = int(np.floor((u_maxx + 180.0) / 360.0))
    for k in range(k_lo, k_hi + 1):
        strip_min = -180.0 + 360.0 * k
        strip_max = 180.0 + 360.0 * k
        strip = Polygon([
            (strip_min, u_miny - 1), (strip_max, u_miny - 1),
            (strip_max, u_maxy + 1), (strip_min, u_maxy + 1),
        ])
        piece = unwrapped.intersection(strip)
        if piece.is_empty:
            continue
        # Rewrap this piece by shifting its longitudes by -360·k.
        def _rewrap_k(
            lon: float, lat: float, z: float | None = None, _k: int = k,
        ) -> tuple[float, ...]:
            if z is not None:
                return lon - 360.0 * _k, lat, z
            return lon - 360.0 * _k, lat

        parts.append(shapely_transform(_rewrap_k, piece))

    if not parts:
        return geom  # paranoia — shouldn't happen
    if len(parts) == 1:
        return parts[0]
    flat: list[Polygon] = []
    for p in parts:
        if p.geom_type == "Polygon":
            flat.append(cast(Polygon, p))
        elif p.geom_type == "MultiPolygon":
            flat.extend(cast(MultiPolygon, p).geoms)
    return MultiPolygon(flat)


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
