# OpenLimno

> Open-source water ecology modeling platform — a modern replacement for PHABSIM with IFIM five-step workflow support, multi-scale habitat assessment (cell / HMU / reach), and SCHISM-backed 2D capability.

**Status**: M0 → M4 (code-layer 1.0 substantially complete) — SPEC v0.5 frozen, **180 tests pass**.
All 1.0-scope modules implemented and integrated end-to-end; case YAML drives the full pipeline:
hydraulics → HSI/WUA cell+HMU → drift egg → regulatory export (CN-SL712 / US-FERC / EU-WFD) → provenance.
See [`tools/m0_checklist/M0_CHECKLIST.md`](./tools/m0_checklist/M0_CHECKLIST.md) for remaining real-world items
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

## Quick start (planned, M2 alpha)

```bash
pixi install
pixi run openlimno --help
pixi run openlimno run examples/lemhi/case.yaml
```

## Documentation

- [`SPEC.md`](./SPEC.md) — frozen technical specification (v0.5)
- [`docs/governance/`](./docs/governance/) — governance, code of conduct, release process
- [`docs/decisions/`](./docs/decisions/) — Architecture Decision Records (ADRs)
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
