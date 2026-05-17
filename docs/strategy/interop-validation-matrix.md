# Interop Validation Matrix

OpenLimno treats external-model support as a validation matrix, not a marketing
claim. A source path is only promoted when it has a reader, CLI coverage, unit
tests, and either a real public fixture or a documented blocker.

| Source | Current status | Validation evidence | Next gap |
|---|---|---|---|
| HEC-RAS `.g0X` | Implemented | Synthetic legacy geometry tests; CLI import coverage | Add public HEC-RAS geometry project fixture |
| HEC-RAS `.hdf/.h5` | Implemented MVP | Synthetic HDF with 2D flow-area cells; FEMA `rashdf` public HEC-RAS `BaldEagleDamBrk.p18.hdf` summary fixture passes when `OPENLIMNO_RUN_HECRAS_REAL=1`; derives depth from WSE minus bed when depth is not written; approximates cell velocity from face velocity when cell-center velocity is not written; CLI inspect/import coverage | Add full time-series HEC-RAS 2D fixture with explicit depth and cell velocity |
| River2D `.cdg/.bed` + habitat CSV | Implemented | Synthetic CDG node/import tests; official River2D `R2D_Habitat.zip` tutorial fixture passes when `OPENLIMNO_RUN_RIVER2D_REAL=1`; official CDG node hydraulic fields and element topology parse; `write_river2d_ugrid()` exports UGRID NetCDF; exported River2D WUA CSV imports through habitat exchange | Add more River2D transient-output variants |
| CF/UGRID NetCDF | Implemented | Synthetic Delft3D/D-Flow-style NetCDF with depth, WSE, UV, area; MHKiT public Delft3D `turbineTest_map.nc` fixture and public WUA example pass when `OPENLIMNO_RUN_NETCDF_REAL=1`; CLI inspect/import coverage | Add larger D-Flow FM UGRID map-file fixture and broader alias matrix |
| MIKE DFS/DFSU | Implemented optional | Fake `mikeio` unit tests; DHI official `HD2D.dfsu` real fixture passes when `OPENLIMNO_RUN_MIKE_REAL=1` | Add DFS2 and mesh real fixtures; harden item-name aliases |
| MIKE 1D/XNS11/RES1D | Implemented optional | Fake `mikeio1d` XNS11/RES1D unit tests; `preprocess diagnose-model --source mike-1d` reports Python package and Linux .NET Runtime readiness; DHI official `mikep_cs_demo.xns11` and `network_river.res1d` fixtures pass in the Pixi `mike` environment with conda-forge .NET Runtime 8.x | Document platform support limits for macOS and add more MIKE+ network variants |
| HABBY/CASiMiR tables | Implemented | Synthetic cell-level, WUA-summary, and HABBY `*_spu.txt` tests; CLI inspect/import coverage; metadata-preamble tables supported; opt-in local/URL fixture hook via `OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL=1`; official HABBY Wiki documents `*_spu.txt` and `*_detailled_mesh.txt` exports, but the public `tuto_telemac_example_data.zip` archive contains only hydraulic/substrate inputs | Add a small, version-pinned public HABBY/CASiMiR exported table and broader column-alias examples |
| inSTREAM/NetLogo IBM | Implemented exchange bridge | Synthetic habitat export and population-summary CSV import tests; official inSTREAM 7.4 Example A depth/velocity matrices pass when `OPENLIMNO_RUN_INSTREAM_REAL=1`; CLI export/inspect/import coverage | Add real model-run population-output fixture and InSALMO-specific examples |
| TELEMAC Selafin | Implemented MVP | Synthetic Selafin binary with mesh/time/depth/WSE/U/V; Hydro-Informatics public `r2dsteady-t15k.slf` real fixture passes when `OPENLIMNO_RUN_TELEMAC_REAL=1`; CLI inspect/import coverage | Expand variable-name matrix and add 3D/layered result handling |

## Opt-In Real Fixtures

Real binary fixtures are downloaded only when explicitly requested:

```bash
OPENLIMNO_RUN_MIKE_REAL=1 \
pytest tests/integration/test_mike_real_fixtures.py

OPENLIMNO_RUN_HECRAS_REAL=1 \
pytest tests/integration/test_hecras_real_fixtures.py

OPENLIMNO_RUN_RIVER2D_REAL=1 \
pytest tests/integration/test_river2d_real_fixtures.py

OPENLIMNO_RUN_TELEMAC_REAL=1 \
pytest tests/integration/test_telemac_real_fixtures.py

OPENLIMNO_RUN_NETCDF_REAL=1 \
pytest tests/integration/test_netcdf_real_fixtures.py \
  tests/integration/test_netcdf_public_wua_example.py

OPENLIMNO_RUN_INSTREAM_REAL=1 \
pytest tests/integration/test_instream_real_fixtures.py

OPENLIMNO_RUN_HABITAT_EXCHANGE_REAL=1 \
OPENLIMNO_HABITAT_EXCHANGE_FIXTURE=/path/to/habby_or_casimir_export.csv \
pytest tests/integration/test_habitat_exchange_real_fixtures.py
```

The HEC-RAS, River2D, MIKE, TELEMAC, CF/UGRID NetCDF, and inSTREAM tests verify
SHA-256 hashes before reading public samples. The HABBY/CASiMiR hook accepts
either a local exported table or a URL plus optional SHA-256. Use
`OPENLIMNO_HECRAS_FIXTURE_DIR`, `OPENLIMNO_MIKE_FIXTURE_DIR`,
`OPENLIMNO_TELEMAC_FIXTURE_DIR`, `OPENLIMNO_NETCDF_FIXTURE_DIR`,
`OPENLIMNO_INSTREAM_FIXTURE_DIR`, `OPENLIMNO_RIVER2D_FIXTURE_DIR`, or
`OPENLIMNO_HABITAT_EXCHANGE_FIXTURE_DIR` to cache downloads outside pytest
temporary directories.
