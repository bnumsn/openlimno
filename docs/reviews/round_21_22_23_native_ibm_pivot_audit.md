# Rounds 21-23 Triple-AI Review — Native IBM Pivot Audit

> Three rounds of triple-AI strategic review (codex + gemini +
> claude) conducted 2026-05-26 in response to a 6-day accumulation
> of ~10,000 LOC native IBM / GIS hydraulics / HEC-RAS mesh /
> calibration work during the ADR-0011 moratorium.
>
> Convergent verdict: **Option Z** — quarantine to
> `experiment/native-ibm-pivot` branch; main returns to
> moratorium-clean state; ratification packet (SCP-0001 +
> ADR-0014 + ADR-0015) drafted here; 90-day deadline (2026-08-26)
> for PSC vote or branch archival.

## Round 21 — Drift Audit (2026-05-26)

### Question

Did the project just charter-violate itself in 6 days, or has the
charter quietly changed?

### Codex verdict (CHARTER-BLOCKING)

> "A in substance, C as the escape hatch": real feature surface,
> charter has NOT changed via any valid amendment. SPEC.md §0.3
> still forbids IBM/ABM in 1.0; ADR-0011 still allows only
> bugfix/doc/audit; new strategy docs are not governance
> amendments. Tracked diff is 10,168 insertions / 670 deletions
> excluding untracked. The work is wired into CLI, docs, packaging,
> mkdocs navigation — public product surface, not dormant
> experiment.
>
> **Recommended action**: SEGMENT today (move to quarantine
> branch); restore main to moratorium-clean. CODIFY later only
> if willing to formally amend SPEC + ADR-0011 + external-action.

### Gemini verdict (CHARTER-BLOCKING × 2)

> "Interpretation B + C": legitimate strategic pivot but bypassed
> governance entirely. The code quality is excellent ("highly
> intentional, production-grade feature build" — wrong,
> prototype-grade per codex D4) and the strategic direction is
> defensible (inSTREAM 7 successor). But if merged to main without
> SPEC update + moratorium revocation, the governance documents
> become fiction.
>
> **Recommended action**: SEGMENT AND CODIFY — feature branch
> + formal SPEC amendment + new ADR; don't merge until ratified.

### Claude (synthesis) verdict

> Closer to codex, stricter than gemini. The charter expansion is
> plausible but unratified. The work shows systematic intent (CLI
> registration, packaging, mkdocs nav, 4 example basins) — not
> "weekend experiment". 9,400 LOC IBM + 851 hydro + 223 HEC-RAS
> mesh = sustained product planning. SPEC §0.3 + ADR-0011 +
> external_action_phase = 3 governance lines, all violated.

### Round 21 TL;DR

- ✅✅✅ All three reviewers: real charter violation, code is
  prototype-quality, recommended action is SEGMENT (not delete,
  not decree).
- The work is too good to discard but too unratified to merge.
- Next action: branch + draft ratification packet.

## Round 22 — IBM/GIS Architecture Critique (2026-05-26)

### Scope

Assume the work is going to live somewhere. Critique its
architecture on its merits, not on charter compliance.

### Convergent HIGH findings (codex + gemini)

| Finding | Codex | Gemini |
|---|---|---|
| API sprawl (`ibm/__init__.py` exports 47 symbols) | A2 HIGH | A2 MEDIUM |
| Provenance fork (`ibm_run_manifest.json` ≠ `provenance.json`) | A5 HIGH | A4 HIGH |
| Third Studio surface (browser stdlib http.server) | A6 HIGH | A5 HIGH |
| God-object pattern (studio.py 3,286 LOC; instream7.py 1,830) | A10 HIGH | A9 HIGH |
| Missing workbench features (no calibration report, no parallel exec) | A11 HIGH | A10 MEDIUM |
| HydroSolver protocol leakage entrenched | A4 MEDIUM | A3 HIGH |
| CLI grammar split (`ibm-run-native` flat ⨯ `openlimno ibm scenario` nested) | A3 MEDIUM | A2 MEDIUM |
| Schema fork (`ibm/schemas/` parallels `wedm/schemas/`) | A7 MEDIUM | A6 LOW |
| Test discipline (no seed→identical, fixture-absence-defaults-warning) | A8 MEDIUM | A7 HIGH |

