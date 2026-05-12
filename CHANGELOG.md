# Changelog

All notable changes documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **v1.1.0 — thermal habitat suitability (first fetcher × habitat coupling)**:
    - New module `openlimno.habitat.thermal` closes the v0.6 loop: fetched data (FishBase temperature preferences + climate-derived water-temperature series) finally drives a habitat-suitability output rather than just sitting in `provenance.fetch_summary` metadata.
    - `ThermalRange(T_opt_min, T_opt_max, T_lethal_min, T_lethal_max)` dataclass + `ThermalRange.from_fishbase(T_opt_min, T_opt_max, *, lethal_margin_C=5.0)` convenience builder. Default lethal margin = ±5 °C around the FishBase preferred range (literature-standard for stream salmonids + cyprinids).
    - `thermal_hsi(T_C, range)` evaluates the trapezoidal SI curve: 0 below `T_lethal_min`, linear ramp 0→1 across the lower shoulder, plateau SI=1 inside the optimum, linear ramp 1→0 across the upper shoulder, 0 above `T_lethal_max`. Scalar or vectorised.
    - `thermal_suitability_series(temperature_df_or_series, range)` accepts the Daymet / Open-Meteo `T_water_C_stefan` schema directly + emits `[time, T_water_C, thermal_SI]`. Closes the fetcher → habitat pipeline in one call.
    - `thermal_metrics(df)` summary: `mean_SI`, `days_optimal`, `days_lethal`, `days_total`, `optimal_fraction` — what reporting wants without re-aggregating the daily series downstream.
    - 11 new unit tests including a real fetcher × habitat coupling pin: take FishBase's `Oncorhynchus mykiss` preferred range, feed it through `ThermalRange.from_fishbase`, evaluate against a synthetic annual sinusoid in the Open-Meteo schema, and assert the optimal-days count + mean SI land in the expected non-trivial band.
- **v1.0.0 — production-stable release**:
    - No new code surface vs. v0.8.2; v1.0.0 is the **stability commitment**. The fetch package (9 active fetchers + cn_hydro charter-pinned stub), WEDM 0.2 case schema, habitat / hydraulics / passage / regulatory-export modules, and CLI / GUI surfaces are all frozen for the 1.0.x line.
    - PyPI classifier bumped `Development Status :: 1 - Planning` → `Development Status :: 5 - Production/Stable`.
    - `tools/fetch_all_smoke.py` extended to 10 cases: real-API checks for DEM / NWIS / Daymet / Open-Meteo / HydroSHEDS / WorldCover / SoilGrids / GBIF + the v0.8.1 FishBase starter-table lookup + the v0.8.2 cn_hydro charter pin (asserts the wheel never registers an adapter + raises `ChinaHydroNotEnabledError` cleanly). **10/10 PASS** on v1.0.0.
    - `docs/RELEASE_v1.0.0.md` — narrative release notes: frozen fetch + schema + CLI + GUI surfaces, headline numbers (19 tags v0.3.0 → v1.0.0, 338 tests, 8 defensive-design pins), real-data correctness checks (texture conservation 100.1%, HydroSHEDS UP_AREA 0.012% err), engineering discipline summary, what's NOT in 1.0 (live FishBase REST, GRDC, native 2D/3D solver, GPU, IBM — all deferred to 1.x / research roadmap), acknowledgements.
    - README status line bumped to v1.0.0 / 338 tests / 10/10 e2e PASS.
- **v0.8.2 — `cn_hydro` adapter INTERFACE (no crawler code)**:
    - New module `openlimno.preprocess.fetch.cn_hydro` exposes the pluggable interface for Chinese discharge data sources: `ChinaHydroAdapter` ABC + `ChinaDischargeResult` dataclass + `register_adapter(adapter) / list_registered_adapters() / fetch_china_discharge(source_key, station_id, start, end)`. The OpenLimno wheel **never** registers a concrete adapter — by design.
    - `fetch_china_discharge(...)` raises `ChinaHydroNotEnabledError` with a clear pointer at the v0.4 fetch-system charter ("no crawler code in the OpenLimno wheel; install a third-party `openlimno-cn`-style plugin") when called without a registered adapter.
    - Charter rationale documented in the module docstring: Chinese gauge data is reachable only through provincial / basin-commission HTML portals (no public REST); programmatic access requires reverse-engineered crawlers (Cookie / CSRF / custom font tables drift every few months) that violate publisher ToS for automated retrieval + carry regional-compliance implications OpenLimno's downstream users shouldn't inherit silently by `pip install`.
    - 5 new unit tests pin: `ChinaHydroNotEnabledError` raised by default; registry empty by default (charter pin — any future PR that quietly registers an adapter in-tree fails CI); end-to-end interface round-trip with a fake adapter; empty-source_key rejection; **and** a regression pin that `cn_hydro.py` contains no `requests` / `httpx` / `bs4` / `lxml` / `fontTools` imports (the libs that would indicate crawler code creep).
