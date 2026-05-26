# IBM Redesign: Beyond inSTREAM

OpenLimno's IBM track should become a modern, auditable population-response
workbench for river fish, benchmarked against inSTREAM / InSALMO but not limited
by NetLogo-era architecture. The current native engine is a useful prototype:
it already has fish individuals, daily light phases, habitat-cell choice,
growth, mortality, spawning, redd development, recruitment, multi-reach state,
and inSTREAM 7 input crosswalks. The redesign turns that prototype into a
versioned scenario system with explicit biological profiles, calibration
reports, uncertainty analysis, and optional high-performance execution.

The public claim remains conservative: research-grade until the scientific
gates close. The technical target is ambitious: exceed inSTREAM as a workflow,
validation, reproducibility, and extensibility platform.

## Evidence Baseline

inSTREAM is the right reference platform because it remains the most mature
open individual-based stream salmonid model. Current inSTREAM 7 represents
fish, reaches, habitat cells, and redds; uses dawn/day/dusk/night phases; and
drives fish behavior from flow, depth, velocity, cover, temperature, turbidity,
and food availability. Its core model target is the growth-risk tradeoff that
links individual behavior to population abundance, biomass, persistence, and
multi-species outcomes.

Reference sources:

- inSTREAM 7 paper, Railsback, Ayllón, Harvey 2021:
  https://research.fs.usda.gov/treesearch/62884
- Cal Poly Humboldt inSTREAM / InSALMO overview:
  https://www.humboldt.edu/ecological-modeling/instream-and-insalmo/instream-and-insalmo-overview
- inSTREAM 7 user manual:
  https://www.humboldt.edu/sites/default/files/ecological-modeling/2024-09/instream73userman2023-07-07.pdf
- inSTREAM / InSALMO 7.4 release note, 2026:
  https://www.humboldt.edu/ecological-modeling/news/new-releases-instream-and-insalmo
- ODD protocol update for ABM / IBM documentation:
  https://www.jasss.org/23/2/7.html
- ABC calibration guidance for agent-based models:
  https://www.sciencedirect.com/science/article/pii/S1364815223002918
- Ecological-model calibration, sensitivity, and uncertainty review:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC13110421/
- FLAME GPU large-scale ABM execution reference:
  https://developer.nvidia.com/blog/fast-large-scale-agent-based-simulations-on-nvidia-gpus-with-flame-gpu/

## Product Position

OpenLimno IBM should not be "inSTREAM rewritten in Python." It should be:

- an inSTREAM-compatible workbench for users who need continuity;
- a transparent scientific-modeling system for users who need audit trails;
- a calibration and uncertainty platform for researchers;
- a bridge from hydraulic model outputs to population response;
- a local-first desktop tool, not a cloud service;
- a native runtime that can support CPU execution now and optional acceleration
  later.

The workflow should exceed inSTREAM in five areas:

1. Reproducibility: every run is defined by one scenario file, versioned
   profiles, input hashes, random seeds, and a run manifest.
2. Calibration: native-vs-reference comparisons produce machine-readable
   objective metrics and profile patches.
3. Uncertainty: ensembles, sensitivity analysis, and posterior-like calibration
   outputs become first-class artifacts.
4. Interoperability: HEC-RAS, SCHISM, TELEMAC, MIKE, HABBY, NetCDF/UGRID,
   Parquet, and inSTREAM exchange all feed the same habitat-cell contract.
5. Extensibility: behavior submodels are replaceable modules, documented with
   ODD-style metadata and tested in isolation.

## Capability Comparison

