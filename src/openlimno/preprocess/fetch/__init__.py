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
    watershed_climate — 5-point watershed-aware climate aggregator (v1.2)
    cache      — XDG-cache-aware on-disk cache shared by all fetchers
    sidecar    — external-source provenance sidecar in case_dir/data/
"""

from __future__ import annotations

from openlimno.preprocess.fetch.cache import (
    CacheEntry,
    cache_dir,
    cached_fetch,
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
from openlimno.preprocess.fetch.daymet import (
    DaymetFetchResult,
    fetch_daymet_daily,
)
from openlimno.preprocess.fetch.dem import (
    DEMFetchResult,
    clip_centerline_to_bbox,
    cut_cross_sections_from_dem,
    fetch_copernicus_dem,
)
from openlimno.preprocess.fetch.fishbase import (
    FISHBASE_CITATION,
    IUCN_STATUSES,
    WATER_TYPES,
    FishBaseTraits,
    fetch_fishbase_traits,
    list_starter_species,
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
from openlimno.preprocess.fetch.nwis import (
    NWISFetchResult,
    fetch_nwis_daily_discharge,
    fetch_nwis_rating_curve,
    find_nwis_stations_near,
)
from openlimno.preprocess.fetch.openmeteo import (
    OpenMeteoFetchResult,
    fetch_open_meteo_daily,
)
from openlimno.preprocess.fetch.sidecar import (
    ExternalSourceRecord,
    read_sidecar,
    record_fetch,
    verify_sidecar,
)
from openlimno.preprocess.fetch.soilgrids import (
    ALL_DEPTHS as SOILGRIDS_ALL_DEPTHS,
)
from openlimno.preprocess.fetch.soilgrids import (
    DEFAULT_DEPTHS as SOILGRIDS_DEFAULT_DEPTHS,
)
from openlimno.preprocess.fetch.soilgrids import (
    DEFAULT_PROPERTIES as SOILGRIDS_DEFAULT_PROPERTIES,
)
from openlimno.preprocess.fetch.soilgrids import (
    SoilGridsFetchResult,
    fetch_soilgrids,
)
from openlimno.preprocess.fetch.spatial_temperature import (
    BBox,
    SpatialTemperatureRasterResult,
    fetch_open_meteo_temperature_raster,
)
from openlimno.preprocess.fetch.species import (
    SpeciesMatchResult,
    SpeciesOccurrencesResult,
    fetch_gbif_occurrences,
    match_species,
)
from openlimno.preprocess.fetch.watershed_climate import (
    WatershedClimateResult,
    fetch_watershed_climate,
    watershed_sample_points,
)
from openlimno.preprocess.fetch.worldcover import (
    WORLDCOVER_CLASSES,
    WORLDCOVER_EPOCHS,
    WorldCoverFetchResult,
    fetch_esa_worldcover,
)

__all__ = [
    "CN_HYDRO_CHARTER_NOTE",
    "FISHBASE_CITATION",
    "HYDROBASINS_LEVELS",
    "HYDROSHEDS_REGIONS",
    "IUCN_STATUSES",
    "SOILGRIDS_ALL_DEPTHS",
    "SOILGRIDS_DEFAULT_DEPTHS",
    "SOILGRIDS_DEFAULT_PROPERTIES",
    "WATER_TYPES",
    "WORLDCOVER_CLASSES",
    "WORLDCOVER_EPOCHS",
    "BBox",
    "CacheEntry",
    "ChinaDischargeResult",
    "ChinaHydroAdapter",
    "ChinaHydroNotEnabledError",
    "DEMFetchResult",
    "DaymetFetchResult",
    "ExternalSourceRecord",
    "FishBaseTraits",
    "HydroshedsLayerResult",
    "NWISFetchResult",
    "OpenMeteoFetchResult",
    "SoilGridsFetchResult",
    "SpatialTemperatureRasterResult",
    "SpeciesMatchResult",
    "SpeciesOccurrencesResult",
    "WatershedClimateResult",
    "WorldCoverFetchResult",
    "cache_dir",
    "cached_fetch",
    "clip_centerline_to_bbox",
    "cut_cross_sections_from_dem",
    "fetch_china_discharge",
    "fetch_copernicus_dem",
    "fetch_daymet_daily",
    "fetch_esa_worldcover",
    "fetch_fishbase_traits",
    "fetch_gbif_occurrences",
    "fetch_hydrobasins",
    "fetch_hydrorivers",
    "fetch_nwis_daily_discharge",
    "fetch_nwis_rating_curve",
    "fetch_open_meteo_daily",
    "fetch_open_meteo_temperature_raster",
    "fetch_soilgrids",
    "fetch_watershed_climate",
    "find_basin_at",
    "find_nwis_stations_near",
    "list_registered_adapters",
    "list_starter_species",
    "match_species",
    "read_sidecar",
    "record_fetch",
    "register_adapter",
    "upstream_basin_ids",
    "verify_sidecar",
    "watershed_sample_points",
    "write_watershed_geojson",
]