- **v0.8.1 — FishBase species-traits starter table**:
    - `openlimno.preprocess.fetch.fishbase` — `fetch_fishbase_traits(scientific_name)` returns a `FishBaseTraits` dataclass (temperature range, depth range, water type, length max, IUCN status, FishBase per-species citation URL) for ~12 commonly-modelled fish species. Curated from canonical FishBase summary pages.
    - Bundled CSV at `src/openlimno/preprocess/fetch/data/fishbase_traits_starter.csv` — auto-included in the wheel via the existing `[tool.hatch.build] packages` config.
    - Starter species cover the salmonids (rainbow / brown / brook / chinook / Atlantic salmon), Asian carps (grass / common / silver), Yangtze schizothoracines + bronze gudgeon, Chinese sturgeon, and European eel — all the species referenced in OpenLimno's example cases.
    - Live FishBase REST integration is post-1.0 P3 (rOpenSci mirror's URL surface is undocumented for non-R clients; FishBase Azure FB-API has uptime swings; coupling to either has a maintenance cost the v0.4 fetch-system charter doesn't accept). The starter-table dataclass + lookup surface here is the contract a future `fetch_fishbase_live(...)` would conform to.
    - CLI `openlimno fetch --fetch-fishbase starter:SCIENTIFIC_NAME` patches the matched traits into `data.fishbase_traits` in the WEDM v0.2 case document.
    - 8 new unit tests pin: starter-table common-species coverage (Lemhi + anywhere_bbox + cross-region anchors), case-insensitive lookup, `None` on no-match (no exception), empty-name rejection, every CSV row's `water_type` ∈ `WATER_TYPES` enum, every row's `iucn_status` ∈ `IUCN_STATUSES`, and temperature/depth-range monotonicity (catches transposed-value typos at table-edit time).
- **v0.8.0 — `openlimno fetch` CLI + QProcess-driven Studio fetch panel**:
    - New `openlimno fetch <case_yaml>` subcommand: runs `--fetch-*` flags against an EXISTING case (additive to its sidecar + WEDM v0.2 `data.*` blocks) instead of re-building mesh/cross-sections like `init-from-osm`. Exact same `--fetch-*` flag surface as `init-from-osm` so callers compose either entry-point freely. End-of-run patches `openlimno: '0.2'` + the matching `data.*` block into `case.yaml`.
    - `Controller.fetch_data_into_case` rewritten to **subprocess via `QProcess`** instead of the v0.7 in-process `QThread`. A fetcher crash (OGR segfault, requests-plumbing AttributeError, etc.) now stays bounded to the subprocess — QGIS itself is never at risk. Trade-off: ~500 ms cold-start to import `openlimno`+`rasterio`+`osgeo` on the first invocation.
    - GUI streams subprocess stdout to the QGIS status bar live (one line at a time) for per-fetcher progress, captures the full log for the completion dialog, and surfaces non-zero exit codes / crash exits as clear error messages.
    - Dead v0.7 in-process thunk machinery deleted (~250 LoC of unreachable code removed from `controller.py`).
    - Two new regression pins: `test_v08_fetch_data_into_case_uses_qprocess_not_qthread` asserts `QProcess` is used (not `QThread`) and that the `openlimno fetch` CLI command exists — together they prevent a future refactor from quietly losing subprocess crash isolation.
- **v0.7.1 — state snapshot doc**:
    - `docs/STATE_2026_05.md` — single-page inventory of where the project stands after the v0.3 → v0.7 arc: headline numbers (324 tests, 9 fetchers, 8/8 e2e PASS), version history at a glance, full fetcher matrix with pin-test names, WEDM v0.2 schema field map, defensive-design pin catalog (the bug pattern each ship caught + its regression test), end-to-end smoke results, GUI surface (v0.7), region × data-type coverage, what's open / on deck (v0.8.0 / v0.8.1 / v0.8.2 / v1.0.0), and engineering discipline summary.
    - Read this as the fast onboard for the v0.3 → v0.7 work; reach for `docs/SPEC.md`, `docs/fetch_system.md`, `docs/RELEASE_v0.4.0.md`, or individual ADRs for depth.
