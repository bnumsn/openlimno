# SCP-0001 Patch — Proposed SPEC §13.9 + §13.10 rewrite

> Companion file to [SCP-0001](0001-native-ibm-pivot.md). This file is
> the **literal text patch** the PSC would apply to `SPEC.md` if the
> charter pivot ratifies. Until PSC vote closes (blocked on U1+U2),
> this file is a DRAFT proposed amendment — `SPEC.md` itself is NOT
> modified.

## Current text (SPEC.md v0.5, lines 998-1002)

```
### 13.9 IBM
P3, M10+。引入感官场契约 (Gemini 评审建议)。

### 13.10 种群动力学
P3, M11+。
```

## Proposed replacement (SCP-0001 patch — apply if/when PSC ratifies)

```
### 13.9 IBM — Native inSTREAM-7 successor (v4 target)

**Priority**: P1 (post-1.0 charter expansion per SCP-0001 + ADR-0014).
**Milestone**: v4.0 (NOT 1.0).
**Status (2026-05-26)**: Prototype code merged to main via
[ADR-0016](decisions/0016-author-override-direct-merge.md) author
override. Charter ratification PENDING PSC vote on SCP-0001.

OpenLimno's native IBM engine (``openlimno.ibm``) implements a
non-NetLogo inSTREAM-7-equivalent individual-based salmonid model
in pure Python. It consumes OpenLimno habitat-cell tables directly
(no NetLogo I/O conversion at runtime) and emits population-summary
tables that integrate with OpenLimno's WEDM/provenance chain.

**Capability surface** (v4 acceptance):

- Daily light-phase fish behaviour (dawn / day / dusk / night)
- Habitat / activity selection from cell CSI + depth + velocity +
  cover + temperature + turbidity + size-priority + density
  competition
- Bioenergetic growth (mass, foraging opportunity, respiration,
  activity cost)
- Mortality (baseline, predation exposure, thermal stress,
  velocity stress)
- Spawning + redd state during configurable window
- Temperature-dependent redd development + fry emergence
- Multi-reach state with ordered-adjacent cross-reach migration
  for calibrated movement studies
- Output tables: population summary, final individuals, cell use,
  events, redd status, optional per-fish daily history

**inSTREAM 7 compatibility (NOT byte-for-byte equivalence)**:

The native engine reads inSTREAM 7 official input files (case
parameter files, GIS reach shapefiles, hydraulic time-series,
initial-population CSV) and produces compatible output schemas
for the BriefPopOut comparison path. Acceptance threshold per
benchmark case lives in `benchmarks/instream7/acceptance.yaml`
(deferred until R-INSTREAM7-FIXTURE track ships official-case
goldens).

**Provenance**: Standalone IBM runs emit `provenance.json` with
the `openlimno-provenance/0.1+ibm` schema (extension of the
canonical Case provenance). When wrapped in `Case.run`, the IBM
output folds into the canonical `provenance.json` chain.
`ibm_run_manifest.json` continues to be emitted for IBM-specific
keys; the two files are SHA-linked via `provenance.ibm.manifest_sha256`.

**Charter promise restraint**:

The native IBM is NOT advertised as a regulatory-grade replacement
for inSTREAM 7 until:

1. ≥ 3 official inSTREAM 7 benchmark cases pass at documented
   tolerance.
2. Seed → identical-output reproducibility test passes in default CI.
3. Round-22 architectural blockers (per ADR-0016) all close.
4. ≥ 1 reviewer-of-record signs an output package (U5).

Until those four conditions close, the project's public claim is
"research-grade native IBM, inSTREAM-7-compatible". The CHANGELOG
"v4-research-track" marker per ADR-0014 § "Implementation notes"
should appear on any version that brings new IBM capability surface.

### 13.10 种群动力学 — Provided via native IBM (v4 target)

**Priority**: Subsumed by §13.9 native IBM (post-1.0 charter
expansion).
**Milestone**: v4.0.

Population-dynamics surface (abundance, biomass, persistence,
demographic structure, multi-species outcomes) is now provided by
the native IBM in §13.9 rather than as a separate workstream. The
v4 acceptance criteria for the native IBM (above) include
population-summary table emission and identifiability diagnostics
across ensemble runs.

The original §13.10 text ("P3, M11+") is superseded.
```

## Diff view (for PR reviewer convenience)

```diff
-### 13.9 IBM
-P3, M10+。引入感官场契约 (Gemini 评审建议)。
-
-### 13.10 种群动力学
-P3, M11+。
+### 13.9 IBM — Native inSTREAM-7 successor (v4 target)
+
+**Priority**: P1 (post-1.0 charter expansion per SCP-0001 + ADR-0014).
+**Milestone**: v4.0 (NOT 1.0).
+**Status (2026-05-26)**: Prototype code merged to main via
+[ADR-0016] author override. Charter ratification PENDING PSC vote.
+
+OpenLimno's native IBM engine (``openlimno.ibm``) implements a
+non-NetLogo inSTREAM-7-equivalent individual-based salmonid model
+[... full capability surface text per proposed-replacement above ...]
+
+### 13.10 种群动力学 — Provided via native IBM (v4 target)
+
+**Priority**: Subsumed by §13.9 native IBM.
+**Milestone**: v4.0.
+
+Population-dynamics surface is now provided by the native IBM in
+§13.9 rather than as a separate workstream.
+
+The original §13.10 text ("P3, M11+") is superseded.
```

## What this patch does NOT change

- **SPEC.md §0.3** (1.0 non-goals list) — UNTOUCHED. The string
  "个体行为模型 (IBM/ABM) / 种群动力学" stays in §0.3 because IBM
  is NOT in 1.0; it's v4. The §0.3 statement remains correct as
  written.
- **CAPABILITY_BOUNDARY_1_0.md** (1.0 D-criteria) — UNTOUCHED.
  IBM is not part of 1.0's DoD.
- **ADR-0011 moratorium** — UNTOUCHED. The IBM-specific exception
  is documented in ADR-0014 + ADR-0015 + ADR-0016, not in
  ADR-0011's text.
- **SPEC.md §13.11 - §13.18** (other research-route items) —
  UNTOUCHED.

## What enables this patch to be applied

This patch is **NOT yet applicable** to SPEC.md. Application
requires:

1. PSC quorum (≥ 5 members per GOVERNANCE.md). U1+U2 must close
   first.
2. PSC majority vote on SCP-0001 + this patch.
3. 14-day public-comment window before PSC vote per GOVERNANCE.md
   § "SPEC change process".
4. Merge commit to main amending SPEC.md from v0.5 → v0.6, with
   updated Appendix B history table.

When the four conditions close, the patch above (the
"Proposed replacement" section) is the literal text the SPEC.md
editor applies. Until then, this file is DRAFT and SPEC.md
remains unchanged.

## See also

- [SCP-0001 main document](0001-native-ibm-pivot.md)
- [ADR-0014](../decisions/0014-charter-pivot-native-ibm.md) — strategic rationale
- [ADR-0015](../decisions/0015-ibm-moratorium-exception.md) — moratorium relationship
- [ADR-0016](../decisions/0016-author-override-direct-merge.md) — author override of Option Z
- [Round 21-23 audit](../../reviews/round_21_22_23_native_ibm_pivot_audit.md) — review chain
