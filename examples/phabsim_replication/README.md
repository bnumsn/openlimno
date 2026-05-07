# PHABSIM (Bovee 1997) Replication Example

Reproduces the canonical USFWS PHABSIM regression case as a runnable
end-to-end OpenLimno workflow: a 6-section uniform prismatic reach with
stylised steelhead spawning HSI curves where Manning normal depth and
WUA both have closed-form analytic solutions.

The same case is enforced by `benchmarks/phabsim_bovee1997` on every PR
(SPEC §7).

## Layout

```
examples/phabsim_replication/
├── README.md
├── build_data.py     # writes data/ from first principles
├── case.yaml         # OpenLimno case YAML
├── quickstart.py     # build + run + analytic check
└── data/             # populated by build_data.py
    ├── cross_section.parquet
    ├── hsi_curve.parquet
    ├── species.parquet
    ├── life_stage.parquet
    └── expected_wua.json
```

## Run

```bash
# 1. Build the deterministic dataset
python examples/phabsim_replication/build_data.py

# 2. Run via the CLI
PYTHONPATH=src openlimno run examples/phabsim_replication/case.yaml

# 3. Or run the all-in-one quickstart that includes the analytic check
PYTHONPATH=src python examples/phabsim_replication/quickstart.py
```

## What it asserts

For each of `Q ∈ {0.5, 1.5, 4.0, 8.0}` m³/s:

| | |
|---|---|
| Manning normal depth | Solved iteratively from `Q = (1/n)·A·R^(2/3)·S^(1/2)` |
| Section velocity | `u = Q / (b·h)` |
| Suitability | Linear interpolation against Bovee 1978 spawning curves |
| Composite | Geometric mean (with `acknowledge_independence: true`) |
| WUA | Sum of `csi · wetted_area` over 6 sections |

The analytic value is in `data/expected_wua.json`; the benchmark requires
`|ol - analytic| / analytic ≤ 1e-3` table-level (ADR-0009).
