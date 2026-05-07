## Summary

<!-- 1-3 sentences. What and why. -->

## Scope discipline (SPEC §0.3)

- [ ] This PR is **in 1.0 scope** (SPEC §4 modules)
- [ ] This PR is **research roadmap** (SPEC §13) and targets a `research-*` branch, not `main`
- [ ] This PR is documentation / CI / chore only

If you ticked "in 1.0 scope" and the work touches a §0.3 non-goal, file a [SPEC change proposal](../docs/governance/SPEC_CHANGE_PROPOSAL.md) first.

## Type

- [ ] Bug fix
- [ ] Feature (in 1.0 scope)
- [ ] Documentation
- [ ] Refactor (no behavior change)
- [ ] Schema change (WEDM)
- [ ] Benchmark / validation
- [ ] CI / build

## Checklist

- [ ] `pixi run check` passes locally
- [ ] If WEDM schema changed: validation example added to `tests/unit/wedm/`
- [ ] If module spec impl: regression case in `tests/`
- [ ] If user-facing: docs updated
- [ ] CHANGELOG.md updated (under "Unreleased")
- [ ] Linked to issue (if applicable): #
- [ ] No new dependency with non-Apache/MIT/BSD/LGPL license

## Reviewers

(CODEOWNERS will auto-assign. ≥ 1 maintainer review for routine, ≥ 2 for security / migration / SPEC-touching code.)

## Related

- SPEC section affected: §
- ADR (if architectural): docs/decisions/00XX-...
