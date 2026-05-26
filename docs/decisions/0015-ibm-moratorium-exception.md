# ADR-0015: Moratorium relationship for the native IBM experiment

- **Status**: DRAFT on `experiment/native-ibm-pivot` (paired with
  ADR-0014; ratification requires PSC vote on SCP-0001)
- **Date**: 2026-05-26
- **Deciders**: acrochen (proposed)
- **SPEC sections**: SPEC.md §0.3; ADR-0011; external_action_phase.md
- **Tags**: [moratorium, governance, ibm, scope-discipline]

## Context

ADR-0011 (2026-05-19) established a stable-major-tag moratorium
with strict source-modification rules. The author wrote it 6 days
before adding ~10,000 LOC of native IBM work — a sequence both
codex and gemini round-21 reviews flagged as a CHARTER-BLOCKING
violation.

This ADR resolves the relationship between the moratorium and
the IBM experiment. Two extreme positions are NOT taken:

- ❌ **Lift the moratorium** to legitimize the IBM work: bypasses
  the U1+U2 governance gate that ADR-0011 protects. Round-23
  rejection of "Option Y decree mode" applies here.
- ❌ **Tighten the moratorium** to delete the IBM work: round-23
  rejection of "Option X delete everything" applies. The work is
  too valuable to discard solely as a discipline gesture.

Instead, this ADR makes the experiment branch a **narrowly bounded
exception**: development continues there, `main` stays moratorium-
clean.

## Decision (proposed)

ADR-0011's "What halts (code-side)" section is **amended on the
experiment branch only**, effective when this ADR is PSC-ratified,
to add:

> Exception E1 — `experiment/native-ibm-pivot` branch:
>
> Development of the native IBM pivot may proceed on the
> `experiment/native-ibm-pivot` branch under these conditions:
>
> 1. **No fast-forward / no force-push to main.** The branch
>    diverges from main at the commit recorded in the
>    quarantine note and stays divergent until SCP-0001 ratifies.
> 2. **No silent cherry-pick to main.** Any IBM-code commit
>    cherry-picked onto main must cite SCP-0001 ratification SHA
>    in its message.
> 3. **Architectural blockers from round-22 must close before
>    ratification.** Provenance unification, god-object split,
>    API sprawl reduction, schema fork resolution, third-Studio
>    decision, seed→identical reproducibility test. These are
>    audit-checked on the branch.
> 4. **Hard 90-day decision deadline (2026-08-26).** PSC vote on
>    SCP-0001 OR the branch goes into archival mode (continued
>    work allowed; no merge expectation).
> 5. **No new IBM development outside this branch.** Once this
>    exception ratifies, IBM work that isn't on this branch is
>    a recidivism violation, not a fresh charter question.

`external_action_phase.md` § "What continues (code-side, narrowly)"
gains a fourth bullet (per ratification):

> 4. **Native IBM development on `experiment/native-ibm-pivot` per
>    ADR-0014 + ADR-0015.** This is a bounded exception, NOT a
>    moratorium lift.

`main` continues to enforce the original "What halts" list. The
exception is branch-scoped, not project-scoped.

## What this is NOT

- Not a precedent for "if you do enough work on a branch, the
  moratorium will give way." Future similar exceptions require
  fresh SCP + fresh ADR. The IBM pivot is exceptional because of
  the strategic opportunity (inSTREAM 7 succession) AND the work
  already done (preventing destruction of legitimate effort).
- Not a relaxation of round-19 / round-20 audit findings. Round-22
  HIGH-severity blockers must close before any merge candidate.
- Not a pre-approval of merge. The experiment branch may close
  with a "reject" vote and stay isolated indefinitely. The user
  must accept this outcome as possible.
- Not a defense of the original 6-day violation. The work itself
  *was* a charter violation. This ADR provides a path forward
  that doesn't compound the violation by either rewarding it (Y)
  or destroying its product of value (X).

## Alternatives considered

### A — No exception (strict ADR-0011)

- Pros: cleanest discipline; future maintainers see no precedent
  for bypassing
- Cons: forces the 9,400 LOC onto a permanent /dev/null path;
  loses the inSTREAM 7 opportunity; codex+gemini round-23 rejected

### B — Full moratorium lift via ADR-0011 amendment

- Pros: simplest; "just admit the moratorium was wrong"
- Cons: governance theatre risk; both AI reviewers rejected;
  destroys credibility of any future moratorium

### C — This ADR: narrowly bounded experiment-branch exception

- Pros: preserves work + preserves discipline; codifies the
  branch's purpose; sets a hard deadline
- Cons: requires PSC ratification to take effect (and PSC doesn't
  exist yet); during the gap, the experiment branch is
  procedurally illegitimate

### D — Defer the question to first PSC meeting

- Pros: maximally honest about the lack of PSC
- Cons: leaves the experiment branch in an undefined state
  indefinitely; encourages drift back to silently editing the
  rules

## Consequences

### Positive (when ratified)

- The 9,400 LOC has a defined path to legitimacy.
- `main` remains moratorium-clean per ADR-0011.
- Future maintainers see an honest sequence: violation flagged →
  triple-AI review → branch quarantine → ratification packet →
  PSC vote. They join a project that demonstrably catches itself.

### Negative

- This ADR cannot take effect until PSC exists. During the gap,
  the experiment branch is "draft-status code under draft-status
  ADR" — minimally legitimate.
- The 90-day deadline (2026-08-26) is aggressive given that PSC
  recruitment has not started in earnest. May need amendment to
  this ADR to extend.

### Neutral / Acknowledged trade-offs

- ADR-0011's wording is preserved. This is an *exception clause*,
  not a re-write.
- The experiment branch's `main`-divergence will grow over time
  (more commits, more refactor). Cherry-picking back at ratify-time
  becomes harder. This is the acknowledged cost.

## Implementation notes

When PSC ratifies, the following commits land:

1. **On `main`**: append the Exception E1 text to ADR-0011 (small edit,
   not a rewrite).
2. **On `main`**: append item 4 to `external_action_phase.md` §
   "What continues".
3. **On `experiment/native-ibm-pivot`**: ratification SHA added to
   ADR-0015's status header.

If PSC rejects, this ADR moves to status "Rejected" and the
experiment branch enters archival mode (existing commits
preserved; no new commits or no new commits beyond archival
maintenance).

## References

- ADR-0011 — moratorium being qualified, not revoked
- ADR-0014 — strategic rationale for the pivot
- SCP-0001 — formal SPEC amendment proposal
- `docs/reviews/round_21_22_23_native_ibm_pivot_audit.md` — review
  chain
- `docs/external_action_phase.md` — original phase declaration
