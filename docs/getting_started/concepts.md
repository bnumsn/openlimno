# Core concepts

A 5-minute orientation. For details, jump to [SPEC](../SPEC.md).

## WEDM — Water Ecology Data Model

OpenLimno is built around an open data model. **All inputs and outputs are open formats** (NetCDF / Parquet / GeoParquet / YAML). No private binaries.

Two layers:

1. **Geometry / time-varying fields** — UGRID NetCDF (mesh, water_depth, velocity)
2. **Tabular data** — Parquet (species, HSI curves, observations, redd counts, rating curves, etc.)

WEDM JSON-Schemas live in `src/openlimno/wedm/schemas/`. Validation runs at every PR.

## HSI rigor — hard constraints, not warnings

The HSI methodology has been criticised for thirty years (Mathur 1985, Williams 1996, Lancaster & Downes 2010). PHABSIM buries these criticisms; OpenLimno surfaces them as **hard constraints**:

- Every HSI curve must declare `category` (Bovee 1986 I/II/III), `geographic_origin`, `transferability_score`, `quality_grade`
- Composite functions `geometric_mean` / `arithmetic_mean` assume **independent** variables; OpenLimno requires `acknowledge_independence: true` in the case YAML, or the run **fails to start**
- WUA computed from C-grade HSI is automatically watermarked

See ADR-0006 for rationale.

## IFIM five steps — not just step 3

PHABSIM is the calculation engine for **step 3** (Study Implementation) of the five-step IFIM methodology. OpenLimno also covers:

- **Step 1-2** via the `studyplan` module: problem statement, target species rationale, TUF library/case merge, HSI source decision tree, uncertainty acknowledgment
- **Step 4** (Alternatives Analysis) via `regulatory_export` templates and §13 multi-objective Pareto (post-1.0)

## Multi-scale habitat — cell, HMU, reach

PHABSIM operates at the cell scale only. Modern stream ecology (Frissell 1986; Kemp 1999; Parasiewicz 2001/2007) requires concurrent micro/meso/macro analyses. OpenLimno aggregates WUA at three scales:

- **cell** — per mesh cell (PHABSIM-equivalent)
- **HMU** — hydromorphological mesohabitat units (riffle/run/pool/glide/cascade/step/backwater), Wadeson 1994 / Parasiewicz 2007
- **reach** — user-defined reaches summing HMUs

## Attraction × Passage — η = η_A × η_P

FishXing returns binary pass/fail, conflating two distinct ecological processes. OpenLimno enforces the Castro-Santos 2005 / Bunt 2012 / Silva 2018 decomposition:

- **η_A**: probability fish reaches the entrance (user-input in 1.0; modeled in §13)
- **η_P**: probability of transit given entrance (computed)

Output term is **passage success rate** (η_P), not "passage efficiency" (which means η in literature).

## Drifting eggs — Asian carps + endemic Yangtze species

Pelagic-spawning species (grass carp, silver carp, copper fish) lay eggs that must drift 50-100 km to hatch. Point HSI cannot capture this. OpenLimno's `habitat.drifting_egg` evaluates 1D Lagrangian drift with hatch-temperature integration and slow-water mortality.

## Regulatory output — three jurisdictions

Habitat curves don't ship as final reports; regulators want specific formats:

- **CN-SL712** — China《河湖生态流量计算规范》four-tuple (monthly min / suitable / multi-year-avg% / 90% guarantee)
- **US-FERC-4e** — flow regime by water-year type (wet / normal / dry)
- **EU-WFD** — ecological status class (high / good / moderate / poor / bad)

These are **template skeletons in 1.0**; final regulatory acceptance requires expert review at M2 (SPEC §14.3).

## Scope discipline

OpenLimno 1.0 deliberately excludes (SPEC §0.3):

- Self-developed 2D/3D solver (uses SCHISM externally)
- GPU acceleration
- Uncertainty quantification, data assimilation, ML surrogates
- Individual-based models
- Water temperature, water quality, sediment, morphodynamics
- Web GUI, cloud, embedded real-time

These appear in §13 Research Roadmap. PHABSIM, River2D, and FishXing all stalled when scope outgrew maintainers; OpenLimno is bound to a frozen 1.0 scope by ADR-0010 + the PR template's mandatory scope checkbox.
