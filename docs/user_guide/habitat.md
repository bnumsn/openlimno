# Habitat assessment

`openlimno.habitat` is the central module: HSI evaluation, WUA computation, multi-scale aggregation, drifting-egg, regulatory exports.

## HSI curves with built-in rigor

```python
from openlimno.habitat import HSICurve, load_hsi_from_parquet

curves = load_hsi_from_parquet("data/lemhi/hsi_curve.parquet")
curve = curves[("oncorhynchus_mykiss", "spawning", "depth")]
suit = curve.evaluate([0.3, 0.6, 1.0])     # array of suitabilities ∈ [0,1]
```

Every HSI curve carries:

- `category` — Bovee 1986 I (expert opinion), II (utilization), III (preference observation)
- `geographic_origin` — basin code; warns on cross-basin transfer
- `transferability_score` ∈ [0,1]
- `quality_grade` — A / B / C; results computed from C-grade are watermarked

See [Concepts § HSI rigor](../getting_started/concepts.md#hsi-rigor--hard-constraints-not-warnings) for rationale.

## WUA at three scales

```python
from openlimno.habitat import (
    cell_wua, composite_csi,
    classify_reach, aggregate_wua_by_hmu,
)
import numpy as np

# Per-section CSI from depth + velocity HSI
suits = {
    "d": curves[("oncorhynchus_mykiss", "spawning", "depth")].evaluate(depths),
    "v": curves[("oncorhynchus_mykiss", "spawning", "velocity")].evaluate(velocities),
}
csi = composite_csi(suits, method="geometric_mean")    # requires ack_independence in case YAML

# Cell-level
total_wua = cell_wua(csi, areas)

# HMU-level (Wadeson 1994 / Parasiewicz 2007)
labels = classify_reach(velocities, depths)             # riffle/run/pool/...
hmu_table = aggregate_wua_by_hmu(csi, areas, labels)
```

## End-to-end: case.run()

```python
from openlimno.case import Case

case = Case.from_yaml("examples/lemhi/case.yaml")
result = case.run(discharges_m3s=[1, 3, 5, 8, 12, 20])
print(result.wua_q)         # WUA-Q DataFrame
result.export(...)          # writes NetCDF/CSV to case `output.dir`
```

Output WUA-Q DataFrame columns: `discharge_m3s`, `wua_m2_<species>_<stage>`, ... — one column per species×stage combination in the case YAML.

## Drifting-egg evaluation

For pelagic-spawning species (e.g. Asian carps; SPEC §4.2.6):

```python
from openlimno.habitat import evaluate_drifting_egg, load_drifting_egg_params

params = load_drifting_egg_params(
    "data/lemhi/drifting_egg_params.parquet", "ctenopharyngodon_idella"
)
result = evaluate_drifting_egg(
    species="ctenopharyngodon_idella",
    spawning_station_m=0.0,
    velocity_along_reach=velocity_dict,        # station_m → m/s
    temperature_along_reach=temp_dict,         # station_m → °C
    hatch_temp_days_curve=params["hatch_temp_days_curve"],
    mortality_velocity_threshold_ms=params["mortality_velocity_threshold_ms"],
)
print(result.summary())
# → "ctenopharyngodon_idella: spawn at 0 m → hatch at 126 km, success=True"
```

Note: 1.0 requires user-supplied temperature forcing (CSV/NetCDF); thermal modelling lands in §13.5.

## Regulatory output

See [Regulatory export](regulatory_export.md).
