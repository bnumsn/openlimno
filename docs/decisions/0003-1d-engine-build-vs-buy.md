# ADR-0003: 1D hydraulic engine: build vs buy

- **Status**: **Accepted (build, minimal scope)** — promoted from Proposed on 2026-05-07
- **Date**: 2026-05-07
- **SPEC sections**: §4.1.1, §10.1
- **Tags**: hydro, dependency, m0-deliverable, accepted

## Context

SPEC §4.1.1 requires a 1D Saint-Venant solver in 1.0 (PHABSIM-equivalent, table-level regression ≤ 1e-3). Two options:

**Build**: implement Saint-Venant from scratch (Preissmann 4-point implicit, Manning friction, embedded culvert/bridge/weir local models per HEC-RAS practice).

**Buy**: wrap an existing open-source 1D engine.

Gemini round 2 review flagged the build option: "1D 引擎的难点不在方程,在涵洞/堰/闸门数值稳定性和特例处理。从头写可能导致 M2 周期失控。"

## Decision

**Decision is deferred to M0 vendor survey.** This ADR captures the candidates and evaluation criteria so that the M0 decision is auditable.

## Candidates

### Candidate A: Build (in-house Saint-Venant)
- Pros: no external dependency, full control, integrates cleanly with WEDM
- Cons: implementation effort 3-6 months for a maintainer-pair; structure handling (culvert/bridge/weir) is bug-prone; HSI rigor demands stable solver

### Candidate B: MASCARET (EDF, LGPL)
- Pros: French nuclear-grade 1D code, mature, includes structures, wraps cleanly
- Cons: LGPL header requirements; Fortran build chain; community is mostly francophone; SI / English docs sparse
- Status: open source as of 2017 (TELEMAC-MASCARET); active

### Candidate C: HEC-RAS 1D open components
- Pros: market standard, every consultant knows it
- Cons: USACE copyright, redistributing binary may not be compliant; "open components" subset is fuzzy (HEC-Hydraulic-Open-Components is unclear); legal review required

### Candidate D: SWMM 1D modules
- Pros: EPA, public domain, mature
- Cons: SWMM is urban-stormwater oriented, river hydraulics is secondary; HSI workflow fit is awkward

### Candidate E: SOBEK (Deltares, GPL)
- Pros: mature, includes ecology variants
- Cons: GPL is incompatible with Apache-2.0 main branch licensing

### Candidate F: HMS (HEC) / EPANET / others
- Out-of-scope for river hydraulics

## M0 evaluation criteria

The M0 vendor survey must score each candidate on:

| Criterion | Weight |
|---|---|
| License compatibility (Apache-2.0 main + LGPL via wrapper acceptable) | 25% |
| Maintenance status (last release < 24 months) | 15% |
| Structure handling (culvert / bridge / weir / gate) | 20% |
| Cross-platform build (Win/Mac/Linux) | 15% |
| Integration cost (Python wrapping effort) | 10% |
| Community / docs (English) | 10% |
| Bus factor of upstream | 5% |

## M0 vendor survey results

Conducted 2026-05-07.

### Candidate B: MASCARET — DROPPED

- No PyPI / conda-forge package as of 2026-05
- Requires building TELEMAC-MASCARET source tarball with Fortran toolchain
- Wrapping needs subprocess + steering file authoring (~weeks of work)
- LGPL header obligations ✓ workable
- **Dropped**: integration cost dominates M1+M2 scope when our actual need is far smaller

### Candidate C: HEC-RAS 1D open components — DROPPED

- No open Python API
- USACE binary redistribution legally fuzzy
- "Open components" project status unclear
- **Dropped**: blocked by legal + interface

### Candidate D: SWMM — DROPPED

- Urban-stormwater oriented, river hydraulics is a sub-mode
- **Dropped**: scope mismatch

### Candidate E: SOBEK — DROPPED

- GPL license incompatible with our Apache-2.0 main branch
- **Dropped**: license

### Candidate A: Build (in-house, minimal scope) — **SELECTED**

Scope is much smaller than originally feared:

- **M1 (PHABSIM/MANSQ equivalence)**: per-section Manning normal-depth solver. Given Q and a cross-section, find h such that Q = (1/n) · A(h) · R(h)^(2/3) · S^(1/2). 1D root-finding. ~50 lines.
- **M2 (PHABSIM/IFG4 equivalence)**: add standard-step backwater profile (downstream-to-upstream march, energy equation). ~150 additional lines.
- **Out of M1/M2 scope** (deferred to 1.x): unsteady Saint-Venant, structures (culvert/weir/bridge), supercritical regime detection.

Total M2 cost estimate: ~3 weeks of one developer including tests + Bovee 1997 regression. Bus-factor-2 review feasible.

## Decision

**Build, minimal-scope.** Implement `Builtin1D` in-house with two components:

1. `MANSQSolver` (M1): per-section Manning normal-depth via `scipy.optimize.brentq`
2. `StandardStepSolver` (M2): backwater profile

Defer MASCARET / HEC-RAS components to a future sub-ADR triggered by 1.x scope (when unsteady or structures land in scope).

## Consequences

### Positive
- M1 unblocked: ~50 lines of Python
- No external runtime dependency beyond NumPy/SciPy
- Cross-platform install trivial
- Implementation reads like a textbook (Chow 1959 Open-Channel Hydraulics ch. 5)

### Negative
- We commit to maintaining a numerical solver, however small
- Future structure handling (culvert/weir/bridge) requires either re-evaluating MASCARET or building per-structure local models per HEC-RAS practice
- No "free" gain from MASCARET's mature edge cases (supercritical / transcritical)

### Acknowledged
- M1 MANSQ solver assumes subcritical regime and cannot resolve hydraulic jumps
- M2 standard step assumes subcritical; supercritical detection deferred to 1.x
- We are not building unsteady; this is intentional, matching PHABSIM scope

## Implementation entry point

`src/openlimno/hydro/builtin_1d.py` — see `Builtin1D` class.

## References

- Chow, V.T. (1959) Open-Channel Hydraulics, McGraw-Hill — Manning normal depth (§5) and standard step (§10)
- Bovee 1986 PHABSIM Reference Manual MANSQ + IFG4 algorithms
- SPEC v0.5 §4.1.1
- Gemini round 2 review (provisional MASCARET preference): superseded by this M0 vendor survey

## Consequences (depending on choice)

If Build: schedule risk on M2 (10-month PHABSIM equivalence target).
If Buy MASCARET: LGPL header obligations + Fortran build burden in CI.
If Buy HEC-RAS: legal review may extend M0 by 1-2 months.

## References

- MASCARET: https://www.opentelemac.org/index.php/component/jdownloads/category/2-mascaret-source
- HEC-RAS: https://www.hec.usace.army.mil/software/hec-ras/
- Gemini round 2 evaluation, SPEC Appendix B
