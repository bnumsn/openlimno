# OpenLimno SPEC — 3.x Research Route

> Per memory rule `feedback_spec_scope_discipline`: SPEC must clearly
> separate 1.0 / research route / far-future vision tiers without
> blending them.

This document scopes the **3.x research route** — work that is
explicitly out-of-scope for the 1.x and 2.x stable surfaces but is
charter-committed for future research releases. It serves as the
contract between the 2.0 stable line and the research-track ships.

## What goes on the 3.x research route

### Multi-model equivalence benchmarks

OpenLimno's `benchmarks/` directory carries adapter contracts and
external-result readers for four reference platforms:

| Reference | Current adapter status | Remaining external deliverable |
|-----------|-------------------------|-----------------|
| PHABSIM (Bovee 1986/1997) | Working — closed-form analytic | Tighten threshold to `1e-4` once `phabsim_bovee1997` adds the missing life-stage HSI variants |
| River2D 0.95 (Steffler & Blackburn 2002) | Reads exported River2D WUA tables via `RIVER2D_REFERENCE_DIR`; `5%` threshold YAML present | Containerised Wine + River2D binary harness; matched Lemhi `River2D.r2d` input |
| HABBY 0.6+ (INRAE Lyon) | Reads exported HABBY/CASiMiR WUA tables via `HABBY_REFERENCE_DIR`; `1e-6` threshold YAML present | Native HABBY project XML writer/headless run |
| FishXing 3.0 (USDA FS) | Parses archived FishXing CSV/XLS(X) velocity reports via `FISHXING_REPORT_DIR`; `5%` velocity threshold YAML present | Curated archive of 5-10 canonical FishXing cases |

Acceptance thresholds now live in `acceptance.yaml` beside each
benchmark adapter, so threshold changes are reviewable data changes
rather than harness rewrites. The remaining 3.x reference runs ship as
`benchmark`-marker tests that run on tagged releases, outside the
default PR gate.

### Per-cell composite full integration

This route item is now implemented at the OpenLimno engine level.
v2.1.0 shipped `apply_overlay_per_cell` as a library-level API, and
v2.4.0 wired it through `Case.run` via
`habitat.composite_overlay_method = "geom_mean_per_cell"`. Provenance,
regulatory exports, and watermark headers can now surface paired
per-cell composite results alongside the basin-scalar product and
geom-mean paths.

The remaining research work is data production, not the composite
engine. v2.6.0 + v2.6.1 + v2.7.0 closed the YAML-driven inline raster
paths for both thermal *and* cover SI: case.yaml referencing
`data.thermal_raster.uri` and/or `data.cover_raster.uri` (paired with
`data.section_locations.uri`) drives the per-cell composite end-to-end
with zero offline preprocessing. Pre-computed CSV inputs
(`data.thermal_si_per_section.uri`, `data.cover_si_per_section.uri`)
remain available as a full-control fallback.

What stays on the 3.x research route is **per-cell raster *production***
for non-Open-Meteo backends — native PRISM/NLDAS/ERA5 spatial-T
fetchers for finer resolution, plus a real LULC-class-table override
(currently the inline cover path hard-codes `DEFAULT_RIPARIAN_COVER_SI`).

### Spatial T(x) thermal raster

`thermal_metrics` currently emits a time-mean scalar from a single
point time series. The per-cell composite engine is ready to consume
a per-cell thermal-SI array. The local raster bridge is now present:
`thermal_si_from_temperature_raster(...)` evaluates a water-temperature
GeoTIFF inside a geometry, and `thermal_si_per_section(...)` returns
one thermal-SI value per section geometry for
`apply_overlay_per_cell(..., thermal_si_per_cell=...)`.

The remote data-production side is now present through
`fetch_open_meteo_temperature_raster(...)`: it samples the Open-Meteo
historical archive over a lon/lat grid, aggregates daily Stefan
air-to-water temperatures, writes an EPSG:4326 GeoTIFF, and carries the
per-sample cache/provenance trail. Native PRISM/NLDAS raster backends
remain optional higher-resolution additions.

