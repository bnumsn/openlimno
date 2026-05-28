# Aquarium logs — calibration datasets

Bundled measurement logs for the `openlimno.fishtank` Hour-3 calibration
lesson. No network dependency: these ship in-repo.

## Files

| file | nature | provenance |
|---|---|---|
| `tank_A_fishless.csv` | **synthetic** | Generated from the Tier-1 model with known "true" parameters (`mu_AOB=0.62`, `mu_NOB=0.35`, dose 2.0 mg-N/L/day), then degraded with realistic hobby test-kit noise (~10% + 0.15 floor) and 0.25 mg/L resolution, sampled every 2–3 days. Seed 20260528. |

## Why synthetic (teaching honesty)

`tank_A_fishless.csv` is synthetic **on purpose**: the student calibrates
the model against it and can check whether the fit *recovers the known
truth* (`mu_AOB≈0.62`, `mu_NOB≈0.35`). That closes the pedagogical loop —
you cannot grade "did the calibration work" against a real log whose true
parameters are unknown. The noise + resolution + sparse sampling make it
behave like a real hobby log.

A genuinely real, digitised hobby log can be added later (cite the source
blog / forum thread and its license) for a second, harder exercise where
the "truth" is unknown and only the fit quality (RMSE + residual pattern)
can be judged.

## Column schema

`day, TAN, NO2, NO3` — all in mg-N/L. `day` is days since cycle start.
Missing measurements may be left blank (the calibration aligner skips NaN).