### Merge-readiness verdict

- **Codex**: "if charter-ratified, merge only after **major
  redesign**. Not AS-IS; not NEVER."
- **Gemini**: "merge readiness: **NEVER** (as-is). Requires
  **major redesign** to shred god objects, unify schemas, and hook
  into the standard Case pipeline."
- **Claude**: codex correct. Code skeleton is salvageable; current
  shape is not mergeable.

### Round 22 TL;DR

- IBM/GIS code is technically valuable but architecturally
  parallel to OpenLimno's Case/WEDM/provenance/Studio systems.
- Biggest risks: API sprawl, provenance fork, third GUI surface,
  oversized modules.
- Tests are real in places, but official parity and deterministic
  reproducibility are not yet strong enough.

## Round 23 — Synthesis + 90-day plan (2026-05-26)

### Decision (100% convergent: codex + gemini + claude)

**Option Z** — quarantine to `experiment/native-ibm-pivot`
branch + draft codification packet in parallel.

### Why Z and not X/Y

- **Not X (delete)**: 9,400 LOC of legitimate strategic work too
  valuable to discard.
- **Not Y (decree)**: bypassing the governance the author just
  wrote signals all governance is theatre. Future maintainers
  would correctly infer process is decorative.
- **Z**: separates three questions cleanly:
  1. Can the project keep the prototype? Yes, on branch.
  2. Can main remain honest? Yes, IBM leaves main.
  3. Can the pivot become real later? Yes, via SCP/ADR + PSC vote.

### Commit sequence executed 2026-05-26

```
git switch -c experiment/native-ibm-pivot
git add -A
git commit -m "experiment: quarantine native IBM pivot per rounds 21-23 triple-AI review"
# → 402 files staged; commit d960493

# Then on experiment branch:
# docs/governance/spec-change-proposals/0001-native-ibm-pivot.md
# docs/decisions/0014-charter-pivot-native-ibm.md
# docs/decisions/0015-ibm-moratorium-exception.md
# docs/reviews/round_21_22_23_native_ibm_pivot_audit.md  (this file)
git commit -m "docs: draft native IBM pivot ratification packet"

# Return to main:
git switch main
# Working tree clean at 40a6e73 (round-20 SCHISM fix)

# On main, add quarantine notice:
# docs/reviews/native_ibm_pivot_quarantined.md
git commit -m "docs: quarantine notice — native IBM pivot moved to experiment branch"
```

### 30-day milestone (T+30 = 2026-06-25)

**Branch architectural triage + governance seeding**:

- SCP-0001 fleshed out with concrete §13.x amendment text
- ADR-0014 + ADR-0015 reviewed by ≥ 1 external party (even
  informal)
- `ibm/__init__.py` `__all__` shrunk to ≤ 10 stable contracts
- `studio.py` shredded into routing / API / view / core layers
- `instream7.py` shredded into parser / runner / benchmark layers
- Third-Studio decision made: delete browser path, demote to
  dev-only, or integrate behind PyQt6 Studio shell
- Seed → identical-output regression test added
- U1 maintainer recruitment outreach started using the
  experiment branch as a "preview" of strategic direction

### 60-day milestone (T+60 = 2026-07-25)

**Rigor + unification**:

- IBM provenance unified into `Case.provenance.json` (no separate
  `ibm_run_manifest.json`)
- Formal calibration report artifact exists; identifiability
  diagnostics tested
- Parallel execution: either implemented or explicitly deferred
  with rationale
- One minimal end-to-end IBM example runs through CLI/workbench
  with deterministic output
- Draft maintainer review packet prepared: scope delta,
  architecture delta, risk register, acceptance criteria
