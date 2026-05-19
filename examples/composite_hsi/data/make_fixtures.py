"""v3.1.0 R11-18 — regenerate the composite_hsi raster fixtures.

The two GeoTIFFs (thermal_C.tif, cover_lulc.tif) are 12×12 EPSG:4326
synthetic rasters used by the composite_hsi example. They're checked
into the repo so the example runs offline (<2s) without network
fetches. This script lets a maintainer rebuild them if GDAL changes
nodata defaults, Windows EOL corrupts a checkout, or fixture
parameters need tweaking.

Usage::

    PYTHONPATH=src python examples/composite_hsi/data/make_fixtures.py

Idempotent: produces byte-stable output. CI can diff the generated
files against the committed ones to detect drift.

Why not auto-run in CI: the fixtures rarely change and the rasterio
dependency stack is heavy. Manual regen + commit is the right
cadence.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

HERE = Path(__file__).resolve().parent


def make_thermal_raster() -> Path:
    """Synthetic 12×12 thermal raster.

    East-west gradient 8..14 °C in EPSG:4326. Anchored at the Heihe
    basin centroid (38.20 °N, 100.20 °E) used by the example case.
    The values are float32 so the inline thermal SI path exercises
    its CRS-reproject + nodata logic against a realistic raster.
    """
    cols, rows = 12, 12
    # East-west gradient 8..14 °C
    grid = np.tile(
        np.linspace(8.0, 14.0, cols, dtype=np.float32),
        (rows, 1),
    )
    transform = from_origin(100.0, 38.25, 0.005, 0.005)
    out = HERE / "thermal_C.tif"
    with rasterio.open(
        out, "w",
        driver="GTiff",
        height=rows, width=cols,
        count=1, dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as ds:
        ds.write(grid, 1)
    return out


def make_cover_lulc_raster() -> Path:
    """Synthetic 12×12 LULC raster.

    WorldCover-style class mix:
        10 = tree cover,  20 = shrubland,
        30 = grassland,   60 = bare / sparse.
    Mosaic'd in a stripe pattern to exercise the per-section sampler
    against multiple classes per case run.
    """
    cols, rows = 12, 12
    # Stripe pattern: 4 rows tree, 3 rows shrub, 3 rows grass, 2 rows bare.
    grid = np.zeros((rows, cols), dtype=np.uint8)
    grid[0:4, :] = 10
    grid[4:7, :] = 20
    grid[7:10, :] = 30
    grid[10:12, :] = 60
    transform = from_origin(100.0, 38.25, 0.005, 0.005)
    out = HERE / "cover_lulc.tif"
    with rasterio.open(
        out, "w",
        driver="GTiff",
        height=rows, width=cols,
        count=1, dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
        nodata=255,
    ) as ds:
        ds.write(grid, 1)
    return out


def main() -> None:
    print(f"Regenerating composite_hsi raster fixtures under {HERE}/…")
    thermal = make_thermal_raster()
    print(f"  ✓ {thermal.name}  (12×12 float32, 8..14 °C east-west)")
    cover = make_cover_lulc_raster()
    print(f"  ✓ {cover.name}  (12×12 uint8, tree/shrub/grass/bare stripes)")
    print("\nDiff against committed fixtures to detect drift:")
    print(f"  git diff --stat {HERE}/")


if __name__ == "__main__":
    main()