| Capability | inSTREAM / InSALMO baseline | OpenLimno target |
|---|---|---|
| Platform | NetLogo model files | Python package + CLI + local Studio |
| Main objects | Reach, habitat cell, fish, redd | Same, plus scenario/profile/manifest/calibration objects |
| Time | Four light phases per day | Four phases by default; configurable phase calendar |
| Habitat forcing | Flow lookup tables and habitat cells | Hydraulic-cell tables from OpenLimno interop stack |
| Fish behavior | Growth-risk habitat selection | Pluggable decision policies: inSTREAM-compatible, DEB-inspired, risk-sensitive |
| Energetics | Salmonid bioenergetics formulas | Profile-backed bioenergetics; optional DEB-style module |
| Mortality | Predation, temperature, hydraulic and lifecycle risks | Same plus explicit uncertainty priors and event attribution |
| Reproduction | Redds, egg survival, emergence | Same plus provenance, calibration, and species-profile evidence labels |
| Multi-species | Supported | Supported via profile registry and multi-species scenario contract |
| Calibration | Manual / BehaviorSpace-style workflows | Objective functions, ABC / simulation-based calibration, reports |
| UQ | User-managed runs | Built-in ensemble, Sobol/Morris screening, posterior summaries |
| Validation | Literature and example models | inSTREAM parity gates + real basin gates + signed calibration reports |
| Reproducibility | NetLogo project and input files | Scenario + profile + input hashes + manifest + deterministic seeds |
| Performance | NetLogo runtime | Pandas/NumPy now; optional vectorized/JAX/Numba backend later |

## Design Goals

### Scientific Goals

- Retain inSTREAM's core ecological insight: individual fish make adaptive
  tradeoffs between growth opportunity and mortality risk.
- Add formal model documentation using ODD-style model metadata: purpose, state
  variables, process overview, scheduling, design concepts, initialization,
  inputs, and submodels.
- Make every behavioral parameter traceable to one of four evidence levels:
  default, literature-derived, calibrated, or expert-edited.
- Support multiple observed patterns for calibration, not just one target
  series: abundance, biomass, size distribution, reach occupancy, redd count,
  recruitment timing, and persistence.
- Keep failure visible. A model that cannot match a reference pattern should
  produce a failed report, not a broad tolerance that hides the mismatch.

### Engineering Goals

- One scenario file should be enough to run and reproduce an IBM job.
- Species profiles should be versioned files, not implicit Python defaults.
- Submodels should be small, typed, and independently testable.
- Outputs should use the same provenance discipline as `Case.run`.
- Studio should edit scenario/profile artifacts rather than maintaining a
  separate hidden UI state.
- Existing `run_native_ibm(...)` users should not break during migration.

### Product Goals

- Make the first screen useful to ecologists: load scenario, inspect profile,
  run deterministic preview, run stochastic ensemble, compare to reference.
- Make calibration defensible to reviewers: every changed parameter must appear
  in a report with prior bounds, accepted value, objective metric, and evidence
  status.
- Make inSTREAM users comfortable: support official example input crosswalks,
  NetLogo BriefPop summaries, and side-by-side reports.

## Target Architecture

```
openlimno.ibm
  schema/
    ibm_scenario.schema.json
    species_profile.schema.json
    calibration_report.schema.json

  profiles/
    presets/
      rainbow_trout.instream7.yaml
      brown_trout.instream7.yaml
      chinook_insalmo.yaml

  state.py
    FishState
    ReddState
    CellState
    ReachState
    IBMEvent
    IBMRunManifest

  forcing.py
    load_habitat_forcing(...)
    validate_time_indexed_cells(...)
    hash_forcing_inputs(...)

  population.py
    load_initial_population(...)
    build_initial_population(...)
    validate_population(...)

  profiles.py
    SpeciesProfile
    load_species_profile(...)
    write_species_profile(...)
    validate_species_profile(...)
    evidence_labels(...)

  submodels/
    habitat_selection.py
      GrowthRiskPolicy
      TerritoryDensityPolicy
      InSTREAMCompatiblePolicy
    growth.py
      BioenergeticGrowth
      DEBInspiredGrowth
    mortality.py
      MortalityRiskModel
      EventAttributedMortality
    movement.py
      SameReachMovement
      OrderedReachMovement
      NetworkMovement
    spawning.py
      ReddPlacement
      FecundityModel
    redds.py
      EggDevelopment
      DewateringScourSurvival

  engine.py
    run_ibm_scenario(...)
    run_native_ibm(...)        # compatibility facade

  calibration.py
    compare_reference(...)
    objective_metrics(...)
    calibrate_profile(...)
    write_calibration_report(...)

  ensemble.py
    run_ensemble(...)
    sensitivity_screen(...)
    summarize_uncertainty(...)

  instream7.py
    official input parser, NetLogo reference runner, BriefPop comparison

  studio.py
    local scenario/profile editor and visual runner
```

