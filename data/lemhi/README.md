# Lemhi River sample data package

> **Status**: M0 deliverable, complete. 124 KB total.
>
> Reproduce with `python tools/build_lemhi_dataset.py`.

This package satisfies SPEC v0.5 §10.1 item 2 (WEDM v0.1 JSON-Schema **+ real samples**).

## Files

| File | Real / synthetic | Source / authority |
|---|---|---|
| `Q_2024.csv` | **Real** | USGS gauge `13305000` Lemhi River near Lemhi, ID; 366 daily values, 2024-01-01 to 2024-12-31 |
| `rating_curve.parquet` | Synthetic | Calibrated to typical Lemhi Q range (2-12 m³/s); form Q = C(h-h₀)^b |
| `species.parquet` | Real | FishBase + Lemhi Subbasin Plan; 2 species (steelhead, Chinook) |
| `life_stage.parquet` | Real | IDFG / Lemhi Subbasin Plan; 6 stages with monthly TUF defaults |
| `hsi_curve.parquet` | **Real** (public-domain values) | USFWS-FWS/OBS-78/07 (Bovee 1978); Raleigh-Hickman-Solomon 1984; 8 curves for steelhead |
| `hsi_evidence.parquet` | Real | mirrors hsi_curve with citation grades |
| `swimming_performance.parquet` | Real | Bell 1986 Fisheries Handbook; Hodge 1996 |
| `passage_criteria.parquet` | Real | Reiser & Peacock 1985 |
| `survey_campaign.parquet` | Synthetic | OpenLimno-flagged; one IDFG-style campaign |
| `cross_section.parquet` | Synthetic | 11 stations × 21 points each, gravel-cobble trapezoid |
| `redd_count.parquet` | Synthetic | 5 redds in spawning reach |
| `mesh.ugrid.nc` | Synthetic | UGRID-1.0 1D mesh, 11 nodes / 10 edges |
| `manifest.json` | — | provenance tracker |

## Why these specific data

- **USGS 13305000** is a long-record gauge used in NOAA salmon / IDFG steelhead recovery analyses; it is the canonical Lemhi mainstem station.
- **Steelhead HSI** values are Bovee 1978 / Raleigh 1984 — the public USFWS Blue Book curves used by every PHABSIM study in the Pacific Northwest.
- **Bell 1986 swim speeds** scale with body length (10/4/2 BL/s burst/prolonged/sustained) with peak around 13 °C.
- **Reiser-Peacock 1985 jump heights** (1.5 m adult / 0.4 m juvenile) are the standard fish-passage references.

## What is *not* here (and why)

- Real cross-sections from IDFG / USGS: not included to keep this package self-contained and license-clean. M1 ingests real IDFG / USGS cross-section CSVs.
- ADCP transects: live USGS QRev CSVs require a registered NWIS account in some cases; M1 deliverable.
- PIT / RST / eDNA: PTAGIS data is public but large; M2-M3 deliverable.
- Substrate / cover survey polygons: M2 deliverable.

## License

- USGS discharge: public domain
- HSI curves: USFWS public-domain values (Blue Book era)
- Bell 1986 / Reiser-Peacock 1985: published values, free to cite
- Synthetic items (rating curve, cross-sections, mesh, redd counts): CC-BY-4.0 (OpenLimno)

The package as a whole is distributed CC-BY-4.0 with attribution to OpenLimno + cited primary sources.

## Validation

`tests/integration/test_lemhi_dataset.py` round-trips every Parquet through its WEDM schema. Run via:

```bash
pixi run pytest tests/integration/test_lemhi_dataset.py
```

15 tests, 0 failures expected.

## Regenerate

```bash
python tools/build_lemhi_dataset.py
```

Requires network for USGS fetch. If offline, the script falls back to a constant placeholder series (with a WARN log) and the rest still produces valid synthetic data.
