# Round-20 — Whole-Architecture Review (codex + gemini, 2026-05-20)

> Triple-AI strategic review at the architecture level (NOT code-level).
> Codex + gemini both delivered full-length reports; claude (me) synthesises.
>
> Prior strategic rounds:
> - Round 18 (code-level R18-1..R18-4): closed v3.6.1
> - Round 19 (audit-progress): codex + gemini dual CHARTER-BLOCKING on
>   the "Capability Illusion" pattern → `docs/external_action_phase.md`
> - **Round 20 (architecture-level)**: this doc

## Reviewer participation

| Reviewer | Findings | TL;DR verdict |
|---|---|---|
| codex (full) | 10 (A1..A10) | "Architecture directionally right; main refactors are real but moratorium-incompatible except as docs/ADRs" |
| gemini (full) | 10 (A1..A10) | "Functionally sound but structurally bloated; moratorium is opportunity for behavior-preserving refactor" |
| claude (synthesis) | — | Convergence on 4 HIGH findings, 2 verified-real bugs, divergence on moratorium-permissiveness |

## Headline numbers

- Architecture inventory: 22,776 LOC src across 11 sub-packages
- Single largest file: `case.py` 3,237 LOC (14.2% of total)
- Single largest dir: `preprocess/` 9,174 LOC (40.3% of total)
- ADRs: 12 (now 13 with this round)

## Convergent findings (strong agreement)

| Theme | Codex | Gemini | Verdict | Action |
|---|---|---|---|---|
| **`case.py` god orchestrator** | A1 HIGH | A1 CRITICAL | ✅ Both flag; gemini stricter | **Doc-only refactor plan** in ADR-0013-style (no source change during moratorium) — captured in this audit; concrete split deferred |
| **`preprocess/` 3-packages-in-1** | A3 MEDIUM | A2 HIGH | ✅ Both | Doc target namespace; defer code |
| **WEDM dict-first vs schema-first** | A7 MEDIUM | A5 HIGH | ✅ Both → typed models | Defer code; document gap |
| **HydroSolver protocol leaky / interop contract too informal** | A4 HIGH + A5 MEDIUM | A3 MEDIUM + A10 MEDIUM | ✅ Both | Document the canonical `hydraulic_cells` staging schema (doc-only); defer Protocol refactor |
| **Surface size growing** | A8 MEDIUM | A6 HIGH | ✅ Both | Cap new adapters; no deletion |
| **SCHISM silent fallback to Builtin1D** | A10 HIGH | A7 MEDIUM (named "actively harmful") | ✅✅ **REAL BUG verified in `case.py:349`** | **FIXED 2026-05-20** — see below |

## Codex-only deeper findings

| # | Theme | Severity | Status |
|---|---|---|---|
| **A6** | **GUI dependency direction incoherent** — `gui_core` imports `studio.headless` (claims to be "core" but depends on application layer); `studio.main_window` imports `gui_core.Controller` (circular at package level); QGIS plugin imports `gui_core` in-process violating ADR-0005 | HIGH | ✅ **Verified**; documented as [ADR-0013](../decisions/0013-gui-dependency-direction.md); refactor blocked by moratorium |
| A2 | `cli.py` is a second orchestrator (Click decls vs command bodies) | MEDIUM | Documented; defer code |
| A9 | Promise-marker modules (`studyplan` TUF not affecting WUA; `cn_hydro.py` stub) | MEDIUM | Documented in audit doc |

## Gemini-only deeper findings

| # | Theme | Severity | Status |
|---|---|---|---|
| A4 | GUI three-way split (inline `gui_core` into `studio`) | LOW | Codex's A6 supersedes; gemini's framing acknowledged in ADR-0013 |
| A8 | "Moratorium is an opportunity for behavior-preserving refactor" | MEDIUM | **DIVERGENT** with codex (see below) |
| A9 | Provenance hashing visibility — should be its own module | HIGH | Documented; not actioned (provenance code exists at `case.py:_emit_provenance` etc.; surface review can wait) |

## Key divergence: moratorium permissiveness

- **Gemini** explicitly argues: "the external-action phase is the
  ideal time to pay down structural debt that doesn't alter outputs"
  and marks Pydantic migration, `case.py` split, `preprocess/`
  reorganization as **moratorium-compatible YES**.
- **Codex** sticks to ADR-0011 letter: "during the moratorium, the
  right move is documentation honesty and freeze discipline, not
  internal code reshuffling" — marks the same refactors **NO**.

**Synthesis**: codex is correct under the explicit ADR-0011 § "What
halts (code-side)" rule. A behavior-preserving refactor isn't listed
under "What continues" (bugfix-against-real-report / doc updates / U3
container work / U6 audit). The fact that it's behavior-preserving
doesn't make it permitted — it just means it would be safe if
permitted.

