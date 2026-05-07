# Hydrodynamics

`openlimno.hydro` provides two backends:

- **`Builtin1D`** — in-house Saint-Venant 1D (M1 MANSQ + M2 standard step), per ADR-0003
- **`SCHISMAdapter`** — subprocess wrapper for SCHISM 2D (M3), per ADR-0002

Both implement the `HydroSolver` Protocol (`prepare`, `run`, `read_results`). 1.0 deliberately does not adopt BMI (ADR-0004).

## Builtin1D — Manning normal depth (M1)

For PHABSIM/MANSQ-equivalent analyses: per-section steady-state Manning normal depth.

```python
from openlimno.hydro.builtin_1d import Builtin1D, load_sections_from_parquet

sections = load_sections_from_parquet("data/lemhi/cross_section.parquet",
                                       manning_n=0.035)
solver = Builtin1D(slope=0.002)
results = solver.solve_reach(sections, discharge_m3s=5.0)
for r in results:
    print(f"{r.station_m:6.0f} m  d={r.depth_mean_m:.2f}  u={r.velocity_mean_ms:.2f}")
```

## Builtin1D — standard-step backwater (M2)

For PHABSIM/IFG4-equivalent: backwater profile from a downstream-known WSE.

```python
results = solver.solve_standard_step(
    sections,
    discharge_m3s=5.0,
    downstream_wse_m=1500.5,   # known WSE at last section (e.g. rating curve)
)
```

## SCHISMAdapter — 2D via subprocess (M3)

```python
from openlimno.hydro import SCHISMAdapter

adapter = SCHISMAdapter(
    container_image="ghcr.io/openlimno/schism:5.11.0",
    container_runtime="docker",
    n_procs=4,
    timeout_s=3600,
)

work = adapter.prepare("examples/lemhi/case.yaml", work_dir="/tmp/run1/")
report = adapter.run(work)
print(f"return_code={report.return_code}, log={report.log_path}")
ds = adapter.read_results(work)        # xarray.Dataset
```

For CI / dev environments without SCHISM:

```python
report = adapter.run(work, dry_run=True)
```

## Validation

| Benchmark | Path | Expected |
|---|---|---|
| Bovee 1997 PHABSIM | `benchmarks/phabsim_bovee1997/` | WUA ≤ 1e-3 abs/rel |
| MMS 1D uniform | `benchmarks/mms/` | < 1e-3 at all N |
| Toro Riemann placeholder | `benchmarks/toro/` | Geometry self-consistency |
| Lemhi end-to-end | `tests/integration/test_lemhi_end_to_end.py` | Unimodal WUA-Q |
