# Triple-AI review of v0.1.0-alpha.13 — second arc, 4-round convergence

_Diff range: [v0.1.0-alpha.10..v0.1.0-alpha.13](../../../compare/v0.1.0-alpha.10...v0.1.0-alpha.13) (4 commits, ~3,200 line diff dominated by review showcase docs)_

This is the second iteration arc on the v0.1.0-alpha series. The first
(rounds 1-8 culminating in alpha.10) is documented at
[`docs/reviews/v0.1.0-alpha.10/`](../v0.1.0-alpha.10/) and
[`docs/reviews/v0.1.0-alpha.4/`](../v0.1.0-alpha.4/). This arc began
post-alpha.10 with the CLI-only review refactor (commit
[`bd925b8`](../../../commit/bd925b8)) and converged at round 4.

## What this arc actually proves about the methodology

The first arc (alpha.1 → alpha.10) ran for 8 rounds against a moving
codebase across multiple feature areas. This second arc was meant to
be a **single-feature stress test**: the diff is small (4 commits,
mostly the review-process refactor itself), the convergence target
should be quick, and the methodology should produce a clean signal
without exhausting the 3-round budget.

What actually happened, round by round:

| round | commit                                       | who caught the round-defining bug         | bug class                                                           |
|-------|----------------------------------------------|-------------------------------------------|---------------------------------------------------------------------|
| 1     | [`bd925b8`](../../../commit/bd925b8)         | (carry-over from alpha.10 round-8)        | short-SHA validation gap; GUI direct-call paths bypass cache wrapper |
| 2     | [`e05c191`](../../../commit/e05c191)         | **Claude (caught 2 regressions I introduced in r1)** + Codex new finding | case-collision in show-ref; missing EOFError in GUI tuple; ANTHROPIC_API_KEY env-var bypass; OGR resource hygiene; missing-backend retry |
| 3     | [`07b6287`](../../../commit/07b6287)         | Claude (3 real bugs)                      | flag-injection via `-`-prefixed BASE; ANTHROPIC env-var family incomplete; pyarrow exception MRO asymmetry |
| 4     | [`4c6ec27`](../../../commit/4c6ec27)         | Codex (1 new P2 — convergence by tag criterion) | OPENAI_API_KEY / GEMINI_API_KEY also need stripping (consistency with claude path) |

**Round 2 is the load-bearing demonstration:** it caught **two
regressions I introduced in round 1's fixes**. A single-round signoff
would have shipped both. The methodology's value isn't "find bugs in
the original code" — it's "find bugs in the fixes for the bugs found
in the original code." Convergence under iteration is the test.

## Failure modes encountered (non-bugs)

Three real-world friction sources hit during this arc:

1. **Codex hit ChatGPT subscription rate limit at round 3.** "You've
   hit your usage limit. Visit chatgpt.com/codex/settings/usage..."
   Round 3's verdict came from gemini + claude only; round 4 retried
   codex once the limit reset (~30 min later) and landed the
   convergence signal. Documented in
   [`round3-codex.md`](round3-codex.md) — 21-line truncation message.

2. **Gemini hit transient `ECONNRESET` at round 3.** Auto-retried by
   gemini-cli's backoff; succeeded on attempt 2. Visible at the top
   of [`round3-gemini.md`](round3-gemini.md). Did not require human
   intervention.