- **v0.7.0 — Studio GUI fetch panel**:
    - `Controller.fetch_data_into_case` — a single dialog wired to a new "⬇ Fetch data into case…" toolbar entry that lets a user pick a target case + select any subset of the 6 fetchers (DEM / watershed / soil / LULC / species / climate) and run them sequentially in a background `QThread`. The canvas stays responsive; status bar shows per-task progress; completion dialog summarises rows/areas/n_tiles per fetcher.
    - Default values smart-pre-fill from the case's `case.bbox` if it's a WEDM v0.2 document, otherwise from the current map canvas extent. The pour-point/centre coordinates default to the bbox centroid so the user can hit OK on the dialog and get sensible fetches without typing.
    - Each task thunk captures dialog values into a snapshot dict before submission so the worker thread never touches Qt widgets that may have been destroyed by then. Eliminates a class of "QObject deleted" crashes that the same pattern in `build_case_from_osm` was vulnerable to.
    - The sidecar is updated through the same `record_fetch` calls the CLI uses, so GUI-triggered fetches show up identically in `provenance.json` and `openlimno reproduce` audits.
    - QGIS plugin (`plugin.py`) gains the matching `_toolbar_too("⬇ Fetch data into case…", ...)` wiring.
    - 2 new tests: `test_v07_fetch_data_into_case_method_exists` (Controller-level method surface pin) + `test_v07_qgis_plugin_wires_fetch_toolbar_entry` (plugin source contains the wiring — broken refactor surfaces in CI).
- **v0.6.0 — case ↔ fetch integration + anywhere_bbox example**:
    - `Case._build_provenance` surfaces the WEDM v0.2 `data.*` blocks (`dem`/`lulc`/`soil`/`watershed`/`species_occurrences`/`climate`) under a new top-level `provenance.fetch_summary` key. Always present (empty dict on v0.1 cases) so downstream tooling can rely on the key existing.
    - Loud species-match validation: `data.species_occurrences.match_type == "NONE"` or `occurrence_count_total == 0` now emits a `provenance.warnings` entry, surfacing to the user that the case is running with an unverified or unsupported taxon. Catches the common "typo'd Latin name" failure mode before HSI/WUA results get published.
    - `examples/anywhere_bbox/README.md` — canonical end-to-end workflow showing how to build a fully-provenanced case anywhere on Earth from `(bbox, species_name)` alone, using all 6 fetcher flags in one `init-from-osm` invocation. Walks the produced WEDM v0.2 case + provenance trail.
    - 2 new tests: `test_provenance_carries_fetch_summary_key` (regression pin: v0.1 cases still get an empty `fetch_summary` dict) + `test_provenance_fetch_summary_picks_up_v02_data_blocks` (synthesised v0.2 case with `match_type=NONE` + zero occurrences → both warnings fire + both data blocks land in `fetch_summary`).
- **v0.5.0 — WEDM schema v0.2 (fetch-system data pointers)**:
    - `src/openlimno/wedm/schemas/case.schema.json` accepts `openlimno: '0.2'` (and still accepts `'0.1'` — v0.1 documents continue to validate unchanged).
    - New optional `case.bbox` field: `[lon_min, lat_min, lon_max, lat_max]` in EPSG:4326. Populated by `init-from-osm` so downstream regional-statistics modules can find the case extent without re-parsing OSM/mesh files.
    - Six new optional `data.*` blocks for fetch-system outputs:
        - `data.dem` — path to merged Copernicus GLO-30 GeoTIFF.
        - `data.lulc` — ESA WorldCover with `year` / `version` / per-class `class_km2` histogram (validated against the 11 LCCS codes).
        - `data.soil` — ISRIC SoilGrids with `lat` / `lon` / property + depth + statistic enumerations (validated against the 6 known SoilGrids depths + 5 statistics).
        - `data.watershed` — HydroSHEDS catchment GeoJSON with `pour_lat` / `pour_lon` / `pour_hybas_id` / `region` (validated against the 9 continent codes) / `level` (1-12) / `n_basins` / `area_km2`.
        - `data.species_occurrences` — GBIF CSV with full taxonomic match (usage_key / family / order / match_type validated against {EXACT,FUZZY,HIGHERRANK,NONE} / confidence 0-100) + occurrence counts.
        - `data.climate` — Daymet or Open-Meteo CSV with `source` (enum) / `lat` / `lon` / `start_year` / `end_year`.
    - `init-from-osm` collects per-branch fetcher outputs in a `_wedm_patches` dict and emits a single end-of-command patch pass that bumps the case to `openlimno: '0.2'` + folds in `case.bbox` + the matching `data.*` block. v0.1 cases that don't use any fetcher remain on `'0.1'`.
    - 9 new schema unit tests pin: v0.2 version-string acceptance, bbox 4-element requirement, full v0.2 data block validation, and 5 enum-rejection paths (unknown WorldCover class code 35, unknown climate source 'openweathermap', unknown HydroSHEDS region 'xx', unknown SoilGrids depth '0-3cm', unknown GBIF match_type 'PARTIAL').
    - All v0.4 tests still pass (320 unit tests after this ship vs 311 before). v0.1 case schema `$id` deliberately retained at `0.1` to preserve the relative `$ref` graph between `case.schema.json` and `builtin_1d_config.schema.json` / `passage_config.schema.json` / `schism_config.schema.json` / `studyplan.schema.json` — a `0.2` `$id` would have broken every existing case's reproduce-path. WEDM "schema version" here is the case-document language version (carried in `openlimno: '0.2'`), not the JSON-Schema-document `$id`.
