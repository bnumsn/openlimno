"""Habitat evaluation for imported hydraulic-cell tables.

This module is the bridge from external hydraulic models (HEC-RAS HDF,
TELEMAC, Delft3D, MIKE plugins, etc.) to OpenLimno habitat outputs. It accepts
a flat staging table with per-cell depth/velocity/area fields and produces:

* per-cell SI/CSI/WUA fields
* grouped WUA summaries
* HMU summaries using the same classifier as the built-in case runner
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .hmu import classify_reach
from .hsi import CompositeMethod, HSICurve, composite_csi, require_independence_ack

DEFAULT_GROUP_COLUMNS = ("source_file", "flow_area", "discharge_m3s", "time_index", "time")


@dataclass(frozen=True)
class HabitatCellsResult:
    """Cell-scale habitat evaluation plus summary tables."""

    cells: pd.DataFrame
    summary: pd.DataFrame
    hmu_summary: pd.DataFrame


def _present_group_columns(df: pd.DataFrame, group_cols: list[str] | None) -> list[str]:
    if group_cols is not None:
        missing = [c for c in group_cols if c not in df.columns]
        if missing:
            raise ValueError(f"group column(s) missing from cells table: {missing}")
        return group_cols
    return [c for c in DEFAULT_GROUP_COLUMNS if c in df.columns]


def evaluate_habitat_cells(
    cells: pd.DataFrame,
    hsi_curves: dict[tuple[str, str, str], HSICurve],
    *,
    species: str,
    life_stage: str,
    composite: CompositeMethod = "geometric_mean",
    acknowledge_independence: bool = False,
    depth_col: str = "depth_m",
    velocity_col: str = "velocity_ms",
    area_col: str = "area_m2",
    group_cols: list[str] | None = None,
) -> HabitatCellsResult:
    """Evaluate HSI/CSI/WUA for a hydraulic-cell staging table.

    Required input columns are ``depth_m``, ``velocity_ms``, and ``area_m2`` by
    default. Optional grouping columns such as ``flow_area`` and ``time_index``
    are preserved into summary outputs when present.
    """

    require_independence_ack(composite, acknowledge_independence)
    for col in (depth_col, velocity_col, area_col):
        if col not in cells.columns:
            raise ValueError(f"hydraulic cells table missing required column {col!r}")

    depth_key = (species, life_stage, "depth")
    velocity_key = (species, life_stage, "velocity")
    missing_curves = [key for key in (depth_key, velocity_key) if key not in hsi_curves]
    if missing_curves:
        raise ValueError(f"missing HSI curve(s): {missing_curves}")

    out = cells.copy()
    depths = out[depth_col].to_numpy(dtype=float)
    velocities = out[velocity_col].to_numpy(dtype=float)
    areas = out[area_col].to_numpy(dtype=float)
    if np.any(areas < 0):
        raise ValueError(f"{area_col!r} contains negative areas")

    si_depth = hsi_curves[depth_key].evaluate(depths)
    si_velocity = hsi_curves[velocity_key].evaluate(velocities)
    csi = composite_csi(
        {"depth": si_depth, "velocity": si_velocity},
        method=composite,
    )

    out["species"] = species
    out["life_stage"] = life_stage
    out["si_depth"] = si_depth
    out["si_velocity"] = si_velocity
    out["csi"] = csi
    out["wua_m2"] = csi * areas
    out["hmu_type"] = classify_reach(velocities, depths)

    groups = _present_group_columns(out, group_cols)
    summary = summarize_habitat_cells(out, group_cols=groups, area_col=area_col)
    hmu_summary = summarize_habitat_by_hmu(out, group_cols=groups)
    return HabitatCellsResult(cells=out, summary=summary, hmu_summary=hmu_summary)


def summarize_habitat_cells(
    habitat_cells: pd.DataFrame,
    *,
    group_cols: list[str] | None = None,
    area_col: str = "area_m2",
) -> pd.DataFrame:
    """Summarize evaluated habitat cells into total WUA by group."""

    for col in ("wua_m2", "csi", area_col):
        if col not in habitat_cells.columns:
            raise ValueError(f"habitat cells table missing required column {col!r}")
    groups = _present_group_columns(habitat_cells, group_cols)
    agg = {
        "wua_m2": ("wua_m2", "sum"),
        "area_m2": (area_col, "sum"),
        "mean_csi": ("csi", "mean"),
        "n_cells": ("csi", "size"),
    }
    if groups:
        return habitat_cells.groupby(groups, dropna=False).agg(**agg).reset_index()
    return pd.DataFrame(
        [
            {
                "wua_m2": float(habitat_cells["wua_m2"].sum()),
                "area_m2": float(habitat_cells[area_col].sum()),
                "mean_csi": float(habitat_cells["csi"].mean()),
                "n_cells": int(len(habitat_cells)),
            }
        ]
    )


def summarize_habitat_by_hmu(
    habitat_cells: pd.DataFrame,
    *,
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Summarize WUA by HMU type, preserving time/flow groups when present."""

    for col in ("wua_m2", "hmu_type", "csi"):
        if col not in habitat_cells.columns:
            raise ValueError(f"habitat cells table missing required column {col!r}")
    groups = [*_present_group_columns(habitat_cells, group_cols), "hmu_type"]
    return (
        habitat_cells.groupby(groups, dropna=False)
        .agg(
            wua_m2=("wua_m2", "sum"),
            mean_csi=("csi", "mean"),
            n_cells=("csi", "size"),
        )
        .reset_index()
    )


__all__ = [
    "DEFAULT_GROUP_COLUMNS",
    "HabitatCellsResult",
    "evaluate_habitat_cells",
    "summarize_habitat_by_hmu",
    "summarize_habitat_cells",
]