## Data Contracts

### IBM Scenario

```yaml
ibm_version: "0.2"

scenario:
  id: lemhi-trout-baseline
  description: Baseline rainbow trout population response run.
  days: 365
  start_day: 1
  start_year: 2026
  seed: 42
  stochastic: true
  light_phases: [dawn, day, dusk, night]

profile:
  uri: profiles/rainbow_trout.instream7.yaml

forcing:
  habitat_cells: data/habitat_cells.parquet
  time_index_column: time_index
  required_columns:
    - cell_id
    - area_m2
    - depth_m
    - velocity_ms
    - csi
    - temperature_c
    - turbidity_ntu
    - hiding_cover
    - feeding_cover
    - spawning_cover

population:
  initial_population: data/initial_fish.parquet
  default_species: rainbow_trout

submodels:
  habitat_selection: native-habitat-utility-v0
  growth: native-bioenergetic-growth-v0
  mortality: native-risk-survival-v0
  movement: native-adjacent-reach-movement-v0
  spawning: native-redd-recruitment-v0

experiments:
  ensemble:
    seeds: [1, 2, 3, 4, 5]
  calibration:
    observed: data/observed_population.csv
    objective: rmse_abundance
    parameters:
      base_daily_survival: [0.990, 0.995, 1.000]
      predation_base_risk: [0.000, 0.003, 0.006]

outputs:
  dir: out/ibm
  formats: [csv, parquet]
  individual_history: false
  manifest: true
```

### Species Profile

```yaml
profile_version: "0.2"
species:
  id: rainbow_trout
  scientific_name: Oncorhynchus mykiss
  common_name: Rainbow trout
  evidence_status: calibrated-reference

growth:
  model: bioenergetic
  weight_a_g_per_cm_b: 0.0115
  weight_b: 3.0
  max_consumption_fraction:
    value: 0.018
    evidence: instream7-mapped

mortality:
  base_daily_survival:
    value: 0.997
    prior: [0.990, 1.000]
    evidence: calibrated
  predation_base_risk:
    value: 0.006
    prior: [0.000, 0.050]
    evidence: expert-default

movement:
  same_reach_required: true
  cross_reach_movement_rate:
    value: 0.0
    prior: [0.0, 0.5]
    evidence: uncalibrated-default

calibration:
  reference_platform: inSTREAM 7.4 / NetLogo 7
  reference_artifacts: []
  accepted: false
  notes: Longer reference outputs required before equivalence claims.
```

### Run Manifest

Every run should write `ibm_run_manifest.json`:

```json
{
  "openlimno_version": "3.6.1",
  "ibm_version": "0.2",
  "scenario_sha256": "...",
  "profile_sha256": "...",
  "forcing_sha256": "...",
  "initial_population_sha256": "...",
  "seed": 42,
  "stochastic": true,
  "submodels": {
    "habitat_selection": "native-habitat-utility-v0",
    "growth": "native-bioenergetic-growth-v0",
    "mortality": "native-risk-survival-v0",
    "movement": "native-adjacent-reach-movement-v0",
    "spawning": "native-redd-recruitment-v0"
  },
  "outputs": {
    "native_ibm_population_summary.csv": {"rows": 366, "sha256": "..."},
    "native_ibm_final_individuals.csv": {"rows": 120, "sha256": "..."},
    "native_ibm_cell_use.csv": {"rows": 1400, "sha256": "..."},
    "native_ibm_events.csv": {"rows": 12, "sha256": "..."},
    "native_ibm_redds.csv": {"rows": 3, "sha256": "..."}
  }
}
```

## Scientific Model Design

### 1. Habitat Selection

