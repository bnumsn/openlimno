# OpenLimno Fishtank — Technical Specification

> `openlimno.fishtank` — a mechanistic ODE + ABM model of a closed/semi-closed
> freshwater aquarium (a microcosm): nitrogen cycle, attached biofilm
> colonisation, dissolved oxygen, and optional Tier-2 carbonate/pH.

Status: **Implemented v0.4 (2026-05-29)** — Tier-1 core, Hour-3 events /
calibration, Hour-4 carbonate diagnostics, agent-based model, scenario IO,
CLI, provenance, browser Studio, 3D virtual tank, and course assets are shipped.
v0.2 fixed the dimensional / stoichiometric /
biofilm errors raised by the 2026-05-28 Codex pre-implementation review
(see `reviews/e0e77d1.codex-fishtank-spec.md`).
v0.4.1 (2026-06-02) fixed `calibration.fit()` silently dropping the scenario
event schedule, which biased fits against any log involving water changes or
feeding (see §10.3 + `reviews/8209f80`).
v0.5 (2026-06-02) added two keeper events (`wipe_biofilm`, `set_param`),
**implemented** the Tier-2 ODE extensions that earlier shipped only as
exercises — plant nitrogen uptake, denitrification, and **opt-in fully-coupled
pH** (DIC/Alk integrated, nitrification eats alkalinity, solved pH feeds back
into the rates) — and grew the scenario library from 5 to 16 typical aquarium
situations. All Tier-2 terms are off by default (`mu_plant=k_denit=couple_ph=0`),
so Tier-1 is byte-identical.

## 0. Scope and non-goals

### In scope (v0.1 teaching core)
- A single well-mixed tank (no spatial gradients — one CSTR compartment).
- Freshwater nitrogen cycle: TAN → NO₂ → NO₃ via two **attached** bacterial guilds.
- Dissolved-oxygen balance with reaeration + nitrification + respiration.
- Discrete keeper events: ammonia dosing (fishless cycle), feeding, water
  change, fish/plant addition, chemical dosing.
- Optional tiers (taught as extensions): carbonate/pH dynamics, plant
  nutrient uptake, denitrification, fish bioenergetics + mortality.
- Calibration of rate parameters against a measured aquarium log.
- Agent-based model (ABM) for fish individuals and attached AOB/NOB biofilm
  patches, used to compare individual/patch mechanisms with the ODE model.
- Local browser Studio with charts, ABM visualization, and a 3-D virtual tank.

### Out of scope (v0.1)
- Spatial structure (substrate depth gradients, flow fields).
- Marine/reef carbonate precipitation (non-equilibrium CaCO₃ kinetics — hard).
- Disease/pathogen dynamics.

### Design rule — teaching-first
When readability and generality conflict, readability wins: plain
dataclasses over ABCs, explicit named rate functions over plugin
registries, bundled data over live APIs, one process = one named function
with a docstring stating its **units**.

Modules are tagged **[core]** (taught in class, minimal) or **[release]**
(packaging/UI engineering, demoed not live-coded). The 4-hour course only
live-codes the [core] set; [release] modules ship pre-built.

## 1. State vector

The model state `y` is a fixed-order float vector. Dissolved concentrations
are mg/L; "mg-N/L" means milligrams of nitrogen per litre.

**Attached vs dissolved is the key distinction** (v0.2 correction):
nitrifying bacteria live as biofilm on filter media / surfaces, NOT
suspended in the water column. Their state is therefore **attached
biomass on a per-tank-volume basis** — a bookkeeping convention that keeps
the rate math per-litre while making the biofilm **immune to water-change
dilution** (§5). Dissolved species (TAN/NO₂/NO₃/DO) DO dilute on a water change.

