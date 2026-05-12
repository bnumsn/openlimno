# OpenLimno v1.0.0 release notes

**Released**: 2026-05-12
**Scope**: project's first production-marked release. Freezes the
fetch surface, WEDM 0.2 case schema, and habitat / hydraulics surface
that have been hardening across v0.3 → v0.8.

## TL;DR

Two years ago OpenLimno started as a SPEC-frozen plan to modernise
PHABSIM. v1.0.0 ships the working result:

- **9 fetchers** pulling subscription-free public-API data for DEM,
  discharge (US), climate (N. America + global), watershed, LULC,
  soil, GBIF species, and FishBase species traits.
- **A 1D builtin hydraulics engine** (Manning normal-depth +
  standard step) backing both PHABSIM-equivalent reach-scale habitat
  modelling and a SCHISM 2D wrapping path.
- **Multi-scale habitat assessment** (cell / HMU / reach) with
  drift-egg evaluation for Asian carps + regulatory exports
  (CN SL/Z 712 / US FERC 4(e) / EU WFD).
- **A QGIS plugin GUI** that builds a case from a bbox + a species
  name, runs the model, and visualises results — no CLI required.
- **End-to-end provenance**: every fetched file is content-addressed
  (SHA-256), cached locally, recorded in a sidecar JSON, and
  validated by `openlimno reproduce`.

The 1.0.x line will not break the user-facing surface listed below.

## What's frozen

### Fetch package (`openlimno.preprocess.fetch`)

| Entry point | Coverage | Schema |
|---|---|---|
| `fetch_copernicus_dem(lon_min, lat_min, lon_max, lat_max)` | global | GeoTIFF + bounds |
| `fetch_nwis_daily_discharge(site, start, end)` | US | DataFrame `(time, discharge_m3s, discharge_cfs)` |
| `fetch_nwis_rating_curve(site)` | US | DataFrame `(h_m, Q_m3s, sigma_Q)` |
| `find_nwis_stations_near(lat, lon, radius_km)` | US | DataFrame `(site_no, station_nm, dec_lat_va, dec_long_va)` |
| `fetch_daymet_daily(lat, lon, sy, ey)` | N. America 1 km | Daymet schema |
| `fetch_open_meteo_daily(lat, lon, sy, ey)` | global 1940– | same as Daymet |
| `fetch_hydrobasins(region, level)` + `find_basin_at` / `upstream_basin_ids` / `write_watershed_geojson` | global × 9 continents | shp path + topology |
| `fetch_hydrorivers(region)` | global × 9 continents | shp path |
| `fetch_esa_worldcover(lon_min, lat_min, lon_max, lat_max, year)` | 60°S–84°N | uint8 GeoTIFF + class histogram |
| `fetch_soilgrids(lat, lon, properties, depths, statistic)` | global 250 m | long DataFrame |
| `match_species(scientific_name)` + `fetch_gbif_occurrences(usage_key, bbox)` | global | taxonomy + occurrences |
| `fetch_fishbase_traits(scientific_name)` | starter table (~12 spp) | `FishBaseTraits` dataclass |
| `fetch_china_discharge(source_key, ...)` | interface only — raises without third-party adapter | charter pin |
| `cached_fetch / record_fetch / read_sidecar / verify_sidecar` | infra | infra |

All result dataclasses + the cache/sidecar JSON shape are part of the
frozen surface. 11 result dataclasses pinned by
`test_fetch_package_exposes_all_result_dataclasses`.

### Case document language (WEDM 0.2)

`openlimno: '0.2'` documents may set `case.bbox` + any of:

- `data.dem` (string)
- `data.lulc` (year / version / class_km2 histogram)
- `data.soil` (lat / lon / properties / depths / statistic)
- `data.watershed` (pour_lat / pour_lon / pour_hybas_id / region / level / n_basins / area_km2)
- `data.species_occurrences` (scientific_name / canonical_name / usage_key / family / match_type / confidence / occurrence counts)
- `data.climate` (source / lat / lon / start_year / end_year)
- `data.fishbase_traits` (full FishBaseTraits)

v0.1 documents remain valid (no breakage).

### CLI surface

```
openlimno new <project>                         # scaffold
openlimno validate <case.yaml>                  # JSON-Schema validate
openlimno run <case.yaml>                       # hydraulics → habitat → provenance
openlimno wua <case.yaml> --species --stage     # WUA-Q curve
openlimno reproduce <provenance.json>           # verify SHA chain
openlimno calibrate <case.yaml> --observed ...  # Manning-n + slope fit
openlimno studyplan validate|report ...         # IFIM Step 1-2
openlimno init-from-osm --bbox ... --fetch-*    # build case from scratch
openlimno fetch <case.yaml> --fetch-*           # add fetchers to existing case
```

### GUI surface (QGIS plugin toolbar)

