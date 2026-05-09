# Triple-AI review of v0.1.0-alpha.4

_Diff range: [v0.1.0-alpha.3..v0.1.0-alpha.4](../../../compare/v0.1.0-alpha.3...v0.1.0-alpha.4) (10 files, +92/-15)_

This is the canonical showcase of why OpenLimno runs **three** AI reviewers
on every release. The alpha.4 diff was small (parquet cache mtime fix +
fixture-based smoke test + spec docstring) but the three reviewers
diverged sharply on what they flagged.

## Verdicts side-by-side

| reviewer | verdict | most important catch | missed |
|---|---|---|---|
| **[Codex](codex.md)** | "no discrete bugs introduced" | (none — clean) | TOCTOU, fixture rot, missing tests |
| **[Gemini](gemini.md)** | 6 concerns across P1/P2 | parquet cache: partial-read race during external write | TOCTOU between stat and read, parquet CVE risk |
| **[Claude](claude.md)** | 6 concerns, 1 outright bug | **TOCTOU**: stat-before-read caches new content under old mtime | (no major miss this round) |

## What each AI caught that the others missed

### Codex caught nothing the others didn't ✗

Codex's clean bill of health was the *least* useful review this round. Neither
Codex's static-analysis-style approach nor its file-execution probes (it ran
`validate_case()` on the new fixture) detected the TOCTOU window.

### Gemini caught the partial-read race ✓

> If an external process is writing to the parquet file when the GUI triggers
> a read, `_read_wua_parquet` may encounter a locked file or, worse, read a
> corrupted/incomplete footer.

Gemini correctly identified that mtime-based invalidation alone doesn't
protect against in-flight writes. It also flagged blocking I/O on the GUI
thread — a real concern even though it's pre-existing and out of scope for
this diff.

### Claude caught the actual TOCTOU bug ✓ (the load-bearing find)

> `getmtime()` runs *before* `_read_wua_parquet()`. If the parquet is
> rewritten in the gap, you cache new rows under the old mtime, and the
> next click won't re-read.

This is a real bug. The fix landed in [commit 45aa79c](../../../commit/45aa79c)
on the *next* alpha — stat *after* read, key cache on `(path, mtime, size)`.

Claude also flagged:
- **Zero tests for the cache change** — a regression where mtime check
  silently no-ops would pass everything.
- **Fixture rot risk** — the binary parquet/NetCDF fixtures have no
  regeneration script, so when the schema bumps the fixture rots silently.
- **Build requirements are prose, not enforced** — the spec docstring says
  "build host needs apt qgis + pip-installed jsonschema 4.18+" but nothing
  fails at build time if those aren't met.
- **CODEOWNERS for binary fixtures** — pyarrow has heap-corruption CVEs
  against malformed parquet (CVE-2023-47248); binary PR artefacts deserve
  a second pair of eyes.

## Reading order for future maintainers

1. Open the three review files (`codex.md`, `gemini.md`, `claude.md`)
   side-by-side. Read all three before triaging — they have different
   blind spots.
2. Cross-reference findings: a concern raised by 2+ reviewers is high-
   confidence; a concern raised by exactly 1 deserves close inspection
   (it might be the load-bearing find of the round).
3. The release commit message and CHANGELOG should explicitly note which
   findings were fixed-this-release, deferred, or rejected. Audit trail.

## Lesson for future rounds

**A single AI reviewer is structurally insufficient.** This isn't redundancy —
each model has distinct training-data and prompting biases that make it
miss specific bug classes. The combinatorial coverage is what matters.

For OpenLimno specifically:
- **Codex** is best at "does this file even compile / parse / validate?"
- **Gemini** is best at "what real-world conditions could trigger this?"
- **Claude** is best at "what implicit assumption is this code making that
  could fail?"

None of those framings is wrong. None alone is sufficient.
