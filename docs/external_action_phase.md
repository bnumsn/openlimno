# External-Action Phase (2026-05-20)

> **Both codex and gemini round-19 strategic reviews flagged this
> as CHARTER-BLOCKING**: "Code work substantively halted; the project
> is now bottlenecked by external action, not Python development."
> This document formalises the new phase.
>
> Effective: 2026-05-20.
> Authority: [ADR-0011 moratorium](decisions/0011-stable-major-tag-moratorium.md)
> + 2026-05-20 round-19 audit-progress review (codex + gemini S4
> dual-CHARTER-BLOCKING).

## TL;DR

**OpenLimno's code is healthy. The project is not.**

- All `pixi run check` gates green (ruff 0; mypy --strict core +
  Studio clean; 702 tests pass on the gated suite plus the 1
  pre-existing env-drift fail).
- The 4-pass R-DOC-AUDIT-WIRED track closed unfreeze-gate U6
  (production-caller audit). The "API exists ≠ capability exists"
  pattern that motivated this entire moratorium is no longer the
  blocker.
- **No internal engineering work is on the critical path to U1+U2
  or U3∨U4∨U5.** Continuing to write Python is strategically
  stagnant.

## What halts (code-side)

Effective immediately:

- **No new internal audit passes.** R-DOC-AUDIT-WIRED is
  substantively complete; further per-finding pins would be
  diminishing returns per the same codex S2 strategic-review
  argument that called the chain "the product."
- **No new infrastructure-only ships.** Per ADR-0011 plus codex
  S6 / gemini S4: hardening already-hardened paths is
  strategically empty until evidence lands.
- **No new triple-AI code-review rounds** unless they are
  triggered by:
  - A real external user bug report
  - A new public API surface change
  - A specific scientific-math or persistence-layer change
  - An external dependency forcing a behaviour update
  (per [`feedback_review_cadence`](../../.claude/projects/-mnt-data-openlimno/memory/feedback_review_cadence.md)
  author memory rule).
- **No new feature work in `src/`** until U1+U2 close. The current
  surface is more than sufficient to support a real basin case
  study and a real PHABSIM cross-check; what's missing is the
  data and the people, not the engine.

## What continues (code-side, narrowly)

Three specific code-side activities remain permitted:

1. **Bug fixes that cite an external bug report.** Per ADR-0011 §
   "While the moratorium is active" — the report must point to a
   real reporter (issue / mailing-list thread / user message),
   not an internal review chain finding.
2. **Doc updates** that advance the unfreeze gate (e.g., the very
   doc you are reading now; the round-19 corrections that
   preceded it; a future audit-doc re-base when U4 evidence
   lands).
3. **Validation harness work for U3** — specifically, the
   `benchmarks/phabsim_real/` scaffold can grow toward a working
   container if/when the USFWS PHABSIM source archive is
   acquired and license-verified. This is *external-prerequisite*
   work (license verification, archive download) gating *code-
   side* work (Dockerfile completion, input deck capture).

## What starts (external action)

In priority order:

### 1. U1 + U2 — Governance (mandatory floor)

