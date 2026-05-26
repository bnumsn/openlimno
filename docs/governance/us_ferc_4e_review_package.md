# US FERC §4(e) Reviewer-of-Record Evaluation Package

Status: draft for external review, 2026-05-26. This package supports
unfreeze gate U5 only; it does not claim U4 real-basin validation.
Companion to [SL/Z 712 package](sl712_review_package.md) and
[EU-WFD package](eu_wfd_review_package.md).

## Project Intro

OpenLimno is an open-source ecological-flow / fish-habitat decision
platform that combines a Water Ecology Data Model (WEDM), built-in
1D hydraulics, habitat suitability indices, provenance hashing,
quality watermarks, and regulatory export templates including the
US Federal Energy Regulatory Commission Section 4(e) (FERC §4(e))
condition-setting format.

This package asks an experienced FERC §4(e) practitioner (or a
US hydroelectric-licensing reviewer familiar with the standard) to
review **the export template itself**, not the scientific validity
of the Lemhi-fixture worked example. The exact reviewer-of-record
charter is per [`CAPABILITY_BOUNDARY_1_0.md`](CAPABILITY_BOUNDARY_1_0.md)
§ F.

## Artifact Under Review

Worked example: `examples/lemhi/out/lemhi_2024/ferc_4e.csv`,
generated from the audited Lemhi fixture run. The fixture uses
real USGS 2024 discharge for gauge 13305000 + literature HSI
curves, but its geometry and survey observations are synthetic.
The output is therefore suitable for template review, not for
basin-evidence claims.

OpenLimno's FERC §4(e) emission is the **flow-regime-by-water-year-type**
contract from SPEC §4.2.4 — the reviewer assesses whether the
fields, units, and aggregation policy align with how a FERC §4(e)
licensing recommendation should be structured.

### Field schema (target review surface)

| Field | Unit | Meaning |
|---|---|---|
| `water_year_type` | enum {dry, normal, wet} | Drought / median / abundance year classification (FERC §4(e) convention) |
| `month` | 1-12 | Calendar month |
| `recommended_flow_m3s` | m³/s | OpenLimno-recommended ecological flow for this (water_year_type, month) cell |
| `monthly_avg_q_m3s` | m³/s | Historical monthly mean discharge for context |
| `wua_at_recommended_pct` | 0-100 | WUA at the recommended flow as % of the WUA peak (across the available discharge sweep) |
| `quality_grade` | enum {A, B, C} | HSI evidence quality (per SPEC §4.2.2.3 transferability rules) |

### Worked rows (Lemhi fixture)

```csv
# OpenLimno WUA — HSI quality grade B (transferred HSI per Bovee 1986)
# water_year_type definitions: dry = <30th percentile annual Q, ...
water_year_type,month,recommended_flow_m3s,monthly_avg_q_m3s,wua_at_recommended_pct,quality_grade
dry,1,3.0,5.10,52.4,B
dry,4,3.0,7.99,52.4,B
dry,8,3.0,2.22,87.1,B
normal,1,5.0,5.10,68.9,B
normal,4,5.0,7.99,68.9,B
normal,8,3.0,2.22,87.1,B
wet,1,8.0,5.10,55.2,B
wet,4,10.0,7.99,40.1,B
wet,8,5.0,2.22,38.7,B
```

(Sample. Full file has 36 rows: 3 water-year types × 12 months.)

## Provenance Chain

Excerpt from `examples/lemhi/out/lemhi_2024/provenance.json`:

```json
{
  "openlimno_version": "3.6.1",
  "wedm_version": "0.1",
  "case": {
    "name": "lemhi_phabsim_replication",
    "yaml_sha256": "632691212f5eea94bed5b8b8c072823bf19ab71be43b51ae92c69e0798c95768"
  },
  "git_sha": "...",
  "inputs": {
    "discharges_m3s": [3.0, 5.0, 8.0, 10.0, ...],
    "input_data_sha256": {
      "cross_section": "...",
      "hsi_curve": "..."
    }
  },
  "parameter_fingerprint": "...",
  "wua_quality_grade": "B"
}
```

## Quality Watermark

