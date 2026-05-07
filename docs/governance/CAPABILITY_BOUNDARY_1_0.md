# OpenLimno 1.0 Capability Boundary Statement

> **Status**: Draft (awaiting PSC signatures) · Date: 2026-05-07 · SPEC v0.5
>
> Per SPEC §10.1 / M0 checklist item 5, this document is the public, signed
> capability-boundary statement that locks the 1.0 scope. After all three
> maintainers + PSC sign, the statement is immutable for the 1.0 release line;
> changes require a SPEC Change Proposal (SCP) and re-signature.

## Why this exists

Open-source ecological modeling projects historically suffer two failure modes:

1. **Scope creep** — adding "just one more module" until nothing ever ships.
2. **Marketing drift** — the README, papers, and code start describing
   different capabilities.

This statement is the canonical answer to "what can OpenLimno 1.0 do, and what
will it explicitly *not* do?" It binds README, paper abstracts, conference
talks, regulatory filings, and grant applications to the same boundary.

---

## A. 1.0 Capabilities (IN scope, must work)

### A.1 Data layer
- **WEDM v0.1** — 12 JSON-Schemas (Draft 2020-12), CF-1.8 + UGRID-1.0 NetCDF
  conventions, Apache-2.0 (code) / CC-BY-4.0 (data) dual licensing.
- **Preprocess** — CSV/Excel cross-section, USGS QRev ADCP, GeoTIFF DEM
  (rasterio + GDAL fallback), 6 biological-observation tables (fish sampling,
  redd, PIT tag, RST, eDNA, macroinvertebrate).
- **Legacy importers (best-effort)** — HEC-RAS .g0X (X1/GR records),
  River2D .cdg (NODES/ELEMENTS).
- **UGRID-1D and UGRID-2D mesh validation** at case load time.

### A.2 Hydrodynamics
- **Built-in 1D engine** — Manning normal depth (MANSQ-equivalent) and
  standard-step backwater (PHABSIM/IFG4-equivalent), in-house implementation
  per ADR-0003.
- **SCHISM v5.11.0 LTS adapter** for 2D — subprocess wrapper with
  prepare/run/read_results lifecycle, OCI container distribution
  (`ghcr.io/openlimno/schism:5.11.0`) per ADR-0002, dry-run mode for CI
  without the binary.
- **Calibration** — scipy 1-parameter Manning n inversion against rating
  curves; Snakefile workflow template.

### A.3 Habitat
- **HSI Bovee Category I/II/III rigor** (ADR-0006) with hard
  `acknowledge_independence` guard for geometric/arithmetic composites.
- **Cell / HMU / reach scales** (Wadeson 1994 / Parasiewicz 2007).
- **Drifting-egg evaluation** (SPEC §4.2.6) — 1D Lagrangian for pelagic-spawning
  carps, auto-invoked from `case.run()` when configured.
- **Quality-grade watermarking** — A-grade clean, B-grade footnoted,
  C-grade overlaid with TENTATIVE banner.

### A.4 Passage
- **η = η_A × η_P decomposition** (Castro-Santos 2005; ADR-0007).
- **Culvert + SwimmingModel + Monte-Carlo** for swim-fatigue distributions.

### A.5 Regulatory exports
- **CN SL/Z 712-2014** four-tuple (monthly min / suitable / multi-year-avg% /
  90% guarantee).
- **US FERC §4(e)** flow regime by water-year type.
- **EU WFD** ecological status (high/good/moderate/poor/bad) via WUA-based
  EQR proxy.

### A.6 Workflow scaffolding
- **IFIM Step 1-2 study plan module** + `openlimno studyplan validate|report`.
- **CLI** — 10 top-level commands: init / validate / run / wua / passage /
  calibrate / reproduce / studyplan / hsi / preprocess.
- **Provenance** — SPEC §1 P7: yaml SHA, git SHA, machine, per-file input
  data SHA-256, pixi.lock SHA, parameter fingerprint, quality grade.
- **Reproducibility** — `openlimno reproduce` verifies SHA-256 chain.

### A.7 Verification
- Bovee 1997 PHABSIM closed-form regression (≤1e-3).
- MMS 1D (5 grid resolutions).
- Toro Riemann placeholder + geometry self-consistency.
- 205 passing tests on PR-required CI path.

### A.8 Visualisation
- **QGIS plugin** (M2 alpha read-only viewer) — Layer 1 of ADR-0005.

---

## B. 1.0 Non-goals (OUT of scope, will be rejected at PR review)