This is the unconditional prerequisite. Per
[ROADMAP § "How to unfreeze"](ROADMAP.md#how-to-unfreeze) and
[CAPABILITY_BOUNDARY § "Signatures"](governance/CAPABILITY_BOUNDARY_1_0.md#f-signatures):

- Recruit at least 3 named maintainers from ≥ 2 institutions.
  Profile per [GOVERNANCE.md § Maintainers](governance/GOVERNANCE.md):
  one each from ecology / water-resources engineering / software
  engineering would close the role requirement.
- Recruit PSC quorum (5 members per GOVERNANCE.md): 1 ecologist,
  1 water-resources engineer, 1 software engineer + 2 at-large.
- Once both bodies are seated, ratify `CAPABILITY_BOUNDARY_1_0.md`
  via the workflow at its § F (3 maintainer sigs + 5 PSC sigs).

Outreach paths:

- **Academic ecology**: post to AFS (American Fisheries Society)
  Computers in Fisheries TC; r/fishbiology; ResearchGate Lemhi
  contributors; FishBase advisory pool.
- **Hydraulics engineering**: ASCE H&H committee; IIHR (Iowa); SAFL
  (Minnesota); China IWHR (Beijing); Wuhan University Hydroinformatics
  group.
- **Open-source software**: NumFOCUS fiscal sponsorship application
  (also unlocks funding for maintainer time); SciPy / PyData community
  via PyData talks; HydroPython community.
- **Charter-aligned CN contacts** (memory `project_openlimno` notes
  CN preference): 中科院水生生物所; 中国水利水电科学研究院 IWHR;
  长江水利委员会 / Yangtze water resources commission; 黄河水利委员会
  / Yellow River conservancy commission.

### 2. U5 — Regulatory reviewer-of-record (fastest evidence)

Codex S4 explicitly identified U5 as "likely fastest" because
review is a discrete action (not data-acquisition + processing
+ publication). The charter (`SPEC.md` §14.3) named three
reviewer-of-record slots: CN-SL712, US-FERC §4(e), EU-WFD.

Per the user-memory CN preference, **SL/Z 712-2014 is the
recommended first target**:

- Run `examples/lemhi/` end-to-end (already operational), producing
  `sl712.csv`.
- Approach an SL/Z 712 working-group member at IWHR or a 水利部
  policy office to review the artifact against the standard's
  four-tuple (monthly min / suitable / multi-year-avg% / 90%
  guarantee).
- Counterpart US: FERC §4(e) review through HKUST/Hydro Research
  Foundation or PNNL fisheries.
- Counterpart EU: WFD ecological-status review through a German
  LAWA-Forschung partner or a UK CEFAS contact.

Acceptance criterion: ONE reviewer-of-record signature in
`docs/governance/announcements/` closes U5.

### 3. U3 — PHABSIM real-Fortran run

Engineering-heavy but bounded. Per [ADR-0012](decisions/0012-phabsim-real-fortran-validation.md):

a) USFWS PHABSIM source archive acquisition — public-domain
   per 17 USC § 105 but actual redistribution-in-container terms
   need verification. Contact: USGS Fort Collins Science Center
   (https://www.usgs.gov/centers/fort-collins-science-center).
b) Bovee 1997 cookbook § 5.1 (Trapezoidal Channel) input-deck
   capture in IFG4 format. Source: the cookbook itself, available
   via USGS reports (BRD-1997-0004).
c) Container build + comparison harness — code-side work, gated
   on (a) + (b).
d) Pinning Δ ≤ 1e-3 cell-by-cell vs OpenLimno → closes U3.

### 4. U4 — Real basin case study

Hardest because it requires field-data acquisition, statistical
comparison, and publication. Per
[`u4_prerequisite_lemhi_fixture_pipeline.md`](u4_prerequisite_lemhi_fixture_pipeline.md):

- Acquire real Lemhi cross-section + spawning-survey data (IDFG /
  USGS partnership), OR
- Acquire a CN basin (preferred per charter) — Yangtze tributary
  with documented IFIM study, or Yellow River reach with available
  ADCP / fish-passage records.
- Replace synthetic fixtures, re-run pipeline, statistical
  comparison, publication.

## Decision rules during the external-action phase

| Situation | Action |
|---|---|
| External user reports a real bug | Investigate; fix only if confirmed; ship as bugfix patch citing the report (per ADR-0011) |
| Internal AI/CI flag finds a "potential issue" | Document in `docs/reviews/v3_7_plus_backlog.md`; **do not** ship |
| Maintainer signs MAINTAINERS.md | This is the U1 trigger; re-evaluate moratorium |
| Reviewer-of-record signs an output | This is the U5 trigger; re-evaluate moratorium |
| USFWS PHABSIM source acquired | U3 code-side work resumes (container build, deck capture) |
| Real basin data acquired | U4 code-side work resumes (re-run, comparison, write-up) |
| Triple-AI review producing diminishing returns | Skip per `feedback_review_cadence` rule |

## What this document does NOT do

❌ Declare the project complete. It declares the *internal-code
phase* of the 1.0-readiness work substantively complete; the
*charter-readiness* work is now what's pending.

❌ Lift the ADR-0011 moratorium. Only U1+U2+(U3∨U4∨U5) closing
lifts it. This document is consistent with the moratorium, not
a replacement for it.

❌ Forbid all code work. Bug fixes against real reports, U3
container work, and docs updates remain permitted (per "What
continues" above).

## See also

- [ROADMAP.md](ROADMAP.md) — overall plan
- [ADR-0011](decisions/0011-stable-major-tag-moratorium.md) — moratorium
- [CAPABILITY_BOUNDARY_1_0.md](governance/CAPABILITY_BOUNDARY_1_0.md) — D-criteria
- [STATE_2026_05.md](STATE_2026_05.md) — current numerics
- [`feedback_review_cadence`](../../.claude/projects/-mnt-data-openlimno/memory/feedback_review_cadence.md) — review-cadence memory rule
- [`reviews/R5_R14_audit.md`](reviews/R5_R14_audit.md) — last
  R-DOC-AUDIT-WIRED pass
- [`u4_prerequisite_lemhi_fixture_pipeline.md`](u4_prerequisite_lemhi_fixture_pipeline.md)
  — what Lemhi prerequisite means and doesn't mean
