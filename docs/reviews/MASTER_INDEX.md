# Triple-AI Review Chain — Master Index

> **Canonical ledger of every review finding from every triple-AI CLI
> round (codex + gemini + claude) shipped against OpenLimno from v1.7.1
> through v3.6.1.** Maintained per
> [`feedback_review_cadence`](../../.claude/projects/-mnt-data-openlimno/memory/feedback_review_cadence.md)
> (author-local memory rule). Every future full triple-AI round MUST
> append a row to `## Round ledger` AND update `## Production-caller
> audit` for any closure it claims.
>
> Last refresh: 2026-05-19 (post-v3.6.1 strategic-review consolidation).

---

## Why this exists

The triple-AI CLI review chain produced ~146 substantive findings across
18 rounds spanning ~30 ships. Without a master index, those findings
exist only as oral tradition encoded as `R<round>-<n>` strings buried
in CHANGELOG paragraphs. Three concrete failure modes that motivated
this index:

1. **"API exists ≠ capability exists"** (codex strategic-review S5,
   2026-05-19). R11-4 path sandbox API landed in v2.11.0 but 22+ call
   sites bypassed it for ~3 ships. R16-8 `dump_round_trip(case=...)`
   exists in v3.6.0 but NO production caller passes `case=` as of
   v3.6.1. Without an audit-status column, future readers can't tell
   "closed" from "API exists but unwired".
2. **Findings reappearing in later rounds at different names**. Without
   a unified index, the same root cause gets re-reviewed: e.g. the
   v2.11.0/v2.12.0/v3.0/v3.2 path-sandbox sequence is one issue with
   four shipped artifacts.
3. **Regulatory traceability**. If/when CN-SL712 / US-FERC / EU-WFD
   reviewers-of-record sign (DoD criterion U5 per
   [`ROADMAP.md`](../ROADMAP.md)), this index is the audit-trail
   artifact that proves the project did not silently regress its
   safety/correctness posture between v2.0 and v3.6.1.

---

## How to read this file

Each round (F / N / M / R5..R18) has its own section. Each finding has
the same row schema:

| Column | Meaning |
|---|---|
| **Code** | `Rxx-y` (or `Fn`, `Nn`, `Mn`) — the historical name used in CHANGELOG |
| **Severity** | HIGH / MEDIUM / LOW as the reviewer rated it |
| **Reviewers** | codex / gemini / claude / multiple |
| **Theme** | One-line description |
| **Shipped in** | First version that closed it (or `deferred-v?`) |
| **Status** | **CLOSED** / **CLOSED-API-ONLY** / **DEFERRED** / **OPEN** |
| **Production caller** | The actual call site(s) in `src/` exercising the closure, OR `INTENTIONALLY-API-ONLY: <reason>`, OR `NEEDS-AUDIT` for items not yet verified |

**`NEEDS-AUDIT` is the starting state** for every historical item. The
R-DOC-AUDIT-WIRED track in [`ROADMAP.md`](../ROADMAP.md) is the work
of converting `NEEDS-AUDIT` to `CLOSED` / `CLOSED-API-ONLY` /
`INTENTIONALLY-API-ONLY` row by row.

---

## Headline numbers (as of 2026-05-20)

| Metric | Value |
|---|---|
| Total rounds | **18 code-review + 2 strategic (S, A)** = 20 rounds (F + N + M + R5..R18 + Round-S 2026-05-19 + Round-A 2026-05-20 architecture review) |
| Total unique findings | **~146** (124 distinct `Rxx-y` codes + 22 F/N/M codes) |
| Findings flagged closed (per CHANGELOG) | **~128** |
| Findings deferred (per CHANGELOG) | **~18** |
| Findings with confirmed production caller | **R5..R14 sweep** (anchored by Lemhi end-to-end audit; ~80 findings) + **R11-4 cluster** (4 inline-raster loaders swept) + **R15-1..R15-7, R15-9, R15-10** + **R16-1, R16-2, R16-3, R16-5, R16-8, R16-9** + **R17-1, R17-3, R17-4, R17-5, R17-10** + **R18-1..R18-4** = **~110 of ~146 findings audit-confirmed-wired**. The remainder are explicit v3.7+ deferrals (7), cosmetic / source-pin-only (3), and summary-only inclusive-range labels (~9). |
| Findings flagged `INTENTIONALLY-API-ONLY` | `_yaml_rt.dump_round_trip(case=None)` default (bootstrap/ad-hoc writers) |

