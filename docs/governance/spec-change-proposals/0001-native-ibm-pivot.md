# SCP-0001: Move native IBM from §0.3 non-goal to §13.x active research route

- **Status**: DRAFT (awaiting PSC quorum per GOVERNANCE.md § Decision-making)
- **Filed**: 2026-05-26 on `experiment/native-ibm-pivot` branch
- **Author**: acrochen (project author)
- **Reviewers required**: 3 maintainer reviews + PSC majority vote (per GOVERNANCE.md)
- **Affects**: SPEC.md §0.3 (1.0 non-goals), §13.9 (research route), §13.10
  (population dynamics)
- **Type**: Charter expansion (NOT a 1.0 release scope change; targets v4)

## Background

SPEC.md v0.5 §0.3 explicitly enumerates "个体行为模型 (IBM/ABM) /
种群动力学" as a non-goal for 1.0 to prevent scope creep. The
reasoning was: a single deep solver (SCHISM) plus habitat-based
assessment (HSI/WUA) is enough product surface to ship 1.0; IBM
adds maintainer burden and validation difficulty that 1.0 cannot
afford.

In the 6 days between 2026-05-20 and 2026-05-26, the project author
prototyped a substantial native IBM engine (~9,400 LOC at
`src/openlimno/ibm/` on the `experiment/native-ibm-pivot` branch,
including inSTREAM 7 input parsers, NetLogo reference execution
crosswalks, browser-based IBM Studio, scenario/profile contracts,
ensemble/calibration runners, and acceptance reports). This was
done *during* the ADR-0011 moratorium (the same author wrote it 6
days earlier).

Three rounds of triple-AI strategic review (codex + gemini + claude;
docs at `docs/reviews/round_21_22_23_native_ibm_pivot_audit.md`)
converged on:

1. The work is a real charter violation of §0.3, ADR-0011, and the
   external-action phase.
2. The work is technically valuable prototype-grade code, with
   5+ HIGH architectural blockers (provenance fork, third Studio,
   god objects, missing validation features).
3. The right response is Option Z: quarantine on a branch +
   draft formal ratification packet here.

This SCP is the first artifact of that ratification packet. It
asks the eventual PSC (per GOVERNANCE.md, ≥ 5 members) to ratify
the strategic decision before any code lands on `main`.

## Proposed change to SPEC.md

### Current (v0.5, frozen)

> §0.3 1.0 非目标 (重点!)
> 下列能力**明确不在 1.0**, 防止范围蔓延:
> - 个体行为模型 (IBM/ABM) / 种群动力学
> ...

### Proposed (v0.6, post-PSC vote)

§0.3 remains unchanged for 1.0. IBM stays out of 1.0.

NEW §13.X "Native IBM as inSTREAM successor (v4 research track)":

> The native IBM track targets v4.0 (post-1.0 ratification + post-
> moratorium-lift). It implements an inSTREAM 7-equivalent
> individual-based salmonid model in pure Python with:
>
> - Daily light-phase fish behavior (dawn/day/dusk/night)
> - Habitat/activity selection from cell-level CSI + depth +
>   velocity + cover + temperature + turbidity
> - Bioenergetic growth, mortality, spawning, redd development
> - Native Python runtime (no NetLogo dependency at runtime)
> - inSTREAM 7 input format compatibility (parser, NOT executor)
> - Native OpenLimno provenance.json chain (NOT a parallel
>   `ibm_run_manifest.json`)
> - Single OpenLimno Studio shell (NOT a parallel browser
>   workbench)
>
> Acceptance criteria for the native IBM v4 capability:
>
> 1. Bit-comparable to inSTREAM 7 reference outputs on
>    ≥ 3 official cases at Δ ≤ documented tolerance
> 2. Seed → identical-output reproducibility test in default CI
> 3. End-to-end Case.run integration with one minimal example
> 4. Formal calibration report artifact + identifiability
>    diagnostics
> 5. Round-22 architectural findings closed (no god objects,
>   no API sprawl, no schema fork, unified Studio)

## Alternatives considered

### A — Keep IBM as v3.x NetLogo bridge (status quo before pivot)

- Pros: charter compliance; less maintainer burden
- Cons: NetLogo-era architecture; users must edit `.nlogo` files;
  no path to provenance-integrated population response

### B — Native IBM as 1.0 capability (immediate, no v4 wait)

- Pros: maximises strategic momentum
- Cons: 1.0 surface freeze (v1.0.0, 2026-05-12) already declared;
  adding a major new subsystem mid-1.0-line violates the surface
  freeze charter and the U6 production-caller audit's premise
- **Rejected by both AI reviewers (round 23)**: governance theatre risk

### C — IBM as external plugin (separate repo)

- Pros: zero core scope creep; cleanest charter compliance
- Cons: fragments the user experience; provenance chain breaks at
  the plugin boundary; loses the inSTREAM 7 successor product
  position

### D (this SCP) — Charter expansion to v4, prototype on experiment branch

- Pros: preserves the work; gives the pivot a legitimate ratification
  path; doesn't compromise 1.0
- Cons: 30/60/90 day overhead; branch could rot without discipline

## Process gate

This SCP cannot ratify on its own. Per GOVERNANCE.md § Decision-making:

| Step | Requirement | Status 2026-05-26 |
|---|---|---|
| 1. File SCP issue | template-conformant | ✅ This document |
| 2. Public comment | ≥ 14 days | Not started |
| 3. PSC majority vote | 5-member PSC | ❌ No PSC exists yet |
| 4. Update SPEC.md | new version v0.6 | Blocked on (3) |
| 5. Sign new MAINTAINERS rows | ≥ 3 maintainers | ❌ U1 still pending |

**Until step 3 closes, IBM stays on `experiment/native-ibm-pivot`.**

## See also

- [ADR-0014](../decisions/0014-charter-pivot-native-ibm.md) — strategic rationale
- [ADR-0015](../decisions/0015-ibm-moratorium-exception.md) — moratorium relationship
- [Round 21-23 audit](../../reviews/round_21_22_23_native_ibm_pivot_audit.md) — review chain that produced this packet
- `docs/strategy/native-ibm-instream-successor.md` (on this branch) — original strategy doc
- SPEC.md §0.3 (frozen v0.5) — the constraint being amended
