"""HydroSHEDS HydroBASINS + HydroRIVERS fetcher (v0.3.3 P0).

HydroSHEDS (Lehner & Grill 2013) is the de-facto open global hydrographic
framework derived from SRTM 3" / MERIT DEM. We expose two vector layers:

* **HydroBASINS** — nested watershed polygons with a Pfafstetter-coded
  ``HYBAS_ID`` + ``NEXT_DOWN`` topology, levels 1-12 (level 12 ≈ 4-6 km²
  units). Lets us answer "what's the upstream catchment of a pour
  point" by following ``NEXT_DOWN`` recursively.
* **HydroRIVERS** — global river network polylines with ``HYRIV_ID`` +
  Strahler order + upstream area. Lets us answer "what river does this
  point belong to, and what's its drainage area at this reach".

For OpenLimno's case-building we need:

* The contributing-area polygon for a pour point (drives water-balance
  / land-cover statistics).
* The total upstream catchment area in km² (drives water-quantity
  regression Q ≈ a·A^b for ungauged sites).
* The local river feature (Strahler order + reach length).

Datasets are ~50-150 MB per continent (zipped shapefile), small enough
to cache on disk under ``$XDG_CACHE_HOME/openlimno/hydrosheds/`` and
reuse across cases. We DO NOT bulk-load features into Python — at level
12 a continent has 1-2 million polygons. Instead we keep the shapefile
on disk and use GDAL/OGR SpatialFilter for lookups + an attribute-only
table scan for the topology walk.

Citation:
    Lehner, B. & Grill, G. (2013). Global river hydrography and network
    routing: baseline data and new approaches to study the world's large
    river systems. Hydrological Processes, 27(15): 2171-2186.
    https://www.hydrosheds.org/
"""
from __future__ import annotations

import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from osgeo import ogr, osr

from openlimno.preprocess.fetch.cache import CacheEntry, cache_dir, cached_fetch

# NOTE: we deliberately do NOT call ogr.UseExceptions() — HydroSHEDS
# shapefiles ship with a .sbn spatial index that emits non-fatal "ERROR
# 1: Inconsistent shape count for bin" warnings on layer iteration. In
# exception mode those abort the read; in legacy (default) mode they're
# logged and harmless. We check return values explicitly where it matters.

HYDROSHEDS_BASE = "https://data.hydrosheds.org/file"

# HydroSHEDS continental regions (their two-letter codes).
HYDROSHEDS_REGIONS = {
    "af": "Africa", "ar": "Arctic", "as": "Asia", "au": "Australia",
    "eu": "Europe", "gr": "Greenland", "na": "North America",
    "sa": "South America", "si": "Siberia",
}

# HydroBASINS supported nesting levels.
HYDROBASINS_LEVELS = tuple(range(1, 13))

HYDROSHEDS_CITATION = (
    "Lehner, B. & Grill, G. (2013). Global river hydrography and "
    "network routing: baseline data and new approaches to study the "
    "world's large river systems. Hydrological Processes, 27(15): "
    "2171-2186, doi:10.1002/hyp.9740. https://www.hydrosheds.org/"
)


@dataclass
class HydroshedsLayerResult:
    """Outcome of a HydroBASINS or HydroRIVERS fetch.

    Attributes:
        shp_path: path to the unzipped ``.shp`` on disk. Pass to
            :func:`find_basin_at` / :func:`upstream_basin_ids` for
            queries — we deliberately do not pre-load features.
        cache: provenance trail entry for the zip download.
        region: continent code (``"as"``, ``"na"`` …).
        level: HydroBASINS Pfafstetter level (1-12) or ``-1`` for rivers.
        layer_kind: ``"hydrobasins"`` or ``"hydrorivers"``.
        citation: APA-style citation for provenance.json.
    """

    shp_path: Path
    cache: CacheEntry
    region: str
    level: int
    layer_kind: str
    citation: str = HYDROSHEDS_CITATION


