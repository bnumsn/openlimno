# ADR-0011: Moratorium on stable major-version tags until D1+D2+(D5∨D6∨D7) close

- **Status**: Accepted (interim; ratify at first PSC meeting)
- **Date**: 2026-05-19
- **Deciders**: acrochen (project author); confirmed by codex + claude
  triple-AI strategic review (gemini upstream-capacity-exhausted at the
  time of review)
- **SPEC sections**: SPEC.md §0.2 / §10 / §13; CAPABILITY_BOUNDARY_1_0.md D1-D8
- **Tags**: [governance, release, scope-discipline]

## Context

OpenLimno tagged `v1.0.0` (2026-05-12), `v2.0.0`, and `v3.0.0` …
through `v3.6.1` (2026-05-19), totalling 30+ public release tags. The
`docs/governance/CAPABILITY_BOUNDARY_1_0.md` Definition-of-Done for the
1.0 release line lists D1–D8 criteria — three named maintainers signed,
PSC signatures, three-platform CI green for ≥ 30 days, SCHISM container
published, PHABSIM Fortran bit-level regression on one real run, one
real basin case study, three regulatory reviewers-of-record signed,
QGIS plugin manually validated on LTS 3.34 + 3.40. As of 2026-05-19,
**zero** of D1, D2, D5, D6, D7 are closed (D3/D4/D8 partial).

The 2026-05-19 plan-level strategic review (codex S1, S6, S7, all
CHARTER-BLOCKING; claude concurring) reached this verdict:

> "Version numbers are trust signals. Right now they encode internal
> engineering milestones, not external readiness."

The v3.x line shipped 19 hardening-only ships (R11-4 sandbox, R13-3
ruamel, R15-4 TOCTOU, R16-1 AEQD sausage-gap, R17-x edge cases, R18-x
fd / antimeridian / magnitude). All real engineering work, none of it
charter-evidence work. Continuing to mint `v3.7+` / `v4.0+` tags on
the same trajectory entrenches the disconnect between public version
numbers and external readiness.

The forces:

- **Technical**: the code is healthy and review-validated; no
  correctness emergency forces a tag.
- **Charter**: the 1.0 charter is explicit and signed off in SPEC v0.5
  on the "what 1.0 means" wording (`SPEC.md` §0.2/§0.3). The DoD doc
  exists. Re-defining "stable" to mean "passes lint + the internal
  test suite + 18 rounds of review" silently rewrites that charter.
- **Regulatory**: a single SL-712 / FERC / WFD reviewer-of-record
  audit, if it finds the public 1.0 tag doesn't match the DoD, is
  reputational damage no further engineering polish can fix.
- **External users**: there are still **zero** confirmed external users
  (no D6 basin signed). Continuing to tag major versions for no users
  is pure ceremony.

## Decision

**No new `vN.0.0` stable major-version tags will be cut** until ALL of
the following close:

1. **U1** — at least 3 named maintainers signed in MAINTAINERS.md (closes D1)
2. **U2** — CAPABILITY_BOUNDARY_1_0.md ratified (closes D2)
3. At least ONE of:
   - **U3** — PHABSIM Fortran real-run Δ ≤ 1e-3 (closes D5)
   - **U4** — One real basin case study published (closes D6)
   - **U5** — At least one regulatory reviewer-of-record signed (closes D7)
4. **U6** — Production-caller audit pass on the R-numbering ledger

(U6 is a process gate; U1+U2 are the necessary governance floor;
U3∨U4∨U5 is the sufficient evidence gate.)

While the moratorium is active:

- **Minor and patch tags are permitted** ONLY for (a) bugfixes that
  cite a real reported bug; (b) documentation; (c) audit/sync work
  advancing the unfreeze gate. They are NOT permitted for "harden
  existing path without new logic" ships.
- **Reviews follow the new cadence rule** in
  [`feedback_review_cadence`](../../.claude/projects/-mnt-data-openlimno/memory/feedback_review_cadence.md)
  (author memory, to be promoted to a repo policy doc at the same
  time as MAINTAINERS.md is signed).

