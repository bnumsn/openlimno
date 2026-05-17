"""CSV exchange bridge for inSTREAM/InSALMO/NetLogo population workflows.

OpenLimno does not run an individual-based model in core. This module provides
stable tabular exchange surfaces so users can move OpenLimno hydraulic/habitat
cells into inSTREAM-style workflows and bring population summaries back for
comparison and reporting.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class InstreamExchangeInspection:
    """Diagnostic view of an inSTREAM/NetLogo exchange table."""

    path: str
    n_rows: int
    columns: tuple[str, ...]
    table_type: str
    detected_roles: dict[str, str]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstreamImportSummary:
    """Small import report for inSTREAM/NetLogo exchange tables."""

    source_key: str
    output_table: str
    n_rows: int
    detected_roles: dict[str, str]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstreamImportResult:
    """Normalized inSTREAM/NetLogo table plus import metadata."""

    table: pd.DataFrame
    summary: InstreamImportSummary


@dataclass(frozen=True)
class InstreamHabitatExportResult:
    """OpenLimno tables prepared for an IBM/NetLogo exchange package."""

    habitat_cells: pd.DataFrame
    flow_summary: pd.DataFrame
    manifest: pd.DataFrame
    paths: dict[str, str] | None = None


ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "scenario_id": ("scenario_id", "scenario", "run_id", "experiment", "treatment"),
    "reach_id": ("reach_id", "reach", "reach_name", "site", "segment"),
    "cell_id": ("cell_id", "cellid", "patch_id", "habitat_cell", "id", "unit_id"),
    "x": ("x", "x_m", "coord_x", "centroid_x", "center_x", "centre_x"),
    "y": ("y", "y_m", "coord_y", "centroid_y", "center_y", "centre_y"),
    "area_m2": ("area_m2", "area", "cell_area", "wetted_area", "surface_m2"),
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
    "discharge_m3s": ("discharge_m3s", "discharge", "flow", "flow_m3s", "q", "q_m3s"),
    "temperature_c": ("temperature_c", "temp_c", "water_temperature_c", "temperature"),
    "turbidity_ntu": ("turbidity_ntu", "turbidity", "ntu"),
    "csi": ("csi", "hsi", "si", "suitability", "suitability_index"),
    "wua_m2": ("wua_m2", "wua", "weighted_usable_area", "usable_area"),
    "hmu_type": ("hmu_type", "mesohabitat", "habitat_unit", "unit_type"),
    "hiding_cover": ("hiding_cover", "hide_cover", "cover", "cover_fraction"),
    "feeding_cover": ("feeding_cover", "drift_cover", "food_cover"),
    "substrate": ("substrate", "substrate_type", "bed_material"),
    "species": ("species", "taxon", "fish", "organism"),
    "life_stage": ("life_stage", "lifestage", "stage", "lifephase", "life_phase"),
    "age_class": ("age_class", "age", "ageclass", "cohort"),
    "year": ("year", "simulation_year", "sim_year"),
    "day": ("day", "julian_day", "day_of_year", "doy", "simulation_day"),
    "time": ("time", "datetime", "date", "timestamp"),
    "time_index": ("time_index", "timestep", "time_step", "step"),
    "abundance": ("abundance", "n_fish", "fish_count", "count", "population", "population_size"),
    "biomass_g": ("biomass_g", "biomass", "total_biomass_g"),
    "mean_length_mm": ("mean_length_mm", "mean_length", "avg_length_mm", "length_mm"),
    "survival_rate": ("survival_rate", "survival", "survivorship"),
    "n_recruits": ("n_recruits", "recruits", "recruitment"),
    "n_spawners": ("n_spawners", "spawners", "adult_spawners"),
}

HABITAT_ROLES = (
    "scenario_id",
    "reach_id",
    "cell_id",
    "x",
    "y",
    "area_m2",
    "depth_m",
    "velocity_ms",
    "discharge_m3s",
    "temperature_c",
    "turbidity_ntu",
    "csi",
    "wua_m2",
    "hmu_type",
    "hiding_cover",
    "feeding_cover",
    "substrate",
    "time",
    "time_index",
)

POPULATION_ROLES = (
    "scenario_id",
    "reach_id",
    "species",
    "life_stage",
    "age_class",
    "year",
    "day",
    "time",
    "time_index",
    "abundance",
    "biomass_g",
    "mean_length_mm",
    "survival_rate",
    "n_recruits",
    "n_spawners",
)

NUMERIC_ROLES = {
    "abundance",
    "area_m2",
    "biomass_g",
    "csi",
    "day",
    "depth_m",
    "discharge_m3s",
    "feeding_cover",
    "hiding_cover",
    "mean_length_mm",
    "n_recruits",
    "n_spawners",
    "survival_rate",
    "temperature_c",
    "time_index",
    "turbidity_ntu",
    "velocity_ms",
    "wua_m2",
    "x",
    "y",
    "year",
}


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(p)
    if suffix in {".tsv", ".tab"}:
        return pd.read_csv(p, sep="\t")
    return pd.read_csv(p, sep=None, engine="python")


def _rows_from_csv_text(path: str | Path) -> list[list[str]]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    return [
        [cell.strip() for cell in row]
        for row in csv.reader(text.splitlines())
        if any(cell.strip() for cell in row)
    ]


def _matrix_role(rows: list[list[str]]) -> str | None:
    joined = " ".join(cell.upper() for row in rows[:5] for cell in row)
    if "VELOC" in joined:
        return "velocity_ms"
    if "DEPTH" in joined:
        return "depth_m"
    return None


def _try_read_instream_hydraulic_matrix(path: str | Path) -> pd.DataFrame | None:
    rows = _rows_from_csv_text(path)
    role = _matrix_role(rows)
    if role is None:
        return None
    marker_idx = None
    for idx, row in enumerate(rows):
        if any("number of flows" in cell.lower() for cell in row):
            marker_idx = idx
            break
    if marker_idx is None or marker_idx + 1 >= len(rows):
        return None

    flow_row = rows[marker_idx + 1]
    flows: list[float] = []
    for cell in flow_row[1:]:
        if cell == "":
            continue
        try:
            flows.append(float(cell))
        except ValueError:
            break
    if not flows:
        return None

    records: list[dict[str, float | int | str]] = []
    for row in rows[marker_idx + 2 :]:
        if not row or row[0].startswith(";"):
            continue
        try:
            cell_id = int(float(row[0]))
        except ValueError:
            continue
        values: list[float] = []
        for cell in row[1 : len(flows) + 1]:
            try:
                values.append(float(cell))
            except ValueError:
                values.append(np.nan)
        for discharge, value in zip(flows, values, strict=False):
            records.append(
                {
                    "cell_id": cell_id,
                    "discharge_m3s": discharge,
                    role: value,
                }
            )
    if not records:
        return None
    out = pd.DataFrame.from_records(records)
    out.attrs["instream_matrix_role"] = role
    return out


def _detect_roles(df: pd.DataFrame) -> dict[str, str]:
    by_norm = {_norm(str(col)): str(col) for col in df.columns}
    roles: dict[str, str] = {}
    for role, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            found = by_norm.get(_norm(alias))
            if found is not None:
                roles[role] = found
                break
    return roles


def _table_type(roles: dict[str, str]) -> str:
    if {"abundance", "biomass_g", "survival_rate", "n_recruits", "n_spawners"} & roles.keys():
        return "population_summary"
    if {"depth_m", "velocity_ms", "csi", "wua_m2"} & roles.keys():
        return "ibm_habitat_cells"
    return "unknown"


def inspect_instream_exchange(path: str | Path) -> InstreamExchangeInspection:
    """Inspect an inSTREAM/InSALMO/NetLogo CSV/Parquet exchange table."""

    p = Path(path)
    matrix = _try_read_instream_hydraulic_matrix(p)
    if matrix is not None:
        role = str(matrix.attrs["instream_matrix_role"])
        return InstreamExchangeInspection(
            path=str(p),
            n_rows=len(matrix),
            columns=tuple(str(col) for col in matrix.columns),
            table_type="ibm_hydraulic_lookup",
            detected_roles={
                "cell_id": "cell_id",
                "discharge_m3s": "discharge_m3s",
                role: role,
            },
        )

    df = _read_table(p)
    roles = _detect_roles(df)
    table_type = _table_type(roles)
    warnings: list[str] = []
    if table_type == "unknown":
        warnings.append("No population metrics or habitat-cell fields detected.")
    if table_type == "population_summary" and "abundance" not in roles:
        warnings.append("Population summary has no abundance column.")
    if table_type == "ibm_habitat_cells" and "area_m2" not in roles:
        warnings.append("Habitat exchange table has no cell area column.")
    return InstreamExchangeInspection(
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
    *,
    default: object | None = None,
) -> None:
    col = roles.get(role)
    if col is None:
        if default is not None:
            target[role] = default
        return
    if role in NUMERIC_ROLES:
        target[role] = pd.to_numeric(source[col], errors="coerce")
    else:
        target[role] = source[col]


def _normalize_population(df: pd.DataFrame, roles: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    out = pd.DataFrame()
    for role in POPULATION_ROLES:
        _copy_role(df, out, roles, role)

    metric_cols = [col for col in ("abundance", "biomass_g", "survival_rate") if col in out]
    if not metric_cols:
        raise ValueError("inSTREAM population summary needs abundance, biomass, or survival columns.")

    warnings: list[str] = []
    if "species" not in out:
        warnings.append("No species column detected in population summary.")
    if not {"year", "day", "time", "time_index"} & set(out.columns):
        warnings.append("No simulation time column detected in population summary.")
    return out, warnings


def _normalize_habitat(df: pd.DataFrame, roles: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    out = pd.DataFrame()
    for role in HABITAT_ROLES:
        _copy_role(df, out, roles, role)
    if "cell_id" not in out:
        out["cell_id"] = np.arange(len(df), dtype=int)

    warnings: list[str] = []
    if "area_m2" not in out:
        warnings.append("No area column detected in habitat exchange table.")
    if not {"depth_m", "velocity_ms"} & set(out.columns):
        warnings.append("No depth or velocity column detected in habitat exchange table.")
    if not {"depth_m", "velocity_ms", "csi", "wua_m2"} & set(out.columns):
        raise ValueError("inSTREAM habitat exchange needs depth, velocity, CSI, or WUA columns.")
    return out, warnings


def read_instream_exchange(
    path: str | Path,
    *,
    source_key: str = "instream-netlogo",
) -> InstreamImportResult:
    """Normalize an inSTREAM/InSALMO/NetLogo CSV/Parquet exchange table."""

    p = Path(path)
    matrix = _try_read_instream_hydraulic_matrix(p)
    if matrix is not None:
        role = str(matrix.attrs["instream_matrix_role"])
        matrix.insert(0, "source_file", str(p))
        matrix.attrs["openlimno_source_model"] = "inSTREAM/InSALMO/NetLogo exchange"
        matrix.attrs["openlimno_source_key"] = source_key
        matrix.attrs["openlimno_output_table"] = "ibm_hydraulic_lookup"
        return InstreamImportResult(
            table=matrix,
            summary=InstreamImportSummary(
                source_key=source_key,
                output_table="ibm_hydraulic_lookup",
                n_rows=len(matrix),
                detected_roles={
                    "cell_id": "cell_id",
                    "discharge_m3s": "discharge_m3s",
                    role: role,
                },
            ),
        )

    df = _read_table(p)
    roles = _detect_roles(df)
    table_type = _table_type(roles)
    if table_type == "population_summary":
        table, warnings = _normalize_population(df, roles)
    elif table_type == "ibm_habitat_cells":
        table, warnings = _normalize_habitat(df, roles)
    else:
        raise ValueError("Cannot detect inSTREAM/NetLogo exchange columns.")

    table.insert(0, "source_file", str(p))
    table.attrs["openlimno_source_model"] = "inSTREAM/InSALMO/NetLogo exchange"
    table.attrs["openlimno_source_key"] = source_key
    table.attrs["openlimno_output_table"] = table_type
    return InstreamImportResult(
        table=table,
        summary=InstreamImportSummary(
            source_key=source_key,
            output_table=table_type,
            n_rows=len(table),
            detected_roles=roles,
            warnings=tuple(warnings),
        ),
    )


def prepare_instream_habitat_exchange(
    cells: pd.DataFrame,
    *,
    scenario_id: str = "baseline",
    reach_id: str = "reach-1",
) -> InstreamHabitatExportResult:
    """Prepare OpenLimno habitat/hydraulic cells for an IBM CSV exchange package."""

    roles = _detect_roles(cells)
    habitat = pd.DataFrame(index=cells.index)
    for role in HABITAT_ROLES:
        default = None
        if role == "scenario_id":
            default = scenario_id
        elif role == "reach_id":
            default = reach_id
        _copy_role(cells, habitat, roles, role, default=default)
    if "cell_id" not in habitat:
        habitat["cell_id"] = np.arange(len(cells), dtype=int)
    if "area_m2" not in habitat:
        raise ValueError("IBM habitat export needs an area_m2/area column.")
    if not {"depth_m", "velocity_ms", "csi", "wua_m2"} & set(habitat.columns):
        raise ValueError("IBM habitat export needs depth, velocity, CSI, or WUA columns.")

    group_cols = [
        col
        for col in ("scenario_id", "reach_id", "discharge_m3s", "time_index", "time")
        if col in habitat
    ]
    agg: dict[str, tuple[str, str]] = {
        "area_m2": ("area_m2", "sum"),
        "n_cells": ("cell_id", "size"),
    }
    if "depth_m" in habitat:
        agg["mean_depth_m"] = ("depth_m", "mean")
    if "velocity_ms" in habitat:
        agg["mean_velocity_ms"] = ("velocity_ms", "mean")
    if "wua_m2" in habitat:
        agg["wua_m2"] = ("wua_m2", "sum")
    if "csi" in habitat:
        agg["mean_csi"] = ("csi", "mean")

    flow_summary = habitat.groupby(group_cols, dropna=False).agg(**agg).reset_index()
    manifest = pd.DataFrame(
        [
            {
                "table": "instream_habitat_cells",
                "rows": len(habitat),
                "description": "Cell-level hydraulic/habitat exchange table for IBM workflows.",
            },
            {
                "table": "instream_flow_summary",
                "rows": len(flow_summary),
                "description": "Reach/flow/time summary derived from habitat cells.",
            },
        ]
    )
    for table in (habitat, flow_summary, manifest):
        table.attrs["openlimno_source_model"] = "OpenLimno IBM exchange"
        table.attrs["openlimno_source_key"] = "instream-netlogo"
    habitat.attrs["openlimno_output_table"] = "ibm_habitat_cells"
    flow_summary.attrs["openlimno_output_table"] = "ibm_flow_summary"
    manifest.attrs["openlimno_output_table"] = "ibm_exchange_manifest"
    return InstreamHabitatExportResult(
        habitat_cells=habitat,
        flow_summary=flow_summary,
        manifest=manifest,
    )


def write_instream_exchange(
    cells: pd.DataFrame,
    output_dir: str | Path,
    *,
    scenario_id: str = "baseline",
    reach_id: str = "reach-1",
) -> InstreamHabitatExportResult:
    """Write an inSTREAM/NetLogo CSV exchange package from OpenLimno cells."""

    result = prepare_instream_habitat_exchange(
        cells,
        scenario_id=scenario_id,
        reach_id=reach_id,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tables = {
        "instream_habitat_cells": result.habitat_cells,
        "instream_flow_summary": result.flow_summary,
        "instream_exchange_manifest": result.manifest,
    }
    paths: dict[str, str] = {}
    for stem, table in tables.items():
        target = out / f"{stem}.csv"
        table.to_csv(target, index=False)
        paths[stem] = str(target)
    return InstreamHabitatExportResult(
        habitat_cells=result.habitat_cells,
        flow_summary=result.flow_summary,
        manifest=result.manifest,
        paths=paths,
    )


__all__ = [
    "InstreamExchangeInspection",
    "InstreamHabitatExportResult",
    "InstreamImportResult",
    "InstreamImportSummary",
    "inspect_instream_exchange",
    "prepare_instream_habitat_exchange",
    "read_instream_exchange",
    "write_instream_exchange",
]
