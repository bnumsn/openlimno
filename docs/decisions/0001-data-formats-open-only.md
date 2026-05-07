# ADR-0001: Data formats: open standards only

- **Status**: Accepted
- **Date**: 2026-05-07
- **SPEC sections**: §1 P3, §3.1
- **Tags**: data-model, governance

## Context

PHABSIM's `.IFG`, River2D's `.cdg/.bed`, HEC-RAS's `.g0X`, MIKE's `.dfs0` — every legacy stream-habitat tool used a private binary format. Twenty years later, those files are difficult-to-impossible to read without the original (often unmaintained) software. This is a primary reason these tools became unmaintainable.

## Decision

OpenLimno persists **all** project state in open standards only:
- **Geometry / mesh / time-varying fields**: NetCDF-4 (UGRID-1.0 + CF Conventions)
- **Tabular data**: Apache Parquet (or GeoParquet for spatial)
- **Configuration**: YAML 1.2 with JSON-Schema validation
- **Provenance**: JSON

No private binary formats are introduced for native storage. Legacy formats (`.IFG`, `.g0X`, `.cdg`) are **read-only best-effort** in `preprocess`, not contractual.

## Alternatives considered

### Alternative A: Native binary format (rejected)
Would gain: faster IO, smaller files, strict schema control.
Lost: long-term readability, ecosystem (xarray/QGIS/Paraview reads UGRID NetCDF natively), audit-ability.

### Alternative B: Mixed (rejected)
Use NetCDF for fields, custom for tables. Adds complexity, no clear benefit.

## Consequences

### Positive
- Files readable in 20 years using xarray/QGIS without OpenLimno
- QGIS plugin can use native GDAL drivers, avoiding plugin-Python dependency hell (see ADR-0005)
- Audit & reproducibility free: file format itself is documented
- Cloud-native path open (Zarr in §13)

### Negative
- Slightly larger files than custom binary
- Must respect CF / UGRID schema conventions strictly

### Acknowledged trade-offs
- Some legacy users may resist NetCDF familiarity over `.IFG`
- Migration tools (`import_phabsim`) are best-effort and may lose metadata

## Implementation notes

JSON-Schema files live in `src/openlimno/wedm/schemas/`. Validation runs in `pixi run validate-schemas` on every PR.

## References

- UGRID-1.0: https://ugrid-conventions.github.io/ugrid-conventions/
- CF Conventions: https://cfconventions.org/
- Apache Parquet: https://parquet.apache.org/
- SPEC v0.5 §1 P3, §3.1