1. 🆕 Build case from OSM river…
2. ⬇ Fetch data into case…
3. ▶ Run case…

Plus menu entries for opening hydraulic-results meshes, WUA-Q CSVs,
and cross-section profile plots.

## Numbers at v1.0.0

| Metric | Value |
|---|---|
| Released tags from v0.3.0 | **19** (v0.3.0 → v1.0.0) |
| Unit tests | **338 passing** |
| End-to-end smoke fetchers | **10/10 PASS** (`tools/fetch_all_smoke.py`, real APIs) |
| Subscription-free fetchers shipped | **9** (10 if you count `fetch_china_discharge`'s charter-pinned stub) |
| Defensive-design regression pins from per-ship critique | **8** (DEM bbox cache, Daymet pre-1980, HydroSHEDS UseExceptions, WorldCover exact-edge tile, SoilGrids d_factor, GBIF null-coord, FishBase enum + monotonicity, cn_hydro charter guard) |
| New ruff / mypy findings vs v0.3.0 baseline | **0 in fetch package**; 35 in `controller.py` (all E702/I001/B008 from the existing GUI dialog style — see v0.7.0 changelog) |

## Real-data correctness (cross-source consistency)

- **SoilGrids texture conservation**: at the Heihe mid-basin test point
  (38.20°N, 100.20°E), clay 21% + sand 38% + silt 41% = **100.1%** —
  the back-end `d_factor` scaling is correctly applied.
- **HydroSHEDS topology cross-check**: my BFS walk of `NEXT_DOWN` +
  `UnionCascaded` aggregates to **2503.4 km²**; HydroSHEDS' own
  pre-computed `UP_AREA` says **2503.1 km²** — error **0.012%**.
- **WorldCover biome match**: top class 74% grassland (288 km²),
  12% bare/sparse, 10% forest — matches Qilian-piedmont
  pastoral/agricultural mix on the ground.
- **GBIF species coverage**: *Salmo trutta* taxonomy matches with
  confidence 99 (EXACT), 1.1 M occurrences in a 10° W. Europe bbox.
- **FishBase starter table**: all 12 species pass enum validation
  (water_type / IUCN status) and range-monotonicity (T_min < T_max,
  depth_min ≤ depth_max).

## Engineering discipline (consistently applied across the arc)

- 5-round single-AI critique before every ship.
- Real-data smoke against live APIs before tagging.
- API-surface regression pins on `__all__` so refactors break CI loudly.
- Every new fetcher carries a defensive-design pin from its 5-round
  critique (DEM bbox, Daymet pre-1980, HydroSHEDS UseExceptions, …).
- Charter pin (v0.8.2): `cn_hydro.py` source must not import
  `requests`/`httpx`/`bs4`/`lxml`/`fontTools` — caught in CI by
  `test_cn_hydro_module_contains_no_crawler_imports`.
- No new ruff/mypy findings vs each ship's parent commit (modulo the
  `controller.py` E702/I001 dialog-style pattern noted in v0.7.0).

## What's NOT in 1.0

Deliberately excluded — tracked for later:

- **Live FishBase REST** — only fully-open distribution is rfishbase R
  dataset dumps. P3 / 1.x.
- **GRDC global discharge** — requires registration. Out of v0.4
  fetch-system charter; would be a separate `openlimno-grdc` plugin.
- **Chinese gauge networks** — v0.8.2 ships the adapter interface;
  concrete crawler implementations live as third-party `openlimno-cn`
  plugins users opt into after auditing their compliance posture.
- **OpenLimno-native 2D/3D solvers** — SCHISM stays the 2D backend in 1.x.
- **GPU acceleration / IBM / population dynamics / WQ-coupling /
  morphodynamics / web GUI** — SPEC v0.5 §0.3 explicitly excludes these
  from 1.0. SPEC v0.5 §13 carries the research roadmap.

## Migration notes

There are **no breaking changes** from v0.8.2 to v1.0.0. v1.0.0 is
the stability commitment; v0.8.2 already had every fetcher + the v0.2
schema. Existing v0.8.x users `pip install --upgrade openlimno` and
keep working unchanged.

## Acknowledgements

- USGS Water Mission Area (NWIS).
- ORNL DAAC (Daymet).
- ECMWF + Copernicus Climate Change Service (ERA5, exposed via Open-Meteo).
- Lehner & Grill + WWF (HydroSHEDS).
- ESA (WorldCover; Zanaga et al. 2022).
- ISRIC World Soil Information (SoilGrids 2.0; Poggio et al. 2021).
- GBIF Secretariat (backbone taxonomy + occurrence aggregation).
- Froese & Pauly + the FishBase team.
- The pyschism / pyqgis / rasterio / GDAL / pandas / numpy projects
  whose APIs OpenLimno wraps.

The fetch system exists because all of the above ship subscription-
free, citation-friendly data.
