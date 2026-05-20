# U4 Evidence Plan: Lemhi Fixture vs Real Basin Case Study

Status: drafted 2026-05-20. This document does not claim U4 closure.

## Current State

The Lemhi pipeline is operational as a fixture pipeline: `examples/lemhi`
loads, `Case.run` completes, and the audited run emits WUA, hydraulics,
provenance, and regulatory CSV artifacts. That is a prerequisite only.
It proves OpenLimno can execute the workflow, not that the workflow has
been validated on a real basin.

`data/lemhi/manifest.json` still identifies the following core evidence
inputs as synthetic: `cross_section.parquet`, `mesh.ugrid.nc`,
`redd_count.parquet`, and `survey_campaign.parquet`. The shipped
`rating_curve.parquet` is also synthetic unless replaced by a successful
run of `tools/lemhi_real_data_fetch.py`.

## Real-Data Progress Available Now

`tools/lemhi_real_data_fetch.py` is the next concrete step. It can fetch
public, subscription-free layers for the Lemhi basin:

- USGS Water Data field measurements for gauge `13305000`, written to
  `rating_curve.parquet` when available.
- Copernicus GLO-30 DEM over the Lemhi reach bbox, written to
  `lemhi_cop30_dem.tif`.
- HydroSHEDS HydroBASINS watershed polygon, written to
  `lemhi_watershed.geojson`.
- GBIF occurrence records for `Salmo trutta` and `Oncorhynchus mykiss`
  in the Lemhi bbox, written to `gbif_*.csv`.

The script updates `manifest.json` only after each file exists and its
SHA-256 is known. This avoids converting the manifest into a promise
about data that has not been fetched.

## Remaining Gap to U4

U4 requires one real basin case study published. The fetch script does
not supply that evidence by itself. A publishable Lemhi case still needs:

- Surveyed cross-sections or a defensible DEM-derived cross-section
  method accepted by a reviewer.
- A real UGRID mesh derived from survey/DEM geometry rather than the
  current synthetic 1D chain.
- Field biological observations: redd counts, electrofishing density,
  snorkel use, PIT/RST data, or an equivalent documented observation set.
- A statistical comparison between observed habitat use and predicted
  WUA-Q or HMU-scale suitability.
- A written case-study report with data provenance, model settings,
  uncertainty limits, and reviewer response.

## Honest Acceptance Standard

The Lemhi fixture pipeline should continue to be described as
"operational prerequisite met." U4 can be claimed only after the synthetic
geometry and biological-observation fixtures are replaced or explicitly
excluded from the scientific claim, the case study is written, and a
reviewable artifact is published.
