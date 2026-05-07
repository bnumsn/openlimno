# ADR-0009: Regulatory output templates: CN-SL712 / US-FERC / EU-WFD

- **Status**: Accepted (M2 expert sign-off needed)
- **Date**: 2026-05-07
- **SPEC sections**: §4.2.4.2, §14.3
- **Tags**: habitat, regulatory, output

## Context

WUA-Q curves and habitat time series are not directly usable in regulatory submissions. Three major regulatory frameworks require specific output formats:

- **China**: SL/Z 712-2014 河湖生态流量计算规范 — monthly minimum / suitable / multi-year average % / 90% guarantee
- **USA**: FERC 4(e) conditions — flow regime by water year type
- **EU**: WFD 2000/60/EC Annex V — ecological status class (high / good / moderate / poor / bad)

Without this, OpenLimno is academically interesting but cannot ship a final report.

## Decision

OpenLimno 1.0 ships three `regulatory_export` templates:

1. **CN-SL712** with the SL/Z 712-2014 §5.2-5.4 four-tuple (monthly min / monthly suitable / multi-year average % / 90% guarantee)
2. **US-FERC-4e** with flow regime by water year type (wet/normal/dry)
3. **EU-WFD** with ecological status class

Each template outputs CSV + PDF.

These are **template skeletons in 1.0**; final regulatory acceptance requires expert sign-off at M2 (SPEC §14.3): one expert per framework as reviewer-of-record, acknowledged in the GMD model description paper.

## Alternatives considered

### A: Generic export only
Rejected: domain review judges this insufficient ("WUA-Q 与监管语言之间还有多大鸿沟").

### B: Many templates (Brazilian ANA, Australian MDB, etc.)
Deferred: 3 templates cover the largest user bases; community can contribute more.

## Consequences

### Positive
- OpenLimno usable for actual regulatory submissions in three major jurisdictions
- M2 expert review provides academic credibility

### Negative
- Maintenance burden for each template as regulations evolve
- Three external relationships (SL712 editor / FERC contractor / EU EA) to maintain

### Acknowledged
- ESA Section 7 biological opinion sub-template and WFD BQE integration are M2+ work, not 1.0
- We do not represent that 1.0 templates suffice for legal submission without local expert review

## References

- SL/Z 712-2014: Chinese standard
- 18 CFR Part 4: US FERC regulations
- EU WFD 2000/60/EC: Annex V
- Poff et al. 2010, ELOHA framework
- SPEC v0.5 §4.2.4.2