When the gate lifts, the **next stable major tag is `v4.0.0`** —
honest semver, marking a real "we are charter-ready now" break point.
A v3.6.x patch line continues to receive bugfix tags but no minor bumps.

**Alternative under discussion**: revert the public-facing line to
`0.x` or `1.0.0-rc.N` and explicitly relabel v1.0–v3.6.1 as
"engineering pre-GA snapshots" in retroactive release notes. This
is a stronger signal but breaks any existing `pixi.lock` / wheel
pinning that may already be in flight. Decision deferred to first
maintainer sync.

## Alternatives considered

### Alternative A — keep tagging v3.7+/v4.0+ on the current trajectory
- Pros: simpler; preserves "release momentum"; less doc churn.
- Cons: version numbers continue to drift from external readiness;
  one regulatory audit closes the project. Charter-blocking per
  codex S1 / S6 / S7.

### Alternative B — tag v3.7+ only after every review-chain finding lands
- Pros: visible "review pays off" cadence.
- Cons: this is precisely what produced the current problem (codex
  S2: "review chain has become the product"). Doubles down on the
  failure mode.

### Alternative C — split into `openlimno-core` (lib, semver) and
  `openlimno-distribution` (versioned by 1.0 milestone)
- Pros: clean separation of "lib that's healthy" from "release that
  isn't ready".
- Cons: distribution churn, two repositories to maintain, doesn't
  exist yet, and we have one author. Defer this option until U1
  (≥ 3 maintainers) closes.

## Consequences

### Positive
- Version numbers regain meaning. The next `v4.0.0` will signal real
  external readiness, not internal cleanup motion.
- Engineering effort redirects from hardening already-passing
  infrastructure toward unblock-the-gate work (PHABSIM real, basin
  case, reviewer outreach, doc audit). All of these advance the
  charter; none of them produce new R-numbered findings.
- The review chain remains valuable (it caught R18-1, a real fd-reuse
  bug, and R18-2/3 real geometry bugs) — it just stops being the
  sole reason ships happen.

### Negative
- "Release momentum" — perceived activity, internal motivation —
  drops. The user must value charter closure over visible tagging
  cadence.
- Some R-numbered deferred items (R17-6 source-pin rewrite, R16-4
  full antimeridian split for very long polylines, R17-8 test gaps)
  go into "patch when needed" mode rather than "next minor's
  backlog". They may sit unaddressed for months.

### Neutral / Acknowledged trade-offs
- The choice between `v4.0.0` and `0.x reset / 1.0.0-rc.N` is
  deferred. Either path is defensible; the moratorium itself does
  not pick.
- "Patches OK if they cite a real bug" leaves a judgement call to
  the maintainer. With ≥ 3 maintainers (U1), this becomes a peer
  review; with one author, it's a discipline test.

## Implementation notes

- This ADR is the authoritative reference for "are we frozen?"
  questions until U1+U2 close.
- The unfreeze gate lives in [`docs/ROADMAP.md`](../ROADMAP.md) §
  "How to unfreeze". When U1+U2+(U3∨U4∨U5)+U6 all close, append
  ADR-0013 (or whatever number) "Lift the moratorium" with the
  evidence; do not edit this ADR.
- CHANGELOG entries for patch ships during the moratorium MUST
  include the line "Moratorium-compliant: cites <bug-report-URL>
  OR advances unfreeze gate <U-N>" so future readers can confirm
  the patch wasn't ceremony.
- Track `R-PHABSIM-REAL` (closes U3) is its own work; see
  [ADR-0012](0012-phabsim-real-fortran-validation.md).

## References

- 2026-05-19 plan-level strategic review (codex output, claude补位):
  see `docs/reviews/MASTER_INDEX.md` § "Round S (strategic)".
- `docs/governance/CAPABILITY_BOUNDARY_1_0.md` (D1-D8).
- `SPEC.md` §0.2 / §0.3 / §10 / §13.
- `feedback_review_cadence` author memory rule.
- Prior art on "stop tagging until you ship something" — NumFOCUS
  governance template; LLVM/Clang release strategy (rc cycles).