| idx | symbol | meaning | unit | phase | dilutes on WC? |
|---|---|---|---|---|---|
| 0 | `TAN` | total ammonia N (NH₃+NH₄⁺) | mg-N/L | dissolved | yes |
| 1 | `NO2` | nitrite N | mg-N/L | dissolved | yes |
| 2 | `NO3` | nitrate N | mg-N/L | dissolved | yes |
| 3 | `X_AOB` | ammonia-oxidiser biomass | mg/L (attached, vol. basis) | attached | **no** |
| 4 | `X_NOB` | nitrite-oxidiser biomass | mg/L (attached, vol. basis) | attached | **no** |
| 5 | `DO` | dissolved oxygen | mg-O₂/L | dissolved | partial (toward tap value) |

`X` carrying capacity `X_max` (§6) is set by media surface area — a new,
under-colonised filter has tiny `X` and takes weeks to reach `X_max`
(this is *why* fishless cycling is slow; see §11).

**Tier-2 extension state** (implemented v0.5; appended after the Tier-1 core
in `state.STATE_ORDER`, all inert at the defaults so Tier-1 is unchanged):

| idx | symbol | meaning | unit | active when |
|---|---|---|---|---|
| 6 | `B_plant` | plant nitrogen pool | mg-N/L | `mu_plant>0` |
| 7 | `DIC` | dissolved inorganic carbon | mmol/L | `couple_ph>0` |
| 8 | `Alk` | carbonate alkalinity | meq/L | `couple_ph>0` |

`B_fish` (live fish biomass) is tracked only in the **agent-based model**
(`agent.py`), not in the ODE state — the ODE represents fish load through the
`feed`/`R_fish` forcing instead.

In **Tier-1, pH is a fixed scenario input** (constant), so `NH3_free`
(§2) is still computable. **With `couple_ph` on, pH is solved** each step from
(DIC, Alk, T): nitrification consumes Alk (2 H⁺/N ≈ 7.14 g-CaCO₃/g-N), the
falling pH throttles the nitrifiers via `nitrification_ph_factor`, and the
dynamic pH drives `NH3_free`. DIC is held constant (CO₂ gas exchange is out of
scope, §0).

## 2. Auxiliary (derived, not integrated)

| symbol | from | formula |
|---|---|---|
| `NH3_free` | TAN, pH, T | unionised fraction `f = 1/(1 + 10^(pKa(T)−pH))`, then `NH3_free = f·TAN` |
| `pKa(T)` | T (°C) | Emerson 1975: `pKa = 0.09018 + 2729.92/(T+273.15)` → 9.25 @ 25 °C |
| `DO_sat` | T, elevation | Benson–Krause / Weiss saturation |
| `pH` | input (Tier-1) / DIC,Alk,T (Tier-2) | §4.5 |
| `theta(T)` | T | Arrhenius `1.07^(T−20)` on all biological rates |

`NH3_free` is the toxic form; TAN can read "fine" while high pH makes free
NH₃ lethal — a key teaching point.

## 3. Process rates — units stated on every term

Define the dimensionless Monod factor `M(s,k) = s/(k+s)` (clipped to 0 for s≤0).
`θ = 1.07^(T−20)` (Arrhenius).

### 3.1 Two rate families — DO NOT confuse (v0.2 core correction)

For each bacterial guild there are **two distinct rates**:

- **Substrate (N) oxidation flux** ρ — the N that leaves the dissolved
  pool. Units **mg-N/L/day**. This is `growth / yield`:
  ```
  ρ1 = (μ_AOB / Y_AOB) · X_AOB · M(TAN, K_TAN) · M(DO, K_O_AOB) · θ      [mg-N/L/day]
  ρ2 = (μ_NOB / Y_NOB) · X_NOB · M(NO2, K_NO2) · M(DO, K_O_NOB) · θ      [mg-N/L/day]
  ```
- **Biomass growth rate** — the biofilm increase. Units **mg/L/day**.
  Equals `Y · ρ` (so the yield cancels back to `μ·X`):
  ```
  growth_AOB = Y_AOB · ρ1 = μ_AOB · X_AOB · M·M · θ                      [mg/L/day]
  growth_NOB = Y_NOB · ρ2 = μ_NOB · X_NOB · M·M · θ                      [mg/L/day]
  ```

