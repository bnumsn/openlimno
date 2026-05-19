# OpenLimno SPEC — 3.x Research Route

> Per memory rule `feedback_spec_scope_discipline`: SPEC must clearly
> separate 1.0 / research route / far-future vision tiers without
> blending them.

This document scopes the **3.x research route** — work that is
explicitly out-of-scope for the 1.x and 2.x stable surfaces but is
charter-committed for future research releases. It serves as the
contract between the 2.0 stable line and the research-track ships.

## Triggers for cutting v3.0

A v2.x → v3.0 jump is justified when at least one of the following
becomes load-bearing for a real user workflow:

1. **A path-traversal exploit is reported in the wild** — R11-4
   sandbox must land before any third-party-YAML-opening Studio
   release.
2. **The SCHISM 2D backend grows lateral-inflow or point-source
   boundaries** — R11-23 schema expansion + the underlying solver
   integration cross the v2.x additive-only line.
3. **A user runs OpenLimno at sub-polar latitude (> ±60°)** — R9-3
   projected-CRS buffering needs to land for thermal/cover raster
   sampling to remain physically accurate there.
4. **Reference-platform equivalence becomes a blocker for a
   contracted study** — the River2D / HABBY / FishXing harnesses
   ship as default CI gates instead of `benchmark`-marker tests.

None of these are forced by a fixed v2.x sunset; v2.x stays
ship-able indefinitely with additive patches as long as none of the
above is blocking. The 11-round review chain (10 ships, 67 findings,
63 closed) confirms the v2.x line is healthy enough to keep getting
patches.

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

### Path-safety / sandbox for user-supplied YAML inputs

(Deferred from v2.10.1 R11-4. Prototype landed at v2.11.0 — see
"Prototype status" below.) Every `data.*.uri` and
`boundaries.*.{series,ref}` accepts a free-form `uri-reference`
string. After v2.10.1 wires `format_checker`, the schema rejects
spaces and other syntactically broken URIs — but it still accepts
`../../../etc/passwd`-style traversal strings and absolute paths
to anywhere on disk. The Studio GUI opens user-supplied YAMLs, so
this is a real concrete-risk surface, not theoretical.

What v3.x must still ship:

1. Route all 23+ existing `_resolve` call sites in `Case` through
   the new `_resolve_safe` wrapper (v2.11.0 ships the wrapper, but
   the legacy call sites still bypass it — by design, to keep
   v2.x additive-only).
2. Tighten the back-compat path: when `allowed_data_roots` is
   unset but a URI escapes the case dir, v3.x emits a stderr
   warning (v2.11.0 silently allows for back-compat).
3. An audit-style integration test `tests/integration/test_path_sandbox.py`
   that exercises every `Case` method taking a YAML-supplied path
   to confirm none bypass the sandbox.

**Prototype status (v2.11.0)**: shipped the API surface so Studio
and third-party-YAML consumers can opt in TODAY:

* `case.allowed_data_roots` schema field (optional array of strings;
  validates as a list of trusted directories outside the case dir).
* `Case._resolve_safe(uri, *, allow_outside_case=False)` method:
  when `allowed_data_roots` is set, raises `ValueError` for any
  URI that escapes both the case dir and the configured roots;
  when unset, falls back to `_resolve` exactly (zero behavior
  change for existing cases).
* `Case._allowed_data_roots()` helper that lists the active
  allow-set (case dir always included).
* 9 pinned tests in `tests/unit/test_path_sandbox.py` covering
  back-compat, allowed-under-case-dir, allowed-under-configured-root,
  traversal rejection, absolute-outside rejection,
  `allow_outside_case=True` opt-out, the case-dir-always-included
  invariant, schema acceptance, and schema-tightness preservation.

Estimated remaining: medium-effort (≈ 250 LoC + ≈ 8 integration
tests, down from the original 300+8 because v2.11.0 already
landed the API). Must land before any v3.0 stable release because
it's a real exploit vector for Studio users opening third-party
study YAMLs.

### Boundary-condition coverage expansion

(Deferred from v2.10.1 R11-2 + R11-23.) Two related schema
strictness items the v2.10.x sweep explicitly left for v3.x:

* **R11-2 — `boundaries` is optional under `hydrodynamics`**.
  Making it required at the schema level would break the Studio
  "case-from-OSM-bbox" entry point (lemhi-tiny fixture ships
  boundaries-less; the Studio fills them in interactively in a
  later wizard step). The right fix is solver-level, not
  schema-level: when `backend=builtin-1d` AND `boundaries` is
  missing AND the case isn't an OSM-stub (signalled by the
  presence of `case.osm_bbox` or similar), emit a fail-loud
  warning before the solver fabricates defaults. Lives with the
  v3.x solver-level warnings sweep.

* **R11-23 — `additionalProperties: false` on `boundaries` blocks
  lateral inflows / point sources / groundwater exchanges**.
  Not relevant for the current 1D builtin (it only knows
  upstream + downstream), but the SCHISM 2D backend and any
  future expansion of `builtin-1d` to handle lateral inputs will
  need a `boundaries.lateral[]` array and possibly
  `boundaries.point_sources[]`. The schema should grow these
  named sibling keys as first-class entries (NOT loosen
  `additionalProperties` back to `true` — that would re-open the
  v2.10.0 typo regression). Track against the SCHISM 2D
  expansion ship.

Both items belong in the v3.x solver-expansion track; neither is a
patch-release item.

### TIFF fixture generator

(Deferred from v2.10.1 R11-18.) The `examples/composite_hsi/data/`
directory ships binary GeoTIFFs (12×12 thermal_C.tif + 12×12
cover_lulc.tif). If GDAL changes float32/uint8 nodata defaults or
a Windows EOL filter corrupts them on checkout, there's no way to
regenerate from source. v3.x should ship a `make_fixtures.py`
beside the data directory and a CI step that regenerates + diffs
to detect drift. Low priority — purely defensive against tooling
regressions, no user impact today.

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
| **2.x** (stable major; 2.0.0 — 2.10.1) | Per-cell composite library API; 11 rounds of triple-AI CLI review polish; inline thermal + cover raster paths (v2.6.x / v2.7.x); YAML-driven dual-raster composite example (v2.8.0); Studio GUI ↔ headless API consolidation (v2.9.0); WEDM schema strictness sweeps (v2.10.0/v2.10.1: `additionalProperties: false` on `hydrodynamics`, `oneOf` discriminator on boundary `type`, `format_checker` wired) | Public API frozen at the v2.0.0 charter restatement. Additive features only; breaking changes require 3.x. |
| **3.x research route** | Reference-platform result readers (PHABSIM/River2D/HABBY/FishXing), spatial-T fetcher/provenance, PEST++ runner validation, optional GUI/QGIS strict typing, **path-safety sandbox (R11-4)**, **solver-level boundary-conditions warning (R11-2)**, **lateral-inflow / point-source boundary schema (R11-23)**, **TIFF fixture generator (R11-18)**, **high-latitude projected-CRS buffering (R9-3)** | Unstable; signature changes allowed. External benchmark gates stay outside the default PR path. |
| **Studio path A** | Independent PyQt6 + PyQGIS GUI | Separate version track (`openlimno-studio`). |