- **v0.4.1 — README + release notes sediment**:
    - README.md updated: status line bumped to v0.4.0 / 311 tests; quickstart split into "run the bundled example" + "build a case from scratch" with the full 7-flag `init-from-osm` command for arbitrary bboxes; new "Data fetcher matrix" table covering all 9 fetcher flags with source/coverage/notes; link to `docs/fetch_system.md` added under Documentation.
    - `docs/RELEASE_v0.4.0.md` — narrative release notes for the v0.3.0→v0.4.0 arc: TL;DR, per-tag changelog, stability guarantees, coverage matrix, real-data correctness checks (SoilGrids texture sum 100.1%, HydroSHEDS UP_AREA agreement 0.012%, WorldCover biome match), engineering quality summary (defensive-design pins, 5-round critique discipline, real-data smoke per ship), what's next (v0.5 → v0.7 roadmap), migration notes (none — no breaking changes from v0.3.6).
- **v0.4.0 — fetch system milestone + design document**:
    - `docs/fetch_system.md` — single source of truth for the 9-fetcher matrix, cache + sidecar contracts, citation chain, CLI surface (`init-from-osm --fetch-*`), region coverage matrix, end-to-end smoke entry-point (`tools/fetch_all_smoke.py`), and the explicitly-excluded sources (FishBase / GRDC / Sentinel Hub / CDS / Chinese gauges) with reasoning + roadmap pointers.
    - Marks the v0.3.0–v0.3.6 fetch surface as **stable**. No code changes vs v0.3.6; the bump to v0.4.0 signals: existing fetcher entry-points, result-dataclass field names, cache key shape, sidecar JSON schema, and citation contract will not break in the 0.4.x line. New fetchers in 0.4.x arrive as additive minor releases following the same conventions.
- **v0.3.6 — GBIF species API + e2e fetch smoke**:
    - `openlimno.preprocess.fetch.species` — `match_species(scientific_name)` against `https://api.gbif.org/v1/species/match` returns the GBIF backbone usageKey + full taxonomic path (kingdom → species) + match_type/confidence so callers can validate a case-config species name is recognised. `fetch_gbif_occurrences(usage_key, bbox, *, limit, max_pages)` against `https://api.gbif.org/v1/occurrence/search` walks paginated georeferenced records inside a bbox, returns a DataFrame of `[scientific_name, decimal_latitude, decimal_longitude, event_date, basis_of_record, dataset_name, country, license]`.
    - GBIF cap-respecting defaults: `limit ≤ 300` (per-page max), `max_pages=10` (≤ 3 000 records total) to avoid runaway API usage. Pagination loop stops on `endOfRecords` OR `max_pages`, whichever first; pin tests cover both exits.
    - Null-coordinate defensive filter (despite `hasCoordinate=true` GBIF occasionally returns null lat/lon — pinned by `test_species_occurrence_filters_null_coordinates`).
    - WKT geometry built via `_bbox_to_wkt` (counter-clockwise POLYGON((...))) — string format pinned by test so a GBIF schema change is a visible diff.
    - CLI `init-from-osm --fetch-species gbif:SCIENTIFIC_NAME:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX` writes `data/species_gbif_<usageKey>.csv` + sidecar entry capturing usageKey/family/match_type/page SHAs for re-use audit. FishBase intentionally NOT integrated here — its only fully-open distribution is via rfishbase R dataset dumps; tracked as v0.4 P2.
    - **API surface guard tests**: `test_fetch_package_exposes_all_fetchers_at_top_level` + `test_fetch_package_exposes_all_result_dataclasses` pin that all 9 fetcher entry points + 11 result dataclasses remain in `openlimno.preprocess.fetch.__all__`. Any accidental removal during refactor surfaces as a CI failure rather than a silent downstream ImportError.
    - **End-to-end smoke**: `tools/fetch_all_smoke.py` hits every fetcher against the Heihe mid-basin test point (38.20°N, 100.20°E) + a few cross-source consistency checks (SoilGrids texture sum ≈ 100%, HydroSHEDS UP_AREA vs my union area). Not in CI (talks to 8 APIs, ~80 MB on first run); developer-run verification after refactors. 8/8 PASS on first run with v0.3.6.
    - 12 new unit tests (10 species + 2 API surface).