def _validate_region(region: str) -> str:
    region = region.lower()
    if region not in HYDROSHEDS_REGIONS:
        raise ValueError(
            f"region={region!r} not a HydroSHEDS continental code. "
            f"Valid: {sorted(HYDROSHEDS_REGIONS)}"
        )
    return region


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Extract a zip into dest_dir, rejecting entries that escape it.

    HydroSHEDS zips are trusted, but file-from-internet → disk is a
    classic zip-slip vector; harden defensively.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = (dest_dir / member).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise RuntimeError(
                    f"refusing to extract {member!r}: would escape "
                    f"{dest_dir} (zip-slip guard)"
                )
        zf.extractall(dest_dir)


def _ensure_unpacked(cache: CacheEntry, subdir: Path, shp_glob: str) -> Path:
    """Lazily unzip the cached payload and locate the ``.shp``."""
    shps = sorted(subdir.glob(shp_glob))
    if not shps:
        _safe_extract_zip(cache.path, subdir)
        shps = sorted(subdir.glob(shp_glob))
    if not shps:
        raise RuntimeError(
            f"HydroSHEDS zip {cache.path.name} extracted to {subdir} "
            f"but no shapefile matched {shp_glob!r}"
        )
    if len(shps) > 1:
        raise RuntimeError(
            f"Multiple shapefiles matched {shp_glob!r} in {subdir}: "
            f"{[s.name for s in shps]}. Expected exactly one."
        )
    return shps[0]


def fetch_hydrobasins(region: str, level: int = 12) -> HydroshedsLayerResult:
    """Download + cache a HydroBASINS continental zip.

    Args:
        region: continent code (see :data:`HYDROSHEDS_REGIONS`).
        level: Pfafstetter nesting level 1-12. Higher = finer; level 12
            is the finest (~4-6 km² basin units). Default is 12 because
            the topology walk produces a watershed boundary at the
            resolution most users expect for sub-basin analysis.

    Returns:
        :class:`HydroshedsLayerResult` with ``.shp_path`` pointing at
        the unzipped shapefile.
    """
    region = _validate_region(region)
    if level not in HYDROBASINS_LEVELS:
        raise ValueError(
            f"level={level} not in HydroBASINS supported range "
            f"{HYDROBASINS_LEVELS}"
        )
    zip_name = f"hybas_{region}_lev{level:02d}_v1c.zip"
    url = f"{HYDROSHEDS_BASE}/HydroBASINS/standard/{zip_name}"
    # Cache key folds region+level into params so different continents
    # / levels never collide on the same SHA-256.
    params = {"region": region, "level": level, "product": "hydrobasins"}

    import requests

    def _do_fetch() -> bytes:
        # HydroBASINS continental zips run 50-150 MB; allow a generous
        # timeout vs the default 120 s in cached_fetch's callers.
        resp = requests.get(url, timeout=600, stream=False)
        resp.raise_for_status()
        return resp.content

    cache = cached_fetch(
        subdir="hydrosheds", url=url, params=params,
        suffix=".zip", fetch_fn=_do_fetch,
    )
    # Unpack into a sibling dir alongside the zip so multiple regions /
    # levels coexist without overwriting each other's shp files.
    unpack_dir = cache_dir(f"hydrosheds/hybas_{region}_lev{level:02d}")
    shp_path = _ensure_unpacked(
        cache, unpack_dir, f"hybas_{region}_lev{level:02d}_v1c.shp",
    )
    return HydroshedsLayerResult(
        shp_path=shp_path, cache=cache, region=region, level=level,
        layer_kind="hydrobasins",
    )


def fetch_hydrorivers(region: str) -> HydroshedsLayerResult:
    """Download + cache a HydroRIVERS continental zip."""
    region = _validate_region(region)
    zip_name = f"HydroRIVERS_v10_{region}_shp.zip"
    url = f"{HYDROSHEDS_BASE}/HydroRIVERS/{zip_name}"
    params = {"region": region, "product": "hydrorivers"}

    import requests

    def _do_fetch() -> bytes:
        resp = requests.get(url, timeout=600, stream=False)
        resp.raise_for_status()
        return resp.content

    cache = cached_fetch(
        subdir="hydrosheds", url=url, params=params,
        suffix=".zip", fetch_fn=_do_fetch,
    )
    unpack_dir = cache_dir(f"hydrosheds/HydroRIVERS_v10_{region}")
    shp_path = _ensure_unpacked(
        cache, unpack_dir, f"HydroRIVERS_v10_{region}.shp",
    )
    return HydroshedsLayerResult(
        shp_path=shp_path, cache=cache, region=region, level=-1,
        layer_kind="hydrorivers",
    )


