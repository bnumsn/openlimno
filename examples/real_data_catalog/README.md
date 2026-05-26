# Real Case Data Catalog

This catalog lists real, publicly available case data that can drive OpenLimno
hydraulics and IBM workflows. The emphasis is on datasets that include more
than a river name: model files, observed calibration data, DEMs, depth rasters,
or GIS boundaries.

The machine-readable table is `sources.csv`.

## Best Next Downloads

1. **Wallens Bend, Clinch River, Tennessee**

   Smallest complete hydraulic-model candidate. It includes HEC-RAS 1D model
   files plus calibration/evaluation water-surface and velocity measurements.
   Start here for a real cross-section and calibration workflow.

   - Main collection: <https://www.sciencebase.gov/catalog/item/6323764ed34e71c6d67acb60>
   - HEC-RAS model files: <https://www.sciencebase.gov/catalog/item/63238571d34e71c6d67acbdf>
   - Calibration WSE/velocity: <https://www.sciencebase.gov/catalog/item/63237e7ad34e71c6d67acbaf>

2. **Big River, Missouri mussel habitat reaches**

   Strong fit for OpenLimno's `gis-hydraulics --dem` path. It has
   topo-bathymetric DEMs for four reaches, observed water-surface profiles,
   and sediment data collected for freshwater mussel habitat hydraulics.

   - Main collection: <https://www.sciencebase.gov/catalog/item/5f92e3f882ce720ee2d57820>
   - DEMs: <https://www.sciencebase.gov/catalog/item/6260324ed34e85fa62b88eb4>
   - Water-surface profiles: <https://www.sciencebase.gov/catalog/item/626033a6d34e85fa62b88ebc>

3. **Johnson Creek near Sycamore, Oregon**

   Good small raster/GIS validation case. It has HEC-RAS model boundary,
   inundation polygons, and depth rasters for several flows.

   - Main collection: <https://www.sciencebase.gov/catalog/item/58812db1e4b00a062356ff95>
   - Example 1,200 cfs depth raster: <https://www.sciencebase.gov/catalog/item/58f78978e4b0b7ea5451f0d6>

4. **Kalamazoo River, Michigan 2D HEC-RAS**

   Complete 2D HEC-RAS archive with calibration data, substrate data, and
   quasi-steady raster outputs. This is the best high-fidelity 2D case found,
   but the model archive is several GB.

   - Collection: <https://www.sciencebase.gov/catalog/item/67a38201d34ee33d441d2f22>

5. **Willamette River, Oregon 2D salmonid-habitat models**

   Large 2D HEC-RAS/topo-bathymetric model suite designed for juvenile salmonid
   habitat assessment. Use as a heavyweight benchmark, not a default test.

   - Collection: <https://www.sciencebase.gov/catalog/item/620e94dad34e6c7e83baa7ce>

## Already Implemented Service-Backed Cases

`examples/real_hydro_ibm_cases/` already builds four live service-backed cases:

- Boise River at Glenwood Bridge, Idaho
- Truckee River at Reno, Nevada
- Delaware River at Trenton, New Jersey
- Yakima River at Kiona, Washington

These use USGS NWIS daily discharge and USGS NHD river-area/flowline geometry.
They are useful smoke tests, but they do not include local surveyed DEM or
bathymetry unless an external DEM is added.

## Recommended Implementation Order

1. Add a downloader/extractor for Wallens Bend and parse HEC-RAS geometry into
   OpenLimno cross sections.
2. Add a Big River workflow using the DEM zips and WSE profiles to validate
   `preprocess gis-hydraulics --dem`.
3. Add a raster-depth importer using Johnson Creek GeoTIFF depth rasters.
4. Add optional heavyweight scripts for Kalamazoo and Willamette that are
   never run in default CI because of file size.

## Sources

- USGS NWIS daily values service: <https://waterservices.usgs.gov/nwis/dv/>
- USGS NHD ArcGIS REST service: <https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer>
- USGS ScienceBase: <https://www.sciencebase.gov/>