- **v0.3.5 — SoilGrids 250 m soil properties**:
    - `openlimno.preprocess.fetch.soilgrids` — `fetch_soilgrids(lat, lon, *, properties, depths, statistic)` against `https://rest.isric.org/soilgrids/v2.0/properties/query` (Poggio et al. 2021, doi:10.5194/soil-7-217-2021, CC-BY 4.0). Subscription-free, no key, global 250 m posterior summaries for 11 soil properties × 6 depth layers × 5 statistics (Q0.05 / Q0.5 / Q0.95 / mean / uncertainty).
    - Defaults are the 6 properties most commonly consumed by fish-ecology + rainfall-runoff models (`bdod`/`clay`/`sand`/`silt`/`soc`/`phh2o`) over the top 0-30 cm (`0-5cm`/`5-15cm`/`15-30cm`) at posterior mean. Long-form DataFrame `(property, depth, statistic, value, unit)` — losslessly tidy for multi-property/multi-depth requests.
    - SoilGrids stores values as int × d_factor on the back-end for compact storage; the fetcher auto-applies the inverse scaling so the returned `value` column is already in `target_units` (e.g., raw 250 + d_factor=10 → 25 % clay). Pinned by a unit test so a future schema rename surfaces as a visible failure.
    - Convenience accessor `.get(property, depth, statistic)` for single-cell pluck without pandas filtering.
    - Cache key folds `(lat, lon, properties, depths, statistic)` so distinct points/queries never reuse each other's response.
    - CLI `init-from-osm --fetch-soil soilgrids:LAT:LON` writes `data/soil.csv` + sidecar entry with full property × depth coverage list.
    - 10 new unit tests: input validation (lat/lon range, unknown depth, unknown statistic, empty property list); schema-enum pin (`ALL_DEPTHS` / `ALL_STATISTICS` / `DEFAULT_*`); end-to-end parse with injected JSON payload + d_factor scaling verification (raw 250 / d_factor 10 → 25.0); `.get()` KeyError on missing combo; empty-layers ocean-point RuntimeError; cache-key distinguishability across different points.
    - Real-data smoke: Heihe mid-basin (38.20°N, 100.20°E), 1.8 s, 18 rows. Clay 21% + sand 38% + silt 41% = 100.1% (texture conservation within measurement noise), pH 7.6 microalkaline (consistent with NW calcareous soils), SOC 47.8 g/kg at 0-5 cm tapering to 23.6 g/kg at 15-30 cm (typical alpine-meadow profile).
- **v0.3.4 — ESA WorldCover 10 m LULC**:
    - `openlimno.preprocess.fetch.worldcover` — `fetch_esa_worldcover(lon_min, lat_min, lon_max, lat_max, *, year=2021)` against `https://esa-worldcover.s3.eu-central-1.amazonaws.com/` (Zanaga et al. 2022, CC-BY 4.0). Subscription-free, no key, global 60°S–84°N coverage at 10 m resolution. 11 LCCS-based classes (`tree_cover`/`shrubland`/`grassland`/`cropland`/`built_up`/`bare_sparse_vegetation`/`snow_and_ice`/`permanent_water_bodies`/`herbaceous_wetland`/`mangroves`/`moss_and_lichen`).
    - Reuses the Copernicus DEM tile-streaming pattern (rasterio `/vsicurl/` window reads from 3°×3° tiles, in-memory mosaic) so a 0.2°×0.2° bbox pulls only KBs even though the source tiles are ~100 MB each. Per-tile cache key folds in the bbox so different sub-bboxes don't reuse the wrong subset.
    - Class histogram (`class_pixels` + `class_km2`) computed during fetch using cos(lat) pixel-area shrinkage at the bbox centroid. NULL (class 0) excluded from totals so tile-edge masked pixels don't poison the "non-land" fraction.
    - Both released epochs supported (2020 v100 + 2021 v200) — default 2021.
    - Hard bbox cap of 25 deg² (~9 tiles, ~3 GB peak merge) to prevent OOM on continent-scale queries; users who really want that should hit `gdal_merge` directly.
    - CLI `init-from-osm --fetch-lulc worldcover:LON_MIN:LAT_MIN:LON_MAX:LAT_MAX[:YEAR]`; sidecar records label `lulc_worldcover_<year>`, source_type `esa_worldcover`, full per-class pixel counts + km² for audit + downstream stats.
    - 12 new unit tests: input validation (invalid bbox, out-of-coverage lat, antimeridian crossing, unknown year, oversize cap), tile name decomposition for all 4 hemispheres, 3°-grid tile-for-bbox math (including exact-edge no-extra-tile regression pin), `WORLDCOVER_CLASSES` completeness, `cos(lat)` pixel-area scaling, and histogram-exclude-nodata.
    - Real-data smoke (Heihe mid-basin 100.1–100.3°E × 38.1–38.3°N, 2021 v200): 1 tile, 5.76 M pixels, 386 km² total of which 74% grassland, 12% bare/sparse, 10% forest — matches the Qilian-piedmont pastoral/agricultural mix on the ground.