# ---------------------------------------------------------------------
# Topology + lookup helpers (no geopandas; ogr-only for streaming).
# ---------------------------------------------------------------------
def find_basin_at(
    shp_path: Path | str, lat: float, lon: float,
) -> dict | None:
    """Return the HydroBASINS feature containing ``(lat, lon)`` — or
    ``None`` if the point falls outside the layer.

    HydroSHEDS is in EPSG:4326 (geographic WGS-84) so ``lon, lat`` map
    directly to ``x, y``. Result dict has the basin's full attribute
    table + a ``geometry_wkt`` field for downstream serialisation.
    """
    ds = ogr.Open(str(shp_path))
    if ds is None:
        raise RuntimeError(f"could not open shapefile {shp_path}")
    layer = ds.GetLayer(0)
    layer.SetSpatialFilterRect(lon, lat, lon, lat)
    # Iterate matches (usually 1; can be ≥2 on shared edges — return
    # the first non-degenerate hit).
    for feat in layer:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        # Tighten: SpatialFilterRect uses bbox; require true Contains.
        pt = ogr.Geometry(ogr.wkbPoint)
        pt.AddPoint_2D(lon, lat)
        if not geom.Contains(pt):
            continue
        attrs = {
            feat.GetFieldDefnRef(i).GetName(): feat.GetField(i)
            for i in range(feat.GetFieldCount())
        }
        attrs["geometry_wkt"] = geom.ExportToWkt()
        return attrs
    return None


def upstream_basin_ids(
    shp_path: Path | str, start_hybas_id: int,
) -> list[int]:
    """Walk ``NEXT_DOWN`` topology to enumerate all basins whose flow
    eventually passes through ``start_hybas_id`` (inclusive).

    Pure attribute-table BFS — geometry is not touched, so this is
    fast even on continent-scale layers.

    Args:
        shp_path: path to a HydroBASINS shapefile (level 1-12).
        start_hybas_id: the pour-point basin's ``HYBAS_ID``.

    Returns:
        sorted list of HYBAS_IDs in the contributing area (always
        contains at least ``start_hybas_id`` itself).
    """
    ds = ogr.Open(str(shp_path))
    if ds is None:
        raise RuntimeError(f"could not open shapefile {shp_path}")
    layer = ds.GetLayer(0)
    fields = {layer.GetLayerDefn().GetFieldDefn(i).GetName()
              for i in range(layer.GetLayerDefn().GetFieldCount())}
    if "HYBAS_ID" not in fields or "NEXT_DOWN" not in fields:
        raise RuntimeError(
            f"shapefile {shp_path} missing HYBAS_ID/NEXT_DOWN — "
            f"is this really HydroBASINS? fields={sorted(fields)}"
        )
    # Build NEXT_DOWN → [HYBAS_ID, ...] inverted index in one pass.
    children: dict[int, list[int]] = {}
    all_ids: set[int] = set()
    for feat in layer:
        hid = int(feat.GetField("HYBAS_ID"))
        nd = int(feat.GetField("NEXT_DOWN"))
        all_ids.add(hid)
        if nd:  # 0 means "drains to ocean / endorheic sink"
            children.setdefault(nd, []).append(hid)
    if start_hybas_id not in all_ids:
        raise ValueError(
            f"start_hybas_id={start_hybas_id} not found in {shp_path}"
        )
    # BFS upstream.
    upstream: list[int] = []
    queue: deque[int] = deque([start_hybas_id])
    visited: set[int] = set()
    while queue:
        cur = queue.popleft()
        if cur in visited:
            continue
        visited.add(cur)
        upstream.append(cur)
        for child in children.get(cur, []):
            if child not in visited:
                queue.append(child)
    return sorted(upstream)


