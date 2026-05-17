# Preprocess

`openlimno.preprocess` ingests real-world data into WEDM. M1 supports the **first-mile core three** (SPEC §4.0.1):

| Source | Reader | CLI |
|---|---|---|
| Cross-sections (CSV / Excel) | `read_cross_sections` | `openlimno preprocess xs` |
| USGS QRev CSV ADCP | `read_adcp_qrev` | `openlimno preprocess adcp` |
| DEM GeoTIFF | `read_dem` | `openlimno preprocess dem-info` |
| External model files | `read_external_model` | `openlimno preprocess import-model` |

## Cross-section CSV / Excel

Required columns (case-insensitive): `station_m`, `distance_m`, `elevation_m`. Optional: `point_index`, `substrate`, `cover`, `depth_m`.

```bash
openlimno preprocess xs \
    --in surveys/lemhi_2024_xs.csv \
    --out data/lemhi/cross_section.parquet \
    --campaign-id lemhi-2024-08
```

API:

```python
from openlimno.preprocess import read_cross_sections, write_cross_sections_to_parquet

df = read_cross_sections("xs.csv", campaign_id="lemhi-2024-08")
write_cross_sections_to_parquet(df, "data/lemhi/cross_section.parquet",
                                 source_note="IDFG 2024 survey")
```

## USGS QRev ADCP

QRev exports vary by version; OpenLimno tolerates the common column-name aliases (`time` / `datetime`, `depth` / `depth_m`, `v_east` / `u_ms`, etc.).

```bash
openlimno preprocess adcp \
    --in QRev_2024-04-15_lemhi.csv \
    --out data/lemhi/adcp_2024-04-15.parquet
```

## DEM GeoTIFF

```bash
openlimno preprocess dem-info elevation/lemhi_lidar_1m.tif
```

API for sampling along a line (e.g. extract bed elevations for a cross-section):

```python
from openlimno.preprocess import read_dem

dem = read_dem("elevation/lemhi_lidar_1m.tif")
print(f"DEM {dem.shape}, CRS {dem.crs}")
elev = dem.sample_along_line(x0=584000, y0=4980000,
                              x1=584050, y1=4980030, n=21)
```

## Best-effort legacy formats (M3+)

The interoperability entry point is intentionally broader than legacy
cross-section migration. It is where OpenLimno exposes the "use your existing
hydraulic or habitat model, then run OpenLimno ecology/reporting" workflow.

```bash
openlimno preprocess import-model --list-supported

openlimno preprocess import-model \
    --source auto \
    --in legacy/river.g03 \
    --out data/imported_hecras_geometry.parquet

openlimno preprocess inspect-model \
    --source hecras-hdf \
    --in ras_project.p01.hdf
```

Current core registry:

| Source key | Model family | Status | Notes |
|---|---|---|---|
| `hecras-geometry` | HEC-RAS `.g0X` | Implemented | Best-effort X1/GR cross-section geometry |
| `river2d-cdg` | River2D `.cdg/.bed` | Implemented | Mesh nodes plus River2D 2002 solved node fields; element topology via Python API |
| `hecras-hdf` | HEC-RAS `.hdf/.h5` | Implemented MVP | Cell-aligned depth, velocity, water surface, cell centers |
| `telemac-slf` | TELEMAC Selafin / Seraphin `.slf/.selafin` | Implemented MVP | Native 2D node-result reader; averages variables onto element/cell rows |
| `delft3d-netcdf` | Delft3D FM / D-Flow FM / CF-UGRID NetCDF | Implemented | Cell-centred depth, velocity/UV, water surface, coordinates, cell area |
| `mike-dfs` | MIKE dfs0/dfs1/dfs2/dfs3/dfsu/mesh | Implemented optional | Requires `mikeio`; DFSU/DFS2 become hydraulic cells, DFS0/DFS1 become time-series tables |
| `mike-1d` | MIKE 1D / MIKE 11 / MIKE+ res1d/xns11 | Implemented optional | Requires `mikeio1d`; RES1D becomes time-series tables, XNS11 becomes cross-section points |
| `habby-csv` | HABBY / CASiMiR / habitat tools CSV/TSV/TXT/Parquet | Implemented | Cell CSI/WUA and reach WUA summary exchange |
| `instream-netlogo` | inSTREAM / InSALMO / NetLogo CSV/TSV/Parquet | Implemented | Habitat-cell export and population-summary import bridge |

