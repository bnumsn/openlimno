# ADR-0016: Author override — direct merge of IBM pivot to main

- **Status**: Accepted (author decision; 2026-05-26)
- **Date**: 2026-05-26
- **Deciders**: acrochen (author override)
- **SPEC sections**: SPEC.md §0.3; ADR-0011; ADR-0014; ADR-0015
- **Tags**: [governance, override, ibm, accepted-cost]

## Context

On 2026-05-26 a three-round triple-AI strategic review (codex +
gemini + claude) converged 100% on **Option Z**: quarantine the
~10,000 LOC IBM/GIS/calibration drift to
`experiment/native-ibm-pivot`, draft SCP-0001 + ADR-0014 + ADR-0015
on that branch, hold for PSC vote at 2026-08-26 hard deadline.

That sequence was executed cleanly (commits `e15df96` on main,
`d960493` + `325c303` on the experiment branch; both pushed to
origin).

**Approximately one minute later**, the project author overrode
that decision and directed: "全部合并到 main" — merge everything
to main, then evaluate the software.

This ADR records the override decision honestly so that future
auditors and maintainer candidates reading the git log can see
the full trail, not just the merge.

## Decision

The author exercises BDFL (benevolent dictator) authority and
directs the merge of `experiment/native-ibm-pivot` into `main` via
`git merge --no-ff` (commit `cfb4960`), bringing ~10K LOC of native
IBM + GIS hydraulics + calibration + HEC-RAS mesh + 4 example
basins + 11 new test files onto the release line.

This is **Option Y "decree mode"** that both codex and gemini
explicitly rejected in their round-23 reviews. The author accepts
the documented governance costs.

## Costs accepted by this override (NOT minimised)

### 1. SPEC §0.3 silently violated on main

SPEC.md v0.5 §0.3 still reads:
> 下列能力**明确不在 1.0**, 防止范围蔓延:
> - 个体行为模型 (IBM/ABM) / 种群动力学

This text remains. Yet `src/openlimno/ibm/` is now on main. The
written charter and the actual codebase now disagree until a
formal SPEC amendment (SCP-0001) closes via PSC vote.

### 2. ADR-0011 moratorium silently violated on main

ADR-0011 § "What halts (code-side)" reads:
> No new feature work in src/ until U1+U2 close.

U1+U2 have not closed. Native IBM is new feature work. The
moratorium text remains on main; the practice has overruled it.

### 3. `external_action_phase.md` silently violated on main

The same 2026-05-20 doc says "No new feature work in src/ until
U1+U2 close" — author-written, now author-violated, on main.

### 4. SCP-0001 + ADR-0014 + ADR-0015 status now obsolete

The ratification packet (drafted 2 commits before this override)
described a 90-day deferred-decision process. That process is now
moot — the merge happened on day zero without PSC review. The
documents remain on main but their core premise (90-day
deferred ratification) is contradicted by the merge graph.

### 5. AI convergence verdict explicitly disregarded

