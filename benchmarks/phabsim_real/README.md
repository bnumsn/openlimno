# PHABSIM real-Fortran-run validation (R-PHABSIM-REAL)

> Charter: [CAPABILITY_BOUNDARY_1_0.md](../../docs/governance/CAPABILITY_BOUNDARY_1_0.md) D5
> · Moratorium gate: [ROADMAP.md § How to unfreeze](../../docs/ROADMAP.md#how-to-unfreeze) U3
> · ADR: [ADR-0012](../../docs/decisions/0012-phabsim-real-fortran-validation.md)
> · Status: **SCAFFOLD (2026-05-20)** — directory + plan + Dockerfile
> placeholder landed; USFWS PHABSIM source acquisition + Bovee §5.1 input
> deck + Δ ≤ 1e-3 test still pending.

## Why this exists

`benchmarks/phabsim_bovee1997/` already exists and asserts OpenLimno
reproduces the **closed-form** Bovee 1997 cookbook formulas within
1e-3. That is OpenLimno-vs-paper. CAPABILITY_BOUNDARY D5 requires
something stricter: OpenLimno-vs-Fortran-binary, on the **same input
deck**, at cell granularity. The 2026-05-19 strategic review
(codex S6, CHARTER-BLOCKING) flagged this gap explicitly:

> "Modernise PHABSIM / River2D / FishXing" cannot rest on parsers and
> closed-form analogs. Parity requires real runs, real basins, and
> reviewer acceptance.

This directory holds the **real-run** harness: a containerised USFWS
PHABSIM Fortran binary, the canonical Bovee 1997 cookbook §5.1
(Trapezoidal Channel) input deck, an invocation script, and a
pytest-marker `benchmark` test that runs both PHABSIM and OpenLimno
on the same input and asserts cell-by-cell Δ ≤ 1e-3.

## Plan (per ADR-0012)

The track ships incrementally. Each sub-deliverable is its own commit;
none of them by themselves close U3.

### Sub-deliverables (in order)

| # | Artifact | Status | Notes |
|---|---|---|---|
| 1 | This README (plan + capture) | ✅ 2026-05-20 | This file |
| 2 | `Dockerfile` building USFWS PHABSIM from source | **🟡 placeholder** | Build strategy + apt deps documented; actual `phabsim` binary build pending USFWS source archive acquisition + license verification |
| 3 | `inputs/bovee1997_5_1.dat` input deck | ❌ pending | To be transcribed from the Bovee 1997 cookbook §5.1 (Trapezoidal Channel) — see "Input deck capture" below |
| 4 | `run_phabsim.sh` container invocation | ❌ pending | Mirrors the SCHISM subprocess pattern from `Case.run` |
| 5 | `test_real_run_matches.py` | ❌ pending | pytest `benchmark` marker; runs both, asserts cell-by-cell Δ ≤ 1e-3 |

### Acceptance

One case (Bovee §5.1 Trapezoidal Channel) at Δ ≤ 1e-3 closes U3.
Additional cases (Compound Channel §5.2, Natural Section §5.3, etc.)
are nice-to-have, not required.

## Strategy — why containerise PHABSIM

Mirrors [ADR-0002](../../docs/decisions/0002-schism-integration-strategy.md)
(SCHISM v5.11.0 LTS pinned to `ghcr.io/bnumsn/schism:5.11.0`):

1. PHABSIM is Fortran 77 with NCAR-era build conventions; building it
   on every CI runner is fragile. Pin one build, distribute as an OCI
   image, depend on the digest.
2. OpenLimno doesn't import PHABSIM — it shells out via `subprocess`,
   reads the binary's output files, and compares against `Case.run`
   on the same input. Same isolation pattern as the SCHISM adapter.
3. Container builds run on tagged ships (`benchmark` marker, not
   default CI). PRs don't pay the container-build cost.

## USFWS PHABSIM source — license + acquisition

- USFWS PHABSIM (a.k.a. PHABSIM for Windows / PHABSIM Suite) is
  **public-domain U.S. federal government work** under 17 USC § 105
  ("Copyright protection under this title is not available for any
  work of the United States Government"). Redistribution should be
  legally permissible.
- BUT: actual binary redistribution-in-container terms may have
  caveats from the data tables (CRITERIA library, HSI curves) packaged
  alongside. **Verify before publishing the OCI image** at
  `ghcr.io/openlimno/phabsim:1986` (USFWS release year tag).
- Source archive URL: https://www.usgs.gov/centers/fort-collins-science-center/science/instream-flow-incremental-methodology-phabsim
- Fortran source is in `IFG4/`, `HABTAE/`, `HABEF/` subdirs of the
  IFIM software suite.

## Input deck capture — Bovee 1997 cookbook §5.1

Section §5.1 is "Trapezoidal Channel — single cross-section". The
hand-computed expected WUA values are tabulated in the cookbook;
they're the same reference values our existing closed-form bench
uses. The difference: this track captures the **PHABSIM input deck
itself** (IFG4 format) so the Fortran binary can be run on it.

The IFG4 input format (one of:
[`HABTAV`, `HABTAE`, `IFG4`, `MANSQ`, `WSP`, `STGQ`]) is:

```
TITLE   Bovee 1997 cookbook 5.1 - Trapezoidal Channel
XSEC    1   <description>
NCOL    11
STA     0.00  0.50  1.00  1.50  2.00  2.50  3.00  3.50  4.00  4.50  5.00
ELE     1.50  1.00  0.50  0.10  0.00  0.00  0.10  0.50  1.00  1.50  2.00
ROUGH   0.030 ...
... (HSI curve tables, target Q values follow)
```

The exact deck layout depends on which IFIM module (HABTAE vs IFG4 vs
MANSQ) we drive. Most likely we want **IFG4 → HABTAE** (hydraulics
+ habitat in one pipeline). To be finalised when sub-deliverable #3
is written.

## How to run (when complete)

```bash
# Build the container (one-time)
docker build -t openlimno/phabsim:scaffold benchmarks/phabsim_real/

# Run the benchmark (after sub-deliverables #3..#5 land)
pixi run -- pytest benchmarks/phabsim_real -v -m benchmark
```

## See also

- [ADR-0012](../../docs/decisions/0012-phabsim-real-fortran-validation.md)
  — full decision context
- [ADR-0002](../../docs/decisions/0002-schism-integration-strategy.md)
  — the SCHISM containerisation pattern we mirror
- `benchmarks/phabsim_bovee1997/` — the existing closed-form harness;
  this directory complements (does not replace) that work