Baseline policy: inSTREAM-compatible growth-risk utility.

Utility should combine:

- expected growth / net energy;
- mortality risk;
- density competition / territorial pressure;
- same-reach or network movement constraints;
- light-phase-specific feeding and predation weights;
- cover, turbidity, temperature, depth, velocity, and optional food supply.

Beyond inSTREAM target:

- support policy alternatives without rewriting the engine;
- record selected cell and decision components per phase for audit runs;
- allow pattern-oriented evaluation of whether fish occupy plausible cells, not
  just whether total abundance matches.

### 2. Growth

Phase 1 keeps the current bioenergetic model and makes it explicit in profile
files.

Phase 2 adds a DEB-inspired growth option:

- reserve / structure state;
- assimilation, maintenance, growth, maturation, and reproduction allocation;
- temperature correction;
- species-specific priors and calibration bounds.

The DEB-inspired model should be optional until calibrated. It is included to
support modern physiological ecology, not to complicate default runs.

### 3. Mortality

Mortality should be event-attributed:

- baseline mortality;
- predation exposure;
- thermal stress;
- hydraulic stress;
- dewatering / stranding if flow slices support it;
- optional disease or angling hooks for research scenarios.

Outputs should report both deaths and dominant risk attribution so a user can
see why a scenario failed.

### 4. Movement

Movement tiers:

1. Cell choice inside current reach.
2. Ordered adjacent reach movement.
3. Network movement over a graph of reaches with barriers, passage
   probabilities, temperature refuges, and seasonal migration windows.

The graph tier is the main route to exceed inSTREAM for basin-scale OpenLimno
cases because it connects passage, thermal refuge, and habitat suitability into
one population-response workflow.

### 5. Spawning And Redds

Keep explicit redd state:

- spawning season and maturity;
- fecundity and female fraction;
- redd placement preference;
- egg survival;
- degree-day development;
- emergence timing.

Add evidence labels and calibration bounds for each reproduction parameter.
Long-term acceptance must include recruitment timing and redd count, not only
adult abundance.

### 6. Multi-Species

The engine should support multiple species profiles in one scenario:

- separate behavior profiles;
- shared cell resources and density competition;
- optional predation or competition interactions;
- population summaries by species, reach, and cohort.

Default implementation can run independent species first. Coupled interactions
should be gated behind explicit scenario flags.

## Calibration And Uncertainty

### Calibration Targets

A reference comparison should support multiple pattern groups:

- abundance by day / season;
- biomass by reach / species;
- mean length and length distribution;
- reach occupancy;
- cell-use distribution;
- redd count and emergence timing;
- persistence probability across multi-year ensembles.

### Objective Metrics

Each metric should produce:

- observed/reference value;
- native value;
- absolute error;
- relative error where meaningful;
- tolerance;
- pass/fail;
- weight in the objective function.

### Calibration Methods

Phase 1:

- deterministic grid / Latin hypercube search over a small parameter set;
- report best profile patch and objective table.

Phase 2:

- ABC-style simulation-based calibration for stochastic IBM outputs;
- posterior-like accepted parameter sets;
- parameter identifiability warnings.

Phase 3:

- surrogate-assisted calibration for expensive runs;
- optional differentiable / vectorized backend experiments.

The calibration system must never silently overwrite source profiles. It writes
`profile.calibrated.yaml` plus `ibm_calibration_report.csv/json`.

### Sensitivity And UQ

Built-in ensemble support:

```bash
openlimno ibm ensemble scenario.yaml \
  --n 200 \
  --seed 42 \
  --out-dir out/ibm_ensemble
```

Required outputs:

- ensemble manifest;
- parameter sample table;
- population quantiles;
- persistence probability;
- sensitivity ranking.

## Modern Technical Strategy

### Runtime Layers

1. Reference backend: clear Pandas/NumPy implementation.
2. Vector backend: structured arrays for large fish/cell counts.
3. Optional accelerator backend: Numba or JAX once contracts stabilize.

