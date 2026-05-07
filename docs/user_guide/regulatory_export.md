# Regulatory export

Three output frameworks (SPEC §4.2.4.2, ADR-0009). Each takes a flow series + WUA-Q curve and renders the format required by its regulatory regime.

| Module | Framework | Output |
|---|---|---|
| `cn_sl712` | China《河湖生态流量计算规范》SL/Z 712-2014 | Monthly four-tuple |
| `us_ferc_4e` | US FERC 4(e) conditions, 18 CFR Part 4 | Flow regime by water-year type |
| `eu_wfd` | EU Water Framework Directive 2000/60/EC | Ecological status class |

## CN-SL712 four-tuple

```python
import pandas as pd
from openlimno.case import Case
from openlimno.habitat.regulatory_export import cn_sl712

case = Case.from_yaml("examples/lemhi/case.yaml")
result = case.run()
Q = pd.read_csv("data/lemhi/Q_2024.csv")

sl = cn_sl712.compute_sl712(
    Q, result.wua_q,
    species="oncorhynchus_mykiss", life_stage="spawning",
    target_wua_pct=0.6, min_wua_pct=0.3,
)
sl.to_csv("out/sl712.csv")
```

Output columns:
- `month` (1–12)
- `monthly_avg_q_m3s` — observed multi-year mean
- `min_eco_flow_m3s` — Q at 30% peak WUA
- `suitable_eco_flow_m3s` — Q at 60% peak WUA
- `multi_year_avg_pct` — suitable / annual avg × 100
- `min_eco_flow_p90_m3s` — 90% guarantee monthly minimum

## US-FERC-4e by water-year type

```python
from openlimno.habitat.regulatory_export import us_ferc_4e

ferc = us_ferc_4e.compute_ferc_4e(Q, result.wua_q,
                                  "oncorhynchus_mykiss", "spawning")
ferc.to_csv("out/ferc4e.csv")
```

Years are bucketed into wet (top 25%) / normal (middle 50%) / dry (bottom 25%) by total annual discharge, then monthly means computed within each bucket.

## EU-WFD ecological status

```python
from openlimno.habitat.regulatory_export import eu_wfd

wfd = eu_wfd.compute_wfd(Q, result.wua_q,
                        "oncorhynchus_mykiss", "spawning")
print(f"Status: {wfd.status} (EQR={wfd.eqr:.2f})")
wfd.to_csv("out/wfd.csv")
```

EQR thresholds (WFD CIS guidance):

| EQR | Status |
|---|---|
| ≥ 0.80 | high |
| ≥ 0.60 | good |
| ≥ 0.40 | moderate |
| ≥ 0.20 | poor |
| < 0.20 | bad |

## Important caveats

- 1.0 outputs are **template skeletons**. Final regulatory acceptance requires expert review at M2 (SPEC §14.3)
- US-FERC-4e does NOT yet include the ESA Section 7 biological opinion sub-template (M3)
- EU-WFD is a WUA-only proxy; full BQE (Biological Quality Elements) integration is M3
- China SL-712 four-tuple matches §5.2-5.4 of the standard but does not auto-render the official report PDF (manual finishing step)

## Custom thresholds

All three modules accept percentage thresholds; defaults match common practice. For example, to use 50% (instead of 60%) suitability:

```python
sl = cn_sl712.compute_sl712(Q, result.wua_q, "oncorhynchus_mykiss", "spawning",
                             target_wua_pct=0.5, min_wua_pct=0.25)
```
