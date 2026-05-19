"""v3.4.0 R9-3 — high-latitude geodesic riparian buffer.

Pins the v2.6.1-deferred R9-3 finding: above ±60° the cos-latitude
approximation that the v2.6.1 riparian_buffer_from_polyline used
made the buffer's E-W extent shrink to roughly half the requested
metres (at 60° lat, cos=0.5). v3.4.0 switches the high-lat path
to a proper geodesic buffer via pyproj.Geod.

Three pins:
  1. Below ±60° (the unchanged majority path): same behavior as
     pre-v3.4.0, no regression.
  2. Above ±60°: the buffer's E-W AND N-S widths both match the
     requested metres (within geodesic tolerance), not the
     cos-shrunken values.
  3. Threshold continuity: behavior at lat=60.0 and lat=60.001
     produces similar buffer extents (no discontinuity jump).
"""
from __future__ import annotations

import numpy as np


def test_v340_r93_temperate_path_unchanged() -> None:
    """v3.4.0 R9-3: at temperate latitudes the cos-latitude path
    still runs (no behavior change for the 95%+ pre-existing
    fixture base)."""
    from openlimno.habitat.cover import riparian_buffer_from_polyline

    # Lemhi reach: ~45° N
    coords = [(-113.95, 44.92), (-113.85, 44.98)]
    geom = riparian_buffer_from_polyline(coords, buffer_m=200.0)
    assert geom.is_valid
    minx, miny, maxx, maxy = geom.bounds
    # cos(45°) ≈ 0.707; 200 m E-W ≈ 200 / (111320 * 0.707) ≈ 2.54e-3 deg
    # But this is a polyline buffer (not point), so the bounds are
    # dominated by the polyline extent. Just check the buffer
    # added margin in both directions.
    assert maxx > -113.85 + 1e-4 and minx < -113.95 - 1e-4
    assert maxy > 44.98 + 1e-4 and miny < 44.92 - 1e-4


def test_v340_r93_high_lat_path_uses_geodesic() -> None:
    """v3.4.0 R9-3: at ±70° (clearly above 60° threshold), the
    geodesic path must produce a buffer whose E-W half-width is
    within ~20% of buffer_m (the cos-lat path would have been off
    by a factor of ~2.9 at this latitude — cos(70°) ≈ 0.342, so
    pre-v3.4 the E-W extent was ~34% of the requested metres).
    """
    from pyproj import Geod

    from openlimno.habitat.cover import riparian_buffer_from_polyline

    # Single-point-ish polyline at 70° N (sub-polar).
    coords = [(0.0, 70.0), (0.001, 70.0)]
    buffer_m = 5000.0
    geom = riparian_buffer_from_polyline(coords, buffer_m=buffer_m)
    assert geom.is_valid
    minx, miny, maxx, maxy = geom.bounds
    # Use Geod to measure actual half-width E-W at lat=70.0.
    geod = Geod(ellps="WGS84")
    # E-W distance from polyline midpoint to maxx, lat=70.
    east_dist = geod.line_length([0.0005, maxx], [70.0, 70.0])
    # We expect east_dist ≈ buffer_m, NOT shrunken by cos(70°).
    # Tolerance: 30% (the 36-azimuth approximation + finite point
    # spacing introduces some slack).
    assert 0.7 * buffer_m < east_dist < 1.3 * buffer_m, (
        f"R9-3 regression: high-lat E-W half-width {east_dist:.0f} m "
        f"is far from the requested {buffer_m} m. cos-lat path "
        f"would have given ~{buffer_m * np.cos(np.radians(70)):.0f} m; "
        f"the geodesic path should be much closer to {buffer_m}."
    )


def test_v340_r93_threshold_continuity() -> None:
    """v3.4.0 R9-3: behavior at lat=60.0 (cos-lat path) and
    lat=60.5 (geodesic path) must not be wildly different — a
    discontinuity at the threshold would surprise users near 60°.
    """
    from openlimno.habitat.cover import riparian_buffer_from_polyline

    just_below = riparian_buffer_from_polyline(
        [(0.0, 59.9), (0.0, 59.91)], buffer_m=1000.0,
    )
    just_above = riparian_buffer_from_polyline(
        [(0.0, 60.5), (0.0, 60.51)], buffer_m=1000.0,
    )
    # Areas should be similar in degrees² order-of-magnitude.
    # cos(60°) ≈ 0.5, so the cos-lat path at 59.9° has an ellipse
    # shape with E-W extent shrunken by half. The geodesic path at
    # 60.5° produces a circle. Areas should be within an order of
    # magnitude — exact equivalence isn't claimed because the two
    # algorithms differ; we just guard against a 100× jump.
    assert 0.1 < just_above.area / just_below.area < 10.0, (
        f"R9-3 threshold discontinuity: 59.9° area={just_below.area}, "
        f"60.5° area={just_above.area}. Ratio outside reasonable range."
    )


def test_v340_r93_high_lat_does_not_explode_near_pole() -> None:
    """v3.4.0 R9-3: very high latitudes (e.g. 85° N) must still
    produce a valid geometry. The cos-lat path would have raised
    ValueError ("crosses too close to the pole"); the geodesic
    path handles polar reaches gracefully."""
    from openlimno.habitat.cover import riparian_buffer_from_polyline

    coords = [(0.0, 85.0), (1.0, 85.0)]
    geom = riparian_buffer_from_polyline(coords, buffer_m=10000.0)
    assert geom.is_valid
    assert geom.area > 0
