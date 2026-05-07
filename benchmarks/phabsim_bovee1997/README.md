# Bovee 1997 PHABSIM standard regression

> SPEC §7 verification suite. Required to pass on every PR.

## Goal

Build a **closed-form** PHABSIM-style case where the analytic / hand-computed
WUA values are known, and assert OpenLimno reproduces them within 1e-3.

We can't run the original PHABSIM Fortran here, but the algorithm is fully
specified in Bovee 1986 / 1997 and Stalnaker 1995; the test below replicates
those equations independently and asserts equivalence.

## Test case

A 6-section uniform prismatic reach. Each cross-section is identical
(rectangular, b=10 m, n=0.030, S=0.001) so analytic Manning normal depth and
WUA are computable.

For a given Q:
- `h = (n Q / (b S^(1/2)))^(3/5)` (wide-rectangular Manning)
- `u = Q / (b h)`
- HSI evaluated at (h, u) per Bovee 1978 spawning curves
- WUA (cell, geometric mean composite) summed over all sections

Hand-computed WUA at four target Q values is asserted within ±1e-3.

## Sections

```
station    bed elev (m)
0          1.000
100        0.900
200        0.800
300        0.700
400        0.600
500        0.500
```

Slope = 0.001 (1 m drop over 1 km), uniform along reach.

## HSI used

Stylised Bovee 1978 steelhead spawning depth-velocity curves (simplified for
clean analytic comparison). See `expected_wua.json` for hand-computed WUA at
four target Q.

## Run

```bash
pixi run -- pytest benchmarks/phabsim_bovee1997 -v
```
