# OpenLimno Fetch System (v0.3 → v0.4)

> Status: **stable** as of v0.4.0. The 9 fetchers below form the
> subscription-free data acquisition layer for OpenLimno case builds.
> Public API surface is pinned by `tests/unit/test_preprocess_fetch.py`
> regression guards.

## 1. Why a fetch system?

Building a fish-ecology / hydraulics case from scratch needs at least:

- **Geometry**: DEM (bathymetry/bank elevation), river centerline, cross sections.
- **Hydrology drivers**: discharge time series, climate (air → water temperature), watershed delineation.
- **Habitat covariates**: land cover, soil, target species records.

Pre-v0.3 these were collected by hand (download portals, manual file
handling, no provenance). The fetch system replaces that with a
uniform API surface: each fetcher returns a result dataclass that
carries a `cache` entry (SHA-256 + URL + fetch time) so downstream
`provenance.json` can recover the full lineage of every CSV / TIF /
GeoJSON in `case_dir/data/`.

**Design constraints (set in `feedback_review_cli_only.md`)**:

1. **Subscription-free public sources only** — no API keys in the fetch
   path. Sources requiring registration (CDS, Sentinel Hub, OpenWeather)
   are intentionally excluded even where the registration is free.
2. **Reproducibility**: every fetch is content-addressable. Two
   developers who run `openlimno init-from-osm` with the same flags
   reach byte-identical inputs.
3. **Memoization**: re-runs hit the local cache, not the upstream API.
   Cache is XDG-aware (`$XDG_CACHE_HOME/openlimno/`) so CI / sandboxed
   home dirs don't pollute `~/.cache`.
4. **Citation chain**: each result has a `citation` field that bubbles
   into `provenance.json` so published cases carry attributions
   automatically.

## 2. The 9-fetcher matrix

| Fetcher | Source | Coverage | Auth | Output | v |
|---|---|---|---|---|---|
| `fetch_copernicus_dem` | Copernicus GLO-30 (AWS S3 COG) | global, 84°S–84°N | none | merged GeoTIFF (float32 elev) | 0.3.0 |
| `fetch_nwis_daily_discharge` | USGS NWIS REST | US only | none | DataFrame `(time, discharge_m3s, discharge_cfs)` | 0.3.0 |
| `fetch_nwis_rating_curve` | USGS NWIS measurements | US only | none | DataFrame `(h_m, Q_m3s, sigma_Q)` | 0.3.0 |
| `fetch_daymet_daily` | ORNL DAAC Daymet v4 | N. America, 1 km | none | DataFrame `(time, tmax_C, tmin_C, T_air_C_mean, T_water_C_stefan)` | 0.3.1 |
| `fetch_open_meteo_daily` | Open-Meteo archive (ERA5/ERA5-Land) | global, 1940-present | none | same schema as Daymet | 0.3.2 |
| `fetch_hydrobasins` + topo helpers | HydroSHEDS HydroBASINS v1c | global (9 continents) | none | shapefile path + `find_basin_at` / `upstream_basin_ids` / `write_watershed_geojson` | 0.3.3 |
| `fetch_esa_worldcover` | ESA WorldCover 10 m COG | global, 60°S–84°N | none | merged uint8 GeoTIFF + class histogram | 0.3.4 |
| `fetch_soilgrids` | ISRIC SoilGrids 2.0 REST | global, 250 m | none | long-form DataFrame `(property, depth, statistic, value, unit)` | 0.3.5 |
| `match_species` + `fetch_gbif_occurrences` | GBIF v1 REST | global | none | taxonomy match + paginated occurrence DataFrame | 0.3.6 |

## 3. Shared infrastructure

### 3.1 Cache (`fetch/cache.py`)

```python
@dataclass
class CacheEntry:
    path: Path           # local payload location
    cache_hit: bool      # served from disk vs freshly fetched
    source_url: str      # what was (or would have been) requested
    fetch_time: str      # ISO-8601 of ORIGINAL fetch (not current call)
    sha256: str          # of payload bytes
```

Cache key = `sha256({url, sorted_params, method})`. Two crucial
properties pinned by `test_request_key_*`:

- Stable across param-dict insertion order.
- Folds in **everything** the response could depend on. The v0.3.0 DEM
  bug — bbox NOT in the params dict, causing different bbox calls to
  reuse the first cached subset — set the bar: every fetcher's params
  dict now includes the spatial extent.

### 3.2 Provenance sidecar (`fetch/sidecar.py`)

`case_dir/data/.openlimno_external_sources.json` records, per produced
file:

```json
{
  "label": "watershed_hydrosheds",
  "source_type": "hydrosheds_hydrobasins",
  "source_url": "https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_as_lev12_v1c.zip",
  "fetch_time": "2026-05-12T10:34:01+0800",
  "produced_file": "data/watershed.geojson",
  "params": {…},
  "notes": "HydroSHEDS HydroBASINS v1c level 12 for AS …",
  "sha256_check": "..."
}
```

`openlimno reproduce` verifies these SHAs at run time to detect any
post-fetch tampering.

### 3.3 Citation contract

