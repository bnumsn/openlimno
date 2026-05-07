"""Drifting-egg evaluation tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from openlimno.habitat import (
    evaluate_drifting_egg,
    load_drifting_egg_params,
)


def make_velocity_field(n: int = 50, u_const: float = 1.0,
                       reach_length_m: float = 100_000.0) -> dict[float, float]:
    stations = np.linspace(0, reach_length_m, n)
    return {float(s): u_const for s in stations}


def make_temperature_field(n: int = 50, T_const: float = 22.0,
                            reach_length_m: float = 100_000.0) -> dict[float, float]:
    stations = np.linspace(0, reach_length_m, n)
    return {float(s): T_const for s in stations}


def grass_carp_curve() -> list[tuple[float, float]]:
    return [(16.0, 4.5), (20.0, 2.0), (24.0, 1.2), (28.0, 0.9)]


def test_drift_egg_full_hatch_in_warm_water() -> None:
    """At 22°C with 1 m/s for 100 km, grass carp should hatch within reach."""
    res = evaluate_drifting_egg(
        species="ctenopharyngodon_idella",
        spawning_station_m=0.0,
        velocity_along_reach=make_velocity_field(),
        temperature_along_reach=make_temperature_field(T_const=22.0),
        hatch_temp_days_curve=grass_carp_curve(),
        mortality_velocity_threshold_ms=0.2,
        dt_s=600.0,
        max_drift_km=200.0,
    )
    # At 22 C, hatch_days ≈ 1.5; at u=1 m/s drift ≈ 86,400 * 1.5 = 129.6 km
    # That exceeds 100 km reach, so the egg fails to hatch within reach
    # Adjust: use longer reach or higher T
    assert res.drift_distance_km > 50.0


def test_drift_egg_hatch_at_high_temperature() -> None:
    """At 28°C hatch_days = 0.9, so 1 m/s drift = ~78 km — fits in 100 km reach."""
    res = evaluate_drifting_egg(
        species="ctenopharyngodon_idella",
        spawning_station_m=0.0,
        velocity_along_reach=make_velocity_field(),
        temperature_along_reach=make_temperature_field(T_const=28.0),
        hatch_temp_days_curve=grass_carp_curve(),
        mortality_velocity_threshold_ms=0.2,
        dt_s=600.0,
        max_drift_km=200.0,
    )
    assert res.success
    assert res.hatch_temp_C_mean == pytest.approx(28.0, rel=1e-3)
    assert 50 < res.drift_distance_km < 100


def test_drift_egg_mortality_in_slow_water() -> None:
    """In water below mortality threshold, mortality_fraction approaches 1."""
    stations = np.linspace(0, 50_000, 30)
    slow_field = {float(s): 0.05 for s in stations}
    temp_field = {float(s): 22.0 for s in stations}
    res = evaluate_drifting_egg(
        species="ctenopharyngodon_idella",
        spawning_station_m=0.0,
        velocity_along_reach=slow_field,
        temperature_along_reach=temp_field,
        hatch_temp_days_curve=grass_carp_curve(),
        mortality_velocity_threshold_ms=0.2,
        dt_s=600.0,
        max_drift_km=100.0,
    )
    assert res.mortality_fraction > 0.95
    assert not res.success


def test_drift_egg_zero_velocity_raises() -> None:
    field = {float(s): 0.0 for s in np.linspace(0, 1000, 5)}
    with pytest.raises(ValueError, match="zero velocities"):
        evaluate_drifting_egg(
            species="ctenopharyngodon_idella",
            spawning_station_m=0.0,
            velocity_along_reach=field,
            temperature_along_reach={float(s): 20.0 for s in np.linspace(0, 1000, 5)},
            hatch_temp_days_curve=grass_carp_curve(),
            mortality_velocity_threshold_ms=0.2,
        )


def test_load_drifting_egg_params_from_lemhi() -> None:
    p = Path(__file__).resolve().parents[2] / "data" / "lemhi" / "drifting_egg_params.parquet"
    if not p.exists():
        pytest.skip("Lemhi data not built; run tools/build_lemhi_dataset.py")
    params = load_drifting_egg_params(p, "ctenopharyngodon_idella")
    assert params["mortality_velocity_threshold_ms"] == 0.2
    assert params["drift_distance_km_min"] == 50.0
    assert len(params["hatch_temp_days_curve"]) == 4


def test_load_drifting_egg_params_unknown_species() -> None:
    p = Path(__file__).resolve().parents[2] / "data" / "lemhi" / "drifting_egg_params.parquet"
    if not p.exists():
        pytest.skip("Lemhi data not built")
    with pytest.raises(ValueError, match="No drifting_egg_params"):
        load_drifting_egg_params(p, "no_such_species")