The CSV begins with `# OpenLimno WUA — HSI quality grade B`. B
means HSI curves are literature-transferred (per Bovee 1986
guidelines) rather than site-calibrated to this basin's
electrofishing data. B-grade is appropriate for licensing
RECOMMENDATIONS that explicitly disclose transferred-curve
provenance; A-grade requires site-calibrated curves; C-grade
is tentative only.

## Review Questions

Please affirm (yes / no / comment) on the following:

1. **Field semantics**: Do the 6 columns (water_year_type, month,
   recommended_flow_m3s, monthly_avg_q_m3s, wua_at_recommended_pct,
   quality_grade) cover the minimum a FERC §4(e) review staff
   member would expect to see in a flow-regime recommendation
   table?
2. **Water-year-type definition**: OpenLimno classifies water
   years by percentile of annual cumulative flow over a historical
   reference window. Is this the right convention vs. e.g.
   precipitation index, basin-specific Pacific Decadal Oscillation
   phase, or other regional standards?
3. **Recommended-flow methodology**: OpenLimno recommends the
   discharge at which WUA reaches the configured
   `target_wua_pct` (default 0.60) of peak WUA. Is this acceptable
   as a default decision rule for FERC §4(e) submission, or does
   FERC expect a different framing (e.g. minimum flow + suitable
   flow + maximum flow tuple instead of a single recommendation)?
4. **Quality-grade disclosure**: Does the B-grade watermark in the
   CSV header constitute sufficient HSI transferability
   disclosure for FERC §4(e) submission, or should the
   transferability statement be in the body / a sibling file?
5. **Traceability**: Does the accompanying `provenance.json`
   (case_yaml_sha256, input_data_sha256, parameter_fingerprint,
   git_sha) carry the audit-trail depth FERC review staff would
   need to reproduce or challenge a recommendation?
6. **Unit conventions**: m³/s for discharge is OpenLimno's
   internal unit. Should the export ALSO emit a cfs column
   alongside m³/s, or is units-in-header sufficient?
7. **Multi-species handling**: When the case has multiple
   species/life-stages, OpenLimno uses `composite=min` by default
   (most conservative; intersection over species WUA). Is that
   the right default for FERC §4(e) recommendations, or should
   the export include per-species rows instead?
8. **Overall**: Would you sign this template as fit for review
   use, while reserving judgment on any basin-specific scientific
   claim?

## Reviewer Signature

By signing, the reviewer affirms they reviewed the FERC §4(e)
export template only, not the scientific validity of the Lemhi
fixture basin.

| Role | Name | Affiliation | Date | Signature |
|---|---|---|---|---|
| US-FERC §4(e) reviewer-of-record | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |

A signed commit, scanned institutional letter, or signed PR review
on a `docs/governance/announcements/ferc_4e_review_response_*.md`
file all qualify.

## Suggested institutional homes for review outreach

US FERC Section 4(e) condition-setting reviewers usually sit at:

- USFS Pacific Southwest Research Station (where inSTREAM lineage
  research is based; Bret Harvey + Steve Railsback at Humboldt
  State / Cal Poly Humboldt)
- US Bureau of Reclamation Mid-Pacific Regional Office or
  Pacific Northwest Region (FERC license-condition practice)
- USFWS Region 1 Hydropower Group (ESA + FERC §4(e) statutory
  authority)
- Trout Unlimited Science Team (third-sector FERC §4(e)
  experience; willing third-party reviewers)
- Hydropower Research Foundation / EPRI Hydroelectric Research
  (institutional industry-side experience)
- PNNL Earth Systems Science Division
- HEC (Hydrologic Engineering Center, USACE) hydraulic /
  ecological flow group

## See also

- [SL/Z 712 review package](sl712_review_package.md) — sister CN
  reviewer package
- [EU-WFD review package](eu_wfd_review_package.md) — sister EU
  reviewer package
- [CAPABILITY_BOUNDARY_1_0.md](CAPABILITY_BOUNDARY_1_0.md) — D7
  reviewer-of-record requirement
- [Outreach letter](announcements/sl712_review_request_2026.md) —
  template for adapting to FERC reviewers
