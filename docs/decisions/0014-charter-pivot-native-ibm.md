# ADR-0014: Charter pivot — native IBM as potential inSTREAM successor (v4 target)

- **Status**: Merged to main 2026-05-26 via [ADR-0016](0016-author-override-direct-merge.md)
  author override; strategic content stands by BDFL decision; PSC
  ratification still pending (single-author project until U1+U2 close)
- **Date**: 2026-05-26
- **Deciders**: acrochen (proposed AND merged via BDFL override; PSC quorum still required for formal ratification)
- **SPEC sections**: SPEC.md §0.3 (1.0 non-goals); proposed §13.x
- **Tags**: [strategy, charter-expansion, ibm, post-1.0]

## Context

OpenLimno's competitive position was set in 2026 as "ecological-flow
and fish-habitat decision platform — make existing hydraulic and
habitat tools useful in a modern, auditable ecological workflow."
That position deliberately treated individual-based modeling (IBM)
as **outside core scope**: IBM was for inSTREAM / InSALMO / HexSim,
and OpenLimno's role was the CSV bridge.

Two months of experience with the bridge (`preprocess/instream_netlogo.py`)
plus 6 days of prototype work (2026-05-20 → 2026-05-26) revealed:

1. The NetLogo runtime is a hard usability cliff for non-modeller
   ecologists. They cannot edit `.nlogo` files without learning a
   research-DSL.
2. inSTREAM 7 (Railsback, Ayllón, Harvey 2021) is the canonical
   open IBM for stream salmonids. Its limits are entirely
   NetLogo-era: no Parquet/UGRID/WEDM workflow, no provenance
   chain, no calibration uncertainty reports, no headless deployment.
3. A native Python IBM that consumes OpenLimno habitat-cell tables
   directly closes both gaps: usability AND provenance.
4. Research-grade prototype was achievable in 6 days (~9,400 LOC,
   86 tests, multiple inSTREAM 7 case crosswalks) — suggesting the
   architectural fit between OpenLimno's existing WEDM/habitat
   surface and IBM kernel is genuinely close.

This ADR proposes that **native IBM becomes a v4 charter capability
(NOT a 1.0 addition)** — i.e., the project's product position
expands AFTER 1.0 ships, not before.

## Decision (proposed)

OpenLimno's charter expands as follows, **effective when PSC
ratifies SCP-0001**:

1. SPEC.md gains §13.x "Native IBM as v4 research track", per
   SCP-0001 text.
2. ADR-0011 moratorium remains in force for 1.0 line; ADR-0015
   defines the experimental-branch exception.
3. inSTREAM 7 parity becomes a v4 acceptance gate, not a 1.0 gate.
4. The user-visible product position becomes:
   - 1.0: ecological-flow decision platform (habitat-based)
   - 2.0–3.x: incremental hardening of 1.0 surface
   - **v4: native IBM successor to inSTREAM 7**
5. Resources during the 1.0-rc-and-moratorium phase (where the
   project actually sits, per ADR-0011) stay focused on U1+U2
   governance + U3-U5 evidence work. IBM development is
   **timeboxed to the experiment branch** until 1.0 closes.

## Alternatives considered

### A — Reject the pivot

- Pros: charter stability; the original "ecology surface, IBM is
  external" promise stays clean
- Cons: gives up the inSTREAM 7 successor opportunity (likely
  irreversible — Cal Poly Humboldt's inSTREAM/InSALMO line is
  research-funded and not actively re-architected for modern
  workflows). The 9,400 LOC prototype goes to /dev/null.
- **Decision verdict**: Too pessimistic about strategic opportunity

### B — IBM-in-core for 1.0

- Pros: maximum strategic momentum; users get inSTREAM-successor
  in 1.0
- Cons: violates v1.0.0 surface freeze (2026-05-12); requires
  bypassing the PSC ratification process (no PSC exists yet);
  defers 1.0 ship by months; both AI reviewers (round 23)
  rejected this option
- **Decision verdict**: Governance-theatre risk too high

### C — IBM as separate `openlimno-ibm` package

- Pros: charter stability; deployment cleanly separates
- Cons: provenance chain breaks at the package boundary;
  inSTREAM 7 successor positioning becomes "OpenLimno + the
  IBM add-on" not "OpenLimno includes IBM" — weaker product
  story
- **Decision verdict**: Worse than this ADR; pivotable to if PSC
  rejects D

### D (this ADR) — Charter expansion to v4 with experiment branch

- Pros: preserves the work; ratification is procedurally clean;
  1.0 charter is honoured; opportunity is captured
- Cons: requires PSC to exist before ratification can close
  (chicken-and-egg with U1+U2). 30/60/90 day overhead on
  branch maintenance.

## Consequences

### Positive (when ratified)

- OpenLimno claims a defensible v4 position as the modern inSTREAM
  successor.
- The 9,400 LOC prototype gets a legitimate runway to mature
  (Round-22 architectural redesign on the experiment branch).
- Future maintainers see the project demonstrated discipline
  (rejected unilateral charter expansion; waited for ratification)
  AND ambition (expanded scope when strategically warranted).

### Negative

- Six weeks (per the 90-day plan) of effort goes into experimental
  refactor work with no merge guarantee.
- If PSC eventually rejects the pivot, the experiment branch
  becomes archival.
- Maintainer recruitment now has to address "do you support the
  IBM pivot?" as part of the onboarding conversation.

### Neutral / Acknowledged trade-offs

- The prototype's `studio.py` (3,286 LOC), `instream7.py`
  (1,830 LOC), and provenance fork are architectural debt that
  MUST be paid down before merge. The user-friendly Studio is a
  separate, future, decision.
- Calibration / identifiability / uncertainty / parallel execution
  are workbench features the prototype does not yet have. They
  are listed in `docs/strategy/ibm-redesign.md` and are part of
  the 60-day milestone.

## Implementation notes

This ADR is **ratification-pending**. Until PSC closes vote on
SCP-0001, no IBM code may land on `main`. The `experiment/native-
ibm-pivot` branch is the bounded location for development.

When ratified, the cherry-pick onto main follows the ordering:

1. Round-22 architecture fixes (god-object split, provenance
   unification, API sprawl reduction, schema fork closure,
   third-Studio decision)
2. Reproducibility gates (seed → identical, golden inSTREAM 7
   fixtures, strict-tolerance CI mode)
3. SPEC §13.x amendment merged
4. ADR-0011 amended or superseded
5. IBM code lands on main as a v4-target capability tagged in
   CHANGELOG with the "v4-research-track" marker
6. CAPABILITY_BOUNDARY_1_0.md remains untouched (1.0 scope
   doesn't change)

## References

- SCP-0001 (this branch) — formal SPEC amendment proposal
- ADR-0015 (this branch) — moratorium relationship
- `docs/reviews/round_21_22_23_native_ibm_pivot_audit.md` (this branch) —
  triple-AI review chain that produced this packet
- `docs/strategy/native-ibm-instream-successor.md` (this branch) —
  original strategic prose
- ADR-0011 — moratorium being amended (not revoked)
- Railsback, Ayllón, Harvey 2021 (River Research and Applications)
  — inSTREAM 7 reference paper