- **v0.3.3 — HydroSHEDS watershed delineation**:
    - `openlimno.preprocess.fetch.hydrosheds` — `fetch_hydrobasins(region, level)` + `fetch_hydrorivers(region)` against `https://data.hydrosheds.org/file/` (Lehner & Grill 2013, doi:10.1002/hyp.9740). Subscription-free, no key, global coverage via 9 continental zips (af/ar/as/au/eu/gr/na/sa/si). Continental zip cached under XDG with the existing `cached_fetch` machinery.
    - Topology helpers using OGR streaming (no geopandas dependency, no in-memory pre-load): `find_basin_at(shp, lat, lon)` for pour-point lookup; `upstream_basin_ids(shp, hybas_id)` walks `NEXT_DOWN` BFS to enumerate the contributing area; `write_watershed_geojson(shp, ids, out)` cascaded-union → single MultiPolygon GeoJSON with `area_km2` + `n_basins` attributes.
    - Defensive `_safe_extract_zip` with zip-slip rejection (paths escaping the destination directory raise `RuntimeError`).
    - CLI `init-from-osm --fetch-watershed hydrosheds:REGION:LAT:LON[:LEVEL]`; sidecar records label `watershed_hydrosheds`, source_type `hydrosheds_hydrobasins`, full HydroSHEDS citation, `pour_hybas_id` + `area_km2` + `n_basins` for audit.
    - 10 new unit tests covering input validation (unknown region, invalid level), zip-slip guard, hand-rolled mini-shapefile topology (4-basin chain), find_basin_at hit/miss, write_watershed_geojson area aggregation, and the missing-basin failure mode.
- **v0.3.2 — global climate via Open-Meteo**:
    - `openlimno.preprocess.fetch.openmeteo` — `fetch_open_meteo_daily(lat, lon, start_year, end_year, *, include_precip)` against `https://archive-api.open-meteo.com/v1/archive` (ERA5/ERA5-Land reanalysis, Hersbach et al. 2020). Subscription-free, no key, global coverage 1940-present.
    - DataFrame schema identical to Daymet (`tmax_C`/`tmin_C`/`T_air_C_mean`/`T_water_C_stefan` + optional `prcp_mm`); reuses `STEFAN_AIR_TO_WATER_A`/`B` from `daymet.py` so the air→water transform is single-sourced across both fetchers.
    - `OpenMeteoFetchResult` duck-types `DaymetFetchResult` for `.df`/`.cache`/`.lat`/`.lon`/`.elevation_m`/`.citation` — downstream code accepts either type unchanged.
    - CLI `init-from-osm --fetch-climate open-meteo:LAT:LON:SY:EY` (parallel to existing `daymet:` form); sidecar records label `climate_open_meteo`, source_type `open_meteo_archive`, full citation.
    - 10 new unit tests covering input validation (inverted years / pre-1940 / out-of-range lat-lon), end-to-end parse, Stefan-constant sharing, precip-column toggle, sub-zero water-temp clip, missing-`daily`-block error path, and cache-key distinguishability for different points.
