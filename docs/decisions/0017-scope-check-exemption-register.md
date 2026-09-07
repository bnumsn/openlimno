# ADR-0017: SPEC §0.3 scope check — blocking, with an explicit exemption register

- **Status**: Proposed
- **Date**: 2026-09-04
- **Deciders**: (pending) — supersedes the enforcement *mode* of ADR-0010, not its intent
- **SPEC sections**: §0.3, §3.2, §13
- **Tags**: [governance, scope, ci, tooling]

## Context

ADR-0010 established three scope-discipline layers: a PR-template question,
CODEOWNERS routing, and a CI keyword check
(`tools/m0_checklist/spec_scope_check.py`). It chose **advisory** mode for the
CI check, rejecting hard-fail because of false positives ("a comment mentioning
GPU as future work").

Two defects made that check inert rather than advisory.

### D1 — every multi-word pattern was unreachable

The keyword table wrapped snake_case phrases in `\b`:

```python
>>> re.search(r"\bagent_based\b", "simulate_agent_based_model")
None
```

`_` is a word character, so `\b` never holds at a snake_case seam. Every
multi-word entry (`agent_based`, `ibm_fish`, `langevin_fish`, `data_assim`,
`temperature_advection`, `self_built_swe`, …) was blind to exactly the case it
existed to catch: the keyword embedded in a longer identifier. It fired only on
`def agent_based(`-style bare identifiers, which the codebase does not contain.

Two entries were unreachable outright: `\bbmi\.\b` (a `\b` after `.` requires a
following word character) and `\bibmi_\b` (a `\b` after `_` requires a following
non-word character; `ibmi` is not a term in SPEC or the codebase — almost
certainly a typo for `bmi_`).

### D2 — the largest §0.3 breach was not in the keyword table at all

The table had `agent_based`, `ibm_fish` and `langevin_fish`, but not `ibm` or
`abm` — the two acronyms SPEC §0.3 actually uses ("个体行为模型 (IBM/ABM)"), and
the ones ADR-0010's own implementation sketch named. Consequently
`src/openlimno/ibm/` (11,136 LOC, 26% of `src/`) produced **zero** hits even
after D1 is fixed. The check reported `OK` for months.

### D3 — advisory in the docstring, gate in CI

The script's docstring said "advisory, not blocking", and it returned `0`
unconditionally. But `.github/workflows/ci.yml` lists `spec-scope-check` in
`ci-success.needs`, and `.pre-commit-config.yaml` runs it as a hook. The wiring
was blocking; the exit code was not. Nobody could tell which was intended.

### The real constraint

The §0.3 non-goal code on `main` is not smuggled. `src/openlimno/ibm/` is a
declared research route (ADR-0014/0015/0016, SCP-0001, README "What 1.0 does NOT
do", SPEC §13). Simply repairing the regex would have turned CI red over code
the project consciously chose to carry. The tool has to be able to say *"yes,
there is agent-based code here, and here is the document that authorised it"*.

## Decision

1. **Boundary policy replaces `\b`.** Two pattern classes, each entry in the
   table carrying its own recorded rationale:
   - *multi-word phrases* are unanchored, joined with `[_-]?` (so snake_case,
     kebab-case and CamelCase all match), with a trailing guard that branches
     on the **case style of the text the body just consumed**:
     `(?:(?<=[a-z])(?![a-z])|(?<=[0-9A-Z])(?![A-Za-z]))`.
     - Body ends lowercase → CamelCase spelling, where an uppercase letter
       starts a new word: only a following *lowercase* letter is forbidden.
       `AgentBased` + `Model` matches; `runtime_min` + `utes` does not.
     - Body ends uppercase or digit → SCREAMING_SNAKE spelling, where case
       transitions carry no meaning (only `_` separates words): *any*
       following letter is forbidden. `AGENT_BASED` + `_MODEL` matches;
       `RUNTIME_MIN` + `UTES` does not.

     A plain lookahead cannot separate those two cases — they are
     indistinguishable from the next character alone. An earlier revision used
     `(?![a-z0-9])`, which implemented only the lowercase half and therefore
     false-positived on every SCREAMING_SNAKE near-miss (`RUNTIME_MINUTES`,
     `HEAT_BALANCER_ID`). Digits are permitted on both sides, since a digit
     never continues an English word: `TemperatureAdvection1d` is the keyword
     plus a dimension suffix, not a different term.

     `IGNORECASE` is scoped to the phrase body via `(?i:…)`; a global
     `re.IGNORECASE` would make the lookbehind's `[a-z]` / `[0-9A-Z]` classes
     collapse into each other and destroy the case-style branch.
   - *short tokens / abbreviations* keep a strict boundary, but expressed as
     "the whole alphanumeric run must be this word"
     (`(?<![0-9A-Za-z])word(?![0-9A-Za-z])`) rather than `\b`. This keeps
     `wasps` and `space` out while letting `_` read as the separator it is, so
     `my_wasp_model` and `polynomial_chaos_pce` now match.

2. **Keyword coverage closes D2**: `ibm`, `abm`, `individual_based` and
   `population_dynamics` are added — the acronyms and phrases §0.3 itself uses.

3. **An exemption register replaces silent tolerance.** `EXEMPTIONS` is a list
   of `(path glob, specific keywords, reason, basis)` records. It is validated
   at every run: no wildcard keyword (a "whole tree, everything" carve-out is
   not expressible), no unknown or duplicated keyword id, a non-empty reason,
   at least one basis, and every basis that looks like a repo document must
   exist on disk. A stale ADR reference therefore fails the check rather than
   quietly legitimising code.

4. **Exempted hits are printed, not swallowed.** Every run lists each rule, its
   reason, its basis citations, and the per-file hit counts it absorbed. The
   fact that `src/openlimno/ibm/` carries ~250 IBM references by decision is
   visible in every CI log.

5. **Blocking on unexempted hits.** Exit `1` when a hit matches no rule, `2`
   when the register itself is malformed, `0` otherwise. `--advisory` forces
   `0` for local pre-flight use. The docstring and the exit code now agree with
   the CI wiring.

## Alternatives considered

### A — Fix the regex only, keep advisory

- Pros: smallest diff; no risk of blocking anyone.
- Cons: the tool would still return `0` on a real violation, which is the
  status quo it was supposed to fix. An "enforcement layer" whose exit code is
  a constant is documentation, not enforcement.
- Verdict: rejected.

### B — Fix the regex, go blocking, no exemptions

- Pros: maximally strict.
- Cons: turns CI red over `src/openlimno/ibm/`, which the project decided to
  carry (ADR-0016). Pressure would immediately be to delete keywords from the
  table — i.e. to make the tool lie again, less visibly.
- Verdict: rejected.

### C — Blocking with a per-line `# noqa: spec-scope` marker

- Pros: no central register to maintain.
- Cons: the justification lives next to the code and never gets audited; ~250
  markers in `ibm/` alone; no place to cite an ADR. Loses the property that a
  reviewer can read the whole carve-out surface in one screen.
- Verdict: rejected.

### D (this ADR) — Blocking with a narrow, cited, printed exemption register

- Pros: ADR-0010's false-positive objection is answered by the register rather
  than by never failing; the carve-out surface is one auditable list; the
  register cannot rot silently (basis-existence is validated).
- Cons: adding legitimate research code now requires a register edit and a
  citable document. That friction is the point, but it is friction.

## Consequences

### Positive

- The check can now fail, and therefore now means something.
- The §0.3-vs-`main` gap that ADR-0016 recorded in prose is re-stated in
  machine-checkable form and re-printed on every CI run.
- Stale governance references (a deleted or renamed ADR cited as a basis) break
  the build.

### Negative

- New §0.3-adjacent code needs a register entry before CI goes green.
- `flask` and `helm` are ordinary English words in a limnology/rigging sense.
  The strict token boundary limits the damage, but a false positive there costs
  a register entry or a pattern tightening.

### Neutral / Acknowledged trade-offs

- The keyword table is still hand-curated, not parsed from SPEC.md. ADR-0010's
  implementation note claimed the script "reads SPEC.md §0.3 each run"; it never
  did, and §0.3 is prose, not a machine-readable list. The docstring now says so
  instead of repeating the claim.
- Bare `gpu` and `mpi` tokens are deliberately **not** keywords, though
  ADR-0010's sketch listed them. In this codebase they occur only as a browser
  "GPU stall" comment and as the process count for the *external* SCHISM binary
  (ADR-0002) — pure noise. The import-level tokens `cuda`/`cupy`/`cudf` are what
  an actual in-house GPU solver would look like, and those are kept.
- Bare `thermal`/`temperature` are likewise not keywords: temperature as an HSI
  input (`habitat/thermal.py`) is 1.0 scope; §0.3 excludes modelling the heat
  budget, which is what `temperature_advection` / `heat_balance` /
  `riparian_shading` detect.

## Open items

**O1 — `fishtank` has no root-charter basis.** `src/openlimno/fishtank/`
(5,538 LOC) contains an explicit agent-based model
(`simulate_agent_based_model`, `FishAgent`, `MicrobePatch`). Its ABM *is*
declared in-scope — but only by `docs/fishtank/SPEC.md` §0, a module-local
document. The root `SPEC.md` §0.3 and the README "What 1.0 does NOT do" section
do not mention `fishtank` at all, even though README enumerates the `ibm/`
research route in detail. The register exempts it on the module-local basis;
closing O1 means either naming the teaching microcosm in the root charter (as
`ibm/` is named) or moving it out of the 1.0 line.

**O2 — `.pre-commit-config.yaml` and the CI job description still say "warn".**
The hook is named "SPEC scope check (warn if §0.3 keywords appear in 1.0 code)"
and ADR-0010 §Decision says the check "warns, does not auto-fail". With this ADR
it fails. Both wordings need updating; neither file is edited here.

**O3 — Local browser Studios.** `ibm/studio_http.py` and
`fishtank/studio_http.py` serve HTTP UIs from `http.server`. SPEC §0.3 excludes
"Web GUI / 云原生 / 多租户 / REST 服务". The current keyword set encodes web-GUI
scope as *frameworks* (`fastapi`/`flask`/`django`/`tauri`), so a stdlib
localhost Studio is invisible to it. Whether a single-user localhost Studio is
the excluded thing is a charter question, not a tooling one; recorded here
rather than silently decided in a regex.

## Implementation notes

- `tools/m0_checklist/spec_scope_check.py` — rewrite.
- `tests/unit/test_spec_scope_check.py` — pins the `simulate_agent_based_model`
  regression, exempted-but-listed behaviour, unexempted-fails behaviour,
  clean-code no-false-positive behaviour, and the register's own invariants.
- `docs/decisions/index.md` needs a row for this ADR.

## References

- [ADR-0010](0010-spec-scope-discipline.md) — enforcement layers; this ADR
  changes its mode from advisory to blocking-with-register
- [ADR-0004](0004-no-bmi-in-1.0.md) — basis for the `bmi` exemption
- [ADR-0014](0014-charter-pivot-native-ibm.md),
  [ADR-0015](0015-ibm-moratorium-exception.md),
  [ADR-0016](0016-author-override-direct-merge.md) — basis for the `ibm/`
  exemption
- `SPEC.md` §0.3, §13
- `README.md` "What 1.0 does NOT do"
- `docs/fishtank/SPEC.md` §0
