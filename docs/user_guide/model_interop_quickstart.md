# Model Interop Quickstart

OpenLimno is designed to sit after the hydraulic or habitat model you already
trust. The common pattern is:

1. Inspect the external model output.
2. Import it to a staging table.
3. Run `wua-cells` or exchange tables through the ecological workflow.

## Public TELEMAC End-To-End Demo

The repository includes a runnable public fixture demo that downloads a TELEMAC
Selafin file, imports all time steps, evaluates a demonstration HSI curve, and
writes WUA tables, a plot, and a Markdown report:

```bash
pixi run python examples/model_interop/telemac_public_wua.py \
  --cache-dir /tmp/openlimno_telemac_fixtures \
  --out-dir /tmp/openlimno_telemac_public_wua
```

The bundled HSI curves are synthetic workflow fixtures. Replace them before
using the outputs for ecological or regulatory decisions.

## Public Delft3D NetCDF End-To-End Demo

The same pattern is available for a public Delft3D NetCDF fixture from MHKiT:

```bash
pixi run python examples/model_interop/delft3d_public_wua.py \
  --cache-dir /tmp/openlimno_netcdf_fixtures \
  --out-dir /tmp/openlimno_delft3d_public_wua
```

It downloads the pinned `turbineTest_map.nc` file, imports all time steps, runs
synthetic demonstration HSI curves, and writes WUA tables, a plot, and a report.
Replace the bundled curves before ecological or regulatory use.

## List Supported Paths

```bash
openlimno preprocess import-model --list-supported
```

## HEC-RAS, TELEMAC, Delft3D / CF-UGRID

```bash
openlimno preprocess inspect-model --source hecras-hdf --in ras_project.p01.hdf
openlimno preprocess import-model --source hecras-hdf --in ras_project.p01.hdf \
  --out data/hecras_hydraulic_cells.parquet --time-index -1

openlimno preprocess inspect-model --source telemac-slf --in telemac_results.slf
openlimno preprocess import-model --source telemac-slf --in telemac_results.slf \
  --out data/telemac_hydraulic_cells.parquet --time-index -1

openlimno preprocess inspect-model --source delft3d-netcdf --in dflowfm_map.nc
openlimno preprocess import-model --source delft3d-netcdf --in dflowfm_map.nc \
  --out data/netcdf_hydraulic_cells.parquet --time-index -1
```

Validate the NetCDF path against the public MHKiT Delft3D turbine-flume fixture:

```bash
OPENLIMNO_RUN_NETCDF_REAL=1 \
pixi run pytest tests/integration/test_netcdf_real_fixtures.py \
  tests/integration/test_netcdf_public_wua_example.py -q
```

Validate the HEC-RAS path against a public FEMA `rashdf` HEC-RAS HDF fixture:

```bash
OPENLIMNO_RUN_HECRAS_REAL=1 \
pixi run pytest tests/integration/test_hecras_real_fixtures.py -q
```

## River2D

```bash
openlimno preprocess inspect-model --source river2d-cdg --in site.cdg
openlimno preprocess import-model --source river2d-cdg \
  --in site.cdg --out data/river2d_mesh_nodes.parquet
openlimno preprocess river2d-ugrid \
  --in site.cdg --out data/river2d_mesh.nc
```

River2D 2002-style `.CDG` files can carry solved node variables. OpenLimno
normalizes bed elevation, depth, unit discharge, derived velocity, and node
coordinates into `mesh_nodes`; triangular topology is available from the Python
API:

```python
from openlimno.preprocess import read_river2d_elements, write_river2d_ugrid

elements = read_river2d_elements("site.cdg")
write_river2d_ugrid("site.cdg", "site_ugrid.nc")
```

Official River2D habitat tutorial files are covered by an opt-in real fixture:

```bash
OPENLIMNO_RUN_RIVER2D_REAL=1 \
pixi run pytest tests/integration/test_river2d_real_fixtures.py -q
```

Run habitat on any imported hydraulic-cell table:

```bash
openlimno wua-cells \
  --cells data/hecras_hydraulic_cells.parquet \
  --hsi data/hsi_curve.parquet \
  --species oncorhynchus_mykiss \
  --stage spawning \
  --out-dir out/hecras_habitat
```

## MIKE 21 / MIKE FM / MIKE 1D

For repository development, use the Pixi `mike` environment so the Linux
`.NET Runtime` required by `mikeio1d` is present:

```bash
pixi install -e mike
pixi run -e mike openlimno preprocess diagnose-model --source mike-1d

pixi run -e mike openlimno preprocess import-model --source mike-dfs \
  --in mike21_results.dfsu --out data/mike_hydraulic_cells.parquet --time-index -1

pixi run -e mike openlimno preprocess import-model --source mike-1d \
  --in river_network.xns11 --out data/mike_cross_sections.parquet

pixi run -e mike openlimno preprocess import-model --source mike-1d \
  --in network_river.res1d --out data/mike_timeseries.parquet
```

