"""External ecohydraulic model interoperability registry.

OpenLimno's core value is ecological post-processing and reproducibility, not
owning every hydraulic solver. This module gives the CLI and downstream plugins
one stable place to ask: "can this external model output be imported into
WEDM-like tables today, or is it a planned/plugin integration?"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from .habitat_exchange import read_habitat_exchange
from .hecras_hdf import read_hecras_hdf
from .instream_netlogo import read_instream_exchange
from .legacy import read_hecras_geometry, read_river2d_cdg
from .mike import MIKE_1D_SUFFIXES, MIKE_DFS_SUFFIXES, read_mike_file
from .netcdf_hydraulic import read_netcdf_hydraulic
from .telemac_slf import read_telemac_selafin

InteropStatus = Literal["implemented", "planned", "plugin"]


@dataclass(frozen=True)
class ExternalModelSupport:
    """One external model/data-family entry in the OpenLimno interop registry."""

    key: str
    model: str
    input_kind: str
    status: InteropStatus
    extensions: tuple[str, ...]
    output_table: str
    notes: str


@dataclass(frozen=True)
class ExternalModelImportResult:
    """Imported table plus source metadata and warnings."""

    source_key: str
    model: str
    input_kind: str
    table: pd.DataFrame
    warnings: tuple[str, ...] = ()


EXTERNAL_MODEL_SUPPORT: tuple[ExternalModelSupport, ...] = (
    ExternalModelSupport(
        key="hecras-geometry",
        model="HEC-RAS",
        input_kind="geometry cross-sections",
        status="implemented",
        extensions=(".g01", ".g02", ".g03", ".g04", ".g05", ".g06", ".g07", ".g08", ".g09"),
        output_table="cross_section_points",
        notes="Best-effort X1/GR geometry reader; hydraulic structures are not imported.",
    ),
    ExternalModelSupport(
        key="river2d-cdg",
        model="River2D",
        input_kind="bed mesh nodes",
        status="implemented",
        extensions=(".cdg", ".bed"),
        output_table="mesh_nodes",
        notes="Best-effort ASCII node reader with River2D 2002 CDG node/result fields and element topology API.",
    ),
    ExternalModelSupport(
        key="hecras-hdf",
        model="HEC-RAS",
        input_kind="2D hydraulic results",
        status="implemented",
        extensions=(".hdf", ".h5"),
        output_table="hydraulic_cells",
        notes="MVP cell-aligned import of depth, velocity, WSE, and cell-center geometry.",
    ),
    ExternalModelSupport(
        key="telemac-slf",
        model="TELEMAC-MASCARET",
        input_kind="2D/3D Selafin results",
        status="implemented",
        extensions=(".slf", ".selafin"),
        output_table="hydraulic_cells",
        notes="Lightweight native Selafin reader for 2D node results averaged onto elements.",
    ),
    ExternalModelSupport(
        key="delft3d-netcdf",
        model="Delft3D FM / D-Flow FM / CF-UGRID",
        input_kind="NetCDF hydraulic results",
        status="implemented",
        extensions=(".nc",),
        output_table="hydraulic_cells",
        notes="Heuristic CF/UGRID cell-centred depth/WSE/velocity/area adapter.",
    ),
    ExternalModelSupport(
        key="mike-dfs",
        model="MIKE 21 / MIKE FM",
        input_kind="DFS/DFSU/mesh results",
        status="implemented",
        extensions=MIKE_DFS_SUFFIXES,
        output_table="mike_staging",
        notes="Optional adapter via DHI mikeio; imports DFSU/DFS2 hydraulics and DFS time series.",
    ),
    ExternalModelSupport(
        key="mike-1d",
        model="MIKE 1D / MIKE 11 / MIKE+",
        input_kind="1D results and cross-sections",
        status="implemented",
        extensions=MIKE_1D_SUFFIXES,
        output_table="mike_staging",
        notes="Optional adapter via DHI mikeio1d; imports RES1D time series and XNS11 cross-sections.",
    ),
    ExternalModelSupport(
        key="habby-csv",
        model="HABBY / CASiMiR / habitat tools",
        input_kind="habitat cell or WUA exchange tables",
        status="implemented",
        extensions=(".csv", ".tsv", ".tab", ".txt", ".parquet"),
        output_table="habitat_exchange",
        notes="Alias-based importer for cell CSI/WUA and summary WUA tables.",
    ),
    ExternalModelSupport(
        key="instream-netlogo",
        model="inSTREAM / NetLogo IBM",
        input_kind="habitat-cell and population-summary exchange tables",
        status="implemented",
        extensions=(".csv", ".tsv", ".tab", ".parquet"),
        output_table="ibm_exchange",
        notes="CSV/Parquet bridge for OpenLimno habitat cells and population summaries.",
    ),
)

_SUPPORT_BY_KEY = {entry.key: entry for entry in EXTERNAL_MODEL_SUPPORT}
_HECRAS_GEOM_RE = re.compile(r"\.g\d{2,3}$", re.IGNORECASE)
_INSTREAM_TABLE_TOKENS = (
    "abundance",
    "ibm",
    "insalmo",
    "instream",
    "netlogo",
    "population",
)
_HABITAT_TABLE_TOKENS = (
    "casimir",
    "habby",
    "habitat",
    "hsi",
    "spu",
    "suitability",
    "wua",
    "detailled_mesh",
    "detailed_mesh",
)


def list_external_model_support() -> tuple[ExternalModelSupport, ...]:
    """Return the supported/planned external-model registry."""

    return EXTERNAL_MODEL_SUPPORT


def infer_external_model(path: str | Path) -> str | None:
    """Infer an interop registry key from a file extension/name."""

    p = Path(path)
    suffix = p.suffix.lower()
    name = p.name.lower()
    if _HECRAS_GEOM_RE.search(name):
        return "hecras-geometry"
    if suffix in {".cdg", ".bed"}:
        return "river2d-cdg"
    if suffix in {".hdf", ".h5"}:
        return "hecras-hdf"
    if suffix in {".slf", ".selafin"}:
        return "telemac-slf"
    if suffix == ".nc":
        return "delft3d-netcdf"
    if suffix in set(MIKE_DFS_SUFFIXES):
        return "mike-dfs"
    if suffix in set(MIKE_1D_SUFFIXES):
        return "mike-1d"
    if suffix in {".csv", ".tsv", ".tab", ".parquet"} and any(
        token in name for token in _INSTREAM_TABLE_TOKENS
    ):
        return "instream-netlogo"
    if suffix in {".csv", ".tsv", ".tab", ".txt", ".parquet"} and any(
        token in name for token in _HABITAT_TABLE_TOKENS
    ):
        return "habby-csv"
    return None


def read_external_model(
    path: str | Path,
    source: str = "auto",
    *,
    flow_area: str | None = None,
    time_index: int | None = None,
) -> ExternalModelImportResult:
    """Read an external model file into a tabular WEDM staging format.

    Only registry entries marked ``implemented`` are currently importable.
    ``planned`` and ``plugin`` entries raise a clear ``NotImplementedError`` so
    command-line users see the roadmap status instead of a misleading parser
    failure.
    """

    p = Path(path)
    source_key = infer_external_model(p) if source == "auto" else source
    if source_key is None:
        raise ValueError(f"Cannot infer external model format from {p.name!r}; pass --source.")
    entry = _SUPPORT_BY_KEY.get(source_key)
    if entry is None:
        raise ValueError(
            f"Unknown external model source {source_key!r}. "
            f"Known: {', '.join(sorted(_SUPPORT_BY_KEY))}"
        )
    if entry.status != "implemented":
        raise NotImplementedError(
            f"{entry.key} ({entry.model} {entry.input_kind}) is {entry.status}, "
            f"not implemented in core OpenLimno yet. {entry.notes}"
        )

    warnings: tuple[str, ...]
    if source_key == "hecras-geometry":
        table = read_hecras_geometry(p)
        warnings = (
            "HEC-RAS geometry import is best-effort; bridges, culverts, storage areas, "
            "roughness strips, and hydraulic results are not imported.",
        )
    elif source_key == "hecras-hdf":
        imported = read_hecras_hdf(p, flow_area=flow_area, time_index=time_index)
        table = imported.table
        warnings = imported.summary.warnings
    elif source_key == "river2d-cdg":
        table = read_river2d_cdg(p)
        warnings = (
            "River2D .cdg import returns node-level mesh/hydraulic fields. "
            "Use read_river2d_elements() when triangular topology is needed; "
            "habitat suitability layers are imported from exported CSV tables.",
        )
    elif source_key in {"mike-dfs", "mike-1d"}:
        imported = read_mike_file(p, time_index=time_index)
        table = imported.table
        warnings = imported.summary.warnings
    elif source_key == "delft3d-netcdf":
        imported = read_netcdf_hydraulic(p, source_key=source_key, time_index=time_index)
        table = imported.table
        warnings = imported.summary.warnings
    elif source_key == "telemac-slf":
        imported = read_telemac_selafin(p, source_key=source_key, time_index=time_index)
        table = imported.table
        warnings = imported.summary.warnings
    elif source_key == "habby-csv":
        imported = read_habitat_exchange(p, source_key=source_key)
        table = imported.table
        warnings = imported.summary.warnings
    elif source_key == "instream-netlogo":
        imported = read_instream_exchange(p, source_key=source_key)
        table = imported.table
        warnings = imported.summary.warnings
    else:  # pragma: no cover - guarded by entry.status above
        raise NotImplementedError(source_key)

    table.attrs["openlimno_source_model"] = entry.model
    table.attrs["openlimno_source_key"] = entry.key
    table.attrs.setdefault("openlimno_output_table", entry.output_table)
    return ExternalModelImportResult(
        source_key=entry.key,
        model=entry.model,
        input_kind=entry.input_kind,
        table=table,
        warnings=warnings,
    )


__all__ = [
    "EXTERNAL_MODEL_SUPPORT",
    "ExternalModelImportResult",
    "ExternalModelSupport",
    "infer_external_model",
    "list_external_model_support",
    "read_external_model",
]
