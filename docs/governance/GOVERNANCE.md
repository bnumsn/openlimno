# OpenLimno Governance

> SPEC §11. Frozen at v0.5.

## Purpose

To ensure OpenLimno remains:
- Maintainable (3+ named maintainers, ≥ 2 institutions)
- Accountable (named release manager, public roadmap)
- Inclusive (Apache Way, NumFOCUS-aligned)
- Trustworthy (peer-reviewed key algorithms, transparent change process)

## Roles

### Project Steering Committee (PSC)

5 members, including **at least**:
- 1 ecologist (fish habitat / freshwater ecology)
- 1 water resources engineer (hydraulics / IFIM practitioner)
- 1 software engineer (open-source experience)

PSC holds final say on:
- SPEC changes (1.0 scope)
- License changes
- Maintainer additions / removals
- Conduct enforcement escalations
- Release approval

### Maintainers

≥ 3 named, from ≥ 2 institutions. M0 deliverable; without 3 signed maintainers, M1 does not start.

Each maintainer:
- Has commit privilege to `main`
- Owns ≥ 1 module (per CODEOWNERS)
- Reviews PRs in their owned module
- Co-signs releases

Bus factor target: **≥ 2 reviewers** for every core module
(`wedm`, `preprocess`, `hydro`, `habitat`, `passage`, `studyplan`).

### Release Manager

One named member of maintainers. Rotating annually.

Owns:
- Release cadence (quarterly)
- CHANGELOG curation
- Tag, sign, and announce releases
- Cross-version regression checks

### Reviewers-of-Record (per SPEC §14.3)

For regulatory output templates (CN-SL712 / US-FERC / EU-WFD), one external expert per framework is acknowledged in M2 evaluation. They are not maintainers but are credited in the GMD model description paper.

## Decision-making

| Decision type | Process |
|---|---|
| Code change in 1.0 scope | 1 maintainer review approval; 2 for security or migration code |
| Release approval | ≥ 2 maintainers sign-off |
| New maintainer | PSC majority vote |
| SPEC change (1.0 scope) | SPEC change proposal + PSC majority vote |
| Conflict of interest | Recuse from vote |
| Tie | Release manager has tie-breaker on technical decisions; PSC chair on governance |

## SPEC change process

1. File `SPEC change proposal` issue using template in `docs/governance/SPEC_CHANGE_PROPOSAL.md`
2. Public comment period: ≥ 14 days
3. PSC vote
4. If accepted: update SPEC.md with new version (e.g., v0.5 → v0.6) and update Appendix B history table

Items in **§13 Research Roadmap** can move to a `research-*` branch without SPEC change. Moving FROM §13 INTO 1.0 scope requires a SPEC change.

## Release cadence

- **Quarterly minor releases** (1.x): non-breaking
- **Major releases** (2.0+): only after PSC approval, with deprecation period of ≥ 1 minor release
- **Patch releases** (1.x.y): bug fixes, security
- **LTS**: every other major version is LTS, with bug fix support for 24 months

## Deprecation policy

Any public API in `openlimno.*` must:
1. Be flagged with `DeprecationWarning` for ≥ 1 minor release before removal
2. Have a documented migration path
3. Have a CHANGELOG entry in both deprecation and removal release

Internal API (`openlimno._*`, `_*` modules) has no such guarantee.

## Bus factor / continuity

If a maintainer disappears for > 3 months:
- PSC may transfer their CODEOWNER responsibilities
- Their commit privilege is suspended after 6 months (re-grantable on request)

If maintainer count drops below 3:
- 1.0 release blocked until restored
- Project enters "dormant maintenance" mode (only security and critical bug fixes accepted)

## Funding & dormant mode

If funding for primary maintainers ends:
- Release manager publishes a "dormant mode" notice to README
- Documentation site stays online for ≥ 24 months
- No new features accepted; bug fixes welcomed
- Project is not declared dead until 24 months of zero commit activity

## Public meetings

Monthly PSC meeting, agenda public, minutes archived in `docs/governance/meetings/`.

## Amendments

Amendments to this document require: PSC majority vote + 14-day public comment period.

---

**Status**: Draft, M0 deliverable. To be ratified at first PSC meeting.

**Last updated**: 2026-05-07
