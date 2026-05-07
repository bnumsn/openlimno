"""Cross-section CSV/Excel reader. SPEC §4.0.1 M1 必交付.

Expected input columns (case-insensitive):
- station_m   — station along reach (m)
- distance_m  — lateral distance from reference point (m)
- elevation_m — bed elevation at point (m)

Optional:
- substrate, cover, point_index, depth_m

Output: pandas DataFrame conforming to WEDM ``cross_section`` row schema, plus
``write_cross_sections_to_parquet`` to drop into a Lemhi-style data directory.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REQUIRED = {"station_m", "distance_m", "elevation_m"}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase + underscore-normalise column names."""
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def read_cross_sections(
    path: str | Path,
    campaign_id: str | None = None,
    sheet_name: str | int | None = None,
) -> pd.DataFrame:
    """Read cross-section table from CSV or Excel.

    Auto-detects format by extension. For Excel, uses the first sheet unless
    ``sheet_name`` is given.

    Returns a DataFrame with the WEDM cross_section row shape:
    ``campaign_id, station_m, point_index, distance_m, elevation_m, substrate, cover``.
    """
    path = Path(path)
    if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
        df = pd.read_excel(path, sheet_name=sheet_name or 0)
    else:
        df = pd.read_csv(path)

    df = _normalize_columns(df)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(
            f"Cross-section input missing required columns: {sorted(missing)}. "
            f"Got: {sorted(df.columns)}"
        )

    cid = campaign_id or str(uuid.uuid4())
    out = pd.DataFrame(
        {
            "campaign_id": cid,
            "station_m": df["station_m"].astype(float),
            "distance_m": df["distance_m"].astype(float),
            "elevation_m": df["elevation_m"].astype(float),
        }
    )
    # Optional fields
    if "point_index" in df.columns:
        out["point_index"] = df["point_index"].astype(int)
    else:
        # Auto-assign point_index per station based on row order
        out["point_index"] = out.groupby("station_m").cumcount().astype(int)
    if "substrate" in df.columns:
        out["substrate"] = df["substrate"].astype(str)
    if "cover" in df.columns:
        out["cover"] = df["cover"].astype(str)
    if "depth_m" in df.columns:
        out["depth_m"] = df["depth_m"].astype(float)

    # Sanity: each (station_m, distance_m) pair must be unique
    if out.duplicated(subset=["station_m", "distance_m"]).any():
        raise ValueError("Duplicate (station_m, distance_m) pair detected in cross-section input")
    return out


def write_cross_sections_to_parquet(
    df: pd.DataFrame, path: str | Path, source_note: str | None = None
) -> Path:
    """Write a cross-section DataFrame to WEDM-conformant Parquet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = {
        b"openlimno.format": b"wedm/0.1/cross_section",
    }
    if source_note:
        metadata[b"openlimno.source"] = source_note.encode("utf-8")
    table = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            **metadata,
        }
    )
    pq.write_table(table, path)
    return path


__all__ = ["read_cross_sections", "write_cross_sections_to_parquet"]
