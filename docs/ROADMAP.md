# OpenLimno Roadmap & Plan Index

> **Status**: post-v3.6.1 strategic-review consolidation.
> Last updated: 2026-05-19.
> Canonical single-page entry point for the project plan. New contributors
> read this first; all other plan/spec docs are pointers from here.

---

## TL;DR — where the project stands today

OpenLimno has a healthy code base (22 K LOC src, 18 K LOC tests, 675 passing
gated tests, ruff 0, mypy `--strict` clean on core + GUI/QGIS) and a tagged
release line through **v3.6.1** (2026-05-19). The v3.x line shipped 18
rounds of triple-AI CLI code review (codex + gemini + claude) on 19 ships,
totalling **~146 substantive review findings, 120+ closed**, with detailed
traceability in [`docs/reviews/MASTER_INDEX.md`](reviews/MASTER_INDEX.md).

**But the project is in a STABLE-MAJOR-TAG MORATORIUM as of 2026-05-19.**
The CAPABILITY_BOUNDARY 1.0 Definition-of-Done (D1–D8) has not closed —
no real PHABSIM Fortran regression run, no real basin case study, no
regulatory reviewer-of-record signatures, no signed maintainers. The
current release train is more accurately "an engineering snapshot ladder",
not a stability ladder. Until D1+D2 (governance) and D5+D6+D7 (validation
evidence) close, no new `vN.0.0` tags will be cut. Patch/minor work
continues internally; user-facing version numbers will reset when the
DoD closes (see [ADR-0011](decisions/0011-stable-major-tag-moratorium.md)).

---

## Document hierarchy (canonical)

| Document | Scope | Status |
|---|---|---|
| [**this file (`docs/ROADMAP.md`)**](ROADMAP.md) | Plan entry point and document index | **Living** |
| [`SPEC.md`](../SPEC.md) (= `docs/SPEC.md`) | Frozen 1.0 technical spec (v0.5) | Frozen for 1.0 line |
| [`docs/external_action_phase.md`](external_action_phase.md) | Where code-side work halts; what external action unblocks the moratorium | **Living** (effective 2026-05-20) |
| [`docs/governance/CAPABILITY_BOUNDARY_1_0.md`](governance/CAPABILITY_BOUNDARY_1_0.md) | What 1.0 will and will NOT do; D1–D8 cut criteria | **Draft** (signatures pending) |
| [`docs/SPEC_v3.md`](SPEC_v3.md) | v3.0 hardening cut (path sandbox + matplotlib threading + audit pass) | Closed (executed via v3.0–v3.6.1) |
| [`docs/SPEC_3x_research_route.md`](SPEC_3x_research_route.md) | 3.x research tier deliverables | Partly executed; needs sync-back (see audit in MASTER_INDEX) |
| [`docs/reviews/MASTER_INDEX.md`](reviews/MASTER_INDEX.md) | Full triple-AI review-chain ledger (F/N/M/R series, ~146 findings) | **Living** |
| [`docs/strategy/competitive-positioning.md`](strategy/competitive-positioning.md) | "Interop before replacement"; HEC-RAS / TELEMAC / MIKE / HABBY / FishXing | Stable |
| [`docs/decisions/`](decisions/) | ADRs (0001–0012, growing) | Stable; append-only |
| [`docs/STATE_2026_05.md`](STATE_2026_05.md) | Time-stamped snapshot, last refreshed 2026-05-20 post-consolidation | Living — refreshed in-place when audit-pass count or unfreeze-gate status changes |
| [`docs/governance/GOVERNANCE.md`](governance/GOVERNANCE.md) | PSC / maintainers / release cadence | **Draft** (M0 deliverable) |

If two documents conflict, this index points to the canonical one. Notify
the maintainer who owns the docs tree if you find a contradiction.

---

## Tier table (read me to know what each version line promises)