**Deferred to v3.x — high-latitude projected-CRS buffering** (R9-3):
v2.6.1's inline `section_locations.buffer_m` uses a cosine-latitude
approximation when the raster CRS is geographic — accurate to ~1 %
to about ±10.6° latitude, but at 60° latitude a 200 m buffer becomes
~200 m N–S × 101 m E–W (an ellipse, not a circle). For temperate-zone
reaches this is fine; for sub-polar work the right fix is to build
the buffer in a local projected CRS via `pyproj.Geod` or
`shapely.ops.transform`, which needs additional `pyproj` plumbing
that's out of scope for v2.x. Users hitting this can either supply
a projected raster directly (v2.6.1's CRS-reproject path keeps
`buffer_m` in raster units when the raster CRS is projected) or
pre-compute per-section thermal SI offline via
`thermal_si_per_section` with explicitly projected geometries and
plug it in via `data.thermal_si_per_section.uri`.

### Multi-parameter calibration (PEST++)

`cli.py calibrate --algo pestpp-glm` now generates a PEST++ GLM
workspace and can execute it with `--run-pestpp` when `pestpp-glm` is
installed. The optional `pestpp` pixi environment installs the
conda-forge PEST++ binary, and `pixi run -e pestpp test-pestpp`
exercises a real `pestpp-glm` process against an OpenLimno-generated
workspace.

The remaining enhancement is packaging, not core integration: publish a
container wrapper for deployments that do not use pixi/conda.

### Pre-1.6.0 baseline lint clean-up

This housekeeping item is closed. v2.4.1 removed the pre-1.6.0 ruff
drift and made `pixi run lint` cover `src/`, `tests/`, and
`benchmarks/_compare`. The default `pixi run check` gate now includes
that repository lint surface so future drift fails loudly.

### Strict mypy

The non-GUI core strict gate is now present as
`pixi run typecheck-strict-core` and is included in `pixi run check`.
It runs `mypy --strict src/openlimno` while excluding the dynamic
GUI/QGIS integration layers (`gui_core`, `studio`, `qgis`), where
upstream PyQt/QGIS stubs remain the limiting factor.

The GUI/QGIS layer now has a separate `typecheck-strict-gui-qgis`
gate included in `pixi run check`. It enforces strict local annotations
while allowing untyped third-party Qt/QGIS calls and decorators because
those runtime APIs still do not ship stable type information.

## What stays out of 3.x

* **OpenLimno Studio path A** (PyQt6 + embedded PyQGIS canvas
  independent GUI). Memory: `project_studio.md`. Separate ship
  track, not a research-route deliverable.
* **F11** cosmetic `_composite_view` column rename. v2.0.0 charter
  decision; would break imports for no functional benefit. Stays
  deferred indefinitely unless an external public-API audit
  demands it.
* **Multi-language top-level architecture changes.** Memory:
  `feedback_polyglot`. Architecture stays language-neutral; module
  layer picks per case.

## Tier separation

| Tier | What ships here | Stability promise |
|------|-----------------|-------------------|
| **1.x** (production stable; 1.0.0 — 1.10.1) | Composite-overlay scalar surface, atomic-write, HSI quality grading, regulatory exports, fetch package, builtin-1D + SCHISM | Frozen at the v1.0.0 surface freeze. Patch ships only. |
| **2.x** (stable major; 2.0.0 — present) | Per-cell composite library API, 6-round-review polish, charter-restated public API | Public API frozen. Additive features only; breaking changes require 3.x. |
| **3.x research route** | Reference-platform result readers, spatial-T fetcher/provenance, PEST++ runner validation, optional GUI/QGIS strict typing | Unstable; signature changes allowed. External benchmark gates stay outside the default PR path. |
| **Studio path A** | Independent PyQt6 + PyQGIS GUI | Separate version track (`openlimno-studio`). |
