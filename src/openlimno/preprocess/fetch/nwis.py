"""USGS NWIS Water Services REST API client.

NWIS is the canonical discharge / gauge-height dataset for US streams,
~10000 active stream gauges, free + no-auth. We use the IV/DV JSON
endpoints + the RDB site-discovery + ``measurements`` field-measurement
endpoint that returns stage/discharge pairs (the rating-curve source).

Why not use ``hydrofunctions`` / ``dataretrieval``? Both pull in heavy
deps; our needs are narrow (daily Q, rating points, station search),
better to keep the dep surface to ``requests + pandas``.

NWIS docs:
    https://waterservices.usgs.gov/docs/  (DV/IV/site/measurements)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from openlimno.preprocess.fetch.cache import CacheEntry, cached_fetch

NWIS_DV = "https://waterservices.usgs.gov/nwis/dv/"
NWIS_SITE = "https://waterservices.usgs.gov/nwis/site/"
NWIS_MEAS = "https://waterservices.usgs.gov/nwis/measurements/"

# USGS NWIS parameter codes
PARAM_DISCHARGE = "00060"  # cubic feet per second
PARAM_GAGE_HEIGHT = "00065"  # feet

CFS_TO_M3S = 0.028316846592  # ft³/s → m³/s
FT_TO_M = 0.3048


@dataclass
class NWISFetchResult:
    """Outcome of an NWIS fetch.

    ``df`` carries the parsed dataset (units already in SI: m³/s, m).
    ``cache`` carries the provenance trail (source URL, fetch_time,
    SHA-256) that should be folded into the case's provenance.json.
    """

    df: pd.DataFrame
    cache: CacheEntry
    station_name: str = ""
    station_lat: float = float("nan")
    station_lon: float = float("nan")
    parameters: list[str] = field(default_factory=list)


def _fetch_text(url: str, params: dict, subdir: str, suffix: str) -> CacheEntry:
    def _do_fetch() -> bytes:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp.content

    return cached_fetch(
        subdir=subdir, url=url, params=params, suffix=suffix, fetch_fn=_do_fetch
    )


def fetch_nwis_daily_discharge(
    site_id: str, start_date: str, end_date: str
) -> NWISFetchResult:
    """Fetch USGS NWIS daily-mean discharge for a stream gauge.

    Args:
        site_id: USGS station number (8–15 digit string). Example:
            ``"13305000"`` is Lemhi River at Lemhi, ID.
        start_date: ISO date ``YYYY-MM-DD`` (inclusive).
        end_date: ISO date ``YYYY-MM-DD`` (inclusive).

    Returns:
        ``NWISFetchResult`` whose ``df`` has columns
        ``[time, discharge_m3s, discharge_cfs]`` matching the Lemhi
        ``Q_2024.csv`` schema so existing case YAMLs work unchanged.
    """
    params = {
        "format": "json",
        "sites": site_id,
        "parameterCd": PARAM_DISCHARGE,
        "startDT": start_date,
        "endDT": end_date,
        "siteStatus": "all",
    }
    cache = _fetch_text(NWIS_DV, params, subdir="nwis", suffix=".json")
    payload = json.loads(cache.path.read_bytes())

    ts_list = payload.get("value", {}).get("timeSeries", [])
    if not ts_list:
        raise ValueError(
            f"NWIS returned no time-series for site {site_id!r} "
            f"in {start_date}..{end_date}. Either the gauge has no "
            f"daily-Q records for this window, the site_id is wrong, "
            f"or the parameter code 00060 isn't measured here."
        )
    ts = ts_list[0]
    values = ts["values"][0]["value"]

    df = pd.DataFrame(values)
    df["dateTime"] = pd.to_datetime(df["dateTime"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df[df["value"] >= 0]  # NWIS uses negative codes for missing

    out = pd.DataFrame(
        {
            "time": df["dateTime"].dt.strftime("%Y-%m-%d"),
            "discharge_m3s": df["value"] * CFS_TO_M3S,
            "discharge_cfs": df["value"],
        }
    ).reset_index(drop=True)

    # Station metadata for provenance
    src_info = ts.get("sourceInfo", {})
    name = src_info.get("siteName", "")
    geo = src_info.get("geoLocation", {}).get("geogLocation", {})
    return NWISFetchResult(
        df=out,
        cache=cache,
        station_name=name,
        station_lat=float(geo.get("latitude", float("nan"))),
        station_lon=float(geo.get("longitude", float("nan"))),
        parameters=[PARAM_DISCHARGE],
    )


def fetch_nwis_rating_curve(site_id: str) -> NWISFetchResult:
    """Fetch USGS NWIS field-measurement rating points for a gauge.

    Returns a DataFrame with columns ``[h_m, Q_m3s, sigma_Q]`` matching
    OpenLimno's ``rating_curve.parquet`` schema. ``sigma_Q`` is derived
    from NWIS measurement quality flag (Excellent/Good/Fair/Poor →
    2%/5%/8%/12% of Q).

    NOTE (v0.3 P0): USGS deprecated the legacy
    ``waterdata.usgs.gov/nwis/measurements?format=rdb`` endpoint in
    2024 as part of the migration to the new Water Data API. As of
    today the replacement REST endpoint for field measurements is
    still in beta and not stable enough to wire up — see the upstream
    migration plan at
    https://waterdata.usgs.gov/blog/wdfn-water-data-migration/. For
    now this function raises so users see a clear error rather than
    silently empty results.
    """
    raise NotImplementedError(
        "USGS NWIS field-measurement (rating-curve) endpoint is in "
        "migration as of 2024 and the legacy RDB format URL now returns "
        "HTML. v0.3 P0 ships discharge + DEM fetch; rating-curve fetch "
        "deferred until USGS Water Data API stabilises. Workaround: "
        "manually download from "
        f"https://waterdata.usgs.gov/monitoring-location/{site_id}/#dataTypeId=continuous-00065-0 "
        "and feed via ``openlimno preprocess`` (rating_curve.parquet)."
    )

    # Implementation kept for when the upstream endpoint stabilises:
    params = {
        "format": "rdb",
        "site_no": site_id,
        "agency_cd": "USGS",
    }
    cache = _fetch_text(NWIS_MEAS, params, subdir="nwis", suffix=".rdb")
    text = cache.path.read_text()

    # RDB: tab-separated, lines starting with # are comments, second-last
    # header row is data-types-and-widths
    data_lines = [
        ln for ln in text.splitlines()
        if ln and not ln.startswith("#") and not ln.startswith("5s")
    ]
    if not data_lines:
        raise ValueError(
            f"NWIS returned no field measurements for site {site_id!r}. "
            f"Either the gauge has no rating points or the site_id is wrong."
        )
    df = pd.read_csv(StringIO("\n".join(data_lines)), sep="\t")
    # Quality-flag → sigma fraction mapping (NWIS standard)
    sigma_map = {
        "Excellent": 0.02, "Good": 0.05, "Fair": 0.08, "Poor": 0.12,
        "Unspecified": 0.10, "Unknown": 0.10,
    }
    df["gage_height_va"] = pd.to_numeric(df["gage_height_va"], errors="coerce")
    df["discharge_va"] = pd.to_numeric(df["discharge_va"], errors="coerce")
    df = df.dropna(subset=["gage_height_va", "discharge_va"])
    df = df[df["gage_height_va"] > 0]

    out = pd.DataFrame(
        {
            "gauge_id": site_id,
            "h_m": df["gage_height_va"] * FT_TO_M,
            "Q_m3s": df["discharge_va"] * CFS_TO_M3S,
            "sigma_Q": (df["discharge_va"] * CFS_TO_M3S) * df.get(
                "measured_rating_diff", "Unspecified"
            ).map(sigma_map).fillna(0.10),
        }
    ).reset_index(drop=True)
    out = out.sort_values("h_m").reset_index(drop=True)

    return NWISFetchResult(df=out, cache=cache, parameters=[PARAM_DISCHARGE, PARAM_GAGE_HEIGHT])


def find_nwis_stations_near(
    lat: float, lon: float, radius_deg: float = 0.5
) -> pd.DataFrame:
    """Find active USGS stream gauges within a bounding box around (lat, lon).

    Returns a DataFrame of nearby stations. Use this for case-discovery
    when the user provides only a map click — they probably don't know
    the gauge ID upfront.

    Args:
        lat: center latitude (decimal degrees).
        lon: center longitude (decimal degrees, negative for W).
        radius_deg: half-width of search bbox in degrees (~111 km/deg).
            Default 0.5° ≈ 55 km — large enough to find SOMETHING in
            most US watersheds, small enough to avoid pulling the
            whole state.
    """
    bbox = f"{lon - radius_deg:.4f},{lat - radius_deg:.4f}," \
           f"{lon + radius_deg:.4f},{lat + radius_deg:.4f}"
    params = {
        "format": "rdb",
        "bBox": bbox,
        "siteType": "ST",  # ST = stream
        "parameterCd": PARAM_DISCHARGE,
        "siteStatus": "active",
        "hasDataTypeCd": "dv",
    }
    cache = _fetch_text(NWIS_SITE, params, subdir="nwis", suffix=".rdb")
    text = cache.path.read_text()
    data_lines = [
        ln for ln in text.splitlines()
        if ln and not ln.startswith("#") and not ln.startswith("5s")
    ]
    if len(data_lines) < 2:
        return pd.DataFrame(
            columns=["site_no", "station_nm", "dec_lat_va", "dec_long_va"]
        )
    df = pd.read_csv(StringIO("\n".join(data_lines)), sep="\t", dtype={"site_no": str})
    return df[["site_no", "station_nm", "dec_lat_va", "dec_long_va"]].reset_index(drop=True)
