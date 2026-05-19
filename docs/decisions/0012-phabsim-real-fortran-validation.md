# ADR-0012: PHABSIM Fortran real-run validation harness (R-PHABSIM-REAL)

- **Status**: Proposed (track open; first sub-deliverable pending)
- **Date**: 2026-05-19
- **Deciders**: acrochen
- **SPEC sections**: SPEC.md §0.2 P5 / §13.7;
  CAPABILITY_BOUNDARY_1_0.md D5
- **Tags**: [hydro, habitat, validation, governance]

## Context

CAPABILITY_BOUNDARY_1_0.md D5 requires:

> One real PHABSIM Fortran run compared, table-level Δ ≤ 1e-3.

The project's competitive positioning (`docs/strategy/competitive-positioning.md`)
states the strategic rule "Interop before replacement" — OpenLimno's
claim to "modernise PHABSIM / River2D / FishXing"
(memory `project_openlimno`) rests on demonstrable parity with at least
one of those reference platforms.

As of v3.6.1, the project has:

- A **closed-form analytic** comparison against the Bovee 1997 cookbook
  (PHABSIM book §5, trapezoidal channel cases) — `benchmarks/phabsim_bovee1997/`
  with Δ ≤ 1e-3 threshold. **This is not a real-run comparison**; it's
  an analytic regression that verifies OpenLimno reproduces the
  closed-form math.
- An export-table reader for River2D and HABBY (reads tables produced
  by external runs; threshold 5% / 1e-6 respectively).
- A report parser for FishXing CSV/XLSX outputs.

**None of these constitute "a real PHABSIM Fortran run compared"** in
the sense of CAPABILITY_BOUNDARY D5. The PHABSIM Fortran binary
(USFWS) has not been built or run by this project; no actual binary
output has been compared cell-by-cell to OpenLimno's `Case.run`
output on the same input geometry.

This gap is one of the three CHARTER-BLOCKING findings in the
2026-05-19 strategic review (codex S6) and the U3 criterion in
[ADR-0011](0011-stable-major-tag-moratorium.md)'s unfreeze gate.

## Decision

Open the **R-PHABSIM-REAL** work track. First sub-deliverable: build a
reproducible OCI-container harness that wraps the USFWS PHABSIM
Fortran binary, mirroring [ADR-0002](0002-schism-integration-strategy.md)'s
SCHISM subprocess-container strategy. Use the harness to replicate one
canonical Bovee 1997 case (Cookbook §5.1, Trapezoidal Channel) end-to-end:

1. Container builds USFWS PHABSIM source from public archive
   (or licensed redistribution, if permitted under the USFWS terms;
   verify license before publishing the OCI image).
2. Container runs PHABSIM's `HABTAE` (or equivalent module) against
   the §5.1 input deck.
3. OpenLimno reads the input deck (legacy `.dat` parser exists in
   `preprocess/legacy.py`), runs `Case.run`, and writes
   the same output cell schema.
4. Comparison harness (lives at `benchmarks/phabsim_real/`, analogous
   to `benchmarks/_compare/`) loads both, joins on cell+stage+species,
   asserts |OpenLimno − PHABSIM| ≤ 1e-3 per cell.
5. Result lives under the `benchmark` pytest marker; CI runs the
   harness on tagged ships once it exists.

**Acceptance**: ONE case (Cookbook §5.1) at Δ ≤ 1e-3 closes the U3
criterion. Additional cases are nice-to-have, not required.

## Alternatives considered

### Alternative A — keep the analytic-only comparison and claim D5 closed
- Pros: zero engineering work; harness already exists.
- Cons: dishonest. The closed-form is OpenLimno-vs-paper, not
  OpenLimno-vs-Fortran-binary. A regulatory or scientific audit
  catches this in five minutes. Charter-blocking under SPEC P5
  ("工程可诊断 > 论文级精度") in the inverse sense — the project
  promised practical reproducibility and didn't deliver it.

### Alternative B — substitute River2D or HABBY real-run for PHABSIM
- Pros: River2D / HABBY have more accessible binaries; License terms
  cleaner.
- Cons: D5 specifically names PHABSIM. Substituting requires SCP +
  PSC vote (per GOVERNANCE.md). Open as a contingency if PHABSIM
  binary acquisition stalls > 90 days.

### Alternative C — license the IFG4 reference data and treat the
  literature tables as ground truth
- Pros: cheapest path; IFG4 reference data is public-domain.
- Cons: reference tables are pre-computed; cell-level cross-check is
  not possible. Acceptable as supplement, not as the U3 closer.

## Consequences

### Positive
- D5 closes meaningfully — "we matched a real Fortran run" is the
  claim consultants and regulators will weigh against the project.
- Reusable container infrastructure: the same OCI-runner pattern
  (already shipped for SCHISM at `ghcr.io/bnumsn/schism:5.11.0`)
  applies to PHABSIM, and likely later to River2D, FishXing.
- Closes codex S6 strategic-review finding.

### Negative
- USFWS PHABSIM source license is "public-domain US federal
  government work" but actual redistribution-in-container terms
  may have caveats; must be verified before publishing the image
  to ghcr.io.
- Building PHABSIM from source has historical pain (Fortran 77
  compiler-version sensitivity; old NCAR build conventions).
  Estimate 1-2 weeks of build-engineer time.
- Bovee 1997 §5.1 input deck must be sourced; may need to be
  digitised from the cookbook scan.

### Neutral / Acknowledged trade-offs
- This work is **not** in the path of any current user. Until
  D6 (basin case) closes, the PHABSIM real-run is for credibility,
  not user value. That's fine — credibility IS the deliverable
  at this milestone.

## Implementation notes

- Sub-deliverable order:
  1. `benchmarks/phabsim_real/README.md` — describe the container
     plan + Bovee §5.1 input deck capture
  2. `benchmarks/phabsim_real/Dockerfile` — build PHABSIM from source
  3. `benchmarks/phabsim_real/inputs/bovee1997_5_1.dat` — input deck
  4. `benchmarks/phabsim_real/run_phabsim.sh` — container invocation
  5. `benchmarks/phabsim_real/test_real_run_matches.py` — pytest
     marker `benchmark`, runs both, asserts Δ ≤ 1e-3
- Reuse the SCHISM container pattern (ADR-0002): subprocess wrapper,
  no Python dependency inside the container, dry-run mode for CI when
  the binary isn't built.
- Container image lives at `ghcr.io/openlimno/phabsim:1986` (USFWS
  release year as tag), pending license confirmation.

## References

- ADR-0002 (SCHISM integration strategy — same containerisation pattern)
- ADR-0011 (this ADR's parent: the moratorium that motivates U3)
- `benchmarks/phabsim_bovee1997/` (the existing closed-form harness)
- USFWS PHABSIM software: https://www.usgs.gov/centers/fort-collins-science-center/science/instream-flow-incremental-methodology-phabsim
  (verify license + binary acquisition path)
- Bovee 1997, "Data Collection Procedures for the Physical Habitat
  Simulation System" (USGS USGS-BRD-1997-0004) — the cookbook
  whose §5.1 we replicate
