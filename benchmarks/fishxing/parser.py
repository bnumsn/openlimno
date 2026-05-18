"""Parser for archived FishXing velocity reference exports."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from benchmarks._compare.adapter import ReferenceResult

DISCHARGE_ALIASES = {
    "dischargem3s",
    "qm3s",
    "flowm3s",
    "discharge",
    "flow",
    "q",
}
VELOCITY_ALIASES = {
    "velocityms",
    "velocitymps",
    "velocitympersec",
    "velocity",
    "barriervelocity",
    "culvertvelocity",
    "v",
}


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _slug(value: object, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() == "nan":
        text = fallback
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return slug or fallback


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix in {".tsv", ".tab"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path, sep=None, engine="python")


def _find_alias(df: pd.DataFrame, aliases: set[str]) -> str | None:
    by_norm = {_norm(str(col)): str(col) for col in df.columns}
    for alias in aliases:
        found = by_norm.get(alias)
        if found is not None:
            return found
    return None


def read_fishxing_report(path: Path | str) -> ReferenceResult:
    """Read an archived FishXing CSV/XLS(X) velocity table.

    The normalized table uses ``discharge_m3s`` plus one or more
    ``velocity_ms_<species>_<stage>`` columns so the shared comparison
    harness can use the ``max_abs_m_per_s`` acceptance threshold.
    """
    report_path = Path(path)
    df = _read_table(report_path)
    q_col = _find_alias(df, DISCHARGE_ALIASES)
    v_col = _find_alias(df, VELOCITY_ALIASES)
    if q_col is None or v_col is None:
        raise ValueError(
            "FishXing report needs discharge and velocity columns; "
            f"got {list(df.columns)!r}"
        )

    working = pd.DataFrame({
        "discharge_m3s": pd.to_numeric(df[q_col], errors="coerce"),
        "velocity_ms": pd.to_numeric(df[v_col], errors="coerce"),
    }).dropna(subset=["discharge_m3s", "velocity_ms"])
    if working.empty:
        raise ValueError(f"FishXing report {report_path} has no numeric rows")

    species_col = _find_alias(df, {"species", "taxon", "fish"})
    stage_col = _find_alias(df, {"lifestage", "stage", "lifephase"})
    working["species"] = df[species_col] if species_col else "species"
    working["life_stage"] = df[stage_col] if stage_col else "stage"

    grouped = (
        working.groupby(["discharge_m3s", "species", "life_stage"], dropna=False)[
            "velocity_ms"
        ]
        .mean()
        .reset_index()
    )
    out = pd.DataFrame({
        "discharge_m3s": sorted(grouped["discharge_m3s"].unique())
    })
    for row in grouped.itertuples(index=False):
        suffix = f"{_slug(row.species, 'species')}_{_slug(row.life_stage, 'stage')}"
        col = f"velocity_ms_{suffix}"
        mask = out["discharge_m3s"] == row.discharge_m3s
        out.loc[mask, col] = float(row.velocity_ms)

    return ReferenceResult(
        platform="fishxing",
        wua_q=out.sort_values("discharge_m3s").reset_index(drop=True).fillna(0.0),
        provenance={"source_file": str(report_path.resolve())},
    )


__all__ = ["read_fishxing_report"]
