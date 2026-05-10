#!/usr/bin/env bash
#
# Three-AI code review: runs Codex, Gemini, and Claude Code in parallel
# against the same diff, lands per-reviewer outputs as Markdown.
#
# Why three? alpha.2 shipped non-functional because Claude alone tested
# only the dev-venv path. Codex caught that. Round-2 Codex flagged a
# Gemini-shaped concern. Round-2 Gemini flagged a Codex-shaped concern.
# No single reviewer is sufficient — they have different blind spots.
#
# Usage:
#     scripts/triple_review.sh                # diff against origin/main
#     scripts/triple_review.sh v0.1.0-alpha.3 # diff against given ref
#     BASE=v0.1.0-alpha.3 scripts/triple_review.sh
#
# Outputs:
#     reviews/<sha>.codex.md
#     reviews/<sha>.gemini.md
#     reviews/<sha>.claude.md
#     reviews/<sha>.summary.md   (cross-references all three)
#
# Requires: codex, gemini, claude CLIs on PATH AND each logged in via
# its subscription (ChatGPT / Google AI / Anthropic Console). API-key
# auth is intentionally not used — see docs/triple_review.md for why.
# Git working tree must be clean.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BASE="${1:-${BASE:-origin/main}}"
# Round-3 review (Claude): defend against ``-``-prefixed BASE values
# being interpreted as flags by downstream git commands. (``--``
# after ``--verify`` doesn't work — it makes git treat the arg as a
# pathspec — and ``--end-of-options`` isn't honored uniformly across
# rev-parse modes. A simple upfront pattern check is the most
# portable form of belt-and-suspenders.)
case "$BASE" in
    -*)
        echo "ERROR: refnames starting with '-' are not allowed (flag-injection risk)" >&2
        exit 2
        ;;
esac
# Round-4 review (Gemini) caught that the previous `case` blacklist
# missed parens, braces, newlines. ``git check-ref-format`` is git's
# own canonical validator — strictly stricter and standard. We allow
# 40-char SHAs in addition since ``check-ref-format`` rejects bare
# hex strings. Refnames containing slashes (e.g. ``origin/main``) need
# ``--allow-onelevel``.
# Round-1 review (Codex P2 + Gemini + Claude consensus, post-alpha.10):
# the previous "reject only 7-char hex" rule still let 4-6 char
# abbreviated SHAs (e.g. ``git rev-parse --short=6``) bypass collision
# protection — they pass ``check-ref-format --allow-onelevel`` as
# valid one-level refnames. Disambiguate by checking whether the
# hex-shaped value is *actually* a real branch/tag in this repo. If
# it is, allow (legit ``cafe`` branch). If it's not, reject as an
# abbreviated SHA. Round-7's case-insensitive lowercasing preserved.
# 8+ char SHAs and refnames-with-slashes unchanged.
base_lower="$(printf '%s' "$BASE" | tr 'A-F' 'a-f')"
# v0.1.0-final residual #2 (post-alpha.13 Claude post-ship): widen
# the disambiguation from 4-7 to 4-39 char hex. A real branch named
# ``cafebabe`` (8 chars, all-hex) was previously parsed as a SHA
# without checking; now any hex-shaped string up to 39 chars must
# resolve to a refname or be rejected. 40-char hex is still
# accepted unconditionally as the canonical full-SHA case.
if [[ "$base_lower" =~ ^[0-9a-f]{4,39}$ ]]; then
    # Round-2 review (Claude P1 #4): the previous version checked
    # ``show-ref --verify`` against the *original-case* $BASE while
    # the regex tested $base_lower, so a user passing ``CAFE`` for a
    # real ``cafe`` branch hit the false-reject path. ``rev-parse
    # --symbolic-full-name`` is case-sensitive (correctly) and covers
    # heads/tags/remotes/HEAD-relative in one call.
    # v0.1.0-final residual #2: must also check exit code — for
    # non-existent refs, ``rev-parse --symbolic-full-name`` exits 128
    # but ECHOES the input back to stdout (with stderr error
    # suppressed), so a stdout-only check passes them through. The
    # corollary: any 4-39 char hex string that isn't a real refname
    # (whether it's an abbreviated SHA or just garbage) gets rejected.
    # Disable errexit around the rev-parse: it exits non-zero on a
    # non-existent ref but echoes the input to stdout; we need both
    # the exit code AND the stdout to disambiguate refnames from
    # abbreviated SHAs from garbage.
    set +e
    full_name=$(git rev-parse --symbolic-full-name "$BASE" 2>/dev/null)
    rc=$?
    set -e
    if [ "$rc" -ne 0 ] || [ -z "$full_name" ]; then
        # v0.1.0 RC review (Claude): the previous "looks like an
        # abbreviated SHA" message read as a guess in the case where
        # the user actually pasted an 8-char SHA they got from
        # ``git log --oneline``. It's not a guess — short hex strings
        # are unconditionally rejected here for collision protection,
        # whether they resolve unambiguously today or not. Make the
        # message reflect that contract.
        echo "ERROR: '$BASE' is hex-shaped and ${#BASE} chars but is not a refname. Abbreviated SHAs (any length <40) are not accepted — pass the full 40-char SHA or a real branch/tag/refname for collision-stable audit trails." >&2
        exit 2
    fi
