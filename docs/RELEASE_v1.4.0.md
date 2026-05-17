# OpenLimno v1.4.0 release notes

**Status**: shipped
**Date**: 2026-05-17
**Theme**: ecological-flow interoperability hub

> Note: this work was staged on the v1.3.0-rc branch in
> `docs/STATE_2026_05.md` + `CHANGELOG.md`; the v1.3.0 tag had
> already been used by the LULC riparian cover ship (`78e769f`),
> so the interop release ships as v1.4.0 to respect that
> published tag.

## TL;DR

v1.4.0 turns OpenLimno from a PHABSIM-modernization platform into an
interoperability layer for fish-habitat and ecological-flow work. Users can keep
their hydraulic or habitat model of record, stage its outputs into OpenLimno,
then run shared HSI/WUA, population-exchange, provenance, and reporting paths.

The goal is explicit: interoperate with the tools practitioners already use
instead of asking them to abandon HEC-RAS, MIKE, TELEMAC, Delft3D, River2D,
HABBY, CASiMiR, FishXing-style passage workflows, or inSTREAM/NetLogo models.

## New User Surface

```bash
openlimno preprocess import-model --list-supported

openlimno preprocess inspect-model --source hecras-hdf --in ras_project.p01.hdf
openlimno preprocess import-model --source hecras-hdf --in ras_project.p01.hdf \
  --out data/hecras_hydraulic_cells.parquet --time-index -1

openlimno wua-cells --cells data/hecras_hydraulic_cells.parquet \
  --hsi data/hsi_curve.parquet --species oncorhynchus_mykiss \
  --stage spawning --out-dir out/hecras_habitat
```

For optional MIKE support in this repository:

```bash
pixi install -e mike
pixi run -e mike openlimno preprocess diagnose-model --source mike-1d
OPENLIMNO_RUN_MIKE_REAL=1 pixi run -e mike pytest tests/integration/test_mike_real_fixtures.py
```

For a public TELEMAC end-to-end demo:

```bash
pixi run python examples/model_interop/telemac_public_wua.py \
  --cache-dir /tmp/openlimno_telemac_fixtures \
  --out-dir /tmp/openlimno_telemac_public_wua
```

For a public Delft3D NetCDF end-to-end demo:

```bash
pixi run python examples/model_interop/delft3d_public_wua.py \
  --cache-dir /tmp/openlimno_netcdf_fixtures \
  --out-dir /tmp/openlimno_delft3d_public_wua
```

## Implemented Interop Matrix

| Source key | Model family | Output table | Validation status |
|---|---|---|---|
| `hecras-geometry` | HEC-RAS `.g0X` | `cross_section_points` | synthetic + CLI tests |
| `river2d-cdg` | River2D `.cdg/.bed` | `mesh_nodes` | synthetic + official `R2D_Habitat.zip` fixture |
| `hecras-hdf` | HEC-RAS HDF | `hydraulic_cells` | synthetic + FEMA `rashdf` public HEC-RAS fixture |
| `telemac-slf` | TELEMAC Selafin | `hydraulic_cells` | synthetic + Hydro-Informatics public fixture |
| `delft3d-netcdf` | Delft3D FM / CF-UGRID NetCDF | `hydraulic_cells` | synthetic + MHKiT public Delft3D fixture |
| `mike-dfs` | MIKE 21 / MIKE FM DFS/DFSU/mesh | `hydraulic_cells` or time series | DHI public `HD2D.dfsu` fixture passes |
| `mike-1d` | MIKE 1D / MIKE 11 XNS11/RES1D | cross-sections or time series | DHI public `mikep_cs_demo.xns11` and `network_river.res1d` fixtures pass in Pixi `mike` env |
| `habby-csv` | HABBY / CASiMiR / MesoHABSIM exchange tables | `habitat_cells` or `wua_summary` | CSV/TXT synthetic tests + fixture hook |
| `instream-netlogo` | inSTREAM / InSALMO / NetLogo exchange | IBM exchange tables | synthetic + official inSTREAM 7.4 matrix fixture |

## What Changed

- Added a central external-model registry and CLI source inference.
- Added HEC-RAS HDF, TELEMAC Selafin, CF/UGRID NetCDF, MIKE, HABBY/CASiMiR, and
  inSTREAM/NetLogo import/export adapters.
- Hardened HEC-RAS HDF import for real 2D summary files that expose flow-area
  topology through `Cells Face and Orientation*` plus `FacePoints Coordinate`
  instead of a direct `Cells Center Coordinate` dataset.