| Tier | What ships here | Stability promise | Status |
|---|---|---|---|
| **0.x** | Initial fetch package, WEDM v0.1/0.2 prototypes, early CLI | Pre-stable | Closed — v0.4.0 froze the fetch surface |
| **1.x** | Composite-overlay scalar surface, atomic-write, HSI quality grading, regulatory exports, builtin-1D + SCHISM, fetch package | Frozen at v1.0.0 surface; patch-only | Active — v1.10.1 last patch |
| **2.x** | Per-cell composite library API; v2.0–v2.14.1 = 11 rounds of triple-AI review polish; inline thermal+cover raster paths; Studio GUI ↔ headless consolidation; WEDM strictness sweeps | Frozen at v2.0.0 charter; additive only | Active — v2.14.1 last patch |
| **3.x** | Strict-by-default path sandbox (R11-4), TOCTOU mitigation (R15-4/R14-11), atomic-write helper generalised, AEQD high-lat buffer (R9-3 + R16-1 + R17-4 + R18-2/3), ruamel.yaml round-trip (R13-3), thread-safe singletons, fd safety (R17-10 + R18-1) | Was supposed to be additive after v3.0 break; in practice has consumed multiple research-route items | **Active** — v3.6.1 last patch; **MORATORIUM on v3.7+ stable major tags** until ROADMAP §"How to unfreeze" closes |
| **3.x research route** | Reference-platform readers (PHABSIM/River2D/HABBY/FishXing), spatial-T fetcher, PEST++ runner, optional GUI/QGIS strict typing | Unstable; signature changes allowed | Multiple items closed in v3.0–v3.6.1; SPEC_3x_research_route.md needs sync (audit in MASTER_INDEX) |
| **Studio path A** | Independent PyQt6 + PyQGIS canvas GUI; bundled installer | Separate ship track (`openlimno-studio`); QGIS plugin deprecated after Studio 1.0 | Active in `gui_core/` + `studio/`; not yet shipped |
| **QGIS plugin** | M2-alpha read-only viewer | **MAINTENANCE-ONLY as of 2026-05-19** — see [`src/openlimno/qgis/openlimno_qgis_plugin/MAINTENANCE_ONLY.md`](../src/openlimno/qgis/openlimno_qgis_plugin/MAINTENANCE_ONLY.md) | Active until Studio 1.0 |

---

## 2026-05-26 update — IBM merge + R-IBM-* cleanup landed

The moratorium described below applies LITERALLY to non-IBM work
only. Native IBM work was merged to main on 2026-05-26 via
[ADR-0016 author override](decisions/0016-author-override-direct-merge.md)
despite the round-21/22/23 triple-AI review recommendation to
quarantine it. The override is documented honestly, and 8 R-IBM-*
cleanup tracks landed the same day:

| Track | Status (2026-05-26) |
|---|---|
| R-IBM-API-SHRINK | ✅ `ibm/__init__.py` `__all__` 68 → 10 |
| R-IBM-VALIDATION | ✅ seed→identical reproducibility test (+ different-seed counterpart) |
| R-IBM-CLI-GRAMMAR | ✅ 8 flat `ibm-*` commands marked `deprecated=True` |
| R-IBM-PROVENANCE | ✅ Case-compatible `provenance.json` emitted alongside `ibm_run_manifest.json` (SHA-linked) |
| R-IBM-STUDIO-CONSOLIDATE | ✅ Browser Studio gated behind `--i-understand-this-is-experimental` |
| R-IBM-SCHEMA-UNIFY | ✅ Boundary documented in `ibm/schemas/README.md` |
| R-IBM-HYDROSOLVER | ✅ Module docstrings on `hydro/{__init__,calibration,gis_hydraulics}.py` document the workflow-helper vs solver-protocol boundary |
| R-IBM-GOD-OBJECT | 🟡 PARTIAL: `studio.py` split into `studio.py` (2458 LOC business) + `studio_http.py` (207 LOC) + `studio_assets.py` (734 LOC HTML); `instream7.py` 1830 LOC + studio.py business chunk still un-split |
| R-SPEC-AMEND | ❌ Awaits PSC vote on [SCP-0001](governance/spec-change-proposals/0001-native-ibm-pivot.md) — blocked on U1+U2 |

