# EU Water Framework Directive (WFD) Reviewer-of-Record Evaluation Package

Status: draft for external review, 2026-05-26. This package supports
unfreeze gate U5 only; it does not claim U4 real-basin validation.
Companion to [SL/Z 712 package](sl712_review_package.md) and
[US-FERC §4(e) package](us_ferc_4e_review_package.md).

## Project Intro

OpenLimno is an open-source ecological-flow / fish-habitat decision
platform. Among its three regulatory export templates is the EU
Water Framework Directive (Directive 2000/60/EC) ecological-status
classification: a five-class output (`high` / `good` / `moderate` /
`poor` / `bad`) derived from a WUA-based Ecological Quality Ratio
(EQR) proxy.

This package asks a WFD practitioner — typically a national or
regional water authority hydroecologist familiar with the WFD
Common Implementation Strategy guidance documents — to review
the export template, not the scientific validity of the Lemhi-
fixture worked example. The exact reviewer-of-record charter is
per [`CAPABILITY_BOUNDARY_1_0.md`](CAPABILITY_BOUNDARY_1_0.md) § F.

## Artifact Under Review

Worked example: `examples/lemhi/out/lemhi_2024/eu_wfd.csv`,
generated from the audited Lemhi fixture run.

### Field schema

| Field | Type | Meaning |
|---|---|---|
| `month` | 1-12 | Calendar month |
| `monthly_avg_q_m3s` | float | Monthly mean discharge |
| `wua_at_monthly_q_m2` | float | WUA at the monthly mean discharge |
| `peak_wua_m2` | float | Maximum WUA across the discharge sweep (reference) |
| `eqr` | 0-1 | Ecological Quality Ratio = wua_at_monthly_q / peak_wua |
| `ecological_status` | enum {high, good, moderate, poor, bad} | WFD five-class classification |
| `quality_grade` | enum {A, B, C} | HSI evidence quality |

### Classification boundaries (configurable; defaults follow WFD CIS guidance)

| EQR range | Status |
|---|---|
| > 0.80 | high |
| 0.60 - 0.80 | good |
| 0.40 - 0.60 | moderate |
| 0.25 - 0.40 | poor |
| < 0.25 | bad |

