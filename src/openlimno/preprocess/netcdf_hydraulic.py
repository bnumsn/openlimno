"""CF/UGRID-style NetCDF hydraulic result importer.

This adapter targets the common open exchange layer used by Delft3D FM /
D-Flow FM, converted TELEMAC/BASEMENT/iRIC outputs, and other hydraulic models
that expose cell-centred depth, water level, velocity, coordinates, and areas in
NetCDF. It is intentionally heuristic: the inspector reports what was detected,
and the importer only emits a flat ``hydraulic_cells`` staging table.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr


@dataclass(frozen=True)
class NetCDFVariableInfo:
    """Small variable metadata row for NetCDF inspection."""

    name: str
    dims: tuple[str, ...]
    shape: tuple[int, ...]
    dtype: str
    role: str | None = None


@dataclass(frozen=True)
class NetCDFHydraulicInspection:
    """Diagnostic view of a CF/UGRID hydraulic NetCDF file."""

    path: str
    variables: tuple[NetCDFVariableInfo, ...]
    selected_depth: str | None
    selected_water_surface: str | None
    selected_velocity: str | None
    selected_u: str | None
    selected_v: str | None
    selected_x: str | None
    selected_y: str | None
    selected_area: str | None
    n_cells: int | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class NetCDFHydraulicImportSummary:
    """Small import report for CF/UGRID NetCDF hydraulics."""

    source_key: str
    n_cells: int
    time_index: int | None
    depth_name: str | None
    velocity_name: str | None
    water_surface_name: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class NetCDFHydraulicImportResult:
    """Hydraulic-cell staging table plus import metadata."""

    table: pd.DataFrame
    summary: NetCDFHydraulicImportSummary


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _data_vars(ds: xr.Dataset) -> list[str]:
    return list(ds.variables)


def _standard_name(ds: xr.Dataset, name: str) -> str:
    return _norm(str(ds[name].attrs.get("standard_name", "")))


def _long_name(ds: xr.Dataset, name: str) -> str:
    return _norm(str(ds[name].attrs.get("long_name", "")))


def _score_var(
    ds: xr.Dataset,
    name: str,
    *,
    any_tokens: tuple[str, ...],
    all_tokens: tuple[str, ...] = (),
    excludes: tuple[str, ...] = (),
    standard_tokens: tuple[str, ...] = (),
) -> int | None:
    haystack = _norm(name) + _standard_name(ds, name) + _long_name(ds, name)
    if any(_norm(token) in haystack for token in excludes):
        return None
    if any_tokens and not any(_norm(token) in haystack for token in any_tokens):
        return None
    if all_tokens and not all(_norm(token) in haystack for token in all_tokens):
        return None
    score = 0
    leaf = _norm(name.split("/")[-1])
    for token in any_tokens:
        tok = _norm(token)
        if tok == leaf:
            score += 20
        elif tok in leaf:
            score += 8
        elif tok in haystack:
            score += 3
    for token in standard_tokens:
        if _norm(token) in _standard_name(ds, name):
            score += 20
    return score


def _find_var(
    ds: xr.Dataset,
    *,
    any_tokens: tuple[str, ...],
    all_tokens: tuple[str, ...] = (),
    excludes: tuple[str, ...] = (),
    standard_tokens: tuple[str, ...] = (),
) -> str | None:
    candidates: list[tuple[int, str]] = []
    for name in _data_vars(ds):
        score = _score_var(
            ds,
            name,
            any_tokens=any_tokens,
            all_tokens=all_tokens,
            excludes=excludes,
            standard_tokens=standard_tokens,
        )
        if score is not None:
            candidates.append((score, name))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _find_x(ds: xr.Dataset) -> str | None:
    return _find_var(
        ds,
        any_tokens=("face_x", "flowelem_xcc", "cell_x", "mesh2d_facex", "x"),
        excludes=("velocity", "ucx", "mesh2d_ucx", "bounds", "node", "edge"),
        standard_tokens=("projection_x_coordinate", "longitude"),
    )


def _find_y(ds: xr.Dataset) -> str | None:
    return _find_var(
        ds,
        any_tokens=("face_y", "flowelem_ycc", "cell_y", "mesh2d_facey", "y"),
        excludes=("velocity", "ucy", "mesh2d_ucy", "bounds", "node", "edge"),
        standard_tokens=("projection_y_coordinate", "latitude"),
    )


def _find_roles(ds: xr.Dataset) -> dict[str, str | None]:
    depth = _find_var(
        ds,
        any_tokens=("waterdepth", "water_depth", "depth", "mesh2d_waterdepth"),
        excludes=("bed", "bottom", "node", "face_nodes", "bounds", "minimum", "maximum"),
        standard_tokens=("sea_floor_depth_below_sea_surface",),
    )
    water_surface = _find_var(
        ds,
        any_tokens=("waterlevel", "water_level", "surfaceelevation", "s1", "watersurface"),
        excludes=("bed", "bottom", "minimum", "maximum"),
        standard_tokens=("water_surface_height_above_reference_datum", "sea_surface_height"),
    )
    velocity = _find_var(
        ds,
        any_tokens=("velocitymagnitude", "currentspeed", "current_speed", "ucmaga", "ucmag", "speed"),
        excludes=("wind", "minimum", "maximum", "normal"),
    )
    u = _find_var(
        ds,
        any_tokens=("ucxa", "mesh2d_ucxa", "uvelocity", "xvelocity", "ucx", "mesh2d_ucx"),
        excludes=("wind", "minimum", "maximum"),
    )
    v = _find_var(
        ds,
        any_tokens=("ucya", "mesh2d_ucya", "vvelocity", "yvelocity", "ucy", "mesh2d_ucy"),
        excludes=("wind", "minimum", "maximum"),
    )
    area = _find_var(
        ds,
        any_tokens=("flowelemba", "facearea", "cellarea", "area", "mesh2d_flowelem_ba"),
        excludes=("node", "edge", "bounds"),
    )
    return {
        "depth": depth,
        "water_surface": water_surface,
        "velocity": velocity,
        "u": u,
        "v": v,
        "x": _find_x(ds),
        "y": _find_y(ds),
        "area": area,
    }


def _time_dim(da: xr.DataArray) -> str | None:
    for dim in da.dims:
        if _norm(dim) == "time" or _norm(dim).endswith("time"):
            return str(dim)
        coord = da.coords.get(dim)
        if coord is not None and np.issubdtype(coord.dtype, np.datetime64):
            return str(dim)
    return None


def _resolve_time_index(n_time: int, time_index: int | None) -> int:
    if n_time <= 0:
        raise ValueError("NetCDF result dataset has zero time steps.")
    idx = -1 if time_index is None else time_index
    if idx < 0:
        idx = n_time + idx
    if idx < 0 or idx >= n_time:
        raise IndexError(f"time_index out of range: {time_index} for {n_time} time steps.")
    return idx


def _select_time(da: xr.DataArray, time_index: int | None) -> tuple[xr.DataArray, int | None]:
    dim = _time_dim(da)
    if dim is None:
        return da, None
    idx = _resolve_time_index(int(da.sizes[dim]), time_index)
    return da.isel({dim: idx}), idx


def _spatial_values(da: xr.DataArray, time_index: int | None) -> tuple[np.ndarray, int | None]:
    selected, idx = _select_time(da, time_index)
    values = np.asarray(selected.values, dtype=float)
    while values.ndim > 1 and values.shape[0] == 1:
        values = values[0]
    return values.reshape(-1), idx


def _infer_n_cells(ds: xr.Dataset, roles: dict[str, str | None]) -> int:
    for role in ("depth", "water_surface", "velocity", "u", "v", "area", "x", "y"):
        name = roles.get(role)
        if name is None:
            continue
        da = ds[name]
        selected, _ = _select_time(da, None)
        values = np.asarray(selected.values)
        if values.ndim == 0:
            continue
        return int(values.size)
    raise ValueError("Cannot infer NetCDF hydraulic cell count from detected variables.")


def _coordinate_values(
    ds: xr.Dataset,
    roles: dict[str, str | None],
    n_cells: int,
) -> tuple[np.ndarray | None, np.ndarray | None, tuple[str, ...]]:
    warnings: list[str] = []
    x_name = roles.get("x")
    y_name = roles.get("y")
    if x_name is None or y_name is None:
        warnings.append("No cell-centre x/y coordinate variables detected.")
        return None, None, tuple(warnings)

    x = np.asarray(ds[x_name].values, dtype=float)
    y = np.asarray(ds[y_name].values, dtype=float)
    if x.ndim == 1 and y.ndim == 1 and x.size * y.size == n_cells and x.size != y.size:
        xx, yy = np.meshgrid(x, y)
        return xx.reshape(-1), yy.reshape(-1), tuple(warnings)
    if x.size == n_cells and y.size == n_cells:
        return x.reshape(-1), y.reshape(-1), tuple(warnings)

    warnings.append(
        f"Coordinate variables {x_name!r}/{y_name!r} are not cell-aligned; skipped."
    )
    return None, None, tuple(warnings)


def _time_label(ds: xr.Dataset, selected_idx: int | None) -> str | None:
    if selected_idx is None:
        return None
    for name in ("time", "mesh2d_time"):
        if name not in ds.coords and name not in ds.variables:
            continue
        arr = np.asarray(ds[name].values)
        if arr.ndim == 0 or len(arr) <= selected_idx:
            continue
        return str(arr[selected_idx])
    return None


def inspect_netcdf_hydraulic(path: str | Path) -> NetCDFHydraulicInspection:
    """Inspect a NetCDF file for hydraulic-cell import candidates."""

    p = Path(path)
    warnings: list[str] = []
    with xr.open_dataset(p) as ds:
        roles = _find_roles(ds)
        infos = []
        for name in _data_vars(ds):
            role = next((key for key, value in roles.items() if value == name), None)
            infos.append(
                NetCDFVariableInfo(
                    name=name,
                    dims=tuple(str(dim) for dim in ds[name].dims),
                    shape=tuple(int(x) for x in ds[name].shape),
                    dtype=str(ds[name].dtype),
                    role=role,
                )
            )
        try:
            n_cells = _infer_n_cells(ds, roles)
        except ValueError as e:
            n_cells = None
            warnings.append(str(e))

    return NetCDFHydraulicInspection(
        path=str(p),
        variables=tuple(infos),
        selected_depth=roles["depth"],
        selected_water_surface=roles["water_surface"],
        selected_velocity=roles["velocity"],
        selected_u=roles["u"],
        selected_v=roles["v"],
        selected_x=roles["x"],
        selected_y=roles["y"],
        selected_area=roles["area"],
        n_cells=n_cells,
        warnings=tuple(warnings),
    )


def read_netcdf_hydraulic(
    path: str | Path,
    *,
    source_key: str = "delft3d-netcdf",
    time_index: int | None = None,
) -> NetCDFHydraulicImportResult:
    """Read CF/UGRID-style NetCDF hydraulic results into ``hydraulic_cells``."""

    p = Path(path)
    warnings: list[str] = []
    with xr.open_dataset(p) as ds:
        roles = _find_roles(ds)
        n_cells = _infer_n_cells(ds, roles)
        rows: dict[str, Any] = {
            "source_file": str(p),
            "flow_area": p.stem,
            "cell_id": np.arange(n_cells, dtype=int),
        }

        x, y, coord_warnings = _coordinate_values(ds, roles, n_cells)
        warnings.extend(coord_warnings)
        if x is not None and y is not None:
            rows["x"] = x
            rows["y"] = y

        resolved_indexes: list[int] = []
        depth_name = roles["depth"]
        if depth_name is not None:
            values, idx = _spatial_values(ds[depth_name], time_index)
            if values.size == n_cells:
                rows["depth_m"] = values
                if idx is not None:
                    resolved_indexes.append(idx)
            else:
                warnings.append(f"Depth variable {depth_name!r} is not cell-aligned; skipped.")
        else:
            warnings.append("No depth variable detected.")

        wse_name = roles["water_surface"]
        if wse_name is not None:
            values, idx = _spatial_values(ds[wse_name], time_index)
            if values.size == n_cells:
                rows["water_surface_m"] = values
                if idx is not None:
                    resolved_indexes.append(idx)
            else:
                warnings.append(
                    f"Water-surface variable {wse_name!r} is not cell-aligned; skipped."
                )

        velocity_name = roles["velocity"]
        if velocity_name is not None:
            values, idx = _spatial_values(ds[velocity_name], time_index)
            if values.size == n_cells:
                rows["velocity_ms"] = values
                if idx is not None:
                    resolved_indexes.append(idx)
            else:
                warnings.append(f"Velocity variable {velocity_name!r} is not cell-aligned; skipped.")
                velocity_name = None
        if "velocity_ms" not in rows:
            if roles["u"] is not None and roles["v"] is not None:
                u, idx_u = _spatial_values(ds[roles["u"]], time_index)
                v, idx_v = _spatial_values(ds[roles["v"]], time_index)
                if u.size == n_cells and v.size == n_cells:
                    rows["velocity_ms"] = np.sqrt(u**2 + v**2)
                    for idx in (idx_u, idx_v):
                        if idx is not None:
                            resolved_indexes.append(idx)
                    velocity_name = f"{roles['u']}+{roles['v']}"
                else:
                    warnings.append("U/V velocity component variables are not cell-aligned; skipped.")
            else:
                warnings.append("No velocity magnitude or U/V component variables detected.")

        area_name = roles["area"]
        if area_name is not None:
            values, _ = _spatial_values(ds[area_name], None)
            if values.size == n_cells:
                rows["area_m2"] = values
            else:
                warnings.append(f"Area variable {area_name!r} is not cell-aligned; skipped.")
        else:
            warnings.append("No cell-area variable detected; WUA needs area_m2.")

        resolved_idx = resolved_indexes[0] if resolved_indexes else None
        if any(idx != resolved_idx for idx in resolved_indexes[1:]):
            warnings.append(f"NetCDF variables resolved to different time indexes: {resolved_indexes}.")
        rows["time_index"] = resolved_idx
        rows["time"] = _time_label(ds, resolved_idx)

    table = pd.DataFrame(rows)
    table.attrs["openlimno_source_model"] = "CF/UGRID NetCDF hydraulics"
    table.attrs["openlimno_source_key"] = source_key
    table.attrs["openlimno_output_table"] = "hydraulic_cells"
    return NetCDFHydraulicImportResult(
        table=table,
        summary=NetCDFHydraulicImportSummary(
            source_key=source_key,
            n_cells=n_cells,
            time_index=resolved_idx,
            depth_name=depth_name,
            velocity_name=velocity_name,
            water_surface_name=wse_name,
            warnings=tuple(warnings),
        ),
    )


__all__ = [
    "NetCDFHydraulicImportResult",
    "NetCDFHydraulicImportSummary",
    "NetCDFHydraulicInspection",
    "NetCDFVariableInfo",
    "inspect_netcdf_hydraulic",
    "read_netcdf_hydraulic",
]
