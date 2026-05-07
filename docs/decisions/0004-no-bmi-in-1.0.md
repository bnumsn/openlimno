# ADR-0004: No BMI in 1.0

- **Status**: Accepted
- **Date**: 2026-05-07
- **SPEC sections**: §3.2
- **Tags**: hydro, interface, scope

## Context

SPEC v0.1 proposed BMI 2.0 (NOAA OWP standard) as the universal solver interface. BMI exists for solver interchange across many backends.

In v0.2, we collapsed to a single backend (SCHISM external) + internal 1D. Two backends do not justify a 25-method standard interface.

## Decision

1.0 uses two concrete Python classes (`Builtin1D` and `SCHISMAdapter`) implementing a 3-method `HydroSolver` Protocol (`prepare` / `run` / `read_results`). No BMI.

When the third backend lands (§13.1 self-built GPU 2D, or §13.2 BMI multi-solver), the simple Protocol can be replaced with BMI in a deliberate refactor.

## Alternatives considered

### A: BMI from day 1
Rejected: 25-method interface with two implementers is over-design.

### B: No interface at all (pick SCHISM, write tightly to it)
Rejected: 1.0 internal 1D and SCHISM share the user-facing semantics (prepare/run/read), the Protocol abstraction is the minimum viable contract.

## Consequences

### Positive
- Less ceremony, faster M2 delivery
- Easier for new contributors to understand

### Negative
- Adding 3rd backend requires a deliberate refactor (acceptable, planned in §13)

### Acknowledged
- We diverge from NOAA NextGen interoperability path; reconsider if NextGen integration becomes a goal

## References

- BMI 2.0: https://bmi-spec.readthedocs.io/
- SPEC v0.5 §3.2
