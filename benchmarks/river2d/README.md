# River2D equivalence — Lemhi standard case

> 3.x research route. v2.2.0 ships the contract; the actual binary
> run is staged for v3.x once the licensing + cross-platform path is
> reproducible in CI.

## Goal

Reproduce the River2D depth × velocity × WUA results on the
Lemhi River case (Steffler & Blackburn 2002) and assert OpenLimno's
output is within **5%** relative error per (discharge, species, stage)
cell.

## Reference platform

* **River2D 0.95** — Windows-only Fortran/C++ binary, downloadable
  from the University of Alberta archive
  ([river2d.ualberta.ca](https://river2d.ualberta.ca/)).
* Free of charge for research and education; not redistributed by
  OpenLimno (each user pulls their own copy).
* Linux/macOS reproduction requires Wine or a Windows VM. v3.x will
  build a containerised reproducible-Wine harness once the v2.2 GUI
  / v3.x research-route SPEC stabilises.

## Adapter status

* `benchmarks/river2d/adapter.py` — v2.2.0 stub. Implements the
  :class:`ModelAdapter` contract from ``benchmarks._compare`` and
  returns ``is_available() = False`` on every host (no River2D
  binary available).
* The adapter contract surface is stable for v3.x: feed it the
  Lemhi case YAML, it returns a :class:`ReferenceResult` with the
  same WUA-Q DataFrame schema OpenLimno emits.

## Acceptance threshold

`acceptance.yaml`:

```yaml
threshold:
  max_abs_m2: 50.0     # absolute WUA difference, m²
  max_rel: 0.05        # 5% relative error per cell
```

These thresholds are looser than the PHABSIM closed-form benchmark
(`1e-3`) because River2D is a numerical 2-D model with its own
discretisation error against analytic solutions.

## What v3.x adds

* Containerised River2D-under-Wine harness (`benchmarks/river2d/
  docker/`).
* Real Lemhi `River2D.r2d` input file matched to the existing
  OpenLimno `examples/lemhi/case.yaml`.
* CI hook that runs the benchmark on tagged releases (skipped on
  PR runs to keep CI under 5 minutes).