Sanity: `μ` [1/day] × `X` [mg/L] = mg/L/day of **biomass**; dividing by
`Y` [mg-biomass per mg-N] converts to mg-N/L/day of **substrate** — the
correct unit to subtract from TAN. The v0.1 spec used `μX` directly as the
N flux, which was dimensionally a biomass rate (the bug Codex caught).

### 3.2 Excretion (TAN source from fish feeding)
```
E_TAN = 1000 · a_exc · F(t) / V     [mg-N/L/day]
```
`F(t)` = feeding rate [g food/day] (piecewise-constant between feed events,
§5), `a_exc ≈ 0.0276 g-N/g-food`, `V` = volume [L]. The `1000` is the g→mg
unit conversion (`a_exc·F/V` alone is g-N/L/day); the ABM applies it in
`agent.py`.

### 3.3 Biomass dynamics — with media carrying capacity
Logistic cap ties biofilm to finite media surface; first-order decay:
```
dX_AOB/dt = growth_AOB · (1 − X_AOB/X_AOB_max) − b_AOB · X_AOB           [mg/L/day]
dX_NOB/dt = growth_NOB · (1 − X_NOB/X_NOB_max) − b_NOB · X_NOB
```
`X_max` from media area (§6). The `(1−X/X_max)` factor produces the
colonisation S-curve: tiny seed → weeks of logistic growth → plateau.
Oxidation flux ρ is **not** capped (a mature filter keeps oxidising at full rate).

### 3.4 N sinks (Tier-2, implemented v0.5)
Plant uptake (`processes.plant_uptake`) — macrophytes/algae assimilate N,
preferring ammonium; logistic-capped at `B_plant_max`, decay mineralises back
to TAN (so dissolved + plant N is **conserved**):
```
base   = mu_plant · B_plant · (1 − B_plant/B_plant_max)
U_TAN  = base · M(TAN, K_plant_N)
U_NO3  = base · f_no3_pref · M(NO3, K_plant_N)         [mg-N/L/day]
dB_plant = (U_TAN + U_NO3) − b_plant·B_plant
```
Denitrification (`processes.denitrification_flux`) — first-order in nitrate,
O₂-**inhibited** (anoxic microsites); this nitrogen leaves as N₂ gas and is the
one process that genuinely breaks dissolved-N conservation:
```
r_denit = k_denit · NO3 · [K_O_denit/(K_O_denit + DO)]   [mg-N/L/day]
```
Both vanish at the defaults (`mu_plant=0`, `k_denit=0`). Light forcing is not
modelled (a teaching caveat — uptake is light-implicit).

### 3.5 Oxygen balance (v0.2 stoichiometry fix)
Mass-based O₂ demand of nitrification: **3.43 g-O₂/g-N** for NH₄-N→NO₂-N,
**1.14 g-O₂/g-N** for NO₂-N→NO₃-N, **4.57 g-O₂/g-N total**. (The "1.5/1.14"
in v0.1 mixed a molar ratio with mass fluxes — wrong.)
```
dDO/dt = k_a·(DO_sat − DO)        # reaeration (surface + filter)
         − 3.43·ρ1 − 1.14·ρ2       # nitrification O₂ demand (g-O₂/g-N × mg-N/L/day)
         − R_fish − R_hetero       # respiration
         + P_plant                 # photosynthesis (light-gated, Tier-2)
```

## 4. ODE system (Tier-1 = the Hour-2 build target)

```
dTAN/dt   =  E_TAN              − ρ1
dNO2/dt   =  ρ1                 − ρ2
dNO3/dt   =  ρ2                 (− U_plant − r_denit)        # sinks Tier-2
dX_AOB/dt =  Y_AOB·ρ1·(1−X_AOB/X_AOB_max) − b_AOB·X_AOB
dX_NOB/dt =  Y_NOB·ρ2·(1−X_NOB/X_NOB_max) − b_NOB·X_NOB
dDO/dt    =  k_a·(DO_sat−DO) − 3.43·ρ1 − 1.14·ρ2 − R_fish (+ P_plant)
```

