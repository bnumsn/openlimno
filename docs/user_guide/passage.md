# Fish passage

`openlimno.passage` computes culvert / fishway passage success rate (η_P), with explicit user input for attraction efficiency (η_A) per ADR-0007.

## Why the η_A vs η_P split

FishXing returns a binary pass/fail answer. The literature (Castro-Santos 2005, Bunt 2012, Silva 2018) shows total passage efficiency is the product of two independent ecological processes:

- **η_A** — attraction: probability fish reaches the entrance. Often 0.3–0.7 in real culverts. **NOT** 1.0.
- **η_P** — passage: probability of transit given entry. Hydraulics + swimming.

OpenLimno 1.0 computes η_P only and requires the user to declare η_A in case config. Composing η = η_A × η_P is the user's choice.

## Quick example

```python
from openlimno.passage import (
    Culvert, load_swimming_model_from_parquet, passage_success_rate,
)

cv = Culvert(
    length_m=18, diameter_or_width_m=1.2, slope_percent=1.5,
    material="corrugated_metal", shape="circular",
)
swim = load_swimming_model_from_parquet(
    "data/lemhi/swimming_performance.parquet",
    species="oncorhynchus_mykiss", stage="juvenile",
)

# Deterministic
res = passage_success_rate(cv, swim, discharge_m3s=0.3, temp_C=12.0)
print(res.summary())
# → Q=0.30 m3/s  V_barrel=1.53 m/s  V_fish_burst=1.44 m/s  eta_P=0.300

# Monte Carlo (default in 1.0)
res_mc = passage_success_rate(cv, swim, discharge_m3s=0.3,
                              monte_carlo=1000, seed=42)
print(f"η_P = {res_mc.eta_P:.3f} ± {res_mc.monte_carlo_std:.3f}")
```

## Composing total passage with user-supplied η_A

```yaml
passage:
  culvert: { ... }
  species: oncorhynchus_mykiss
  attraction_efficiency:
    value: 0.6                    # USER MUST PROVIDE
    source: "Site survey 2023, 60% of tagged fish approached entrance"
    note: "η_A = 1.0 assumes perfect entrance; empirical 0.3-0.7 more realistic"
  monte_carlo:
    n: 1000
    seed: 42
```

```python
import yaml
case_cfg = yaml.safe_load(open("case.yaml"))
eta_A = case_cfg["passage"]["attraction_efficiency"]["value"]
eta_total = eta_A * res.eta_P
```

## Swim model details

Three swim bands (Bell 1986):

| Band | Time scale | Default speed |
|---|---|---|
| burst | < 20 s | ~10 BL/s |
| prolonged | 20 s – 200 min | ~4 BL/s |
| sustained | > 200 min | ~2 BL/s |

Temperature dependence is built into the loaded `SwimmingModel`. Selection of which band applies is driven by the culvert length divided by speed.

## Roadmap (§13.18)

- η_A modeling from 2D entrance hydraulics + sensory field
- IBM micro fish trajectories (§13.9) for individual passage simulation
- Complex fishways: vertical-slot, weir-and-pool, Denil, nature-like