These boundaries follow the [WFD CIS Guidance Document 13](https://circabc.europa.eu/sd/a/06480e87-27a6-41e6-b165-0581c2b046ad/Guidance%20doc%2013%20-%20Overall%20Approach%20Classification%20-%20Final.pdf)
recommended split (0.20 increments below "high", finer above)
but should be open to per-basin or per-Member-State override.

### Worked rows (Lemhi fixture)

```csv
# OpenLimno WUA — HSI quality grade B (transferred HSI per Bovee 1986)
# EQR = wua_at_monthly_q / peak_wua; ecological_status from WFD CIS 13 defaults
month,monthly_avg_q_m3s,wua_at_monthly_q_m2,peak_wua_m2,eqr,ecological_status,quality_grade
1,5.10,42.3,61.5,0.688,good,B
4,7.99,28.7,61.5,0.467,moderate,B
7,3.50,55.8,61.5,0.907,high,B
8,2.22,53.1,61.5,0.863,high,B
10,4.20,46.2,61.5,0.751,good,B
12,5.50,40.1,61.5,0.652,good,B
```

(Sample; full file has 12 rows.)

## Provenance Chain

Same `provenance.json` schema as the SL712 + FERC packages — see
those for the full field list. Key WFD-specific traceability:

- The EQR boundaries (high/good/moderate/poor/bad thresholds) MUST
  be recorded in the case.yaml + reflected in `provenance.json`
  so a reviewer can confirm which classification rule the
  ecological_status column was derived under.
- `quality_grade=B` should propagate consistently — the same B
  appears in wua_q.csv (the source) and in eu_wfd.csv (the
  classification).

## Quality Watermark

The CSV begins with `# OpenLimno WUA — HSI quality grade B`. WFD
review staff should treat B-grade outputs as "fit for surveillance
monitoring / preliminary classification" but NOT for binding
designation of heavily modified water bodies (HMWBs) — that
needs A-grade calibrated curves per WFD CIS 4 (Heavily Modified
Water Bodies guidance).

## Review Questions

Please affirm (yes / no / comment):

1. **Five-class structure**: The CSV has `ecological_status ∈
   {high, good, moderate, poor, bad}`. Is this the right
   discrete set for the WFD output template, or should there
   also be an "unknown" / "indeterminate" sentinel for cases
   where peak_wua is too small to give a meaningful EQR?
2. **Boundary defaults**: OpenLimno uses {0.80, 0.60, 0.40, 0.25}
   as the high/good/moderate/poor/bad thresholds per WFD CIS 13.
   Is this an acceptable cross-Member-State default, or does
   variability in implementation require an explicit
   `boundaries: ...` block in case.yaml with no default?
3. **EQR definition**: OpenLimno defines EQR as `wua_at_monthly_q
   / peak_wua`. This is a habitat-based proxy, not the canonical
   reference-condition / observed-condition ratio. Is the
   habitat-proxy framing acceptable for WFD review staff if
   clearly labeled (header banner), or should the export
   explicitly NOT use the term "EQR" if it deviates from the
   strict WFD definition?
4. **Reference-condition handling**: The current peak_wua-based
   reference is internal (highest WUA observed across the sweep).
   WFD canonical practice uses a reference-condition site or
   pre-disturbance baseline. Does OpenLimno need a
   `reference_wua_m2` case-yaml field to allow site-specific
   reference baselines?
5. **HMWB / Artificial water body designation**: WFD allows
   heavily-modified or artificial water bodies to use "good
   ecological potential" instead of "good ecological status".
   OpenLimno does not distinguish. Should the export gain an
   `eq_status_type ∈ {ecological_status, ecological_potential}`
   field, OR should it remain status-only and require external
   re-classification for HMWBs?
6. **Quality grade traceability**: Does the B-grade watermark
   provide sufficient HSI transferability disclosure for the
   classification's defensibility to a Member-State
   regulatory body?
7. **Provenance sufficiency**: Does the accompanying
   `provenance.json` (input SHA chain + parameter_fingerprint +
   classification thresholds) carry enough audit trail for a
   Member-State enforcement context?
8. **Overall**: Would you sign this template as fit for WFD-
   compliant export use, while reserving judgment on any
   basin-specific scientific claim AND any classification
   decision OpenLimno would produce from real data?

## Reviewer Signature

| Role | Name | Affiliation | Date | Signature |
|---|---|---|---|---|
| EU-WFD reviewer-of-record | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |

## Suggested institutional homes for review outreach

WFD practitioners with ecological-flow / habitat-assessment
expertise typically sit at:

- **German LAWA-Forschung** (Bund/Länder-Arbeitsgemeinschaft
  Wasser; the Federal/State WFD-implementation working group;
  hydroecology subgroup is the natural review home)
- **Cefas (UK Centre for Environment, Fisheries and Aquaculture
  Science)** — long history of WFD ecological-status reviews
  + IFIM practitioner community
- **EAWAG (Swiss Federal Institute of Aquatic Science)** —
  rivers division + WFD-equivalent Swiss federal practice
- **IRSTEA / INRAE (France)** — HABBY developers; familiar with
  the WFD habitat-based ecological-status path
- **VKI / Eurofins Miljø (Denmark / Nordic)** — water-quality
  + macroinvertebrate WFD compliance practice; would assess the
  fish-habitat-as-EQR-proxy framing critically
- **JRC Ispra (Joint Research Centre, EU Commission)** — WFD
  intercalibration exercise leadership; understands cross-MS
  comparability concerns
- **WWF European Freshwater Programme** — third-sector reviewer
  with WFD implementation critique experience

## See also

- [SL/Z 712 review package](sl712_review_package.md) — sister CN
  reviewer package
- [US-FERC §4(e) review package](us_ferc_4e_review_package.md) —
  sister US reviewer package
- [CAPABILITY_BOUNDARY_1_0.md](CAPABILITY_BOUNDARY_1_0.md) — D7
  reviewer-of-record requirement
- WFD CIS Guidance Documents (esp. #13 Overall Classification, #4
  HMWB, #20 Reference Conditions)
