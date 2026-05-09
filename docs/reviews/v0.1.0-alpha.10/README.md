# Triple-AI review of v0.1.0-alpha.10 — convergence round

_Diff range: [v0.1.0-alpha.9..v0.1.0-alpha.10](../../../compare/v0.1.0-alpha.9...v0.1.0-alpha.10) (4 files, +73/-25)_

This is the eighth and final review round of the v0.1.0-alpha series. It
documents **convergence by the explicit-tag criterion** and three
documented residuals shipped as known limitations rather than attempting
a ninth fix-round.

## Why this round matters

The pre-commitment was: "3 more rounds (alpha.7 → alpha.10) OR until a
round produces zero P0/P1, whichever comes first." That budget protects
against the failure mode of *iterating reviewer feedback indefinitely* —
where each round's fix introduces enough new surface for the next round
to find another concern, with no convergence proof.

Round 8 hit the budget *and* the criterion at the same time:

| reviewer  | P0 | P1 | P2 | total | verdict                                    |
|-----------|----|----|----|-------|--------------------------------------------|
| Codex     | 0  | 0  | 2  | 2     | "regressions but P2"                       |
| Gemini    | —  | —  | —  | 6     | untagged; 1 content-level P1 concern       |
| Claude    | —  | —  | —  | 7     | untagged; 1 content-level P1, 1 false-pos. |

Codex (the only reviewer that uses explicit P-tags) reported **zero P0
and zero P1**. By the documented convergence criterion, this is the
clean round.

## Three residuals shipped as known limitations

These are real concerns, not P0/P1-tagged by any reviewer, documented
here for v0.1.0 final:

1. **Missing-backend retry futility** (Gemini #2 + Claude #1, consensus)
   `_read_wua_parquet` raises `RuntimeError` when neither pyarrow nor
   GDAL is importable. The controller's retry loop catches `RuntimeError`
   as transient and burns 3 attempts × 50 ms backoff before giving up.
   Cosmetic latency on a guaranteed-failure path; no data corruption.
   **Filed as issue:** consider a `MissingBackendError` subclass that the
   controller short-circuits on.

2. **GUI direct-call paths bypass the cache wrapper** (Codex P2)
   `Controller.open_wua_q` and `plot_cross_section` call
   `_read_wua_parquet` directly rather than `_read_xs_rows_cached`.
   Round-7 changed the helper to propagate read failures, so a torn
   parquet now raises through to the GUI handler. Acceptable for an
   alpha — Qt's default exception handler shows a dialog rather than
   crashing — but the cache wrapper should be the single entry point.

3. **OGR fallback resource hygiene** (Claude #3)
   The GDAL/OGR branch never explicitly closes the `Dataset`, and
   `GetLayer(0)` returning `None` on malformed input crashes with
   `AttributeError` (not retried under round-7's narrowed exception
   list). Long-running GUI sessions could leak file handles. Mitigation:
   pyarrow is the bundled-default path; OGR is the fallback that few
   users will hit in practice.

## Round-8 false positive worth recording

Claude flagged as concern #2:

> `pyarrow.lib.ArrowInvalid` inherits from `Exception` in essentially
> every released pyarrow. Neither `OSError` nor `ValueError` catches it.

This is wrong. Codex's review session ran a runtime probe:

```
ArrowInvalid (<class 'pyarrow.lib.ArrowInvalid'>, <class 'ValueError'>,
              <class 'pyarrow.lib.ArrowException'>, <class 'Exception'>, ...)
```

`ArrowInvalid` *is* a subclass of `ValueError`, so the existing
`except ValueError` catches it. This is a textbook example of why
single-reviewer review is dangerous: in isolation Claude's claim looks
authoritative, and the prescribed fix (add `pyarrow.lib.ArrowException`
to the tuple) would have been merged. Codex's empirical probe broke
the false certainty.

## What the 8-round audit trail looks like

| round | tag        | reviewer who caught the round-defining bug | bug class                                                  |
|-------|------------|--------------------------------------------|------------------------------------------------------------|
| 1     | a.2        | (none — shipped broken)                    | scipy.optimize / WEDM schemas excluded from bundle         |
| 2     | a.3        | Codex                                      | non-functional AppImage diagnosed in one paragraph         |
| 3     | a.4        | Claude                                     | TOCTOU between stat and read (load-bearing find)           |
| 4     | a.5        | Codex                                      | `${#FAILURES[@]:-0}` invalid bash; `set -e` killed waits   |
| 5     | a.7        | Claude+Codex                               | torn rows cemented in cache; sibling-tag selection         |
| 6     | a.8        | Codex+Gemini                               | post-stat None bypass; 7-char SHA bypass                   |
| 7     | a.9        | Gemini                                     | `_read_wua_parquet` swallowed Exception → retry unreachable|
| 8     | a.10       | (consensus residuals; no P0/P1)            | convergence                                                |

Every round caught at least one issue invisible to the others. No two
adjacent rounds had the same load-bearing reviewer.

## Reading order for the round-8 reviews

1. [`codex.md`](codex.md) — runtime-probe verification (the
   `ArrowInvalid` MRO check), 2× P2 regression catches.
2. [`gemini.md`](gemini.md) — architectural framing of the
   `RuntimeError`-as-transient design smell.
3. [`claude.md`](claude.md) — priority-ordered concerns with one
   confident false positive that the other two reviewers' empirical
   evidence overruled.

## Lesson for future rounds

Convergence is *defined* by the explicit-tag criterion, not by
"all reviewers happy." Reviewers will always find more concerns —
that's not a failure mode, it's the methodology working. The maintainer's
job is to triage, not to chase clean reviews indefinitely.
