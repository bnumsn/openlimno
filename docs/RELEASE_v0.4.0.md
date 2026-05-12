# OpenLimno v0.4.0 release notes — fetch system stable

**Released**: 2026-05-12
**Scope**: v0.3.0 → v0.4.0 (7 minor releases)
**Headline**: a subscription-free global data acquisition layer is now
the default for new OpenLimno cases.

## TL;DR

Before v0.3.0, building a new OpenLimno case required hand-downloading
DEM tiles, gauge time series, climate, watersheds, soil and land-cover
from 6+ different portals — and there was no machine-readable trail
back to the source. v0.4.0 closes that loop: **9 fetchers covering 8
data types, all auth-free, all content-addressed, all citation-
emitting**. The 0.4.x line promises no breaking changes to that surface.

If you build cases from scratch, the new entrypoint is:

```bash
openlimno init-from-osm --bbox … \
  --fetch-dem cop30 \
  --fetch-watershed hydrosheds:as:LAT:LON \
  --fetch-soil   soilgrids:LAT:LON \
  --fetch-lulc   worldcover:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX \
  --fetch-species "gbif:Salmo trutta:…" \
  --fetch-climate open-meteo:LAT:LON:SY:EY
```

## What landed (chronological)

| Tag | Date | Headline | New unit tests |
|---|---|---|---|
| v0.3.0 | 2026-… | DEM (Copernicus GLO-30) + USGS NWIS + sidecar provenance | 37 |
| v0.3.1 | 2026-… | Daymet v4 daily climate (N. America 1 km) | +4 |
| v0.3.2 | 2026-… | Open-Meteo archive (global ERA5 backend) | +10 |
| v0.3.3 | 2026-… | HydroSHEDS HydroBASINS watershed delineation | +11 |
| v0.3.4 | 2026-… | ESA WorldCover 10 m global LULC | +12 |
| v0.3.5 | 2026-… | ISRIC SoilGrids 250 m soil properties | +10 |
| v0.3.6 | 2026-… | GBIF species match + occurrence + 8-fetcher e2e smoke | +12 |
| **v0.4.0** | **2026-05-12** | **Stability milestone + design doc** | — |

Total: **311 unit tests** (up from 180 at v0.3.0 baseline). **8/8 e2e
fetcher smoke PASS** on first run against live APIs.

## What the fetch surface guarantees

The 0.4.x line will **not** break:

1. **Entry-point names** — `fetch_copernicus_dem`, `fetch_nwis_daily_discharge`,
   `fetch_daymet_daily`, `fetch_open_meteo_daily`, `fetch_hydrobasins`,
   `find_basin_at`, `upstream_basin_ids`, `write_watershed_geojson`,
   `fetch_esa_worldcover`, `fetch_soilgrids`, `match_species`,
   `fetch_gbif_occurrences`. Pinned by
   `test_fetch_package_exposes_all_fetchers_at_top_level`.
2. **Result dataclass field names** — `DaymetFetchResult.df`,
   `WorldCoverFetchResult.class_km2`, etc.
3. **Cache key shape** — SHA-256 of canonical
   `{url, sorted_params, method}`. Two semantically identical fetches
   produce one cache entry. Pinned by `test_request_key_*`.
4. **Sidecar JSON schema** —
   `case_dir/data/.openlimno_external_sources.json` carries
   `{label, source_type, source_url, fetch_time, produced_file,
    params, notes, sha256_check}` per record.
5. **Citation contract** — every result has a `citation` field with
   APA-style attribution including DOI where available; the CLI folds
   those into `provenance.json` automatically.

New fetchers in the 0.4.x line **may** be added (additive, minor
release). FishBase / GRDC / Sentinel Hub / CDS / Chinese gauges are
explicitly out of scope — see `docs/fetch_system.md` §7 for reasons.

## Coverage by data type × region

