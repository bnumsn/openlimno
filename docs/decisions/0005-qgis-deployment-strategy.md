# ADR-0005: QGIS plugin: subprocess CLI, not in-process import

- **Status**: Accepted
- **Date**: 2026-05-07
- **SPEC sections**: §8.3
- **Tags**: gui, qgis, deployment

## Context

QGIS bundles its own Python interpreter and locks GDAL / Qt to specific versions. Installing OpenLimno's deps via `pip install` inside QGIS frequently fails with DLL / GDAL-version conflicts on Windows and macOS.

Gemini round 2 review: "QGIS plugin 部署摩擦…会让'1.0 易安装'目标破产。"

## Decision

Three-layer strategy:

1. **Read-only viewer**: uses only QGIS's bundled GDAL and Qt to open NetCDF/Parquet outputs. No OpenLimno Python package needed inside QGIS. (M2 alpha.)
2. **Calculation invocation**: QGIS plugin shells out to an external `openlimno` CLI (installed via pixi/conda). Plugin and CLI never share a Python process. (M3.)
3. **Result return**: CLI writes NetCDF/Parquet to disk; plugin reopens via path. (M3.)

Distribution: QGIS Plugin Repository (primary) + OSGeo4W / conda-forge sidecar (secondary). No git-based dev install.

Compatibility: pin to QGIS LTS versions (3.34 LTS / 3.40 LTS). CI matrix: QGIS LTS × OS.

## Alternatives considered

### A: In-process import (`pip install openlimno` in QGIS Python)
Rejected: dependency hell as documented above.

### B: Headless-only, no QGIS plugin
Rejected: SPEC §11.1 cites QGIS plugin as the ecologist user entry point — not optional.

### C: Tauri / Electron desktop GUI
Moved to §13 research roadmap. QGIS chosen because ecologists already use it.

## Consequences

### Positive
- QGIS plugin can release independently of OpenLimno core
- Avoids GDAL version war
- Subprocess boundary is a natural failure surface (CLI errors are not GUI crashes)

### Negative
- Latency for interactive workflows (acceptable; runs are minutes)
- Two install steps (pixi for CLI, QGIS plugin repo for plugin)

## References

- SPEC v0.5 §8.3
- QGIS API stability policy: https://api.qgis.org/api/api_break.html