In **Tier-1** (Hour 2): `U_plant = r_denit = P_plant = 0`, `R_fish` is a
constant, pH is a fixed input. The TAN source is a constant **ammonia dose**
(fishless cycle, §5) — NOT the fish/feeding event system, which is taught
in Hour 3. Students see the pure nitrification cascade.

### Nitrogen accounting (v0.2 conservation fix)
The dissolved-N pool `TAN+NO2+NO3` is **conserved** except for the
`E_TAN`/ammonia-dose source and the Tier-2 NO₃ sinks. The N assimilated
into bacterial biomass is **neglected** in Tier-1: with `Y_AOB≈0.15`
mg-VSS/mg-N and biomass ≈12% N, N-into-biomass per N-oxidised is ≈1.8% —
below measurement noise. §10's conservation test therefore checks the
**dissolved-N budget only**, with the ≈1.8% biomass-assimilation term
documented as the closure tolerance. (Tier-2 may add an explicit
assimilation sink `i_N_biomass·growth` for full closure as an exercise.)

### 4.1 Agent-based companion model

`agent.py` runs the same tank state variables with explicit agents:

- fish individuals: biomass, 3-D position, activity, stress, alive/dead state;
- AOB biofilm patches: attached biomass, media position, local activity factor;
- NOB biofilm patches: same patch structure, using NO₂ substrate kinetics.

At each ABM time step, fish feeding/excretion adds TAN, fish respiration
consumes DO, AOB patches oxidise TAN→NO₂, NOB patches oxidise NO₂→NO₃, and
events reuse the same `Event` semantics as the ODE solver. The ABM is seeded
and deterministic for reproducible teaching comparisons. It is not a spatial
CFD model; patch coordinates are teaching/visualization coordinates used to
make heterogeneity explicit.

**TAN source is additive in both models** (v0.4): total source = abiotic
`ammonia_dose` + feed-derived source. The ODE keeps `ammonia_dose` and
`feed_dose` as separate `Params` fields (a `feed` event sets `feed_dose`, it
does **not** overwrite the dose); the ABM sums `ammonia_dose` with per-fish
excretion scaled by the live-biomass fraction. So dosing and feeding add
rather than replace, and a dosed tank with fish stays comparable across both
models.

#### Known ABM↔ODE divergences (intentional Tier-1 simplifications)

These are documented teaching caveats, **not** bugs — they follow from the
Tier-1 scope (§0) and the ABM's explicit, stepped formulation:

- **Fish O₂ demand**: the ODE uses a constant `R_fish` (default 0); the ABM
  derives O₂ demand from live fish biomass. A stocked-tank ABM run can show a
  DO dip the ODE misses unless `R_fish` is set. Set `R_fish` in the scenario
  to align them.
- **pH**: fixed in both models' integration (Tier-1, §1). The carbonate pH
  crash is a **post-hoc ODE diagnostic** (`diagnostic_ph_trajectory`); the ABM
  has no live pH feedback, so at a fixed high pH it can over-stress fish that
  a falling pH would protect. Full DIC/Alk coupling is the Tier-2 exercise.
- **Event timing**: the ABM applies an event on the first step that reaches
  `event.day` (exact at the default `dt_days=0.25`; up to one step late at
  coarse `dt_days`). The ODE solver splits segments exactly at event days.
- **Per-step O₂ / substrate**: the ABM throttles nitrification by `M(DO)` but
  does not enforce a per-step O₂ budget, so very coarse `dt_days` can oxidise
  slightly more N than the step's oxygen supports. Keep `dt_days ≤ 0.25`.
- **Within-step ordering**: the ABM computes AOB then NOB fluxes sequentially
  within a step (NO₂ from AOB is available to NOB the same step); the ODE
  evaluates all fluxes simultaneously. A small, expected numerical difference.

