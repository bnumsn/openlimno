"""Generic habitat-result table exchange for HABBY/CASiMiR-style outputs.

HABBY, CASiMiR, MesoHABSIM, and similar tools differ in file containers and
column labels, but their exchange surface is usually simple: cell area,
suitability index, weighted usable area, discharge/time, species/stage, and
optional depth/velocity. This adapter normalizes those tables without claiming
to be a full project-file reader for any one tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HabitatExchangeInspection:
    """Diagnostic view of an external habitat table."""

    path: str
    n_rows: int
    columns: tuple[str, ...]
    table_type: str
    detected_roles: dict[str, str]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HabitatExchangeImportSummary:
    """Small import report for HABBY/CASiMiR-style exchange tables."""

    source_key: str
    output_table: str
    n_rows: int
    detected_roles: dict[str, str]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HabitatExchangeImportResult:
    """Normalized habitat table plus import metadata."""

    table: pd.DataFrame
    summary: HabitatExchangeImportSummary


ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "cell_id": ("cell_id", "cellid", "element_id", "elementid", "face_id", "unit_id", "id", "n"),
    "x": ("x", "x_m", "coord_x", "centroid_x", "center_x", "centre_x"),
    "y": ("y", "y_m", "coord_y", "centroid_y", "center_y", "centre_y"),
    "area_m2": (
        "area_m2",
        "area",
        "area_m²",
        "cell_area",
        "cellarea",
        "wetted_area",
        "wetted_area_m2",
        "surface_m2",
        "a_i",
        "ai",
    ),
    "csi": (
        "csi",
        "hsi",
        "si",
        "hv",
        "suitability",
        "suitability_index",
        "habitat_value",
        "habitat_value_dominant",
        "habitat_suitability",
        "habitat_suitability_index",
        "hydraulic_habitat_suitability",
        "hhs",
    ),
    "wua_m2": (
        "wua_m2",
        "wua",
        "spu",
        "spu_m2",
        "weighted_usable_area",
        "weighted_usable_area_m2",
        "usable_area",
        "usable_area_m2",
    ),
    "depth_m": ("depth_m", "depth", "water_depth", "waterdepth", "h"),
    "velocity_ms": (
        "velocity_ms",
        "velocity_m_s",
        "velocity",
        "water_velocity",
        "current_speed",
        "speed",
        "v",
    ),
    "discharge_m3s": (
        "discharge_m3s",
        "discharge",
        "flow",
        "flow_m3s",
        "q",
        "q_m3s",
    ),
    "species": ("species", "taxon", "fish", "organism", "model"),
    "life_stage": ("life_stage", "lifestage", "stage", "lifephase", "life_phase"),
    "time": ("time", "datetime", "date", "timestamp"),
    "time_index": ("time_index", "timestep", "time_step", "step"),
    "hmu_type": ("hmu_type", "mesohabitat", "habitat_unit", "unit_type"),
}


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _role_hit_count(columns: pd.Index) -> int:
    by_norm = {_norm(str(col)) for col in columns}
    hits = 0
    for aliases in ROLE_ALIASES.values():
        if any(_norm(alias) in by_norm for alias in aliases):
            hits += 1
    return hits


def _read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(p)
    if suffix in {".tsv", ".tab"}:
        return pd.read_csv(p, sep="\t", skipinitialspace=True)
    candidates = []
    for skiprows in (0, 1, 2):
        try:
            candidates.append(
                pd.read_csv(p, sep=None, engine="python", skipinitialspace=True, skiprows=skiprows)
            )
        except Exception:
            continue
    if not candidates:
        raise ValueError(f"Could not read habitat exchange table {p}.")
    return max(candidates, key=lambda df: _role_hit_count(df.columns))


def _detect_roles(df: pd.DataFrame) -> dict[str, str]:
    by_norm = {_norm(str(col)): str(col) for col in df.columns}
    roles: dict[str, str] = {}
    for role, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            found = by_norm.get(_norm(alias))
            if found is not None:
                roles[role] = found
                break
    if "csi" not in roles:
        for col in df.columns:
            norm = _norm(str(col))
            if "hvdominant" in norm or norm.endswith("habitatvalue"):
                roles["csi"] = str(col)
                break
    return roles


def _table_type(roles: dict[str, str]) -> str:
    if "cell_id" in roles or ("x" in roles and "y" in roles) or ("area_m2" in roles and "csi" in roles):
        return "habitat_cells"
    if "wua_m2" in roles or ("area_m2" in roles and "csi" in roles):
        return "wua_summary"
    return "unknown"


def inspect_habitat_exchange(path: str | Path) -> HabitatExchangeInspection:
    """Inspect a HABBY/CASiMiR-style delimited/Parquet exchange table."""

    p = Path(path)
    df = _read_table(p)
    roles = _detect_roles(df)
    table_type = _table_type(roles)
    warnings: list[str] = []
    if table_type == "unknown":
        warnings.append("No WUA or area*suitability columns detected.")
    if table_type == "habitat_cells" and "area_m2" not in roles:
        warnings.append("Cell table has no area column; WUA cannot be recomputed.")
    if "csi" not in roles and "wua_m2" not in roles:
        warnings.append("No suitability or WUA column detected.")
    return HabitatExchangeInspection(
        path=str(p),
        n_rows=len(df),
        columns=tuple(str(col) for col in df.columns),
        table_type=table_type,
        detected_roles=roles,
        warnings=tuple(warnings),
    )


def _copy_role(
    source: pd.DataFrame,
    target: pd.DataFrame,
    roles: dict[str, str],
    role: str,
    target_name: str | None = None,
) -> None:
    col = roles.get(role)
    if col is None:
        return
    target[target_name or role] = source[col]


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _normalize_cells(df: pd.DataFrame, roles: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    out = pd.DataFrame()
    for role in (
        "cell_id",
        "x",
        "y",
        "depth_m",
        "velocity_ms",
        "discharge_m3s",
        "species",
        "life_stage",
        "time",
        "time_index",
        "hmu_type",
    ):
        _copy_role(df, out, roles, role)

    if "cell_id" not in out:
        out["cell_id"] = np.arange(len(df), dtype=int)

    if "area_m2" in roles:
        out["area_m2"] = _numeric(df[roles["area_m2"]])
    else:
        warnings.append("No area column detected; per-cell WUA is preserved only if present.")

    if "csi" in roles:
        out["csi"] = _numeric(df[roles["csi"]]).clip(lower=0.0, upper=1.0)
    if "wua_m2" in roles:
        out["wua_m2"] = _numeric(df[roles["wua_m2"]])

    if "wua_m2" not in out and {"area_m2", "csi"}.issubset(out.columns):
        out["wua_m2"] = out["area_m2"] * out["csi"]
    if "csi" not in out and {"wua_m2", "area_m2"}.issubset(out.columns):
        area = out["area_m2"].replace(0, np.nan)
        out["csi"] = (out["wua_m2"] / area).clip(lower=0.0, upper=1.0)

    if "wua_m2" not in out:
        raise ValueError("Habitat cell table needs WUA or area*suitability columns.")

    return out, warnings


def _normalize_summary(df: pd.DataFrame, roles: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    out = pd.DataFrame()
    for role in ("discharge_m3s", "species", "life_stage", "time", "time_index"):
        _copy_role(df, out, roles, role)
    if "wua_m2" in roles:
        out["wua_m2"] = _numeric(df[roles["wua_m2"]])
    elif {"area_m2", "csi"}.issubset(roles):
        out["area_m2"] = _numeric(df[roles["area_m2"]])
        out["mean_csi"] = _numeric(df[roles["csi"]])
        out["wua_m2"] = out["area_m2"] * out["mean_csi"]
    else:
        raise ValueError("Habitat summary table needs WUA or area*suitability columns.")

    if "area_m2" in roles and "area_m2" not in out:
        out["area_m2"] = _numeric(df[roles["area_m2"]])
    if {"wua_m2", "area_m2"}.issubset(out.columns) and "mean_csi" not in out:
        area = out["area_m2"].replace(0, np.nan)
        out["mean_csi"] = (out["wua_m2"] / area).clip(lower=0.0, upper=1.0)
    if "area_m2" not in out:
        warnings.append("No total/wetted area column detected; normalized WUA was not computed.")
    return out, warnings


def read_habitat_exchange(path: str | Path, *, source_key: str = "habby-csv") -> HabitatExchangeImportResult:
    """Normalize a HABBY/CASiMiR-style delimited/Parquet table.

    Returns ``habitat_cells`` when cell-level columns are detected, otherwise
    returns ``wua_summary``. The adapter is alias-based and preserves only the
    common exchange surface needed for OpenLimno comparison/reporting.
    """

    p = Path(path)
    df = _read_table(p)
    roles = _detect_roles(df)
    table_type = _table_type(roles)
    if table_type == "habitat_cells":
        table, warnings = _normalize_cells(df, roles)
    elif table_type == "wua_summary":
        table, warnings = _normalize_summary(df, roles)
    else:
        raise ValueError("Cannot detect HABBY/CASiMiR habitat exchange columns.")

    table.insert(0, "source_file", str(p))
    table.attrs["openlimno_source_model"] = "HABBY/CASiMiR habitat exchange"
    table.attrs["openlimno_source_key"] = source_key
    table.attrs["openlimno_output_table"] = table_type
    return HabitatExchangeImportResult(
        table=table,
        summary=HabitatExchangeImportSummary(
            source_key=source_key,
            output_table=table_type,
            n_rows=len(table),
            detected_roles=roles,
            warnings=tuple(warnings),
        ),
    )


__all__ = [
    "HabitatExchangeImportResult",
    "HabitatExchangeImportSummary",
    "HabitatExchangeInspection",
    "inspect_habitat_exchange",
    "read_habitat_exchange",
]