Do not start with GPU code. First freeze the scenario/profile/submodel
interfaces. Acceleration is valuable only after reference outputs are stable.

### Parallelism

- Scenario ensembles parallelize naturally by seed / parameter sample.
- Single-run parallelism is secondary and should not complicate correctness.
- Use process-level parallelism first; add vectorized agent kernels later.

### Storage

- CSV remains human-inspectable.
- Parquet becomes the preferred large-run format.
- Zarr can be considered for long ensemble outputs after core workflows are
  stable.

### Studio

Studio should be local-first:

- default host remains loopback;
- non-loopback binding requires explicit warning;
- no authentication is needed for loopback-only local use;
- no hidden profile changes;
- every run creates a manifest and downloadable scenario/profile bundle.

## CLI Design

Current commands remain compatibility wrappers:

- `openlimno ibm-run-native`
- `openlimno ibm-studio`
- `openlimno ibm-benchmark-instream7`
- `openlimno ibm-run-instream7-netlogo-reference`
- `openlimno ibm-summarize-instream7-brief`
- `openlimno ibm-compare-instream7-netlogo`

New command group:

```bash
openlimno ibm scenario init --out scenario.yaml
openlimno ibm submodels
openlimno ibm scenario validate scenario.yaml
openlimno ibm profile init --species rainbow_trout --out profiles/rainbow_trout.yaml
openlimno ibm profile validate profiles/rainbow_trout.yaml
openlimno ibm profile inspect profiles/rainbow_trout.yaml
openlimno ibm run scenario.yaml
openlimno ibm compare --native out/ibm --reference reference.csv --out report.csv
openlimno ibm calibrate scenario.yaml \
  --observed observed_population.csv \
  --param base_daily_survival=0.99,0.995,1.0 \
  --out-dir out/calibration
openlimno ibm ensemble scenario.yaml \
  --seed 1 --seed 2 --seed 3 \
  --out-dir out/ensemble
```

## Validation Gates

### Engineering Gates

- Profile schema validates all preset profiles.
- Scenario schema validates examples and rejects unknown fields.
- Current `run_native_ibm(...)` output compatibility is preserved.
- Run manifest hashes change when inputs change.
- Deterministic runs are bit-stable for pinned examples.
- Stochastic runs are seed-reproducible.
- Studio API can load scenario, edit profile, run, and write manifest.

### Scientific Gates

- inSTREAM Example A and B official input crosswalk remains green.
- NetLogo BriefPop comparisons are generated from pinned NetLogo 7.x outputs.
- Acceptance reports include abundance, biomass, mean length, reach allocation,
  redds, and recruitment timing.
- At least one species profile has a signed calibration report before any
  stronger claim than "research prototype."
- Real-basin validation must be separate from inSTREAM parity. Passing NetLogo
  parity does not prove field validity.

### Documentation Gates

- ODD-style model description generated from scenario/profile/submodel metadata.
- Every preset profile includes source/evidence labels.
- Every calibration report includes failed metrics, not only the aggregate score.
- Docs explicitly state which claims are supported and which are not.

## Migration Plan

### Phase 0: Freeze Current Prototype Behavior

- Keep current tests for `native.py`, `instream7.py`, and Studio green.
- Add golden-output smoke fixtures for a small deterministic scenario.
- Document current limitations honestly.

### Phase 1: Scenario/Profile Contracts

- Add `ibm_scenario.schema.json` and `species_profile.schema.json`.
- Implement load/write/validate helpers.
- Add profile presets mapped from current `SpeciesProfile` defaults.
- Add `ibm_run_manifest.json` to current output writer.

### Phase 2: New CLI Group

- Add `openlimno ibm profile validate/inspect`.
- Add `openlimno ibm scenario validate`.
- Add `openlimno ibm run scenario.yaml`.
- Keep old commands as wrappers.

### Phase 3: Submodel Extraction

- Extract habitat selection, growth, mortality, movement, spawning, and redds.
- Keep `run_native_ibm(...)` as a facade.
- Add per-submodel tests and ODD metadata.

### Phase 4: Calibration Workbench

