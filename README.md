# OpenLimno

> Open-source ecological-flow and fish-habitat decision platform — a
> reproducible interoperability hub for PHABSIM/IFIM studies, HEC-RAS/SCHISM
> hydraulic results, MIKE 21/FM/1D projects, passage analysis, species evidence,
> and regulatory reports.

**Status**: package metadata is **v3.6.1**. The 1.0 line froze its public
API surface at v1.0.0 (2026-05-12); v2.0 / v3.0 added per-cell composite
and a strict-by-default path sandbox respectively; v3.0 → v3.6.1 was
18 rounds of triple-AI CLI code review that closed ~146 substantive
findings. **706 default-gated tests pass; 31 optional/external tests are
deselected by default; ruff 0; mypy `--strict` core + Studio clean.**

> ⚠️ **Stable-major-tag MORATORIUM in effect (2026-05-19)** — per
> [ADR-0011](./docs/decisions/0011-stable-major-tag-moratorium.md), the
> project will NOT cut new `vN.0.0` stable major-version tags until
> the [unfreeze gate](./docs/ROADMAP.md#how-to-unfreeze) closes
> (≥ 3 signed maintainers + ratified CAPABILITY_BOUNDARY + at least
> one of: real PHABSIM Fortran run, real basin case study, or a
> regulatory reviewer-of-record signed). Until then, v1.0–v3.6.1
> should be read as engineering pre-GA snapshots; treat the version
> chain as informational, not as a stability promise.
>
> ⚠️ **External-action phase (2026-05-20)** — internal-code work is
> substantively complete (U6 audit gate closed; 4 R-DOC-AUDIT-WIRED
> passes; 706 default-gated tests green; PEST++ real-binary gate green
> separately). The project is now blocked on **external
> action only**: maintainer recruitment, regulatory reviewer outreach,
> real-basin data acquisition, USFWS PHABSIM source license
> verification. See [`docs/external_action_phase.md`](./docs/external_action_phase.md)
> for the recommended outreach paths and what code work continues
> (narrowly: bug fixes against real reports + docs + U3 container
> work). Do not open PRs adding new features or new audit passes.

**Where to start:**
- New contributors → [`docs/ROADMAP.md`](./docs/ROADMAP.md) (canonical plan + doc index)
- Reviewers → [`docs/reviews/MASTER_INDEX.md`](./docs/reviews/MASTER_INDEX.md) (full triple-AI ledger)
- What 1.0 will + will NOT do → [`docs/governance/CAPABILITY_BOUNDARY_1_0.md`](./docs/governance/CAPABILITY_BOUNDARY_1_0.md)

All 1.0-scope modules implemented end-to-end; case YAML drives the full pipeline:
hydraulics → HSI/WUA cell+HMU → drift egg → regulatory export (CN-SL712 / US-FERC / EU-WFD) → provenance.
v0.3 → v0.8 added a subscription-free fetch surface (9 fetchers, global coverage, see below).

## What it is

OpenLimno is an ecological-flow / fish-habitat assessment platform that sits
between field data, hydraulic models, habitat models, and decision documents:

- **PHABSIM / RHYHABSIM / SEFA lineage** — HSI / WUA / WUA-Q and IFIM reporting
- **HEC-RAS / SCHISM / River2D / TELEMAC / Delft3D / MIKE lineage** — hydraulic
  result interoperability and ecological post-processing
- **HABBY / CASiMiR / MesoHABSIM lineage** — cell / HMU / reach habitat aggregation
- **FishXing lineage** — culvert and passage analysis with attraction × passage decomposition
- **inSTREAM / InSALMO / IBM lineage** — CSV exchange with population-response models

OpenLimno's differentiator is not owning every solver. It provides current data
formats (NetCDF / Parquet / UGRID), modern HSI rigor (Bovee Category I/II/III,
transferability, independence assumption), multi-scale aggregation, provenance,
and regulatory output templates (CN SL/Z 712 / US FERC / EU WFD).

MIKE support is optional: install `openlimno[mike]` to enable `mikeio` /
`mikeio1d` adapters for DFSU/DFS2/DFS0/mesh/RES1D/XNS11 staging imports.
Use `openlimno preprocess diagnose-model --source mike-1d` to check the extra
Linux .NET Runtime requirement before opening real MIKE 1D files.
Repository users can run `pixi install -e mike` to get the DHI readers plus
conda-forge `.NET Runtime` in a reproducible environment.

## What 1.0 does NOT do

To prevent scope creep, 1.0 explicitly excludes (see `SPEC.md` §0.3):

- OpenLimno-native 2D/3D solvers (uses SCHISM externally)
- GPU acceleration
- Uncertainty quantification, data assimilation, ML surrogates
- Regulatory-grade individual-based / population dynamics in the 1.0
  capability boundary; a native non-NetLogo research prototype is available
  via `openlimno ibm-run-native`, with official inSTREAM 7.4 example-case
  input crosswalks via `openlimno ibm-benchmark-instream7` and NetLogo
  `BriefPopOut` summaries via `openlimno ibm-summarize-instream7-brief`,
  but it is not yet a numerically calibrated inSTREAM replacement
- Water temperature / quality / sediment / morphodynamics (1.x)
- Web GUI / cloud / embedded real-time
- Multi-solver BMI interchange

These appear in `SPEC.md` §13 Research Roadmap.

## Quick start

```bash
pixi install
pixi run openlimno --help

# Run the bundled Lemhi (Idaho, USA) example end-to-end:
pixi run openlimno run examples/lemhi/case.yaml
```

## Build a case from scratch (v0.3+)

For an arbitrary river anywhere on Earth, the data fetchers turn a
bbox + a target species into a fully-provenanced case directory:

```bash
pixi run openlimno init-from-osm \
  --bbox 100.10,38.10,100.30,38.30 \
  --output-dir cases/heihe_pilot \
  --fetch-dem cop30 \
  --fetch-watershed hydrosheds:as:38.20:100.20 \
  --fetch-soil    soilgrids:38.20:100.20 \
  --fetch-lulc    worldcover:100.10:38.10:100.30:38.30:2021 \
  --fetch-species "gbif:Schizothorax prenanti:100.10:38.10:100.30:38.30" \
  --fetch-climate open-meteo:38.20:100.20:2020:2024
```

Every fetched layer is content-addressed (SHA-256), cached locally
(`$XDG_CACHE_HOME/openlimno/`), and recorded in
`case_dir/data/.openlimno_external_sources.json` with full source URL,
fetch time, parameters and citation. `openlimno reproduce` verifies
those SHAs end-to-end.

### Data fetcher matrix (subscription-free, no API keys)

| Fetcher flag | Source | Coverage | Notes |
|---|---|---|---|
| `--fetch-dem cop30` | Copernicus GLO-30 | global | 30 m elevation, COG streaming |
| `--fetch-discharge usgs-nwis:…` | USGS NWIS | US | daily Q + rating curve |
| `--fetch-climate daymet:…` | ORNL DAAC Daymet v4 | N. America | 1 km daily |
| `--fetch-climate open-meteo:…` | Open-Meteo (ERA5-Land) | global, 1940– | ~11 km daily, schema = Daymet |
| `--fetch-watershed hydrosheds:…` | HydroSHEDS HydroBASINS v1c | global (9 continents) | upstream catchment + area |
| `--fetch-lulc worldcover:…` | ESA WorldCover 10 m | 60°S–84°N | 11 LCCS classes + km² histogram |
| `--fetch-soil soilgrids:…` | ISRIC SoilGrids 2.0 | global, 250 m | 11 properties × 6 depths |
| `--fetch-species gbif:…` | GBIF backbone + occurrence | global | taxonomic match + bbox records |

Full design in [`docs/fetch_system.md`](./docs/fetch_system.md);
human-run end-to-end smoke at `tools/fetch_all_smoke.py`.

## Documentation

- [`SPEC.md`](./SPEC.md) — frozen technical specification (v0.5)
- [`docs/fetch_system.md`](./docs/fetch_system.md) — fetch package design (v0.4 stable)
- [`docs/RELEASE_v1.3.0.md`](./docs/RELEASE_v1.3.0.md) — interoperability release candidate notes
- [`examples/model_interop/`](./examples/model_interop/) — command recipes for HEC-RAS, TELEMAC, MIKE, HABBY/CASiMiR, and inSTREAM exchange
- [`docs/governance/`](./docs/governance/) — governance, code of conduct, release process
- [`docs/decisions/`](./docs/decisions/) — Architecture Decision Records (ADRs)
- [`docs/triple_review.md`](./docs/triple_review.md) — three-AI code review
  process (Codex + Gemini + Claude). Every release runs all three; the
  audit trail is attached to each GitHub Release. See
  [`docs/reviews/v0.1.0-alpha.4/`](./docs/reviews/v0.1.0-alpha.4/) for
  the canonical worked example where Claude found a TOCTOU bug Codex
  and Gemini both approved.
- [`docs/user_guide/`](./docs/user_guide/) — user guide (M2+)
- [`tools/m0_checklist/`](./tools/m0_checklist/) — M0 deliverables tracker

## Governance

Apache Way / NumFOCUS-aligned. See [`docs/governance/`](./docs/governance/) for:

- 3 named maintainers (≥ 2 institutions)
- Quarterly release cadence
- Bus factor ≥ 2 per core module
- API semver

## License

- Code: [Apache-2.0](./LICENSE)
- Spec, docs, schemas, sample data: [CC-BY-4.0](./LICENSE)

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md).

OpenLimno follows a "scope discipline" rule: any feature listed in `SPEC.md` §0.3 (1.0 non-goals) is treated as Research Roadmap (§13) by default and is not accepted into 1.0 without an SPEC change proposal accepted by the PSC.
