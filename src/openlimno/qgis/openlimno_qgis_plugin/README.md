# OpenLimno QGIS Plugin (M2 alpha)

> SPEC §8.3.1, ADR-0005. Read-only viewer for OpenLimno hydraulic + habitat outputs.

## What it does

- Opens OpenLimno `hydraulics.nc` (UGRID NetCDF) as a QGIS mesh / raster layer
- Opens `wua_q.csv` / `wua_q.parquet` and shows a table dialog
- (Future M3) trigger a local `openlimno run` via subprocess

## What it does NOT do (deliberately)

- Run hydraulics or habitat (use the `openlimno` CLI)
- Edit data
- Depend on the OpenLimno Python package inside QGIS Python (avoids
  GDAL / Python / DLL conflicts; see ADR-0005 Layer 1 strategy)

## Install

### Via QGIS Plugin Repository (M3)

`Plugins → Manage and Install Plugins → All → search "OpenLimno"`. Install,
restart QGIS. **Pending plugin repo submission post-M2.**

### Manual (M2 alpha)

```bash
# Find your QGIS plugin path (varies by OS):
#   Linux:   ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
#   macOS:   ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
#   Windows: %APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/

# Copy this directory:
cp -r src/openlimno/qgis/openlimno_qgis_plugin/ \
      "<QGIS_PLUGIN_DIR>/openlimno"

# Restart QGIS, enable in Plugins → Manage.
```

## Manual test plan

Until QGIS is wired into CI (M3), maintainers run these checks against a
Lemhi build (`python tools/build_lemhi_dataset.py` + `pixi run openlimno run
examples/lemhi/case.yaml`):

- [ ] `Open OpenLimno hydraulic results…` action appears in QGIS menu
- [ ] Selecting `examples/lemhi/out/lemhi_2024/hydraulics.nc` loads as mesh
       layer; render shows reasonable extent
- [ ] `water_depth` / `velocity_magnitude` variables visible in layer properties
- [ ] `Open WUA-Q curve…` action loads `wua_q.csv` into a dialog with 12 rows
       and the expected `wua_m2_<species>_<stage>` columns
- [ ] Plugin loads cleanly on QGIS LTS 3.34 (Linux, macOS, Windows)
- [ ] No errors in QGIS Python console at plugin load time

## Compatibility

Per ADR-0005:
- QGIS LTS 3.34, 3.40
- Apple Silicon + Intel macOS, Linux, Windows

## License

Apache-2.0, same as OpenLimno proper.
