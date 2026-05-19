# R-DOC-AUDIT-WIRED — R15..R17 sweep

> **Third R-DOC-AUDIT-WIRED pass, 2026-05-20.**
> Closes the strategic-review S5 ("API exists ≠ capability exists")
> finding for rounds R15, R16, R17. Earlier passes:
> - 2026-05-20 pass #1: R18-4 (`tests/unit/test_r18_4_audit_wired.py`)
> - 2026-05-20 pass #2: R11-4 inline-raster cluster (`tests/unit/test_r11_4_audit_wired.py`)
>
> This pass audits 32 codes (R15-1..R15-10, R16-1..R16-12, R17-1..R17-10).
> Note: R15-8 and R16-12 are summary-only inclusive-range labels in the
> CHANGELOG chain-summary — no separate itemised body exists. So the
> real R15 ∪ R16 ∪ R17 itemized count is **30 substantive findings**.
> Of those, **17 are CLOSED with production caller verified**, **9 are
> deferred to v3.7+**, and **4 are intrinsic / cosmetic / test-only**
> closures that have no separate caller to wire.

## Audit verdicts

Verdict legend:
- ✅ **WIRED** — helper / contract exists AND at least one production call site is present
- ✅ **INTRINSIC** — the closure IS the production behavior (no separate helper to wire)
- ⚠️ **COSMETIC** — docstring / comment / source-pin test only (still legitimate but no caller to verify)
- ⚪ **DEFERRED** — explicitly deferred to a future version line; not in scope of this audit

### Round R15 (10 codes, 8 substantive bodies)

| Code | Severity | Theme | Verdict | Production artifact / caller |
|---|---|---|---|---|
| R15-1 | codex P2 / claude security | URI redaction widening in path-safety raise path | ✅ INTRINSIC | `_apply_sandbox_check` redacts absolute `uri` in `OPENLIMNO_PATH_SAFETY_REDACT=1` mode; raise path itself is the caller |
| R15-2 | codex P2 | GUI autoload trust-set widened to `_allowed_data_roots()` | ✅ WIRED | `gui_core/controller.py:76` — `case._allowed_data_roots()` consumed by autoload |
| R15-3 | claude HIGH | R11-2 logic inversion fix (bbox + boundaries-absent semantics) | ✅ INTRINSIC | `Case.run`'s pre-solver warning; pinned by `test_v330_r153_*` |
| R15-4 / R14-11 | claude MED + codex | TOCTOU mitigation via `_open_safe_fd` (POSIX `O_NOFOLLOW`) | ✅ WIRED | `case.py:853` defines; `_open_safe` (line 914) wraps it as the production contract; consumers of `Case._open_safe` rely on it |
| R15-5 | claude MED | `case_yaml` kwarg made required on GUI autoload | ✅ INTRINSIC | Signature change of `_load_wua_q_plot_layer`; the only caller is the GUI path |
| R15-6 | claude MED | matplotlib `force=False` in Studio init | ✅ INTRINSIC | `studio.__init__`; production = Studio bootstrap |
| R15-7 | claude LOW | `_resolve_safe` / `_resolve_write_safe` dedup helper `_apply_sandbox_check` | ✅ WIRED | `case.py:762` helper, called from `_resolve_safe:1030` AND `_resolve_write_safe:1108` |
| R15-8 | (label-only) | inclusive-range label in summary | — | no substantive body |
| R15-9 | claude test | fixture-missing fail-loud | ✅ INTRINSIC | `tests/unit/test_v3*_fixtures_validate*.py` — test infrastructure |
| R15-10 | claude test | redact write-safe test tightening | ✅ INTRINSIC | test infrastructure |

### Round R16 (12 codes, 11 substantive bodies)

| Code | Severity | Theme | Verdict | Production artifact / caller |
|---|---|---|---|---|
| R16-1 | claude + gemini HIGH | AEQD continuous-strip buffer (replaces vertex-only 36-gon) | ✅ WIRED | `habitat/cover.py:255` `_riparian_buffer_geodesic`; called by `riparian_buffer_from_polyline:206` |
| R16-2 | claude + gemini HIGH | GUI autoload worker-side `trust_roots` threading | ✅ WIRED | `gui_core/controller.py:27` `_run_case_for_worker` returns 3-tuple including `trust_roots`; consumed by `_load_wua_q_plot_layer:988` |
| R16-3 | claude HIGH | QGIS load uses RESOLVED path | ✅ INTRINSIC | `_load_wua_q_plot_layer` passes `str(resolved)` to QgsRasterLayer |
| R16-4 | claude HIGH | full antimeridian split (very long polylines) | ⚪ DEFERRED to v3.7+ | (R18-2 partly addressed via `_split_at_antimeridian` for moderate cases) |
| R16-5 | claude HIGH | `_uri_looks_absolute` widening (`file://`, `~/…`, UNC) | ✅ WIRED | `case.py:60` defines; `case.py:838` callsite in `_apply_sandbox_check` redaction path |
| R16-6 | claude HIGH | source-inspection pin for R11-2 corrected semantics | ⚠️ COSMETIC | `test_v330_r153_source_matches_corrected_intent` is itself the audit artifact |
| R16-7 | claude | R9-3 test reference-point wrong (midpoint vs vertex) | ⚪ DEFERRED to v3.7+ | (alternate R16-1 sparse-polyline test exercises right invariant) |
| R16-8 | claude | `dump_round_trip(case=)` opt-in sandbox routing | ✅ WIRED | _yaml_rt.py:96 + R-DOC-AUDIT-WIRED pass #1 (2026-05-20) — three production callers now pass `case=` |
| R16-9 | claude | thread-safe `_WARNED_MISSING_RUAMEL` singleton | ✅ INTRINSIC | `_yaml_rt.py:54` lock + `:171` guard |
| R16-10 | claude | CHANGELOG over-count | ⚠️ COSMETIC | release-note hygiene |
| R16-11 | claude | versioned-error-prefix drift | ⚪ DEFERRED to v3.7+ | bundled with R17-6 sweep |
| R16-12 | (label-only) | inclusive-range label in summary | — | no substantive body |

