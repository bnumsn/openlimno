# Preprocess

`openlimno.preprocess` ingests real-world data into WEDM. M1 supports the **first-mile core three** (SPEC §4.0.1):

| Source | Reader | CLI |
|---|---|---|
| Cross-sections (CSV / Excel) | `read_cross_sections` | `openlimno preprocess xs` |
| USGS QRev CSV ADCP | `read_adcp_qrev` | `openlimno preprocess adcp` |
| DEM GeoTIFF | `read_dem` | `openlimno preprocess dem-info` |

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

| Format | Status | Module |
|---|---|---|
| HEC-RAS `.g0X` | Best-effort, M3 | `read_hecras_geometry` |
| River2D `.cdg/.bed` | Best-effort, M3 | `import_river2d` |
| TRDI / SonTek native ADCP binary | M3 | `read_adcp_native` |
| PHABSIM `.IFG` | M3 | `import_phabsim` |

These are best-effort migrators (per ADR-0003 reasoning); they are not part of the 1.0 contract because the upstream binary formats are not openly specified.
