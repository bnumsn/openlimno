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

## Headline numbers (as of 2026-05-19)

| Metric | Value |
|---|---|
| Total rounds | **18** (F = round 1, N = round 2, M = round 3, R5..R18 = rounds 4..18) |
| Total unique findings | **~146** (124 distinct `Rxx-y` codes + 22 F/N/M codes) |
| Findings flagged closed (per CHANGELOG) | **~128** |
| Findings deferred (per CHANGELOG) | **~18** |
| Findings with confirmed production caller | **TBD** (R-DOC-AUDIT-WIRED pass not yet run) |
| Findings flagged `INTENTIONALLY-API-ONLY` | **TBD** |

**Until the R-DOC-AUDIT-WIRED pass completes, treat "~128 closed" as
upper-bound. The lower bound is the count of findings with a
verifiable production call site.**

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
| **Path-safety sandbox** | R11-4, R12-1..R12-3, R13-1, R13-2, R13-4, R13-5, R14-1, R14-3, R14-11, R15-1, R15-7, R15-9, R16-3, R16-5, R17-1, R17-2 | v2.10.1 (R11-4) | v3.0.0 wrap, v3.5.0 TOCTOU, v3.6.0 R17 hardening, v3.6.1 R18-1 fd | `_resolve_safe` + `_resolve_write_safe` + `_open_safe_fd` + `_open_safe` — wired through ~10 of 11 audit sites per SPEC_v3.md §3; `output.dir` intentionally bypassed |
| **AEQD high-latitude buffer** | R9-3, R16-1, R16-4, R16-7, R17-4, R17-5, R18-2, R18-3 | v2.6.1 (R9-3) | v3.6.1 (R18-2 antimeridian split + R18-3 magnitude guard) | `_riparian_buffer_geodesic` — called from `cover_si_from_polyline` via `riparian_buffer_from_polyline`; production users: any thermal/cover raster sampling at > ±60° lat |
| **YAML round-trip** | R13-3 | v2.12.0 deferred | v3.3.0 (apply_optimised_params), v3.4.0 (NWIS auto-wire + WEDM patch), v3.6.0 R16-8 (sandbox routing) | `apply_optimised_params_to_case_yaml` (calibrate.py:562) wired; cli.py:1724 + cli.py:2052 wired; **R16-8 `case=` kwarg NOT yet wired by any production caller — confirmed by R18-4** |
| **fd ownership / TOCTOU** | R15-4, R14-11, R17-10, R18-1 | v3.0 deferred | v3.5.0 (`_open_safe_fd` O_NOFOLLOW), v3.6.0 (`_open_safe` cm), v3.6.1 (R18-1 no-double-close) | `_open_safe` + `_open_safe_fd` — **NEEDS-AUDIT**: not yet confirmed which consumers (rasterio, parquet, yaml) actually route through these versus raw `open()` |
| **Studio QThread GUI** | R13-4 (matplotlib Agg), R16-2 (worker-side trust_roots), R17-3 (fallback diagnostic), R17-7 (resolve on GUI thread; deferred) | v3.0.0 | partly v3.6.0; R17-7 still open | `gui_core/controller.py` `_run_case_for_worker` + `_load_wua_q_plot_layer` — wired |

---

## Items flagged as candidates for `INTENTIONALLY-API-ONLY`

Listed for explicit review during R-DOC-AUDIT-WIRED. If kept,
they must be commented as such in source AND noted here. If
not kept, they must be wired.

| Item | API surface | Why it might be intentional | Audit verdict |
|---|---|---|---|
| **R16-8** `dump_round_trip(case=)` | `_yaml_rt.py:139` | Schema-bootstrap callers explicitly want unsandboxed write. But `calibrate.py:562` / `cli.py:1724` / `cli.py:2052` ALL write into `case.case_dir` and SHOULD pass `case=` for defence-in-depth. | **TBD** — likely wire these three; declare bootstrap path `INTENTIONALLY-API-ONLY` |
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
| R18-4 | LOW | codex + gemini | `dump_round_trip(case=)` opt-in, no production caller | **DEFERRED to v3.7+** | **OPEN** | Three call sites identified (`calibrate.py:562`, `cli.py:1724`, `cli.py:2052`); audit/wire pending |

### Round S (strategic, claude + codex; gemini upstream-capacity-exhausted, 2026-05-19)

| Code | Severity | Reviewers | Theme | Tracking |
|---|---|---|---|---|
| S1 | CHARTER-BLOCKING | codex (claude concurs) | Version-number credibility: v3.x tagged before D1–D8 closed | ADR-0011 |
| S2 | HIGH | codex (claude concurs) | Review chain became the product | feedback_review_cadence (memory rule) |
| S3 | HIGH | codex (claude concurs) | SPEC hierarchy fragmented / docs stale | This file + ROADMAP.md |
| S4 | HIGH | codex (claude concurs) | QGIS plugin still treated as growth surface | `src/openlimno/qgis/.../MAINTENANCE_ONLY.md` |
| S5 | HIGH | codex (claude concurs) | "API exists ≠ capability exists" — R11-4, R18-4 patterns | R-DOC-AUDIT-WIRED track |
| S6 | CHARTER-BLOCKING | codex (claude concurs) | Competitive positioning ≫ evidence; PHABSIM real run missing | ADR-0012 |
| S7 | CHARTER-BLOCKING | codex (claude concurs) | Governance on paper, not in release process | Triggers unfreeze gate U1+U2 |
| S8 | MEDIUM | claude (third-party补位) | Memory `feedback_review_cli_only` was literal-followed but no frequency rule | feedback_review_cadence (memory rule, now added) |
| S9 | MEDIUM | claude | v3.x silently broke own "additive-only" promise by absorbing 3.x research-route items | R-SPEC-3X-SYNC track |
| S10 | LOW | claude | The review chain itself is an external-facing asset; should be navigable | This file is the response |

### Rounds R5..R17 (historical)

**Status: NEEDS-AUDIT.** The R-DOC-AUDIT-WIRED track will populate
these tables in the order: R17 → R16 → R15 → ... (most recent first,
so production-caller status is established before drift accumulates).

Each round, when audited, gets its own subsection here. CHANGELOG
entries are the authoritative source for severity / reviewer / theme;
this index is the authoritative source for current
production-caller status. The two MUST agree at audit time.

---

## See also

- [`docs/ROADMAP.md`](../ROADMAP.md) — strategic context, freeze status, unfreeze gate
- [`docs/decisions/0011-stable-major-tag-moratorium.md`](../decisions/0011-stable-major-tag-moratorium.md) — why v3.7+ is frozen
- [`docs/decisions/0012-phabsim-real-fortran-validation.md`](../decisions/0012-phabsim-real-fortran-validation.md) — the R-PHABSIM-REAL track
- [`CHANGELOG.md`](../../CHANGELOG.md) — authoritative source for each ship's findings
- [`feedback_review_cadence`](../../.claude/projects/-mnt-data-openlimno/memory/feedback_review_cadence.md) — author memory rule on when to trigger the next full triple-AI round
