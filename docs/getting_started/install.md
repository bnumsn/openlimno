# Install

OpenLimno targets desktop platforms first (SPEC §5). HPC and cloud paths are deferred to §13 research roadmap.

## Recommended: pixi (cross-platform)

```bash
git clone https://github.com/openlimno/openlimno.git
cd openlimno
pixi install
pixi run pytest          # 160+ tests should pass
```

Pixi pulls dependencies from conda-forge: NumPy, pandas, xarray, NetCDF-4, PyArrow, GDAL, GMSH, scipy, snakemake, etc.

## Conda / mamba

```bash
mamba create -n openlimno python=3.12
mamba activate openlimno
mamba install -c conda-forge \
    numpy pandas xarray netcdf4 pyarrow pyproj shapely geopandas rasterio \
    matplotlib pyyaml jsonschema click rich gmsh triangle scipy \
    snakemake-minimal pestpp
pip install -e .
```

## Pip (no conda)

GDAL/rasterio binary wheels can be brittle on Windows. Pixi is strongly recommended for first-time users.

```bash
pip install -e .
```

## Verifying the install

```bash
openlimno --version
openlimno validate examples/lemhi/case.yaml
python tools/build_lemhi_dataset.py     # builds the sample data package
openlimno run examples/lemhi/case.yaml
```

## SCHISM (M3 backend)

OpenLimno does NOT bundle SCHISM. To use the SCHISM 2D backend (ADR-0002):

### Container path (recommended)

```bash
docker pull ghcr.io/openlimno/schism:5.11.0     # M3 deliverable
```

Then in your case YAML:
```yaml
hydrodynamics:
  backend: schism
  schism:
    container_image: ghcr.io/openlimno/schism:5.11.0
    container_runtime: docker
    n_procs: 4
```

### Source build (HPC)

See [SCHISM upstream docs](https://schism-dev.github.io/schism/master/getting-started/installation.html). Tested with v5.11.0.

```bash
export OPENLIMNO_SCHISM=/path/to/pschism_TVD-VL
```

## QGIS plugin (M2 alpha)

Manual install while waiting for QGIS Plugin Repository submission:

```bash
# Locate your QGIS plugin directory (varies by OS):
#   Linux:   ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
#   macOS:   ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
#   Windows: %APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/

cp -r src/openlimno/qgis/openlimno_qgis_plugin "<QGIS_PLUGIN_DIR>/openlimno"
```

Restart QGIS, enable from `Plugins → Manage and Install Plugins`.
