# U4 prerequisite: Lemhi fixture pipeline operational (2026-05-20)

> **Round-19 codex S2 + gemini S2 correction (HIGH × 2)**: this
> document was previously titled `r_basin_1_lemhi_status.md` and
> claimed Lemhi "partially closed" unfreeze gate U4. Both reviewers
> independently identified that framing as a recurrence of the
> codex S5 strategic pattern — "API exists ≠ capability exists" —
> in different wording. Gemini called it "The Capability Illusion".
> The pipeline running without crashing on a fixture is **NOT**
> evidence for U4 ("one real basin case study published"); it is a
> prerequisite. This doc is renamed to reflect what it actually
> attests to.
>
> Status: ✅ **PREREQUISITE MET** — Lemhi fixture pipeline runs
> end-to-end. The pipeline produces a default 7-artifact set on the
> shipped fixtures. **NOT** counted toward unfreeze gate U4.

## What this document attests to

✅ The OpenLimno pipeline can:
1. Load `examples/lemhi/case.yaml` via `Case.from_yaml` without
   error (R10/R11 WEDM schema accepts the shipped fixture).
2. Run `Case.run(discharges_m3s=[5.0, 10.0, 20.0, 40.0])` to
   completion (~1s on a development machine).
3. Produce the 7-artifact default set documented below.
4. Optionally produce a composite WUA-Q PNG via
   `studio.headless.run_case_with_plots`.

✅ The R5..R14 review-chain helpers (atomic-write, regulatory CSV
emission, provenance SHA chain, HSI quality grade watermark) are
exercised in composition by this run and audit-confirmed wired.

## What this document does NOT attest to

❌ The WUA numbers produced are **not** field-validated. No
documented Lemhi spawning observations have been compared against
the predicted-WUA peaks.

❌ The cross-section geometry is **not** real. Per
`data/lemhi/manifest.json`:
- `cross_section.parquet`: `"real": false, "note": "synthetic"`
- `mesh.ugrid.nc`: `"real": false, "note": "synthetic 1D mesh"`
- `rating_curve.parquet`: `"real": false, "note": "synthetic"`
- `redd_count.parquet`: `"real": false`
- `survey_campaign.parquet`: `"real": false`

The HSI curves, life-stage tables, swimming performance, passage
criteria, and discharge series ARE real per the same manifest
(`hsi_curve.parquet` from USFWS Blue Book + Raleigh 1984; `Q_2024.csv`
from USGS gauge 13305000; etc.).

❌ `examples/lemhi/case.yaml:1` literally says "placeholder" in
the comment header. The case was always staged as a fixture to
prove the pipeline shape, never as a publication artifact.

❌ No reviewer-of-record has signed any output of this run.

## Default 7-artifact contract (bare `Case.run`)

| Artifact | Format | Notes |
|---|---|---|
| `wua_q.csv` | CSV (with `#`-prefixed grade-B watermark header) | WUA-Q curve per species/stage; one row per discharge |
| `wua_hmu.csv` | CSV | WUA aggregated to HMU (Hydromorphological Mesohabitat Unit) scale |
| `hydraulics.nc` | UGRID-1.0 NetCDF | Depth + velocity per cell × discharge |
| `provenance.json` | JSON | SHA chain: openlimno_version, git_sha, parameter_fingerprint, wua_quality_grade, inputs, dependencies |
| `sl712.csv` | CSV | CN SL/Z 712-2014 four-tuple regulatory export |
| `ferc_4e.csv` | CSV | US FERC §4(e) regulatory export |
| `eu_wfd.csv` | CSV | EU Water Framework Directive ecological status |

**+1 PNG via `studio.headless.run_case_with_plots`**:

| `wua_q_curve.png` | matplotlib PNG | Composite WUA-Q curve panel |

(Per-species/stage panels like
`wua_q_oncorhynchus_mykiss_spawning.png` are only emitted when the
species/stage carries nonzero WUA across the sweep.)

