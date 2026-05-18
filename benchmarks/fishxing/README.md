# FishXing equivalence — fish-passage velocity-time-distance

> 3.x research route. v2.2.0 ships the contract; FishXing 3.0 is a
> JVM application from USDA Forest Service Stream Systems Technology
> Center, no longer actively maintained but still distributable.

## Goal

For the same culvert / fish-passage configuration, reproduce
FishXing's velocity-time-distance (VTD) decision tables and assert
OpenLimno's `passage` module output is within **5%** relative error
on the burst-prolonged-sustained swim-speed boundaries.

This is complementary to the WUA/IFIM line — FishXing answers
"can this fish traverse this culvert at this discharge?" while the
HABBY/PHABSIM/River2D family answers "how much usable habitat at
this discharge?". The 3.x research route includes both.

## Reference platform

* **FishXing 3.0** — JVM application; last released 2006. Source +
  installer available from
  [fsl.orst.edu/geowater/FX3](https://www.fsl.orst.edu/geowater/FX3/).
* No active maintenance; OpenLimno's adapter target is the *file
  format* (Excel-based reports) rather than a live binary run. The
  v3.x bridge will parse archived FishXing output files (.fx3 +
  derived .xls) and compare against OpenLimno passage outputs on
  matched configurations.

## Adapter status

* `benchmarks/fishxing/adapter.py` — v2.2.0 stub. ``is_available()``
  checks for a ``FISHXING_REPORT_DIR`` environment variable. ``run``
  raises ``NotImplementedError`` (real parser is v3.x).

## Acceptance threshold

`acceptance.yaml`:

```yaml
threshold:
  max_abs_m_per_s: 0.05      # 5 cm/s on velocity boundaries
  max_rel: 0.05               # 5% relative
```

Note: thresholds are on velocity rather than WUA m² — FishXing's
output domain is fish-passage criteria, not habitat-area. The
:class:`WUAComparison` returned by the harness has its
``platform_b`` set to ``"fishxing"`` so consumers can branch on the
domain (velocity vs WUA) by adapter identity.

## What v3.x adds

* `benchmarks/fishxing/parser.py` — reads archived `.fx3` reports
  into :class:`benchmarks._compare.ReferenceResult`.
* A curated fixture of 5 — 10 canonical FishXing test cases (culvert
  geometries + species + life-stage combinations) with archived
  reference outputs checked into the repo.
* CI hook on tagged releases (skipped on PR).
