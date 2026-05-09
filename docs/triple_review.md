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

See [docs/reviews/v0.1.0-alpha.4/](reviews/v0.1.0-alpha.4/) for a worked
example where the three diverged sharply on a 92-line diff.

## When to invoke

| trigger | how | output goes to |
|---|---|---|
| **Pre-commit on a non-trivial PR** | `bash scripts/triple_review.sh origin/main` | `reviews/<sha>.*.md` (gitignored) |
| **Pre-tag locally** | `bash scripts/triple_review.sh <previous-tag>` | `reviews/<sha>.*.md` |
| **Tag push (any v* tag)** | GitHub Action `triple-review.yml` (auto) | release assets + 90-day artefact |

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
GitHub Releases by the Action rather than committed to history.

## CI invocation (GitHub Actions)

`.github/workflows/triple-review.yml` triggers on every `v*` tag push.
Required secrets:

- `CODEX_API_KEY` — OpenAI API key with Codex access
- `GEMINI_API_KEY` — Google AI Studio key
- `ANTHROPIC_API_KEY` — Anthropic API key (for `claude -p --bare`)

The workflow:

1. Identifies the previous tag (chronological).
2. Installs the three CLIs via npm.
3. Runs `scripts/triple_review.sh <prev-tag>`.
4. Attaches every `reviews/*.md` to the just-published GitHub Release.
5. Uploads the same files as a 90-day workflow artefact.

## How to read the output

Open all three review files **before triaging anything**. The pattern that
matters is the *intersection* and *symmetric difference* of findings:

- A concern raised by **all three** → almost certainly real, fix it.
- A concern raised by **two** → likely real, check it carefully.
- A concern raised by **only one** → could be the load-bearing find of the
  round, OR could be a false positive. Read closely. Don't dismiss.
- **No concerns from any** → suspicious. Either the diff is genuinely
  trivial, or the prompt scope was too narrow.

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

## What this process is NOT

- **Not a substitute for human review.** The triple-review surfaces
  candidates; a human still decides which fixes matter and how to make
  the trade-offs.
- **Not a substitute for tests.** Reviewers can identify missing test
  coverage but can't write the tests for you (or rather, they can, but
  the tests they suggest still need human-judged correctness).
- **Not free.** Each review uses paid LLM API tokens. Budget accordingly;
  the GitHub Action is rate-limited to one run per tag push.

## Cost back-of-envelope

A 3000-line diff review costs approximately:

| reviewer | tokens in | tokens out | cost |
|---|---|---|---|
| Codex | ~30k | ~3k | $0.50 |
| Gemini | ~30k | ~3k | $0.10 |
| Claude | ~30k | ~3k | $0.45 |
| total / tag | | | **~$1.05** |

Acceptable for the audit-trail value. Cheaper than fixing alpha.2 in
production after beta users found the broken AppImage.

## Origin

The need for this came from a real production incident: Claude approved
v0.1.0-alpha.2 after running 11 self-designed smoke tests, all of which
passed. The shipped AppImage couldn't run a case. Codex found the bug
in one paragraph. Gemini-then-Codex-then-Claude rounds since have each
caught what the others missed.

The first triple-review was on v0.1.0-alpha.4 — see
[docs/reviews/v0.1.0-alpha.4/](reviews/v0.1.0-alpha.4/).