3. **Claude reviewed the wrong scope at round 1.** Instead of the
   bd925b8 diff (CLI-only refactor + showcase docs), Claude analyzed
   the alpha.10 controller.py state retrospectively and re-graded
   alpha.10's residuals as P0/P1. The findings were technically
   actionable (some shipped as fixes in round 1's commit) but were
   not for *this round's diff*. The other two reviewers stayed in
   scope, so the round still produced useful signal — but it
   illustrates the hazard of single-AI review: one reviewer's
   wrong-scope read would have been treated as authoritative without
   triangulation.

## False positives the methodology overruled

Each round had at least one false positive that the empirical
evidence corrected. The most instructive:

**Round 3 Claude P1: "pass `--` before $BASE in `git rev-parse`."**
Sounds correct: `--` is the standard end-of-options marker. But for
`git rev-parse --verify`, `--` is interpreted as "treat the following
arg as a *pathspec*, not a revision," which breaks the verification
entirely. I applied the fix as prescribed; my own immediate test
caught it (the script started rejecting valid tags); reverted and
replaced with an upfront `case "$BASE" in -*)` rejection. The
maintainer's job is to triage, not to apply blindly — even when
three independent AIs sound confident.

(Round 4 Claude also flagged `ds = None` as cargo-cult cleanup —
arguably correct for CPython refcounting, but defensive against
circular-reference edge cases in OGR. Kept as-is per the OGR
Python-binding idiom.)

## Convergence

By the documented criterion (Codex P0/P1=0 by explicit tag count),
round 4 converged:

| reviewer  | round 4 verdict                  | distinct unique findings        |
|-----------|----------------------------------|----------------------------------|
| **Codex** | 0 P0, 0 P1, **3 P2**             | 2 are stale flags from earlier rounds it didn't pick up; 1 is genuinely new (env-u for codex/gemini) |
| Gemini    | (untagged)                       | redundant ValueError catch; broad RuntimeError; zip strict=False; test gaps; pre-existing perf concerns |
| Claude    | (untagged)                       | MissingParquetBackend ordering invariant; 8-char hex branch bypass; pyarrow.lib import edge case; UX nit on direct-call wording |

## Documented residuals (shipping as alpha.13 known limitations)

These are real concerns that did not trigger a fifth fix-round per
the 3-round budget discipline:

1. **Env-u extension to codex/gemini.** Round-4 Codex P2: only the
   `ANTHROPIC_*` env-var family is stripped; `OPENAI_API_KEY` and
   `GEMINI_API_KEY` would still let those reviewers fall back to
   API auth on a maintainer machine that has them set. Trivial fix
   (3 lines of `env -u` repetition); deferred to v0.1.0 final.

2. **8-char hex branch name bypass.** Round-4 Claude: a real branch
   named `cafebabe` would be parsed as a SHA without the
   disambiguation that the 4-7-char path uses. Edge case in
   practice (8-char all-hex branch names are rare).

3. **`MissingParquetBackend(RuntimeError)` ordering invariant.**
   Round-4 Claude: the cache wrapper's `except MissingParquetBackend:
   raise` clause must precede the broader `except (..., RuntimeError)`,
   else the short-circuit silently breaks. A tooling reorder
   (ruff/sort) could regress this. Mitigation: a unit test pinning
   the behavior would catch it; deferred until the test-coverage gap
   below is addressed.

4. **`from pyarrow.lib import ArrowException` edge case.** Round-4
   Claude: some vendor pyarrow builds may not expose
   `ArrowException`; the import-time failure would silently downgrade
   to the GDAL backend even when pyarrow is otherwise functional.
   Wrap the secondary import in its own `try/except ImportError`
   that sets `ArrowException = None` and falls through cleanly.

5. **Test coverage gap.** Gemini "CRITICAL" across rounds 3-4: none
   of the new exception paths (`MissingParquetBackend`,
   `layer is None`, `ArrowException` normalization, GUI try/except)
   has a unit test. v0.1.0 final must close this before the API
   surface stabilizes.

## Reading order

Each round's three review files are stored as `roundN-{codex,gemini,claude}.md`.
For the methodology paper / future maintainers:

1. Start with **round 2** — the load-bearing example of the
   methodology catching its own iteration drift.
2. Read **round 4** for the convergence signal and the
   subscription-rate-limit failure mode.
3. **Round 1's claude.md** as a wrong-scope cautionary tale.
4. **Round 3** for the false-positive triage example
   (the `--` flag-injection prescription).

## Lesson reinforced

A single round of reviewer feedback is structurally insufficient even
for the AI-review-orchestrator code itself. Round 1 introduced two
regressions that round 2 caught. Round 2's fixes introduced one
edge-case (the `--` misadvice from claude that I temporarily applied)
that round 3's empirical retest caught. The methodology only
converges because each round has a chance to find what the previous
round broke.
