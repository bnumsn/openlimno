# ADR-0013: GUI dependency direction — gui_core / studio / qgis cleanup

- **Status**: Proposed (doc-only finding; concrete refactor blocked
  by moratorium per ADR-0011)
- **Date**: 2026-05-20
- **Deciders**: acrochen
- **SPEC sections**: SPEC §2 architecture; ADR-0005 (QGIS subprocess
  deployment)
- **Tags**: [gui, governance, architectural-debt]

## Context

Round-20 architecture review (codex A6 HIGH; gemini A4 LOW) flagged a
real dependency-direction incoherence in the GUI tier:

```
src/openlimno/gui_core/controller.py:24
    from openlimno.studio.headless import run_case_with_plots

src/openlimno/studio/main_window.py:48
    from openlimno.gui_core import Controller

src/openlimno/qgis/openlimno_qgis_plugin/plugin.py:27
    import openlimno.gui_core  # noqa: F401
src/openlimno/qgis/openlimno_qgis_plugin/plugin.py:69
    from openlimno.gui_core import Controller
```

Three issues:

1. **`gui_core` is supposed to be the shared low-level layer**, but it
   imports `studio.headless` — making `gui_core` depend on `studio`,
   the opposite of the name's promise.
2. **`studio.main_window` imports `gui_core.Controller`** — circular
   at the package level (the deferred `from ... import` inside
   `gui_core/controller.py` is what currently makes this work at
   runtime; remove the lazy guard and it breaks).
3. **The QGIS plugin imports `openlimno.gui_core` IN-PROCESS** at
   line 27 and line 69 — directly violating
   [ADR-0005 § Decision](0005-qgis-deployment-strategy.md):

   > QGIS plugin should NOT depend on the OpenLimno Python package
   > inside QGIS Python; communicates with OpenLimno via subprocess
   > CLI calls.

   The plugin works in practice because the user-side workflow tends
   to install OpenLimno into the same env that QGIS uses (against
   recommendation), but the architectural promise is broken.

## Decision

**This ADR documents the problem; it does NOT yet refactor.** The
fix requires source changes to `gui_core/`, `studio/`, and the QGIS
plugin — moratorium-incompatible per ADR-0011 § "No new
infrastructure-only ships".

**The target architecture (when the moratorium lifts):**

```
openlimno.app/              # NEW: headless run + plot APIs (was studio.headless)
    headless.py             # run_case_with_plots, HeadlessRunResult

openlimno.gui_core/         # SHARED Qt-widget primitives (no headless deps)
    widgets/                # WuaQTable, ProvenancePane, ...
    controller.py           # imports openlimno.app.headless ONLY
    qt_threads.py           # QThread workers

openlimno.studio/           # Studio path A application
    main_window.py          # imports openlimno.gui_core
    [no headless logic]

openlimno.qgis.openlimno_qgis_plugin/   # M2-alpha viewer (DEPRECATED post Studio 1.0)
    plugin.py               # ONLY subprocess invocation of `openlimno` CLI
                            # NO `import openlimno.gui_core` — restores ADR-0005
```

The dependency direction would then be linear:

```
qgis (subprocess-only) ←→ openlimno CLI ←→ openlimno.app ← openlimno.gui_core ← openlimno.studio
                                              ↑
                                              └── openlimno.case + helpers
```

## Alternatives considered

### Alternative A — invert: move `headless` INTO `gui_core`
- Pros: simpler; one rename.
- Cons: `gui_core` becomes a "GUI-cum-headless-runner" — the
  abstraction is muddled.

### Alternative B — keep status quo
- Pros: zero work; ADR-0005 violation is documented but tolerated.
- Cons: rots further. New Studio features add new circular
  imports. Memory `project_studio` says QGIS deprecates after
  Studio 1.0, so the architectural drift directly increases the
  cost of that deprecation.

### Alternative C (chosen for the post-moratorium plan) — `openlimno.app` as the headless run-orchestrator
- Pros: explicit naming; restores ADR-0005; clean dependency chain;
  the QGIS plugin's subprocess-only mode is trivial to enforce
  (the plugin source can then be a single-file `plugin.py` calling
  `subprocess.run(["openlimno", "run", "--case", path])`).
- Cons: 1-2 days of mechanical refactor work + ~5 import-path
  updates in tests.

## Consequences

### Positive (when the refactor lands)
- ADR-0005 promise restored: QGIS plugin's in-process import surface
  shrinks to zero (just `subprocess.run`).
- `gui_core` becomes genuinely "core" — only Qt primitives, no
  application logic.
- Studio path A's deprecation of the QGIS plugin (memory
  `project_studio`) becomes a simple file deletion, not an
  abstraction-extraction.

### Negative
- ~5 import-path changes ripple across tests and the user-visible
  `from openlimno.studio.headless import run_case_with_plots`
  pattern. The latter is documented in `examples/lemhi/quickstart.py`
  and would need a re-export or a deprecation-warning shim for ≥ 1
  minor release per
  [GOVERNANCE.md § Deprecation policy](../governance/GOVERNANCE.md).

### Neutral / Acknowledged trade-offs
- The QGIS plugin's `import openlimno.gui_core` was probably added to
  silence a startup error when OpenLimno isn't installed. With the
  subprocess-only model the plugin can detect missing CLI via
  `shutil.which("openlimno")` and show a setup hint dialog rather
  than crashing on import.

## Why this is documented now, not fixed

ADR-0011 moratorium § "What halts (code-side)" — no new
infrastructure-only ships. A pure refactor isn't strictly listed
under "what continues" either. Per round-20 codex review's
moratorium-compatibility verdict on this finding (NO for code, YES
for ADR/doc clarification), this ADR captures the analysis NOW so
that when the moratorium lifts the refactor is a clear, scoped
unit of work — NOT a re-discovery exercise.

## Implementation notes (for when this thaws)

1. Create `src/openlimno/app/__init__.py` re-exporting
   `run_case_with_plots`, `HeadlessRunResult`.
2. Move `src/openlimno/studio/headless.py` → `src/openlimno/app/headless.py`.
3. In `src/openlimno/studio/__init__.py`, add a compatibility re-export
   with `DeprecationWarning`:

   ```python
   from openlimno.app.headless import run_case_with_plots, HeadlessRunResult  # noqa: F401
   import warnings
   warnings.warn(
       "openlimno.studio.headless is deprecated; "
       "import from openlimno.app.headless instead.",
       DeprecationWarning, stacklevel=2,
   )
   ```

4. Update `src/openlimno/gui_core/controller.py:24` to
   `from openlimno.app.headless import run_case_with_plots`.
5. Update QGIS plugin to be subprocess-only:

   ```python
   import subprocess
   import shutil

   def _has_cli():
       return shutil.which("openlimno") is not None

   class Controller:
       def run_case(self, case_yaml: str) -> int:
           if not _has_cli():
               raise RuntimeError(...)
           return subprocess.run(["openlimno", "run", case_yaml]).returncode
   ```

6. Update `examples/lemhi/quickstart.py` to use `openlimno.app`.
7. Update test imports.

Estimated effort: 1-2 days mechanical + smoke testing on real QGIS LTS.

## References

- [Round-20 architecture review](../reviews/round_20_audit.md)
- [ADR-0005](0005-qgis-deployment-strategy.md) — the policy currently violated
- [ADR-0011](0011-stable-major-tag-moratorium.md) — why this is doc-only now
- Memory `project_studio` — Studio 1.0 deprecates QGIS plugin
