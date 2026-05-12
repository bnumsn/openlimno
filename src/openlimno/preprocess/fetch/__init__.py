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
    worldcover — ESA WorldCover 10 m global LULC (2020 v100, 2021 v200)
    soilgrids  — ISRIC SoilGrids 250 m soil properties (11 vars × 6 depths)
    species    — GBIF backbone taxon match + georeferenced occurrences
    fishbase   — curated FishBase species-traits starter table (~12 spp)
    cn_hydro   — Chinese hydrology adapter INTERFACE (no crawler code)
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
from openlimno.preprocess.fetch.soilgrids import (
    ALL_DEPTHS as SOILGRIDS_ALL_DEPTHS,
    DEFAULT_DEPTHS as SOILGRIDS_DEFAULT_DEPTHS,
    DEFAULT_PROPERTIES as SOILGRIDS_DEFAULT_PROPERTIES,
    SoilGridsFetchResult,
    fetch_soilgrids,
)
from openlimno.preprocess.fetch.cn_hydro import (
    CN_HYDRO_CHARTER_NOTE,
    ChinaDischargeResult,
    ChinaHydroAdapter,
    ChinaHydroNotEnabledError,
    fetch_china_discharge,
    list_registered_adapters,
    register_adapter,
)
from openlimno.preprocess.fetch.fishbase import (
    FISHBASE_CITATION,
    IUCN_STATUSES,
    WATER_TYPES,
    FishBaseTraits,
    fetch_fishbase_traits,
    list_starter_species,
)
from openlimno.preprocess.fetch.species import (
    SpeciesMatchResult,
    SpeciesOccurrencesResult,
    fetch_gbif_occurrences,
    match_species,
)
from openlimno.preprocess.fetch.worldcover import (
    WORLDCOVER_CLASSES,
    WORLDCOVER_EPOCHS,
    WorldCoverFetchResult,
    fetch_esa_worldcover,
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
    "WORLDCOVER_CLASSES",
    "WORLDCOVER_EPOCHS",
    "WorldCoverFetchResult",
    "fetch_esa_worldcover",
    "SOILGRIDS_ALL_DEPTHS",
    "SOILGRIDS_DEFAULT_DEPTHS",
    "SOILGRIDS_DEFAULT_PROPERTIES",
    "SoilGridsFetchResult",
    "fetch_soilgrids",
    "SpeciesMatchResult",
    "SpeciesOccurrencesResult",
    "fetch_gbif_occurrences",
    "match_species",
    "FISHBASE_CITATION",
    "IUCN_STATUSES",
    "WATER_TYPES",
    "FishBaseTraits",
    "fetch_fishbase_traits",
    "list_starter_species",
    "CN_HYDRO_CHARTER_NOTE",
    "ChinaDischargeResult",
    "ChinaHydroAdapter",
    "ChinaHydroNotEnabledError",
    "fetch_china_discharge",
    "list_registered_adapters",
    "register_adapter",
    "ExternalSourceRecord",
    "read_sidecar",
    "record_fetch",
    "verify_sidecar",
]
