# OpenLimno Fishtank — Technical Specification

> `openlimno.fishtank` — a mechanistic ODE model of a closed/semi-closed
> freshwater aquarium (a microcosm). Doubles as the worked example for a
> 4-hour Master's "Aquatic Ecology Models" lab. See
> [`COURSE_PLAN.md`](./COURSE_PLAN.md) for the teaching schedule.

Status: **DRAFT v0.1 (2026-05-28)** — design document, pre-implementation.

## 0. Scope and non-goals

### In scope (v0.1)
- A single well-mixed tank (no spatial gradients — one CSTR compartment).
- Freshwater nitrogen cycle: TAN → NO₂ → NO₃ via two bacterial guilds.
- Dissolved-oxygen balance with reaeration + biological demand.
- Discrete keeper events: feeding, water change, fish addition, dosing.
- Optional tiers (taught as extensions): carbonate/pH system, plant
  nutrient uptake, fish bioenergetics + mortality.
- Calibration of rate parameters against a measured aquarium log.

### Out of scope (v0.1)
- Spatial structure (substrate depth gradients, flow fields).
- Marine/reef carbonate precipitation (acknowledged hard — see the
  Reef2Reef community discussion; non-equilibrium CaCO₃ kinetics).
- Disease/pathogen dynamics.
- 3-D rendering / game-like visuals.

### Design rule
This is a **teaching-first** codebase. When readability and generality
conflict, readability wins: plain dataclasses over ABCs, explicit rate
functions over plugin registries, bundled data over live APIs, one
process = one named function with a docstring stating its units.

## 1. State vector

The model state `y` is a fixed-order float vector. Concentrations are
mg/L unless noted; "mg-N/L" means milligrams of nitrogen per litre.

| index | symbol | meaning | unit | typical range |
|---|---|---|---|---|
| 0 | `TAN` | total ammonia nitrogen (NH₃ + NH₄⁺) | mg-N/L | 0 – 8 |
| 1 | `NO2` | nitrite nitrogen | mg-N/L | 0 – 15 |
| 2 | `NO3` | nitrate nitrogen | mg-N/L | 0 – 80 |
| 3 | `X_AOB` | ammonia-oxidising bacteria biomass | mg/L | 0 – 50 |
| 4 | `X_NOB` | nitrite-oxidising bacteria biomass | mg/L | 0 – 50 |
| 5 | `DO` | dissolved oxygen | mg-O₂/L | 0 – 9 |

**Tier-2 extension state** (taught in Hour 4, optional):

| index | symbol | meaning | unit |
|---|---|---|---|
| 6 | `DIC` | dissolved inorganic carbon | mmol/L |
| 7 | `Alk` | carbonate alkalinity | meq/L |
| 8 | `B_fish` | total live fish biomass | g |
| 9 | `B_plant` | total plant biomass | g |

pH is **derived** from (DIC, Alk, T) by solving the carbonate equilibrium,
not integrated — see §4.5.

## 2. Auxiliary (derived, not integrated) quantities

| symbol | from | formula sketch |
|---|---|---|
| `NH3_free` | TAN, pH, T | fraction of TAN that is un-ionised NH₃ (the toxic form): `f = 1/(1 + 10^(pKa−pH))`, pKa(T) ≈ 9.25 at 25 °C |
| `DO_sat` | T, elevation | oxygen saturation (Benson–Krause / Weiss) |
| `pH` | DIC, Alk, T | carbonate equilibrium (Tier-2) |
| `theta(T)` | T | Arrhenius temperature factor `1.07^(T−20)` applied to all biological rates |

`NH3_free` matters because fish toxicity tracks free NH₃, not TAN — a key
teaching point (TAN can look "fine" but high pH makes it lethal).

## 3. Process rates

All rates are per-litre per-day unless noted. `θ = 1.07^(T−20)` multiplies
every biological rate (Arrhenius, standard in wastewater ASM models).

### 3.1 Ammonia excretion (source of TAN)
Fish convert fed protein to ammonia. Tie excretion to feeding for the
teaching tier:
```
E_TAN = a_exc · F(t) / V
```
- `F(t)` = feeding rate [g food/day] from the event schedule
- `a_exc` ≈ 0.092 · 0.30 ≈ 0.0276 g-N per g-food (≈9.2% N in food,
  ~30% excreted as TAN within a day; rest is growth/feces)
- `V` = tank volume [L]

### 3.2 Nitrification step 1 (AOB): TAN → NO₂
Double-Monod (substrate + oxygen), Arrhenius-corrected:
```
r1 = θ · μ_AOB · X_AOB · [TAN/(K_TAN + TAN)] · [DO/(K_O_AOB + DO)]
```

### 3.3 Nitrification step 2 (NOB): NO₂ → NO₃
```
r2 = θ · μ_NOB · X_NOB · [NO2/(K_NO2 + NO2)] · [DO/(K_O_NOB + DO)]
```

