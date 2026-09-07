# ADR-0018 — fishtank as a declared second product line, and localhost Studio is not the excluded "Web GUI"

- **Status**: Accepted
- **Date**: 2026-09-07
- **Supersedes**: closes open items O1 and O3 of [ADR-0017](0017-scope-check-exemption-register.md)
- **Amends**: `SPEC.md` §0.3 (two clarifications), `SPEC.md` §0.5 (new), `SPEC.md` §9

## Context

ADR-0017 fixed the SPEC §0.3 scope checker and, in doing so, made two
long-standing ambiguities impossible to keep ignoring. Both were recorded there
as open items because a regex cannot settle a charter question.

**O1 — `fishtank/` had no root-charter basis.** 5,538 lines with their own CLI
entry point, PySide6 desktop app and Studio, containing a genuine ABM
(`simulate_agent_based_model`, `FishAgent`, `MicrobePatch`). It *was* declared —
but only in `docs/fishtank/SPEC.md` §0, a module-local document. Root `SPEC.md`
never mentioned it and README's "What 1.0 does NOT do" did not either, while
`ibm/` — the other ABM in the tree — carries three ADRs plus explicit README
disclosure. The asymmetry meant the scope checker had to exempt `fishtank/` on
a basis weaker than the one it accepted for `ibm/`.

**O3 — localhost Studios versus "Web GUI".** `ibm/studio_http.py`,
`fishtank/studio_http.py` and `cli.py` serve HTTP UIs from stdlib
`http.server`. §0.3 excludes "Web GUI / 云原生 / 多租户 / REST 服务", but the
checker encoded that exclusion as *framework* names (`fastapi`, `flask`,
`django`, `tauri`), so a stdlib localhost Studio was invisible to it. Whether
the Studios are the excluded thing was never decided; the keyword list simply
happened not to look where they live.

## Decision

### 1. `fishtank/` is a declared second product line (SPEC §0.5)

Acknowledged in the root SPEC rather than split out or left implicit.

The reasoning that decided it: fishtank's value is *reusing* the main line's
foundations — WEDM-style provenance and SHA-256 content addressing, the pixi
environment, the same `ruff` / `mypy --strict` / schema gate, the Studio
conventions. A separate repository would have to rebuild all of that, and the
teaching value comes precisely from "a small model built to real engineering
standards." Splitting solves a bookkeeping problem by creating a duplication
problem.

What acknowledgement costs, and the fences that pay for it (SPEC §0.5):

1. **No reverse dependency.** fishtank must not import from
   `habitat/`, `hydro/`, `passage/`, `studyplan/`, `wedm/`, and the main line
   must not import fishtank. The CLI mounts it through `LazyGroup`, so the main
   import graph does not contain it — pinned by
   `tests/unit/test_cli_lazy_import.py`.
2. **No regulatory path.** Nothing fishtank produces may reach the SL/Z 712,
   FERC 4(e) or EU WFD exporters.
3. **Outside the 1.0 semver promise.** fishtank's API follows the course, and
   correspondingly may never be a reason to delay 1.0.
4. **Course material stays out of the public repo** (`.gitignore`); only
   `docs/fishtank/{README,SPEC}.md` ship.

§0.3's IBM/ABM non-goal is clarified accordingly: what 1.0 excludes is
*regulatory-grade* IBM and population-dynamics conclusions. Both ABMs in the
tree are declared non-regulatory — `ibm/` as the §13 research route,
`fishtank/` as the §0.5 teaching line — and neither may feed the exporters.

### 2. A single-user localhost Studio is not the excluded "Web GUI"

§0.3 excludes an **outward-facing service** posture: multi-tenant, exposed
beyond loopback, OpenLimno as a REST backend for third parties. A single-user
Studio bound to loopback and started and stopped by a command is not that. It
is the same thing as the PySide6 desktop app rendered differently, and both
serve §0.2 goal 1 — "installs, runs, produces a figure."

**The test is service posture, not implementation technology.** A multi-tenant
public service written on stdlib `http.server` is out of scope; a single-user
tool bound to 127.0.0.1 written on fastapi is not. Encoding the exclusion as
framework names had it exactly backwards — it would have waved through the
former and flagged the latter.

This is why the guards added in #18 matter to the charter and not just to
security: the Host allowlist, the Origin check and the loopback default are
what *make* the Studios single-user local tools rather than a service that
merely happens to be unreachable today.

## Consequences

- The scope checker's `web_gui` category is re-expressed around posture:
  binding to a non-loopback address, multi-tenancy and auth/session machinery
  are what it should look for. Framework names stay as weak signals rather than
  the definition. `EXEMPTIONS` entries for `fishtank/**` now cite SPEC §0.5 and
  this ADR instead of a module-local document.
- `fishtank/**` gains a charter basis of the same strength `ibm/**` has.
- Anyone adding an authenticated, multi-tenant or non-loopback-by-default
  surface is now clearly in SPEC-change-proposal territory, whatever library
  they use.
- ADR-0017's O1 and O3 are closed. Its O2 and the rest stand.

## Alternatives rejected

**Split fishtank into its own repository.** Cleanest on paper. Rejected because
the shared gate and provenance machinery are the point, not incidental — and
because the main CLI already stopped paying fishtank's startup cost when the
import became lazy, which was the concrete harm.

**Leave fishtank implicit with a one-line cross-reference.** Cheapest.
Rejected: the exemption register requires a citable basis, and "a module-local
doc" is a weaker basis than the same register demands of `ibm/`. Writing the
rule down in one place and applying it unevenly is how scope discipline becomes
decorative.

**Treat the Studios as excluded and require a SPEC change proposal.** The
literal reading of §0.3. Rejected because it would put two working, shipped,
tested tools into limbo over a word that plainly meant something else — §0.3's
neighbours in that bullet (云原生, 多租户, REST 服务) are all service-posture
terms, not "any HTTP".
