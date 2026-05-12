"""Online data acquisition for OpenLimno (v0.3 P0).

Subscription-free public sources only. Every fetch records source URL +
fetch_time + SHA-256 in the returned object so provenance.json can carry
the trail for reproducibility / citation.

Submodules:
    nwis  — USGS National Water Information System (US discharge + rating curve)
    dem   — Copernicus GLO-30 (global) / NASA SRTM (60°N–56°S) DEM tiles
    cache — XDG-cache-aware on-disk cache shared by both fetchers
"""
from __future__ import annotations

from openlimno.preprocess.fetch.cache import (
    CacheEntry,
    cache_dir,
    cached_fetch,
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

__all__ = [
    "CacheEntry",
    "cache_dir",
    "cached_fetch",
    "DEMFetchResult",
    "clip_centerline_to_bbox",
    "cut_cross_sections_from_dem",
    "fetch_copernicus_dem",
    "NWISFetchResult",
    "fetch_nwis_daily_discharge",
    "fetch_nwis_rating_curve",
    "find_nwis_stations_near",
]