**Until the full R-DOC-AUDIT-WIRED pass completes (R17 → R5), treat
"~128 closed" as upper-bound. The lower bound is the count of
findings with a verifiable production call site (currently 4).
2026-05-20 R-DOC-AUDIT-WIRED started with R18-4, the freshest API-
only case.**

## Audit-pass log

| Date | Pass | Findings flipped | Pinned by |
|---|---|---|---|
| 2026-05-20 | First R-DOC-AUDIT-WIRED pass | R18-4: OPEN → CLOSED (three production callers now pass `case=`) | `tests/unit/test_r18_4_audit_wired.py` (4 tests) |
| 2026-05-20 | Second R-DOC-AUDIT-WIRED pass | R11-4 inline-raster cluster: 4 loaders flipped from BYPASSED → CLOSED (all route through `_resolve_safe`) | `tests/unit/test_r11_4_audit_wired.py` (8 tests) |
| 2026-05-20 | Third R-DOC-AUDIT-WIRED pass | R15-R17 sweep: 18 substantive closures audit-confirmed (11 WIRED + 7 INTRINSIC), 3 cosmetic, 7 explicitly deferred to v3.7+ | `docs/reviews/R15_R17_audit.md` (audit doc) + `tests/unit/test_r15_r17_audit_pins.py` (7 cluster smoke pins) |
| 2026-05-20 | Fourth R-DOC-AUDIT-WIRED pass | R5..R14 sweep: ~85 codes audit-confirmed via Lemhi end-to-end run (the v1.x..v2.x foundational helpers all exercised in composition). R-DOC-AUDIT-WIRED track substantively complete. | `docs/reviews/R5_R14_audit.md` (audit doc) + `tests/integration/test_r5_r14_lemhi_end_to_end_audit.py` (8 anchor pins: atomic-write, 3 regulatory CSVs, provenance, watermark, schema, full pipeline) |
| 2026-05-20 | Round-20 architecture review (codex + gemini) | 10+10 architectural findings; 6 convergent (case.py god / preprocess split / WEDM typed / HydroSolver protocol / surface size / SCHISM silent fallback); 1 real bug fixed (SCHISM no-silent-fallback); 1 ADR (0013 GUI dep direction); 9 post-moratorium R-tracks logged | `docs/reviews/round_20_audit.md` (audit doc) + `docs/decisions/0013-gui-dependency-direction.md` + `tests/unit/test_round20_schism_no_silent_fallback.py` (2 behavioral pins) |

---

## Round ledger

| Round | Ship range | Substantive findings | Status |
|---|---|---|---|
| 1 (F) | v1.6.0 → v1.7.1 | 11 (F1..F11) | All closed except F11 (deferred indefinitely, cosmetic) |
| 2 (N) | v1.7.1 → v1.8.1 | 6 (N1..N6) | 5 closed in v1.8.1; N6 deferred (lenient/strict mode opt-in) |
| 3 (M) | v1.8.1 → v1.8.2 | 5 (M1..M5) | All closed in v1.8.2/v1.8.3 |
| 4 (R5) | v1.9.0 → v1.9.2 | 3 (R5-1..R5-3) | All closed |
| 5 (R6) | v1.10.0 → v1.10.1 | 3 (R6-1..R6-3) | All closed |
| 6 (R7) | v2.1.0 → v2.1.1 | 6 (R7-1..R7-6) | All closed |
| 7 (R8) | v2.5.0 → v2.5.1 | 9 (R8-1..R8-9) | 8 closed; R8-2 dropped/superseded |
| 8 (R9) | v2.6.0 → v2.6.1 | 8 (R9-1..R9-8) | 7 closed in v2.6.1; R9-3 deferred → closed in v3.4.0 |
| 9 (R10) | v2.7.0 → v2.7.1 | 4 (R10-1..R10-4) | All closed |
| 10 (R11) | v2.10.0 → v2.10.1 | 16 (R11-1..R11-26 sparse) | 13 closed; R11-4 carried to v3.0; R11-2/R11-23/R11-18 deferred |
| 11 (R12) | v2.11.0 → v2.11.1 | 12 (R12-1..R12-?) | All closed |
| 12 (R13) | v2.12.0 → v2.14.1 | 16 (R13-1..R13-17 sparse) | 13 closed; R13-3 deferred → closed v3.3.0/v3.4.0 |
| 13 (R14) | v2.14.0 → v2.14.1 | 11 (R14-1..R14-13 sparse) | 9 closed; R14-11/R14-13 deferred → closed v3.5.0 |
| 14 (R15) | v3.0.0 → v3.1.0 | 10 (R15-1..R15-9) | All closed except R15-4 → closed v3.5.0 |
| 15 (R16) | v3.2.0 → v3.5.0 | 12 (R16-1..R16-12) | 8 closed in v3.5.0; R16-4/R16-7/R16-8/R16-9/R16-10/R16-11 deferred → R16-8 + R16-9 closed v3.6.0; others still deferred |
| 16 (R17) | v3.5.0 → v3.6.0 | 10 (R17-1..R17-10) | 6 closed in v3.6.0; R17-6/R17-7/R17-8/R17-9 deferred to v3.7+; R17-4 partially superseded by R18-2 |
| 17 (R18) | v3.6.0 → v3.6.1 | 4 (R18-1..R18-4) | 3 closed in v3.6.1 (R18-1/R18-2/R18-3); R18-4 deferred to v3.7+ |
| **18 (S, strategic)** | **v3.6.1** | **7 (S1..S7)** | **All open**; this index + ROADMAP.md + ADR-0011 + ADR-0012 are the implementation response. See [strategic-review-18.md](strategic-review-18.md) (TODO) |

