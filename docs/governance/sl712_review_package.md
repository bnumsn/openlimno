# SL/Z 712-2014 Reviewer-of-Record Evaluation Package

Status: draft for external review, 2026-05-20. This package supports U5
only; it does not claim U4 real-basin validation.

## Project Intro / 项目简介

OpenLimno is an open-source instream-flow habitat assessment toolkit. It
combines a WEDM data model, built-in 1D hydraulics, habitat suitability
indices, provenance hashing, quality watermarks, and regulatory export
templates including CN SL/Z 712-2014.

OpenLimno 是一个开源河流生态流量与栖息地适宜性评估工具。项目包含 WEDM
数据模型、一维水动力计算、栖息地适宜性指数、可追溯哈希、质量等级水印，
以及包括 SL/Z 712-2014 在内的监管导出模板。

## Artifact Under Review

Worked example: `examples/lemhi/out/lemhi_2024/sl712.csv`, generated from
the audited Lemhi fixture run. The fixture uses real USGS 2024 discharge
for gauge `13305000` and literature HSI curves, but its geometry and
survey observations are synthetic. The output is therefore suitable for
template review, not for basin-evidence claims.

OpenLimno's SL/Z 712 four-tuple is emitted monthly:

| Field | Meaning |
|---|---|
| `min_eco_flow_m3s` | flow where WUA reaches `min_wua_pct * peak` |
| `suitable_eco_flow_m3s` | flow where WUA reaches `target_wua_pct * peak` |
| `multi_year_avg_pct` | suitable flow / annual average flow * 100 |
| `min_eco_flow_p90_m3s` | 10th percentile monthly flow, used as 90% guarantee minimum |

Example rows from the fixture export:

```csv
month,monthly_avg_q_m3s,min_eco_flow_m3s,suitable_eco_flow_m3s,multi_year_avg_pct,min_eco_flow_p90_m3s
1,5.095197109677419,3.0,3.0,58.66446363957208,4.813856
4,7.992888746666667,3.0,3.0,58.66446363957208,7.09902176
8,2.216109305806452,3.0,3.0,58.66446363957208,2.04730464
```

Header parameters:

```text
annual_avg_m3s=5.114
target_wua_pct=0.60
min_wua_pct=0.30
discharge_series_n=366
```

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
  "git_sha": "a415d158a87e8db2e5b9bc0069b9a202d6ff670a",
  "inputs": {
    "discharges_m3s": [3.0],
    "input_data_sha256": {
      "cross_section": "b6e69fdc2326fef3cb4be6ce74cb78d5b94686c92ef80eaec732e35fcc0c4ba1",
      "hsi_curve": "db4bcdb75c801513796b25fd99427a2caa9575516016833c045b5d05a4856c7b"
    }
  },
  "parameter_fingerprint": "e24819af4e7518cd8648b77700001be506a4a5ddeff6d6ee0a245a95bad7c991",
  "wua_quality_grade": "B"
}
```

## Quality Watermark

The CSV begins with `# OpenLimno WUA - HSI quality grade B`. In
OpenLimno, B-grade means the HSI curves are literature/neighboring-basin
transfers rather than site-calibrated curves. B-grade is publishable only
with disclosure; C-grade would be tentative and visibly watermarked.

## Review Questions

1. Does the four-tuple mapping above match the intended SL/Z 712-2014
   interpretation, especially the monthly minimum/suitable distinction?
2. Is the WUA-threshold method (`0.30 * peak`, `0.60 * peak`) acceptable
   as a default, or should OpenLimno expose different SL/Z 712 defaults?
3. Is `multi_year_avg_pct = suitable / annual_avg * 100` the right audit
   field for the template?
4. Is the 10th percentile monthly flow an acceptable representation of
   90% guarantee minimum in this export?
5. Is the B-grade HSI watermark sufficient disclosure for transferred HSI
   curves?
6. Does `provenance.json` carry enough audit trail for regulator review:
   software version, git SHA, input SHA, parameter fingerprint, and warnings?
7. What terminology should be changed to better match Chinese regulatory
   practice?
8. Would you sign this template as fit for review use, while reserving
   judgment on any basin-specific scientific claim?

## Reviewer-of-Record Signature

By signing, the reviewer affirms they reviewed the SL/Z 712 export
template only, not the scientific validity of the Lemhi fixture basin.

| Role | Name | Affiliation | Date | Signature |
|---|---|---|---|---|
| CN-SL712 reviewer-of-record | _TBD_ | _TBD_ | YYYY-MM-DD | _Pending_ |

Signed commit or scanned institutional letter may be attached under
`docs/governance/announcements/` and referenced from the row above.