### 4.5 Carbonate / pH (Tier-2, Hour 4 exercise)
pH from charge balance given (DIC, Alk, T), root-solved on [H⁺] ∈ bracket:
```
Alk = [HCO3⁻] + 2[CO3²⁻] + [OH⁻] − [H⁺]
[HCO3⁻],[CO3²⁻] = f(DIC,[H⁺],K1(T),K2(T))   →  solve [H⁺]  →  pH = −log10[H⁺]
```
Nitrification consumes **7.14 g CaCO₃ alkalinity per g-N** — so high feeding
→ nitrification → alkalinity drop → pH drop → NH₃-fraction shift. This closes
the toxicity loop and is the Hour-4 capstone.

**Two modes (v0.5):** by default this runs *diagnostically* (post-hoc on a
finished Tier-1 run, `carbonate.diagnostic_ph_trajectory`) — pH does not feed
back. With **`couple_ph>0`** it runs *fully coupled*: DIC/Alk are integrated
state (§1), Alk is consumed inside the RHS, pH is solved each step and throttles
nitrification (`nitrification_ph_factor`), so a crashing buffer self-limits the
cycle (nitrate plateaus instead of running away). The coupled mode was the
SPEC's deferred research step; it is now an opt-in capability, not the default.

## 5. Discrete events — solver segmentation

The continuous ODE is integrated **between** event times; at each event
boundary the solver stops, applies an instantaneous state map, and restarts
(see §7 `solver.py`). Within a segment, time-varying drivers (`F(t)`,
`light(t)`, ammonia dose) are **piecewise-constant**.

| event | effect on state |
|---|---|
| `ammonia_dose(rate_mg_n_l_day)` | sets a constant TAN source for the segment (fishless cycle; Hour 2) |
| `feed(amount_g, repeat_days)` | sets `F(t)` daily rate → drives `E_TAN` (Hour 3) |
| `water_change(fraction f)` | dissolved `c ← c·(1−f) + c_tap·f` for TAN/NO2/NO3/DO; **attached X unchanged** |
| `wipe_biofilm(fraction f)` | attached `X_AOB,X_NOB ← X·(1−f)`; **dissolved pool unchanged** — the mirror of a water change (washed media / medication) |
| `set_param(target, value)` | retargets one physical/forcing param (`k_a`, `DO_sat`, `temperature_c`, `R_fish`, `ph`) for the next segment — time-varying drivers (power outage, heat wave). Kinetic constants are not settable. |
| `dose(chemical,amount)` | bumps the relevant state (e.g. `Alk +=` for buffer dosing) |

`add_fish`/`add_plants` are not separate event kinds: fish load is set through
`feed`/`R_fish` and the ABM `fish_count`; plant biomass is seeded via the
`B_plant` initial state.

**Mechanics specified**: events sort by `(day, priority)`; same-day events
apply in priority order (water_change before feed before dose); `c_tap` is
a tap-water chemistry vector in the scenario; output segments are stitched
on a common `t_eval` grid; the solver uses `solve_ivp(method="LSODA",
max_step=0.25 day)` per segment to resolve fast transients.

## 6. Parameter table (aquarium-tuned defaults, 20 °C)

Kinetic FORMS are from the Activated Sludge Model (ASM1, Henze et al. 1987);
the **magnitudes here are re-scaled to aquarium biofilm**, NOT used raw from
wastewater (where suspended biomass is far denser). The colonisation
timescale is governed jointly by `X_seed`, `X_max`, `μ`, temperature, and
substrate — calibrate against an observed log (Hour 3; the course ships a
synthetic log with known truth, see §"Calibration target") rather than
trusting defaults blindly.

