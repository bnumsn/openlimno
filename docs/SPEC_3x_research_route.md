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

OpenLimno's `benchmarks/` directory carries adapter contracts for
four reference platforms. The contracts ship in v2.2.0; the actual
reference runs land in 3.x:

| Reference | Adapter status (v2.2.0) | 3.x deliverable |
|-----------|-------------------------|-----------------|
| PHABSIM (Bovee 1986/1997) | Working — closed-form analytic | Tighten threshold to `1e-4` once `phabsim_bovee1997` adds the missing life-stage HSI variants |
| River2D 0.95 (Steffler & Blackburn 2002) | Stub — `is_available() = False` | Containerised Wine + River2D harness; matched Lemhi `River2D.r2d` input; `5%` per-cell equivalence |
| HABBY 0.6+ (INRAE Lyon) | Stub — checks `import habby` | XML-translation bridge; `1e-6` per-cell equivalence on the shared combination-rule menu |
| FishXing 3.0 (USDA FS) | Stub — env-var gated | `.fx3` report parser + curated archive of 5—10 canonical test cases; `5%` velocity equivalence |

The 3.x research route ships these as `benchmark`-marker tests that
run on tagged releases, skipped on PR runs to keep main CI fast.

### Per-cell composite full integration

v2.1.0 shipped `apply_overlay_per_cell` as a library-level API. The
3.x research route wires it through `Case.run`:

* New schema key `habitat.composite_overlay_method = "geom_mean_per_cell"`
  routes Case to use the per-cell engine.
* Provenance, regulatory exports, and watermark headers learn to
  surface per-cell composite results alongside the basin-scalar
  product/geom_mean.
* Per-section cover-SI arrays land via `cover_si_per_section`
  (already shipped in v2.1.0); per-section thermal-SI requires a
  spatial T(x) fetcher (v3.x research route — see below).

### Spatial T(x) thermal raster

`thermal_metrics` currently emits a time-mean scalar from a single
point time series. The per-cell composite engine is ready to consume
a per-cell thermal-SI array, but no fetcher produces spatial T(x)
yet. The 3.x research route lands:

* A spatial-temperature fetcher (candidates: PRISM gridded T, NLDAS
  for North America; ERA5-Land 2-m air-T → river-T regression
  globally).
* Per-cell thermal-SI computation against FishBase preferred ranges.
* Provenance trail for the spatial-T → per-cell-SI chain.

### Multi-parameter calibration (PEST++)

`cli.py calibrate --algo pestpp-glm` currently raises `NotImplementedError`
with a "v3.x research route" pointer. The 3.x ship:

* Bundles PEST++ via container (PESTPP-GLM, PESTPP-IES) for
  multi-parameter Manning's n + roughness + auxiliary-source
  inversion.
* Defines a PEST++ control-file translator from OpenLimno case YAML.
* Adds a `calibrate` integration benchmark on the Bovee 1997 case
  with a single perturbed `manning_n` to verify pestpp-glm recovers
  the truth.

### Pre-1.6.0 baseline lint clean-up

The 6-round review chain held the **changeset** clean (every v1.6.0
— v2.1.0 file passes `ruff check` at commit time) but did not
address pre-1.6.0 drift. 3.x housekeeping:

* `src/openlimno/cli.py` — 12 findings (E702, B904).
* `src/openlimno/gui_core/controller.py` — 74 findings.
* `src/openlimno/preprocess/fetch/dem.py` — 7 findings.
* `tests/unit/test_preprocess_fetch.py` — 31 findings.
* Etc. Total ~170—189 across the repo.

These are pre-existing, not introduced by 1.6.0+ work. The 3.x
research-route ship batches them into one `chore: 2.x baseline
lint clean-up` PR and lands a CI gate against future drift.

### Strict mypy

`pyproject.toml` carries a `# Pragmatic stance for a 2.0 science
codebase` comment explaining why strict-mode mypy is deferred. The
3.x route flips to strict once upstream stubs (yaml, geopandas,
rasterio) stabilise.

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
| **3.x research route** | Multi-model benchmarks, per-cell Case.run integration, spatial T(x), PEST++, baseline lint, strict mypy | Unstable; signature changes allowed. CI gate is `benchmark`-marker only, skipped on PR. |
| **Studio path A** | Independent PyQt6 + PyQGIS GUI | Separate version track (`openlimno-studio`). |