The following are **explicitly excluded** from 1.0 to keep the scope shippable.
PRs touching any of these will be closed and pointed at this section.

- ❌ OpenLimno-native 2D/3D hydrodynamic solver (SCHISM is the sole 2D backend)
- ❌ GPU acceleration of any solver
- ❌ Uncertainty quantification / ensemble forecasts / data assimilation
- ❌ ML surrogate models / neural operators
- ❌ Individual-based / agent-based models / population dynamics
- ❌ Water temperature, water quality, sediment transport, bed evolution
- ❌ Web GUI / cloud-native / multi-tenant / REST API
- ❌ Embedded real-time scheduling
- ❌ Multi-solver BMI interchange (only SCHISM is deeply integrated)
- ❌ PEST++ multi-parameter inversion (1.x scope; 1-parameter scipy is in)
- ❌ Unsteady shallow-water solver (post-1.0; placeholder skipped in CI)

---

## C. Research roadmap (SPEC §13 — *NOT* committed for 1.0)

These are aspirational and have a separate, slower track:

- C.1 PEST++ multi-parameter calibration
- C.2 Time-varying meshes (auto morphology)
- C.3 ML / neural-operator surrogates
- C.4 Population-dynamics overlay
- C.5 Cumulative-impact frameworks
- C.6 Cloud / SaaS deployment

Each item requires its own ADR, prototype, and PSC vote before being promoted.

---

## D. Definition of "Done" for 1.0

A 1.0 release tag is cut **only when all of the following hold**:

| # | Criterion | Verification |
|---|---|---|
| D1 | Three named maintainers signed | `docs/governance/MAINTAINERS.md` filled, GPG verified |
| D2 | This statement signed by maintainers + PSC | Signatures section below |
| D3 | Three-platform CI green for ≥30 days | Linux + macOS + Windows × Py 3.11/3.12 |
| D4 | SCHISM container published | `ghcr.io/openlimno/schism:5.11.0` digest pinned |
| D5 | PHABSIM Fortran bit-level regression | One real PHABSIM run compared, table-level Δ ≤ 1e-3 |
| D6 | One real basin case study published | China-domestic preferred (Yangtze tributary or Yellow River) |
| D7 | Three regulatory reviewers-of-record signed | CN-SL712 + US-FERC + EU-WFD experts |
| D8 | QGIS plugin manually validated on LTS 3.34 + 3.40 | Manual test plan signed |

Until **all** of D1-D8 are checked, the project remains in 1.0-rc.

---

## E. Capability claims allowed in marketing

The following statements are **PSC-approved** for use in README, papers,
talks, and grant applications. Any other capability claim requires PSC
review.

> **OpenLimno 1.0** is an open-source desktop platform for instream-flow
> habitat assessment. It replaces the ageing PHABSIM, River2D, and FishXing
> toolchains with a modern data model (WEDM, UGRID + CF NetCDF), a built-in
> 1D hydraulic engine, a deep SCHISM-2D adapter, multi-scale habitat
> evaluation (cell/HMU/reach), and three regulatory export templates
> (CN SL712, US FERC §4(e), EU WFD). It does **not** provide a native
> 2D/3D solver, ML surrogates, or any cloud/web service.

---

## F. Signatures

By signing, each party affirms:

1. They have read SPEC v0.5 in full.
2. They agree the 1.0 scope is exactly as defined in §A above and excludes §B.
3. They will reject scope-violating PRs and update this document via SCP.

### Maintainers (3 required)

| Name | Affiliation | GPG fingerprint | Date | Signature |
|---|---|---|---|---|
| _TBD_ | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |
| _TBD_ | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |
| _TBD_ | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |

### Project Steering Committee (5 required)

| Role | Name | Affiliation | Date | Signature |
|---|---|---|---|---|
| Ecologist | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |
| Water resources engineer | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |
| Software engineer | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |
| At-large 1 | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |
| At-large 2 | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |

### Initial signature workflow

1. The first maintainer opens a PR adding their row + GPG-signed commit.
2. Two co-maintainers review and counter-sign in PR review.
3. PSC members add their rows in subsequent PRs (each requires 2 maintainer reviews).
4. After all 8 signatures, the merged commit's SHA is recorded as the
   "1.0 boundary anchor" and listed in the next release notes.

---

## G. Amendment process

This document changes only via:

- **SCP** (SPEC Change Proposal) referencing the affected section.
- 30-day public comment window on `docs/governance/announcements/`.
- 2/3 maintainer + simple-majority PSC vote.
- New signatures from all current maintainers + PSC.

Removing items from §A (capability regression) requires a major-version bump.