These are best-effort migrators (per ADR-0003 reasoning); they are not part of the 1.0 contract because the upstream binary formats are not openly specified. MIKE support is intentionally optional so non-MIKE users do not need DHI dependencies:

```bash
pip install "openlimno[mike]"

openlimno preprocess diagnose-model --source mike-dfs
openlimno preprocess diagnose-model --source mike-1d
```

For repository development, use the bundled Pixi environment instead:

```bash
pixi install -e mike
pixi run -e mike openlimno preprocess diagnose-model --source mike-1d
```

On Linux, `mikeio1d` also needs an OS-level .NET Runtime. If
`diagnose-model --source mike-1d` reports `dotnet_ok = no`, install .NET
Runtime 8.0 through your platform package manager (for Ubuntu:
`sudo apt install dotnet-runtime-8.0`) before opening real `.res1d` or
`.xns11` files. The Pixi `mike` environment installs conda-forge
`dotnet-runtime` for this case and is intentionally limited to Linux/Windows,
matching the wheels currently published by DHI for `mikeio1d`.

For HEC-RAS HDF results, import one time step into a hydraulic-cell staging
table. Start with inspection when you do not know the exact 2D flow-area name or
whether your chosen output variables are cell-aligned:

```bash
openlimno preprocess inspect-model \
    --source hecras-hdf \
    --in ras_project.p01.hdf \
    --flow-area "2D Area 1"

openlimno preprocess import-model \
    --source hecras-hdf \
    --in ras_project.p01.hdf \
    --out data/hecras_hydraulic_cells.parquet \
    --flow-area "2D Area 1" \
    --time-index -1

openlimno wua-cells \
    --cells data/hecras_hydraulic_cells.parquet \
    --hsi data/lemhi/hsi_curve.parquet \
    --species oncorhynchus_mykiss \
    --stage spawning \
    --out-dir out/hecras_habitat
```

For Delft3D FM / D-Flow FM, converted TELEMAC, or other CF/UGRID NetCDF
hydraulic results:

```bash
openlimno preprocess inspect-model \
    --source delft3d-netcdf \
    --in dflowfm_map.nc

openlimno preprocess import-model \
    --source delft3d-netcdf \
    --in dflowfm_map.nc \
    --out data/netcdf_hydraulic_cells.parquet \
    --time-index -1
```

The importer detects common variables such as `mesh2d_waterdepth`,
`mesh2d_s1`, `mesh2d_ucmag`, `mesh2d_ucx/mesh2d_ucy`,
`mesh2d_face_x/mesh2d_face_y`, and `mesh2d_flowelem_ba`. Use
`inspect-model` first when a model export uses different names.

For River2D `.CDG` files:

```bash
openlimno preprocess inspect-model \
    --source river2d-cdg \
    --in fortnewfinal.CDG

openlimno preprocess import-model \
    --source river2d-cdg \
    --in fortnewfinal.CDG \
    --out data/river2d_mesh_nodes.parquet

openlimno preprocess river2d-ugrid \
    --in fortnewfinal.CDG \
    --out data/river2d_mesh.nc
```

The importer handles the compact `NODES`/`ELEMENTS` layout used by simple
exports and the official River2D 2002 tutorial layout with `Node Information`
and `Element Information` sections. For solved River2D `.CDG` files, node rows
include bed elevation, roughness, depth, unit discharge, and derived velocity
when those variables are present. Use `read_river2d_elements()` from Python to
extract triangular element topology, or `write_river2d_ugrid()` to convert the
mesh to a minimal UGRID NetCDF file.

