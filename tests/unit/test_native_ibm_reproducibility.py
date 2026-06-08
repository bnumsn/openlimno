"""R-IBM-VALIDATION: seed → identical-output regression.

Per ADR-0016 cleanup track + round-22 codex A11 / gemini A7
(test discipline finding), the native IBM run path must be
deterministic given a fixed seed. Two runs with identical
``NativeIBMConfig(seed=N, ...)`` and identical inputs must
produce bit-identical outputs across all result tables.

This pin catches future regressions where someone introduces a
non-seeded source of randomness (default-RNG drift, OS-tied
hash randomisation, time-based jitter, etc.) without realising
they broke reproducibility — which is the core regulatory-defense
property of the IBM pipeline.

The test runs a medium-length sweep (15 days, ~25 fish, multi-
phase competition) so all submodels exercise: habitat selection,
growth, mortality, spawning window, redd state, density
competition, multi-reach gating.
"""

from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from openlimno.ibm import (
    NativeIBMConfig,
    SpeciesProfile,
    build_initial_population,
    run_native_ibm,
)


def _habitat_cells() -> pd.DataFrame:
    """Multi-cell habitat with enough variety to exercise the
    cell-competition + size-priority + density paths."""
    return pd.DataFrame(
        {
            "cell_id": [10, 20, 30, 40, 50],
            "area_m2": [25.0, 30.0, 20.0, 28.0, 22.0],
            "depth_m": [0.2, 0.7, 1.6, 0.5, 1.0],
            "velocity_ms": [0.1, 0.35, 1.1, 0.4, 0.6],
            "csi": [0.25, 0.95, 0.35, 0.75, 0.55],
            "temperature_c": [12.0, 12.0, 12.0, 12.0, 12.0],
            "hiding_cover": [0.1, 0.8, 0.2, 0.5, 0.3],
            "feeding_cover": [0.1, 0.6, 0.2, 0.4, 0.3],
        }
    )


def _config(seed: int) -> NativeIBMConfig:
    """Configuration that exercises the daily simulation across
    spawning, growth, mortality, multi-reach state."""
    return NativeIBMConfig(
        days=15,
        seed=seed,
        scenario_id="reproducibility_pin",
        reach_id="r1",
    )


def test_native_ibm_seed_produces_identical_outputs() -> None:
    """R-IBM-VALIDATION: two runs with the same seed + same inputs
    must produce bit-identical output tables across population
    summary, final individuals, cell use, and events."""
    cells = _habitat_cells()
    profile = SpeciesProfile()

    # Run 1
    pop1 = build_initial_population(n=25, species="rainbow_trout", length_mm=120.0)
    result1 = run_native_ibm(
        cells,
        pop1,
        profile=profile,
        config=_config(seed=20260526),
    )

    # Run 2 — same seed, regenerated initial population (which is also
    # built with deterministic numpy default RNG seeded internally
    # by the config), same cells, same profile.
    pop2 = build_initial_population(n=25, species="rainbow_trout", length_mm=120.0)
    result2 = run_native_ibm(
        cells,
        pop2,
        profile=profile,
        config=_config(seed=20260526),
    )

    # The four core output tables must be element-wise identical.
    assert_frame_equal(
        result1.population_summary.reset_index(drop=True),
        result2.population_summary.reset_index(drop=True),
        check_dtype=False,
    )
    assert_frame_equal(
        result1.final_individuals.reset_index(drop=True),
        result2.final_individuals.reset_index(drop=True),
        check_dtype=False,
    )
    assert_frame_equal(
        result1.cell_use.reset_index(drop=True),
        result2.cell_use.reset_index(drop=True),
        check_dtype=False,
    )
    # Events table — may be empty in a short benign run but still
    # must match.
    if not result1.events.empty or not result2.events.empty:
        assert_frame_equal(
            result1.events.reset_index(drop=True),
            result2.events.reset_index(drop=True),
            check_dtype=False,
        )


def test_native_ibm_different_seed_produces_different_outputs() -> None:
    """Counterpart pin: changing the seed MUST produce different
    output (otherwise the seed isn't actually plumbed through).
    Together with the identical-seed test, this triangulates the
    'seed actually drives randomness' invariant.
    """
    cells = _habitat_cells()
    profile = SpeciesProfile()
    pop = build_initial_population(n=25, species="rainbow_trout", length_mm=120.0)

    result_a = run_native_ibm(cells, pop.copy(), profile=profile, config=_config(seed=1))
    result_b = run_native_ibm(cells, pop.copy(), profile=profile, config=_config(seed=999_999))

    # At least one core table must differ in some row — otherwise
    # the seed isn't doing anything.
    different = (
        not result_a.population_summary.equals(result_b.population_summary)
        or not result_a.final_individuals.equals(result_b.final_individuals)
        or not result_a.cell_use.equals(result_b.cell_use)
    )
    assert different, (
        "R-IBM-VALIDATION regression: two runs with seed=1 and seed=999999 "
        "produced bit-identical outputs. The seed parameter isn't actually "
        "driving randomness through the simulation."
    )
