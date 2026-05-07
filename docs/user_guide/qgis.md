# QGIS plugin (M2 alpha)

Read-only viewer for OpenLimno results. Per [ADR-0005](../decisions/0005-qgis-deployment-strategy.md), the plugin uses **only QGIS-bundled GDAL/Qt** and does not depend on the OpenLimno Python package inside QGIS Python (avoiding GDAL / Qt / DLL conflicts).

## What it does

- Open `hydraulics.nc` (UGRID NetCDF) as a QGIS mesh / raster layer
- Open `wua_q.csv` / `wua_q.parquet` and display in a table dialog
- Opens regulatory CSVs (cn_sl712, us_ferc_4e, eu_wfd) tolerating their `#`-prefixed comment header

## What it does NOT do (deliberately)

- Run hydraulics or habitat (use the `openlimno` CLI; M3 will add subprocess invocation from the plugin)
- Edit data
- Depend on the OpenLimno Python package inside QGIS Python

## Install (manual, M2 alpha)

```bash
# Find your QGIS plugin path:
#   Linux:   ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
#   macOS:   ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
#   Windows: %APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/

cp -r src/openlimno/qgis/openlimno_qgis_plugin "<QGIS_PLUGIN_DIR>/openlimno"
```

Restart QGIS and enable from `Plugins → Manage and Install Plugins`. Two new actions appear in the menu:

- *Open OpenLimno hydraulic results…* — file picker for `.nc`, loads as mesh layer
- *Open WUA-Q curve…* — file picker for `.csv` / `.parquet`, shows table

## Compatibility

| Platform | QGIS LTS | Status |
|---|---|---|
| Linux x86_64 | 3.34, 3.40 | M2 alpha tested |
| macOS Intel + Apple Silicon | 3.34, 3.40 | M2 alpha untested |
| Windows | 3.34, 3.40 | M2 alpha untested |

Real testing on QGIS LTS environments lands on the M0 maintainers (manual test plan in `src/openlimno/qgis/openlimno_qgis_plugin/README.md`).

## Roadmap

| Milestone | Capability |
|---|---|
| M2 alpha (current) | read-only viewer |
| M3 | subprocess CLI invocation from plugin (run a case from QGIS) |
| M4 GA | publication-grade map rendering (legend, scalebar, north arrow), CN/EN translations |
| §13 | full processing provider, expression functions for HSI |

## Distribution

| Channel | Status |
|---|---|
| Official QGIS Plugin Repository | Pending submission post-M2 |
| OSGeo4W / conda-forge sidecar | Pending |
| Manual git clone | Available now |
