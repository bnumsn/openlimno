# OpenLimno

> Open-source water ecology modeling platform — a modern replacement for PHABSIM with IFIM five-step workflow support, multi-scale habitat assessment (cell / HMU / reach), and SCHISM-backed 2D capability.

**Status (v1.0.0)**: **production-stable**, **338 tests pass**, **10/10 fetcher e2e PASS** against live APIs.
All 1.0-scope modules implemented end-to-end; case YAML drives the full pipeline:
hydraulics → HSI/WUA cell+HMU → drift egg → regulatory export (CN-SL712 / US-FERC / EU-WFD) → provenance.
v0.3 → v0.8 added a subscription-free fetch surface (9 fetchers, global coverage, see below).
1.0.x will not break the user-facing fetch / case-schema / habitat surfaces; see [`docs/RELEASE_v1.0.0.md`](./docs/RELEASE_v1.0.0.md) for the stability commitments.
See [`tools/m0_checklist/M0_CHECKLIST.md`](./tools/m0_checklist/M0_CHECKLIST.md) for the deployment checklist
(maintainer signing, real SCHISM container build, QGIS LTS testing, real basin study).

## What it is

OpenLimno is a desktop ecological flow / habitat assessment platform that replaces and modernizes:

- **PHABSIM** — 1D habitat suitability modeling (HSI / WUA / WUA-Q)
- **River2D** — 2D habitat suitability (via SCHISM 2D wrapping in 1.0)
- **FishXing** — culvert fish passage analysis (with attraction × passage decomposition)

with current data formats (NetCDF / Parquet / UGRID), modern HSI rigor (Bovee Category I/II/III, transferability, independence assumption), multi-scale aggregation (cell / HMU / reach, MesoHABSIM-compatible), drift-egg evaluation for Asian carps, and regulatory output templates (CN SL/Z 712 / US FERC / EU WFD).

## What 1.0 does NOT do

To prevent scope creep, 1.0 explicitly excludes (see `SPEC.md` §0.3):

- OpenLimno-native 2D/3D solvers (uses SCHISM externally)
- GPU acceleration
- Uncertainty quantification, data assimilation, ML surrogates
- Individual-based / population dynamics
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
