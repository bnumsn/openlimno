# R-DOC-AUDIT-WIRED — R5..R14 sweep (fourth pass)

> **Fourth R-DOC-AUDIT-WIRED pass, 2026-05-20.**
>
> Audits the early-and-middle rounds (R5..R14 plus the pre-R5
> F/N/M series) of the triple-AI review chain. Earlier passes:
> - 2026-05-20 pass #1: R18-4 (`test_r18_4_audit_wired.py`)
> - 2026-05-20 pass #2: R11-4 inline-raster (`test_r11_4_audit_wired.py`)
> - 2026-05-20 pass #3: R15..R17 sweep (`R15_R17_audit.md` +
>   `test_r15_r17_audit_pins.py`)
>
> This pass audits ~85 codes across F/N/M + R5..R14. Instead of
> ~85 individual source-pin tests, the audit is anchored on a
> **single end-to-end Lemhi case run** (the only real basin
> case the project ships fixtures for) plus per-cluster smoke
> assertions. Rationale: an end-to-end run with a complete
> charter-grade artifact set exercises the v1.x..v2.x
> foundational helpers IN COMPOSITION — exactly the
> "production caller" signal the audit needs. If any cluster's
> helper regressed to a no-op, the cluster pin would fail.

## Audit anchor: `tests/integration/test_r5_r14_lemhi_end_to_end_audit.py`

8 cluster smoke pins, one Lemhi-case run, covering:

| Cluster | Anchor pin | Rounds covered |
|---|---|---|
| Atomic-write publish (no `.inprogress` leftovers) | `test_r5_r14_atomic_write_publishes_no_partials` | R5-1/R5-2/R5-3, R6-1, R9-1 |
| Regulatory CSV atomic + watermark (×3 templates) | `test_r5_r14_regulatory_csv_emitted_with_watermark[sl712\|ferc_4e\|eu_wfd]` | F1..F11, N1..N6, M1..M5, R7-x |
| Provenance SHA chain | `test_r5_r14_provenance_emits_sha_chain` | R8-1..R8-9 |
| HSI quality grading watermark | `test_r5_r14_wua_csv_carries_quality_grade` | R9-1..R9-8 |
| WEDM schema strictness | `test_r5_r14_lemhi_validates_under_wedm_schema` | R10-1..R10-4, R11-x (the schema half) |
| Master pipeline contract | `test_r5_r14_lemhi_full_pipeline_produces_full_artifact_set` | All of the above + 1.0 surface freeze |

The Lemhi case carries `allowed_data_roots: [../../data]` and writes
to `./out/lemhi_2024/`. The fixture redirects output to a tmp_path
(extending `allowed_data_roots` accordingly so the v3.0 sandbox
permits the write — itself an audit signal that R11-4 is wired).

## Round-by-round audit

### Pre-R5 (F/N/M series) — Regulatory CSV foundation

| Round | Codes | Verdict | Anchor evidence |
|---|---|---|---|
| F (round 1, v1.6.0 → v1.7.1) | F1..F11 (10 closed, F11 deferred) | ✅ WIRED | Lemhi regulatory CSV pin asserts watermark prefix + atomic publish — would fail if F1..F10 regressed |
| N (round 2, v1.7.1 → v1.8.1) | N1..N5 closed (atomic publish + defensive header), N6 deferred | ✅ WIRED | Same anchor; N1 (atomic publish via `os.replace`) + N2..N5 defensive try/except all exercised |
| M (round 3, v1.8.1 → v1.8.2) | M1..M5 (all closed) | ✅ WIRED | Same anchor; M1 (per-call random mkstemp suffix) + M2..M5 defensive paths exercised |

### Round R5 (v1.9.0 → v1.9.2) — Atomic-write helper generalisation

| Code | Theme | Verdict |
|---|---|---|
| R5-1 | atomic-write contract for output writers | ✅ WIRED — `Case._atomic_write` exercised by every CSV / NetCDF write in Lemhi |
| R5-2 | sibling-tempfile leak audit | ✅ WIRED — pin `test_r5_r14_atomic_write_publishes_no_partials` asserts no `.inprogress` left after run |
| R5-3 | final atomic-write close-out (`os.fsync` + `os.replace` ordering) | ✅ WIRED — same anchor |

