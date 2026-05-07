# User guide

Module-by-module guide. Each page is a focused recipe + API reference pointer.

| Topic | Module | What it does |
|---|---|---|
| [Preprocess](preprocess.md) | `openlimno.preprocess` | Import CSV/Excel cross-sections, USGS QRev ADCP CSVs, GeoTIFF DEMs |
| [Hydrodynamics](hydro.md) | `openlimno.hydro` | Builtin1D (Manning + standard step) and SCHISMAdapter |
| [Habitat](habitat.md) | `openlimno.habitat` | HSI evaluation, WUA, HMU multi-scale aggregation, drifting-egg |
| [Passage](passage.md) | `openlimno.passage` | η = η_A × η_P fish passage analysis |
| [Studyplan](studyplan.md) | `openlimno.studyplan` | IFIM steps 1-2: research design |
| [Regulatory export](regulatory_export.md) | `openlimno.habitat.regulatory_export` | CN-SL712 / US-FERC-4e / EU-WFD output |
| [QGIS plugin](qgis.md) | `openlimno.qgis` | Read-only viewer for results |

Cross-cutting:

- [Concepts](../getting_started/concepts.md): WEDM, HSI rigor, IFIM
- [SPEC](../SPEC.md): full design contract
- [ADRs](../decisions/index.md): architectural decisions