For native TELEMAC Selafin / Seraphin files:

```bash
openlimno preprocess inspect-model \
    --source telemac-slf \
    --in telemac_results.slf

openlimno preprocess import-model \
    --source telemac-slf \
    --in telemac_results.slf \
    --out data/telemac_hydraulic_cells.parquet \
    --time-index -1
```

The Selafin importer reads 2D mesh connectivity, node coordinates, time steps,
and common hydraulic variables such as `WATER DEPTH`, `FREE SURFACE`,
`VELOCITY`, `VELOCITY U`, and `VELOCITY V`. Node values are averaged onto
element/cell rows so the output can use the same `wua-cells` pathway as HEC-RAS,
MIKE, and CF/UGRID NetCDF imports.

For MIKE 21 / MIKE FM outputs, inspect the file first, then import one time
step into the same `hydraulic_cells` staging table used by HEC-RAS:

```bash
openlimno preprocess inspect-model \
    --source mike-dfs \
    --in mike21_results.dfsu

openlimno preprocess import-model \
    --source mike-dfs \
    --in mike21_results.dfsu \
    --out data/mike_hydraulic_cells.parquet \
    --time-index -1
```

For MIKE 1D / MIKE 11 cross-sections:

```bash
openlimno preprocess import-model \
    --source mike-1d \
    --in river_network.xns11 \
    --out data/mike_cross_sections.parquet
```

For HABBY, CASiMiR, MesoHABSIM, or other habitat tools that already produced
cell suitability or WUA tables:

```bash
openlimno preprocess inspect-model \
    --source habby-csv \
    --in habby_wua_cells.csv

openlimno preprocess import-model \
    --source habby-csv \
    --in habby_wua_cells.csv \
    --out data/habitat_cells.parquet
```

The exchange importer recognizes common aliases for `cell_id`, `x`, `y`,
`area_m2`, `csi`/`hsi`/`si`, `wua_m2`, `depth_m`, `velocity_ms`,
`discharge_m3s`, `species`, and `life_stage`. If only `area_m2` and
`csi`/`hsi` are present, OpenLimno computes `wua_m2 = area_m2 * csi`.
If a summary table includes `wua_m2` plus total or wetted area, OpenLimno also
computes `mean_csi`.

HABBY's official TELEMAC tutorial exports habitat chronicles as
`*_spu.txt` and detailed mesh tables as `*_detailled_mesh.txt`; OpenLimno
accepts `.txt` alongside `.csv`, `.tsv`, `.tab`, and `.parquet`, including
`SPU` as a WUA alias and HABBY-style `*_HV_Dominant` fields as habitat
suitability values. The public tutorial archive itself only ships hydraulic and
substrate inputs, so the real exported-table test uses the local/URL fixture
hook until a small official WUA export is published.

For inSTREAM / InSALMO / NetLogo population workflows, OpenLimno provides a CSV
exchange bridge instead of a native IBM runtime. Export evaluated habitat cells
from OpenLimno:

```bash
openlimno ibm-export \
    --target instream-netlogo \
    --cells out/hecras_habitat/habitat_cells.csv \
    --scenario-id baseline \
    --reach-id reach-1 \
    --out-dir out/instream_exchange
```

This writes:

- `instream_habitat_cells.csv` — cell-level depth, velocity, area, CSI/WUA,
  cover/substrate fields when present, and scenario/reach IDs.
- `instream_flow_summary.csv` — reach/flow/time summaries useful for checking
  the exchange before using it in a NetLogo model.
- `instream_exchange_manifest.csv` — row counts and table descriptions.

After an IBM run, bring population summaries back into OpenLimno:

```bash
openlimno preprocess inspect-model \
    --source instream-netlogo \
    --in instream_population_summary.csv

openlimno preprocess import-model \
    --source instream-netlogo \
    --in instream_population_summary.csv \
    --out data/instream_population_summary.parquet
```

