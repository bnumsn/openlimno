# OpenLimno

Open-source water ecology modeling platform. Modern replacement for PHABSIM with IFIM five-step support, multi-scale habitat (cell / HMU / reach), drift-egg evaluation, attraction/passage decomposition, and regulatory output (CN-SL712 / US-FERC / EU-WFD).

> **Status**: M0 setup phase. SPEC v0.5 frozen. See [SPEC.md](SPEC.md).

## Why OpenLimno

PHABSIM (1995), River2D (last release 2010), FishXing (last beta 2012). All canonical IFIM tools have stalled. OpenLimno aims to be the modern, maintained, community-governed replacement.

What's different from a "fork":

- **Open data formats only.** UGRID NetCDF / Zarr / Parquet / GeoParquet. No proprietary binaries.
- **HSI rigor.** Bovee Category I/II/III, transferability scoring, independence acknowledgment as hard constraints.
- **Multi-scale habitat.** cell (PHABSIM-equivalent), HMU (MesoHABSIM), reach (basin-scale).
- **Attraction × passage.** η = η_A × η_P, not FishXing's pass/fail conflation.
- **Drifting-egg evaluation.** Native support for Asian carp / sturgeon workflows.
- **Regulatory output.** CN-SL712 four-tuple, US-FERC 4(e), EU-WFD ecological status.
- **Frozen 1.0 scope, transparent governance, named maintainers, quarterly release.**

## What 1.0 is not

See SPEC §0.3. Briefly: no native 2D/3D solver (uses SCHISM externally), no GPU, no UQ, no IBM, no embedded real-time. These are in the [research roadmap](SPEC.md#13-研究路线-1-0-不做-但保留接口空间).

## Get started

- [Install](getting_started/install.md)
- [Quickstart](getting_started/quickstart.md)
- [Core concepts](getting_started/concepts.md)
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
