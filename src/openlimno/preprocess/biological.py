"""Biological observation readers. SPEC §3.1.4.2.

Readers for the 6 biological observation tables defined in
``biological_observations.schema.json``:

- fish_sampling
- redd_count
- pit_tag_event
- rst_count
- edna_sample
- macroinvertebrate_sample

Each reader parses a CSV/Excel file and returns a DataFrame conforming to the
WEDM row schema, with optional schema validation.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from jsonschema import Draft202012Validator

from openlimno.wedm import _schema_dir


def _bio_schemas() -> dict[str, dict[str, Any]]:
    """Load the biological_observations schema and return per-table $defs."""
    p = _schema_dir() / "biological_observations.schema.json"
    schema = json.loads(p.read_text())
    return schema["$defs"]


def _read_table(path: str | Path, date_columns: list[str] | None = None) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
        df = pd.read_excel(p)
    else:
        df = pd.read_csv(p)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    for col in date_columns or []:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _stamp_campaign(df: pd.DataFrame, campaign_id: str | None) -> pd.DataFrame:
    if "campaign_id" not in df.columns:
        df = df.copy()
        df["campaign_id"] = campaign_id or str(uuid.uuid4())
    return df


def validate_biological_table(df: pd.DataFrame, table_name: str) -> list[str]:
    """Validate every row of df against the named biological table schema.

    Returns a list of human-readable errors (empty list = OK).
    """
    schemas = _bio_schemas()
    if table_name not in schemas:
        return [f"Unknown biological table: {table_name}"]
    validator = Draft202012Validator(schemas[table_name])
    errs: list[str] = []
    for i, row in df.iterrows():
        record = {k: v for k, v in row.to_dict().items() if pd.notna(v)}
        # Coerce datetimes to ISO strings for JSON-Schema "date-time" format
        for k, v in record.items():
            if hasattr(v, "isoformat"):
                record[k] = v.isoformat()
            elif hasattr(v, "item"):
                record[k] = v.item()
        for err in validator.iter_errors(record):
            errs.append(f"row {i}: {'/'.join(str(x) for x in err.absolute_path)}: {err.message}")
    return errs


def write_to_parquet(df: pd.DataFrame, path: str | Path, table_name: str) -> Path:
    """Write a biological observation DataFrame to WEDM-conformant Parquet."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    table = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            b"openlimno.format": f"wedm/0.1/biological/{table_name}".encode(),
        }
    )
    pq.write_table(table, p)
    return p


# --------------------------------------------------------------
# Per-table readers
# --------------------------------------------------------------
def read_fish_sampling(path: str | Path, campaign_id: str | None = None) -> pd.DataFrame:
    """Read fish sampling (electrofishing/snorkel/seine/...) table."""
    df = _read_table(path, date_columns=["time"])
    return _stamp_campaign(df, campaign_id)


def read_redd_count(path: str | Path, campaign_id: str | None = None) -> pd.DataFrame:
    """Read redd survey table."""
    df = _read_table(path, date_columns=["survey_date"])
    return _stamp_campaign(df, campaign_id)


def read_pit_tag_event(path: str | Path) -> pd.DataFrame:
    """Read PIT tag event table (release / recapture / detection)."""
    return _read_table(path, date_columns=["time"])


def read_rst_count(path: str | Path, campaign_id: str | None = None) -> pd.DataFrame:
    """Read RST (rotary screw trap) count table."""
    df = _read_table(path, date_columns=["time_start", "time_end"])
    return _stamp_campaign(df, campaign_id)


def read_edna_sample(path: str | Path, campaign_id: str | None = None) -> pd.DataFrame:
    """Read eDNA sample table."""
    df = _read_table(path, date_columns=["time"])
    return _stamp_campaign(df, campaign_id)


def read_macroinvertebrate_sample(path: str | Path, campaign_id: str | None = None) -> pd.DataFrame:
    """Read macroinvertebrate (Surber/kicknet/Hess/...) sample table."""
    df = _read_table(path)
    return _stamp_campaign(df, campaign_id)


__all__ = [
    "read_edna_sample",
    "read_fish_sampling",
    "read_macroinvertebrate_sample",
    "read_pit_tag_event",
    "read_redd_count",
    "read_rst_count",
    "validate_biological_table",
    "write_to_parquet",
]