**Exception**: the SCHISM silent-fallback finding (codex A10 + gemini
A7) is **not a refactor; it's a bug fix** against a real
regulatory-defense hazard surfaced by both AIs. Per ADR-0011 §
"What continues" item 1 ("bug fixes that cite an external bug
report"), this round-20 dual-AI flag IS the external report.

## Actions taken 2026-05-20

### A10/A7 fix — `Case.run` SCHISM no-silent-fallback (HIGH)

`src/openlimno/case.py:343..399`: split the previous combined
`if dry or report.return_code != 0:` branch:
- `if dry:` — intentional CI / dry-run path. Falls back to Builtin1D,
  emits explicit "dry_run=True — used Builtin1D approximation" warning.
- `elif report.return_code != 0:` — real SCHISM failure. Raises
  `RuntimeError` with the log path and remediation hint. The caller
  must explicitly opt in to a Builtin1D approximation via case YAML.

This closes the regulatory-defense hazard: a user requesting SCHISM
2D whose container crashes mid-run no longer gets 1D math + a soft
warning. SL-712 / FERC / WFD exports from such a run would have
been misleading.

Pinned by `tests/unit/test_round20_schism_no_silent_fallback.py` (2
tests):
- `test_round20_schism_nonzero_return_code_raises` — monkey-patches
  `SCHISMAdapter.run` to return `return_code=42`; asserts
  `Case.run` raises `RuntimeError` matching `"SCHISM hydrodynamic
  run failed"`.
- `test_round20_schism_dry_run_still_falls_back` — pins that the
  intentional dry-run path is unchanged.

Moratorium-compliant per ADR-0011 § "What continues" item 1: cites
codex A10 + gemini A7 dual external review.

### A6 — GUI dependency direction (ADR-only)

[ADR-0013](../decisions/0013-gui-dependency-direction.md) captures:
- The three-way violation (`gui_core` → `studio.headless`,
  `studio.main_window` → `gui_core`, QGIS plugin → `gui_core`
  in-process).
- The target architecture: `openlimno.app` as the headless
  orchestrator; `openlimno.gui_core` as pure Qt primitives;
  `openlimno.studio` as the application; QGIS plugin subprocess-only.
- Why this is documented but not refactored now (moratorium).
- Concrete implementation notes for when the moratorium lifts.

## Findings deferred to post-moratorium

These all sit in the round-20 audit ledger but require source
changes that don't fit ADR-0011 § "What continues":

| Finding | Codex | Gemini | Post-moratorium track |
|---|---|---|---|
| `case.py` split into stages | A1 | A1 | R-CASE-SPLIT |
| `cli.py` command-bodies → service modules | A2 | (part of A1) | R-CLI-DECOUPLE |
| `preprocess/` → `fetch/` + `interop/` + `preprocess/` | A3 | A2 | R-PREPROCESS-SPLIT |
| `HydraulicCellsImporter` / `HabitatExchangeImporter` Protocol | A4 | A3 | R-INTEROP-CONTRACT |
| `HydroSolver.read_results()` normalization | A5 + A10 | A10 | R-HYDROSOLVER-NORMALIZE |
| GUI dependency cleanup | A6 | A4 | R-GUI-DEPS-CLEAN (per ADR-0013) |
| WEDM Pydantic / typed models | A7 | A5 | R-WEDM-TYPED |
| Integration declaration template | A8 | A6 | R-INTEROP-GOVERNANCE |
| Promise-marker honesty pass | A9 | A7 | R-PROMISE-AUDIT |
| `openlimno.provenance` extract | — | A9 | R-PROVENANCE-MODULE |

Each gets its own track row in [`docs/ROADMAP.md`](../ROADMAP.md)
when the moratorium lifts.

## TL;DR

1. **Architecture is directionally sound** — both AIs agree. The
   product center is right (ecology surface, WEDM/provenance core,
   one-deep-solver, interop-before-replacement).
2. **One real bug fixed** — SCHISM silent fallback to Builtin1D
   was a regulatory-defense hazard surfaced by both AIs converging
   HIGH. Fixed 2026-05-20, pinned by 2 tests.
3. **9 architectural-debt items documented** as post-moratorium
   tracks (R-CASE-SPLIT, R-CLI-DECOUPLE, R-PREPROCESS-SPLIT, ...);
   ADR-0013 captures the most concrete one (GUI dep direction).
   Per codex S4 (round-19) + codex's own moratorium-discipline this
   round: doc the debt now; refactor when external action lifts the
   freeze.

## See also

- [`docs/decisions/0013-gui-dependency-direction.md`](../decisions/0013-gui-dependency-direction.md)
  — the only concrete ADR action from this round
- [`docs/reviews/MASTER_INDEX.md`](MASTER_INDEX.md) — review-chain
  ledger; round S row updated below
- [`docs/external_action_phase.md`](../external_action_phase.md) —
  the moratorium that constrained this round
- `tests/unit/test_round20_schism_no_silent_fallback.py` — the
  behavioral pin closing A10/A7
