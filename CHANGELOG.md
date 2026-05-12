# Changelog

All notable changes documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