| param | symbol | default | unit | note |
|---|---|---|---|---|
| AOB max growth | `mu_AOB` | 0.55 | /day | aquarium biofilm, 20 °C (< ASM 0.77) |
| NOB max growth | `mu_NOB` | 0.40 | /day | NOB lag → nitrite spike persists |
| TAN half-sat | `K_TAN` | 1.0 | mg-N/L | |
| NO₂ half-sat | `K_NO2` | 1.3 | mg-N/L | |
| O₂ half-sat AOB | `K_O_AOB` | 0.50 | mg-O₂/L | |
| O₂ half-sat NOB | `K_O_NOB` | 0.68 | mg-O₂/L | NOB more O₂-sensitive |
| AOB yield | `Y_AOB` | 0.15 | mg/mg-N | |
| NOB yield | `Y_NOB` | 0.041 | mg/mg-N | |
| AOB decay | `b_AOB` | 0.10 | /day | |
| NOB decay | `b_NOB` | 0.10 | /day | |
| AOB seed | `X_AOB_seed` | 0.02 | mg/L | tiny inoculum → weeks-long cycle |
| NOB seed | `X_NOB_seed` | 0.02 | mg/L | |
| AOB capacity | `X_AOB_max` | `1000·c_media·media_area_m2/V` (≈5.0) | mg/L | media-limited |
| NOB capacity | `X_NOB_max` | `1000·c_media·media_area_m2/V` (≈5.0) | mg/L | |
| media biomass dens. | `c_media` | 0.5 | g/m² | per m² filter media (×1000 → mg/L) |
| media area | `media_area_m2` | 1.0 | m² | filter+surfaces |
| reaeration | `k_a` | 2.0 | /day | filter-dependent |
| Arrhenius θ | `theta` | 1.07 | — | per °C from 20 |
| N per food | `a_exc` | 0.0276 | g-N/g-food | 9.2 %N × 30 % excreted |
| O₂ demand step1 | — | 3.43 | g-O₂/g-N | NH₄-N→NO₂-N |
| O₂ demand step2 | — | 1.14 | g-O₂/g-N | NO₂-N→NO₃-N |
| alk consumed | — | 7.14 | g-CaCO₃/g-N | Tier-2 pH |

Defaults are tuned to produce a **3–6 week** fishless cycle (the real
range, §11). All overridable per-scenario.

## 7. Module contracts

| module | tag | holds | exposes |
|---|---|---|---|
| `state.py` | core | `Chemistry`, `Params` dataclasses | `.to_vector()/.from_vector()`, `nh3_free_fraction()` |
| `processes.py` | core | (stateless) | `monod()`, `oxidation_fluxes()`, `derivatives(t,y,p)`, `plant_uptake()`, `denitrification_flux()`, `effective_ph()`, `nitrification_ph_factor()` |
| `solver.py` | core | (stateless) | `simulate(chemistry, params, days, schedule)->Result`: segment loop over events + `solve_ivp` |
| `events.py` | core | `Event`, `EventSchedule`, `TapWater` | `apply_event(chemistry, params, event, tap)` |
| `agent.py` | core | `FishAgent`, `MicrobePatch` | `simulate_agent_based_model(scenario)->dict`: seeded ABM over fish individuals + AOB/NOB patches |
| `library.py` | core | static dicts | `default_params()`, `species()`, `equipment()`, `tap_water()`, `scenarios()`/`scenario_payload()` (typical-case library, §8) |
| `calibration.py` | core | (stateless) | `align(sim,obs)`, `rmse()`, `fit(observation, chemistry, base_params, schedule)->CalibrationResult` |
| `io.py` | release | (stateless) | `load_scenario/write_scenario`, `read_observation`, `write_result` + `provenance.json` |
| `studio.py` / `studio_http.py` | release | local browser Studio + ABM Agents + 3D virtual tank | `run_app()`, `run_fishtank_studio()` |
| `cli.py` | release | click | `python -m openlimno.fishtank ...`, `openlimno fishtank ...`, `fishtank ...` |

`derivatives(t,y,p)` is the pedagogical heart — the whole model dynamics
readable in one ~30-line function.

## 8. Scenario YAML schema (draft)

