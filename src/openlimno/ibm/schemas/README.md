# IBM schemas — relationship to WEDM

This directory holds JSON schemas for the native IBM track:
`ibm_scenario.schema.json` and `species_profile.schema.json`. They
sit in parallel to the canonical [`wedm/schemas/`](../../wedm/schemas/)
case-level schemas.

This duality was flagged by round-22 review (codex A7 / gemini A6,
MEDIUM/LOW) as "schema fork": IBM has its own schema loader
(`openlimno.ibm.scenario.load_ibm_schema`) while WEDM has a richer
validator with `$ref` resolution and format-checker wiring
(`openlimno.wedm.validate_case`). The two are not interchangeable.

This README documents the boundary so future contributors don't
accidentally widen the fork.

## Current state (2026-05-26, post-merge per ADR-0016)

### WEDM (`src/openlimno/wedm/schemas/`)

- 12 schemas covering case + builtin_1d + schism + hsi + species +
  life_stage + studyplan + passage + migration_corridor +
  physical/biological observations + drifting_egg
- Driven by `openlimno.wedm.validate_case(case_yaml_path)`
- Uses `jsonschema.Draft202012Validator` with format-checker
- Cross-schema `$ref` resolution against the on-disk schema
  registry
- Output: list of human-readable validation errors

### IBM (`src/openlimno/ibm/schemas/`)

- 2 schemas covering native IBM scenario + species profile
- Driven by `openlimno.ibm.scenario.validate_ibm_scenario(...)` and
  `validate_species_profile(...)`
- Loads schemas directly from disk via `load_ibm_schema(name)`;
  validates with a fresh `Draft202012Validator` (NO format-checker
  wiring, NO cross-schema $ref resolution against the WEDM
  registry)
- Output: raises `jsonschema.ValidationError` on first failure
  (no aggregated error list)

## Why the two stay separate (for now)

1. **IBM scenarios are NOT cases.** A `case.yaml` is a hydraulic /
   habitat / regulatory pipeline definition. An IBM scenario is a
   population-dynamics simulation config. They share NO fields:
   no mesh, no hydrodynamics backend, no habitat overlay, no
   regulatory_export.
2. **IBM schema is post-1.0 charter (per SCP-0001).** Putting IBM
   schemas under the `wedm/` registry would expand WEDM's
   surface beyond what 1.0 ratifies. Until SCP-0001 closes via
   PSC vote, the IBM schema's authority lives in `ibm/`.
3. **Validator semantics differ.** WEDM aggregates all validation
   errors and returns them as a list (for the CLI `validate`
   command to surface every problem). IBM's
   `validate_ibm_scenario` raises on first failure (for fail-fast
   scenario runs). Unifying the validators would require picking
   one mode or supporting both — out of scope for the cleanup
   track.

## Boundary contract (DO and DO NOT)

DO:
- Treat `ibm/schemas/` as the authoritative source for IBM
  scenario + species-profile JSON shape.
- Treat `wedm/schemas/case.schema.json` as the authoritative
  source for `case.yaml` shape.
- Cross-reference between the two using documentation + tests, NOT
  cross-`$ref`.

DO NOT:
- Add `$ref` from `wedm/schemas/*` into `ibm/schemas/*` or vice
  versa.
- Modify either schema set without updating the corresponding
  test_*_schemas.py file.
- Treat the parallel structure as a permanent design — it's
  conditional on SCP-0001 charter ratification, after which IBM
  may move to `wedm/schemas/ibm/` or stay separate by explicit
  decision in ADR-0014.

## Future direction

The R-IBM-SCHEMA-UNIFY cleanup track (per ADR-0016) is now
considered **documented-as-intentional** rather than open code
work. Future cleanups would be:

1. After SCP-0001 ratifies (PSC vote, U1+U2 closed): decide
   whether IBM schemas move under `wedm/schemas/ibm/`.
2. If the answer is yes, the validator infrastructure
   (`load_ibm_schema`) folds into `openlimno.wedm.validate_*`
   with an IBM-specific entry point.
3. If the answer is no, this README graduates from
   "explanation" to "permanent design note".

Either path is OK; the round-22 finding is closed when this
README + tests document the boundary clearly enough that a new
contributor knows which schema dir to edit. As of 2026-05-26 that
condition is met.
