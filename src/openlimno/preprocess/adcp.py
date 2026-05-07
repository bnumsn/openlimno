"""USGS QRev CSV ADCP transect reader. SPEC §4.0.1 M1 必交付.

QRev (Quality control & Rating Evaluation for ADCP) is the USGS-recommended
post-processing tool for moving-boat ADCP discharge measurements. Its CSV
exports include:
  - ensemble-by-ensemble averaged variables (time, position, depth, velocity)
  - whole-transect totals (discharge, span, etc.)

This reader extracts ensemble-level data into the WEDM ``adcp_transect`` row
schema. We are tolerant of column-name variants because QRev exports differ
slightly across versions.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pandas as pd

# Map of QRev column synonyms → canonical WEDM names
COLUMN_ALIASES: dict[str, list[str]] = {
    "time": ["time", "datetime", "date_time", "ens_time", "ensemble_time"],
    "depth_m": ["depth", "depth_m", "ens_depth", "depth_avg"],
    "u_ms": ["u", "u_ms", "v_east", "velocity_east"],
    "v_ms": ["v", "v_ms", "v_north", "velocity_north"],
    "w_ms": ["w", "w_ms", "v_vert", "velocity_vert"],
    "backscatter_db": ["backscatter", "bs", "backscatter_db"],
    "lon": ["lon", "longitude", "x"],
    "lat": ["lat", "latitude", "y"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _resolve_column(df: pd.DataFrame, canonical: str) -> str | None:
    """Find which column in df matches a canonical name."""
    for alias in COLUMN_ALIASES.get(canonical, [canonical]):
        if alias in df.columns:
            return alias
    return None


def read_adcp_qrev(
    path: str | Path, campaign_id: str | None = None
) -> pd.DataFrame:
    """Read a USGS QRev CSV ADCP transect into a WEDM-conformant DataFrame.

    Parameters
    ----------
    path
        QRev CSV file (sometimes named ``*_QRev.csv`` or transect summary).
    campaign_id
        Survey campaign UUID; auto-generated if omitted.

    Returns
    -------
    DataFrame with columns: campaign_id, time, lon, lat, depth_m, u_ms, v_ms,
    w_ms, backscatter_db. Some columns may be NaN if the QRev export omitted them.
    """
    path = Path(path)

    # QRev sometimes prefixes metadata with a ``,`` line or with column-only line;
    # be tolerant by skipping leading lines until a recognizable header is found.
    with path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    skip = 0
    for i, line in enumerate(lines):
        cols = [c.strip().lower() for c in line.split(",")]
        if any(any(alias in cols for alias in COLUMN_ALIASES["time"]) for _ in [0]):
            skip = i
            break
    df = pd.read_csv(path, skiprows=skip)
    df = _normalize_columns(df)

    cid = campaign_id or str(uuid.uuid4())

    out: dict[str, Any] = {"campaign_id": [cid] * len(df)}

    time_col = _resolve_column(df, "time")
    if time_col:
        try:
            out["time"] = pd.to_datetime(df[time_col], errors="coerce")
        except Exception:
            out["time"] = pd.NaT

    for canonical in ("depth_m", "u_ms", "v_ms", "w_ms", "backscatter_db",
                      "lon", "lat"):
        c = _resolve_column(df, canonical)
        if c:
            out[canonical] = pd.to_numeric(df[c], errors="coerce")
        else:
            out[canonical] = pd.Series([float("nan")] * len(df))

    return pd.DataFrame(out)


__all__ = ["read_adcp_qrev"]
