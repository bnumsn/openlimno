# M0 Exit Checklist

> SPEC v0.5 §10.1. Until every box below is ticked, M1 does not start.

## 1. Three named maintainers, signed

- [ ] Maintainer 1: name, affiliation, email, GPG fingerprint, signed PR to `docs/governance/MAINTAINERS.md`
- [ ] Maintainer 2: same
- [ ] Maintainer 3: same
- [ ] At least 2 distinct affiliations
- [ ] CODEOWNERS updated with handles, no `_TBD_` remaining
- [ ] Each module (`wedm`/`preprocess`/`hydro`/`habitat`/`passage`/`studyplan`) has primary + secondary reviewer (bus factor ≥ 2)

## 2. WEDM v0.1 JSON-Schema + sample data

- [x] All schemas in `src/openlimno/wedm/schemas/` (10 schemas committed, Draft 2020-12 self-validate)
- [x] `pixi run validate-schemas` self-validates every schema
- [x] **Lemhi River sample data package** built via `tools/build_lemhi_dataset.py`:
      - real USGS 13305000 discharge (366 days)
      - public-value steelhead HSI (Bovee 1978 / Raleigh 1984)
      - synthetic mesh / cross-sections / rating curve / redd counts (clearly labeled)
      - manifest.json tracking real-vs-synthetic
- [x] Sample data round-trips through schema validator (`tests/integration/test_lemhi_dataset.py`, 15 tests pass)
- [x] `examples/lemhi/case.yaml` validates against case.schema.json

## 3. SCHISM integration ADR

- [x] ADR-0002 promoted Proposed → **Accepted** (2026-05-07)
- [x] LTS version selected: **v5.11.0** (rationale in ADR upstream survey table)
- [x] conda-forge availability confirmed: **NOT packaged** → ADR pivoted to OCI container
- [x] `ghcr.io/openlimno/schism:5.11.0` Dockerfile sketched in ADR-0002 §Implementation
- [ ] Subprocess wrapper full implementation — M3 deliverable, stub in place

## 4. 1D engine build-vs-buy ADR

- [x] ADR-0003 promoted Proposed → **Accepted (build, minimal scope)** (2026-05-07)
- [x] Vendor survey scoring documented in ADR-0003 (MASCARET/HEC-RAS/SWMM/SOBEK all dropped)
- [x] Selection: **Build (in-house Manning normal-depth + standard step)**
- [x] Implementation prototype: `src/openlimno/hydro/builtin_1d.py` runs Lemhi end-to-end (8 unit tests)
- [x] Implementation plan documented in ADR (M1 ~50 lines done, M2 ~200 lines for standard step)

## 5. 1.0 capability boundary frozen statement

- [ ] `SPEC.md` §0.3 + Appendix A consistent (SPEC v0.5 already aligned; PSC re-affirms)
- [ ] PSC issues "1.0 Capability Boundary Statement" PR, signed by all 3 maintainers

## 6. Three-platform CI passing

- [ ] `lint` job green
- [ ] `typecheck` job green
- [ ] `schema-validation` job green
- [ ] `test` matrix green on linux-amd64, macos (Apple Silicon + Intel), win-amd64, Python 3.11+3.12
- [ ] `benchmark-fast` green (MMS + Toro placeholders OK at M0)
- [ ] `docs` mkdocs strict build green
- [ ] `spec-scope-check` placeholder runs

## Bonus (recommended for M0)

- [ ] M0 review meeting minutes posted to `docs/governance/meetings/`
- [ ] Project announcement / call-for-maintainers blog post
- [ ] First three regulatory reviewers-of-record (§14.3) invited (M2 deliverable but invitations now)
- [ ] Funding application drafted (NSFC / NSF / Horizon Europe / national programs)

## M1 vertical slice (delivered ahead of schedule, 2026-05-07)

To prove the architecture closes end-to-end before maintainers come on board:

- [x] `Builtin1D` MANSQ solver (`src/openlimno/hydro/builtin_1d.py`)
- [x] HSI curve evaluation + composite + cell WUA (`src/openlimno/habitat/`)
- [x] `Case` orchestrator (`src/openlimno/case.py`) — load YAML, validate, solve, habitat, write outputs + provenance
- [x] CLI `openlimno run` wired and working
- [x] `examples/lemhi/quickstart.py` produces a textbook unimodal WUA-Q curve PNG
- [x] 8 end-to-end integration tests pass

## M2 progress (delivered ahead of schedule, 2026-05-07)

Beyond the M1 PHABSIM equivalence target:

- [x] Standard-step backwater (PHABSIM/IFG4 equivalent)
- [x] HMU automatic classification + reach aggregation (cell / HMU / reach scales)
- [x] Passage module: Culvert + SwimmingModel + η_P with Monte Carlo
- [x] Regulatory exports: CN-SL712 four-tuple, US-FERC-4e, EU-WFD ecological status
- [x] StudyPlan IFIM Step 1-2 module + CLI `openlimno studyplan validate|report`
- [x] Drifting-egg evaluation (Chinese pelagic-spawning carps)
- [x] QGIS plugin (M2 alpha read-only viewer) — manual test plan documented
- [x] Bovee 1997 PHABSIM regression benchmark — closed-form ≤1e-3
- [x] Total: **125 tests pass** after M2 phase 1