The non-IBM moratorium (next section) remains in force.

## Active moratorium — what is FROZEN as of 2026-05-19 (non-IBM)

Per [ADR-0011](decisions/0011-stable-major-tag-moratorium.md):

1. **No new `vN.0.0` stable major-version tags** until the unfreeze gate
   below closes.
2. **No new infrastructure-only minor ships** in the v3.x line — the next
   user-visible version bump must carry validation evidence, not
   review-chain findings.
3. **Triple-AI CLI review cadence reduced** (see
   [`feedback_review_cadence`](../../.claude/memory/feedback_review_cadence.md)
   — author-local memory rule; not yet codified in repo):
   - Strong trigger (review required): public API change · path/sandbox /
     persistence / auth · scientific math · external user bug report
   - Skip-eligible (CI + targeted single-AI review): pure docs · dep
     bumps · typo / format / linter drift · internal helper rename ·
     "harden existing path without new logic" ships
   - Frequency cap: at least 3 ships between full triple-AI rounds in
     the same version line
   - Every full triple-AI round MUST record a row in
     [`MASTER_INDEX.md`](reviews/MASTER_INDEX.md) (round number, ship
     range, findings closed/deferred, production-caller-wired audit).

---

## How to unfreeze — gate to resume stable-major-tag releases

The moratorium lifts when **all** of the following hold (i.e. when the
project demonstrates evidence-grade readiness, not just clean lint):

| # | Criterion | Status 2026-05-20 | Verification |
|---|---|---|---|
| **U1** | At least 3 named maintainers + PSC quorum signed | ❌ pending external action | `docs/governance/MAINTAINERS.md` filled, GPG verified |
| **U2** | CAPABILITY_BOUNDARY_1_0.md ratified and committed | ❌ pending external action | Signature section non-`Pending` |
| **U3** | One real PHABSIM Fortran case Δ ≤ 1e-3 vs OpenLimno | 🟡 scaffold only (`benchmarks/phabsim_real/`); binary acquisition + Bovee §5.1 deck pending | [ADR-0012](decisions/0012-phabsim-real-fortran-validation.md) harness committed and CI-green on tagged ship |
| **U4** | One real basin case study published | ❌ prerequisite met (Lemhi fixture pipeline runs end-to-end), but real cross-sections + field-data comparison + reviewer not started — see [`u4_prerequisite_lemhi_fixture_pipeline.md`](u4_prerequisite_lemhi_fixture_pipeline.md) | Charter target: China-domestic (Yangtze tributary / Yellow River); fallback: any peer-reviewed basin |
| **U5** | At least one reviewer-of-record signed for one regulatory export template (CN-SL712 / US-FERC §4(e) / EU-WFD) | ❌ pending external action | `docs/governance/announcements/` signature |
| **U6** | Production-caller audit pass | ✅ **substantively complete** 2026-05-20 (4 audit passes; ~110/~146 findings audit-confirmed-wired; see [`reviews/MASTER_INDEX.md`](reviews/MASTER_INDEX.md) audit-pass log) | Every "closed" Rxx finding in [`MASTER_INDEX.md`](reviews/MASTER_INDEX.md) has either ≥ 1 production call site OR an explicit `INTENTIONALLY-API-ONLY` flag with justification |

U1+U2 are governance. U3+U4+U5 are evidence. U6 is hygiene.
U1+U2 are the **necessary** floor; U3 OR U4 OR U5 (any one) is the
**sufficient** evidence trigger. U6 is enforced on every ship after the
moratorium lifts via a release-gate script.

When the gate closes, the next stable major tag is `v4.0.0`. (v3.x
continues to receive bugfix patches but no minor bumps.) Alternative
under discussion in ADR-0011: **revert public-facing line to `v0.x` or
`v1.0.0-rc.N`** until U3+U4+U5 land, and treat v1.0–v3.6.1 as
"engineering pre-GA snapshots". Decision deferred to first maintainer
sync.

