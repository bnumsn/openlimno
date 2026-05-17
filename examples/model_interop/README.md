# OpenLimno model-interoperability quickstart

This example directory is intentionally data-light. Real hydraulic model files
are usually large or licence-sensitive, so the recipes point at your model
exports and at the public fixture tests OpenLimno can download on demand.

## Public TELEMAC End-To-End Demo

Run a real public TELEMAC Selafin file all the way through OpenLimno habitat
evaluation:

```bash
pixi run python examples/model_interop/telemac_public_wua.py \
  --cache-dir /tmp/openlimno_telemac_fixtures \
  --out-dir /tmp/openlimno_telemac_public_wua
```

Outputs:

- `hydraulic_cells.parquet` — imported TELEMAC hydraulic cells across all time steps.
- `demo_hsi_curve.parquet` — synthetic HSI curves used only for the workflow demo.
- `habitat_cells.parquet` — SI/CSI/WUA per hydraulic cell.
- `wua_summary.csv` — WUA by time step.
- `wua_hmu.csv` — WUA by HMU type and time step.
- `wua_timeseries.png` — quick visual check.
- `REPORT.md` — source, checksum, HSI warning, and WUA summary.

## Public Delft3D NetCDF End-To-End Demo

Run a public Delft3D NetCDF file from MHKiT through the same OpenLimno habitat
evaluation path:

```bash
pixi run python examples/model_interop/delft3d_public_wua.py \
  --cache-dir /tmp/openlimno_netcdf_fixtures \
  --out-dir /tmp/openlimno_delft3d_public_wua
```

Outputs use the same file names as the TELEMAC demo, with `wua_summary.csv`
grouped by NetCDF time index.

## Public River2D Fixture

The official River2D habitat tutorial is covered by an opt-in fixture test. It
downloads `R2D_Habitat.zip`, imports the solved `fortnewfinal.CDG` node fields
and element topology, validates UGRID export, and normalizes the tutorial WUA
CSV:

```bash
OPENLIMNO_RUN_RIVER2D_REAL=1 \
pixi run pytest tests/integration/test_river2d_real_fixtures.py -q
```

## 1. Inspect What OpenLimno Can Read

```bash
pixi run openlimno preprocess import-model --list-supported
```

Use `inspect-model` before importing binary or model-result files:

```bash
pixi run openlimno preprocess inspect-model \
  --source hecras-hdf \
  --in path/to/ras_project.p01.hdf

pixi run openlimno preprocess inspect-model \
  --source telemac-slf \
  --in path/to/telemac_results.slf

pixi run openlimno preprocess inspect-model \
  --source delft3d-netcdf \
  --in path/to/dflowfm_map.nc
```

## 2. Import Hydraulic Cells

All implemented 2D hydraulic adapters stage to the same `hydraulic_cells` shape
where possible:

```bash
pixi run openlimno preprocess import-model \
  --source hecras-hdf \
  --in path/to/ras_project.p01.hdf \
  --out data/hecras_hydraulic_cells.parquet \
  --time-index -1

pixi run openlimno preprocess import-model \
  --source telemac-slf \
  --in path/to/telemac_results.slf \
  --out data/telemac_hydraulic_cells.parquet \
  --time-index -1

pixi run openlimno preprocess import-model \
  --source delft3d-netcdf \
  --in path/to/dflowfm_map.nc \
  --out data/netcdf_hydraulic_cells.parquet \
  --time-index -1
```

## 3. Run WUA On Imported Cells

```bash
pixi run openlimno wua-cells \
  --cells data/hecras_hydraulic_cells.parquet \
  --hsi path/to/hsi_curve.parquet \
  --species oncorhynchus_mykiss \
  --stage spawning \
  --out-dir out/hecras_habitat
```

The same command works for `telemac_hydraulic_cells.parquet`,
`netcdf_hydraulic_cells.parquet`, and MIKE DFSU/DFS2 hydraulic-cell outputs.

## 4. MIKE 21/FM/1D

Use the project-managed environment so Linux `.NET Runtime` is available for
MIKE 1D/XNS11:

```bash
pixi install -e mike
pixi run -e mike openlimno preprocess diagnose-model --source mike-1d

pixi run -e mike openlimno preprocess import-model \
  --source mike-dfs \
  --in path/to/mike21_results.dfsu \
  --out data/mike_hydraulic_cells.parquet \
  --time-index -1

pixi run -e mike openlimno preprocess import-model \
  --source mike-1d \
  --in path/to/river_network.xns11 \
  --out data/mike_cross_sections.parquet

pixi run -e mike openlimno preprocess import-model \
  --source mike-1d \
  --in path/to/network_river.res1d \
  --out data/mike_timeseries.parquet
```

Validate against DHI public fixtures:

```bash
OPENLIMNO_RUN_MIKE_REAL=1 \
pixi run -e mike pytest tests/integration/test_mike_real_fixtures.py -q
```

## 5. HABBY / CASiMiR / MesoHABSIM Tables

```bash
pixi run openlimno preprocess inspect-model \
  --source habby-csv \
  --in path/to/habby_or_casimir_wua.csv

pixi run openlimno preprocess import-model \
  --source habby-csv \
  --in path/to/habby_or_casimir_wua.csv \
  --out data/habitat_exchange.parquet
```

CSV, TSV, TXT, and Parquet are accepted. HABBY-style `*_spu.txt` and
`*_detailled_mesh.txt` exports are normalized through the same adapter.

## 6. inSTREAM / InSALMO / NetLogo

Export OpenLimno habitat cells for an IBM workflow:

```bash
pixi run openlimno ibm-export \
  --target instream-netlogo \
  --cells out/hecras_habitat/habitat_cells.csv \
  --scenario-id baseline \
  --reach-id reach-1 \
  --out-dir out/instream_exchange
```

Import IBM population summaries or inSTREAM 7 hydraulic matrices:

```bash
pixi run openlimno preprocess import-model \
  --source instream-netlogo \
  --in path/to/instream_population_summary.csv \
  --out data/instream_population_summary.parquet
```

## 7. Public Fixture Checks

```bash
OPENLIMNO_RUN_TELEMAC_REAL=1 \
pixi run pytest tests/integration/test_telemac_real_fixtures.py -q

OPENLIMNO_RUN_TELEMAC_REAL=1 \
pixi run pytest tests/integration/test_telemac_public_wua_example.py -q

OPENLIMNO_RUN_NETCDF_REAL=1 \
pixi run pytest tests/integration/test_netcdf_real_fixtures.py \
  tests/integration/test_netcdf_public_wua_example.py -q

OPENLIMNO_RUN_INSTREAM_REAL=1 \
pixi run pytest tests/integration/test_instream_real_fixtures.py -q
```

HABBY/CASiMiR exported WUA tables do not yet have a small pinned public fixture.
Use the local/URL hook when validating project-specific exports:

```bash
OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL=1 \
OPENLIMNO_HABITAT_EXCHANGE_FIXTURE=/path/to/exported_wua_table.txt \
pixi run pytest tests/integration/test_habitat_exchange_real_fixtures.py -q
```
