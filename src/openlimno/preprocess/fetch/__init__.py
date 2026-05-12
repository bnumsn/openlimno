"""Online data acquisition for OpenLimno.

Subscription-free public sources only. Every fetch records source URL +
fetch_time + SHA-256 in the returned object so provenance.json can carry
the trail for reproducibility / citation.

Submodules:
    nwis      — USGS NWIS (US discharge + rating curve)
    dem       — Copernicus GLO-30 (global) / NASA SRTM (60°N–56°S) DEM tiles
    daymet    — Daymet v4 daily climate (North America, 1 km)
    openmeteo  — Open-Meteo archive (global, ~11 km ERA5-Land backend)
    hydrosheds — HydroBASINS + HydroRIVERS continental shapefiles
    cache      — XDG-cache-aware on-disk cache shared by all fetchers
    sidecar    — external-source provenance sidecar in case_dir/data/
"""
from __future__ import annotations

from openlimno.preprocess.fetch.cache import (
    CacheEntry,
    cache_dir,
    cached_fetch,
)
from openlimno.preprocess.fetch.daymet import (
    DaymetFetchResult,
    fetch_daymet_daily,
)
from openlimno.preprocess.fetch.hydrosheds import (
    HYDROBASINS_LEVELS,
    HYDROSHEDS_REGIONS,
    HydroshedsLayerResult,
    fetch_hydrobasins,
    fetch_hydrorivers,
    find_basin_at,
    upstream_basin_ids,
    write_watershed_geojson,
)
from openlimno.preprocess.fetch.openmeteo import (
    OpenMeteoFetchResult,
    fetch_open_meteo_daily,
)
from openlimno.preprocess.fetch.dem import (
    DEMFetchResult,
    clip_centerline_to_bbox,
    cut_cross_sections_from_dem,
    fetch_copernicus_dem,
)
from openlimno.preprocess.fetch.nwis import (
    NWISFetchResult,
    fetch_nwis_daily_discharge,
    fetch_nwis_rating_curve,
    find_nwis_stations_near,
)
from openlimno.preprocess.fetch.sidecar import (
    ExternalSourceRecord,
    read_sidecar,
    record_fetch,
    verify_sidecar,
)

__all__ = [
    "CacheEntry",
    "cache_dir",
    "cached_fetch",
    "DEMFetchResult",
    "DaymetFetchResult",
    "fetch_daymet_daily",
    "OpenMeteoFetchResult",
    "fetch_open_meteo_daily",
    "HYDROBASINS_LEVELS",
    "HYDROSHEDS_REGIONS",
    "HydroshedsLayerResult",
    "fetch_hydrobasins",
    "fetch_hydrorivers",
    "find_basin_at",
    "upstream_basin_ids",
    "write_watershed_geojson",
    "clip_centerline_to_bbox",
    "cut_cross_sections_from_dem",
    "fetch_copernicus_dem",
    "NWISFetchResult",
    "fetch_nwis_daily_discharge",
    "fetch_nwis_rating_curve",
    "find_nwis_stations_near",
    "ExternalSourceRecord",
    "read_sidecar",
    "record_fetch",
    "verify_sidecar",
]
