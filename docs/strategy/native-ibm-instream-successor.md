# Native IBM Successor to inSTREAM / InSALMO

OpenLimno's population-response path should not embed NetLogo or require users
to edit `.nlogo` projects. The native IBM module is a headless, tested Python
engine that consumes OpenLimno habitat-cell tables and emits population summary
tables that can be archived with the rest of an ecological-flow case.

Status: this is a research prototype and calibration path, not a regulatory
claim of numerical equivalence to inSTREAM 7. Official input parity,
optional NetLogo reference execution, and NetLogo-output summarization are
implemented; full population-trajectory acceptance still requires longer
version-pinned NetLogo reference outputs and submodel calibration.

The target redesign is tracked separately in
[`ibm-redesign.md`](ibm-redesign.md). That document defines the intended
scenario/profile contracts, submodel boundaries, calibration workflow, and
migration path from the current `native.py` prototype.

## Reference Software Survey

| System | Core model | Strengths | Limits OpenLimno should improve |
|---|---|---|---|
| inSTREAM 7 / InSALMO 7 | NetLogo individual-based salmonid model | Mature trout/salmonid behavior model; daily light cycle; habitat/activity selection; growth, mortality, spawning; public examples and manual | NetLogo runtime and model-file editing; weaker integration with modern Parquet/UGRID/WEDM/provenance workflows |
| HexSim | Spatially explicit individual-based population viability platform | Generic multi-species IBM, traits, movement, genetics, disturbance and landscape workflows | Not stream-hydraulic specific; not built around WUA/HSI/regulatory evidence packages |
| PHABSIM / SEFA | Habitat suitability / WUA rather than IBM | Regulatory familiarity and traditional IFIM workflow | Does not predict mechanistic abundance or persistence from individual behavior |
| HABBY / CASiMiR / MesoHABSIM | Hydraulic-habitat coupling and mesohabitat aggregation | Strong habitat post-processing and model interoperability | Population response is not the central engine |

Primary references:

- Railsback, Harvey, and Ayllon. 2023. *InSTREAM 7 user manual: model
  description, software guide, and application guide*. USFS PSW-GTR-276.
  https://doi.org/10.2737/PSW-GTR-276
- Cal Poly Humboldt inSTREAM/InSALMO 7 download and model notes:
  https://www.humboldt.edu/ecological-modeling/instream-and-insalmo/instream-7-and-insalmo-7
- Railsback, Ayllon, and Harvey. 2021. *InSTREAM 7: Instream flow assessment
  and management model for stream trout*. River Research and Applications.
  https://research.fs.usda.gov/treesearch/62884
- HexSim project overview: https://www.hexsim.net/

## Native Engine Scope

The first native engine in `openlimno.ibm` implements the inSTREAM-like kernel
that must live inside OpenLimno:

- individual fish state (`fish_id`, age, length, mass, cell, alive/dead);
- daily simulation with light phases (`dawn`, `day`, `dusk`, `night`);
- habitat/activity selection from cell-level CSI, depth, velocity, cover,
  temperature, turbidity, size-priority access, and density competition;
- simplified bioenergetic growth from individual mass, foraging opportunity,
  consumption, respiration, and activity cost;
- mortality from baseline, predation exposure, thermal stress, and velocity
  stress;
- spawning into explicit redd/egg state during a configurable spawning window;
- temperature-dependent redd development and fry emergence;
- multi-reach fish state tracking with same-reach habitat selection by default,
  plus optional ordered-adjacent cross-reach migration for calibrated movement
  studies;
- output tables for population summary, final individuals, cell use, events,
  redd status, and optional per-fish daily history.

The key behavioral assumptions are profile parameters, not hidden constants:
light-phase feeding/predation weights, turbidity response, feeding-cover
effect, thermal and hydraulic mortality weights, density-competition strength
and minimum cell capacity, bioenergetic clipping limits, female spawner
fraction, spawning-cell weighting, and redd survival are all available through
`SpeciesProfile`.

This is intentionally not a byte-for-byte clone of inSTREAM. The design target
is a validated successor: native runtime, reproducible random seeds, testable
submodels, direct OpenLimno habitat-cell input, and ordinary CSV/Parquet outputs.

A local browser-based IBM Studio is available via `openlimno ibm-studio`. It is
the interactive successor surface for scenario setup, species-profile tuning,
habitat-cell edits, a plan-view river scene with habitat cells, fish symbols,
flow direction, live/dead fish toggles, run/step/reset controls, population
charts, fish/redd/event tables, output links, and inSTREAM 7 benchmark/BriefPop
comparison setup.