```yaml
fishtank_version: "0.2"
tank: {volume_l: 120.0, temperature_c: 25.0, elevation_m: 50.0, ph: 7.4}   # ph fixed in Tier-1
chemistry:                       # initial conditions
  tan_mg_n_l: 0.0
  no2_mg_n_l: 0.0
  no3_mg_n_l: 5.0
  x_aob_mg_l: 0.02               # tiny seed
  x_nob_mg_l: 0.02
  do_mg_l: 7.5
media: {area_m2: 1.0}
run: {days: 42, dt_output_hours: 6, seed: 20260528, tier: 1}
agents: {seed: 42, dt_days: 0.25, fish_count: 6, fish_biomass_g: 4.0, feed_g_day: 0.3, aob_agents: 36, nob_agents: 36}
events:
  - {day: 0, type: ammonia_dose, rate_mg_n_l_day: 2.0}    # fishless cycle source (Hour 2)
  - {day: 14, type: water_change, fraction: 0.25, repeat_days: 7}
tap_water: {tan_mg_n_l: 0.0, no2_mg_n_l: 0.0, no3_mg_n_l: 5.0, do_mg_l: 8.5}
parameters: {}                   # optional overrides of library defaults
profile_uri: ""                  # optional fitted-parameter file
```

### 8.1 Typical-scenario library

`library.scenarios()` ships one coherent payload per typical aquarium
situation; the Studio's **Preset** dropdown (GET `/api/scenarios`) and
`examples/fishtank/*.yaml` are generated from it. Each payload is coherent for
**both** the ODE and ABM panels — the binding constraint is that a fishless
nitrogen spike is lethal, so a single payload cannot show *both* an instructive
ammonia spike *and* surviving fish. Therefore fish-in scenarios drive nitrogen
through `feed` events (the ODE folds food into an equivalent ammonia dose; the
ABM converts it to per-fish excretion scaled by the live fraction — so as ABM
fish die its nitrate falls below the ODE's, a deliberate teaching contrast),
abiotic fishless cycles use `ammonia_dose`, and stocked tanks meant to survive
start from an established biofilm.

The library has **16** scenarios (v0.5): the 5 nitrogen-cycle lifecycle cases,
4 operations/failure modes exercising the new events, and 4 Tier-2 ecology
cases (the rest below). Every preset has a matching `examples/fishtank/*.yaml`.

| scenario | teaching point |
|---|---|
| `fishless_cycle` (default) | classic TAN→NO₂→NO₃ cascade; no fish at risk |
| `seeded_instant_cycle` | mature seeded media suppresses the spike |
| `fish_in_disaster` | fish stocked into an uncycled tank → ammonia toxicity, mass mortality |
| `mature_stocked_tank` | established filter + moderate feeding + weekly water changes → all fish survive |
| `old_tank_syndrome` | low-alkalinity heavy load → carbonate buffer exhausted → pH crash (diagnostic) |
| `low_oxygen` | under-aeration (`k_a`↓) → O₂-limited nitrification stalls (NO₃ ~6.6 not ~88) |
| `staged_stocking` | feeding ramped in steps → biofilm keeps pace, free NH₃ stays safe |
| `nitrate_control` | weekly water changes export nitrate (~45 vs ~88) |
| `filter_crash` | `wipe_biofilm` (washed media / medication) → ammonia rebound then recolonise |
| `power_outage` | `set_param k_a` blackout then restore → DO crashes and recovers |
| `heat_wave` | `set_param temperature_c` 25→32 before the TAN peak → free-NH₃ peak rises (~0.14→0.20) |
| `overfeeding` | thin biofilm + heavy feed → ammonia/oxygen stress |
| `planted_tank` | plant uptake on → N sink draws nitrate down (partial); plants grow |
| `denitrification_substrate` | `k_denit` on, low O₂ → NO₃→N₂ removed (~5 vs ~38) |
| `ph_crash_coupled` | `couple_ph` on → pH self-limits nitrification (NO₃ ~13 vs ~184 diagnostic) |
| `buffer_dosing` | `dose→Alk` weekly holds the buffer → nitrification sustained (NO₃ ~30) |

## 9. Output contract

`simulate()` returns a `Result`:
- `timeseries`: DataFrame [day, TAN, NO2, NO3, X_AOB, X_NOB, DO, NH3_free, pH]
  (pH is the fixed input in Tier-1, solved in Tier-2)
- `events_log`: DataFrame showing which events fired when, plus before/after
  dissolved state and TAN-source values
- `warnings`: e.g. "NH3_free > 0.05 mg/L (chronic fish stress) on day 3"
- `provenance`: scenario hash (when loaded from YAML), parameter fingerprint,
  git sha, machine metadata, output summary, and warning list

Toxicity flags (literature): free NH₃ > 0.05 mg/L = chronic stress;
NO₂ > 0.5 mg-N/L = "brown blood"; NO₃ > 50 = water-change due.

## 10. Validation strategy

1. **Dissolved-N conservation**: total dissolved N (TAN+NO2+NO3) budget
   closes to within the documented ≈1.8% biomass-assimilation tolerance
   between events; sources = ammonia dose + feeding, sinks = plant uptake
   + denitrification + water change. Unit test asserts this.
2. **Qualitative pattern**: a fishless-cycle run reproduces the textbook
   "ammonia spike → nitrite spike (lagged, NOB slower) → nitrate
   accumulation" sequence over **3–6 weeks**.
3. **Calibration target**: fit `mu_AOB, mu_NOB` (most-sensitive params) to a
   bundled **synthetic teaching log** (generated from known truth
   `mu_AOB=0.62 / mu_NOB=0.35` + noise, so calibration can be checked against
   ground truth); report RMSE. Logs in `data/aquarium_logs/`.
   **`fit()` replays the scenario's `EventSchedule`** (water changes, feeding,
   dose changes) inside the objective simulation (v0.4 fix): a real aquarium
   log is produced under keeper actions, so omitting them aligns an event-free
   run against event-affected observations and silently biases the fit. The
   `fishtank calibrate --scenario` CLI threads `scenario.schedule` through;
   `schedule=None` defaults to an event-free run (correct only for a steady
   fishless cycle). Unit test asserts recovery of the generating params **with**
   the schedule and a degraded fit without it.
