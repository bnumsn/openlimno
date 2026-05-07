# ADR-0006: HSI rigor as hard constraints

- **Status**: Accepted
- **Date**: 2026-05-07
- **SPEC sections**: §4.2.2, §4.2.2.2, §4.2.2.3
- **Tags**: habitat, hsi, scientific-rigor

## Context

The HSI methodology has been criticized for thirty years (Mathur 1985, Williams 1996, Lancaster & Downes 2010) on three grounds:

1. **Variable independence**: HSI(depth) × HSI(velocity) × HSI(substrate) assumes independence of preferences; in reality, fish preference for depth is conditional on velocity.
2. **Transferability**: HSI curves calibrated in one basin do not generalize to another.
3. **Category I/II/III conflation**: Bovee 1986 distinguishes I (expert opinion), II (utilization), III (preference); these have different statistical bases and should not be mixed.

PHABSIM and FishXing bury these assumptions silently. Reviewers of OpenLimno (round 1 domain review) flagged this as paradigm-obsolete: a modern tool that reproduces these silent assumptions would be rejected by GMD / Ecological Modelling.

## Decision

OpenLimno enforces HSI rigor at the API / config layer, not as advisory warnings:

1. `hsi_curve` schema requires `category`, `geographic_origin`, `transferability_score`, `independence_tested`.
2. Composite functions `geometric_mean` / `arithmetic_mean` require `acknowledge_independence: true` in case config — without it, the case **fails to start**.
3. WUA results computed from C-grade HSI are **watermarked** in output figures.
4. Legacy import (`import_phabsim`) supplies sensible defaults (`category="III"`, `quality="C"`) and **does not block**, ensuring backward compatibility while flagging risk.

This is "硬约束教育" (Round-2 domain review wording): the framework educates users by making them confront the assumptions rather than hiding them.

## Alternatives considered

### A: Soft warnings (`logger.warning`)
Rejected: warnings are ignored. The whole point is to confront the user.

### B: Documentation-only
Rejected: docs are not read.

### C: Block legacy data without override
Rejected by Round-2 review: breaks migration. ADR-0006 retains hard block on geom/arith composite, but allows legacy data import via `--warn-only`.

## Consequences

### Positive
- Makes OpenLimno academically defensible (paper review-resistant)
- Educates users about HSI methodology limits
- Enables future RSF/Occupancy migration (ADR/§13.17) without API break

### Negative
- Initial onboarding friction
- Some users may resent being forced to confront methodology debate

### Acknowledged
- We accept that OpenLimno is not a "drop-in PHABSIM replacement" in the literal sense; it is a "modernized PHABSIM" with explicit caveats

## References

- Mathur et al. 1985, A critique of the IFIM, CJFAS
- Williams 1996, Lost in space, Ecology
- Lancaster & Downes 2010, RRA
- Bovee 1986, IFIM stream habitat analysis
- SPEC v0.5 §4.2.2