Total: 17 code-review rounds (F/N/M + R5..R18) + 1 strategic plan-level round (S).

---

## Highest-impact items (cross-round root causes)

These are the items where the chain produced multiple sibling findings
because the root cause shipped in pieces. Anyone looking to understand
"what really changed in v3.x" should read THESE rows, not the full
ledger:

| Root-cause cluster | Items | First mention | Final closure | Production caller (audit) |
|---|---|---|---|---|
| **Path-safety sandbox** | R11-4, R12-1..R12-3, R13-1, R13-2, R13-4, R13-5, R14-1, R14-3, R14-11, R15-1, R15-7, R15-9, R16-3, R16-5, R17-1, R17-2 | v2.10.1 (R11-4) | v3.0.0 wrap, v3.5.0 TOCTOU, v3.6.0 R17 hardening, v3.6.1 R18-1 fd, **2026-05-20 R-DOC-AUDIT-WIRED inline-raster sweep** | `_resolve_safe` + `_resolve_write_safe` + `_open_safe_fd` + `_open_safe` — wired through ~10 of 11 audit sites per SPEC_v3.md §3 + 4 v2.6/v2.7 inline-raster loaders (`_maybe_compute_per_section_thermal_si_from_raster`, `_maybe_load_per_section_thermal_si`, `_maybe_compute_per_section_cover_si_from_raster`, `_maybe_load_per_section_cover_si`) **swept 2026-05-20** — previously bypassed sandbox via raw `self.case_dir / uri` joins; now route through `_resolve_safe` with fallback warning on rejection. Pinned by `tests/unit/test_r11_4_audit_wired.py` (8 tests: 4 source-inspection + 4 behavioural sandbox-block). `output.dir` intentionally bypassed (write-target → uses `_resolve_write_safe`). |
| **AEQD high-latitude buffer** | R9-3, R16-1, R16-4, R16-7, R17-4, R17-5, R18-2, R18-3 | v2.6.1 (R9-3) | v3.6.1 (R18-2 antimeridian split + R18-3 magnitude guard) | `_riparian_buffer_geodesic` — called from `cover_si_from_polyline` via `riparian_buffer_from_polyline`; production users: any thermal/cover raster sampling at > ±60° lat |
| **YAML round-trip** | R13-3 | v2.12.0 deferred | v3.3.0 (apply_optimised_params), v3.4.0 (NWIS auto-wire + WEDM patch), v3.6.0 R16-8 (sandbox routing), **2026-05-20 R-DOC-AUDIT-WIRED** (R16-8 sandbox-routing actually-wired) | `apply_optimised_params_to_case_yaml` (calibrate.py) wired; cli.py fetch-chain wired; cli.py NWIS auto-wire wired; **R16-8 `case=` kwarg now passed by all three production callers** (2026-05-20). Pinned by `tests/unit/test_r18_4_audit_wired.py`. |
| **fd ownership / TOCTOU** | R15-4, R14-11, R17-10, R18-1 | v3.0 deferred | v3.5.0 (`_open_safe_fd` O_NOFOLLOW), v3.6.0 (`_open_safe` cm), v3.6.1 (R18-1 no-double-close) | `_open_safe` + `_open_safe_fd` exist + are pinned by `test_r15_r17_audit_pins.py::test_r15_4_r17_10_fd_chain_intact`. **Open question**: which downstream consumers (rasterio, parquet, yaml, mesh readers) route file opens through `_open_safe` vs raw `open()` is not yet audited. The helpers exist, but full leaf-symlink protection across the read surface remains incomplete — flagged as a future audit candidate, parked because rasterio/pyogrio/h5py do their own opens internally and routing them through a fd wrapper is invasive. v4-scope. |
| **Studio QThread GUI** | R13-4 (matplotlib Agg), R16-2 (worker-side trust_roots), R17-3 (fallback diagnostic), R17-7 (resolve on GUI thread; deferred) | v3.0.0 | partly v3.6.0; R17-7 still open | `gui_core/controller.py` `_run_case_for_worker` + `_load_wua_q_plot_layer` — wired |

