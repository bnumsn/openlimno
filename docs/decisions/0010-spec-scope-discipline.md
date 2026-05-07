# ADR-0010: SPEC §0.3 scope discipline enforcement

- **Status**: Accepted
- **Date**: 2026-05-07
- **SPEC sections**: §0.3, §1 P1, §11
- **Tags**: governance, scope, m0-deliverable

## Context

PHABSIM, River2D, FishXing all stalled in part because feature scope grew beyond maintainer capacity. SPEC §0.3 lists 1.0 non-goals to prevent this. But a list in SPEC is not enforcement.

Both Codex and Gemini round 1 reviews independently flagged "scope creep" as the highest-probability project-killing risk.

## Decision

Three enforcement layers:

1. **PR template** asks: "Is this in 1.0 scope (§4) or research roadmap (§13)?" Author must tick.
2. **CI check** (`tools/m0_checklist/spec_scope_check.py`): scans new code for keywords matching §0.3 non-goals (e.g., `gpu`, `mpi`, `bayesian_hsi`, `ibm`, `data_assimilation`). On match, posts a comment requiring SPEC change proposal review.
3. **CODEOWNERS** routes all `SPEC.md` edits and §13-touching PRs to PSC for explicit review.

The check is advisory (warns, does not auto-fail), but PSC review is required for override.

## Alternatives considered

### A: Trust contributors / no check
Rejected: PHABSIM/R2D/FX history demonstrates this fails.

### B: Hard-fail CI on §0.3 keyword
Rejected: too many false positives (e.g., a comment mentioning GPU as future work).

## Consequences

### Positive
- Visible reminder at PR time
- PSC review on borderline cases
- Reduces 18-month delivery risk

### Negative
- Some friction for contributors

### Acknowledged
- Heuristic check; may miss subtle scope expansion (counter: PSC reviews still happen for §13 / SPEC edits)

## Implementation notes

`tools/m0_checklist/spec_scope_check.py` reads `SPEC.md` §0.3 each run, extracts keywords, greps the diff. Output: list of suspect lines.

## References

- Codex round 1 review #1
- Gemini round 1 review #4
- SPEC v0.5 §0.3, §1 P1
