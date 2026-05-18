"""Helpers for normalising external reference-platform result files."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from benchmarks._compare.adapter import ReferenceResult
from openlimno.preprocess.habitat_exchange import read_habitat_exchange


def _slug(value: object, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() == "nan":
        text = fallback
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return slug or fallback


def _wua_result_from_table(table: pd.DataFrame) -> pd.DataFrame:
    if "discharge_m3s" not in table.columns:
        raise ValueError(
            "External habitat reference table must include discharge_m3s "
            "(or a supported alias such as Q/q_m3s)."
        )
    if "wua_m2" not in table.columns:
        raise ValueError("External habitat reference table must include WUA.")

    working = table.copy()
    if "species" not in working.columns:
        working["species"] = "species"
    if "life_stage" not in working.columns:
        working["life_stage"] = "stage"

    grouped = (
        working.groupby(["discharge_m3s", "species", "life_stage"], dropna=False)[
            "wua_m2"
        ]
        .sum()
        .reset_index()
    )

    out = pd.DataFrame({
        "discharge_m3s": sorted(grouped["discharge_m3s"].unique())
    })
    for row in grouped.itertuples(index=False):
        suffix = f"{_slug(row.species, 'species')}_{_slug(row.life_stage, 'stage')}"
        col = f"wua_m2_{suffix}"
        mask = out["discharge_m3s"] == row.discharge_m3s
        out.loc[mask, col] = float(row.wua_m2)
    return out.sort_values("discharge_m3s").reset_index(drop=True).fillna(0.0)


def reference_result_from_habitat_file(
    path: Path | str,
    *,
    platform: str,
    source_key: str,
) -> ReferenceResult:
    """Read a HABBY/CASiMiR/River2D-style WUA table as a reference result."""
    result = read_habitat_exchange(path, source_key=source_key)
    return ReferenceResult(
        platform=platform,
        wua_q=_wua_result_from_table(result.table),
        provenance={
            "source_file": str(Path(path).resolve()),
            "source_key": source_key,
            "output_table": result.summary.output_table,
            "warnings": list(result.summary.warnings),
        },
    )


__all__ = ["reference_result_from_habitat_file"]