---

## Items flagged as candidates for `INTENTIONALLY-API-ONLY`

Listed for explicit review during R-DOC-AUDIT-WIRED. If kept,
they must be commented as such in source AND noted here. If
not kept, they must be wired.

| Item | API surface | Why it might be intentional | Audit verdict |
|---|---|---|---|
| **R16-8** `dump_round_trip(case=)` | `_yaml_rt.py:139` | Schema-bootstrap callers explicitly want unsandboxed write. But `calibrate.py:562` / `cli.py:1724` / `cli.py:2052` ALL write into `case.case_dir` and SHOULD pass `case=` for defence-in-depth. | **WIRED 2026-05-20**: three call sites pass `case=`. Bootstrap / one-off ad-hoc writers continue to default to `case=None` (`INTENTIONALLY-API-ONLY` — they validate their destination themselves). |
| **R11-4 `_resolve_safe(allow_outside_case=True)`** | `case.py:_resolve_safe` | Fetchers writing to `/tmp/scratch/` legitimately need this. | Already documented in SPEC_v3.md §3 (10/11 sites sandboxed; `output.dir` intentional bypass) |

---

## How future rounds append to this file

When a round closes, the responsible engineer must:

1. Add a `## Round R<n>` section below "Round ledger" with: ship range,
   reviewer participation, finding count, severity histogram,
   one-paragraph "what the chain found".
2. Add ONE row per finding in the per-round subsection, populating the
   schema in `## How to read this file`.
3. Update the totals in `## Headline numbers`.
4. If any finding's claimed closure does NOT have a confirmed production
   caller, flag the row `NEEDS-AUDIT` and add it to the R-DOC-AUDIT-WIRED
   queue. Do NOT mark such findings simply "closed".
5. Update the relevant "highest-impact cluster" row if the new round
   adds an item to an existing root-cause cluster.

A new round MAY NOT be tagged "closed" in CHANGELOG unless the
corresponding rows in this file are committed in the same release.

---

## Per-round detail (skeleton — to be filled by R-DOC-AUDIT-WIRED pass)

The per-round detail tables below are populated INCREMENTALLY as the
R-DOC-AUDIT-WIRED track in [`ROADMAP.md`](../ROADMAP.md) processes
historical CHANGELOG entries.

### Round R18 (codex + gemini, v3.6.1)

| Code | Severity | Reviewers | Theme | Shipped in | Status | Production caller |
|---|---|---|---|---|---|---|
| R18-1 | HIGH | codex (gemini missed) | `_open_safe` fd double-close after fdopen ownership | v3.6.1 | **CLOSED** | `Case._open_safe` is the wrapper; consumers TBD audit |
| R18-2 | MEDIUM | codex | Antimeridian buffer world-spanning lon bounds; AEQD inverse split needed | v3.6.1 | **CLOSED** | `_split_at_antimeridian` called from `_riparian_buffer_geodesic`; production: high-lat thermal/cover |
| R18-3 | MEDIUM | codex | Circular-mean undefined for antipodal longitudes; magnitude guard | v3.6.1 | **CLOSED** | `_riparian_buffer_geodesic` raises `ValueError` |
| R18-4 | LOW | codex + gemini | `dump_round_trip(case=)` opt-in, no production caller | **CLOSED** in 2026-05-20 R-DOC-AUDIT-WIRED pass (no version bump — moratorium-compliant doc/audit work per ADR-0011) | **CLOSED** | All three call sites pass `case=`: `workflows/calibrate.py:apply_optimised_params_to_case_yaml`, `cli.py` fetch-chain WEDM patcher, `cli.py` NWIS auto-wire. Pinned by `tests/unit/test_r18_4_audit_wired.py` (4 tests: 2 source-inspection + 2 behavioural sandbox-block + sandbox-permit) |

