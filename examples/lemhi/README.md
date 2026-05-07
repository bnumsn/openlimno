# Lemhi River PHABSIM Equivalence Example

Goal: reproduce the canonical PHABSIM Bovee 1997 standard case in OpenLimno using Lemhi River public data, demonstrating SPEC §4.1 (1D hydraulics) + §4.2 (HSI/WUA) + §4.2.4.1 (WUA-Q curve).

## Status

**M0**: schema-valid placeholder case.yaml; data files are TBD.

**M1**: real Lemhi cross-sections and ADCP transects imported via `openlimno preprocess`.

**M2**: end-to-end run reproducing PHABSIM WUA table within ≤ 1e-3 (table-level regression, see SPEC §4.1.3).

## Why Lemhi

- USGS public data: cross-sections, gauges, rating curves, redd surveys all available
- Used as the validation case in River2D (Steffler & Blackburn 2002)
- Salmonid-driven (Oncorhynchus mykiss / Chinook), classic IFIM workflow
- No data licensing complications

## Files (M1+)

```
examples/lemhi/
├── case.yaml                 # study configuration (this directory)
├── README.md                 # you are here
└── ../../data/lemhi/
    ├── mesh.ugrid.nc         # 1D cross-section chain
    ├── Q_2024.csv            # upstream discharge
    ├── rating_curve.parquet  # downstream rating curve
    ├── species.parquet       # Oncorhynchus mykiss entry
    ├── life_stage.parquet    # spawning + fry
    ├── hsi_curve.parquet     # USFWS Blue Book HSI for steelhead
    ├── hsi_evidence.parquet  # citations + quality grades
    └── survey_campaign.parquet
```

## Running (M2+)

```bash
pixi run openlimno validate examples/lemhi/case.yaml
pixi run openlimno run examples/lemhi/case.yaml
pixi run openlimno wua examples/lemhi/case.yaml --species oncorhynchus_mykiss --stage spawning --plot
```

## Comparing to PHABSIM

`benchmarks/phabsim_bovee1997/` runs the same hydraulic + HSI inputs through PHABSIM (via Wine on Linux CI) and asserts WUA table equivalence (≤ 1e-3).
