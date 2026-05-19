# composite_hsi — v2.7.x dual-raster YAML-driven per-cell composite

> v2.8.0 upgrade. This example was the v1.10.0 synthetic-DataFrame
> walkthrough of `apply_overlay`; v2.8.0 promotes it to a *real*
> `Case.run` workflow driven entirely by `case.yaml` + checked-in
> raster fixtures, demonstrating the end-to-end charter that
> v2.6.0 + v2.6.1 + v2.7.0 + v2.7.1 closed.

## What this example shows

A single `case.yaml` that:

1. Loads hydraulics (cross-sections, HSI curves, species, life-stage)
   from the shared Lemhi PHABSIM-equivalent fixture under
   `../../data/lemhi/`.
2. Pulls **per-section thermal SI** directly from a GeoTIFF — the
   v2.6.0 inline path. `data.thermal_raster.uri` references a 12×12
   °C raster; `data.section_locations.uri` provides one (lon, lat)
   per cross-section; `data.fishbase_traits` supplies the
   `ThermalRange` (FishBase ECOL_009 for *Oncorhynchus mykiss*,
   0..25 °C — aligned to `habitat.species` in v2.10.1 R11-1).
3. Pulls **per-section cover SI** the same way — the v2.7.0 inline
   path. `data.cover_raster.uri` references an LULC GeoTIFF; each
   section's pixel code is mapped via `DEFAULT_RIPARIAN_COVER_SI`.
4. Runs the v2.4.0 per-cell composite path
   (`habitat.composite_overlay_method = geom_mean_per_cell`) and
   threads BOTH per-section arrays into `apply_overlay_per_cell` so
   the composite is the true four-way
   `(d × v × c × t)^(1/4)` per-cell geometric mean — not a
   basin-scalar broadcast.

No offline preprocessing. No hand-built DataFrames. The full chain
runs in <2 s and writes a complete provenance trail to
`./out/composite_hsi_demo/`.

## Running

```bash
PYTHONPATH=src python examples/composite_hsi/quickstart.py
```

Or via the CLI:

```bash
PYTHONPATH=src openlimno run examples/composite_hsi/case.yaml
```

Outputs in `./out/composite_hsi_demo/`:

| File | Source ship | Content |
|------|-------------|---------|
| `wua_q.{csv,parquet}` | v1.0 | depth × velocity WUA per discharge |
| `composite_wua_q.{csv,parquet}` | v2.4.0 + v2.7.0 | per-cell composite WUA per discharge |
| `composite_hsi.json` | v1.6.0 + v2.6.1 R9-7 synth | overlay factors + per-series stats |
| `thermal_hsi.csv` | v1.1.1 | basin-scalar thermal series (back-compat) |
| `cover_si.json` | v1.5.0 | basin-scalar cover summary (back-compat) |
| `provenance.json` | v0.8 | full audit trail |
| `composite_wua_q_comparison.png` | this script | base vs composite plot per series |

## Files shipped under `./data/`

| File | Shape / type | Description |
|------|--------------|-------------|
| `thermal_C.tif` | 12×12 float32, EPSG:4326 | east-west 8..14 °C gradient simulating a real river thermal cross-section |
| `cover_lulc.tif` | 12×12 uint8, EPSG:4326 | WorldCover-style class mix (10=tree, 20=shrub, 30=grass, 60=bare) — symbolic stand-in for an ESA WorldCover tile clipped to a real Heihe riparian buffer |
| `section_locations.csv` | 11 rows | per-section (station_m, lon, lat) anchors; one per Lemhi cross-section |

The rasters and locations are deliberately synthetic so the example
is fully self-contained — no network fetches, no proprietary data,
and the entire chain (case load → sample raster → composite → write)
runs offline in under two seconds.

## Charter checkpoint

The v2.0.0 charter listed "per-cell raster overlay end-to-end,
YAML-driven" as a 3.x research-route item. v2.6.0 closed the thermal
side; v2.7.0 closed the cover side; v2.6.1 + v2.7.1 polished the CRS
/ nodata / unmapped-code edges. **v2.8.0 is the example that proves
the full chain works as a single user-runnable case.yaml**, with no
in-script construction of overlay arrays.

## Comparing to the v1.10.0 example

The v1.10.0 quickstart built bell-shaped WUA-Q DataFrames in Python
and called `apply_overlay()` on them — useful for understanding the
formula, but not representative of the production path. The v2.8.0
version drops the synthetic DataFrames entirely; everything flows
through `Case.from_yaml` → `Case.run`, and the per-cell composite
mechanics are exercised the same way a real basin study would
exercise them.
