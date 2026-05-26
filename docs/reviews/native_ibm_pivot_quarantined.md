# Native IBM Pivot — Quarantined to `experiment/native-ibm-pivot`

> **⚠️ SUPERSEDED 2026-05-26 by [ADR-0016](../decisions/0016-author-override-direct-merge.md)
> (author override).** This notice was committed at `e15df96` recording
> Option Z (quarantine to experiment branch, hold for PSC vote). Approximately
> one minute later, the author overrode that decision and merged
> `experiment/native-ibm-pivot` into main at `cfb4960`. The text below is
> preserved verbatim as historical record of the Option Z decision the
> author chose AGAINST. Read [ADR-0016](../decisions/0016-author-override-direct-merge.md)
> for the override rationale and accepted costs.

> **Posted on `main` 2026-05-26 (now superseded).** This is a short notice. The
> substantive review chain lives on the `experiment/native-ibm-pivot`
> branch at
> `docs/reviews/round_21_22_23_native_ibm_pivot_audit.md`.

## What happened

Between 2026-05-20 and 2026-05-26 the project author (acrochen)
prototyped ~10,000 LOC of native individual-based modeling (IBM)
work in the working tree on `main`:

- `src/openlimno/ibm/` (~9,400 LOC; native IBM engine + inSTREAM 7
  parsers/benchmarks + browser-based IBM Studio + scenario /
  profile / ensemble / calibration / acceptance runners)
- `src/openlimno/hydro/{calibration.py, gis_hydraulics.py}`
  (~850 LOC)
- `src/openlimno/preprocess/hecras_mesh.py` (~220 LOC)
- 11+ new test files (864 tests collected, up from 705)
- 4 new example basin directories (Boise Glenwood, Yakima Kiona,
  Truckee Reno, Delaware Trenton, Wallens Bend)
- Modifications across cli.py, case.py, hydro/, preprocess/,
  wedm/, pyproject.toml, README, ADR-0011, external_action_phase.md

This work violated three governance documents the same author
wrote earlier:

- **SPEC.md §0.3** — "个体行为模型 (IBM/ABM) / 种群动力学"
  is an explicit 1.0 non-goal
- **ADR-0011** — moratorium permits only bug-fix-with-external-
  citation / doc / U3-container / U6-audit work
- **`docs/external_action_phase.md`** — "No new feature work in
  src/ until U1+U2 close"

## What we did about it

Three rounds of triple-AI strategic review (codex + gemini +
claude, 2026-05-26) converged 100% on **Option Z**:

> Quarantine the unratified work to a branch; draft a formal
> ratification packet there; do not merge to main until PSC
> (per GOVERNANCE.md § Decision-making) ratifies SPEC amendment
> + new ADRs; hard 90-day decision deadline (2026-08-26).

Executed sequence:

1. Created `experiment/native-ibm-pivot` from the dirty working
   tree at `40a6e73`.
2. Committed all 402 modified/new files to the branch
   (commit `d960493`).
3. Drafted the ratification packet on the branch:
   - `docs/governance/spec-change-proposals/0001-native-ibm-pivot.md`
     (formal SPEC change proposal)
   - `docs/decisions/0014-charter-pivot-native-ibm.md`
     (strategic rationale)
   - `docs/decisions/0015-ibm-moratorium-exception.md`
     (narrowly-bounded moratorium exception)
   - `docs/reviews/round_21_22_23_native_ibm_pivot_audit.md`
     (full 3-round audit)
   (Commit `325c303` on the branch.)
4. Returned `main` to `40a6e73` (round-20 SCHISM fix; the last
   moratorium-clean commit).
5. Added this notice as the only main-side record (this commit).

## What this means for main

- `main` remains at the round-20 SCHISM-no-silent-fallback state
  (commit `40a6e73`).
- ADR-0011 moratorium remains in force.
- `docs/external_action_phase.md` remains in force.
- SPEC §0.3 remains unchanged.
- 705 default tests pass; 1 pre-existing env-drift fail
  (`test_v2101_format_checker_wired_uri_reference`).
- No IBM code, no IBM docs (other than this notice), no IBM API
  surface on main.

## What happens next

Per ADR-0015 (DRAFT, on the experiment branch):

| Date | Milestone |
|---|---|
| **T+30: 2026-06-25** | Branch architectural triage: `ibm/__init__.py` `__all__` reduced; `studio.py` + `instream7.py` shredded; third-Studio decision; seed→identical regression test |
| **T+60: 2026-07-25** | Provenance unified to Case chain; formal calibration report; identifiability diagnostics; parallel execution decision; one minimal end-to-end IBM example |
| **T+90: 2026-08-26** | PSC vote on SCP-0001 + ADR-0014 + ADR-0015. **Ratified** → cherry-pick to main. **Rejected** → branch archival. **Deferred** → ADR-0015 deadline amended |

## How to read this notice in 6 months

If you are a future maintainer or reviewer looking at this file:

- The work that produced this notice is preserved at
  `experiment/native-ibm-pivot` (commits `d960493` and `325c303`).
- The 3-round triple-AI review process is documented on the
  experiment branch at
  `docs/reviews/round_21_22_23_native_ibm_pivot_audit.md`.
- The ratification status of the IBM pivot is recorded in
  ADR-0014 / ADR-0015 on the experiment branch.
- If neither ratification nor archival happened by 2026-08-26,
  that itself is a process-drift finding worth a future round.

## Honest acknowledgement

The 6-day work pattern (write strict moratorium → immediately
violate it) was a real governance failure. This quarantine
preserves both the strategic value of the IBM work AND the
credibility of the project's stated governance — neither at the
expense of the other, per round-23's "Option Z" verdict.

The cost of this approach is **branch-rot risk + rebase pain**,
acknowledged in ADR-0015. The 90-day deadline is the hedge
against drift becoming permanent.