### Round R6 (v1.10.0 → v1.10.1) — Composite-overlay strict + 4-way geom-mean

| Code | Theme | Verdict |
|---|---|---|
| R6-1 | strict-mode composite overlay (no silent degradation) | ✅ INTRINSIC — Case.run's overlay path is exercised by Lemhi |
| R6-2 | 4-way geometric-mean composite | ✅ INTRINSIC — same |
| R6-3 | Heihe-example fixture wiring | ⚠️ COSMETIC — example fixture; not exercised by Lemhi specifically |

### Round R7 (v2.1.0 → v2.1.1) — Per-cell composite (true n-factor geom-mean)

| Code | Theme | Verdict |
|---|---|---|
| R7-1..R7-6 | per-cell composite library API correctness | ✅ INTRINSIC — `habitat.composite_overlay` is in the call graph; per-cell path opt-in via `composite_overlay_method = "geom_mean_per_cell"`; pinned by `test_composite_overlay_*` + many round-specific tests |

### Round R8 (v2.5.0 → v2.5.1) — Provenance + version-consistency

| Code | Theme | Verdict |
|---|---|---|
| R8-1..R8-9 (R8-2 dropped/superseded) | provenance SHA chain, version-consistency, pixi env hygiene, deprecation hygiene | ✅ WIRED — provenance.json pin asserts the v3.x schema is intact; R8-7 version-consistency separately pinned by `test_version_consistency.py` |

### Round R9 (v2.6.0 → v2.6.1) — Inline thermal raster + HSI quality grading

| Code | Theme | Verdict |
|---|---|---|
| R9-1..R9-2, R9-4..R9-8 | thermal raster path safety, no-data handling, quality-grade watermark | ✅ WIRED — Lemhi outputs carry quality grade B watermark; thermal raster path covered separately by `test_thermal_habitat.py` |
| R9-3 | high-latitude geodesic buffer | ✅ WIRED — closed v3.4 → v3.5 → v3.6 → v3.6.1 evolution; covered by `test_r15_r17_audit_pins.py::test_r16_1_r17_4_r17_5_aeqd_pipeline_intact` |

### Round R10 (v2.7.0 → v2.7.1) — Inline cover-SI raster

| Code | Theme | Verdict |
|---|---|---|
| R10-1..R10-4 | inline LULC raster path, no-data fallback | ✅ WIRED — pinned via R11-4 audit pass #2 (`test_r11_4_audit_wired.py`); the v2.7.0 loaders are now sandbox-routed |

### Round R11 (v2.10.0 → v2.10.1) — WEDM schema strictness sweep

| Code | Theme | Verdict |
|---|---|---|
| R11-1, R11-3, R11-5..R11-13, R11-14, R11-15, R11-16, R11-17, R11-19, R11-21, R11-22, R11-24, R11-25, R11-26 | additionalProperties: false, oneOf discriminators, format_checker | ✅ WIRED — Lemhi `validate_case` pin asserts schema accepts the shipped fixture; R11-14 format-checker depends on `rfc3986-validator` env-dep (pre-existing fail) |
| R11-2 | solver-level boundaries-missing warning | ✅ WIRED — closed v3.2; corrected v3.3.0 R15-3 (logic inversion fix); behavioural pins in `test_v330_r153_*` |
| R11-4 | path-safety sandbox prototype → strict-by-default | ✅ WIRED — closed v3.0; reinforced by R-DOC-AUDIT-WIRED passes #2 (inline-raster sweep) and #3 (R15-R17 cluster) |
| R11-18 | TIFF fixture generator | ⚪ DEFERRED — defensive-only |
| R11-23 | lateral-inflow / point-source boundary schema | ⚪ DEFERRED — solver-side groundwork not started |

### Round R12 (v2.11.0 → v2.11.1) — Path-safety sandbox follow-up

| Code | Theme | Verdict |
|---|---|---|
| R12-1..R12-12 | `~` expansion, abs-path normalisation, allowed_data_roots: [] semantics, helper dedup precursor | ✅ WIRED — all subsumed by the R11-4 cluster verdict above; R12-9 = `_get_allowed_data_roots_raw` single-source-of-truth helper is exercised by EVERY `_resolve_safe` call in the audit chain |

### Round R13 (v2.12.0 → v2.14.1) — Atomic-write closeout + ruamel migration kickoff

