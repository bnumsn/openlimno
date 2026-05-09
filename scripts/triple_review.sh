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
# Requires: codex, gemini, claude CLIs on PATH; git working tree clean.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BASE="${1:-${BASE:-origin/main}}"
# Round-4 review (Gemini) caught that the previous `case` blacklist
# missed parens, braces, newlines. ``git check-ref-format`` is git's
# own canonical validator — strictly stricter and standard. We allow
# 40-char SHAs in addition since ``check-ref-format`` rejects bare
# hex strings. Refnames containing slashes (e.g. ``origin/main``) need
# ``--allow-onelevel``.
# Round-6 review (Codex P1): a 7-char hex string like 'e990c00' is
# rejected by the SHA regex (>=8 chars) but ACCEPTED by
# check-ref-format as a one-level ref name — so the 8-char minimum
# we documented as "collision protection" wasn't enforced. Reject
# short hex BEFORE falling back to ref-format validation.
if [[ "$BASE" =~ ^[0-9a-f]+$ ]] && [ "${#BASE}" -lt 8 ]; then
    echo "ERROR: short SHAs (<8 chars) rejected — collision risk on busy repos" >&2
    exit 2
fi
if ! [[ "$BASE" =~ ^[0-9a-f]{8,40}$ ]] \
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
        # Two modes:
        #   * CI-style (ANTHROPIC_API_KEY set): --bare for hermetic, stateless
        #     invocation. Skips keychain / hooks / plugin sync. Required for
        #     reproducible review on a clean GitHub Actions runner.
        #   * Local-style (no API key): rely on the user's logged-in session.
        # Either way we feed the prompt + diff via stdin (NOT argv) so we
        # don't hit ARG_MAX on big diffs.
        if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
            CLAUDE_FLAGS=(-p --bare --add-dir "$REPO_ROOT")
        else
            CLAUDE_FLAGS=(-p --add-dir "$REPO_ROOT")
        fi
        {
            cat "$PROMPT_FILE"
            echo
            echo "Diff to review:"
            echo '```diff'
            cat "$DIFF_FILE"
            echo '```'
        } | claude "${CLAUDE_FLAGS[@]}" 2>&1
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
