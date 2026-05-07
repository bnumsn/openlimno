# ADR-0008: Multi-scale habitat aggregation: cell / HMU / reach

- **Status**: Accepted
- **Date**: 2026-05-07
- **SPEC sections**: §3.1.1, §4.2.3, §4.2.5
- **Tags**: habitat, scale, mesohabitat

## Context

PHABSIM operates at the **micro-habitat** (cell) scale. Modern stream ecology (Frissell 1986 hierarchical framework, Kemp 1999 mesohabitat units, Parasiewicz 2001 MesoHABSIM) requires concurrent micro / meso / macro analyses.

Without HMU-level aggregation, OpenLimno cannot answer questions like "if this riffle is removed, how much spawning habitat is lost?" — the canonical question in dam / diversion review.

## Decision

OpenLimno 1.0 supports three aggregation scales:

1. **Cell**: standard PHABSIM-style WUA over individual mesh cells
2. **HMU (mesohabitat)**: WUA aggregated over hydromorphological mesohabitat polygons (riffle/run/pool/glide/cascade/step/backwater per Wadeson 1994 / Parasiewicz 2007)
3. **Reach**: WUA aggregated to user-defined reaches (sum of HMUs)

HMUs are stored as a parallel data layer in WEDM (`hmu` polygon table). They can be:
- User-supplied (manual delineation in QGIS)
- Auto-classified by `openlimno.habitat.classify_hmu()` from hydraulic results (Froude + relative depth thresholds)

## Alternatives considered

### A: Cell-only (PHABSIM legacy)
Rejected: domain review judges this paradigm-obsolete.

### B: HMU-only (MesoHABSIM-style)
Rejected: loses cell-level resolution that some research uses.

### C: Cell + reach (skip HMU)
Rejected: HMU is the natural unit for management decisions and required by domain reviewers.

## Consequences

### Positive
- Compatible with MesoHABSIM workflows
- Enables management questions (HMU removal scenarios)
- Defensible against modern ecology review

### Negative
- Slightly more complex config and data model (one extra table + one extra aggregation level)

### Acknowledged
- HMU classification thresholds (Froude / depth) vary by region; defaults from Wadeson 1994 + Parasiewicz 2007 are starting points, users can override

## References

- Frissell et al. 1986, A hierarchical framework for stream habitat classification
- Kemp et al. 1999, Mesohabitats and the management of fluvial systems
- Parasiewicz 2001, MesoHABSIM, Fisheries
- Parasiewicz 2007, MesoHABSIM revisited
- Wadeson 1994, A geomorphological approach
- SPEC v0.5 §4.2.3