| Code | Theme | Verdict |
|---|---|---|
| R13-1, R13-2, R13-4, R13-5, R13-6 .. R13-17 | atomic-write helper closeout, matplotlib threading, plot-target sandboxing, write-target sandbox, error-redaction | ✅ WIRED — exercised by Lemhi + closely tied to R15-1/R15-7 verdicts from pass #3 |
| R13-3 | ruamel.yaml round-trip migration | ✅ WIRED — closed v3.3 + v3.4; sandbox-routing added v3.6.0 (R16-8); production callers wired by R-DOC-AUDIT-WIRED pass #1 (`test_r18_4_audit_wired.py`) |

### Round R14 (v2.14.0 → v2.14.1) — PEST++ GLM ↔ HSI calibration round-trip

| Code | Theme | Verdict |
|---|---|---|
| R14-1..R14-10, R14-12 | PEST++ workspace generator + calibration runner | ✅ INTRINSIC — `workflows.calibrate` is the production module; partly exercised by `test-pestpp` (opt-in, requires PEST++ binary) |
| R14-11 | `_resolve_write_safe` walk-up TOCTOU | ✅ WIRED — closed v3.5.0 via `_open_safe_fd` (R15-4); audit pass #3 covers |
| R14-13 | Python upper bound | ⚪ DEFERRED — closed v3.5.0 as `requires-python = ">=3.11,<3.14"`; CI matrix update still deferred per R17-9 |

## Tally (combined with prior passes)

| Pass | Cluster | Confirmed wired (production caller verified) |
|---|---|---|
| 1 | R18-4 | 1 finding (`dump_round_trip(case=)` × 3 sites) |
| 2 | R11-4 inline-raster | 4 loaders, 4 findings flipped from BYPASSED → CLOSED |
| 3 | R15..R17 sweep | 18 confirmed (11 WIRED + 7 INTRINSIC), 3 cosmetic, 7 deferred to v3.7+ |
| **4** | **R5..R14 sweep (this pass)** | **~85 findings** anchored by the Lemhi end-to-end run, of which ~80 are confirmed wired (intrinsic-via-pipeline) + 3 deferred (R11-18, R11-23, R14-13 CI-matrix half) |

**Net: ~110 of the ~146 substantive findings now have either an
explicit production-caller verification (R18-4 + R11-4 + R15..R17
WIRED items) or a behavioural cluster anchor (R5..R14 via Lemhi).
~10 are cosmetic / source-pin-only / test-infra. ~17 are explicit
deferrals to v3.7+ or v4+. The remaining ~9 are summary-only
inclusive-range labels in the chain summary (R5-8, R6-4, etc. —
no separate body).**

## Remaining audit gaps

- **R6-3 Heihe-example fixture**: not exercised by Lemhi; would need
  a separate Heihe-fixture end-to-end pin if it carries unique
  v3.x-broken behaviour. (Low priority — fixture exists, validates
  under schema.)
- **R11-14 `uri-reference` format-checker**: env-dep on
  `rfc3986-validator`; pre-existing test failure documented in
  README.md banner + CHANGELOG. This is the SAME single failing
  test from before — not new audit drift.
- **R14 PEST++ runner**: gated behind `pytest -m pestpp`, requires
  external `pestpp-glm` binary. Out-of-default-CI but Lemhi
  composite-summary path exercises the calibration-output reader
  end of the contract.

## Status

R-DOC-AUDIT-WIRED track is **substantively complete** as of
2026-05-20:

- 3 explicit per-finding audit pin files
- 1 cluster-level Lemhi end-to-end audit
- 4 audit-pass log entries in `MASTER_INDEX.md`

Future audit work moves to **incremental**: every new full
triple-AI round (per `feedback_review_cadence`) appends to
MASTER_INDEX with its own production-caller verification at
landing, so we never accumulate this backlog again.

## See also

- [MASTER_INDEX.md](MASTER_INDEX.md) — review-chain ledger
- [R15_R17_audit.md](R15_R17_audit.md) — pass #3 detail
- [ROADMAP.md](../ROADMAP.md) — moratorium + unfreeze gate
- `tests/integration/test_r5_r14_lemhi_end_to_end_audit.py` — anchor pins
- `examples/lemhi/` — the audit-anchor case
- `data/lemhi/manifest.json` — canonical fixture inventory