- U1 has 1-2 serious maintainer candidates

### 90-day milestone (T+90 = 2026-08-26)

**Ratification or archival**:

- Code on `experiment/native-ibm-pivot` is fully compliant with
  round-22 architectural findings
- U1 closes (≥ 3 maintainers signed) or becomes the blocker
- U2 PSC formed and votes on SCP-0001 + ADR-0014 + ADR-0015
- Outcome A — Ratified: cherry-pick onto main as v4-target
  capability per ADR-0014 § "Implementation notes"
- Outcome B — Rejected: branch enters archival mode; no merge
  expectation; main untouched
- Outcome C — Deferred: ADR-0015 deadline amended; new 90-day
  window with explicit reasoning

### Decision matrix (codex + gemini convergent)

| Gate | T+30 | T+60 | T+90 |
|---|---|---|---|
| **U1** ≥ 3 maintainers | Outreach active; 0-1 candidates | 1-2 candidates committed | Closes OR is the blocker |
| **U2** PSC + CAPABILITY_BOUNDARY | Drafts ready; not ratified | Reviewable boundary | Ratified OR IBM stays experimental |
| **U3** PHABSIM real run | No change (waits USFWS source) | Harness only if external input | Likely still open |
| **U4** real basin | Data path selected | Pipeline active | Draft evidence unlikely published |
| **U5** SL712 reviewer | Outreach should START | Plausible signed review | **Most likely gate to close** |
| **U6** production audit | Holds on main; experiment branch self-audits | Branch audit ledger | Required before any IBM merge |

### Pushbacks (codex + gemini convergent)

| User instinct | Cost |
|---|---|
| Y: decree (just amend the docs alone) | Governance credibility. Maintainers won't join a project where the author writes strict rules and immediately breaks them. |
| X: delete everything | Strategic loss + author burnout. 9,400 LOC of inSTREAM-successor work erased because governance failed once is overcorrection. |
| Z: branch + drafts (chosen) | Branch rot risk + rebase pain. Drafts decay unless someone owns them weekly. **rebase pain is temporary; lost trust from broken governance is permanent.** |

### Round 23 TL;DR

- Shift to experimental branch immediately; remove the unratified
  10K LOC from main without destroying the work.
- Draft governance ratification (SCP + ADRs) on the branch,
  forcing the design to mature while waiting for PSC to exist.
- Spend 90 days redesigning the code so when the PSC IS ready to
  vote, the code is worthy of being merged.

## Author's commitment

By committing this audit to the experiment branch, the project
author (acrochen) acknowledges:

1. The 2026-05-20 → 2026-05-26 work violated three governance
   documents the author wrote himself (SPEC §0.3, ADR-0011,
   external_action_phase.md).
2. The work itself is technically valuable and strategically
   defensible, which is precisely why the response is quarantine
   not deletion.
3. Until SCP-0001 + ADR-0014 + ADR-0015 ratify, IBM development
   stays on `experiment/native-ibm-pivot`. No silent cherry-picks
   to main.
4. At T+90 (2026-08-26), the project either has PSC vote +
   merge-ready code, OR the branch becomes archival. Drift
   without a vote IS a recidivism violation.

## See also

- [SCP-0001](../governance/spec-change-proposals/0001-native-ibm-pivot.md) — SPEC amendment proposal
- [ADR-0014](../decisions/0014-charter-pivot-native-ibm.md) — strategic rationale
- [ADR-0015](../decisions/0015-ibm-moratorium-exception.md) — moratorium relationship
- ADR-0011 — moratorium being qualified, not revoked
- SPEC.md §0.3 — non-goal being amended
- `docs/external_action_phase.md` — original phase declaration (also
  qualified by ADR-0015 once ratified)
- `docs/strategy/native-ibm-instream-successor.md` (this branch) —
  original strategic prose
- `docs/strategy/ibm-redesign.md` (this branch) — design target for
  the workbench