fi
if ! [[ "$base_lower" =~ ^[0-9a-f]{40}$ ]] \
        && ! [[ "$base_lower" =~ ^[0-9a-f]{4,39}$ ]] \
        && ! git check-ref-format --allow-onelevel "$BASE" 2>/dev/null; then
    echo "ERROR: '$BASE' is not a valid ref name or SHA" >&2
    exit 2
fi
HEAD_SHA="$(git rev-parse --short HEAD)"
HEAD_REF="$(git rev-parse --abbrev-ref HEAD)"
REVIEWS_DIR="reviews"
mkdir -p "$REVIEWS_DIR"

OUT_CODEX="$REVIEWS_DIR/${HEAD_SHA}.codex.md"
OUT_GEMINI="$REVIEWS_DIR/${HEAD_SHA}.gemini.md"
OUT_CLAUDE="$REVIEWS_DIR/${HEAD_SHA}.claude.md"
OUT_SUMMARY="$REVIEWS_DIR/${HEAD_SHA}.summary.md"

DIFF_FILE="$(mktemp /tmp/review-diff.XXXXXX.patch)"
trap 'rm -f "$DIFF_FILE"' EXIT

# --- Generate the diff ---------------------------------------------------
echo "==> Generating diff: $BASE..HEAD ($HEAD_SHA on $HEAD_REF)"
# Resolve $BASE to a SHA so we fail loudly on misspelled refs (rather
# than silently producing an empty diff). Round-3 review caught the
# `git diff || true` swallowing this exact failure.
if ! BASE_SHA="$(git rev-parse --verify "${BASE}^{commit}" 2>/dev/null)"; then
    echo "ERROR: can't resolve BASE='$BASE' — fetch it or pass a valid ref" >&2
    exit 2
fi
# No path filter: every changed file gets reviewed, including
# scripts/, .github/workflows/, docs/, pyproject.toml. Round-3 review
# caught the original filter excluding the very files of the orchestrator
# itself.
# Triple-dot semantics: diff against the merge-base, not the raw range.
# Codex round-3 caught that on a feature branch behind main, the
# two-dot form would include the *inverse* of unrelated main commits.
git diff "$BASE_SHA...HEAD" > "$DIFF_FILE"
DIFF_LINES=$(wc -l < "$DIFF_FILE")
echo "    diff: $DIFF_LINES lines"
if [ "$DIFF_LINES" -eq 0 ]; then
    echo "    no changes — nothing to review"
    exit 0
fi

# --- Build the shared review prompt --------------------------------------
PROMPT_FILE="$(mktemp /tmp/review-prompt.XXXXXX.txt)"
trap 'rm -f "$DIFF_FILE" "$PROMPT_FILE"' EXIT

cat > "$PROMPT_FILE" <<EOF
You are reviewing a Git diff on the OpenLimno project (open-source water-
ecology modeling, successor to PHABSIM/River2D/FishXing). The diff range
is $BASE..$HEAD_SHA on branch $HEAD_REF.

Read the unified diff supplied below (~$DIFF_LINES lines), then evaluate.
Cover:

1. Architecture — is the change consistent with what the rest of the
   codebase does? Any unjustified new abstraction?
2. Bug risk — what corner cases are missed? Race conditions, path
   traversal, integer overflow, CRS mismatches, file-handle leaks?
3. Test adequacy — what's NOT covered? Could a regression here pass
   the new tests? What minimum extra coverage would you require?
4. Performance — any O(n^2) hot paths, memory leaks, blocking I/O on
   the GUI thread?
5. Packaging / portability — anything in the build that won't reproduce
   on a clean GitHub Actions runner?
6. Security — anything user-supplied that gets concatenated into shell,
   SQL, or HTTP? Privileged file overwrites? Symlink TOCTOU?

Be specific. Cite file:line where relevant. Do NOT praise. List real
concerns only. Cap at ~600 words.
EOF

# --- Run all three reviewers in parallel ---------------------------------
echo "==> Launching Codex, Gemini, Claude in parallel..."