Every result dataclass exposes a `citation` field with an APA-style
string including the canonical DOI / URL where available. The CLI
wrappers fold these into `provenance.json` automatically. Examples:

- Daymet: `Thornton et al., ORNL DAAC v4 — tile {tile_id}`
- ERA5: `Hersbach et al. 2020, doi:10.1002/qj.3803`
- HydroSHEDS: `Lehner & Grill 2013, doi:10.1002/hyp.9740`
- WorldCover: `Zanaga et al. 2022, doi:10.5281/zenodo.7254221`
- SoilGrids: `Poggio et al. 2021, doi:10.5194/soil-7-217-2021`
- GBIF: backbone taxonomy `doi:10.15468/39omei`; per-occurrence
  license carried in the row's `license` column.

## 4. CLI surface

All 8 case-building fetchers are wired into a single `init-from-osm`
command:

```bash
openlimno init-from-osm \
  --bbox 100.10,38.10,100.30,38.30 \
  --output-dir cases/heihe_pilot \
  --fetch-dem cop30 \
  --fetch-discharge usgs-nwis:13317000:2024-01-01:2024-12-31 \
  --fetch-watershed hydrosheds:as:38.20:100.20 \
  --fetch-soil soilgrids:38.20:100.20 \
  --fetch-lulc worldcover:100.10:38.10:100.30:38.30:2021 \
  --fetch-species "gbif:Schizothorax prenanti:100.10:38.10:100.30:38.30" \
  --fetch-climate open-meteo:38.20:100.20:2020:2024
```

Each `--fetch-*` flag is independent — users opt into the subset they
need. Every fetch produces a file under `case_dir/data/` and a
sidecar record.

## 5. Coverage matrix

| Region | DEM | Discharge | Climate | Watershed | LULC | Soil | Species |
|---|---|---|---|---|---|---|---|
| US / Canada | cop30 | **nwis** | **daymet** (1 km) or open-meteo | hydrosheds (na) | worldcover | soilgrids | gbif |
| Europe / Russia | cop30 | open-meteo only† | open-meteo | hydrosheds (eu/ar/si) | worldcover | soilgrids | gbif |
| China / Asia | cop30 | open-meteo only† | open-meteo | hydrosheds (as) | worldcover | soilgrids | gbif |
| Africa / Australia / S America | cop30 | open-meteo only† | open-meteo | hydrosheds (af/au/sa) | worldcover | soilgrids | gbif |

† No public global gauge-discharge API exists with US-NWIS-equivalent
ease. Chinese / European gauge networks ship behind reverse-engineered
provincial portals (dibiaoshui-style); GRDC global archive is monthly
+ has registration. These are tracked as **v0.4 P2 → P3 fetcher
candidates** but intentionally not in the v0.3 fetch surface.

## 6. End-to-end smoke

`tools/fetch_all_smoke.py` exercises all 8 fetchers against a single
Heihe mid-basin test point and emits a one-line PASS/FAIL per fetcher
plus correctness cross-checks:

- SoilGrids `clay + sand + silt ≈ 100%` (texture conservation).
- HydroSHEDS aggregated `SUB_AREA` vs the pour-point's `UP_AREA`
  attribute — must agree to < 0.1% (validates BFS-walk topology).
- WorldCover top class matches expected biome from a-priori knowledge.

Not in default CI (talks to 8 APIs, ~80 MB on first run). Run locally
after fetch-package refactors via:

```bash
XDG_CACHE_HOME=/tmp/openlimno-smoke-cache python3 tools/fetch_all_smoke.py
```

8/8 PASS on v0.4.0.

## 7. What's NOT in the fetch system

Deliberately excluded from v0.4 — tracked for later:

- **FishBase** — only fully-open distribution is rfishbase R dataset
  dumps. P2.
- **GRDC global discharge** — requires registration + monthly cap. P3.
- **Chinese gauge networks** — reverse-engineered crawler territory
  (dibiaoshui-style); 9 697 stations across 7 basins / 16 provinces;
  needs font-decryption + cookie handling. Out of fetch-system charter
  (the fetch system is subscription-free public APIs); could become a
  separate `openlimno-cn` plugin.
- **Sentinel-2 / HLS optical** — requires Sentinel Hub OAuth or NASA
  Earthdata token. Out of fetch-system charter.
- **ERA5-Land via CDS API** — requires `~/.cdsapirc` registration;
  the same data is reachable for OpenLimno's daily-aggregation needs
  via Open-Meteo's archive endpoint, which is auth-free. P3 only if
  sub-daily ERA5 ever needed.
- **Bathymetry from sonar / single-beam** — out of scope; users
  with field bathymetry plug their own CSV through the existing
  `cross_section.parquet` interface.

## 8. Versioning

v0.3.0 introduced the cache + first 2 fetchers. v0.3.1 → v0.3.6 each
added exactly one fetcher with a real-data smoke. v0.4.0 marks the
fetch surface as **stable** — no breaking changes planned in the
0.4.x line; new fetchers will keep the same dataclass/citation/cache
conventions and arrive as additive minor releases.
