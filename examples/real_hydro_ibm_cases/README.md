# Real Hydro + IBM Case Batch

This directory builds several real-data OpenLimno screening cases. Each case
uses public USGS services:

- USGS NWIS daily mean discharge, parameter `00060`, statistic `00003`
- USGS National Hydrography Dataset river-area boundaries and linked flowlines
- OpenLimno GIS hydraulics with the `builtin-1d` solver
- OpenLimno native IBM with a shared rainbow trout screening profile

The default cases are:

| case | USGS station | NHD area | river |
| --- | --- | --- | --- |
| `boise_glenwood` | `13206000` | `120008049` | Boise River |
| `truckee_reno` | `10348000` | `120008177` | Truckee River |
| `delaware_trenton` | `01463500` | `167393148` | Delaware River |
| `yakima_kiona` | `12510500` | `153011766` | Yakima River |

## Build And Run

```bash
pixi run python examples/real_hydro_ibm_cases/build_cases.py
```

After the first build, use `--offline` to rebuild from saved raw downloads:

```bash
pixi run python examples/real_hydro_ibm_cases/build_cases.py --offline
```

Outputs:

- Case folders: `examples/real_hydro_ibm_cases/cases/<case>/`
- Hydraulic forcing: `cases/<case>/data/hydraulics/hydraulic_cells.csv`
- Hydraulic cell geometry: `cases/<case>/data/hydraulics/hydraulic_cells.geojson`
- Calibration template: `cases/<case>/data/hydraulics/calibration_observed_template.csv`
- IBM scenario: `cases/<case>/scenario.yaml`
- Batch summary: `examples/real_hydro_ibm_cases/batch_results.csv`

## Sources

- USGS NWIS daily values service:
  <https://waterservices.usgs.gov/nwis/dv/>
- USGS NHD ArcGIS REST service:
  <https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer>

## Limits

These are workflow validation cases. The river boundaries and flow records are
real, but the hydraulic cross-sections use boundary-derived geometry unless a
local DEM/bathymetric survey is supplied. Use the generated calibration
template to add observed water surface, depth, or velocity before making
management decisions.