- M0 repository scaffolding: pixi.toml, pyproject.toml, CI matrix, governance documents, ADR templates, WEDM JSON-Schema initial drafts
- SPEC v0.5 frozen, Approved-for-M0 (unconditional)
- Lemhi sample data package (`data/lemhi/`): USGS 13305000 real discharge, public-value steelhead HSI (Bovee 1978 / Raleigh 1984), synthetic mesh + cross-sections + rating curve, all schema-validated
- `tools/build_lemhi_dataset.py` reproducible builder (live USGS fetch + offline fallback)
- ADR-0002 SCHISM integration: **Accepted**, LTS pin v5.11.0, OCI container distribution (conda-forge not feasible)
- ADR-0003 1D engine: **Accepted (build, minimal scope)** — in-house Manning + standard step; MASCARET / HEC-RAS / SWMM / SOBEK rejected after upstream survey
- **M1 vertical slice delivered**:
    - `openlimno.hydro.Builtin1D.solve_normal_depth` — MANSQ Manning normal-depth (PHABSIM/MANSQ equivalent)
    - `openlimno.habitat` — HSI evaluation, composite (geom/arith/min/weighted), cell-level WUA, hard `acknowledge_independence` guard
    - `openlimno.case.Case` — end-to-end orchestrator: YAML → validate → hydraulics → habitat → NetCDF/Parquet/CSV + provenance.json
    - `openlimno run` CLI command wired
    - `examples/lemhi/quickstart.py` produces a textbook unimodal WUA-Q curve (peak ~7 m³/s, 65 m² for steelhead spawning)
- **M2 progress (early delivery)**:
    - `openlimno.hydro.Builtin1D.solve_standard_step` — backwater profile from downstream-known WSE (PHABSIM/IFG4 equivalent)
    - `openlimno.habitat.classify_hmu` + `aggregate_wua_by_hmu` — Wadeson 1994 / Parasiewicz 2007 mesohabitat (cascade/step/riffle/run/glide/pool/backwater); ADR-0008
    - `openlimno.passage` — Culvert + SwimmingModel + `passage_success_rate` (η_P; deterministic + Monte Carlo); ADR-0007 attraction-passage decomposition explicit
    - `openlimno.habitat.regulatory_export.cn_sl712` — SL/Z 712-2014 four-tuple (monthly min / suitable / multi-year-avg% / 90% guarantee); ADR-0009
    - `openlimno.habitat.regulatory_export.us_ferc_4e` — FERC 4(e) flow regime by water-year type (wet/normal/dry)
    - `openlimno.habitat.regulatory_export.eu_wfd` — EU WFD ecological status (high/good/moderate/poor/bad) via WUA-based EQR proxy
    - `openlimno.studyplan` — IFIM Step 1-2 study planning module: problem statement, target species rationale, objective variable picker, TUF library/case merge (SPEC §4.4.1.1 priority rules), HSI source decision tree, uncertainty acknowledgment; CLI `openlimno studyplan validate|report`
    - `openlimno.habitat.drifting_egg` — 1D Lagrangian drift evaluation for pelagic-spawning carps (grass carp / silver carp / 圆口铜鱼); SPEC §4.2.6
    - `openlimno.qgis.openlimno_qgis_plugin` — QGIS plugin (M2 alpha read-only viewer), follows ADR-0005 Layer 1 strategy (no in-process OpenLimno deps)
    - **Bovee 1997 PHABSIM regression benchmark** (`benchmarks/phabsim_bovee1997/`) — closed-form rectangular Manning + analytic WUA matched within 1e-3
    - Lemhi data builder extended with `drifting_egg_params.parquet` (3 Chinese pelagic-spawning species)
    - `examples/lemhi/studyplan.yaml` — full IFIM study plan example with TUF override
- Total test count after M2 phase 1: **125 passing**

- **M3-M4 progress (additional early delivery, 2026-05-07)**:
    - `openlimno.preprocess` — production CSV/Excel cross-section reader, USGS QRev CSV ADCP reader (column-alias tolerant), GeoTIFF DEM reader (rasterio + GDAL fallback) with along-line sampling
    - CLI: `openlimno preprocess xs|adcp|dem-info` wired to real implementations
    - `openlimno.hydro.SCHISMAdapter` (M3 alpha) — subprocess wrapper, LTS-pin v5.11.0, container + native command builders, dry-run mode for CI without SCHISM
    - `openlimno.workflows.calibrate_manning_n` — scipy.optimize 1-parameter Manning's n calibration against rating curves; CLI `openlimno calibrate`; Snakefile template at `src/openlimno/workflows/snakefiles/calibrate.smk`
    - SPEC §7 verification suite expanded: MMS 1D (5 grid resolutions), Toro Riemann placeholder + geometry self-consistency, plus Bovee 1997 — all on the PR-required CI path
    - mkdocs user guide filled with real content: install, quickstart, concepts, preprocess, hydro, habitat, passage, studyplan, regulatory_export, qgis pages
    - mkdocstrings auto-doc API reference for 5 modules
