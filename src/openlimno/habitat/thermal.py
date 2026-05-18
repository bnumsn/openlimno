"""Thermal habitat suitability (v1.1.0).

Combines:

* **FishBase species traits** — preferred temperature range
  (``temperature_min_C``, ``temperature_max_C``) — from
  :mod:`openlimno.preprocess.fetch.fishbase`.
* **Daily water temperature** — typically ``T_water_C_stefan``
  produced by the Daymet / Open-Meteo fetchers' Stefan-Preud'homme
  1993 air→water transformation.

into a per-day habitat suitability index :math:`SI \\in [0, 1]`
using a trapezoidal curve:

```
SI = 0                              for T < T_lethal_min
SI = linear 0 → 1                   for T_lethal_min ≤ T < T_opt_min
SI = 1                              for T_opt_min ≤ T ≤ T_opt_max
SI = linear 1 → 0                   for T_opt_max < T ≤ T_lethal_max
SI = 0                              for T > T_lethal_max
```

FishBase reports *preferred* temperature ranges, which we map to
``(T_opt_min, T_opt_max)``. The two lethal limits aren't directly
in FishBase so we default ``T_lethal_min = T_opt_min - 5 °C`` and
``T_lethal_max = T_opt_max + 5 °C`` — a literature-standard
margin for stream salmonids + cyprinids. Callers with site-specific
incipient-upper-lethal data (IULT) can override via the dataclass.

This module **does not depend on hydraulics** — it consumes a
temperature time series directly. The reach-scale WUA computed in
:mod:`openlimno.habitat.wua` is depth/velocity-driven; thermal SI is
a temporal overlay that multiplies into total habitat:

    HSI_total(t, x) = HSI_geom(t, x) × thermal_SI(t)

The scalar time-series path stays independent from hydraulics. The
local spatial bridge, :func:`thermal_si_from_temperature_raster` /
:func:`thermal_si_per_section`, consumes an already-built T(x) raster
and emits per-section thermal SI values that can feed v2.1.0's
:func:`openlimno.habitat.composite.apply_overlay_per_cell`. Remote
PRISM/NLDAS/ERA5-style T(x) fetchers remain on the research route.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from shapely.geometry import mapping

# Default lethal margin around the FishBase preferred range, in °C.
# Conservative for the salmonid / cyprinid species in OpenLimno's
# default scope; override per-species when sub-lethal CTmax data is
# available (Beitinger, Bennett & McCauley 2000 review for many
# warmwater species; Hokanson et al. 1977 for trout/salmon).
DEFAULT_LETHAL_MARGIN_C = 5.0


@dataclass(frozen=True)
class ThermalRange:
    """Trapezoidal-curve parameters for thermal HSI.

    Attributes:
        T_opt_min, T_opt_max: preferred range (SI = 1.0).
        T_lethal_min, T_lethal_max: lethal limits (SI = 0.0). The
            ramp on each side is linear between lethal and opt.
        source: free-text provenance, typically ``"FishBase ..."``.
    """

    T_opt_min: float
    T_opt_max: float
    T_lethal_min: float
    T_lethal_max: float
    source: str = ""

    def __post_init__(self) -> None:
        if not (
            self.T_lethal_min < self.T_opt_min
            <= self.T_opt_max < self.T_lethal_max
        ):
            raise ValueError(
                f"ThermalRange parameters must satisfy "
                f"T_lethal_min < T_opt_min ≤ T_opt_max < T_lethal_max; "
                f"got ({self.T_lethal_min}, {self.T_opt_min}, "
                f"{self.T_opt_max}, {self.T_lethal_max})"
            )

    @classmethod
    def from_fishbase(
        cls, T_opt_min: float, T_opt_max: float, *,
        lethal_margin_C: float = DEFAULT_LETHAL_MARGIN_C,
        source: str = "FishBase (default lethal margin)",
    ) -> ThermalRange:
        """Build a :class:`ThermalRange` from FishBase preferred-range
        values, defaulting the lethal limits to ``opt ± margin``.
        """
        if lethal_margin_C <= 0:
            raise ValueError(
                f"lethal_margin_C={lethal_margin_C} must be positive"
            )
        return cls(
            T_opt_min=T_opt_min,
            T_opt_max=T_opt_max,
            T_lethal_min=T_opt_min - lethal_margin_C,
            T_lethal_max=T_opt_max + lethal_margin_C,
            source=source,
        )


def thermal_hsi(T_C: float | np.ndarray, tr: ThermalRange) -> float | np.ndarray:
    """Evaluate the trapezoidal thermal HSI at one or more temperatures.

    Args:
        T_C: temperature in °C; scalar or numpy array.
        tr: :class:`ThermalRange` parameters.

    Returns:
        SI ∈ [0, 1] of the same shape as ``T_C``.
    """
    T = np.asarray(T_C, dtype=float)
    si = np.zeros_like(T, dtype=float)

    # Ramp up: T_lethal_min ≤ T < T_opt_min
    left_mask = (tr.T_lethal_min <= T) & (tr.T_opt_min > T)
    left_denom = tr.T_opt_min - tr.T_lethal_min
    si = np.where(
        left_mask,
        (T - tr.T_lethal_min) / left_denom if left_denom > 0 else 0.0,
        si,
    )

    # Optimum plateau
    opt_mask = (tr.T_opt_min <= T) & (tr.T_opt_max >= T)
    si = np.where(opt_mask, 1.0, si)

    # Ramp down: T_opt_max < T ≤ T_lethal_max
    right_mask = (tr.T_opt_max < T) & (tr.T_lethal_max >= T)
    right_denom = tr.T_lethal_max - tr.T_opt_max
    si = np.where(
        right_mask,
        (tr.T_lethal_max - T) / right_denom if right_denom > 0 else 0.0,
        si,
    )

    # Clip defensively in case of numerical noise
    si = np.clip(si, 0.0, 1.0)
    if np.isscalar(T_C):
        return float(si)
    return si


def thermal_suitability_series(
    temperature_series: pd.Series | pd.DataFrame,
    tr: ThermalRange,
    *,
    temperature_column: str = "T_water_C_stefan",
    time_column: str = "time",
) -> pd.DataFrame:
    """Compute a daily thermal-SI series.

    Args:
        temperature_series: either a :class:`pd.Series` indexed by date
            holding °C values, OR a :class:`pd.DataFrame` with a
            ``temperature_column`` (default ``T_water_C_stefan`` to
            match the Daymet / Open-Meteo fetchers' default output).
        tr: :class:`ThermalRange` parameters.

    Returns:
        DataFrame with columns ``[time, T_water_C, thermal_SI]``.
    """
    if isinstance(temperature_series, pd.Series):
        df = temperature_series.to_frame(name="T_water_C").reset_index()
        df = df.rename(columns={df.columns[0]: time_column})
    else:
        if temperature_column not in temperature_series.columns:
            raise KeyError(
                f"temperature_column={temperature_column!r} not in "
                f"DataFrame columns {list(temperature_series.columns)}"
            )
        if time_column not in temperature_series.columns:
            raise KeyError(
                f"time_column={time_column!r} not in DataFrame "
                f"columns {list(temperature_series.columns)}"
            )
        df = pd.DataFrame({
            time_column: temperature_series[time_column].values,
            "T_water_C": temperature_series[temperature_column].values,
        })

    df["thermal_SI"] = thermal_hsi(df["T_water_C"].values, tr)
    return df[[time_column, "T_water_C", "thermal_SI"]].rename(
        columns={time_column: "time"},
    )


def thermal_metrics(thermal_df: pd.DataFrame) -> dict[str, float]:
    """Summarise a thermal-SI series into scalar metrics for
    provenance / reporting.

    Returns:
        ``{
            'mean_SI': float,                 # 0..1
            'days_optimal': int,              # SI == 1
            'days_lethal': int,               # SI == 0
            'days_total': int,
            'optimal_fraction': float,        # days_optimal / total
        }``
    """
    si = thermal_df["thermal_SI"].astype(float)
    n = len(si)
    if n == 0:
        return {
            "mean_SI": float("nan"),
            "days_optimal": 0, "days_lethal": 0, "days_total": 0,
            "optimal_fraction": float("nan"),
        }
    days_optimal = int((si >= 1.0 - 1e-9).sum())
    days_lethal = int((si <= 1e-9).sum())
    return {
        "mean_SI": float(si.mean()),
        "days_optimal": days_optimal,
        "days_lethal": days_lethal,
        "days_total": n,
        "optimal_fraction": days_optimal / n,
    }


def thermal_si_from_temperature_raster(
    temperature_raster: Path | str,
    geometry: object,
    tr: ThermalRange,
    *,
    band: int = 1,
) -> tuple[float, dict[str, float]]:
    """Compute pixel-weighted thermal SI inside a geometry.

    This is the local raster bridge for the 3.x spatial T(x) route: it
    consumes an already-built water-temperature raster in degrees Celsius
    and evaluates :func:`thermal_hsi` per pixel. Remote PRISM/NLDAS/ERA5
    fetchers can produce the raster later without changing this API.

    Args:
        temperature_raster: single-band or multi-band GeoTIFF with water
            temperature values in degrees Celsius.
        geometry: shapely geometry in the raster CRS.
        tr: thermal suitability curve.
        band: 1-based raster band index.

    Returns:
        ``(mean_si, stats)`` where ``mean_si`` is the mean per-pixel
        thermal suitability and ``stats`` carries pixel count and
        temperature/SI ranges for provenance.
    """
    with rasterio.open(temperature_raster) as src:
        nodata = src.nodata
        # v2.5.1 (R8-6): use ``filled=False`` so geometry-outside pixels
        # return masked, not silently filled with the nodata value
        # (which defaults to 0 °C when the source raster declares no
        # nodata — a 0 °C bias on every outside-geometry pixel).
        out, _ = rasterio.mask.mask(
            src,
            [mapping(geometry)],
            crop=True,
            nodata=nodata,
            filled=False,
            indexes=band,
        )

    out_ma = np.ma.asarray(out)
    arr = np.asarray(out_ma.filled(np.nan), dtype=float)
    valid = np.isfinite(arr)
    if np.ma.is_masked(out_ma):
        valid &= ~np.ma.getmaskarray(out_ma)
    if nodata is not None:
        valid &= arr != float(nodata)
    values = arr[valid]
    if values.size == 0:
        raise RuntimeError(
            "No valid temperature pixels matched the supplied geometry; "
            "check raster CRS, nodata, and geometry overlap."
        )

    si = np.asarray(thermal_hsi(values, tr), dtype=float)
    stats = {
        "pixel_count": float(values.size),
        "mean_temperature_C": float(values.mean()),
        "min_temperature_C": float(values.min()),
        "max_temperature_C": float(values.max()),
        "min_si": float(si.min()),
        "max_si": float(si.max()),
    }
    return float(si.mean()), stats


def thermal_si_per_section(
    temperature_raster: Path | str,
    section_geometries: Sequence[object],
    tr: ThermalRange,
    *,
    band: int = 1,
) -> np.ndarray:
    """Return one mean thermal SI value per section geometry.

    The output shape matches ``section_geometries`` and is directly
    consumable by ``apply_overlay_per_cell(..., thermal_si_per_cell=...)``.
    """
    return np.array(
        [
            thermal_si_from_temperature_raster(
                temperature_raster,
                geom,
                tr,
                band=band,
            )[0]
            for geom in section_geometries
        ],
        dtype=float,
    )