Validate against DHI public fixtures:

```bash
OPENLIMNO_RUN_MIKE_REAL=1 \
pixi run -e mike pytest tests/integration/test_mike_real_fixtures.py -q
```

## HABBY / CASiMiR / MesoHABSIM

```bash
openlimno preprocess inspect-model --source habby-csv --in habby_wua_cells.csv
openlimno preprocess import-model --source habby-csv --in habby_wua_cells.csv \
  --out data/habitat_exchange.parquet
```

The importer accepts CSV, TSV, TXT, and Parquet tables. HABBY-style `*_spu.txt`
and `*_detailled_mesh.txt` exports are normalized through the same adapter.

## inSTREAM / InSALMO / NetLogo

```bash
openlimno ibm-export --target instream-netlogo \
  --cells out/hecras_habitat/habitat_cells.csv \
  --scenario-id baseline --reach-id reach-1 \
  --out-dir out/instream_exchange

openlimno preprocess import-model --source instream-netlogo \
  --in instream_population_summary.csv \
  --out data/instream_population_summary.parquet
```

OpenLimno also reads inSTREAM 7 hydraulic matrix inputs such as `*-Depths.csv`
and `*-Vels.csv` into long `ibm_hydraulic_lookup` tables.

OpenLimno can also run a native, non-NetLogo inSTREAM-like IBM directly from
habitat cells. This path is intended for reproducible research and calibration;
it is not yet a numerically calibrated replacement for regulatory inSTREAM
population runs:

```bash
openlimno ibm-run-native \
  --cells out/hecras_habitat/habitat_cells.csv \
  --species rainbow_trout \
  --initial-abundance 100 \
  --days 365 \
  --individual-history \
  --out-dir out/native_ibm
```

The native engine writes population summary, final individual state, cell-use,
event, and redd-status tables; `--individual-history` also writes a per-fish
daily state table for calibration and audit runs. It is designed for
reproducible OpenLimno workflows and does not edit or execute `.nlogo` files.
When the habitat-cell table contains `time_index`, the runner advances through
those slices as daily hydraulic/habitat forcing.

For an inSTREAM/NetLogo-style local browser interface around the same native
engine, launch IBM Studio:

```bash
openlimno ibm-studio --port 8770 --out-dir out/ibm_studio
```

IBM Studio provides scenario setup, species-profile controls, habitat-cell
editing, an inSTREAM-style river view with habitat cells, fish symbols, flow
direction, live/dead fish toggles, run/step/reset controls, population charts,
fish/redd/event tables, CSV output links, and optional inSTREAM 7
benchmark/BriefPop comparison panels.

To run the native engine against the official inSTREAM 7.4 example package:

```bash
openlimno ibm-benchmark-instream7 \
  --fixture InSTREAM-7.4_2026-02-11.zip \
  --days 7 \
  --out-dir out/instream7_benchmark
```

This writes an official input inventory plus native prototype population,
cell-use, final individual, event, and redd-status tables for Example A and
Example B. Example B uses the official reach order for bounded adjacent-reach
migration; treat it as a calibration benchmark, not a final numerical
equivalence claim.

To generate a version-local NetLogo reference run from the same official package,
point OpenLimno at a NetLogo 7 `NetLogo_Console` executable. The command copies
the official case, patches a short end date, forces daily BriefPop output, and
runs BehaviorSpace headlessly:

```bash
openlimno ibm-run-instream7-netlogo-reference \
  --fixture InSTREAM-7.4_2026-02-11.zip \
  --case-id ExampleA \
  --days 2 \
  --seed 11 \
  --netlogo-console "/path/to/NetLogo 7.0.2/NetLogo_Console" \
  --out-dir out/instream7_netlogo_reference
```

The generated `BriefPopOut-*.csv` can be summarized and compared with the native
benchmark output.

If you generate a NetLogo `BriefPopOut-*.csv` file from the official inSTREAM
7 model, summarize it to the same reach/species population level before
comparing it with the native benchmark:

```bash
openlimno ibm-summarize-instream7-brief \
  --brief-pop BriefPopOut-r1.csv \
  --out out/instream7_netlogo_brief_summary.csv
```


Then generate a row-level tolerance report against the native benchmark output:

```bash
openlimno ibm-compare-instream7-netlogo \
  --native-summary out/instream7_benchmark/instream7_native_population_summary.csv \
  --brief-pop BriefPopOut-r1.csv \
  --out out/native_vs_netlogo_comparison.csv \
  --abundance-tolerance 0 \
  --biomass-rel-tolerance 0.05 \
  --mean-length-tolerance-mm 1.0
```

The comparison aligns each NetLogo BehaviorSpace run by ordered BriefPop
snapshot within reach/species and reports abundance, biomass, and mean-length
deltas plus pass/fail flags for each tolerance.
