"""GeoTIFF DEM reader. SPEC §4.0.1 M1 必交付.

Returns a NumPy array + affine transform + CRS so downstream code can
sample bed elevations along cross-section lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class DEM:
    """Digital elevation model raster + georeferencing."""

    elevation: np.ndarray  # (rows, cols), m
    transform: tuple[float, float, float, float, float, float]
    """Affine: (a, b, c, d, e, f) with x = a*col + b*row + c, y = d*col + e*row + f"""
    crs: str  # EPSG string e.g. "EPSG:32612"
    nodata: float | None = None
    bounds: tuple[float, float, float, float] | None = None
    """(min_x, min_y, max_x, max_y) in CRS units"""

    @property
    def shape(self) -> tuple[int, int]:
        return self.elevation.shape  # type: ignore[return-value]

    def sample(self, x: float, y: float) -> float:
        """Sample elevation at a single (x, y) world coordinate.

        Uses nearest-pixel sampling (M1). Bilinear/bicubic land in M2.
        """
        a, b, c, d, e, f = self.transform
        # Inverse affine: solve [col, row] from [x, y]
        # x = a*col + b*row + c, y = d*col + e*row + f
        det = a * e - b * d
        if det == 0:
            raise ValueError("Singular DEM transform")
        col = ((x - c) * e - (y - f) * b) / det
        row = ((y - f) * a - (x - c) * d) / det
        ic, ir = int(round(col)), int(round(row))
        if not (0 <= ir < self.elevation.shape[0] and 0 <= ic < self.elevation.shape[1]):
            return float("nan")
        v = float(self.elevation[ir, ic])
        if self.nodata is not None and v == self.nodata:
            return float("nan")
        return v

    def sample_along_line(
        self, x0: float, y0: float, x1: float, y1: float, n: int = 50
    ) -> np.ndarray:
        """Sample DEM along a line from (x0, y0) to (x1, y1)."""
        xs = np.linspace(x0, x1, n)
        ys = np.linspace(y0, y1, n)
        return np.array([self.sample(float(x), float(y)) for x, y in zip(xs, ys, strict=False)])


def read_dem(path: str | Path) -> DEM:
    """Read a GeoTIFF DEM into a DEM object.

    Tries rasterio first; if unavailable, falls back to GDAL via osgeo. If
    neither is installed, raises ImportError with install hint.
    """
    path = Path(path)
    try:
        import rasterio
        with rasterio.open(path) as ds:
            elev = ds.read(1).astype(float)
            transform = ds.transform
            t = (transform.a, transform.b, transform.c,
                 transform.d, transform.e, transform.f)
            crs = ds.crs.to_string() if ds.crs else "EPSG:4326"
            nodata = ds.nodata if ds.nodata is not None else None
            bounds = (ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top)
            return DEM(
                elevation=elev, transform=t, crs=crs,
                nodata=nodata, bounds=bounds,
            )
    except ImportError:
        pass

    try:
        from osgeo import gdal
        ds = gdal.Open(str(path))
        if ds is None:
            raise FileNotFoundError(path)
        elev = ds.GetRasterBand(1).ReadAsArray().astype(float)
        gt = ds.GetGeoTransform()  # (c, a, b, f, d, e) in GDAL convention
        # Convert to our (a, b, c, d, e, f) format
        c, a, b, f, d, e = gt
        nodata = ds.GetRasterBand(1).GetNoDataValue()
        srs = ds.GetSpatialRef()
        crs = srs.GetAuthorityCode(None) if srs else "4326"
        crs_str = f"EPSG:{crs}" if crs else "EPSG:4326"
        rows, cols = elev.shape
        bounds = (
            c, f + e * rows,
            c + a * cols, f,
        )
        return DEM(
            elevation=elev, transform=(a, b, c, d, e, f),
            crs=crs_str, nodata=nodata, bounds=bounds,
        )
    except ImportError:
        raise ImportError(
            "Reading GeoTIFF requires either `rasterio` or `gdal`. "
            "Install via `pixi install` (rasterio is in default deps)."
        ) from None


__all__ = ["DEM", "read_dem"]