## M3-M4 progress (additional early delivery, 2026-05-07)

- [x] **Preprocess M1 production code**: CSV/Excel cross-section, USGS QRev ADCP, GeoTIFF DEM (rasterio + GDAL fallback)
- [x] **SCHISM adapter (M3 alpha)**: prepare/run/read_results lifecycle, LTS pin v5.11.0, container + native command builders, dry-run for CI without SCHISM
- [x] **SPEC §7 verification suite**: MMS 1D (5 grid resolutions) + Toro Riemann (placeholder + geometry self-consistency) + Bovee 1997 all green
- [x] **Calibration workflow (M4 alpha)**: scipy 1-parameter Manning n calibration, CLI `openlimno calibrate`, Snakefile template
- [x] **Documentation**: mkdocs user guide filled (install, quickstart, concepts, 7 module pages), mkdocstrings API auto-doc
- [x] M3-M4 phase 1 test count: **156 passing**

## Honest-completion sweep (2026-05-07)

A code audit identified 7 gaps between SPEC promises and implementation depth. All addressed:

- [x] **B. case.run() full integration** — studyplan / HMU multi-scale / regulatory exports auto-invoked from case YAML
- [x] **D. HydroSolver Protocol real implementation** — Builtin1D.prepare/run/read_results work via pickled work-dir state; SCHISM backend wired into case.run() with dry-run fallback for CI
- [x] **C. HSI quality_grade watermarking** — CSV header line + plot diagonal overlay + provenance.wua_quality_grade
- [x] **A. 6 CLI stubs filled** — init / wua / passage / reproduce / studyplan init / hsi upgrade (8 new CLI tests)
- [x] **E. Provenance §1 P7 fields** — per-file WEDM data SHA-256, pixi.lock SHA, parameter fingerprint, quality grade
- [x] **F. Biological observation readers** — 6 tables (fish_sampling / redd_count / pit_tag_event / rst_count / edna_sample / macroinvertebrate_sample) with schema validators (8 tests)
- [x] **G. SCHISM real input generation** — UGRID-2D → hgrid.gr3 ASCII, runnable param.nml, depth-averaged vgrid.in, bctides.in stub (5 new tests)
- [x] Final test count: **180 passing** + 1 skipped (post-1.0 unsteady SWE)

## Final-completion sweep v2 (2026-05-07)

Eight additional gaps identified after the first honest-completion sweep, all addressed:

- [x] **33. Drift-egg auto-run in `case.run()`** — replaces the warning-only stub; `metric: drifting-egg` + `habitat.drifting_egg` block now drive `evaluate_drifting_egg()` per discharge and write `drift_egg.csv`. Schema extended (`case.schema.json` adds `habitat.drifting_egg` with constant or CSV temperature forcing).
- [x] **34. UGRID mesh validator** — `openlimno.preprocess.validate_ugrid_mesh` (UGRID-1D + UGRID-2D); `case.run()` resolves `mesh.uri`, validates, and forwards to SCHISMAdapter.prepare.
- [x] **35. Legacy importers** — best-effort `read_hecras_geometry` (.g0X X1/GR) + `read_river2d_cdg` (NODES/ELEMENTS).
- [x] **36. Snakemake calibrate workflow** — integration test parses calibrate.smk, dry-runs under snakemake when present, skips cleanly otherwise.
- [x] **37. SCHISM dry-run end-to-end** — `case.run()` with backend=schism + `dry_run: true` produces real hgrid.gr3 from a UGRID-2D mesh, falls back to Builtin1D for habitat post-processing. Adapter no longer raises when no binary on PATH (rc=127 + fallback path).
- [x] **38. `examples/phabsim_replication`** — full standalone Bovee 1997 case (build_data.py + case.yaml + quickstart.py + README.md). Analytic-WUA agreement within 1.78e-4 relative error.
- [x] **39. CLI subprocess tests** — `python -m openlimno` shim added (`__main__.py`); subprocess tests exercise help/version/validate/init/run/studyplan via the actual entry point.
- [x] **Final v2 test count: 205 passing**, 3 skipped (snakemake × 2, post-1.0 unsteady SWE × 1)
- [x] Code: ~5,200 LoC src, ~3,200 LoC tests

Remaining for full 1.0 release (M5 / real-world enablement, requires humans):
- [ ] QGIS plugin manual testing on real QGIS LTS 3.34/3.40 (requires QGIS env)
- [ ] CI infrastructure deployed on GitHub Actions (Win/Mac/Linux × Py 3.11/3.12)
- [ ] SCHISM container `ghcr.io/openlimno/schism:5.11.0` built and published
- [ ] PHABSIM-vs-OpenLimno bit-level regression against actual PHABSIM run
- [ ] PEST++ multi-parameter calibration (1.x scope)
- [ ] Real domestic basin case study (China)
- [ ] M5 expert reviewers-of-record signed (CN-SL712 / US-FERC / EU-WFD)
- [ ] 3 named maintainers signed

---

When all ticked: PSC issues a "M0 → M1 transition" announcement on GitHub Discussions and updates this file's status to "M0 EXITED".