(
    set +e
    {
        echo "# Codex review — \`$BASE..$HEAD_SHA\`"
        echo
        echo "_Generated by \`codex review --base $BASE\` on $(date -Iseconds)_"
        echo
        # v0.1.0-final residual #1 + RC reviews (Codex P2 + Claude):
        # strip every Codex/OpenAI auth or routing env var the CLIs
        # are documented to honor. The list is conservative — when in
        # doubt prefer to strip than to risk silent API fallback. Names
        # here cover: classic API-key auth, organization scoping
        # (which changes billing), endpoint override (which changes
        # provider), Azure routing, project ID for newer auth flows.
        env -u OPENAI_API_KEY -u OPENAI_BASE_URL -u OPENAI_API_BASE \
            -u OPENAI_ORG_ID -u OPENAI_ORGANIZATION \
            -u OPENAI_PROJECT_ID -u OPENAI_API_TYPE \
            -u CODEX_API_KEY \
            codex review --base "$BASE" --title "Triple-review: $HEAD_REF $HEAD_SHA" 2>&1
    } > "$OUT_CODEX"
) &
PID_CODEX=$!

(
    set +e
    {
        echo "# Gemini review — \`$BASE..$HEAD_SHA\`"
        echo
        echo "_Generated by \`gemini -p\` on $(date -Iseconds)_"
        echo
        # v0.1.0-final residual #1 + RC reviews (Codex P2 + Claude):
        # strip every Gemini/Google auth or routing env var the CLI is
        # documented to honor. ``GOOGLE_GENAI_USE_VERTEXAI``,
        # ``GOOGLE_CLOUD_PROJECT``, and ``GOOGLE_CLOUD_LOCATION``
        # together select Vertex AI (paid API) vs the logged-in
        # subscription path. ``GOOGLE_GEMINI_BASE_URL`` and
        # ``GOOGLE_APPLICATION_CREDENTIALS`` allow endpoint
        # redirection / service-account auth respectively.
        env -u GEMINI_API_KEY -u GOOGLE_API_KEY \
            -u GOOGLE_GENERATIVE_AI_API_KEY \
            -u GOOGLE_GENAI_USE_VERTEXAI \
            -u GOOGLE_CLOUD_PROJECT -u GOOGLE_CLOUD_PROJECT_ID \
            -u GOOGLE_CLOUD_LOCATION -u GOOGLE_GEMINI_BASE_URL \
            -u GOOGLE_APPLICATION_CREDENTIALS \
            gemini -p "$(cat "$PROMPT_FILE")" < "$DIFF_FILE" 2>&1
    } > "$OUT_GEMINI"
) &
PID_GEMINI=$!

(
    set +e
    {
        echo "# Claude review — \`$BASE..$HEAD_SHA\`"
        echo
        echo "_Generated by \`claude -p\` on $(date -Iseconds)_"
        echo
        # CLI-only: rely on the user's logged-in `claude` session
        # (Anthropic Console subscription). API-key mode (--bare with
        # ANTHROPIC_API_KEY) is intentionally not supported — see
        # docs/triple_review.md "Why CLI subscription, not API". Feed
        # prompt + diff via stdin (NOT argv) to dodge ARG_MAX on big
        # diffs.
        # Round-2 review (Codex P2): `claude -p` silently honors
        # ANTHROPIC_API_KEY whenever it's set. A stale env var from
        # an old API-based setup would either fail before reaching
        # the subscription session, or worse, bill the API silently
        # despite the "CLI-only" promise. Strip it for this invocation
        # via `env -u`.
        # Round-3 review (Claude): also strip ANTHROPIC_AUTH_TOKEN
        # and ANTHROPIC_BASE_URL — claude-code honors the whole
        # family. Stripping only one of the three would still let
        # API auth sneak in. (RC review: ANTHROPIC_BASE_URL is
        # already in the env -u list below.)
        {
            cat "$PROMPT_FILE"
            echo
            echo "Diff to review:"
            echo '```diff'
            cat "$DIFF_FILE"
            echo '```'
        } | env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL \
                claude -p --add-dir "$REPO_ROOT" 2>&1
    } > "$OUT_CLAUDE"
) &
PID_CLAUDE=$!

# Wait for all three; record exit codes. Round-3 review (Codex) caught
# that with `set -e` active, a non-zero `wait` immediately terminates
# the script — so the prior aggregation logic was DEAD CODE that never
# ran when any reviewer failed. Now we explicitly disable errexit
# around the waits (the `|| true` form is too easy to mis-edit), then
# re-enable below for the rest of the script.
set +e
wait $PID_CODEX; CODEX_RC=$?
wait $PID_GEMINI; GEMINI_RC=$?
wait $PID_CLAUDE; CLAUDE_RC=$?
set -e

