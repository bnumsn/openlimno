# Study plan (IFIM steps 1-2)

`openlimno.studyplan` covers the IFIM workflow that PHABSIM ignores: problem identification, study planning, target species rationale, time-use factors. SPEC §4.4.

## Why a separate module

PHABSIM is the calculation engine for IFIM Step 3 (Study Implementation). Steps 1 (Problem Identification) and 2 (Study Planning) decide *which species, which life stages, which time windows, which HSI sources, which uncertainties to acknowledge*. OpenLimno makes these explicit so the case YAML alone is insufficient — you also need a `studyplan.yaml`.

## File schema

```yaml
problem_statement: |
  Establish minimum and suitable ecological flow recommendations for the
  Lemhi River near Lemhi, ID, supporting native steelhead spawning success
  and juvenile rearing under projected diversion scenarios.

study_planning:
  spatial_scope: "Lemhi mainstem from Hayden Creek to Salmon River, 18 km"
  temporal_scope: "Water years 2020-2024"
  stakeholders:
    - "Idaho Department of Fish and Game"
    - "USFWS / NOAA Fisheries (ESA section 7)"

target_species_rationale:
  - species: oncorhynchus_mykiss
    rationale: "ESA-listed Snake River steelhead DPS"
    protection_status: "ESA Threatened"

objective_variables: [wua-q, wua-time, hdc, persistent_habitat, passage_eta_p]

# Override the library-default Time Use Factor for specific (species, stage)
tuf_override:
  - species: oncorhynchus_mykiss
    stage: spawning
    monthly: [0, 0, 0.2, 0.8, 1.0, 0.4, 0, 0, 0, 0, 0, 0]
    rationale: "IDFG 2023 redd-survey timing data"

hsi_source_decision:
  preference: neighboring_basin
  rationale: "USFWS Blue Book transferability_score=0.6"

uncertainty_sources_acknowledged:
  - hsi_uncertainty
  - transferability
  - measurement_error
  - temporal_assumption
```

## CLI

```bash
openlimno studyplan validate examples/lemhi/studyplan.yaml
openlimno studyplan report examples/lemhi/studyplan.yaml
```

`report` produces a human-readable summary suitable for project file documentation.

## TUF priority rules (SPEC §4.4.1.1)

Time Use Factors come from two places:

1. **Library default** in `life_stage.parquet` per `(species, stage)` (e.g., USFWS / IDFG canonical timing)
2. **Case override** in `studyplan.yaml.tuf_override`

The case override **always wins** when both define the same `(species, stage)`. This lets you:

- Use library defaults for cross-case comparability
- Override per-project where local data dictates

```python
from openlimno.studyplan import StudyPlan, merge_tuf

sp = StudyPlan.from_yaml("examples/lemhi/studyplan.yaml")
monthly, source = sp.merge_tuf("oncorhynchus_mykiss", "spawning",
                                library_default_monthly=lib_default)
print(f"TUF source: {source}")          # "case_override" | "library_default" | "fallback_uniform"
```

## What's not in 1.0 (SPEC §4.4.3)

- IFIM Step 4 Alternatives Analysis → §13.16 multi-objective Pareto
- IFIM Step 5 negotiation tools → out of OpenLimno scope (left to project teams)
