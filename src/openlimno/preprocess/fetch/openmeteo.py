"""Open-Meteo daily climate fetcher (v0.3.2 P0).

Open-Meteo (https://open-meteo.com/) is a free, no-auth, no-quota
weather/climate REST API. Its archive backend stitches ERA5 / ERA5-Land
reanalysis (Hersbach et al. 2020) into a single global, hourly + daily
endpoint, which gives OpenLimno a Daymet-equivalent surface for
**anywhere on Earth** — Daymet only covers North America.

For OpenLimno's fish-biology models we mostly need:

* **Daily air temperature** (``tmax`` + ``tmin``) — feeds the
  drift-egg ``hatch_temp_days_curve`` lookup, the swim-performance
  temperature dependency, and any thermal-habitat constraint module.
* Optionally **precipitation** for water-balance / sediment-flux
  models.

Air → water temperature transformation matches the Daymet fetcher
(Stefan & Preud'homme 1993, a=5.0, b=0.75) so both climate sources
emit identical DataFrame schemas — a case can swap ``--fetch-climate
daymet:...`` for ``--fetch-climate open-meteo:...`` and downstream
biology modules don't notice. The choice is purely about geographic
coverage (Daymet: N. America 1 km; Open-Meteo: global ≈11 km via
ERA5-Land).

Endpoint:
    https://archive-api.open-meteo.com/v1/archive
Docs:
    https://open-meteo.com/en/docs/historical-weather-api
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd
import requests

from openlimno.preprocess.fetch.cache import CacheEntry, cached_fetch
from openlimno.preprocess.fetch.daymet import (
    STEFAN_AIR_TO_WATER_A,
    STEFAN_AIR_TO_WATER_B,
)

OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# ERA5-Land archive backend coverage. Open-Meteo's archive nominally
# starts 1940-01-01 (ERA5) and lags ~5 days behind real-time. We refuse
# pre-1940 requests locally so the upstream API doesn't silently snap
# the window (mirrors the Daymet guard).
OPENMETEO_FIRST_YEAR = 1940
OPENMETEO_LAST_YEAR_GUARD = 2099  # generous upper bound

OPENMETEO_CITATION = (
    "Open-Meteo Historical Weather API "
    "(https://open-meteo.com/, ERA5 reanalysis backend: "
    "Hersbach et al. 2020, doi:10.1002/qj.3803). "
    "CC-BY 4.0."
)


@dataclass
class OpenMeteoFetchResult:
    """Outcome of an Open-Meteo archive fetch.

    Mirrors :class:`DaymetFetchResult` for the **shared** attributes
    (``.df``, ``.cache``, ``.lat``, ``.lon``, ``.elevation_m``,
    ``.citation``) so downstream code can accept either type. Note
    that Daymet's ``.tile_id`` has no analogue here (Open-Meteo
    doesn't expose a tile / grid identifier), and Open-Meteo adds
    ``.timezone`` + ``.utc_offset_seconds`` which Daymet doesn't.

    Attributes:
        df: DataFrame with columns
            ``[time, tmax_C, tmin_C, T_air_C_mean, T_water_C_stefan]``
            (optionally ``prcp_mm``), indexed 0..N-1. ``time`` is
            ISO ``YYYY-MM-DD`` to match Daymet + OpenLimno Q_*.csv.
        cache: provenance trail entry.
        lat, lon: grid-snapped coordinates returned by the API.
        elevation_m: grid-cell elevation (metres) as reported by
            Open-Meteo; handy sanity check vs the case's bank_elev.
        timezone: timezone identifier (we request ``UTC``).
        utc_offset_seconds: explicit offset reported alongside the
            timezone (kept for provenance auditing).
        citation: APA-style citation string folded into provenance.json.
    """

    df: pd.DataFrame
    cache: CacheEntry
    lat: float = float("nan")
    lon: float = float("nan")
    elevation_m: float = float("nan")
    timezone: str = ""
    utc_offset_seconds: int = 0
    citation: str = ""


def fetch_open_meteo_daily(
    lat: float, lon: float, start_year: int, end_year: int,
    *, include_precip: bool = False,
) -> OpenMeteoFetchResult:
    """Fetch Open-Meteo daily climate for a lat/lon point.

    Args:
        lat: latitude in decimal degrees (-90 to +90; global coverage).
        lon: longitude in decimal degrees (-180 to +180).
        start_year, end_year: integer years. Archive covers
            ${OPENMETEO_FIRST_YEAR}-present; the API lags ~5 days
            behind real-time, so ``end_year = current year`` may yield
            an incomplete final week.
        include_precip: also pull ``precipitation_sum`` (mm/day). Off
            by default to match the Daymet fetcher's default.

    Returns:
        ``OpenMeteoFetchResult`` whose ``df`` is column-compatible with
        :func:`fetch_daymet_daily` — downstream code is agnostic to
        which climate source produced it.
    """
    if start_year > end_year:
        raise ValueError(
            f"start_year ({start_year}) must be ≤ end_year ({end_year})"
        )
    if start_year < OPENMETEO_FIRST_YEAR or end_year > OPENMETEO_LAST_YEAR_GUARD:
        raise ValueError(
            f"Open-Meteo archive coverage is {OPENMETEO_FIRST_YEAR}-present "
            f"(ERA5 backend). Got start_year={start_year}, "
            f"end_year={end_year}. The upstream API silently snaps "
            f"out-of-window requests, which would mislabel your CSV — "
            f"refusing locally."
        )
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"lat={lat} outside [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"lon={lon} outside [-180, 180]")

    daily_vars = ["temperature_2m_max", "temperature_2m_min"]
    if include_precip:
        daily_vars.append("precipitation_sum")
    params = {
        "latitude": f"{lat:.6f}",
        "longitude": f"{lon:.6f}",
        "start_date": f"{start_year}-01-01",
        "end_date": f"{end_year}-12-31",
        "daily": ",".join(daily_vars),
        "timezone": "UTC",
    }

    def _do_fetch() -> bytes:
        resp = requests.get(OPEN_METEO_ARCHIVE, params=params, timeout=120)
        resp.raise_for_status()
        return resp.content

    cache = cached_fetch(
        subdir="openmeteo", url=OPEN_METEO_ARCHIVE, params=params,
        suffix=".json", fetch_fn=_do_fetch,
    )
    payload = json.loads(cache.path.read_text())

    daily = payload.get("daily")
    if not daily or "time" not in daily:
        raise RuntimeError(
            f"Open-Meteo response missing 'daily' block. "
            f"keys={list(payload.keys())!r}"
        )

    times = daily["time"]
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    if not (len(times) == len(tmax) == len(tmin)):
        raise RuntimeError(
            f"Open-Meteo daily arrays length mismatch: "
            f"time={len(times)}, tmax={len(tmax)}, tmin={len(tmin)}"
        )

    df_raw = pd.DataFrame({
        "time": times,
        "tmax_C": pd.to_numeric(tmax, errors="coerce"),
        "tmin_C": pd.to_numeric(tmin, errors="coerce"),
    })
    if include_precip:
        prcp = daily.get("precipitation_sum", [])
        if len(prcp) != len(times):
            raise RuntimeError(
                f"Open-Meteo precipitation_sum length mismatch: "
                f"time={len(times)}, prcp={len(prcp)}"
            )
        df_raw["prcp_mm"] = pd.to_numeric(prcp, errors="coerce")

    df_raw["T_air_C_mean"] = (df_raw["tmax_C"] + df_raw["tmin_C"]) / 2.0
    df_raw["T_water_C_stefan"] = (
        STEFAN_AIR_TO_WATER_A
        + STEFAN_AIR_TO_WATER_B * df_raw["T_air_C_mean"]
    ).clip(lower=0.0)

    cols = ["time", "tmax_C", "tmin_C", "T_air_C_mean", "T_water_C_stefan"]
    if include_precip:
        cols.append("prcp_mm")
    out = df_raw[cols].reset_index(drop=True)

    return OpenMeteoFetchResult(
        df=out, cache=cache,
        lat=float(payload.get("latitude", lat)),
        lon=float(payload.get("longitude", lon)),
        elevation_m=float(payload.get("elevation", float("nan"))),
        timezone=str(payload.get("timezone", "")),
        utc_offset_seconds=int(payload.get("utc_offset_seconds", 0)),
        citation=OPENMETEO_CITATION,
    )