### 3.4 Bacterial growth and decay
Biomass grows on the substrate it oxidises, with first-order decay:
```
dX_AOB/dt = Y_AOB · r1 − b_AOB · X_AOB
dX_NOB/dt = Y_NOB · r2 − b_NOB · X_NOB
```

### 3.5 Plant / denitrification sinks for NO₃ (Tier-2)
```
U_plant   = θ · v_plant · B_plant · [NO3/(K_NO3 + NO3)] · light(t)
r_denit   = θ · k_denit · [NO3/(K_NO3d + NO3)] · [K_O_inh/(K_O_inh + DO)]
```
Denitrification is O₂-inhibited — only meaningful in low-O₂ pockets;
small in a well-aerated tank (a teaching caveat about model assumptions).

### 3.6 Oxygen balance
```
dDO/dt = k_a · (DO_sat − DO)        # surface + filter reaeration
         − 1.5 · r1 − 1.14 · r2      # O₂ consumed per g-N nitrified
         − R_fish − R_hetero          # fish + heterotroph respiration
         + P_plant                    # plant photosynthesis (light-gated)
```
Stoichiometry: 3.43 g-O₂/g-N for full nitrification, split ≈1.5 (step 1)
+ 1.14 (step 2) per the standard nitrification O₂ demand.

## 4. ODE system (Tier-1, the Hour-2 build target)

```
dTAN/dt   =  E_TAN              − r1
dNO2/dt   =  r1                 − r2
dNO3/dt   =  r2                 − U_plant − r_denit
dX_AOB/dt =  Y_AOB·r1           − b_AOB·X_AOB
dX_NOB/dt =  Y_NOB·r2           − b_NOB·X_NOB
dDO/dt    =  k_a·(DO_sat−DO) − 1.5·r1 − 1.14·r2 − R_fish + P_plant
```

In Tier-1 (Hour 2) `U_plant = r_denit = P_plant = 0` and `R_fish` is a
constant — students see the pure nitrification cascade. Each later hour
switches one of these on.

### 4.5 Carbonate / pH (Tier-2, Hour 4 exercise)
pH is found by root-solving the charge balance given (DIC, Alk, T):
```
Alk = [HCO3⁻] + 2[CO3²⁻] + [OH⁻] − [H⁺]
[HCO3⁻], [CO3²⁻] = f(DIC, [H⁺], K1(T), K2(T))
→ solve for [H⁺], pH = −log10[H⁺]
```
Nitrification consumes alkalinity (7.14 g CaCO₃ per g-N) — a real reason
hobby tanks crash pH. This closes the loop: high feeding → nitrification
→ alkalinity drop → pH drop → NH₃ fraction shifts. Great teaching arc.

## 5. Discrete events

Events fire at scheduled times and apply an instantaneous map to the
state (the solver stops, applies, restarts):

| event | effect |
|---|---|
| `feed(amount_g)` | sets `F(t)` pulse for the day → drives `E_TAN` |
| `water_change(fraction)` | `c ← c·(1−f) + c_tap·f` for every dissolved species; biofilm `X` unchanged (lives on media) |
| `add_fish(species, n, length)` | increases `B_fish`, raises baseline excretion |
| `dose(chemical, amount)` | bumps the relevant state (e.g. `Alk += ...` for buffer) |
| `add_plants(species, mass)` | increases `B_plant` |

## 6. Parameter table (defaults, 20 °C)

Heritage: nitrification kinetics from the Activated Sludge Model (ASM1,
Henze et al. 1987) adapted to aquarium scale; toxicity thresholds from
hobby + aquaculture literature.

| param | symbol | default | unit | source note |
|---|---|---|---|---|
| AOB max growth | `mu_AOB` | 0.77 | /day | Nitrosomonas, 20 °C |
| NOB max growth | `mu_NOB` | 0.78 | /day | Nitrobacter |
| TAN half-sat | `K_TAN` | 1.0 | mg-N/L | |
| NO₂ half-sat | `K_NO2` | 1.3 | mg-N/L | |
| O₂ half-sat (AOB) | `K_O_AOB` | 0.50 | mg-O₂/L | |
| O₂ half-sat (NOB) | `K_O_NOB` | 0.68 | mg-O₂/L | NOB more O₂-sensitive |
| AOB yield | `Y_AOB` | 0.15 | mg/mg-N | |
| NOB yield | `Y_NOB` | 0.041 | mg/mg-N | |
| AOB decay | `b_AOB` | 0.10 | /day | |
| NOB decay | `b_NOB` | 0.10 | /day | |
| reaeration | `k_a` | 2.0 | /day | filter-dependent |
| Arrhenius θ | `theta` | 1.07 | — | per °C from 20 |
| N per food | `a_exc` | 0.0276 | g-N/g-food | 9.2% N × 30% excreted |
| NH₃ pKa(25 °C) | `pKa` | 9.25 | — | for NH3_free fraction |