---

## Near-term work plan (concrete, non-moratorium-blocked)

These items can ship as patch releases inside the moratorium because
they advance the unfreeze gate or document existing state honestly.

| Track | First deliverable | Closes |
|---|---|---|
| **R-PHABSIM-REAL** | PHABSIM Fortran-in-OCI container harness; replicate Bovee 1997 cookbook 5.1 (Trapezoidal Channel) Δ ≤ 1e-3 | U3 |
| **R-BASIN-1** | Lemhi fixture pipeline **OPERATIONAL** (prerequisite only — fixture geometry is synthetic per `data/lemhi/manifest.json`; pipeline produces 7 default artifacts + 1 Studio PNG; pinned by `tests/integration/test_r5_r14_lemhi_end_to_end_audit.py`). **NOT** counted toward U4 evidence — that requires real cross-sections + field-data comparison + reviewer-of-record (all external-data work, see [`u4_prerequisite_lemhi_fixture_pipeline.md`](u4_prerequisite_lemhi_fixture_pipeline.md)). | U4 prerequisite (not U4 evidence) |
| **R-CN-BASIN** | Yangtze-tributary or Yellow-River case (memory `project_openlimno` charter) | U4 (preferred) |
| **R-REGREVIEW-SL712** | CN SL/Z 712-2014 reviewer-of-record outreach + sample signed export | U5 |
| **R-DOC-AUDIT-WIRED** | Production-caller audit on all R5-x..R18-x closures; flag every API-only "closed" item | U6 + closes the S5 strategic finding |
| **R-DOC-STATE-REFRESH** | ✅ **Closed 2026-05-20** — `STATE_2026_05.md` rewritten in-place to reflect v3.6.1 + 4 audit passes + moratorium status | Documentation hygiene |
| **R-QGIS-MAINT** | Move QGIS strict-typing gate out of `pixi run check` default; mark plugin as maintenance-only | Reduces v3.x carrying cost |
| **R-SPEC-3X-SYNC** | Update SPEC_3x_research_route.md to mark items closed in v3.0–v3.6.1 | Documentation hygiene |

All of these are doc/audit/validation work, not "harden existing code"
work. The next bump (v3.6.2 or v3.7.0-rc.1 — TBD pending ADR-0011
decision) ships when the doc-audit batch (R-DOC-AUDIT-WIRED +
R-DOC-STATE-REFRESH + R-SPEC-3X-SYNC + R-QGIS-MAINT) is done.

---

## Out of scope (forever, or until 1.0 ratification)

These are explicitly NOT on any track:

- OpenLimno-native 2D/3D solver (SCHISM is the sole 2D backend per
  [ADR-0002](decisions/0002-schism-integration-strategy.md) and [SPEC §0.3](../SPEC.md))
- GPU acceleration of any solver
- ML / neural-operator surrogates
- Individual-based / agent-based models (in-core; CSV bridges are fine)
- Water temperature / quality / sediment solvers (read results only)
- Web GUI / cloud / multi-tenant / REST API
- Multi-solver BMI interchange
- Multi-language top-level architecture (memory `feedback_polyglot`:
  architecture stays language-neutral; module layer picks per case)

---

## Where to look when you have a question

| Question | Look here |
|---|---|
| Why does X exist as a 1.0 feature? | `SPEC.md` (frozen v0.5) |
| What can 1.0 do and not do? | `docs/governance/CAPABILITY_BOUNDARY_1_0.md` |
| What is the v3.x stable promise? | `docs/SPEC_v3.md` |
| Which review found bug Y? | `docs/reviews/MASTER_INDEX.md` |
| Why did we choose technology Z? | `docs/decisions/00NN-*.md` (ADR list) |
| How do we compare to PHABSIM / HEC-RAS / etc.? | `docs/strategy/competitive-positioning.md` |
| When will 1.0 actually ship? | This document, section "How to unfreeze" |
| How is the project governed? | `docs/governance/GOVERNANCE.md` |