## Official inSTREAM 7 Benchmark Path

OpenLimno now includes an opt-in official-case benchmark for the public
inSTREAM 7.4 distribution. It reads the official ZIP archive or an extracted
directory, verifies the same input surfaces that the NetLogo models use, and
runs the native IBM from those inputs:

```bash
openlimno ibm-benchmark-instream7 \
  --fixture InSTREAM-7.4_2026-02-11.zip \
  --days 7 \
  --out-dir out/instream7_benchmark
```

The benchmark covers:

- Example A: one reach and one trout species;
- Example B: three reaches and three trout species;
- official initial-population strata;
- official daily flow, temperature, and turbidity time series aligned to each
  model's `start-date`;
- official depth and velocity lookup matrices, including string cell IDs such
  as `T-1`, `L-1`, and `I-1`;
- official species life-history parameters for spawning, length-weight,
  consumption, respiration, and redd survival;
- official shapefile cell attributes for area, hiding places, velocity shelter,
  and spawning fraction;
- a multi-day native run that preserves individual state, spawning history,
  reach state, and redd/egg state across daily forcing slices;
- native population, cell-use, event, final-individual, and redd/egg status
  outputs.

The generated `instream7_official_inventory.csv` is the item-by-item input
parity table. The generated `instream7_native_population_summary.csv` is the
native prototype run driven by those official inputs.

The official ZIP does not ship reference population-output CSVs from NetLogo
runs. Therefore this benchmark is an official-input and native-output
crosswalk by default. For local reference generation,
`openlimno ibm-run-instream7-netlogo-reference` copies an official case,
shortens its end date, forces daily BriefPop output, and invokes a user-supplied
NetLogo 7 `NetLogo_Console` executable headlessly. The generated
`BriefPopOut-*.csv` can then be converted by
`openlimno ibm-summarize-instream7-brief` into the same reach/species
population-summary level, and `openlimno ibm-compare-instream7-netlogo` turns
native and NetLogo summaries into a row-level abundance/biomass/mean-length
tolerance report.
The test suite also carries short two-day NetLogo 7.0.2 summary fixtures for
Example A and Example B under `tests/fixtures/instream7/netlogo_702_short/`;
these pin the smoke-test comparison path, not full scientific equivalence.

Current two-day NetLogo 7.0.2 smoke comparison snapshot, generated locally on
2026-05-24:

- Example A total abundance aligns at setup and remains within +2 fish on days
  1 and 2 (`360 -> 360 -> 357` native vs `360 -> 358 -> 355` NetLogo), but
  two of three strict zero-abundance-tolerance rows still fail.
- Example B total abundance is close after the ordered-adjacent migration
  approximation (`1875 -> 1869 -> 1865` native vs `1875 -> 1870 -> 1863`
  NetLogo). Reach totals improved relative to same-reach-only selection, but
  20 of 27 strict tolerance rows still fail because species/reach biomass and
  mean-length distributions are not yet fully calibrated.

## Advanced Design Targets

To be more useful than a NetLogo-only workflow, the native IBM should continue
in these directions:

1. Calibrated species profiles for salmonids and locally important taxa, using
   the exposed behavior parameters beyond the official example-parameter
   mapping.
2. Further calibration of multi-reach movement among reaches; the engine now
   supports ordered-adjacent migration with size, direction, and habitat-utility
   controls, but those controls still need longer reference runs before a
   numerical-equivalence claim.
3. Calibrated redd/egg survival parameters for dewatering, scour, and
   temperature-dependent development.
4. Ensemble and sensitivity runs using OpenLimno workflow/provenance metadata.
5. Longer NetLogo cross-validation artifacts for inSTREAM 7 public A/B examples;
   short two-day summary fixtures, optional NetLogo reference execution, and
   `BriefPopOut` tolerance tests are already wired.
6. Longer-run performance benchmarks for large cell meshes and multi-year
   population runs.

The current implementation now performs official input parity and native
replacement runs against the public A/B examples, and it can generate short
local NetLogo reference runs, summarize `BriefPopOut` files, and produce
tolerance reports for calibration. The official profile mapping now uses lower fish-predation and
thermal-stress mortality rates that match short-run total abundance much more
closely, and the Example B path includes a bounded adjacent-reach migration
approximation. Full reach/species numerical equivalence still requires longer
version-pinned reference output files generated from the official model,
because they are not included in the distribution archive.
