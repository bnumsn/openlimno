# anywhere_bbox — case from "give me a bbox + a species"

This is the canonical OpenLimno workflow for building a fully-
provenanced case anywhere on Earth from nothing but:

- a `(lon_min, lat_min, lon_max, lat_max)` bounding box, and
- a target species scientific name.

Everything else — bathymetry, climate, watershed boundary, soil, land
cover, species occurrence records — gets pulled by the v0.3.x fetch
package from subscription-free public APIs. The produced
`case.yaml` is a WEDM v0.2 document that downstream OpenLimno modules
consume unchanged.

## Worked example: Heihe mid-basin (Qilian piedmont, NW China)

```bash
# Pour point + bbox: a small alpine catchment NW of Zhangye, Gansu.
# Species: Schizothorax prenanti (a cold-water schizothoracine cyprinid
# whose range overlaps the upper Heihe). We use a moderately large
# bbox to maximise GBIF occurrence hits for the validator.

XDG_CACHE_HOME=/tmp/openlimno-anywhere-cache \
  pixi run openlimno init-from-osm \
    --bbox 100.10,38.10,100.30,38.30 \
    --output examples/anywhere_bbox/run \
    --fetch-dem cop30 \
    --fetch-watershed hydrosheds:as:38.20:100.20 \
    --fetch-soil     soilgrids:38.20:100.20 \
    --fetch-lulc     worldcover:100.10:38.10:100.30:38.30:2021 \
    --fetch-species  "gbif:Schizothorax prenanti:97.0:28.0:105.0:33.0" \
    --fetch-climate  open-meteo:38.20:100.20:2020:2024
```

After this command:

- `examples/anywhere_bbox/run/case.yaml` is a **WEDM v0.2** case
  with `case.bbox` set and 6 populated `data.*` blocks.
- `examples/anywhere_bbox/run/data/` holds the produced files
  (`watershed.geojson`, `lulc_2021.tif`, `soil.csv`,
  `climate_2020_2024.csv`, `species_gbif_<key>.csv`).
- `examples/anywhere_bbox/run/.openlimno_external_sources.json`
  records every fetch's source URL, fetch time, parameters, and
  SHA-256.

Then run the case:

```bash
pixi run openlimno run examples/anywhere_bbox/run/case.yaml
```

The produced `out/.../provenance.json` includes a new top-level
`fetch_summary` block (added in v0.6) that surfaces the v0.2
`data.*` pointers as descriptive metadata. The `external_sources`
list carries the full per-fetch SHA chain for
`openlimno reproduce`.

## What the species validator flags (v0.6)

`Case._build_provenance` reads `data.species_occurrences.match_type`
from the case.yaml and writes warnings to `provenance.warnings`:

- `match_type == "NONE"` → loud warning. The user wrote a name GBIF
  couldn't resolve; downstream HSI / WUA results are running with
  an unverifiable taxon identity.
- `occurrence_count_total == 0` → loud warning. The species has
  zero GBIF records inside the bbox. Either the bbox is wrong, the
  taxon name is wrong, or this is a restoration / introduction case
  — in any case worth confirming before publishing.

## Why this exists

Pre-v0.3 OpenLimno was a great runtime once you had a fully-prepared
case. Building that case required reading 6 different data portals'
docs and accepting that none of them had a machine-readable
provenance trail. The fetch system + WEDM v0.2 closes both of those
gaps in a single CLI invocation. `anywhere_bbox/` is the example
that proves the chain end-to-end.

## Notes

- The HydroSHEDS continental shapefile (~80 MB Asia) only downloads
  once — subsequent runs hit the local cache instantly.
- Open-Meteo's archive endpoint is rate-limited per IP; if you build
  many cases across a wide region, leave the `XDG_CACHE_HOME` cache
  warm between runs.
- The example does NOT specify `--fetch-discharge` because USGS NWIS
  is US-only. For non-US cases discharge has to come from a
  user-provided CSV (see `data.rating_curve` and the boundaries
  block in `case.yaml`) until v0.4+ ships a global discharge fetcher.