All defaults live in `library.py` and are overridable per-scenario.

## 7. Module contracts

| module | holds | exposes | reset/serialise |
|---|---|---|---|
| `state.py` | `Tank`, `Chemistry`, `Biota` dataclasses | `.to_vector()`, `.from_vector()` | dataclass → dict → JSON |
| `processes.py` | (stateless) | `excretion()`, `nitrify_aob()`, `nitrify_nob()`, `oxygen_balance()`, `derivatives(t, y, params)` | pure functions |
| `solver.py` | (stateless) | `simulate(scenario) -> Result` wrapping `scipy.integrate.solve_ivp` + event handling | — |
| `events.py` | `EventSchedule` | `apply(state, event)`, `due(t)` | list of typed events |
| `io.py` | (stateless) | `load_scenario(yaml)`, `write_scenario`, `read_observation(csv)`, `write_result(csv)` + `provenance.json` | — |
| `library.py` | static dicts | `default_params()`, `species(name)`, `equipment(name)`, `tap_water(profile)` | — |
| `studio.py` | HTTP/Streamlit app | `run_app()` → sliders + plots | — |
| `cli.py` | argparse/click | `fishtank run / validate / calibrate / studio` | — |

`derivatives(t, y, params)` is the single function the solver calls; every
process function feeds into it. This is the pedagogical heart — students
can read the entire model dynamics in one ~30-line function.

## 8. Scenario YAML schema (draft)

```yaml
fishtank_version: "0.1"
tank:
  volume_l: 120.0
  temperature_c: 25.0
  elevation_m: 50.0
chemistry:                 # initial conditions
  tan_mg_n_l: 0.0
  no2_mg_n_l: 0.0
  no3_mg_n_l: 5.0
  x_aob_mg_l: 0.1          # tiny seed bacteria
  x_nob_mg_l: 0.1
  do_mg_l: 7.5
biota:
  fish:
    - species: "zebra_danio"
      number: 8
      length_mm: 35
  plants:
    - species: "vallisneria"
      mass_g: 40
run:
  days: 45
  dt_output_hours: 6
  seed: 20260528
events:
  - day: 0   ; type: add_fish ; species: zebra_danio ; n: 8 ; length_mm: 35
  - day: 0   ; type: feed     ; amount_g: 0.5 ; repeat_days: 1
  - day: 7   ; type: water_change ; fraction: 0.25 ; repeat_days: 7
parameters:                # optional overrides of library defaults
  mu_AOB: 0.77
profile_uri: ""            # optional path to a fitted parameter file
```

## 9. Output contract

`simulate()` returns a `Result` with:
- `timeseries`: DataFrame [day, TAN, NO2, NO3, X_AOB, X_NOB, DO, NH3_free, pH]
- `events_log`: which events fired when
- `warnings`: e.g. "NH3_free exceeded 0.05 mg/L (fish stress) on day 3"
- `provenance`: scenario hash + parameter fingerprint + git sha + library version

Toxicity flags use literature thresholds (free NH₃ > 0.05 mg/L = chronic
stress, NO₂ > 0.5 mg-N/L = "brown blood", NO₃ > 50 = water-change due).

## 10. Validation strategy

1. **Conservation check**: total N (TAN+NO2+NO3 + bound-in-biomass) is
   conserved between events (sources = feeding, sinks = plant uptake +
   denitrification + water change). A unit test asserts the N budget
   closes to < 0.1% between events.
2. **Qualitative pattern**: a fishless-cycle run must reproduce the
   textbook "ammonia spike → nitrite spike (lagged) → nitrate
   accumulation" sequence.
3. **Calibration target**: fit `mu_AOB`, `mu_NOB` to a bundled real
   aquarium log; report RMSE. Bundled logs live in `data/aquarium_logs/`.
4. **Sensitivity**: ±10% one-at-a-time on each parameter; rank by effect
   on day-30 NO₃ (the regulatory-equivalent output for a tank).

## 11. Relationship to OpenLimno

- **Reuses**: scenario-YAML + provenance.json pattern; the
  cohort/population idea from the IBM (`B_fish` could later become an
  individual-based fish module sharing `openlimno.ibm` bioenergetics);
  the browser-Studio HTTP pattern; the calibration ABC/grid harness.
- **Distinct**: single well-mixed compartment (no GIS/cells), continuous
  ODE (not daily-step IBM), hobby-facing not regulatory.
- **Namespace**: `openlimno.fishtank.*` — one repo, two scales
  (`limno` = open waters / macrocosm; `fishtank` = closed microcosm).

## See also
- [`COURSE_PLAN.md`](./COURSE_PLAN.md) — the 4-hour teaching schedule.
- ASM1: Henze, M. et al. (1987) *Activated Sludge Model No. 1*, IWA.
- inSTREAM 7 bioenergetics (already in `openlimno.ibm`) for the future
  fish-growth tier.
