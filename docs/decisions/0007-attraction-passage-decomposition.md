# ADR-0007: Passage analysis: η = η_A × η_P decomposition

- **Status**: Accepted
- **Date**: 2026-05-07
- **SPEC sections**: §4.3
- **Tags**: passage, fish, scientific-rigor

## Context

FishXing returns a binary pass/fail on whether a fish *can* swim through a culvert under given hydraulics. This conflates two distinct ecological processes:

- **η_A (Attraction Efficiency)**: probability the fish reaches the culvert/fishway entrance — depends on attraction flow, entrance siting, sensory cues
- **η_P (Passage Efficiency)**: probability the fish, having entered, transits successfully — depends on hydraulics and swimming performance

Empirical η_A is often the limiting factor (0.3–0.7 typical) yet FishXing implicitly assumes η_A = 1.0 (Castro-Santos 2005, Bunt 2012, Silva 2018).

## Decision

OpenLimno 1.0 explicitly:

1. Computes η_P only.
2. Requires `attraction_efficiency` field in passage config (default 1.0 with explicit `note: "η_A = 1.0 means perfect entrance; empirical 0.3-0.7 more realistic"`).
3. When user provides η_A < 1, output also annotates η = η_A × η_P alongside η_P.
4. Documentation and CLI use term **"passage success rate"** (η_P only), never "passage efficiency" (which in literature refers to η).
5. η_A as a derived model (from 2D/3D entrance hydraulics + sensory field) is in §13.18 (research roadmap), not 1.0.

## Alternatives considered

### A: Reproduce FishXing pass/fail
Rejected: complicit in the same scientific conflation we set out to fix.

### B: Single η output, internally split
Rejected: hides assumption; users wouldn't know they're getting η_P only.

### C: Require η_A modeling in 1.0
Rejected: η_A modeling needs entrance hydraulics + sensory cues; not in 1.0 scope.

## Consequences

### Positive
- Defensible against fish passage literature reviewers
- Integrates with §13.18 derivation when ready

### Negative
- Slightly more verbose config for simple cases (acceptable)

## References

- Castro-Santos 2005, Optimal swim speeds
- Bunt et al. 2012, Performance of fish passage structures
- Silva et al. 2018, Future of fish passage, Fish & Fisheries
- SPEC v0.5 §4.3