- HEC-RAS HDF import now derives `depth_m` from `water_surface_m -
  bed_elevation_m` when a cell depth dataset is not present but both WSE and
  cell minimum elevation are available.
- When HEC-RAS lacks cell-center velocity but exposes face velocity, OpenLimno
  now imports an explicit approximate `velocity_ms` as the mean absolute face
  velocity around each cell and records that approximation in warnings.
- Added `wua-cells` for direct WUA evaluation from imported hydraulic-cell
  tables.
- Added a Pixi `mike` environment with `dotnet-runtime` 8.x, `mikeio`, and
  `mikeio1d`.
- Added MIKE dependency diagnostics so `.NET Runtime` gaps are visible before a
  user tries to open real XNS11 or RES1D files.
- Hardened MIKE 1D result export by suffixing duplicate DHI result column names,
  allowing wide RES1D tables to write cleanly to Parquet/CSV.
- Hardened River2D import for the official 2002 `.CDG` tutorial layout,
  including node depth/unit-discharge fields, derived velocity, and a Python API
  plus CLI command for triangular element topology and UGRID NetCDF export.
- Added a public TELEMAC end-to-end example that downloads a real Selafin
  fixture, imports all time steps, evaluates demonstration HSI curves, and writes
  WUA tables, a plot, and a Markdown report.
- Hardened the CF/UGRID NetCDF adapter against real Delft3D variable layouts
  where cell-centre coordinates are coordinates rather than data variables, and
  where depth-averaged velocity is exposed as `ucxa`/`ucya`.
- Added a public Delft3D NetCDF end-to-end WUA example using the pinned MHKiT
  `turbineTest_map.nc` fixture.
- Added strategy docs that position OpenLimno against PHABSIM, River2D,
  HEC-RAS, MIKE, TELEMAC, HABBY, CASiMiR, FishXing, and inSTREAM.

## Remaining Gaps

- Add a full time-series HEC-RAS 2D HDF fixture with depth and cell velocity.
- Add additional River2D transient-output variants beyond the official habitat
  tutorial CDG/CSV shape.
- Add a small public HABBY/CASiMiR exported WUA table. The public HABBY TELEMAC
  tutorial archive contains hydraulic/substrate inputs, not post-calculation WUA
  exports.
- Add full end-to-end tutorials for HEC-RAS and MIKE once public fixtures expose
  the depth/velocity/area fields needed by `wua-cells`.
- Run Pixi `mike` CI on Windows once GitHub runner timing is measured.

## Verification

The release candidate has been checked locally with:

```bash
pixi run pytest tests/unit/test_legacy_importers.py tests/unit/test_cli.py \
  tests/unit/test_habitat.py tests/integration/test_mike_real_fixtures.py \
  tests/integration/test_telemac_real_fixtures.py \
  tests/integration/test_telemac_public_wua_example.py \
  tests/integration/test_netcdf_real_fixtures.py \
  tests/integration/test_hecras_real_fixtures.py \
  tests/integration/test_river2d_real_fixtures.py \
  tests/integration/test_instream_real_fixtures.py \
  tests/integration/test_habitat_exchange_real_fixtures.py -q

OPENLIMNO_RUN_MIKE_REAL=1 OPENLIMNO_MIKE_FIXTURE_DIR=/tmp/openlimno_mike_fixtures \
  pixi run -e mike pytest tests/integration/test_mike_real_fixtures.py -q

OPENLIMNO_RUN_HECRAS_REAL=1 OPENLIMNO_HECRAS_FIXTURE_DIR=/tmp/openlimno_hecras_fixtures \
  pixi run pytest tests/integration/test_hecras_real_fixtures.py -q

OPENLIMNO_RUN_RIVER2D_REAL=1 OPENLIMNO_RIVER2D_FIXTURE_DIR=/tmp/openlimno_river2d_fixtures \
  pixi run pytest tests/integration/test_river2d_real_fixtures.py -q

OPENLIMNO_RUN_NETCDF_REAL=1 OPENLIMNO_NETCDF_FIXTURE_DIR=/tmp/openlimno_netcdf_fixtures \
  pixi run pytest tests/integration/test_netcdf_real_fixtures.py \
  tests/integration/test_netcdf_public_wua_example.py -q

pixi run -e docs mkdocs build
```

Known doc warnings are inherited review-archive relative links; they are not
introduced by the interop release.