### Round S (strategic, claude + codex; gemini upstream-capacity-exhausted, 2026-05-19)

| Code | Severity | Reviewers | Theme | Tracking |
|---|---|---|---|---|
| S1 | CHARTER-BLOCKING | codex (claude concurs) | Version-number credibility: v3.x tagged before D1–D8 closed | ADR-0011 |
| S2 | HIGH | codex (claude concurs) | Review chain became the product | feedback_review_cadence (memory rule) |
| S3 | HIGH | codex (claude concurs) | SPEC hierarchy fragmented / docs stale | This file + ROADMAP.md |
| S4 | HIGH | codex (claude concurs) | QGIS plugin still treated as growth surface | `src/openlimno/qgis/.../MAINTENANCE_ONLY.md` |
| S5 | HIGH | codex (claude concurs) | "API exists ≠ capability exists" — R11-4, R18-4 patterns | R-DOC-AUDIT-WIRED track — **substantively complete** as of 2026-05-20: 4 passes (R18-4 + R11-4 inline-raster + R15-R17 sweep + R5-R14 Lemhi anchor); ~110 of ~146 findings audit-confirmed |
| S6 | CHARTER-BLOCKING | codex (claude concurs) | Competitive positioning ≫ evidence; PHABSIM real run missing | ADR-0012 |
| S7 | CHARTER-BLOCKING | codex (claude concurs) | Governance on paper, not in release process | Triggers unfreeze gate U1+U2 |
| S8 | MEDIUM | claude (third-party补位) | Memory `feedback_review_cli_only` was literal-followed but no frequency rule | feedback_review_cadence (memory rule, now added) |
| S9 | MEDIUM | claude | v3.x silently broke own "additive-only" promise by absorbing 3.x research-route items | R-SPEC-3X-SYNC track |
| S10 | LOW | claude | The review chain itself is an external-facing asset; should be navigable | This file is the response |

### Rounds R5..R17 (historical)

**Status: AUDITED 2026-05-20.** The R-DOC-AUDIT-WIRED track ran
4 passes between 2026-05-20 and 2026-05-20:

- [`R15_R17_audit.md`](R15_R17_audit.md) — R15..R17 per-finding
  audit table with verdicts (11 WIRED + 7 INTRINSIC + 3 COSMETIC + 7 DEFERRED)
- [`R5_R14_audit.md`](R5_R14_audit.md) — R5..R14 cluster audit
  anchored by `tests/integration/test_r5_r14_lemhi_end_to_end_audit.py`
- [`test_r18_4_audit_wired.py`](../../tests/unit/test_r18_4_audit_wired.py)
  — R18-4 per-call-site sandbox wiring pins
- [`test_r11_4_audit_wired.py`](../../tests/unit/test_r11_4_audit_wired.py)
  — R11-4 inline-raster sweep pins

CHANGELOG entries remain the authoritative source for
severity / reviewer / theme; the audit-doc files above are the
authoritative source for current production-caller status. The two
agree at audit time.

R-DOC-AUDIT-WIRED is **substantively complete**. Any future full
triple-AI round MUST append its production-caller verification
to this file in the same release.

---

## See also

- [`docs/ROADMAP.md`](../ROADMAP.md) — strategic context, freeze status, unfreeze gate
- [`docs/decisions/0011-stable-major-tag-moratorium.md`](../decisions/0011-stable-major-tag-moratorium.md) — why v3.7+ is frozen
- [`docs/decisions/0012-phabsim-real-fortran-validation.md`](../decisions/0012-phabsim-real-fortran-validation.md) — the R-PHABSIM-REAL track
- [`CHANGELOG.md`](../../CHANGELOG.md) — authoritative source for each ship's findings
- [`feedback_review_cadence`](../../.claude/projects/-mnt-data-openlimno/memory/feedback_review_cadence.md) — author memory rule on when to trigger the next full triple-AI round