The importer recognizes common population aliases such as `scenario`,
`reach`, `species`, `stage`, `age_class`, `year`, `day`, `abundance`,
`biomass_g`, `mean_length_mm`, `survival_rate`, `recruits`, and `spawners`.
It also recognizes inSTREAM 7 hydraulic matrix inputs such as `*-Depths.csv`
and `*-Vels.csv`, expanding the flow columns into a long
`ibm_hydraulic_lookup` table with `cell_id`, `discharge_m3s`, and either
`depth_m` or `velocity_ms`.
It does not edit `.nlogo` model files; users should map the CSV package into
their inSTREAM/InSALMO project deliberately.

To validate the adapter against DHI's public sample files, install the optional
MIKE readers and opt into the networked integration test:

```bash
pip install "openlimno[mike]"

OPENLIMNO_RUN_MIKE_REAL=1 \
pytest tests/integration/test_mike_real_fixtures.py

OPENLIMNO_RUN_MIKE_REAL=1 \
pixi run -e mike pytest tests/integration/test_mike_real_fixtures.py
```

The test downloads DHI's `HD2D.dfsu`, `mikep_cs_demo.xns11`, and
`network_river.res1d` samples from the official `DHI/mikeio` and
`DHI/mikeio1d` GitHub repositories and verifies their SHA-256 hashes before
importing them. Set `OPENLIMNO_MIKE_FIXTURE_DIR` to reuse a local fixture cache.
On Linux, the MIKE 1D fixtures require .NET Runtime 8.0; without it, the MIKE 1D
part reports an explicit skip while DFSU still runs. In the Pixi `mike`
environment, the DHI DFSU, XNS11, and RES1D public fixtures are expected to
pass.

To validate the TELEMAC Selafin adapter against a public tutorial result file:

```bash
OPENLIMNO_RUN_RIVER2D_REAL=1 \
pytest tests/integration/test_river2d_real_fixtures.py

OPENLIMNO_RUN_TELEMAC_REAL=1 \
pytest tests/integration/test_telemac_real_fixtures.py
```

The River2D test downloads the official public `R2D_Habitat.zip` tutorial from
the University of Alberta River2D site, verifies its SHA-256 hash, imports the
solved `fortnewfinal.CDG` node fields and element topology, and normalizes the
exported WUA CSV table through the habitat-exchange path.

The test downloads Hydro-Informatics' public `r2dsteady-t15k.slf` tutorial
fixture from GitHub, verifies its SHA-256 hash, inspects the Selafin header, and
imports 25,007 triangular elements into `hydraulic_cells`. Set
`OPENLIMNO_TELEMAC_FIXTURE_DIR` to reuse a local fixture cache.

To validate the inSTREAM matrix reader against the official public inSTREAM 7.4
example package:

```bash
OPENLIMNO_RUN_INSTREAM_REAL=1 \
pytest tests/integration/test_instream_real_fixtures.py
```

The test downloads the Cal Poly Humboldt / Lang Railsback inSTREAM 7.4 example
archive, verifies its SHA-256 hash, and imports the Example A depth and velocity
matrices into `ibm_hydraulic_lookup`. Set `OPENLIMNO_INSTREAM_FIXTURE_DIR` to
reuse a local fixture cache.

For HABBY/CASiMiR exported tables, the integration hook is ready for local or
future public fixtures:

```bash
OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL=1 \
OPENLIMNO_HABITAT_EXCHANGE_FIXTURE=/path/to/habby_wua_cells.csv \
pytest tests/integration/test_habitat_exchange_real_fixtures.py
```

Use `OPENLIMNO_HABITAT_EXCHANGE_URL` and
`OPENLIMNO_HABITAT_EXCHANGE_SHA256` instead of `..._FIXTURE` when validating a
downloaded public table.

The public HABBY TELEMAC tutorial archive is useful for validating OpenLimno's
native TELEMAC Selafin reader because it contains `d1.slf` ... `d9.slf` and
substrate inputs. It does not include the post-calculation WUA/TXT exports, so
HABBY/CASiMiR exchange validation still uses the local/URL fixture hook above.