**Opt-in extensions** (require `habitat.composite_overlay_method`
or similar in case.yaml; NOT default):

| `composite_wua_q.csv` | CSV | Per-cell composite using `composite_overlay_method = geom_mean_per_cell` |
| `composite_hsi.json` | JSON | Composite-overlay summary metadata |
| `sl712_composite.csv`, `ferc_4e_composite.csv`, `eu_wfd_composite.csv` | CSV | Composite versions of the 3 base regulatory exports |

The original `examples/lemhi/out/lemhi_2024/` directory in the
repo contains all 13 artifacts (7 default + 6 opt-in) plus 2 PNGs
because it was produced by a run with composite-overlay enabled.
**Bare `Case.run` on the unmodified Lemhi case.yaml produces 7
artifacts, NOT 13.** The previous version of this doc mis-counted.

## WUA numbers from a fresh run (audit reference)

```
Discharges: [5.0, 10.0, 20.0, 40.0] m³/s
HSI grade: B (transferred curves; SPEC §4.2.2)
Composite method: min (default; avoids independence assumption)

Q (m³/s) │ WUA spawning (m²) │ WUA fry (m²)
─────────┼──────────────────┼────────────
   5.0   │       61.5        │     0.28
  10.0   │       48.5        │     0
  20.0   │        8.35       │     0
  40.0   │        0          │     0
```

These numbers are reproducible from
`tests/integration/test_r5_r14_lemhi_end_to_end_audit.py` and were
sanity-checked by hand on 2026-05-20.

**They are NOT validated against field data.** A real Lemhi
publication would need to compare these against, e.g., IDFG
electrofishing surveys at known discharges, USGS redd-count
surveys, or peer-reviewed prior WUA studies on Lemhi steelhead.
None of that comparison exists in this repo.

## How to advance U4 from prerequisite to evidence

Per [ROADMAP.md unfreeze gate U4](ROADMAP.md#how-to-unfreeze): "One
real basin case study published" closes U4. The Lemhi-specific path:

1. **Acquire real cross-section survey** — IDFG / Lemhi Watershed
   Council / USGS partner data. Replace
   `data/lemhi/cross_section.parquet` (currently synthetic).
2. **Acquire real mesh** — survey-based 1D or 2D mesh. Replace
   `data/lemhi/mesh.ugrid.nc` (currently synthetic 11-node mesh).
3. **Acquire field-data observations** — spawning redd counts by
   discharge, electrofishing density, snorkel survey use. Replace
   `data/lemhi/redd_count.parquet` and
   `data/lemhi/survey_campaign.parquet`.
4. **Run pipeline against real data** — same `Case.run` call,
   probably same case.yaml structure.
5. **Statistical comparison** — rank correlation between predicted
   WUA-Q peak Q and observed spawning peak Q; mean-bias check on
   absolute WUA where applicable.
6. **Submit for peer review** — write up as `docs/reviews/
   lemhi_real_basin_2026.md` (or similar). Reviewer-of-record on
   the regulatory-export half closes U5 in parallel.

**Steps 1–3 are external-data-acquisition work.** Steps 4–6 are
publication work, not Python development. The OpenLimno code side
does not need any further changes to support this — the pipeline
already runs.

## See also

- [`ROADMAP.md`](ROADMAP.md) — unfreeze gate definition
- [`SPEC.md`](../SPEC.md) — frozen 1.0 technical spec
- [`CAPABILITY_BOUNDARY_1_0.md`](governance/CAPABILITY_BOUNDARY_1_0.md) D6
  ("One real basin case study published")
- [`tests/integration/test_r5_r14_lemhi_end_to_end_audit.py`](../tests/integration/test_r5_r14_lemhi_end_to_end_audit.py)
  — pins the 7-artifact contract + Studio PNG
- [`data/lemhi/manifest.json`](../data/lemhi/manifest.json) —
  canonical real/synthetic classification of every Lemhi fixture