- Test count after M3-M4 phase 1: **156 passing**

- **Honest-completion sweep (2026-05-07)** — addressed gaps identified in code audit:
    - **B. case.run() full integration** — studyplan / HMU multi-scale / regulatory_export auto-invoked; cell + HMU WUA tables both written; case YAML `regulatory_export: [...]` now drives outputs (`sl712.csv`, `ferc_4e.csv`, `eu_wfd.csv`)
    - **D. HydroSolver Protocol real implementation** — Builtin1D.prepare/run/read_results now do real work (pickled work-dir state); SCHISM backend wired into `case.run()` with dry-run fallback for environments without SCHISM
    - **C. HSI quality_grade watermarking** — wua_q.csv/wua_hmu.csv get a `# … grade B/C` header; quickstart PNG gets a red diagonal "C-GRADE — TENTATIVE" overlay; provenance.wua_quality_grade recorded
    - **A. CLI 6 stubs filled** — `init` (project skeleton), `wua` (computes + plots), `passage` (full η_P + η_A composition), `reproduce` (SHA-256 verification + optional rerun), `studyplan init` (templated YAML), `hsi upgrade` (interactive + bulk metadata edit)
    - **E. Provenance full SPEC §1 P7 fields** — added per-file SHA-256 of all referenced WEDM data, pixi.lock SHA, parameter fingerprint (case + studyplan + discharges hash), wua_quality_grade
    - **F. Biological observation readers** — `read_fish_sampling`, `read_redd_count`, `read_pit_tag_event`, `read_rst_count`, `read_edna_sample`, `read_macroinvertebrate_sample`, plus `validate_biological_table` with full WEDM schema validation (8 unit tests)
    - **G. SCHISM real input generation** — `_write_hgrid_from_ugrid` converts a UGRID-2D NetCDF into proper hgrid.gr3 ASCII; `_render_param_nml` produces a runnable param.nml skeleton; vgrid.in (depth-averaged) and bctides.in stub written
- **Final test count: 180 passing**, 1 skipped (post-1.0 unsteady SWE)
- Code: ~4,600 LoC src, ~2,500 LoC tests
- Remaining `NotImplementedError`s in code are intentional out-of-scope guards (PEST++ multi-parameter scoped to 1.x; unknown hydro backend rejected)

- **Final-completion sweep v2 (2026-05-07)** — last 8 honest gaps closed:
    - **33. Drift-egg auto-runs from `case.run()`**: `metric: drifting-egg` plus `habitat.drifting_egg` block now drives `evaluate_drifting_egg()` per discharge and writes `drift_egg.csv`; constant + CSV temperature forcing supported. Schema extended (case.schema.json `habitat.drifting_egg`).
    - **34. UGRID mesh validator**: `openlimno.preprocess.validate_ugrid_mesh` covers UGRID-1D and UGRID-2D; `case.run()` resolves `mesh.uri`, validates it, surfaces warnings, and forwards to SCHISMAdapter.prepare.
    - **35. Legacy importers (best-effort)**: `read_hecras_geometry` (HEC-RAS .g0X X1/GR records, fixed-width or comma-delimited bodies) + `read_river2d_cdg` (River2D bed-file NODES/ELEMENTS).
    - **36. Snakemake workflow**: `tests/integration/test_snakemake_calibrate.py` parses the calibrate.smk and dry-runs it under `snakemake` when available; skips cleanly otherwise.
    - **37. SCHISM dry-run e2e**: `tests/integration/test_case_schism_dry_run.py` proves backend=schism + dry_run produces real `hgrid.gr3` from a UGRID-2D mesh and falls back to Builtin1D for habitat post-processing. Adapter no longer raises when no SCHISM binary is on PATH (rc=127 + fallback path).
    - **38. examples/phabsim_replication**: full standalone Bovee 1997 example (build_data.py + case.yaml + quickstart.py + README.md) reproducing analytic WUA within 1.78e-4 relative error; CI-asserted by `tests/integration/test_phabsim_replication_example.py`.
    - **39. CLI subprocess tests**: `tests/integration/test_cli_subprocess.py` spawns `python -m openlimno` (new `__main__.py` shim) and exercises help/version/validate/init/run/studyplan paths via the actual entry-point.
    - **Final test count after v2: 205 passing**, 3 skipped (snakemake-not-installed × 2, post-1.0 unsteady SWE × 1)
    - Code: ~5,200 LoC src, ~3,200 LoC tests

### Changed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- N/A
