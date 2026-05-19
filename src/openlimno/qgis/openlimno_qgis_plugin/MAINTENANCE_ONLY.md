# OpenLimno QGIS plugin — MAINTENANCE-ONLY status

> **Effective**: 2026-05-19 (post-v3.6.1 strategic-review consolidation;
> see [`docs/decisions/0011-stable-major-tag-moratorium.md`](../../../../docs/decisions/0011-stable-major-tag-moratorium.md)).

## What this means

The QGIS plugin (under `src/openlimno/qgis/openlimno_qgis_plugin/`)
enters **maintenance-only mode**. New UX features will NOT be accepted.
The Studio path A (`src/openlimno/studio/` + `src/openlimno/gui_core/`)
is the active investment track. Per memory rule `project_studio`, the
QGIS plugin is **deprecated after Studio 1.0 ships** — this document
formalises the soft-freeze that precedes that deprecation.

## Why

The 2026-05-19 plan-level strategic review (codex S4, HIGH) flagged
that the project carries the cost of two GUI tracks (QGIS plugin +
Studio path A) before validating ONE basin case. The v3.x line shipped
multiple findings (R16-2 GUI thread, R17-3 worker-side trust_roots,
R17-7 GUI-thread `resolve()` deferred) specifically hardening a
surface that is scheduled for deprecation.

QGIS still has a real role: it is the bridge for users with existing
QGIS workflows who want to view OpenLimno outputs (NetCDF hydraulics,
WUA-Q CSV, regulatory CSV). That use case continues to be supported.
What stops:

- New menu actions / dialogs / wizards
- New plugin-internal features (legend customisation, expression
  functions, processing provider integration)
- New defensive hardening UNLESS it closes a real reported user bug
  OR is the minimum needed for [CAPABILITY_BOUNDARY D8](../../../../docs/governance/CAPABILITY_BOUNDARY_1_0.md)
  (manual validation on QGIS LTS 3.34 + 3.40)

## What is accepted during maintenance-only

| Class | Accepted? | Notes |
|---|---|---|
| Security fix | ✅ Yes | Same bar as core (review required) |
| Compatibility fix (QGIS LTS bump, PyQt version drift, OS quirks) | ✅ Yes | Cite the upstream version that triggered it |
| D8 manual-validation work | ✅ Yes | This is the only D-criterion the QGIS plugin can close |
| New UX feature (button, dialog, menu entry) | ❌ No | Redirect to Studio path A roadmap |
| Plugin-internal refactor without user-visible behavior change | ⚠️ Discouraged | Allowed only if it removes carrying cost (e.g. drops a now-unused dependency) |
| Triple-AI review chain rounds | ❌ No | Per `feedback_review_cadence` memory rule — QGIS plugin doesn't trigger a full round |

## Gate changes (already in this commit)

- The QGIS plugin source files are EXCLUDED from
  `pixi run typecheck-strict-gui-qgis` by default. Mypy still runs on
  changed files when a PR touches `src/openlimno/qgis/**`, but the
  default `pixi run check` pipeline no longer pays the strict-typing
  cost on every ship.
- `tests/integration/test_qgis_plugin_shim.py` remains in
  `pixi run test-qgis`, which is opt-in (not in `pixi run check`).
  That hasn't changed; this doc formalises that the plugin's CI cost
  is now an opt-in.

## What removes this declaration

Studio 1.0 ships with feature parity for the QGIS plugin's three core
actions:

1. *Open OpenLimno hydraulic results…* (load `.nc` as mesh layer)
2. *Open WUA-Q curve…* (table dialog)
3. *Plot cross-section profile…*

When Studio 1.0 is signed off by the same maintainer set that signed
CAPABILITY_BOUNDARY_1_0.md (per U1 in
[ROADMAP.md](../../../../docs/ROADMAP.md#how-to-unfreeze) plus a
parallel sign-off for Studio 1.0), this plugin moves from
maintenance-only to **deprecated**:

- A removal-warning toast on plugin load points users at Studio.
- The plugin source moves to a `legacy/` namespace.
- After two further minor cycles (post-unfreeze), the plugin source
  is deleted from `main` and lives only on the archived release branch.

## See also

- [`docs/ROADMAP.md`](../../../../docs/ROADMAP.md) — overall plan
  including QGIS plugin's place in the tier table
- [`docs/decisions/0005-qgis-deployment-strategy.md`](../../../../docs/decisions/0005-qgis-deployment-strategy.md)
  — original ADR explaining why subprocess (not in-process) was
  chosen; still valid for the maintenance-only path
- [`docs/decisions/0011-stable-major-tag-moratorium.md`](../../../../docs/decisions/0011-stable-major-tag-moratorium.md)
  — the moratorium that motivates this declaration
- Memory `project_studio` — the Studio path A investment that
  replaces this plugin
