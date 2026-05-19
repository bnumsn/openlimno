# R-BASIN-1 — Lemhi end-to-end status (2026-05-20)

> Closes one half of [ROADMAP.md unfreeze-gate U4](ROADMAP.md#how-to-unfreeze):
> demonstrating one real basin case runs end-to-end through OpenLimno
> with publication-grade artifacts.
>
> Status: **OPERATIONAL** at the engineering level. The pipeline runs
> end-to-end on Lemhi fixtures (`data/lemhi/*.parquet`, `Q_2024.csv`,
> `mesh.ugrid.nc`, `rating_curve.parquet`) and produces every artifact
> the 1.0 surface freeze contract promises. What remains for full U4
> closure is **scientific validation** (not engineering work).

## What works end-to-end (verified 2026-05-20)

A single call:

```python
from openlimno.case import Case
case = Case.from_yaml("examples/lemhi/case.yaml")
result = case.run(discharges_m3s=[5.0, 10.0, 20.0, 40.0])
```

…produces, in `out/lemhi_2024/`:

| Artifact | Format | Contract |
|---|---|---|
| `wua_q.csv` | CSV (with `#`-prefixed grade-B watermark header) | WUA-Q curve per species/stage; one row per discharge |
| `wua_hmu.csv` | CSV | WUA aggregated to HMU (Hydromorphological Mesohabitat Unit) scale |
| `composite_wua_q.csv` | CSV | Per-species composite using `composite: min` (avoids independence assumption per SPEC §4.2.2.3) |
| `hydraulics.nc` | UGRID-1.0 NetCDF | Depth + velocity per cell × discharge |
| `provenance.json` | JSON | SHA chain: openlimno_version, git_sha, parameter_fingerprint, wua_quality_grade, inputs, dependencies |
| `sl712.csv` | CSV | CN SL/Z 712-2014 four-tuple regulatory export |
| `sl712_composite.csv` | CSV | Composite version of SL712 |
| `ferc_4e.csv` | CSV | US FERC §4(e) regulatory export |
| `ferc_4e_composite.csv` | CSV | Composite version of FERC |
| `eu_wfd.csv` | CSV | EU Water Framework Directive ecological status |
| `eu_wfd_composite.csv` | CSV | Composite version of EU-WFD |
| `composite_hsi.json` | JSON | Composite-overlay summary metadata |

With `studio.headless.run_case_with_plots`:

| Additional artifact | Format |
|---|---|
| `wua_q_curve.png` | matplotlib PNG, all species/stage combos on one panel |
| `wua_q_oncorhynchus_mykiss_spawning.png` | per species/stage PNG |

All 13 core artifacts + 2 plots are pinned by the R-DOC-AUDIT-WIRED
pass #4 audit (`tests/integration/test_r5_r14_lemhi_end_to_end_audit.py`).

## What's WUA on Lemhi 2024

Concrete numbers from the audit run (4 discharges, steelhead spawning
+ fry):

| Q (m³/s) | WUA spawning (m²) | WUA fry (m²) |
|---|---|---|
| 5.0 | 61.5 | 0.28 |
| 10.0 | 48.5 | 0 |
| 20.0 | 8.35 | 0 |
| 40.0 | 0 | 0 |

These numbers are not yet validated against any field measurement —
they're the OpenLimno computation against the shipped HSI curves,
shipped HSI evidence (transferability flag drives the grade-B
watermark), and the Lemhi geometry. See "What needs scientific
validation" below.

## What needs scientific validation for full U4 closure

The engineering pipeline is operational. For U4 to count as "real
basin case study published" (the [CAPABILITY_BOUNDARY D6](governance/CAPABILITY_BOUNDARY_1_0.md)
criterion), the following work is required — none of it is more
OpenLimno code:

1. **Field-data comparison**. Lemhi has historical electrofishing /
   redd-survey data (USGS / IDFG records). The OpenLimno WUA-Q
   prediction needs to be compared against documented spawning-site
   use at known discharges. Validation target: rank-order agreement
   between predicted-WUA peak Q and observed-spawning peak Q.
2. **HSI evidence chain**. `data/lemhi/hsi_evidence.parquet` carries
   the transferability metadata that drives the B watermark. A real
   publication needs (a) primary HSI source citation; (b)
   transferability justification per Bovee 1986 / SPEC §4.2.2.3;
   (c) reviewer-of-record sign-off (this is part of U5).
3. **Reach selection**. `examples/lemhi/case.yaml` ships an
   11-node mesh — enough for the engineering smoke test, NOT
   enough for a publication-grade WUA curve. Real publication
   needs a denser reach (200+ cross-sections per IFIM Step 4)
   from documented Lemhi cross-section surveys.
4. **Discharge regime**. The audit uses 4 toy discharges. Real
   work needs the full Q-time-series from `data/lemhi/Q_2024.csv`
   driving habitat-time-series + duration-curve analysis per
   SPEC §4.2.4. The plumbing exists; just hasn't been exercised
   on Lemhi specifically.

## What R-BASIN-1 Lemhi *cannot* close on its own

Per [ROADMAP.md unfreeze-gate](ROADMAP.md#how-to-unfreeze):

- **U1+U2**: governance (need ≥ 3 maintainers + PSC signatures)
- **U5**: regulatory reviewer-of-record on at least one of
  SL-712 / FERC / EU-WFD
- **R-CN-BASIN**: charter prefers a Chinese basin (Yangtze
  tributary / Yellow River); Lemhi closes the "ANY real basin"
  question but not the "preferred CN basin" question

So R-BASIN-1 partially advances U4 — concretely, it eliminates the
"does the pipeline even run on a real fixture?" doubt. Publication-
grade closure requires (1)–(4) above PLUS U5 sign-off.

## Linked artifacts

- `examples/lemhi/case.yaml` — the case definition
- `data/lemhi/` — fixture inventory (`manifest.json` is the canonical list)
- `examples/lemhi/quickstart.py` — the user-facing entry point
- `examples/lemhi/README.md` — the user-facing walkthrough
- `tests/integration/test_r5_r14_lemhi_end_to_end_audit.py` — the audit pin
- `benchmarks/lemhi/` — basin-specific benchmark fixtures (separate
  from `examples/lemhi/`)

## Next concrete actions (when U1+U2 close)

1. Acquire IDFG / USGS Lemhi cross-section + spawning observations
2. Replace placeholder mesh with documented Lemhi survey
3. Re-run + write up as `docs/reviews/lemhi_real_basin_2026.md`
4. Submit for U5 reviewer-of-record outreach (SL-712 most accessible
   given charter preference for CN regulators)

None of these is code work. All are field/data/outreach work.