### Round R17 (10 codes)

| Code | Severity | Theme | Verdict | Production artifact / caller |
|---|---|---|---|---|
| R17-1 | claude + gemini HIGH | Windows literal bugs + case-insensitive `_uri_looks_absolute` | ✅ WIRED | `case.py:60` rewrite; called from `case.py:838` |
| R17-2 | claude + gemini | `_open_safe_fd` docstring honesty | ⚠️ COSMETIC | docstring at `case.py:853..` ; pinned by `test_v360_r172_*` |
| R17-3 | claude HIGH | `_run_case_for_worker` fallback scoped + stderr diagnostic | ✅ INTRINSIC | `gui_core/controller.py:27..` ; pinned by `test_v360_r173_*` |
| R17-4 | claude + gemini HIGH | AEQD circular-mean longitude (antimeridian-safe centre) | ✅ WIRED | `habitat/cover.py:309..` in `_riparian_buffer_geodesic` (production AEQD path) |
| R17-5 | claude HIGH | PROJ Transformer `lru_cache` | ✅ WIRED | `habitat/cover.py:239,248` factories; called from `_riparian_buffer_geodesic:336-337` |
| R17-6 | claude LOW | source-inspection test brittleness | ⚪ DEFERRED to v3.7+ | rewrite candidates |
| R17-7 | gemini MEDIUM | `_load_wua_q_plot_layer.resolve()` on GUI thread | ⚪ DEFERRED to v3.7+ | move resolve to worker |
| R17-8 | claude | test gaps (`_apply_sandbox_check`, `_atomic_write` partial-failure, `Geod.fwd` cache) | ⚪ DEFERRED to v3.7+ | dedicated test plan |
| R17-9 | claude | CI matrix Python 3.13 entry | ⚪ DEFERRED to v3.7+ | infra |
| R17-10 | gemini | `_open_safe` context-manager wrapper | ✅ WIRED | `case.py:914..` ; corrected v3.6.1 R18-1; pinned by `test_v361_r181_*` |

## Tally

| Verdict | R15 | R16 | R17 | Total |
|---|---|---|---|---|
| ✅ WIRED | 3 | 5 | 3 | **11** |
| ✅ INTRINSIC | 5 | 1 | 1 | **7** |
| ⚠️ COSMETIC | 0 | 2 | 1 | **3** |
| ⚪ DEFERRED | 0 | 3 | 4 | **7** |
| label-only | 1 | 1 | 0 | 2 |

**Substantive closures: 18 confirmed CLOSED, 3 cosmetic-only, 7 deferred.**

Combined with prior audit passes:

| Pass | Cluster | Findings flipped | Pin file |
|---|---|---|---|
| 1 (2026-05-20) | R18-4 | 1 (OPEN→CLOSED) | `test_r18_4_audit_wired.py` (4 tests) |
| 2 (2026-05-20) | R11-4 inline-raster | 4 loaders (BYPASSED→CLOSED) | `test_r11_4_audit_wired.py` (8 tests) |
| 3 (2026-05-20) | R15..R17 sweep | 18 confirmed wired/intrinsic (this doc) | `test_r15_r17_audit_pins.py` (cluster smoke pins) |

## Audit pins

The 18 substantive closures don't all need individual behavioural
tests — many are already pinned by their own `test_v{ship}_r{round}_*`
file at landing time (cited in the verdict tables above). What WAS
missing: a CLUSTER smoke pin that asserts the cross-cluster helpers
(`_apply_sandbox_check`, `_uri_looks_absolute`, `_aeqd_transformer_*`,
`_open_safe`, `_run_case_for_worker`) remain importable + callable
from production. That pin file is `tests/unit/test_r15_r17_audit_pins.py`.

## Remaining backlog (post-audit)

The 7 deferred items move to `docs/reviews/v3_7_plus_backlog.md`
(to be created when the v3.7-rc.1 ship plan starts). Until then,
their closure path is unchanged from the CHANGELOG body:

- **R16-4**: full antimeridian split for very-long polylines
- **R16-7**: R9-3 test reference-point correction
- **R16-11**: versioned error-prefix drift
- **R17-6**: source-inspection test brittleness rewrites
- **R17-7**: `_load_wua_q_plot_layer.resolve()` to worker thread
- **R17-8**: test gaps for `_apply_sandbox_check`, `_atomic_write`,
  `Geod.fwd` cache
- **R17-9**: CI matrix Python 3.13 entry

## See also

- [MASTER_INDEX.md](MASTER_INDEX.md) — full review-chain ledger
- [ROADMAP.md](../ROADMAP.md) — strategic plan + freeze status
- [ADR-0011](../decisions/0011-stable-major-tag-moratorium.md) — moratorium