| Region | DEM | Discharge | Climate | Watershed | LULC | Soil | Species |
|---|---|---|---|---|---|---|---|
| US / Canada | cop30 | **nwis** | **daymet** (1 km) or open-meteo | hydrosheds (na) | worldcover | soilgrids | gbif |
| Europe / Russia | cop30 | (open-meteo only) | open-meteo | hydrosheds (eu/ar/si) | worldcover | soilgrids | gbif |
| China / Asia | cop30 | (open-meteo only) | open-meteo | hydrosheds (as) | worldcover | soilgrids | gbif |
| Africa / Australia / S. America | cop30 | (open-meteo only) | open-meteo | hydrosheds (af/au/sa) | worldcover | soilgrids | gbif |

The only data-type × region gap is **gauge discharge outside the US**.
There is no public global gauge API with US-NWIS-equivalent ease:
GRDC requires registration + ships monthly, and provincial Chinese
portals require reverse-engineered crawlers (dibiaoshui-style). Those
are tracked as v0.4 P2 → P3 candidates, intentionally outside the
fetch-system charter (which is subscription-free public APIs only).

## Real-data correctness checks

End-to-end smoke against Heihe mid-basin (38.20°N, 100.20°E):

- **SoilGrids texture conservation**: clay 21% + sand 38% + silt 41% =
  **100.1%** (within measurement noise — strong evidence the back-end
  `d_factor` scaling is correctly applied).
- **HydroSHEDS topology cross-check**: my BFS walk of `NEXT_DOWN` +
  cascaded union returned **2503.4 km²**; HydroSHEDS' own
  pre-computed `UP_AREA` says **2503.1 km²** — **0.012% error**,
  proves topology + geometry aggregation are both correct.
- **WorldCover biome match**: top class 74% grassland (288 km²),
  12% bare/sparse, 10% forest — matches Qilian-piedmont
  pastoral/agricultural mix on the ground.

## Engineering quality

- **No new ruff / mypy findings** in any of the 7 ship commits relative
  to the v0.3.0 baseline.
- **Defensive design** pinned across the fetch surface:
  - DEM bbox-in-cache-key (v0.3.0 regression bug)
  - HydroSHEDS no global `ogr.UseExceptions()` (v0.3.3 ship blocker)
  - WorldCover exact-3°-edge no-extra-tile (v0.3.4 regression pin)
  - GBIF null-coord filter despite `hasCoordinate=true`
  - SoilGrids ocean-point empty-layers RuntimeError
  - WorldCover histogram excludes class-0 nodata
  - HydroSHEDS write_watershed_geojson missing-basin loud failure
  - sidecar path-traversal guard
  - hydrosheds zip-slip guard
- **5-round single-AI critique** before every ship (substitute for
  the unavailable `triple_review.sh`).
- **Real-data smoke** for every fetcher before publishing the tag.
- **API surface guard tests** pin `__all__` membership so a future
  refactor can't silently drop an entry-point.

## What's next

The fetch layer is the data plane. The next OpenLimno arcs build on
it:

- **v0.5.0 — WEDM schema v0.2**: `case.yaml` accepts `data.lulc`,
  `data.soil`, `data.species` blocks; the fetch outputs are schema-
  validated rather than free-form filenames.
- **v0.6.0 — habitat × fetch integration**: HSI / WUA / passage
  modules consume LULC + soil + species + climate as first-class
  covariates; `examples/anywhere_bbox/` becomes the canonical "give
  me a bbox + a species, get a fully-validated case" template.
- **v0.7.0 — Studio GUI × fetch**: the desktop GUI gets a Fetch
  panel; a user can build a case end-to-end without touching the
  CLI.

## Migration notes for v0.3.x users

There are **no breaking changes** from v0.3.6 to v0.4.0. The bump is
purely a stability signal. If you were using v0.3.6 you can install
v0.4.0 without code changes.

## Acknowledgements

Built on the open data community: USGS, ORNL DAAC, ECMWF (via
Open-Meteo's archive), HydroSHEDS / Lehner & Grill, ESA WorldCover,
ISRIC SoilGrids, and the GBIF backbone aggregators. The fetch system
exists because they ship subscription-free, citation-friendly APIs.
