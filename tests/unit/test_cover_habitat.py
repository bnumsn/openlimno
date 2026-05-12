"""v1.3.0 LULC riparian cover × WUA tests.

Hand-roll a tiny WorldCover raster + a polyline / polygon mask, run
through cover_si_from_* — pin the class→SI mapping, the buffer
geometry, and the histogram aggregation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


def _write_lulc(path: Path, arr: np.ndarray, lon0=100.0, lat0=38.0, px_deg=5e-5):
    """Tiny EPSG:4326 GeoTIFF with class codes."""
    h, w = arr.shape
    transform = from_origin(lon0, lat0, px_deg, px_deg)
    with rasterio.open(
        path, "w", driver="GTiff", height=h, width=w, count=1,
        dtype="uint8", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(arr, 1)


def test_default_riparian_cover_si_covers_all_worldcover_codes():
    """Every one of the 11 WorldCover classes must have a mapped SI
    so a real fetch never lands a no-mapping pixel that drops out
    silently."""
    from openlimno.habitat import DEFAULT_RIPARIAN_COVER_SI
    from openlimno.preprocess.fetch import WORLDCOVER_CLASSES
    assert set(DEFAULT_RIPARIAN_COVER_SI) == set(WORLDCOVER_CLASSES)
    # And every SI must be in [0, 1]
    for code, si in DEFAULT_RIPARIAN_COVER_SI.items():
        assert 0.0 <= si <= 1.0, f"class {code} has SI={si}"


def test_default_cover_si_priors_match_habitat_literature():
    """Sanity: tree cover ≥ shrubland ≥ grassland ≥ cropland ≥ built-up.
    Wetland sits between tree and grassland."""
    from openlimno.habitat import DEFAULT_RIPARIAN_COVER_SI as t
    assert t[10] > t[20] > t[30] > t[40] > t[50]
    assert t[10] >= t[90] >= t[30]


def test_cover_si_from_lulc_raster_aggregates_inside_polygon(tmp_path):
    from openlimno.habitat import cover_si_from_lulc_raster
    from shapely.geometry import box
    # 10×10 raster: top half grassland (30, SI=0.4), bottom half cropland (40, SI=0.2)
    arr = np.zeros((10, 10), dtype=np.uint8)
    arr[:5, :] = 30
    arr[5:, :] = 40
    tif = tmp_path / "lulc.tif"
    _write_lulc(tif, arr)
    # Cover the whole raster: lon 100..100+10*5e-5=100.0005, lat 37.9995..38.0
    full = box(100.0, 37.9995, 100.0005, 38.0)
    si, hist = cover_si_from_lulc_raster(tif, full)
    # 50/50 mix → SI = 0.5 × 0.4 + 0.5 × 0.2 = 0.3
    assert si == pytest.approx(0.3)
    assert hist == {30: 50, 40: 50}


def test_cover_si_from_lulc_raster_respects_custom_table(tmp_path):
    from openlimno.habitat import cover_si_from_lulc_raster
    from shapely.geometry import box
    arr = np.full((4, 4), 30, dtype=np.uint8)  # all grassland
    tif = tmp_path / "lulc.tif"
    _write_lulc(tif, arr)
    full = box(100.0, 37.9998, 100.0002, 38.0)
    # Custom table puts grassland at SI=1.0 (e.g., for a grazing-
    # adapted fish species)
    si, _ = cover_si_from_lulc_raster(
        tif, full, cover_si_table={30: 1.0},
    )
    assert si == pytest.approx(1.0)


def test_cover_si_from_lulc_raster_fails_on_all_nodata(tmp_path):
    """All-zero raster + table that doesn't include 0 → loud error,
    not silent NaN."""
    from openlimno.habitat import cover_si_from_lulc_raster
    from shapely.geometry import box
    arr = np.zeros((4, 4), dtype=np.uint8)  # all no-data
    tif = tmp_path / "lulc.tif"
    _write_lulc(tif, arr)
    full = box(100.0, 37.9998, 100.0002, 38.0)
    with pytest.raises(RuntimeError, match="No LULC pixels matched"):
        cover_si_from_lulc_raster(tif, full)


def test_riparian_buffer_polyline_size_correct():
    """A 50 m buffer around a polyline at the equator → polygon area
    ≈ length × 2 × 50 m + 2 × π × 25² (end caps). Pin the cos(lat)
    correction so a buffer at 60°N has the right metric width."""
    from openlimno.habitat import riparian_buffer_from_polyline
    # Equator: 1° lon ≈ 111 320 m. 0.001° polyline = ~111 m long.
    coords = [(100.0, 0.0), (100.001, 0.0)]
    buf = riparian_buffer_from_polyline(coords, buffer_m=50.0)
    # In metric coords, the rectangular sleeve area would be
    # L × 2*W = 111.32 m × 100 m = 11_132 m². With round caps:
    # + π × 50² ≈ 7854 m². Total ≈ 18 986 m².
    # But here we have lat/lon area; convert via 1 deg² ≈
    # (111_320)² × cos(0)² m² at the equator.
    DEG2_TO_M2 = 111_320 ** 2  # at the equator
    area_m2 = buf.area * DEG2_TO_M2
    assert 16_000 < area_m2 < 22_000, f"buffer area {area_m2} m²"


def test_riparian_buffer_rejects_invalid_inputs():
    from openlimno.habitat import riparian_buffer_from_polyline
    with pytest.raises(ValueError, match="≥ 2 vertices"):
        riparian_buffer_from_polyline([(100.0, 38.0)])
    with pytest.raises(ValueError, match="buffer_m"):
        riparian_buffer_from_polyline([(100.0, 38.0), (100.1, 38.0)], buffer_m=0)


def test_cover_si_from_polyline_aggregates_along_river(tmp_path):
    """End-to-end riparian path: a polyline through a raster split
    50/50 between tree cover (10, SI=1.0) and built-up (50, SI=0.0)
    perpendicular to the river. The 50-m buffer should cross both
    LULC zones → mean SI ≈ 0.5.
    """
    from openlimno.habitat import cover_si_from_polyline
    # 100×100 px raster at 5e-5 deg/px ≈ 5.5 m/px at the equator.
    # Top half (rows 0..49) = tree cover; bottom half = built-up.
    arr = np.zeros((100, 100), dtype=np.uint8)
    arr[:50, :] = 10
    arr[50:, :] = 50
    tif = tmp_path / "lulc.tif"
    _write_lulc(tif, arr, lon0=100.0, lat0=38.0, px_deg=5e-5)
    # Polyline runs E-W along the centre row (between rows 49-50)
    # That puts the centerline at the LULC boundary; a 50-m buffer
    # extends ~9 rows up and down, so it crosses both classes about
    # evenly.
    lat_mid = 38.0 - 50 * 5e-5  # row 50 latitude
    coords = [(100.001, lat_mid), (100.004, lat_mid)]
    si, hist = cover_si_from_polyline(tif, coords, buffer_m=50.0)
    # Both classes contribute
    assert 10 in hist and 50 in hist
    # Mean SI should be near 0.5 (allow generous tolerance for the
    # geometry / cos-lat sampling)
    assert 0.35 < si < 0.65, f"si={si}, hist={hist}"


def test_watershed_cover_si_runs_against_geojson(tmp_path):
    """End-to-end watershed path. Same raster, but mask via a
    GeoJSON polygon file (the shape ``write_watershed_geojson``
    produces)."""
    from openlimno.habitat import watershed_cover_si
    arr = np.full((10, 10), 10, dtype=np.uint8)  # all tree
    tif = tmp_path / "lulc.tif"
    _write_lulc(tif, arr)
    geojson = {
        "type": "Feature",
        "properties": {"area_km2": 0.1},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [100.0, 38.0 - 10 * 5e-5],
                [100.0 + 10 * 5e-5, 38.0 - 10 * 5e-5],
                [100.0 + 10 * 5e-5, 38.0],
                [100.0, 38.0],
                [100.0, 38.0 - 10 * 5e-5],
            ]],
        },
    }
    gp = tmp_path / "ws.geojson"
    gp.write_text(json.dumps(geojson))
    si, hist = watershed_cover_si(tif, gp)
    # All-tree → SI = 1.0 (DEFAULT_RIPARIAN_COVER_SI[10] = 1.0)
    assert si == pytest.approx(1.0)
    assert hist == {10: 100}


def test_cover_si_summary_orders_by_pixel_count():
    from openlimno.habitat import cover_si_summary
    hist = {10: 50, 30: 100, 40: 25}
    df = cover_si_summary(hist)
    assert list(df["class_code"].values) == [30, 10, 40]
    assert (df["fraction"].sum()) == pytest.approx(1.0)
    # cover_si column comes from the default mapping
    assert df.set_index("class_code").loc[10, "cover_si"] == 1.0
    assert df.set_index("class_code").loc[30, "cover_si"] == 0.4
    assert df.set_index("class_code").loc[40, "cover_si"] == 0.2


def test_cover_si_summary_handles_empty_hist():
    from openlimno.habitat import cover_si_summary
    df = cover_si_summary({})
    assert list(df.columns) == [
        "class_code", "pixel_count", "fraction", "cover_si",
    ]
    assert len(df) == 0