Codex round-23 pushback (Option Y → "the cost is governance
credibility... future contributors will correctly infer that
process applies only when convenient") and gemini round-23
pushback ("you cannot bootstrap a consensus-driven governance
model by immediately bypassing it") were both read and accepted
as documenting REAL costs, then chosen anyway.

### 6. Future maintainer-recruitment friction

When U1 outreach goes out, candidates may read this ADR + the
round 21-23 audit doc + the merge graph and conclude that
governance discipline at OpenLimno is unilateral. The author
accepts that some candidates will decline on this basis.

## Why this decision anyway

The author's reasoning (recorded for honesty, not as
justification):

1. **Strategic urgency over process integrity.** The
   inSTREAM-7-successor opportunity is judged time-sensitive. A
   90-day deferred-decision window risks losing prototype
   momentum and decay of the 6-day work.

2. **No actual PSC exists to override.** ADR-0015's "PSC vote"
   gate is, today, a vote of zero people. The 90-day deadline
   would lapse without a vote regardless. Quarantine on the
   experiment branch ends up as "indefinitely-deferred" by
   default.

3. **The audit chain itself is the documentation.** Future
   maintainer candidates will see: 3-round AI review → quarantine
   commit → ratification packet → author override → ADR-0016 →
   merge. That trail is more honest than a silent slow drift.

4. **Single-author projects accept BDFL decisions.** OpenLimno
   has one author. The governance documents pretend otherwise.
   This override makes the gap explicit.

## What this ADR does NOT do

- Does NOT revoke SPEC §0.3. The 1.0 charter still excludes IBM
  on paper. The override accepts the inconsistency rather than
  hiding it.
- Does NOT revoke ADR-0011 moratorium. The moratorium remains;
  IBM is an exception authorised by this ADR; future work outside
  IBM still falls under ADR-0011 rules.
- Does NOT supersede ADR-0014 or ADR-0015. Those documents'
  strategic and process content remains relevant; only their
  "DRAFT pending PSC vote" status changes to "merged via
  ADR-0016 override; PSC ratification still pending."
- Does NOT close the Round-22 architectural-blockers backlog.
  API sprawl, provenance fork, third Studio, god-object pattern,
  missing workbench features all remain on main as POST-MERGE
  cleanup work tracked under the R-IBM-* track names.
- Does NOT magically close the unfreeze gate. U1+U2 governance
  still pending; U3 PHABSIM real run still pending; U4 real basin
  still pending; U5 SL712 reviewer still pending. U6 production-
  caller audit was closed pre-merge; the IBM additions ADD new
  audit debt that pulls U6 back open until the R-IBM-AUDIT track
  closes.

## What replaces the 90-day quarantine plan

Post-merge cleanup tracks (recorded here for future planning):

| Track | Source | Pre-condition for "cleanup done" |
|---|---|---|
| **R-IBM-PROVENANCE** | round-22 codex A5 + gemini A4 | `ibm_run_manifest.json` retired; IBM runs feed `Case.provenance.json` |
| **R-IBM-STUDIO-CONSOLIDATE** | round-22 codex A6 + gemini A5 | Third Studio decision: delete browser path / dev-only / integrate behind PyQt6 |
| **R-IBM-API-SHRINK** | round-22 codex A2 + gemini A2 | `ibm/__init__.py` `__all__` ≤ 10 stable contracts |
| **R-IBM-GOD-OBJECT** | round-22 codex A10 + gemini A9 | `studio.py` (3286 LOC) and `instream7.py` (1830 LOC) split by responsibility |
| **R-IBM-VALIDATION** | round-22 codex A11 + gemini A10 | seed→identical reproducibility test in default CI; strict-tolerance inSTREAM 7 parity; calibration report artifact |
| **R-IBM-HYDROSOLVER** | round-22 codex A4 + gemini A3 | `hydro/calibration.py` + `gis_hydraulics.py` either follow HydroSolver protocol or move to `preprocess` |
| **R-IBM-CLI-GRAMMAR** | round-22 codex A3 + gemini A2 | Either `openlimno ibm ...` nested or flat `ibm-*` prefixed, not both |
| **R-IBM-SCHEMA-UNIFY** | round-22 codex A7 + gemini A6 | `ibm/schemas/` either uses WEDM registry/format-checker or formally documents the parallel system |
| **R-SPEC-AMEND** | this ADR | SCP-0001 ratifies (PSC vote when U1+U2 close) to make SPEC §13.x text match main codebase |

These tracks are NOT timeboxed to 90 days. They are open until
addressed. The merge ships without them; cleanup happens
incrementally.

## Alternatives explicitly rejected

### A — Honour Option Z

Pros: governance integrity preserved; future maintainer trust
intact.
Cons: judged by author as "process for process's sake" given
single-author reality and no actual PSC.
Verdict: rejected for reasons in § "Why this decision anyway".

### B — Lift ADR-0011 in addition to merging

Pros: closer alignment of stated rules with reality.
Cons: would silently strip the discipline mechanism that
*still applies* to non-IBM work. Cleaner to keep the moratorium
text, document the IBM exception in this ADR, and let the
inconsistency stand as a visible audit signal.
Verdict: not chosen. ADR-0011 remains.

### C — Amend SPEC §0.3 in the same commit

Pros: stated text matches codebase.
Cons: SPEC amendments per GOVERNANCE.md require PSC vote.
Single-author amendment of a frozen v0.5 SPEC is even more
governance-overreach than this merge. Cleaner to leave §0.3
text intact + this ADR + SCP-0001's "DRAFT, awaiting PSC"
state visible.
Verdict: not chosen.

## How to read this ADR in 6 months

If you are a future maintainer or reviewer of OpenLimno:

1. The merge that brought IBM to main happened on
   `cfb4960` per this ADR's author override.
2. The audit chain that preceded it
   (`docs/reviews/round_21_22_23_native_ibm_pivot_audit.md`)
   recommended NOT to merge. The author chose otherwise.
3. The honest signal you should take from this:
   - OpenLimno has a documented strategic pivot (IBM-as-
     inSTREAM-successor) backed by real prototype code
   - OpenLimno's governance documents (SPEC, ADRs) and its
     actual behavior do not fully align — this ADR is the
     bridge that records the gap honestly
   - If you join as a maintainer and want this gap closed,
     you have authority via the GOVERNANCE.md PSC process to
     close it; until then, BDFL decisions stand

## See also

- [ADR-0011](0011-stable-major-tag-moratorium.md) — moratorium that this override partly contradicts
- [ADR-0014](0014-charter-pivot-native-ibm.md) — strategic rationale (now merged to main despite "DRAFT")
- [ADR-0015](0015-ibm-moratorium-exception.md) — process that this override bypasses
- [SCP-0001](../governance/spec-change-proposals/0001-native-ibm-pivot.md) — SPEC change proposal (now merged but still requires PSC ratification)
- [Round 21-22-23 audit](../reviews/round_21_22_23_native_ibm_pivot_audit.md) — full triple-AI review that recommended against this merge
- [Quarantine notice](../reviews/native_ibm_pivot_quarantined.md) — main-side notice from 1 commit before this merge, now superseded by this ADR
