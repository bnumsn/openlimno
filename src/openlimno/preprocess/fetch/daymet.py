"""Daymet daily surface weather fetcher (v0.3.1 P1).

Daymet (Thornton et al., ORNL DAAC v4) is the standard 1 km daily
gridded surface-weather dataset for North America (1980-present),
free + no-auth, accessible via a simple REST single-pixel API.

For OpenLimno's fish-biology models we mostly need:

* **Daily air temperature** (``tmax`` + ``tmin``) — feeds the
  drift-egg ``hatch_temp_days_curve`` lookup, the swim-performance
  temperature dependency, and any thermal-habitat constraint module
  added later.
* Optionally **precipitation** for water-balance / sediment-flux
  models (not yet in OpenLimno core).

Air → water temperature is NOT 1:1. A reasonable first-order
approximation is the Stefan & Preud'homme (1993) linear model

    T_water ≈ a + b · T_air

with (a, b) ≈ (5.0, 0.75) for unshaded mid-latitude streams. We
output BOTH the raw air temp + a transformed water-temp column
under that assumption, clearly labelled (and the SPEC reference is
in the column metadata) — users with their own model can ignore the
transformed column. Stefan & Preud'homme is cited in
``provenance.json`` for any case that consumes the water-temp column.

API docs:
    https://daymet.ornl.gov/web_services
    https://daymet.ornl.gov/single-pixel/api/data
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO

import pandas as pd
import requests

from openlimno.preprocess.fetch.cache import CacheEntry, cached_fetch

DAYMET_SINGLE_PIXEL = "https://daymet.ornl.gov/single-pixel/api/data"

# Stefan & Preud'homme 1993 air→water linear regression coefficients.
# For unshaded mid-latitude US streams this is the canonical default;
# basin-specific calibration is always preferred.
STEFAN_AIR_TO_WATER_A = 5.0
STEFAN_AIR_TO_WATER_B = 0.75


@dataclass
class DaymetFetchResult:
    """Outcome of a Daymet single-pixel fetch.

    Attributes:
        df: DataFrame with columns
            ``[time, tmax_C, tmin_C, T_air_C_mean, T_water_C_stefan]``
            indexed 0..N-1. ``time`` is YYYY-MM-DD ISO format so it
            slots into OpenLimno's Q_*.csv schema unchanged.
        cache: provenance trail entry.
        lat, lon: snapped pixel center (Daymet 1 km grid).
        tile_id: Daymet Lambert conformal conic tile identifier.
        elevation_m: pixel-mean elevation from the Daymet grid (handy
            sanity check vs the case's bank_elev).
        citation: APA-style citation string from the Daymet header
            (folded into provenance.json by the CLI wrapper).
    """

    df: pd.DataFrame
    cache: CacheEntry
    lat: float = float("nan")
    lon: float = float("nan")
    tile_id: str = ""
    elevation_m: float = float("nan")
    citation: str = ""


def fetch_daymet_daily(
    lat: float, lon: float, start_year: int, end_year: int,
    *, include_precip: bool = False,
) -> DaymetFetchResult:
    """Fetch Daymet daily surface weather for a lat/lon point.

    Args:
        lat: latitude in decimal degrees (-49.5 to +83.5 covers full
            Daymet domain — Continental US + Hawaii + Alaska +
            Puerto Rico).
        lon: longitude in decimal degrees (negative for W).
        start_year, end_year: integer years. Daymet covers 1980–present.
        include_precip: also pull ``prcp`` (precipitation mm/day). Off
            by default since v0.3.1 only uses temperature internally.

    Returns:
        ``DaymetFetchResult`` whose ``df`` slots into Q_*.csv-style
        time-series consumers without further reshaping.
    """
    if start_year > end_year:
        raise ValueError(
            f"start_year ({start_year}) must be ≤ end_year ({end_year})"
        )
    # Daymet v4 coverage starts 1980-01-01; the upstream API silently
    # snaps out-of-range requests to its available window (a 1950
    # request returns 1980+ data — undetectable from the response and
    # silently mislabels the produced CSV's date column). Pre-validate
    # locally to fail loudly.
    DAYMET_FIRST_YEAR = 1980
    DAYMET_LAST_YEAR_GUARD = 2099  # generous upper bound; raise if needed
    if start_year < DAYMET_FIRST_YEAR or end_year > DAYMET_LAST_YEAR_GUARD:
        raise ValueError(
            f"Daymet v4 coverage is {DAYMET_FIRST_YEAR}-present. Got "
            f"start_year={start_year}, end_year={end_year}. The upstream "
            f"API silently returns its default range for out-of-window "
            f"requests, which would mislabel your CSV — refusing locally."
        )
    # Daymet's domain is N. America: CONUS+Mexico (lat 14.5-51,
    # lon -125 to -67), Hawaii, Alaska (lat 49.5-72, lon -179 to -130),
    # Puerto Rico. Approximate it with a generous bbox for the
    # local check; the upstream API will further reject points
    # outside actual tiles with a clearer message via raise_for_status.
    in_na_box = (-180.0 <= lon <= -50.0) and (14.0 <= lat <= 84.0)
    if not in_na_box:
        raise ValueError(
            f"(lat={lat}, lon={lon}) outside Daymet's North-America "
            f"domain (lon ∈ [-180, -50], lat ∈ [14, 84]). For South "
            f"America / Europe / Asia / Africa / Oceania use ERA5-Land "
            f"(not yet wired)."
        )

    variables = ["tmax", "tmin"]
    if include_precip:
        variables.append("prcp")
    params = {
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "vars": ",".join(variables),
        "start": f"{start_year}-01-01",
        "end": f"{end_year}-12-31",
        "format": "csv",
    }

    def _do_fetch() -> bytes:
        resp = requests.get(DAYMET_SINGLE_PIXEL, params=params, timeout=120)
        resp.raise_for_status()
        return resp.content

    cache = cached_fetch(
        subdir="daymet", url=DAYMET_SINGLE_PIXEL, params=params,
        suffix=".csv", fetch_fn=_do_fetch,
    )
    text = cache.path.read_text()

    # Parse the Daymet header (free-form key:value lines before the CSV
    # header row that starts with "year,yday,..."). We extract a few
    # for provenance/sanity.
    header_lines: list[str] = []
    body_start = 0
    for i, line in enumerate(text.splitlines()):
        if line.startswith("year,yday"):
            body_start = i
            break
        header_lines.append(line)
    snapped_lat = lat
    snapped_lon = lon
    tile_id = ""
    elev = float("nan")
    citation = ""
    for h in header_lines:
        if h.startswith("Latitude:"):
            # "Latitude: 44.94  Longitude: -113.93"
            parts = h.replace("Longitude:", " ").split()
            try:
                snapped_lat = float(parts[1])
                snapped_lon = float(parts[2])
            except (IndexError, ValueError):
                pass
        elif h.startswith("Tile:"):
            tile_id = h.split(":", 1)[1].strip()
        elif h.startswith("Elevation:"):
            try:
                elev = float(h.split(":", 1)[1].strip().split()[0])
            except (IndexError, ValueError):
                pass
        elif h.startswith("How to cite:"):
            citation = h.split(":", 1)[1].strip()

    body = "\n".join(text.splitlines()[body_start:])
    df_raw = pd.read_csv(StringIO(body))

    # Rename "tmax (deg c)" → "tmax_C" so column names are SQL-friendly
    rename = {c: c.split()[0] + "_C" for c in df_raw.columns
              if "tmax" in c or "tmin" in c}
    if include_precip:
        rename.update({c: "prcp_mm" for c in df_raw.columns if "prcp" in c})
    df_raw = df_raw.rename(columns=rename)

    # year + yday → ISO date
    df_raw["time"] = pd.to_datetime(
        df_raw["year"].astype(int).astype(str)
        + "-" + df_raw["yday"].astype(int).astype(str).str.zfill(3),
        format="%Y-%j",
    ).dt.strftime("%Y-%m-%d")

    df_raw["T_air_C_mean"] = (df_raw["tmax_C"] + df_raw["tmin_C"]) / 2.0
    df_raw["T_water_C_stefan"] = (
        STEFAN_AIR_TO_WATER_A
        + STEFAN_AIR_TO_WATER_B * df_raw["T_air_C_mean"]
    ).clip(lower=0.0)  # streams don't go below 0°C in the ice-free state

    cols = ["time", "tmax_C", "tmin_C", "T_air_C_mean", "T_water_C_stefan"]
    if include_precip:
        cols.append("prcp_mm")
    out = df_raw[cols].reset_index(drop=True)

    return DaymetFetchResult(
        df=out, cache=cache,
        lat=snapped_lat, lon=snapped_lon, tile_id=tile_id,
        elevation_m=elev, citation=citation,
    )
