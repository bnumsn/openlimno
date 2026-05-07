# Quickstart: Lemhi River WUA-Q

This walkthrough takes ~30 seconds. It loads the sample Lemhi River case, sweeps a range of flows, and produces a WUA-Q curve PNG.

## Build the sample data

```bash
python tools/build_lemhi_dataset.py
```

This fetches USGS gauge 13305000 (Lemhi River near Lemhi, ID) daily discharge for 2024 and writes the WEDM data package under `data/lemhi/` (mesh, cross-sections, HSI curves, swimming performance, drift-egg parameters, ~14 files).

## Inspect the case

```bash
openlimno validate examples/lemhi/case.yaml
```

Should print `✓ examples/lemhi/case.yaml validates against WEDM 0.1`.

## Run end-to-end

```bash
openlimno run examples/lemhi/case.yaml
```

Outputs land in `examples/lemhi/out/lemhi_2024/`:
- `wua_q.csv` — WUA per species/stage at each Q
- `hydraulics.nc` — depth/velocity per (Q, station) NetCDF
- `provenance.json` — git SHA, machine, input hashes
- `sl712.csv` — China SL/Z 712-2014 four-tuple ecological flow recommendation

## Plot

```bash
python examples/lemhi/quickstart.py
```

Produces `wua_q_curve.png`:

```
WUA peaks ~7 m³/s at 65 m² for steelhead spawning;
fry curve drops out at high Q (depths exceed fry preference).
```

This is the canonical PHABSIM unimodal WUA-Q shape.

## Compute regulatory output

```python
import pandas as pd
from openlimno.case import Case
from openlimno.habitat.regulatory_export import cn_sl712, us_ferc_4e, eu_wfd

case = Case.from_yaml("examples/lemhi/case.yaml")
result = case.run()
Q = pd.read_csv("data/lemhi/Q_2024.csv")

# China SL/Z 712-2014 four-tuple
sl = cn_sl712.compute_sl712(Q, result.wua_q,
                            "oncorhynchus_mykiss", "spawning")
sl.to_csv("out/sl712.csv")

# US FERC 4(e) by water-year type
ferc = us_ferc_4e.compute_ferc_4e(Q, result.wua_q,
                                  "oncorhynchus_mykiss", "spawning")
ferc.to_csv("out/ferc.csv")

# EU WFD ecological status class
wfd = eu_wfd.compute_wfd(Q, result.wua_q,
                        "oncorhynchus_mykiss", "spawning")
print(f"WFD status: {wfd.status} (EQR={wfd.eqr:.2f})")
```

## Calibrate Manning's n

```bash
openlimno calibrate examples/lemhi/case.yaml \
    --observed data/lemhi/rating_curve.parquet
```

## Next

- [Core concepts](concepts.md): WEDM, HSI rigor, IFIM five steps
- [User guide](../user_guide/index.md): each module in depth
- [SPEC](../SPEC.md): the full design contract
