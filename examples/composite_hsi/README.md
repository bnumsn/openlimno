# composite_hsi — multivariate HSI overlay on a Heihe-mid-basin case

This example demonstrates the **multivariate HSI composite** introduced
in v1.6.0 and extended with the four-way geometric-mean method in
v1.10.0. The case is sited in the Heihe mid-basin (Qilian piedmont,
NW China; 38.20 °N, 100.20 °E), targeting the cold-water
schizothoracine cyprinid *Schizothorax prenanti* whose range overlaps
the upper Heihe.

It is deliberately **self-contained** — no network fetches, no PHABSIM
fixture replication. The hydraulic + HSI inputs are synthesised so the
script runs in <1 s and the focus stays on what the composite-HSI
overlay does to a WUA-Q curve.

## What the script shows

`quickstart.py` reproduces the same WUA-Q sweep twice, once per
combination method:

1. **`method="product"`** (default; v1.6.0 behaviour) — the basin
   cover and thermal scalars multiply onto the depth × velocity WUA:

       WUA_composite(Q) = WUA_dv(Q) · SI_C · SI_T

   One weak overlay zeros the composite. This is HABBY's *product*
   option and is the safe default when overlays are independent of
   d×v suitability.

2. **`method="geom_mean"`** (v1.10.0; redesigned v1.10.1 after the
   6th-pass review identified NaN-propagation and WUA-inflation
   flaws in the v1.10.0 reach-scale linearisation) — column-level
   overlay softening with the overlay entering as the n-th root:

       WUA_composite(Q) = WUA_dv(Q) · (SI_C · SI_T)^(1/n)

   where `n = 1 + n_overlays`. Softer than product (the overlay
   shrinks WUA less aggressively as the number of overlays grows)
   but never inflates composite above the hydraulic base. The
   **true** per-cell four-way geometric mean
   `(d × v × c × t)^(1/4)` requires cover and thermal as per-cell
   rasters and is flagged for v2.x.

The two composite WUA-Q curves are plotted alongside the base d×v
curve so a reviewer can see at a glance how the choice of overlay
combination rule reshapes the recommended flow.

## Running

```bash
PYTHONPATH=src python examples/composite_hsi/quickstart.py
```

Outputs into `examples/composite_hsi/out/`:

* `wua_q_overlay_comparison.png` — base / product / geom-mean curves
  on one plot
* `composite_summary_product.json` — overlay payload (v1.6.0 schema)
* `composite_summary_geom_mean.json` — overlay payload, geom-mean
  method (carries the new `method` key)

## Notes on the canonical Heihe values

* `cover_si=0.4255` — middle-third Qilian piedmont
  (`watershed_cover_si` averaged across grass/shrubland/cropland
  fractions from WorldCover 2021, 100.10–100.30 °E × 38.10–38.30 °N).
* `thermal_si=0.62` — period-mean of *S. prenanti* preferred range
  (2.5–18.5 °C, FishBase ECOL_009) against Open-Meteo
  2020–2024 surface T at 38.20 °N / 100.20 °E.
* `overlay_si=0.26381` (product) — folded scalar that gates 1.6.0
  regulatory exports.

These numbers anchor the canonical smoke point exercised by the test
suite (`test_v172_overlay_si_skip_warning`, etc.) and let you tie the
example back to the real data flow demonstrated by
`examples/anywhere_bbox/` — without taking on the fetch dependency.
