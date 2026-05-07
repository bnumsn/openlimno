# SPEC Change Proposal Template

> Use this template to propose changes to [`SPEC.md`](../../SPEC.md). File as a GitHub Issue tagged `spec-change`. Public comment period ≥ 14 days. Decision by PSC majority vote.

---

## Title

[One-line summary, e.g. "Add Bayesian HSI to 1.0 scope"]

## SPEC sections affected

- [ ] §0.2 Goals / §0.3 Non-goals
- [ ] §3 Contracts / WEDM
- [ ] §4 Module specifications
- [ ] §6 Algorithm choices
- [ ] §10 Roadmap
- [ ] §11 Governance
- [ ] §13 Research roadmap (move to/from)
- [ ] Other: ___

## Type of change

- [ ] Add to 1.0 scope (bring from §13)
- [ ] Remove from 1.0 scope (move to §13)
- [ ] Restructure existing §
- [ ] Clarify wording / fix internal contradiction
- [ ] Add new module
- [ ] Change algorithm / data model
- [ ] Other: ___

## Motivation

(Why is this change needed? What concrete user / project need?)

## Proposed change

(Specific text changes. Quote current SPEC and proposed replacement.)

## Impact analysis

| Area | Impact |
|---|---|
| Scope (§0.3 risk) | (will this expand 1.0?) |
| Data model | (does WEDM change? backward compatible?) |
| API | (does public API change? semver impact?) |
| Roadmap | (does M1-M5 timeline shift?) |
| Maintenance burden | (per maintainer hours/week) |
| Bus factor | (do we have ≥ 2 reviewers for this area?) |
| External dependencies | (new packages? license check?) |
| Validation | (new benchmarks needed?) |
| Domain risk | (will this break HSI rigor / IFIM compatibility / regulatory output?) |

## Alternatives considered

(What other approaches were considered? Why was this one chosen?)

## Compatibility

- [ ] Backward compatible (no migration needed)
- [ ] Migration path documented (cite migration script / docs)
- [ ] Breaking change with deprecation cycle (≥ 1 minor release)

## Acceptance criteria

(How do we know this proposal is implemented?)

- [ ] SPEC.md updated (cite section)
- [ ] Implementation PR linked
- [ ] Tests added (cite path)
- [ ] Documentation updated
- [ ] CHANGELOG entry

## References

- Linked issues:
- Related ADRs:
- Cited literature:

## PSC vote

| Member | Vote | Date |
|---|---|---|
| | | |

## Outcome

- [ ] Accepted (SPEC bumped to v0.X)
- [ ] Rejected (with reason)
- [ ] Tabled (revisit at __)
- [ ] Withdrawn by proposer