# Detect content-level failures too: a review file containing only the
# script-side header (no actual review body) is a failure even if the
# CLI returned 0. We use a simple heuristic — body must be > N lines.
HEADER_LINES=4   # script writes 4 header lines per file
declare -A REVIEW_BODY
for f in "$OUT_CODEX" "$OUT_GEMINI" "$OUT_CLAUDE"; do
    if [ -s "$f" ]; then
        body=$(($(wc -l < "$f") - HEADER_LINES))
        REVIEW_BODY[$f]=$body
    else
        REVIEW_BODY[$f]=0
    fi
done

# Aggregate failures across exit-code AND body-length checks. Use
# `(... || true)` on each test so `set -u` doesn't trip when an entry
# is absent; ${FAILURES[@]:-} below provides the same safety on read.
EXIT_CODE=0
FAILURES=()
[ "$CODEX_RC" -ne 0 ] && FAILURES+=("codex(rc=$CODEX_RC)") || true
[ "$GEMINI_RC" -ne 0 ] && FAILURES+=("gemini(rc=$GEMINI_RC)") || true
[ "$CLAUDE_RC" -ne 0 ] && FAILURES+=("claude(rc=$CLAUDE_RC)") || true
for f in "$OUT_CODEX" "$OUT_GEMINI" "$OUT_CLAUDE"; do
    if [ "${REVIEW_BODY[$f]}" -le 1 ]; then
        FAILURES+=("$(basename "$f")(empty-body)")
    fi
done

echo "==> Reviews written:"
for f in "$OUT_CODEX" "$OUT_GEMINI" "$OUT_CLAUDE"; do
    if [ -s "$f" ] && [ "${REVIEW_BODY[$f]}" -gt 1 ]; then
        echo "    ✓ $f ($(wc -l < "$f") lines)"
    elif [ -s "$f" ]; then
        echo "    ⚠ $f (header-only — reviewer didn't produce content)"
    else
        echo "    ✗ $f (empty)"
    fi
done

if [ "${#FAILURES[@]}" -gt 0 ]; then
    # `${FAILURES[*]}` is safe here — we already gated on length.
    echo "==> FAILED reviewers: ${FAILURES[*]}"
    EXIT_CODE=1
fi

# --- Summary ------------------------------------------------------------
{
    echo "# Triple-AI review — $BASE..$HEAD_SHA"
    echo
    echo "_$(git log -1 --pretty=format:'%s' HEAD)_"
    echo
    echo "_Generated $(date -Iseconds) on \`$(uname -s) $(uname -r)\`_"
    echo
    echo "## Reviewers"
    echo
    echo "| AI | output | lines |"
    echo "| --- | --- | --- |"
    for f in "$OUT_CODEX" "$OUT_GEMINI" "$OUT_CLAUDE"; do
        ai=$(echo "$f" | sed 's|.*\.\([^.]*\)\.md|\1|')
        if [ -s "$f" ]; then
            echo "| ${ai^} | [\`${f#reviews/}\`](${f#reviews/}) | $(wc -l < "$f") |"
        else
            echo "| ${ai^} | _(failed)_ | 0 |"
        fi
    done
    echo
    echo "## Diff scope"
    echo
    echo "- Range: \`$BASE..$HEAD_SHA\`"
    echo "- Lines: $DIFF_LINES"
    echo "- Files touched:"
    # Round-4 review (Codex) caught the summary previously used a
    # path-filtered two-dot diff, while reviewers see triple-dot
    # unfiltered. Use the same revspec/scope so the artifact lists
    # exactly what was reviewed.
    git diff --name-only "$BASE_SHA...HEAD" \
        | sed 's/^/  - /'
    echo
    echo "## Reading order"
    echo
    echo "1. Each reviewer above sees the same diff with the same prompt."
    echo "2. Read all three before triaging — they have different blind spots."
    echo "3. Lessons from past rounds: Claude tested only dev-venv → Codex caught"
    echo "   bundle regressions. Codex assumed live network → Gemini caught it."
    echo "   Three reviewers ≠ overkill, it's structurally necessary."
} > "$OUT_SUMMARY"

echo "==> Summary: $OUT_SUMMARY"
echo
echo "Done. Skim: cat $OUT_SUMMARY"

# Exit non-zero if any reviewer failed (so CI fails the workflow rather
# than uploading auth-error output as a "successful" review). Round-3
# review caught that swallowing failures here masked exactly the
# alpha.5 case where all three reviewers got auth errors but the
# release showed "review attached".
exit "$EXIT_CODE"