def write_watershed_geojson(
    shp_path: Path | str,
    hybas_ids: list[int],
    out_path: Path | str,
) -> dict:
    """Union the geometries of ``hybas_ids`` into a single watershed
    polygon and write it to ``out_path`` as GeoJSON (EPSG:4326).

    Returns a small summary dict (area_km2 sum, n_basins, bbox).

    We use OGR's ``UnionCascaded`` over the matching features — accurate
    enough for cartographic display + downstream LULC mask use. For
    rigorous tessellation-free area we sum the ``SUB_AREA`` attribute
    (km²) which HydroBASINS pre-computes on a Mollweide projection.

    Note:
        Builds an ``IN (...)`` SQL filter listing every HYBAS_ID, so
        practical limit is ~50-100k basins (OGR-SQL parser). Real fish-
        ecology cases stay well under that; if you ever hit it, batch
        the call into 10k-ID chunks and union the resulting GeoJSONs.
    """
    if not hybas_ids:
        raise ValueError("hybas_ids is empty")
    ids_set = set(hybas_ids)
    ds = ogr.Open(str(shp_path))
    if ds is None:
        raise RuntimeError(f"could not open shapefile {shp_path}")
    layer = ds.GetLayer(0)

    # OGR's SQL escape isn't trivial; HYBAS_IDs are ints, so we can
    # build a safe IN list ourselves.
    if not all(isinstance(i, int) for i in hybas_ids):
        raise TypeError("hybas_ids must contain ints only")
    in_clause = ",".join(str(i) for i in hybas_ids)
    layer.SetAttributeFilter(f"HYBAS_ID IN ({in_clause})")

    collection = ogr.Geometry(ogr.wkbMultiPolygon)
    area_km2 = 0.0
    bbox = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    matched: set[int] = set()
    for feat in layer:
        hid = int(feat.GetField("HYBAS_ID"))
        if hid not in ids_set:
            continue
        matched.add(hid)
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        sa = feat.GetField("SUB_AREA") if "SUB_AREA" in {
            feat.GetFieldDefnRef(i).GetName()
            for i in range(feat.GetFieldCount())
        } else None
        if sa is not None:
            area_km2 += float(sa)
        x_min, x_max, y_min, y_max = geom.GetEnvelope()
        bbox[0] = min(bbox[0], x_min)
        bbox[1] = min(bbox[1], y_min)
        bbox[2] = max(bbox[2], x_max)
        bbox[3] = max(bbox[3], y_max)
        if geom.GetGeometryType() == ogr.wkbPolygon:
            collection.AddGeometry(geom.Clone())
        else:
            for k in range(geom.GetGeometryCount()):
                collection.AddGeometry(geom.GetGeometryRef(k).Clone())

    missing = ids_set - matched
    if missing:
        raise RuntimeError(
            f"requested {len(ids_set)} basins but only {len(matched)} "
            f"matched in shapefile. Missing first 5: "
            f"{sorted(missing)[:5]}"
        )

    union = collection.UnionCascaded()
    if union is None:
        raise RuntimeError("UnionCascaded produced no geometry")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    driver = ogr.GetDriverByName("GeoJSON")
    if out_path.exists():
        out_path.unlink()
    out_ds = driver.CreateDataSource(str(out_path))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    out_layer = out_ds.CreateLayer("watershed", srs, ogr.wkbMultiPolygon)
    out_layer.CreateField(ogr.FieldDefn("area_km2", ogr.OFTReal))
    out_layer.CreateField(ogr.FieldDefn("n_basins", ogr.OFTInteger))
    feat_defn = out_layer.GetLayerDefn()
    feat = ogr.Feature(feat_defn)
    feat.SetField("area_km2", float(area_km2))
    feat.SetField("n_basins", len(hybas_ids))
    feat.SetGeometry(union)
    out_layer.CreateFeature(feat)
    feat = None
    out_ds = None  # flush

    return {
        "area_km2": area_km2,
        "n_basins": len(hybas_ids),
        "bbox": tuple(bbox),
        "out_path": str(out_path),
    }