- Add objective metrics and compare reports.
- Add deterministic parameter search.
- Add ABC-style calibration for selected parameters.
- Write calibrated profiles as new files.

### Phase 5: Ensemble And UQ

- Add ensemble runner.
- Add uncertainty summaries and sensitivity ranking.
- Add performance tests for fish count × cell count × day count.

### Phase 6: Studio Rebase

- Make Studio open/save scenario and profile files.
- Surface manifests and calibration reports.
- Add non-loopback binding warning.
- Add profile diff view so users can see every parameter change.

### Phase 7: Optional Accelerator Backend

- Benchmark reference engine first.
- Add vectorized backend only where profiling proves value.
- Experiment with JAX/Numba for ensembles or large fish/cell arrays.
- Keep reference backend authoritative for correctness.

## Acceptance Criteria

The redesign is complete when:

- A native IBM run can be reproduced from one scenario file and one profile
  file.
- The same scenario can be run by CLI and Studio with matching manifest hashes.
- The inSTREAM comparison workflow produces explicit pass/fail rows per metric.
- Profile edits are validated, evidence-labelled, and never hidden.
- Ensemble runs produce uncertainty bands and persistence summaries.
- At least one calibrated profile has a report that a reviewer can inspect.
- Documentation still says "research-grade" unless the scientific gates close.

## First Implementation Slice

The first code slice should be deliberately narrow:

1. Add profile schema + load/write helpers.
2. Add scenario schema + load helper.
3. Add manifest writer to `write_native_ibm_result`.
4. Add `openlimno ibm profile validate`.
5. Add `openlimno ibm run scenario.yaml` as a wrapper around current
   `run_native_ibm`.
6. Add tests proving the old CLI still works.

This gives users a better contract without destabilizing the biological kernel.

## Implementation Status

Implemented in the current working tree:

- `species_profile.schema.json` and `ibm_scenario.schema.json`;
- `load_species_profile`, `write_species_profile`, `load_ibm_scenario`, and
  `run_ibm_scenario`;
- `ibm_run_manifest.json` with input hashes, seed, resolved submodels, profile
  overrides, scenario overrides, and output hashes;
- registered submodel metadata via `openlimno ibm submodels`;
- semantic scenario validation for unsupported submodel slots/ids;
- `openlimno ibm profile validate/inspect`;
- `openlimno ibm scenario validate`;
- `openlimno ibm run`;
- `openlimno ibm ensemble` across explicit seeds or scenario-defined seeds,
  writing final summaries, daily uncertainty bands, and parameter sensitivity
  ranking when ensemble parameter grids are supplied;
- `openlimno ibm calibrate` for deterministic grid-search calibration against
  observed daily abundance, writing `ibm_calibration_summary.csv`,
  `ibm_calibration_manifest.json`, and `best_profile.yaml`.
- ABC-style rejection calibration through `run_ibm_abc_calibration` and
  `openlimno ibm calibrate --method abc`, writing accepted samples, posterior
  summaries, and a best profile;
- runtime submodel classes for growth-risk habitat scoring, bioenergetic growth,
  size-priority cell assignment, ordered adjacent-reach movement, redd
  spawning, and redd emergence, with `native.py` calling those extracted
  implementations.
- graph-based reach movement with optional passage probabilities, plus
  calibrated redd-placement scoring with optional hydraulic survival terms;
- event attribution helpers and `native_ibm_event_daily.csv` /
  `native_ibm_event_summary.csv` reports;
- Studio run rebasing on standard IBM scenario/profile/habitat files, so
  Studio and CLI share the same manifest-producing runner;
- native-vs-inSTREAM parity summary reports next to the detailed comparison
  CSV.

Remaining validation gates before changing the public "research-grade" claim:

- real-basin calibration reports reviewed against observed abundance, biomass,
  size distribution, reach occupancy, redd counts, recruitment timing, and
  persistence;
- broader inSTREAM / InSALMO official-case parity runs under documented
  tolerances;
- performance profiling before enabling any optional accelerator backend as a
  non-reference engine.