4. **Sensitivity**: ±10% OAT on each param; rank by effect on day-30 NO₃.

## 11. Why fishless cycling takes weeks (teaching note)

The lag is **not** a model artefact to tune away — it is the lesson. Cycling
is slow because the biofilm starts as a tiny inoculum (`X_seed` ≈ 0.02 mg/L)
and grows logistically toward a media-limited `X_max`. Early on, ρ ∝ X is
near-zero, so TAN accumulates; only after AOB colonise (~1 week) does TAN
fall (peak ~day 7) and NO₂ rise; NOB lag further (lower `μ_NOB`), so NO₂
peaks later (~day 15) and stays elevated into week 3. With the default
parameters the cascade resolves in roughly **3–4 weeks**; lowering the
seed, temperature, or media area pushes it toward the upper 6-week end.
NO₃ accumulates throughout. Seeding from an established filter (raising
`X_seed`) is exactly how hobbyists "instant-cycle" — a parameter the model
exposes. **The course must NOT present a "few-day" cycle** (a v0.1 error).

## 12. Relationship to OpenLimno

- **Reuses**: scenario-YAML + provenance pattern; calibration grid/ABC
  harness; browser-Studio HTTP pattern; (future) `openlimno.ibm`
  bioenergetics for a fish-growth tier.
- **Distinct**: single well-mixed compartment (no GIS/cells), continuous
  ODE (not daily-step IBM), hobby-facing not regulatory.
- **Namespace**: `openlimno.fishtank.*` — one repo, two scales
  (`limno` = open waters/macrocosm; `fishtank` = closed microcosm).

## See also
- [`README.md`](./README.md) — module overview and quick start.
- ASM1: Henze, M. et al. (1987) *Activated Sludge Model No. 1*, IWA.
- Emerson, K. et al. (1975) ammonia pKa(T), *J. Fish. Res. Board Can.*
- 2026-05-28 Codex pre-implementation review: `reviews/e0e77d1.codex-fishtank-spec.md`.
