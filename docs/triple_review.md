# Triple-AI code review

OpenLimno runs **three** independent AI code reviewers on every release: Codex,
Gemini, and Claude. The alpha.2 release shipped non-functional because a
single reviewer (Claude alone) approved a build that couldn't actually run
cases. The pattern of one-reviewer blind spots repeats: round-2 Codex
flagged what Gemini missed; round-2 Gemini flagged what Codex missed;
round-3 Claude found a TOCTOU bug both others approved.

This document captures the methodology so it survives contributor turnover.

## Why three

A single AI reviewer is structurally insufficient:

- Each model has distinct training data, distinct sandboxing, and distinct
  prompting biases. They miss different things.
- The combinatorial coverage is what makes the review useful, not the depth
  of any one review.
- Three is empirically the smallest ensemble where no two pairs are
  consistently correlated. Two reviewers with similar blind spots produce
  false-positive consensus.

See [docs/reviews/v0.1.0-alpha.4/](reviews/v0.1.0-alpha.4/) for the worked
example where the three diverged sharply on a 92-line diff, and
[docs/reviews/v0.1.0-alpha.10/](reviews/v0.1.0-alpha.10/) for the
8-round audit trail and convergence proof.

## Why CLI subscription, not API

Each reviewer is invoked through its **CLI's own logged-in subscription**
(ChatGPT for Codex, Google AI for Gemini, Anthropic Console for Claude
Code). API keys (`OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`)
are **not used** anywhere — not in the orchestrator, not in CI.

Reasons:

- The maintainer already pays for the three subscriptions; per-call API
  billing on top of that is double-pay.
- Subscription auth has higher rate limits and saner quota behaviour than
  API tier.
- It removes a class of secrets-management risk: no keys to rotate,
  leak, or expire.

The trade-off is that the review is **maintainer-local**: it cannot run on
a headless CI runner, since CLI auth requires interactive OAuth login that
GitHub-hosted runners can't perform. This is intentional; see
[When to invoke](#when-to-invoke).

## When to invoke

| trigger | how | output goes to |
|---|---|---|
| **Pre-commit on a non-trivial PR** | `bash scripts/triple_review.sh origin/main` | `reviews/<sha>.*.md` (gitignored) |
| **Pre-tag locally** | `bash scripts/triple_review.sh <previous-tag>` | `reviews/<sha>.*.md` |
| **Post-tag manual upload** | `gh release create <tag> reviews/<sha>.*.md ...` | release assets |

There is **no GitHub Action** for this — it was tried in alpha.5..alpha.9
and removed in alpha.10 once the API-vs-CLI trade-off was resolved
(see [`feedback_review_cli_only`](#why-cli-subscription-not-api) above
for the rationale).

## Local invocation

```bash
# Default: review HEAD against origin/main
bash scripts/triple_review.sh

# Review against a specific tag
bash scripts/triple_review.sh v0.1.0-alpha.3

# Or via env var
BASE=v0.1.0-alpha.3 bash scripts/triple_review.sh
```

Outputs land in `reviews/<sha>.codex.md`, `reviews/<sha>.gemini.md`,
`reviews/<sha>.claude.md`, plus a `<sha>.summary.md` index. The `reviews/`
directory is gitignored — outputs are per-build artefacts, attached to
GitHub Releases manually via `gh release create` rather than committed
to history.

## Prerequisites

The maintainer's local environment must have all three CLIs installed and
each logged into its own subscription account:

```bash
# One-time setup, done once per machine:
codex auth login    # uses ChatGPT subscription
gemini auth         # uses Google account
claude              # interactive setup with Anthropic Console
```

Verify:

```bash
codex --version
gemini --version
claude --version
```

If any of the three are missing, the orchestrator script will refuse to
run that reviewer and exit non-zero. Don't paper over by skipping; the
whole point is the three-way coverage.

## How to read the output

Open all three review files **before triaging anything**. The pattern that
matters is the *intersection* and *symmetric difference* of findings:

- A concern raised by **all three** → almost certainly real, fix it.
- A concern raised by **two** → likely real, check it carefully.
- A concern raised by **only one** → could be the load-bearing find of the
  round, OR could be a false positive. Read closely. Don't dismiss.
- **No concerns from any** → suspicious. Either the diff is genuinely
  trivial, or the prompt scope was too narrow.

Round 8 (alpha.9..alpha.10) provides the canonical false-positive example:
Claude confidently asserted that `pyarrow.lib.ArrowInvalid` does not
subclass `ValueError`, prescribing a fix that would have been merged in
isolation. Codex's runtime probe (`ArrowInvalid.__mro__`) overruled it.

The summary file (`reviews/<sha>.summary.md`) lists which files each
reviewer touched, but does NOT consolidate findings. That's deliberate:
a meta-AI summary would re-introduce the single-reviewer bias the whole
process is designed to avoid.

## How to act on findings

Per release, the maintainer's job is to triage every flagged concern into
one of three buckets:

1. **Fix this release** — landing in the same alpha/beta tag.
2. **Defer with rationale** — file an issue and link it from the next
   release notes. Don't silently ignore.
3. **Reject with rationale** — same: write the rationale somewhere durable
   so it doesn't re-surface.

The release commit message should call out each fixed concern by reviewer
+ position, like:

```
- gemini: fixture-based smoke test (was Overpass-dependent)
- claude: TOCTOU in cache mtime check
- codex: deferred — `rasterio` exclude (issue #N)
```

This makes the audit trail readable to future maintainers (and to the
next round of reviewers).

## Convergence criterion

A release converges when **Codex reports zero P0 and zero P1** by its
explicit P-tag taxonomy. Gemini and Claude do not use P-tags consistently;
their content-level concerns are documented as known limitations rather
than triggering further fix-rounds.

The pre-committed budget is **3 fix-rounds maximum** between any two
adjacent releases. If round 4+ would be needed, ship with documented
residuals instead. This protects against the failure mode of iterating
reviewer feedback indefinitely — where each round's fix introduces enough
new surface for the next round to find another concern, with no
convergence proof.

## What this process is NOT

- **Not a substitute for human review.** The triple-review surfaces
  candidates; a human still decides which fixes matter and how to make
  the trade-offs.
- **Not a substitute for tests.** Reviewers can identify missing test
  coverage but can't write the tests for you (or rather, they can, but
  the tests they suggest still need human-judged correctness).
- **Not free** — but cheap, since it runs on existing subscriptions
  rather than per-call API billing.

## Origin

The need for this came from a real production incident: Claude approved
v0.1.0-alpha.2 after running 11 self-designed smoke tests, all of which
passed. The shipped AppImage couldn't run a case. Codex found the bug
in one paragraph. Gemini-then-Codex-then-Claude rounds since have each
caught what the others missed.

The first triple-review was on v0.1.0-alpha.4 — see
[docs/reviews/v0.1.0-alpha.4/](reviews/v0.1.0-alpha.4/). The convergence
proof and 8-round audit trail are in
[docs/reviews/v0.1.0-alpha.10/](reviews/v0.1.0-alpha.10/).
