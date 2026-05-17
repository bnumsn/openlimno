# OpenLimno

Open-source ecological-flow and fish-habitat decision platform. OpenLimno
connects field data, hydraulic models, habitat suitability, fish passage,
species evidence, population-response exchange, and regulatory reporting in one
reproducible workflow.

> **Status**: v1.0 stable surface freeze; current package metadata v1.3.0.
> SPEC v0.5 remains the core scope contract. See [SPEC.md](SPEC.md).

## Why OpenLimno

The field is split across legacy IFIM/WUA tools, general hydraulic platforms,
habitat-specific packages, passage calculators, and individual/population
models. OpenLimno is the interoperability layer between them: it can preserve
PHABSIM-style WUA outputs, consume or wrap hydraulic results, evaluate habitat
and passage, and emit auditable regulatory products.

What's different from a "fork":

- **Open data formats only.** UGRID NetCDF / Zarr / Parquet / GeoParquet. No proprietary binaries.
- **HSI rigor.** Bovee Category I/II/III, transferability scoring, independence acknowledgment as hard constraints.
- **Multi-scale habitat.** cell (PHABSIM-equivalent), HMU (MesoHABSIM), reach (basin-scale).
- **Attraction × passage.** η = η_A × η_P, not FishXing's pass/fail conflation.
- **Drifting-egg evaluation.** Native support for Asian carp / sturgeon workflows.
- **Regulatory output.** CN-SL712 four-tuple, US-FERC 4(e), EU-WFD ecological status.
- **Model interoperability.** HEC-RAS, River2D, CF/UGRID NetCDF, MIKE optional
  adapters with dependency diagnostics, HABBY/CASiMiR CSV/TXT table exchange,
  and inSTREAM/NetLogo CSV bridges.
- **Frozen 1.0 scope, transparent governance, named maintainers, quarterly release.**

## What 1.0 is not

See [SPEC](SPEC.md) §0.3. Briefly: no native 2D/3D solver (uses SCHISM
externally), no GPU, no UQ, no IBM, no embedded real-time. These are in SPEC
§13 research roadmap.

## Get started

- [Install](getting_started/install.md)
- [Quickstart](getting_started/quickstart.md)
- [Core concepts](getting_started/concepts.md)
- [Competitive positioning](strategy/competitive-positioning.md)
- [Replicate a PHABSIM case](user_guide/index.md)

## Get involved

- [Contributing](https://github.com/openlimno/openlimno/blob/main/CONTRIBUTING.md)
- [Governance](governance/GOVERNANCE.md)
- [Code of Conduct](https://github.com/openlimno/openlimno/blob/main/CODE_OF_CONDUCT.md)
- Monthly PSC meetings (first Tuesday, 15:00 UTC, agenda public)

## Citing

(Pending GMD model description paper — M5/1.0 release.)

## License

- Code: Apache-2.0
- Spec, schemas, docs, sample data: CC-BY-4.0
